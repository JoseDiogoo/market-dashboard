"""Pipeline global: screener (milhares de ações) -> estatística (percentis por setor) -> análise profunda do top N -> data.js
Uso: python fetch.py [--quick]   (--quick = só 2 setores, para testar)"""
import json, math, re, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import logging
import yfinance as yf
logging.getLogger('yfinance').setLevel(logging.CRITICAL)  # 404 de fundamentais em ações sem cobertura são esperados
from yfinance import EquityQuery as EQ
from tese import UNIVERSE as CURATED, NOMES, TESE, TAPE

MIN_USD = 2e9        # capitalização mínima para entrar no universo
DEEP_MIN_USD = 10e9  # só empresas desta dimensão entram na análise profunda automática
STALE_DAYS = 10      # preços sem negócio há mais de N dias (suspensas/deslistadas) são excluídos
DEEP_N = 250         # nº de ações com análise completa (além das curadas)
RF, ERP = 0.04, 0.05  # taxa sem risco e prémio de risco assumidos nos cenários (parâmetros, não previsões)
# Universo 100% investível em corretoras europeias comuns (XTB, Trading 212, DEGIRO): EUA + Europa Ocidental/Nórdicas.
# código Yahoo -> (nome da bolsa, país, região). Sem China continental, Índia, Coreia, Turquia, etc.
EX = {"NYQ": ("NYSE", "EUA", "us"), "NMS": ("NASDAQ", "EUA", "us"), "NGM": ("NASDAQ", "EUA", "us"), "NCM": ("NASDAQ", "EUA", "us"), "ASE": ("AMEX", "EUA", "us"),
      "LSE": ("Londres (LSE)", "Reino Unido", "eu"), "GER": ("XETRA", "Alemanha", "eu"), "PAR": ("Euronext Paris", "França", "eu"), "AMS": ("Euronext Amesterdão", "Países Baixos", "eu"),
      "LIS": ("Euronext Lisboa", "Portugal", "eu"), "BRU": ("Euronext Bruxelas", "Bélgica", "eu"), "EBS": ("SIX Suíça", "Suíça", "eu"), "MCE": ("BME Madrid", "Espanha", "eu"),
      "MIL": ("Borsa Italiana", "Itália", "eu"), "STO": ("Nasdaq Estocolmo", "Suécia", "eu"), "CPH": ("Nasdaq Copenhaga", "Dinamarca", "eu"), "OSL": ("Oslo Børs", "Noruega", "eu")}
PAIS = {k: v[1] for k, v in EX.items()}
EXCH = list(PAIS)
SECTORS = ["Technology", "Financial Services", "Healthcare", "Consumer Cyclical", "Industrials", "Communication Services", "Consumer Defensive", "Energy", "Basic Materials", "Real Estate", "Utilities"]
SUB = {"GBp": ("GBP", .01), "GBX": ("GBP", .01), "ILA": ("ILS", .01), "ZAc": ("ZAR", .01), "ZAC": ("ZAR", .01)}  # moedas cotadas em subunidade


def log(*a):
    print(*a, flush=True)


def retry(fn, n=4):
    for i in range(n):
        try:
            return fn()
        except Exception as e:
            if i == n - 1:
                raise
            time.sleep((20 if "Too Many" in str(e) or "Rate" in str(e) else 1.5) * (i + 1))  # espera mais se o Yahoo limitar o ritmo


# ---------------------------------------------------------------- câmbios
def fx_of(cur):
    """USD por 1 unidade da moeda principal de 'cur'."""
    base, _ = SUB.get(cur, (cur, 1))
    if base == "USD":
        return 1.0
    try:
        c = yf.Ticker(f"{base}USD=X").history(period="5d")["Close"].dropna()
        return float(c.iloc[-1])
    except Exception:
        return None


def currencies():
    def probe(e):
        try:
            r_ = retry(lambda: yf.screen(EQ("and", [EQ("eq", ["exchange", e]), EQ("gt", ["intradaymarketcap", 1])]), size=1))
            return e, r_["quotes"][0]["currency"] if r_.get("quotes") else None
        except Exception:
            return e, None
    with ThreadPoolExecutor(8) as ex:
        ec = dict(ex.map(probe, EXCH))
    curs = sorted({c for c in ec.values() if c})
    with ThreadPoolExecutor(8) as ex:
        fx = dict(zip(curs, ex.map(fx_of, curs)))
    return ec, fx


