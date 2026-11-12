"""Backtest de regras de saída (só preço). Uso: python research/backtest_exits.py
Entradas simuladas a cada 10 dias úteis em ~10 anos de histórico das ações com análise completa; horizonte máx. 252 dias.
LIMITES: universo = ações que HOJE passam o crivo (viés de sobrevivência e de seleção: os retornos absolutos são otimistas; só a comparação ENTRE regras e a calibração valem);
alvos de analistas históricos não existem no Yahoo (não se testam); sem custos nem impostos; cash a 0%; entradas sobrepostas (amostras correlacionadas)."""
import json, math, pathlib, sys, time
import numpy as np, pandas as pd, yfinance as yf

H = 252
D = json.loads(pathlib.Path("data.js").read_text(encoding="utf-8")[len("window.DATA="):])
syms = list(D["tickers"])
OUT = pathlib.Path("research/prices.pkl")
if OUT.exists():
    P = pd.read_pickle(OUT)
else:
    P = {}
    for i in range(0, len(syms), 40):
        part = syms[i:i + 40]
        for tries in range(3):
            try:
                df = yf.download(part, period="10y", auto_adjust=True, progress=False, threads=True, group_by="ticker")
                break
            except Exception as e:
                print("erro", e); time.sleep(10)
        for s in part:
            try:
                x = df[s][["Open", "High", "Low", "Close"]].dropna()
                if len(x) > 600:
                    P[s] = x
            except Exception:
                pass
        print(f"{min(i + 40, len(syms))}/{len(syms)} · {len(P)} com histórico", flush=True)
    pd.to_pickle(P, OUT)
print(len(P), "ações")
Phi = lambda x: .5 * (1 + math.erf(x / math.sqrt(2)))

def first(mask):
    i = np.argmax(mask)
    return i if mask[i] else None

rules = {}
def add(name, r, d):
    rules.setdefault(name, []).append((r, d))
