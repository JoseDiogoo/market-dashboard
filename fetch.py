"""Pipeline global: screener (milhares de ações) -> estatística (percentis por setor) -> análise profunda do top N -> data.js
Uso: python fetch.py [--quick]   (--quick = só 2 setores, para testar)"""
import quality, news, tese_auto
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
    return bool(re.search(r"-P[A-Z]?$", s)) or bool(re.search(r"[A-Z]\d{2}\.SA$", s) and not s.endswith("11.SA")) or bool(re.search(r"\d{2}\.BK$|-[RFN]\.BK$", s))


def norm(name):
    return " ".join(w for w in re.findall(r"[a-z0-9]+", str(name).lower()) if w not in STOPW)


GENERIC = {"bank", "energy", "group", "international", "holdings", "technologies", "technology", "financial", "industries", "resources", "systems", "global", "services", "capital", "trust", "partners",
           "pharmaceuticals", "corporation", "company", "limited", "national", "united", "american", "first", "real", "estate", "insurance", "health", "healthcare", "media", "entertainment", "motor",
           "motors", "mining", "gold", "power", "electric", "electronics", "communications", "solutions", "software", "brands", "foods", "water", "gas", "oil", "petroleum"}


def toks(name):
    return {w for w in re.findall(r"[a-z]+", str(name).lower()) if len(w) >= 4 and w not in STOPW and w not in GENERIC}


def same_company(n1, m1, n2, m2):
    """Mesma empresa cotada em duas bolsas: nomes com palavra distintiva em comum e capitalização em USD quase idêntica (±7%)."""
    return 0.93 <= m1 / m2 <= 1.07 and bool(toks(n1) & toks(n2))


def base(sym):
    return sym.split(".")[0].upper()


def same_ticker(s1, n1, m1, s2, n2, m2):
    """Mesmo ticker-base em bolsas diferentes (ex.: MRVL e MRVL.SW) e nomes com palavra distintiva comum = mesma empresa, mesmo que a cotação secundária esteja desatualizada."""
    return base(s1) == base(s2) and s1 != s2 and (bool(toks(n1) & toks(n2)) or 0.6 <= m1 / m2 <= 1.7)


def dedupe(df):
    """A mesma empresa em várias bolsas: mantém a cotação mais líquida (curadas têm prioridade)."""
    keep, seen, buckets, bases = [], {}, {}, {}
    for i, r_ in df.assign(_n=df.name.map(norm), _c=df.s.isin(CURATED)).sort_values(["_c", "dvol"], ascending=False).iterrows():
        b = int(math.log(r_.mcap) / 0.07)
        dup = (r_._n and any(0.67 <= r_.mcap / m <= 1.5 for m in seen.get(r_._n, []))) or any(same_company(r_["name"], r_.mcap, n2, m2) for bb in (b - 1, b, b + 1) for n2, m2 in buckets.get(bb, []))
        dup = dup or any(same_ticker(r_.s, r_["name"], r_.mcap, s2, n2, m2) for s2, n2, m2 in bases.get(base(r_.s), []))
        if dup:
            continue
        bases.setdefault(base(r_.s), []).append((r_.s, r_["name"], r_.mcap))
        seen.setdefault(r_._n, []).append(r_.mcap)
        buckets.setdefault(b, []).append((r_["name"], r_.mcap))
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


def atr14(hd):
    """Average True Range de 14 dias (Wilder) em unidades de preço; None se faltarem máximos/mínimos."""
    try:
        d = hd[["High", "Low", "Close"]].dropna()
        pc = d["Close"].shift(1)
        tr = pd.concat([d["High"] - d["Low"], (d["High"] - pc).abs(), (d["Low"] - pc).abs()], axis=1).max(axis=1).dropna()
        if len(tr) < 30:
            return None
        return float(tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1])
    except Exception:
        return None