# ---------------------------------------------------------------- screener global
def fetch_universe(sectors):
    ec, fx = currencies()
    thr = {e: MIN_USD / fx[ec[e]] for e in EXCH if ec.get(e) and fx.get(ec[e])}  # limiar em moeda local por bolsa
    log(f"bolsas ativas: {len(thr)}/{len(EXCH)}")
    ors = [EQ("and", [EQ("eq", ["exchange", e]), EQ("gt", ["intradaymarketcap", v])]) for e, v in thr.items()]

    def sector_pages(sector):
        q = EQ("and", [EQ("or", ors), EQ("eq", ["sector", sector])])
        out, off = [], 0
        while off < 9750:
            r_ = retry(lambda: yf.screen(q, size=250, offset=off, sortField="intradaymarketcap", sortAsc=False))
            qs = r_.get("quotes", [])
            out += qs
            off += 250
            if len(qs) < 250:
                break
        for x in out:
            x["_sector"] = sector
        log(f"  {sector}: {len(out)}")
        return out
    with ThreadPoolExecutor(4) as ex:
        quotes = [x for part in ex.map(sector_pages, sectors) for x in part]
    return quotes, fx


def parse_rating(s):
    try:
        return float(str(s).split(" - ")[0])
    except Exception:
        return None


STOPW = {"inc", "incorporated", "corp", "corporation", "ltd", "limited", "plc", "sa", "ag", "se", "nv", "co", "company", "holdings", "holding", "group", "the", "class", "adr", "ads", "spa", "as", "ab", "asa", "oyj", "bhd", "tbk", "pcl", "public", "llc", "lp", "cv", "de"}


def is_receipt(s):
    """Recibos de depósito/BDRs/NVDRs duplicam empresas estrangeiras com métricas pouco fiáveis."""
    return bool(re.search(r"[A-Z]\d{2}\.SA$", s) and not s.endswith("11.SA")) or bool(re.search(r"\d{2}\.BK$|-[RFN]\.BK$", s))


def norm(name):
    return " ".join(w for w in re.findall(r"[a-z0-9]+", str(name).lower()) if w not in STOPW)


def dedupe(df):
    """A mesma empresa cotada em várias bolsas: mantém a cotação mais líquida (maior volume em USD)."""
    keep, seen = [], {}
    for i, r_ in df.assign(_n=df.name.map(norm), _c=df.s.isin(CURATED)).sort_values(["_c", "dvol"], ascending=False).iterrows():  # curadas têm prioridade
        dup = any(0.67 <= r_.mcap / m <= 1.5 for m in seen.get(r_._n, []))
        if r_._n and dup:
            continue
        seen.setdefault(r_._n, []).append(r_.mcap)
        keep.append(i)
    return df.loc[sorted(keep)]


def to_frame(quotes, fx):
    rows, seen = [], set()
    for q in quotes:
        s = q.get("symbol")
        if not s or s in seen or q.get("quoteType") != "EQUITY":
            continue
        cur = q.get("currency")
        base, mult = SUB.get(cur, (cur, 1))
        f_main = fx.get(cur) if cur in fx else None  # USD por moeda principal
        price, mc = q.get("regularMarketPrice"), q.get("marketCap")
        if not price or not mc or not f_main:
            continue
        seen.add(s)
        rows.append({"s": s, "name": q.get("displayName") or q.get("longName") or q.get("shortName") or s, "ex": q.get("exchange"), "cur": cur, "sec": q["_sector"],
                     "px": price, "chg": q.get("regularMarketChangePercent"), "mcap": mc * f_main, "fpe": q.get("forwardPE"), "pe": q.get("trailingPE"), "pb": q.get("priceToBook"),
                     "dy": q.get("dividendYield"), "ret": q.get("fiftyTwoWeekChangePercent"), "hi": q.get("fiftyTwoWeekHigh"), "lo": q.get("fiftyTwoWeekLow"),
                     "ma200": q.get("twoHundredDayAverage"), "epst": q.get("epsTrailingTwelveMonths"), "epsf": q.get("epsForward"), "rat": parse_rating(q.get("averageAnalystRating")),
                     "tm": q.get("regularMarketTime"), "fcur": q.get("financialCurrency"), "fx": f_main * mult, "dvol": (q.get("regularMarketVolume") or 0) * price * f_main * mult})  # USD por 1 unidade do preço cotado (ex.: GBp)
    df = pd.DataFrame(rows)
    # sanidade dos rácios do Yahoo: P/B só é fiável se o balanço estiver na moeda do preço (ADRs falham); valores absurdos viram n/d
    df.loc[df.fcur.notna() & (df.fcur != df.cur), "pb"] = np.nan
    for c, lo, hi in (("fpe", 1, 500), ("pe", 1, 500), ("pb", 0.05, 200)):
        df[c] = df[c].where((df[c] >= lo) & (df[c] <= hi))
    df = df[df.mcap >= MIN_USD]
    n0 = len(df)
    df = df[~df.s.map(is_receipt)]
    n1 = len(df)
    df = df[df.tm.notna() & (time.time() - df.tm <= STALE_DAYS * 86400)]
    n2 = len(df)
    df = dedupe(df).reset_index(drop=True)
    QC.update({"receipts_removed": n0 - n1, "stale_removed": n1 - n2, "duplicates_removed": n2 - len(df)})
    return df


