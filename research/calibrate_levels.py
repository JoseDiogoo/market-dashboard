"""Calibração à Osler (NY Fed, 2000) dos níveis técnicos: um nível só entra na interface se REVERTER mais do que níveis aleatórios.
Uso: python research/calibrate_levels.py   (descarrega 10 anos de OHLCV das ações com análise completa; cache em research/ohlcv.pkl)
Saída: research/levels_calibration.json (lido por fetch.py/benchmarks via levels.py e mostrado em «Como foi calculado»).

MÉTODO (sem olhar para o futuro: o nível do dia t usa só dados até ao fecho de t-1)
 Evento de SUPORTE: a mínima do dia t toca o nível L (L abaixo do fecho anterior, a <= 3 ATR), sem abrir já abaixo dele. Compra limite em L.
   Resultado nos 20 dias seguintes: «reverteu» se o fecho atingir L + 1 ATR antes de fechar em L - 1 ATR (rompeu); sem decisão = excluído.
 RESISTÊNCIA = o espelho (série multiplicada por -1).  Cooldown de 10 dias por série. Controlo: K séries de níveis ALEATÓRIOS a distância
 uniforme de 0,1 a 3 ATR do fecho anterior, com o mesmo procedimento. Vantagem = taxa real - taxa dos controlos.
 IC 95% por bootstrap sobre ações (reamostra ações, não eventos: os eventos da mesma ação são correlacionados). Estabilidade: vantagem nas
 duas metades do período. «aprovado» = limite inferior do IC > 0 E vantagem > 0 nas duas metades E sobreviver à correção de Holm-Bonferroni (todos os tipos x lados).
LIMITES: universo = ações que HOJE passam o crivo (viés de sobrevivência: taxas absolutas otimistas; só a comparação real vs controlo vale);
 sem custos; eventos sobrepostos; testa-se muitos tipos de nível (risco de data snooping: por isso exige-se IC e as duas metades)."""
import json, pathlib, sys, time
import numpy as np, pandas as pd, yfinance as yf
from numpy.lib.stride_tricks import sliding_window_view as swv

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
OUT, CACHE = ROOT / "research" / "levels_calibration.json", ROOT / "research" / "ohlcv.pkl"
H, REACH, COOL, K, WARM, FW = 20, 3.0, 10, 8, 260, 20
rng = np.random.default_rng(7)


def load():
    if CACHE.exists():
        return pd.read_pickle(CACHE)
    d = json.loads((ROOT / "data.js").read_text(encoding="utf-8")[len("window.DATA="):])
    syms, P = list(d["tickers"]), {}
    for i in range(0, len(syms), 40):
        part = syms[i:i + 40]
        df = yf.download(part, period="10y", auto_adjust=True, progress=False, threads=True, group_by="ticker")
        for s in part:
            try:
                x = df[s][["Open", "High", "Low", "Close", "Volume"]].dropna()
                if len(x) > 800:
                    P[s] = x
            except Exception:
                pass
        print(f"{min(i + 40, len(syms))}/{len(syms)} · {len(P)}", flush=True)
    pd.to_pickle(P, CACHE)
    return P


def atr(h, l, c):
    pc = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().values


def rolling_arg(x, w, fn):  # índice (absoluto) do min/máx da janela de w barras que termina em t
    out = np.full(len(x), -1)
    a = fn(swv(x, w), axis=1)
    out[w - 1:] = a + np.arange(len(x) - w + 1)
    return out


def avwap(tp, v, anchor):
    cpv, cv = np.r_[0, np.cumsum(tp * v)], np.r_[0, np.cumsum(v)]
    t = np.arange(len(tp))
    ok = (anchor >= 0) & (anchor <= t)
    a = np.where(ok, anchor, 0)
    num, den = cpv[t + 1] - cpv[a], cv[t + 1] - cv[a]
    return np.where(ok & (den > 0), num / np.where(den > 0, den, 1), np.nan)


