"""Estudo de eventos: divergência de RSI (alta/baixa) e exaustão de Bollinger (2,0σ e 2,5σ) em 10 anos de histórico (cache de backtest_exits.py).
Retorno futuro do fecho do sinal (5, 20, 60 dias) MENOS a média desse horizonte em todos os dias da mesma ação (retira o efeito de a ação ser vencedora).
LIMITES: universo = ações que HOJE passam o crivo (viés de sobrevivência); sinais com espaçamento mínimo de 10 dias por ação (menos sobreposição); sem custos; t-stats ingénuos (eventos correlacionados no tempo/mercado)."""
import math, pathlib
import numpy as np, pandas as pd

P = pd.read_pickle("research/prices.pkl")
W = 5          # janela do pivô (confirmado W dias depois: sem olhar para o futuro)
HZS = (5, 20, 60)


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up, dn = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    au = pd.Series(up).ewm(alpha=1 / n, adjust=False).mean().values
    ad = pd.Series(dn).ewm(alpha=1 / n, adjust=False).mean().values
    return 100 - 100 / (1 + au / np.where(ad == 0, 1e-12, ad))


def pivots(c, kind):
    """índices dos pivôs (mínimos ou máximos locais em ±W dias), só confirmados W dias depois."""
    out = []
    for i in range(W, len(c) - W):
        seg = c[i - W:i + W + 1]
        if (kind == "low" and c[i] == seg.min() and (seg == c[i]).sum() == 1) or (kind == "high" and c[i] == seg.max() and (seg == c[i]).sum() == 1):
            out.append(i)
    return out


events = {"RSI alta": [], "RSI baixa": [], "Bollinger 2,0σ": [], "Bollinger 2,5σ": [], "Bollinger 2,5σ + RSI<30": []}
base = {h: [] for h in HZS}
for s, x in P.items():
    c = x["Close"].values.astype(float); n = len(c)
    if n < 600:
        continue
    r = rsi(c)
    fwd = {h: np.full(n, np.nan) for h in HZS}
    for h in HZS:
        fwd[h][:n - h] = c[h:] / c[:n - h] - 1
    mu = {h: np.nanmean(fwd[h]) for h in HZS}
    for h in HZS:
        base[h].append(fwd[h][~np.isnan(fwd[h])])

    def add(name, t):
        for h in HZS:
            if t < n - h and not np.isnan(fwd[h][t]):
                events[name].append((s, t, h, fwd[h][t] - mu[h], fwd[h][t] > 0, (t / n)))

    # divergências: sinal no dia de confirmação do 2.º pivô (i2 + W)
    for kind, name in (("low", "RSI alta"), ("high", "RSI baixa")):
        pv = pivots(c, kind); last = -99
        for a, b in zip(pv[:-1], pv[1:]):
            if not 5 <= b - a <= 60:
                continue
            t = b + W
            if t >= n or t - last < 10:
                continue
            if kind == "low" and c[b] < c[a] * 0.99 and r[b] > r[a] + 2 and r[a] < 40:
                add(name, t); last = t
            if kind == "high" and c[b] > c[a] * 1.01 and r[b] < r[a] - 2 and r[a] > 60:
                add(name, t); last = t
    # Bollinger sobre 20 dias
    sma = pd.Series(c).rolling(20).mean().values; sd = pd.Series(c).rolling(20).std().values
    for k, name in ((2.0, "Bollinger 2,0σ"), (2.5, "Bollinger 2,5σ")):
        below = c <= sma - k * sd; last = -99
        for t in range(21, n):
            if below[t] and not below[t - 1] and t - last >= 10:
                add(name, t); last = t
                if k == 2.5 and r[t] < 30:
                    add("Bollinger 2,5σ + RSI<30", t)

print(f"ações: {len(P)} | período: ~10 anos | pivô ±{W} dias\n")
print("Retorno futuro EXCESSO (vs. média da própria ação em todos os dias) e % de subidas; base = todos os dias")
print(f"{'sinal':26s} {'h':>3s} {'n':>6s} {'excesso':>8s} {'mediana':>8s} {'%sobe':>6s} {'base%':>6s} {'t':>5s} {'1.ª met.':>9s} {'2.ª met.':>9s}")
allb = {h: np.concatenate(base[h]) for h in HZS}
for name, ev in events.items():
    df = pd.DataFrame(ev, columns=["s", "t", "h", "ex", "up", "pos"])
    for h in HZS:
        g = df[df.h == h]
        if len(g) < 30:
            print(f"{name:26s} {h:3d} {len(g):6d}  (poucos eventos)"); continue
        t = g.ex.mean() / (g.ex.std() / math.sqrt(len(g)))
        a = g[g.pos < .5].ex.mean() * 100; b = g[g.pos >= .5].ex.mean() * 100
        print(f"{name:26s} {h:3d} {len(g):6d} {g.ex.mean()*100:7.2f}% {g.ex.median()*100:7.2f}% {g.up.mean()*100:5.1f}% {(allb[h] > 0).mean()*100:5.1f}% {t:5.1f} {a:8.2f}% {b:8.2f}%")