# ---------------------------------------------------------------- estatística
def prank(s, by):
    return s.groupby(by).rank(pct=True) * 100  # percentil dentro do setor; NaN fica NaN


def factors(df):
    """Fatores como percentis (0-100) dentro do setor. Percentis são robustos a outliers (equivalente a winsorizar)."""
    fpe = df.fpe.where((df.fpe >= 1) & (df.fpe <= 80))
    pb = df.pb.where((df.pb >= 0.05) & (df.pb <= 40))
    ey = (df.epst / df.px).clip(-0.2, 0.3)
    value = pd.concat([prank(-np.log(fpe), df.sec), prank(-np.log(pb), df.sec), prank(ey, df.sec)], axis=1).mean(axis=1)
    g = (df.epsf / df.epst - 1).where((df.epst > 0) & (df.epsf > 0)).clip(-1, 1)
    growth = prank(g, df.sec)
    mom = pd.concat([prank(df.ret, df.sec), prank(df.px / df.ma200 - 1, df.sec)], axis=1).mean(axis=1)
    analyst = prank(-df.rat, df.sec)
    income = prank(df.dy.fillna(0).clip(0, 12), df.sec)
    F = pd.concat([value, growth, mom, analyst, income], axis=1)
    F.columns = ["v", "g", "m", "a", "i"]
    w = pd.Series({"v": .30, "g": .20, "m": .15, "a": .25, "i": .10})
    ok = F.notna()
    comp = (F.fillna(50) * w).sum(axis=1) / w.sum()  # fatores em falta = neutro (50)
    comp[ok.sum(axis=1) < 3] = np.nan
    return F, comp


def sector_stats(df):
    out = {}
    for sec, g in df.groupby("sec"):
        row = {"n": int(len(g))}
        for k, col in (("fpe", g.fpe.where((g.fpe >= 1) & (g.fpe <= 80))), ("pb", g.pb.where((g.pb >= 0.05) & (g.pb <= 40))), ("dy", g.dy), ("ret", g.ret)):
            c = col.dropna()
            row[k] = [round(float(c.quantile(q)), 2) for q in (.25, .5, .75)] if len(c) >= 8 else None
        out[sec] = row
    return out


# ---------------------------------------------------------------- análise profunda
def sc(v, lo, hi):
    return None if v is None else max(0.0, min(1.0, (v - lo) / (hi - lo)))
def avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.5
def r(v, n=2):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), n)
def pct(v):
    return None if v is None else v * 100
def Phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def dcf(fcf, g, shares, netdebt, rate=0.09, tg=0.03, yrs=10):
    cash, pv = fcf, 0.0
    for y in range(1, yrs + 1):
        cash *= 1 + g + (tg - g) * (y - 1) / (yrs - 1)
        pv += cash / (1 + rate) ** y
    pv += cash * (1 + tg) / (rate - tg) / (1 + rate) ** yrs
    return (pv - netdebt) / shares