def swing_anchor(x, w, kind):  # índice do último pivô CONFIRMADO (w barras depois) até t
    n = len(x)
    piv = np.zeros(n, bool)
    win = swv(x, 2 * w + 1)
    ex = win.min(axis=1) if kind == "low" else win.max(axis=1)
    piv[w:n - w] = x[w:n - w] == ex
    conf = np.where(piv)[0] + w
    out = np.full(n, -1)
    last, j, pv = -1, 0, np.where(piv)[0]
    for t in range(n):
        while j < len(conf) and conf[j] <= t:
            last = pv[j]; j += 1
        out[t] = last
    return out


def volume_profile(h, l, c, v, win=126, bins=40, va=.70, step=3):
    n = len(c); poc, lo_, hi_ = (np.full(n, np.nan) for _ in range(3))
    tp = (h + l + c) / 3
    for t in range(win, n, step):
        s = slice(t - win + 1, t + 1)
        a, b = l[s].min(), h[s].max()
        if b <= a:
            continue
        idx = np.minimum(((tp[s] - a) / (b - a) * bins).astype(int), bins - 1)
        vol = np.bincount(idx, weights=v[s], minlength=bins)
        k = int(vol.argmax()); lo, hi, tot = k, k, vol[k]
        while tot < va * vol.sum() and (lo > 0 or hi < bins - 1):
            up = vol[hi + 1] if hi < bins - 1 else -1; dn = vol[lo - 1] if lo > 0 else -1
            if up >= dn: hi += 1; tot += up
            else: lo -= 1; tot += dn
        bw = (b - a) / bins
        sl = slice(t, min(t + step, n))
        poc[sl], lo_[sl], hi_[sl] = a + (k + .5) * bw, a + lo * bw, a + (hi + 1) * bw
    return poc, lo_, hi_


def pivot_cluster(c, step=5, w=8, tol=.025, look=252):
    import fetch
    n = len(c); sup, res = np.full(n, np.nan), np.full(n, np.nan)
    for t in range(look, n, step):
        lv = fetch.levels(pd.Series(c[t - look + 1:t + 1]), c[t]) or {}
        s = [x["p"] for x in lv.get("sup", []) if x["n"] >= 2]; r = [x["p"] for x in lv.get("res", []) if x["n"] >= 2]
        sl = slice(t, min(t + step, n))
        if s: sup[sl] = max(s)
        if r: res[sl] = min(r)
    return sup, res


def round_level(c, kind):
    st = 10.0 ** np.floor(np.log10(c)) / 2
    return np.floor(c / st) * st if kind == "sup" else np.ceil(c / st) * st


def levels_of(o, h, l, c, v):
    s = lambda x, w: pd.Series(x).rolling(w).mean().values
    tp = (h + l + c) / 3
    poc, val, vah = volume_profile(h, l, c, v)
    psup, pres = pivot_cluster(c)
    L = {"EMA 21": (pd.Series(c).ewm(span=21, adjust=False).mean().values,) * 2, "SMA 50": (s(c, 50),) * 2, "SMA 200": (s(c, 200),) * 2,
         "VWAP ancorado (mín. 52 sem.)": (avwap(tp, v, rolling_arg(l, 252, np.argmin)), avwap(tp, v, rolling_arg(h, 252, np.argmax))),
         "VWAP ancorado (último pivô)": (avwap(tp, v, swing_anchor(l, 10, "low")), avwap(tp, v, swing_anchor(h, 10, "high"))),
         "Volume Profile POC (6 meses)": (poc, poc), "Volume Profile área de valor": (val, vah),
         "Pivôs agrupados (≥2 toques)": (psup, pres), "Número redondo": (round_level(c, "sup"), round_level(c, "res")),
         "Máx./mín. de 52 semanas": (pd.Series(l).rolling(252).min().values, pd.Series(h).rolling(252).max().values)}
    return L  # nome -> (nível como suporte, nível como resistência)