def levels(h, p, w=8, tol=0.025):
    """Suportes/resistências: pivôs (mínimos/máximos locais em ±w dias) agrupados a ±2,5%. n = nº de vezes que o preço reagiu ali."""
    v = h.values.astype(float)
    if len(v) < 2 * w + 5:
        return {}
    piv = []
    for k in range(w, len(v) - w):
        seg = v[k - w:k + w + 1]
        if v[k] == seg.min() or v[k] == seg.max():
            piv.append(v[k])
    cl = []
    for x in sorted(piv):
        if cl and x <= cl[-1][0] * (1 + tol):
            cl[-1][1].append(x)
            cl[-1][0] = float(np.mean(cl[-1][1]))
        else:
            cl.append([x, [x]])
    lv = [(c[0], len(c[1])) for c in cl]
    sup = sorted([x for x in lv if x[0] < p * 0.99], key=lambda x: -x[0])
    res = sorted([x for x in lv if x[0] > p * 1.01], key=lambda x: x[0])
    pick = lambda a: [{"p": r(x[0], 2), "n": x[1]} for x in sorted(a, key=lambda x: (-(x[1] >= 2), abs(x[0] / p - 1)))[:3]]
    return {"sup": sorted(pick(sup), key=lambda x: -x["p"]), "res": sorted(pick(res), key=lambda x: x["p"])}


def cl(v, hi=300):
    """ratios absurdos (P/E de 4000, etc.) → None: não aparecem nem entram em comparações"""
    return None if v is None or not (1 <= v < hi) else v


def deep(sym):
    try:
        time.sleep(0.4)  # ritmo suave para não ser limitado
        t = yf.Ticker(sym)
        i = retry(lambda: t.info)
        hd = retry(lambda: t.history(period="1y"))
        h = hd["Close"].dropna()
        atr = atr14(hd)
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
        try:
            h5 = retry(lambda: t.history(period="6y", interval="1mo"))["Close"].dropna()
            h5.index = naive_index(h5)
        except Exception:
            h5 = None
        q = quality.analyze(t, i, p, mcap, rs.get("beta"), h5, fin)
        vol = rs.get("vol") or 0
        risk = "Baixo" if vol < 22 else "Médio" if vol < 35 else "Alto"
        nws = []
        for n_ in (t.news or [])[:10]:
            c = n_.get("content", n_)
            url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
            if c.get("title") and url:
                nws.append({"title": c["title"], "link": url, "src": (c.get("provider") or {}).get("displayName", ""), "date": (c.get("pubDate") or "")[:10]})
        news.tag(nws)
        senti = news.summarize(nws)
        dropv = news.verdict((p / hi - 1) * 100 if hi else None, float(h.iloc[-1] / h.iloc[-2] - 1) * 100 if len(h) > 1 else None, senti, q)
        eps_t, eps_f = i.get("trailingEps"), i.get("forwardEps")
        sim = {"r": 0.09, "tg": 0.03, "g": round(g, 4), "nd": r((debt or 0) - (cash or 0), 0) if same else None, "sh": r(shares, 0), "fpe": r(cl(fpe), 1)}
        if dcfv is not None and not fin:
            sim.update({"mode": "dcf", "fcf": r(i["freeCashflow"], 0)})
        elif same and eps_t and eps_t > 0:
            sim.update({"mode": "pe", "eps": r(eps_t, 2), "epsf": r(eps_f, 2) if eps_f and eps_f > 0 else None})
        co = consenso(t, i)
        dy = i.get("dividendYield")
        cat = CURATED.get(sym) or ("d" if (dy or 0) >= 3 and risk != "Alto" else "g" if (rg or 0) >= 10 or (eg or 0) >= 15 else "v")
        out = {
            "name": NOMES.get(sym) or i.get("shortName") or i.get("longName") or sym, "cat": cat, "sector": i.get("sector"), "industry": i.get("industry"), "cur": cur,
            "price": r(p), "low": r(lo), "high": r(hi), "d1": r((p / float(h.iloc[-2]) - 1) * 100, 2) if len(h) > 1 else None, "m1": r((p / float(h.iloc[-22]) - 1) * 100, 1) if len(h) > 22 else None,
            "drawdown": r((p / hi - 1) * 100, 1), "target": r(tgt), "tlow": r(tl), "thigh": r(th), "upside": r(up, 1),
            "dcf": r(dcfv), "dcf_ok": dcf_ok, "dcf_up": r((dcfv / p - 1) * 100, 1) if dcfv else None, "fair": r(fair), "buy_below": r(buy_below),
            "zone": "buy" if buy_below and p <= buy_below else "wait", "cons": co, "risk": risk, "vol": rs.get("vol"), "rs": rs,
            "dy": r(dy, 2), "payout": r(pct(i.get("payoutRatio")), 0), "pe": r(cl(i.get("trailingPE")), 1), "fpe": r(cl(fpe), 1), "eve": r(cl(eve), 1), "roe": r(roe, 1), "om": r(om, 1), "nd": r(nd, 1),
            "fcfy": r(fcfy, 1), "eg": r(eg, 1), "rg": r(rg, 1), "mcap": mcap, "q": q, "sr": levels(h, p), "sim": sim, "atr": r(atr, 2),
            "hist": [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in h.items()], "news": nws, "senti": senti, "drop": dropv}
        auto = tese_auto.gen(i, {**out, "cat": None})
        if sym in TESE:  # curadas: texto escrito à mão + saúde financeira automática
            f = TESE[sym]
            out["tese"] = {"faz": f[0], "barata": f[1], "saude": auto["saude"], "cat": f[2] + auto["cat"][:2], "riscos": f[3] + auto["riscos"][:2], "hand": True}
        else:
            out["tese"] = {**auto, "hand": False}
        return sym, out
    except Exception as e:
        log("deep falhou", sym, str(e)[:80])
        return sym, None