calib = []  # (x, hit, above52, model)
for s, x in P.items():
    o, h, l, c = (x[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(c)
    lr = np.diff(np.log(c))
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    for i in range(260, n - H - 1, 10):
        p0 = c[i]
        sig = lr[i - 252:i].std() * math.sqrt(252)
        if not (0.05 < sig < 1.5):
            continue
        atr = tr[i - 14:i].mean()
        hi52 = h[i - 251:i + 1].max()
        wh, wl, wo, wc = h[i + 1:i + 1 + H], l[i + 1:i + 1 + H], o[i + 1:i + 1 + H], c[i + 1:i + 1 + H]
        ret = lambda px: px / p0 - 1

        def barrier(T=None, S=None, trail=None):
            """devolve (retorno, dias). T alvo fixo, S stop fixo, trail = k·ATR abaixo do máximo de fecho desde a entrada."""
            cm = np.maximum.accumulate(np.concatenate([[p0], wc]))[:-1]
            stop = np.full(H, -np.inf)
            if S is not None:
                stop = np.maximum(stop, np.full(H, S))
            if trail is not None:
                stop = np.maximum(stop, cm - trail * atr)
            it = first(wh >= T) if T is not None else None
            isx = first(wl <= stop)
            if isx is not None and (it is None or isx <= it):
                return ret(min(wo[isx], stop[isx]) if np.isfinite(stop[isx]) else wc[isx]), isx + 1
            if it is not None:
                return ret(T), it + 1
            return ret(wc[-1]), H

        add("Manter 12 meses", ret(wc[-1]), H)
        for pct in (10, 20, 30):
            add(f"Alvo +{pct}%", *barrier(T=p0 * (1 + pct / 100)))
        add("Alvo +20%, stop -12%", *barrier(T=p0 * 1.2, S=p0 * .88))
        add("Alvo = máx. 52s (mín. +5%)", *barrier(T=max(hi52, p0 * 1.05)))
        t50 = p0 * math.exp(0.674 * sig)
        add("Alvo 50% prob. (vol)", *barrier(T=t50))
        add("Alvo 25% prob. (vol)", *barrier(T=p0 * math.exp(1.15 * sig)))
        for k in (2, 3, 4, 6):
            add(f"Trailing {k}×ATR", *barrier(trail=k))
        r1, d1 = barrier(T=t50, trail=3)
        # metade no alvo 50%, metade com trailing 3×ATR (aprox.: a 2.ª metade segue o trailing; se o alvo bate, 1.ª metade sai nesse dia)
        it = first(wh >= t50)
        if it is None:
            add("½ no alvo 50% + ½ trailing 3×ATR", *barrier(trail=3))
        else:
            cm = np.maximum.accumulate(np.concatenate([[p0], wc]))[:-1]
            stop = cm - 3 * atr
            isx = first(wl <= stop)
            r2 = ret(min(wo[isx], stop[isx])) if isx is not None else ret(wc[-1])
            d2 = (isx + 1) if isx is not None else H
            if isx is not None and isx <= it:  # stop antes do alvo: sai tudo
                add("½ no alvo 50% + ½ trailing 3×ATR", r2, d2)
            else:
                add("½ no alvo 50% + ½ trailing 3×ATR", .5 * ret(t50) + .5 * r2, (it + 1 + d2) / 2)
        for xx in (0.10, 0.20, 0.30, 0.40):
            b = p0 * (1 + xx)
            calib.append((xx, bool((wh >= b).any()), b > hi52, 2 * (1 - Phi(math.log(1 + xx) / sig)), math.log(1 + xx) / sig))

print("\n=== REGRAS DE SAÍDA (todas as entradas; retorno sobre 12 meses, cash a 0% depois de sair) ===")
base = np.mean([r for r, _ in rules["Manter 12 meses"]])
print(f"{'regra':38s} {'n':>6s} {'ret.médio':>9s} {'mediana':>8s} {'%perdas':>8s} {'pior 5%':>8s} {'dias':>5s} {'ret/dia':>8s}")
for name, v in rules.items():
    r = np.array([a for a, _ in v]); d = np.array([b for _, b in v])
    print(f"{name:38s} {len(r):6d} {r.mean()*100:8.1f}% {np.median(r)*100:7.1f}% {(r<0).mean()*100:7.0f}% {np.percentile(r,5)*100:7.1f}% {d.mean():5.0f} {r.mean()/d.mean()*252*100:7.1f}%")

print("\n=== CALIBRAÇÃO: um alvo de +X% foi mesmo tocado em 12 meses? (modelo = reflexão, sem tendência) ===")
cdf = pd.DataFrame(calib, columns=["x", "hit", "acima52", "modelo", "z"])
for xx, g in cdf.groupby("x"):
    print(f"alvo +{int(xx*100)}%: real {g.hit.mean()*100:5.1f}% | modelo {g.modelo.mean()*100:5.1f}% | n={len(g)}")
    for a, gg in g.groupby("acima52"):
        print(f"      {'acima' if a else 'abaixo'} do máx. 52s: real {gg.hit.mean()*100:5.1f}% | modelo {gg.modelo.mean()*100:5.1f}% | n={len(gg)}")
print("\n=== por z (distância em desvios-padrão anuais) ===")
cdf["zb"] = pd.cut(cdf.z, [0, .25, .5, .75, 1, 1.5, 3])
for b, g in cdf.groupby("zb", observed=True):
    a = g[g.acima52]; bb = g[~g.acima52]
    print(f"z {b}: real {g.hit.mean()*100:5.1f}% (modelo {g.modelo.mean()*100:5.1f}%) | acima52 real {a.hit.mean()*100 if len(a) else float('nan'):5.1f}% n={len(a)} | abaixo52 real {bb.hit.mean()*100 if len(bb) else float('nan'):5.1f}% n={len(bb)}")
