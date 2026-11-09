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
print("\nresumo:", D["audit"])
sys.exit(1 if bad else 0)
