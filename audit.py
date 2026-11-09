"""Auditoria independente de data.js. Uso: python audit.py   (sai com código 1 se alguma verificação crítica falhar)"""
import json, random, sys, time
import yfinance as yf
import fetch

raw = open("data.js", encoding="utf-8").read()
D = json.loads(raw[len("window.DATA="):])
cols = D["cols"]
R = [dict(zip(cols, r)) for r in D["rows"]]
ROW = {r["s"]: r for r in R}
T = D["tickers"]
bad = []


def check(name, ok, detail=""):
    print(("OK   " if ok else "FALHA"), name, detail)
    if not ok:
        bad.append(name)


check("só bolsas autorizadas", {r["ex"] for r in R} <= set(fetch.EXCH), str(sorted({r["ex"] for r in R})))
check("sem símbolos duplicados", len(R) == len({r["s"] for r in R}), f"{len(R)} linhas")
groups = {}
for r in R:
    groups.setdefault(fetch.norm(r["name"]), []).append(r)
dups = [(k, [(x["s"], x["ex"]) for x in g]) for k, g in groups.items() if k and len(g) > 1 and max(x["mcap"] for x in g) / min(x["mcap"] for x in g) < 1.5]
check("sem a mesma empresa em 2 bolsas", not dups, str(dups[:5]))
srt = sorted(R, key=lambda r: r["mcap"])
pairs = []
for i, x in enumerate(srt):
    for y in srt[i + 1:]:
        if y["mcap"] / x["mcap"] > 1.07:
            break
        if fetch.same_company(x["name"], x["mcap"], y["name"], y["mcap"]):
            pairs.append((x["s"], y["s"], x["name"][:20], y["name"][:20]))
check("sem a mesma empresa com nomes diferentes (nome + cap. idêntica)", not pairs, str(pairs[:6]))
bs = {}
for r in R:
    bs.setdefault(fetch.base(r["s"]), []).append(r)
tk = [(g[0]["s"], g[1]["s"]) for g in bs.values() if len(g) > 1 and any(fetch.same_ticker(x["s"], x["name"], x["mcap"], y["s"], y["name"], y["mcap"]) for i, x in enumerate(g) for y in g[i + 1:])]
check("sem o mesmo ticker-base em duas bolsas (ex.: MRVL / MRVL.SW)", not tk, str(tk[:6]))
check("sem recibos de depósito/BDRs", not any(fetch.is_receipt(r["s"]) for r in R))
age_h = [(time.time() - r["tm"] * 60) / 3600 for r in R]
check("nenhum preço com mais de 10 dias", max(age_h) < 240, f"mais antigo: {max(age_h) / 24:.1f} dias; mediana {sorted(age_h)[len(age_h) // 2]:.1f} h")
check("todos com preço e cap. positivos", all(r["px"] and r["px"] > 0 and r["mcap"] >= 2000 for r in R))
check("rácios dentro de limites plausíveis", all((r["fpe"] is None or 0 < r["fpe"] < 1000) and (r["pb"] is None or 0 < r["pb"] < 1000) and (r["pe"] is None or 0 < r["pe"] < 5000) for r in R))
check("scores entre 0 e 100", all(r["sc1"] is None or 0 <= r["sc1"] <= 100 for r in R))
check("análise completa ⊂ universo", all(s in ROW for s in T), str([s for s in T if s not in ROW][:10]))
mism = [(s, t["price"], ROW[s]["px"]) for s, t in T.items() if s in ROW and abs(t["price"] / ROW[s]["px"] - 1) > 0.05]
check("preço completo ≈ preço do screener (±5%)", not mism, str(mism[:5]))
tg = [(s, t["target"], t["price"]) for s, t in T.items() if t["target"] and not (0.3 <= t["target"] / t["price"] <= 3.5)]
check("alvos coerentes com o preço", not tg, str(tg[:5]))
check("ordem de oportunidades só com análise completa", all(s in T for s in D["order"]))
check("destaques existem", all((v is None or v in T) for v in D["highlights"].values()))
# comparação com cotações obtidas de novo e de forma independente (histórico diário)
random.seed(1)
sample = random.sample(R, 25)
diffs = []
for r in sample:
    try:
        c = yf.Ticker(r["s"]).history(period="5d")["Close"].dropna()
        last = float(c.iloc[-1])
        diffs.append((r["s"], r["px"], round(last, 2), abs(last / r["px"] - 1)))
    except Exception:
        pass