def consenso(t, info):
    c = {"strongBuy": 0, "buy": 0, "hold": 0, "sell": 0, "strongSell": 0}
    try:
        row = t.recommendations_summary.iloc[0]
        c = {k: int(row[k]) for k in c}
    except Exception:
        pass
    tot = sum(c.values())
    bp = round(100 * (c["strongBuy"] + c["buy"]) / tot) if tot else None
    mean = info.get("recommendationMean")
    label = None if mean is None else "Compra Forte" if mean < 1.8 else "Compra" if mean < 2.6 else "Manter" if mean < 3.4 else "Venda"
    firms = []
    try:
        u = t.upgrades_downgrades.reset_index()
        u = u[u["GradeDate"] >= pd.Timestamp.now() - pd.Timedelta(days=120)].drop_duplicates("Firm")
        for _, x in u.head(5).iterrows():
            firms.append({"f": x["Firm"], "g": x["ToGrade"], "pt": r(x["currentPriceTarget"], 0) if x["currentPriceTarget"] else None})
    except Exception:
        pass
    return {**c, "total": tot, "buy_pct": bp, "label": label, "mean": r(mean), "firms": firms}


SPY = {}
QC = {}  # contadores de controlo de qualidade (vão para data.js → audit)


def naive_index(s):
    i = s.index
    return i.tz_localize(None).normalize() if i.tz is None else i.tz_convert(None).normalize()


def risk_stats(h, p, tgt):
    """Estatísticas de risco do último ano + cenários lognormais a 12 meses (ilustrativos, com CAPM simples)."""
    ret = h.pct_change().dropna()
    if len(ret) < 60:
        return {}
    vol = float(ret.std() * math.sqrt(252))
    dd = float((h / h.cummax() - 1).min() * 100)
    ann = float(ret.mean() * 252)
    sharpe = (ann - RF) / vol if vol else None
    var95 = float(np.percentile(ret, 5) * 100)
    beta = None
    if "ret" in SPY:
        a = ret.copy()
        a.index = naive_index(a)
        j = pd.concat([a.rename("a"), SPY["ret"].rename("b")], axis=1, join="inner").dropna()
        if len(j) >= 100 and j.b.var() > 0:
            beta = float(j.cov().iloc[0, 1] / j.b.var())
    mu = RF + ERP * (beta if beta is not None else 1.0)
    m = mu - vol ** 2 / 2
    z = {5: -1.645, 25: -0.674, 50: 0.0, 75: 0.674, 95: 1.645}
    fan = {str(k): r(p * math.exp(m + vol * zz), 2) for k, zz in z.items()}
    ptouch = None
    if tgt and vol > 0:
        if tgt <= p:
            ptouch = 100.0
        else:
            b = math.log(tgt / p)
            ptouch = 100 * min(1.0, Phi(-(b - m) / vol) + math.exp(min(50, 2 * m * b / vol ** 2)) * Phi((-b - m) / vol))
    return {"vol": r(vol * 100, 0), "maxdd": r(dd, 0), "sharpe": r(sharpe, 2), "var95": r(var95, 1), "beta": r(beta, 2), "mu": r(mu * 100, 1), "fan": fan, "ptouch": r(ptouch, 0)}