def macro():
    """Taxas dos EUA via FRED (CSV público, sem chave). Falha → mantém 4%. Devolve {id: (valor %, data)}."""
    global RF
    import requests, io
    out = {}
    for sid, nm in (("DGS10", "Treasury 10 anos"), ("DGS2", "Treasury 2 anos"), ("DFF", "Fed Funds")):
        try:
            txt = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=25, headers={"User-Agent": "Mozilla/5.0"}).text
            rows = [l.split(",") for l in txt.strip().splitlines()[1:] if l.split(",")[-1] not in (".", "")]
            out[sid] = {"n": nm, "v": float(rows[-1][1]), "d": rows[-1][0]}
        except Exception:
            pass
    if "DGS10" in out and 0.5 < out["DGS10"]["v"] < 12:
        RF = quality.RF = out["DGS10"]["v"] / 100
    return out


# ---------------------------------------------------------------- orquestração
def nz(v, d=0):
    return None if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else round(float(v), d)


def rerank(d):
    """Classificação comum à geração e à renovação de preços."""
    d.setdefault("analysis_updated", d["updated"])
    T = d["tickers"]
    rows = {row[0]: dict(zip(d["cols"], row)) for row in d["rows"]}
    for s, t in T.items():
        row = rows.get(s, {})
        # O consenso entra separadamente: retirar o fator analistas desta parcela.
        v = sum(w * (row.get(k) if row.get(k) is not None else 50) for k, w in (("fv", .30), ("fg", .20), ("fm", .15), ("fi", .10))) / .75
        fpe, eve = t.get("fpe"), t.get("eve")
        val = avg([sc(30 - fpe, 0, 22) if fpe and fpe > 0 else None, sc(20 - eve, 0, 14) if eve and eve > 0 else None, sc(t.get("fcfy"), 0, 8)])
        rent = avg([sc(t.get("roe"), 5, 25), sc(t.get("om"), 5, 30)])
        solv = avg([sc(4 - t["nd"], 0, 4) if t.get("nd") is not None else None])
        grow = avg([sc(t.get("eg"), -10, 20), sc(t.get("rg"), -5, 15)])
        t["score"] = round(25 * (val + rent + solv + grow))
        t["pillars"] = [round(25 * x) for x in (val, rent, solv, grow)]
        t["sc1"] = row.get("sc1")
        c = t["cons"]
        bpa = 100 * (c["strongBuy"] + c["buy"] + 2.5) / (c["total"] + 5)  # consenso com prior de 5 analistas neutros: 1 só analista não vale 100%
        qs = t["q"].get("qscore")
        qs = 50 if qs is None else qs
        nm_ = t["q"].get("norm") or {}
        pen = {"Baixo": 0, "Médio": 4, "Alto": 12}[t["risk"]] + (8 if t["q"].get("trap") else 0) + (12 if nm_.get("peak") else 6 if nm_.get("cyc") else 0)
        t["rank"] = round(0.22 * t["score"] + 0.15 * v + 0.23 * 100 * (sc(t["upside"], 0, 40) or 0) + 0.20 * bpa + 0.20 * qs - pen)

    def elite(t):  # crivo do Top 10: compounders com consenso forte, caixa real, balanço saudável
        q, c = t["q"], t["cons"]
        return bool(c["total"] >= 10 and (c["buy_pct"] or 0) > 65 and q.get("compounder", {}).get("ok") and not q.get("trap") and not (q.get("norm") or {}).get("peak")
                    and (q.get("qscore") or 0) >= 60 and (q.get("altman") or {}).get("zone") != "perigo" and (t.get("nd") is not None and t["nd"] < 4)
                    and (t.get("fcfy") is not None and t["fcfy"] > 0))
    for t in T.values():
        t["elite"] = elite(t)
    elig = [s for s in T if s in CURATED or ((rows.get(s, {}).get("mcap") or 0) * 1e6 >= DEEP_MIN_USD)]
    order = sorted(elig, key=lambda s: (not T[s]["elite"], -T[s]["rank"]))
    solid = [s for s in order if T[s]["cons"]["total"] >= 5]  # destaques exigem pelo menos 5 analistas
    clean = [s for s in solid if not T[s]["q"].get("trap")]
    safe = [s for s in clean if (T[s]["dy"] or 0) >= 2 and T[s]["risk"] != "Alto" and T[s].get("payout") is not None and T[s]["payout"] < 90 and (T[s]["fcfy"] or 0) > 0 and (T[s]["eg"] is None or T[s]["eg"] >= -5)]
    pick = clean[0] if clean else solid[0] if solid else None
    disc = [s for s in clean if s != pick and T[s]["score"] >= 55 and (T[s]["cons"]["buy_pct"] or 0) >= 50 and T[s]["upside"] and (T[s]["q"].get("qscore") or 0) >= 60]
    hl = {"pick": pick, "dividend": max(safe, key=lambda s: T[s]["dy"]) if safe else None, "discount": max(disc, key=lambda s: T[s]["upside"]) if disc else None}
    d["order"], d["highlights"] = order, hl
    d.setdefault("audit", {})["elite"] = sum(t["elite"] for t in T.values())
    return d