worst = sorted(diffs, key=lambda x: -x[3])[:3]
ok_n = sum(1 for d in diffs if d[3] < 0.05)
check("amostra de 25 preços ≈ histórico independente (±5%)", ok_n >= 0.9 * len(diffs), f"{ok_n}/{len(diffs)} dentro de 5%; piores: {worst}")
Q = {k: t["q"] for k, t in T.items() if t.get("q")}
check("todas as análises completas têm bloco de qualidade", len(Q) == len(T), f"{len(Q)}/{len(T)}")
check("qualidade: nota 0-100, Piotroski ≤ 9, anos ascendentes", all((q.get("qscore") is None or 0 <= q["qscore"] <= 100) and (not q.get("piotroski") or 0 <= q["piotroski"]["score"] <= q["piotroski"]["of"] <= 9) and [x["y"] for x in q.get("series", [])] == sorted(x["y"] for x in q.get("series", [])) for q in Q.values()))
check("financeiras sem Piotroski/Altman/ROIC", all(not (q.get("fin") and (q.get("piotroski") or q.get("altman") or q.get("roic"))) for q in Q.values()))
check("P/E histórico plausível", all(0 < x["pe"] < 500 for q in Q.values() for x in q.get("series", []) if x.get("pe") is not None))
check("ROIC e margens plausíveis", all(-5000 < (x.get(k) or 0) < 5000 for q in Q.values() for x in q.get("series", []) for k in ("roic", "om", "nm", "gm")))
with_q = sum(1 for q in Q.values() if q.get("qscore") is not None)
check("≥60% das análises com nota de qualidade", with_q >= 0.6 * len(T), f"{with_q}/{len(T)}")
rev_d = []
for s in random.sample(list(Q), min(15, len(Q))):
    try:
        i = yf.Ticker(s).info
        rv, ser = i.get("totalRevenue"), Q[s].get("series")
        if rv and ser and ser[-1]["rev"] and i.get("financialCurrency") == i.get("currency"):
            rev_d.append((s, round(ser[-1]["rev"] * 1e6 / rv, 2)))
    except Exception:
        pass
bad_r = [x for x in rev_d if not 0.5 <= x[1] <= 1.6]
check("vendas do último exercício ≈ vendas 12m", len(bad_r) <= max(1, len(rev_d) // 8), f"{len(rev_d)} amostras; fora: {bad_r}")
import re
EN = re.compile(r"\b(the|and|provides|which|its)\b", re.I)
auto = {k: t["tese"] for k, t in T.items() if not t["tese"].get("hand")}
eng = [k for k, x in auto.items() if EN.search(" ".join([x["faz"].replace(T[k]["name"].strip(" -"), ""), *x["barata"], *x["saude"], *x["cat"], *x["riscos"]]))]
check("teses automáticas 100% em português (sem texto em inglês do Yahoo)", not eng and all(len(x["faz"]) > 60 and "resumo do Yahoo" not in x["faz"] for x in auto.values()), str(eng[:5]))
el = [k for k in D["order"] if T[k]["elite"]]
top = el[:10]
check("Top 10: só compounders que passam o crivo", all(T[k]["cons"]["total"] >= 10 and (T[k]["cons"]["buy_pct"] or 0) > 65 and T[k]["q"]["compounder"]["ok"] and not T[k]["q"]["trap"] and not T[k]["q"]["norm"].get("peak") and (T[k]["q"]["qscore"] or 0) >= 60 for k in top), f"{len(el)} elite: {top}")
check("elite vem primeiro na ordem das oportunidades", D["order"][:len(el)] == el)
check("destaque principal sem armadilha de valor", not T[D["highlights"]["pick"]]["q"]["trap"])
check("taxa sem risco (FRED) plausível", 0.005 < D["meta"]["rf"] < 0.12, f"rf={D['meta']['rf']} macro={D.get('macro')}")
check("sentimento só pos/neu/neg", all(a.get("s") in ("pos", "neu", "neg") for t in T.values() for a in t["news"]) and all(a["s"] in ("pos", "neu", "neg") for a in D["mnews"]["items"]))
check("data.js sem NaN/Infinity (JSON válido)", not re.search(r"\b(NaN|-?Infinity)\b", raw))
check("ratios sem extremos (P/E, P/E projetado, EV/EBITDA ≤ 300)", all(t[k] is None or 0 < t[k] <= 300 for t in T.values() for k in ("pe", "fpe", "eve")))
dc = [(k, t["dcf"], fetch.dcf(t["sim"]["fcf"], t["sim"]["g"], t["sim"]["sh"], t["sim"]["nd"])) for k, t in T.items() if t.get("sim", {}).get("mode") == "dcf" and t.get("dcf")]
check("simulador: DCF do front-end = DCF do pipeline (±1%)", all(abs(a / b - 1) < 0.01 for _, a, b in dc), f"{len(dc)} comparados")
check("simulador: todos têm modo ou ficam sem simulação", all((t.get("sim") or {}).get("mode") in ("dcf", "pe", None) for t in T.values()), f"dcf={sum(1 for t in T.values() if t['sim'].get('mode') == 'dcf')} pe={sum(1 for t in T.values() if t['sim'].get('mode') == 'pe')}")
check("suportes abaixo e resistências acima do preço", all(all(x["p"] < t["price"] for x in t["sr"].get("sup", [])) and all(x["p"] > t["price"] for x in t["sr"].get("res", [])) for t in T.values()), f"{sum(1 for t in T.values() if t['sr'].get('sup'))} com suportes")
at = [(k, t.get("atr"), t["price"]) for k, t in T.items()]
check("ATR 14d presente (≥90%) e plausível (0 < ATR < 25% do preço)", sum(1 for _, a, _p in at if a) >= 0.9 * len(at) and all(a is None or 0 < a < 0.25 * p for _, a, p in at), f"{sum(1 for _, a, _p in at if a)}/{len(at)}")
print("INFO notícias de mercado:", len(D["mnews"]["items"]), D["mnews"]["sources"], "| insiders com dados:", sum(1 for t in T.values() if t["q"].get("insiders")), "| cíclicas:", sum(1 for t in T.values() if t["q"]["norm"].get("cyc")))
print("\nresumo:", D["audit"])
sys.exit(1 if bad else 0)
