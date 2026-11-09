"""Notícias abertas (RSS CNBC, MarketWatch, Bloomberg, Yahoo) + motor de sentimento financeiro por léxico (sem dependências)."""
import re, time, html
import xml.etree.ElementTree as ET
import requests

FEEDS = [("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
         ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
         ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
         ("Yahoo Finance", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US")]

# Léxico financeiro: palavras exatas (curtas) + radicais (≥5 letras, apanham flexões: investigates/investigation…) + expressões
POS_W = {"beat": 2, "beats": 2, "record": 1.5, "buy": 1, "gain": 1, "gains": 1, "rise": 1, "rises": 1, "rose": 1, "climb": 1, "climbs": 1, "jump": 1.5, "jumps": 1.5, "win": 1, "wins": 1.5,
         "top": 1, "tops": 1.5, "boost": 1.5, "boosts": 1.5, "raise": 1.5, "raises": 1.5, "raised": 1.5, "strong": 1.5, "profit": 1, "profits": 1, "growth": 1, "deal": 0.5, "dividend": 1, "buyback": 1.5}
POS_S = {"surg": 2, "soar": 2, "rally": 1.5, "rallies": 1.5, "upgrad": 2, "outperform": 2, "approv": 1.5, "breakthrough": 2, "optimis": 1.5, "bullish": 2, "rebound": 1.5, "recover": 1,
         "exceed": 1.5, "strengthen": 1.5, "accelerat": 1.5, "expand": 1, "thrive": 1.5, "boom": 1.5, "milestone": 1}
NEG_W = {"miss": 2, "misses": 2, "missed": 2, "fall": 1.2, "falls": 1.2, "fell": 1.2, "drop": 1.5, "drops": 1.5, "dropped": 1.5, "sink": 2, "sinks": 2, "sank": 2, "cut": 1.5, "cuts": 1.5, "loss": 1.5,
         "losses": 1.5, "lose": 1.2, "loses": 1.2, "weak": 1.5, "fear": 1.5, "fears": 1.5, "risk": 0.6, "risks": 0.6, "threat": 1.5, "slide": 1.5, "slides": 1.5, "slid": 1.5, "fine": 1, "fined": 1.5,
         "ban": 1.5, "banned": 1.5, "halt": 1.5, "halts": 1.5, "delay": 1, "delays": 1, "sell": 0.5, "short": 0.5, "worry": 1.2, "worries": 1.2, "tariff": 1, "tariffs": 1, "spy": 2, "ousted": 2.5, "fired": 2}
NEG_S = {"plung": 2.5, "tumbl": 2, "slump": 2, "crash": 3, "selloff": 2, "warn": 2, "weaken": 1.5, "declin": 1.5, "disappoint": 2, "slash": 2, "downgrad": 2, "underperform": 2, "scandal": 3,
         "investigat": 2.5, "lawsuit": 2, "fraud": 3, "bankrupt": 3, "recall": 2, "layoff": 1.5, "subpoena": 2.5, "antitrust": 2, "sanction": 2, "restat": 2.5, "delist": 3, "resign": 2, "concern": 1,
         "scrutin": 1.5, "slowdown": 1.5, "bearish": 2, "pessimis": 1.5, "default": 2.5, "probe": 2, "plummet": 2.5, "struggl": 1.5, "crisis": 2.5, "turmoil": 2, "controvers": 1.5}
PHRASES_POS = {"all-time high": 2, "raises guidance": 2, "beats expectations": 2, "record high": 2, "price target raised": 1.5}
PHRASES_NEG = {"sell-off": 2, "cuts guidance": 2.5, "lowers guidance": 2.5, "short seller": 2.5, "going concern": 3, "price target cut": 1.5, "profit warning": 2.5, "accounting irregular": 3}
# sinais de problema estrutural (afetam o negócio, não só o preço)
STRUCT_S = ("investigat", "scandal", "lawsuit", "fraud", "bankrupt", "subpoena", "antitrust", "sanction", "restat", "delist", "resign", "recall", "probe", "layoff", "crisis", "controvers")
STRUCT_W = {"spy", "ousted", "fired", "ban", "banned", "default"}
STRUCT_P = ("short seller", "going concern", "cuts guidance", "lowers guidance", "profit warning", "accounting irregular")


def _tok(title):
    low = title.lower()
    return low, re.findall(r"[a-z][a-z\-']+", low)


def score(title):
    """−1…+1 e nº de sinais estruturais, por léxico transparente (palavras, radicais, expressões)."""
    low, ws = _tok(title)
    pos = neg = 0.0
    st = 0
    for w in ws:
        pos += POS_W.get(w, 0) + sum(v for k, v in POS_S.items() if w.startswith(k))
        neg += NEG_W.get(w, 0) + sum(v for k, v in NEG_S.items() if w.startswith(k))
        if w in STRUCT_W or any(w.startswith(k) for k in STRUCT_S):
            st += 1
    for k, v in PHRASES_POS.items():
        pos += v if k in low else 0
    for k, v in PHRASES_NEG.items():
        neg += v if k in low else 0
    st += sum(1 for k in STRUCT_P if k in low)
    return max(-1.0, min(1.0, (pos - neg) / 3.0)), st


def label(v):
    return "pos" if v >= 0.15 else "neg" if v <= -0.15 else "neu"


def summarize(items):
    """Agregado de sentimento dos títulos (mais recentes primeiro pesam mais)."""
    if not items:
        return {"n": 0, "label": None}
    sc = [score(a["title"]) for a in items]
    wts = [1 / (1 + 0.15 * i) for i in range(len(sc))]
    m = sum(w * s for w, (s, _) in zip(wts, sc)) / sum(wts)
    return {"n": len(sc), "mean": round(m, 2), "label": label(m), "pos": sum(1 for s, _ in sc if s >= .15), "neg": sum(1 for s, _ in sc if s <= -.15),
            "neu": sum(1 for s, _ in sc if -.15 < s < .15), "struct": sum(1 for _, k in sc if k)}


def tag(items):
    for a in items:
        a["s"] = label(score(a["title"])[0])
    return items


def verdict(drawdown, d1, summ, q):
    """Veredicto SEMPRE presente: o que as notícias dizem e o que isso significa para quem pensa em comprar."""
    if not summ or not summ.get("n"):
        return {"k": "sem", "label": "Sem notícias recentes", "t": "Não há notícias recentes nas fontes consultadas, por isso este indicador não influencia a decisão.", "a": "Decide pelos números da ficha."}
    qs = (q or {}).get("qscore")
    solid = qs is not None and qs >= 65
    dd = drawdown if drawdown is not None else 0
    st, neg, pos, n = summ.get("struct", 0), summ.get("neg", 0), summ.get("pos", 0), summ["n"]
    if st >= 2 and neg >= 2 or summ["mean"] <= -0.35:
        return {"k": "estrutural", "label": "🔴 Notícias graves", "t": f"{neg} de {n} notícias são negativas e {st} mencionam temas sérios (investigações, processos, gestão, contabilidade). Pode haver um problema que afete o negócio, não só o preço.",
                "a": "Evita comprar a queda até perceberes o impacto nos lucros. Se já tens a ação, reavalia a tese." + (" As contas continuam sólidas, o que atenua o risco." if solid else "")}
    if summ["label"] == "neg":
        return {"k": "negativo", "label": "🟠 Tom negativo", "t": f"{neg} de {n} notícias são negativas, mas sem temas graves: parece mais ruído de mercado ou resultados fracos do que um problema estrutural.",
                "a": ("Possível reação exagerada: as contas são sólidas. Espera o preço estabilizar e entra por fases." if solid and dd <= -8 else "Acompanha antes de entrar; confirma se os resultados e as estimativas se mantêm.")}
    if summ["label"] == "pos":
        return {"k": "positivo", "label": "🟢 Notícias positivas", "t": f"{pos} de {n} notícias são positivas e nenhuma menciona temas graves.",
                "a": "Boas notícias ajudam, mas já podem estar no preço: respeita a zona de compra." if dd > -8 else "O preço caiu apesar de notícias positivas: pode ser oportunidade, confirma a zona de compra."}
    return {"k": "neutro", "label": "🟡 Notícias neutras", "t": f"{n} notícias recentes sem tom claro ({pos} positivas, {neg} negativas)." + (f" {st} mencionam temas que merecem leitura." if st else ""),
            "a": "As notícias não alteram a análise: decide pelos números (zona de compra, qualidade, metas)."}


def market(limit=24):
    out, ok = [], []
    for name, url in FEEDS:
        try:
            r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12)
            root = ET.fromstring(r.content)
            n = 0
            for it in root.iter("item"):
                t, l = (it.findtext("title") or "").strip(), (it.findtext("link") or "").strip()
                if t and l:
                    out.append({"title": html.unescape(t), "link": l, "src": name, "date": (it.findtext("pubDate") or "")[:22]})
                    n += 1
                if n >= 8:
                    break
            ok.append(name)
        except Exception:
            pass
    seen, res = set(), []
    for a in out:
        k = re.sub(r"\W+", "", a["title"].lower())[:50]
        if k not in seen:
            seen.add(k)
            res.append(a)
    return {"items": tag(res[:limit]), "sources": ok, "summary": summarize(res), "ts": int(time.time())}