def events(o, h, l, c, a, L):
    """Eventos de suporte para a série de níveis L (já alinhada: L[t] conhecido ao fecho de t-1). Devolve (índices, reverteu 0/1, retorno em R)."""
    n = len(c); pc, pa = np.r_[np.nan, c[:-1]], np.r_[np.nan, a[:-1]]
    with np.errstate(invalid="ignore"):
        ok = np.isfinite(L) & (L < pc) & ((pc - L) <= REACH * pa) & (l <= L) & (o >= L)
    ok[:WARM] = False
    idx, last, res = [], -99, []
    for t in np.where(ok)[0]:
        if t - last < COOL or t + FW >= n:
            continue
        up, dn = L[t] + pa[t], L[t] - pa[t]
        seg = c[t:t + FW]
        iu, idn = np.argmax(seg >= up) if (seg >= up).any() else 99, np.argmax(seg <= dn) if (seg <= dn).any() else 99
        if iu == 99 and idn == 99:
            continue
        last = t; idx.append(t); res.append(1 if iu < idn else 0)
    return np.array(idx), np.array(res)


def tabulate(P):
    """por nome -> por lado -> por ação: (nº eventos real, nº reverteu, nº controlo, nº reverteu controlo, metade-A reais/hits, metade-B ...)."""
    tab = {}
    t0 = time.time()
    for si, (sym, x) in enumerate(P.items()):
        o, h, l, c, v = (x[k].values.astype(float) for k in ("Open", "High", "Low", "Close", "Volume"))
        if (v > 0).mean() < .9:
            continue
        a, n = atr(h, l, c), len(c); half = n // 2
        Ls = levels_of(o, h, l, c, v)
        mir = (-o, -l, -h, -c)  # espelho para resistências
        for side in ("sup", "res"):
            args = (o, h, l, c) if side == "sup" else mir
            sgn = 1 if side == "sup" else -1
            for name, lv in list(Ls.items()) + [("__controlo__", None)]:
                if name == "__controlo__":  # níveis aleatórios a 0,1-3 ATR do fecho anterior (acima, no caso das resistências)
                    series = []
                    for _ in range(K):
                        d = rng.uniform(.1, REACH, n)
                        series.append(np.r_[np.nan, ((c - d * a) if side == "sup" else -(c + d * a))[:-1]])
                else:
                    series = [sgn * np.r_[np.nan, lv[0 if side == "sup" else 1][:-1]]]
                for sr in series:
                    idx, res = events(*args, a, sr)
                    e = tab.setdefault((name, side), {}).setdefault(sym, [0, 0, 0, 0, 0, 0, 0, 0])
                    if len(idx):
                        A = idx < half
                        e[0] += len(idx); e[1] += int(res.sum()); e[2] += int(A.sum()); e[3] += int(res[A].sum()); e[4] += int((~A).sum()); e[5] += int(res[~A].sum())
        if si % 20 == 0:
            print(f"{si + 1}/{len(P)} · {time.time() - t0:.0f}s", flush=True)
    return tab


def summarise(tab, B=2000):
    out = {}
    for (name, side), per in tab.items():
        if name == "__controlo__":
            continue
        ctl = tab[("__controlo__", side)]
        syms = [s for s in per if s in ctl]
        R = np.array([per[s] for s in syms], float); C = np.array([ctl[s] for s in syms], float)
        rate = lambda M, i, j: M[:, j].sum() / max(M[:, i].sum(), 1)
        pr, pc_ = rate(R, 0, 1), rate(C, 0, 1)
        ea, eb = rate(R, 2, 3) - rate(C, 2, 3), rate(R, 4, 5) - rate(C, 4, 5)
        boots = []
        for _ in range(B):
            ii = rng.integers(0, len(syms), len(syms))
            boots.append(rate(R[ii], 0, 1) - rate(C[ii], 0, 1))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        bz = np.array(boots); praw = float(min(1, 2 * min((bz <= 0).mean(), (bz >= 0).mean()) + 1 / B))  # p bilateral do bootstrap
        out.setdefault(name, {})[side] = {"p_raw": round(praw, 4), "n": int(R[:, 0].sum()), "n_ctl": int(C[:, 0].sum()), "p": round(pr, 4), "p_ctl": round(pc_, 4), "edge": round(pr - pc_, 4),
                                          "ci": [round(lo, 4), round(hi, 4)], "edge_h1": round(ea, 4), "edge_h2": round(eb, 4), "stocks": len(syms),
                                          "ok_raw": bool(lo > 0 and ea > 0 and eb > 0)}
    # Holm-Bonferroni sobre TODOS os testes (tipos x lados): com 20 testes, um «aprovado» a 95% é o que o acaso dá em média
    flat = sorted(((v["p_raw"], n, sd) for n, d in out.items() for sd, v in d.items()))
    m, run_ok = len(flat), True
    for r, (pv, n, sd) in enumerate(flat):
        thr = 0.05 / (m - r)
        run_ok = run_ok and pv <= thr
        out[n][sd]["p_holm_limiar"] = round(thr, 4)
        out[n][sd]["ok"] = bool(out[n][sd]["ok_raw"] and run_ok)
    return out