def build(quick=False):
    t0 = time.time()
    QC.clear()
    MAC = macro()
    log(f"macro: {MAC} · RF={RF:.4f}")
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
    try:
        mn = news.market()
    except Exception:
        mn = {"items": [], "sources": [], "summary": {"n": 0}}
    QC.update({"market_news_sources": mn["sources"], "macro": {k: v["v"] for k, v in MAC.items()}})
    d = {"mnews": mn, "macro": MAC, "version": "Radar de Investimento", "tape": tape, "tape_names": TAPE, "audit": QC, "updated": time.strftime("%Y-%m-%d %H:%M"), "eurusd": tape.get("EURUSD=X", {}).get("price"), "order": [], "highlights": {}, "tickers": T, "cols": cols, "rows": rows,
            "pais": PAIS, "exinfo": {k: {"n": v[0], "p": v[1], "r": v[2]} for k, v in EX.items()}, "sector_stats": stats, "meta": {"n_universe": len(df), "n_deep": len(T), "n_exch": int(df.ex.nunique()), "min_usd": MIN_USD, "deep_min_usd": DEEP_MIN_USD, "rf": RF, "erp": ERP, "sources": ["Yahoo Finance (cotações, fundamentais, analistas, insiders)", "FRED (taxas EUA)", "CNBC / MarketWatch / Bloomberg / Yahoo (notícias RSS)"]}}
    return rerank(d)