def deep(sym):
    try:
        time.sleep(0.4)  # ritmo suave para não ser limitado
        t = yf.Ticker(sym)
        i = retry(lambda: t.info)
        h = retry(lambda: t.history(period="1y"))["Close"].dropna()
        if len(h) < 30:
            return sym, None
        cur, fcur = i.get("currency"), i.get("financialCurrency")
        p = i.get("currentPrice") or i.get("regularMarketPrice") or float(h.iloc[-1])
        lo, hi = i.get("fiftyTwoWeekLow") or float(h.min()), i.get("fiftyTwoWeekHigh") or float(h.max())
        ebitda, debt, cash, mcap = i.get("ebitda"), i.get("totalDebt"), i.get("totalCash"), i.get("marketCap")
        same = (fcur == cur) or fcur is None  # só combina quantias financeiras com o preço se a moeda for a mesma
        nd = (debt - cash) / ebitda if ebitda and debt is not None and cash is not None and ebitda > 0 else None
        fcfy = i["freeCashflow"] / mcap * 100 if i.get("freeCashflow") is not None and mcap and same else None
        tgt, tl, th = i.get("targetMeanPrice"), i.get("targetLowPrice"), i.get("targetHighPrice")
        if tgt and cur in SUB and tgt / p < 0.05:  # alvo em libras e preço em pence (ou equivalente)
            tgt, tl, th = tgt * 100, (tl or 0) * 100 or None, (th or 0) * 100 or None
        if tgt and not (0.3 <= tgt / p <= 3.5):  # alvo incoerente com o preço (moeda/erro de dados): descartado
            QC.setdefault("targets_dropped", []).append(sym)
            tgt = tl = th = None
        up = (tgt / p - 1) * 100 if tgt else None
        fpe, eve = i.get("forwardPE"), i.get("enterpriseToEbitda")
        roe, om = pct(i.get("returnOnEquity")), pct(i.get("operatingMargins"))
        eg, rg = pct(i.get("earningsGrowth")), pct(i.get("revenueGrowth"))
        val = avg([sc(30 - fpe, 0, 22) if fpe and fpe > 0 else None, sc(20 - eve, 0, 14) if eve and eve > 0 else None, sc(fcfy, 0, 8), sc(up, 0, 30)])
        rent = avg([sc(roe, 5, 25), sc(om, 5, 30)])
        solv = avg([None if nd is None else sc(4 - nd, 0, 4)])
        grow = avg([sc(eg, -10, 20), sc(rg, -5, 15)])
        score = round(25 * (val + rent + solv + grow))
        shares = mcap / p if mcap else None
        fin = i.get("sector") == "Financial Services"
        g = 0.03 if eg is None and rg is None else min(0.08, max(0.0, avg([sc(eg, 0, 15) and eg / 100, sc(rg, 0, 15) and rg / 100])))
        dcfv = None
        if not fin and same and shares and i.get("freeCashflow") and i["freeCashflow"] > 0:
            dcfv = dcf(i["freeCashflow"], g, shares, (debt or 0) - (cash or 0))
            dcfv = dcfv if dcfv > 0 else None
        dcf_ok = bool(dcfv and 0.5 * p <= dcfv <= 2 * p)
        parts = [x for x in (tgt, dcfv if dcf_ok else None) if x]
        fair = sum(parts) / len(parts) if parts else None
        buy_below = fair * 0.85 if fair else None
        rs = risk_stats(h, p, tgt)
        vol = rs.get("vol") or 0
        risk = "Baixo" if vol < 22 else "Médio" if vol < 35 else "Alto"
        news = []
        for n in (t.news or [])[:6]:
            c = n.get("content", n)
            url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
            if c.get("title") and url:
                news.append({"title": c["title"], "link": url, "src": (c.get("provider") or {}).get("displayName", ""), "date": (c.get("pubDate") or "")[:10]})
        co = consenso(t, i)
        dy = i.get("dividendYield")
        if sym in TESE:
            f = TESE[sym]
            tese = {"faz": f[0], "barata": f[1], "cat": f[2], "riscos": f[3]}
        else:
            tese = {"faz": ((i.get("longBusinessSummary") or "Sem descrição disponível.")[:420] + " (resumo do Yahoo, em inglês)"), "barata": [], "cat": [], "riscos": []}
        cat = CURATED.get(sym) or ("d" if (dy or 0) >= 3 and risk != "Alto" else "g" if (rg or 0) >= 10 or (eg or 0) >= 15 else "v")
        return sym, {
            "name": NOMES.get(sym) or i.get("shortName") or i.get("longName") or sym, "cat": cat, "sector": i.get("sector"), "industry": i.get("industry"), "cur": cur,
            "price": r(p), "low": r(lo), "high": r(hi), "d1": r((p / float(h.iloc[-2]) - 1) * 100, 2) if len(h) > 1 else None, "m1": r((p / float(h.iloc[-22]) - 1) * 100, 1) if len(h) > 22 else None,
            "drawdown": r((p / hi - 1) * 100, 1), "target": r(tgt), "tlow": r(tl), "thigh": r(th), "upside": r(up, 1),
            "dcf": r(dcfv), "dcf_ok": dcf_ok, "dcf_up": r((dcfv / p - 1) * 100, 1) if dcfv else None, "fair": r(fair), "buy_below": r(buy_below),
            "zone": "buy" if buy_below and p <= buy_below else "wait", "cons": co, "risk": risk, "vol": rs.get("vol"), "rs": rs,
            "dy": r(dy, 2), "payout": r(pct(i.get("payoutRatio")), 0), "pe": r(i.get("trailingPE"), 1), "fpe": r(fpe, 1), "eve": r(eve, 1), "roe": r(roe, 1), "om": r(om, 1), "nd": r(nd, 1),
            "fcfy": r(fcfy, 1), "eg": r(eg, 1), "rg": r(rg, 1), "score": score, "pillars": [round(25 * x) for x in (val, rent, solv, grow)], "mcap": mcap, "tese": tese,
            "hist": [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in h.items()], "news": news}
    except Exception as e:
        log("deep falhou", sym, str(e)[:80])
        return sym, None