def overextension(P):
    """Distância à SMA 50 em ATR (percentil vs 2 anos da própria ação) e retorno/queda máxima nos 20 dias seguintes. Sem regra pré-definida: só mede."""
    rows = []
    for sym, x in P.items():
        h, l, c = (x[k].values.astype(float) for k in ("High", "Low", "Close"))
        a = atr(h, l, c); s50 = pd.Series(c).rolling(50).mean().values
        d = pd.Series((c - s50) / np.maximum(a, 1e-9))
        rk = d.rolling(504).apply(lambda w: (w[:-1] < w[-1]).mean(), raw=True).values
        fw = np.full(len(c), np.nan); mae = np.full(len(c), np.nan)
        fw[:-FW] = c[FW:] / c[:-FW] - 1
        mae[:-FW] = swv(l[1:], FW).min(axis=1)[:len(c) - FW] / c[:-FW] - 1
        near = c / pd.Series(h).rolling(252).max().values
        rows.append(pd.DataFrame({"s": sym, "rk": rk, "fw": fw, "mae": mae, "near": near}))
    df = pd.concat(rows).dropna()
    res = {}
    for nm, m in (("distância à SMA50 no top 10% da própria história", df.rk >= .9), ("distância à SMA50 no top 5%", df.rk >= .95), ("a menos de 3% do máximo de 52 semanas", df.near >= .97)):
        per = df.assign(m=m).groupby(["s", "m"])[["fw", "mae"]].mean().unstack("m").dropna()
        dd = {}
        for k in ("fw", "mae"):
            diff = (per[(k, True)] - per[(k, False)]).values
            bs = [diff[rng.integers(0, len(diff), len(diff))].mean() for _ in range(2000)]
            dd[k] = {"diff": round(float(diff.mean()), 4), "ci": [round(float(np.percentile(bs, 2.5)), 4), round(float(np.percentile(bs, 97.5)), 4)]}
        res[nm] = {"n": int(m.sum()), "fwd20_vs_resto": dd["fw"], "pior_queda20_vs_resto": dd["mae"]}
    return res


if __name__ == "__main__":
    P = load()
    print(len(P), "ações")
    tab = tabulate(P)
    out = {"date": time.strftime("%Y-%m-%d"), "stocks": len(P), "params": {"horizonte_dias": FW, "alcance_atr": REACH, "cooldown": COOL, "controlos_por_serie": K, "alvo_e_stop_atr": 1.0},
           "levels": summarise(tab), "overext": overextension(P)}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for n, d in out["levels"].items():
        for s, v in d.items():
            print(f"{n:34s} {s}  n={v['n']:6d}  real={v['p']:.3f} ctl={v['p_ctl']:.3f}  vantagem={v['edge']:+.3f} IC=[{v['ci'][0]:+.3f},{v['ci'][1]:+.3f}] p={v['p_raw']:.3f}  h1={v['edge_h1']:+.3f} h2={v['edge_h2']:+.3f}  {'APROVADO' if v['ok'] else ('bruto sim, Holm não' if v['ok_raw'] else '—')}")
    print(json.dumps(out["overext"], ensure_ascii=False, indent=1))