def refresh_rows(d):
    """Atualiza preços do universo (≈10 s) sem refazer a análise profunda. Multi-fonte com reserva:
    1) screener do Yahoo (universo inteiro) → 2) download em lote do Yahoo (só análises completas) → 3) mantém o snapshot (marcado como atrasado)."""
    t0 = time.time()
    src = {"name": "Yahoo Finance · screener", "ok": True, "mode": "full"}
    cur = None
    try:
        quotes, fx = fetch_universe(SECTORS)
        cur = to_frame(quotes, fx).set_index("s")
        if fx.get("EUR") and math.isfinite(fx["EUR"]) and fx["EUR"] > 0:
            d["eurusd"] = fx["EUR"]
    except Exception as e:
        log("refresh: screener falhou", str(e)[:80])
    if cur is None or cur.empty:
        try:  # reserva: endpoint diferente, só as ações com análise completa
            syms = list(d["tickers"])
            h = yf.download(syms, period="5d", progress=False, auto_adjust=False, threads=True)["Close"].dropna(how="all")
            rows = {s: (float(h[s].dropna().iloc[-1]), float(h[s].dropna().iloc[-1] / h[s].dropna().iloc[-2] - 1) * 100) for s in syms if s in h and len(h[s].dropna()) > 1}
            cur = pd.DataFrame({"px": {s: v[0] for s, v in rows.items()}, "chg": {s: v[1] for s, v in rows.items()}, "tm": {s: h[s].dropna().index[-1].timestamp() for s in rows}})
            src = {"name": "Yahoo Finance · download (reserva)", "ok": bool(len(cur)), "mode": "deep"}
        except Exception as e:
            log("refresh: reserva falhou", str(e)[:80])
            cur = pd.DataFrame(columns=["px", "chg", "tm"])
            src = {"name": "Snapshot guardado", "ok": False, "mode": "stale"}
    d.setdefault("analysis_updated", d["updated"])
    ci = {c: i for i, c in enumerate(d["cols"])}
    refreshed = set()
    for row in d["rows"]:
        if row[0] in cur.index:
            x = cur.loc[row[0]]
            if not math.isfinite(float(x.px)) or x.px <= 0 or not math.isfinite(float(x.tm)):
                continue
            refreshed.add(row[0])
            if "fx" in x and pd.notna(x.fx):
                row[ci["fx"]] = nz(x.fx, 6)
            row[ci["px"]], row[ci["chg"]], row[ci["tm"]] = nz(x.px, 2 if x.px < 1000 else 0), nz(x.chg, 2), int(x.tm / 60)
    for s, t in d["tickers"].items():
        if s in refreshed:
            p = float(cur.px[s])
            if not math.isfinite(p) or p <= 0:
                continue
            old = t["price"]
            for key in ("pe", "fpe"):
                if t.get(key) is not None:
                    t[key] = r(t[key] * p / old, 1)
            for key in ("fcfy", "dy"):
                if t.get(key) is not None:
                    t[key] = r(t[key] * old / p, 2)
            if t.get("mcap"):
                t["mcap"] *= p / old
            t["price"], t["d1"] = round(p, 2), nz(cur.chg[s], 2)
            if t.get("target"):
                t["upside"] = round((t["target"] / p - 1) * 100, 1)
            t["zone"] = "buy" if t.get("buy_below") and p <= t["buy_below"] else "wait"
    try:
        d["mnews"] = news.market()
    except Exception:
        pass
    src["ok"] = bool(refreshed)
    src["coverage"] = len(refreshed) / max(1, len(d["rows"]))
    if not refreshed:
        src["mode"] = "stale"
    elif len(refreshed) < len(d["rows"]):
        src["mode"] = "partial"
    src["ms"] = int((time.time() - t0) * 1000)
    src["ts"] = int(time.time())
    d["source"] = src
    # updated é a data da análise; nunca a hora de uma tentativa de rede.
    return rerank(d)


if __name__ == "__main__":
    d = build(quick="--quick" in sys.argv)
    open("data.js", "w", encoding="utf-8").write("window.DATA=" + json.dumps(d, separators=(",", ":")).replace("</", "<\\/"))
    log("TOP:", ", ".join(f"{s} {d['tickers'][s]['rank']}" for s in d["order"][:10]), "· destaques:", d["highlights"])