# ---------------------------------------------------------------- orquestração
def nz(v, d=0):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), d)


def build(quick=False):
    t0 = time.time()
    QC.clear()
    quotes, fx = fetch_universe(SECTORS[:2] if quick else SECTORS)
    df = to_frame(quotes, fx)
    log(f"universo: {len(df)} ações · {df.ex.nunique()} bolsas · {time.time() - t0:.0f}s")
    F, comp = factors(df)
    df["sc1"] = comp
    for c in F.columns:
        df["f_" + c] = F[c]
    stats = sector_stats(df)
    cand = df[(df.mcap >= DEEP_MIN_USD) & df.sc1.notna()].nlargest(DEEP_N, "sc1").s.tolist()
    want = list(dict.fromkeys(list(CURATED) + cand))
    try:
        s = yf.Ticker("SPY").history(period="1y")["Close"].dropna()
        s.index = naive_index(s)
        SPY["ret"] = s.pct_change().dropna()
    except Exception:
        pass
    log(f"análise profunda: {len(want)} ações …")
    T = {}
    for passo in range(3):  # repete as que falharam por limite de pedidos
        pend = [x for x in want if x not in T]
        if not pend:
            break
        if passo:
            log(f"  nova tentativa de {len(pend)} ações após pausa …")
            time.sleep(40)
        with ThreadPoolExecutor(3) as ex:
            T.update({s: d for s, d in ex.map(deep, pend) if d})
    log(f"profundas concluídas: {len(T)}/{len(want)} · {time.time() - t0:.0f}s")
    byS = df.set_index("s")
    for s, t in T.items():
        v = byS.sc1.get(s) if s in byS.index else None
        v = 50.0 if v is None or pd.isna(v) else float(v)
        t["sc1"] = round(v)
        c = t["cons"]
        bpa = 100 * (c["strongBuy"] + c["buy"] + 2.5) / (c["total"] + 5)  # consenso com prior de 5 analistas neutros: 1 só analista não vale 100%
        t["rank"] = round(0.30 * t["score"] + 0.20 * v + 0.25 * 100 * (sc(t["upside"], 0, 40) or 0) + 0.25 * bpa - {"Baixo": 0, "Médio": 4, "Alto": 12}[t["risk"]])
    elig = [s for s in T if s in CURATED or (s in byS.index and byS.mcap[s] >= DEEP_MIN_USD)]
    order = sorted(elig, key=lambda s: -T[s]["rank"])
    solid = [s for s in order if T[s]["cons"]["total"] >= 5]  # destaques exigem pelo menos 5 analistas
    safe = [s for s in solid if (T[s]["dy"] or 0) >= 2 and T[s]["risk"] != "Alto" and (T[s]["payout"] or 0) < 90 and (T[s]["fcfy"] or 0) > 0 and (T[s]["eg"] is None or T[s]["eg"] >= -5)]
    disc = [s for s in solid if s != solid[0] and T[s]["score"] >= 55 and (T[s]["cons"]["buy_pct"] or 0) >= 50 and T[s]["upside"]]
    hl = {"pick": solid[0], "dividend": max(safe, key=lambda s: T[s]["dy"]) if safe else None, "discount": max(disc, key=lambda s: T[s]["upside"]) if disc else None}
    def pos(v, d=1):  # rácios negativos (prejuízo / capital próprio negativo) não são mostrados
        return None if v is None or pd.isna(v) or v <= 0 else nz(v, d)
    cols = ["s", "name", "ex", "cur", "sec", "px", "chg", "mcap", "fpe", "pe", "pb", "dy", "ret", "hi", "lo", "rat", "sc1", "fv", "fg", "fm", "fa", "fi", "fx", "dp", "tm"]
    rows = []
    for x in df.itertuples():
        rows.append([x.s, str(x.name)[:40], x.ex, x.cur, x.sec, nz(x.px, 2 if x.px < 1000 else 0), nz(x.chg, 2), round(x.mcap / 1e6), pos(x.fpe), pos(x.pe), pos(x.pb), nz(x.dy, 2), nz(x.ret, 1),
                     nz(x.hi, 2), nz(x.lo, 2), nz(x.rat, 1), nz(x.sc1), nz(x.f_v), nz(x.f_g), nz(x.f_m), nz(x.f_a), nz(x.f_i), nz(x.fx, 6), 1 if x.s in T else 0, int(x.tm / 60)])

    def quote(sym):
        try:
            c = yf.Ticker(sym).history(period="5d")["Close"].dropna()
            return sym, {"price": r(c.iloc[-1], 2), "prev": r(c.iloc[-2], 2)}
        except Exception:
            return sym, None
    with ThreadPoolExecutor(3) as ex:
        tape = {s: q for s, q in ex.map(quote, TAPE) if q}
    # --- auditoria de coerência
    mism = [s for s, t in T.items() if s in byS.index and byS.px[s] and abs(t["price"] / byS.px[s] - 1) > 0.05]
    nm = df.name.map(norm)
    dupn = int(sum(1 for _, g in df.assign(_n=nm).groupby("_n") if len(g) > 1 and (g.mcap.max() / g.mcap.min()) < 1.5 and g._n.iloc[0]))
    QC.update({"universe": len(df), "dup_symbols": int(len(df) - df.s.nunique()), "dup_names_left": dupn, "deep_missing_in_rows": [s for s in T if s not in byS.index],
               "price_mismatch": mism, "deep_ok": len(T), "deep_wanted": len(want), "oldest_price_days": round((time.time() - float(df.tm.min())) / 86400, 1),
               "median_price_age_h": round(float((time.time() - df.tm).median()) / 3600, 1)})
    return {"audit": QC, "updated": time.strftime("%Y-%m-%d %H:%M"), "eurusd": tape.get("EURUSD=X", {}).get("price"), "order": order, "highlights": hl, "tickers": T, "cols": cols, "rows": rows,
            "pais": PAIS, "exinfo": {k: {"n": v[0], "p": v[1], "r": v[2]} for k, v in EX.items()}, "sector_stats": stats, "meta": {"n_universe": len(df), "n_deep": len(T), "n_exch": int(df.ex.nunique()), "min_usd": MIN_USD, "deep_min_usd": DEEP_MIN_USD, "rf": RF, "erp": ERP}}


def refresh_rows(d):
    """Atualiza preços/variação do universo inteiro (≈10 s) sem refazer a análise profunda. Usado pelo Streamlit."""
    quotes, fx = fetch_universe(SECTORS)
    cur = to_frame(quotes, fx).set_index("s")
    ci = {c: i for i, c in enumerate(d["cols"])}
    for row in d["rows"]:
        if row[0] in cur.index:
            x = cur.loc[row[0]]
            row[ci["px"]], row[ci["chg"]], row[ci["tm"]] = nz(x.px, 2 if x.px < 1000 else 0), nz(x.chg, 2), int(x.tm / 60)
    for s, t in d["tickers"].items():
        if s in cur.index:
            p = float(cur.px[s])
            t["price"], t["d1"] = round(p, 2), nz(cur.chg[s], 2)
            if t.get("target"):
                t["upside"] = round((t["target"] / p - 1) * 100, 1)
            t["zone"] = "buy" if t.get("buy_below") and p <= t["buy_below"] else "wait"
    d["updated"] = time.strftime("%Y-%m-%d %H:%M")
    return d


if __name__ == "__main__":
    d = build(quick="--quick" in sys.argv)
    open("data.js", "w", encoding="utf-8").write("window.DATA=" + json.dumps(d, separators=(",", ":")).replace("</", "<\\/"))
    log("TOP:", ", ".join(f"{s} {d['tickers'][s]['rank']}" for s in d["order"][:10]), "· destaques:", d["highlights"])
