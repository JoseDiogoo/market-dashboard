"""Notícias abertas (RSS CNBC, MarketWatch, Bloomberg, Yahoo) + motor de sentimento financeiro por léxico (sem dependências)."""
import re, time, html
import xml.etree.ElementTree as ET
import requests

FEEDS = [("CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
         ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
         ("Bloomberg", "https://feeds.bloomberg.com/markets/news.rss"),
         ("Yahoo Finance", "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US")]

POS = {"beat": 2, "beats": 2, "surge": 2, "surges": 2, "soar": 2, "soars": 2, "jump": 1.5, "jumps": 1.5, "rally": 1.5, "rallies": 1.5, "record": 1.5, "upgrade": 2, "upgrades": 2,
       "upgraded": 2, "raises": 1.5, "raised": 1.5, "boost": 1.5, "boosts": 1.5, "strong": 1.5, "growth": 1, "profit": 1, "profits": 1, "gain": 1, "gains": 1, "rise": 1, "rises": 1, "climb": 1,
       "climbs": 1, "outperform": 2, "buyback": 1.5, "dividend": 1, "approval": 1.5, "approves": 1.5, "wins": 1.5, "win": 1, "breakthrough": 2, "expands": 1, "optimism": 1.5, "bullish": 2,
       "rebound": 1.5, "recovery": 1, "tops": 1.5, "exceeds": 1.5, "beat expectations": 2, "all-time high": 2, "buy": 1}
NEG = {"miss": 2, "misses": 2, "plunge": 2.5, "plunges": 2.5, "tumble": 2, "tumbles": 2, "slump": 2, "slumps": 2, "fall": 1, "falls": 1, "drop": 1.5, "drops": 1.5, "sink": 2, "sinks": 2,
       "downgrade": 2, "downgrades": 2, "downgraded": 2, "cut": 1.5, "cuts": 1.5, "slashes": 2, "warns": 2, "warning": 1.5, "weak": 1.5, "loss": 1.5, "losses": 1.5, "fear": 1.5, "fears": 1.5,
       "selloff": 2, "sell-off": 2, "crash": 3, "lawsuit": 2, "sues": 1.5, "probe": 2, "investigation": 2, "fraud": 3, "recall": 2, "bankruptcy": 3, "layoffs": 1.5, "concern": 1, "concerns": 1,
       "risk": 0.5, "risks": 0.5, "bearish": 2, "decline": 1.5, "declines": 1.5, "slows": 1, "slowdown": 1.5, "halt": 1.5, "fine": 1, "fined": 1.5, "default": 2.5, "short": 0.5, "sell": 0.5}
# termos que sugerem problema estrutural (não ruído passageiro)
STRUCT = {"fraud", "investigation", "probe", "bankruptcy", "default", "recall", "lawsuit", "sues", "restatement", "delisting", "downgrade", "downgrades", "downgraded",
          "cuts guidance", "lowers guidance", "slashes", "layoffs", "antitrust", "ban", "sanctions", "accounting", "subpoena", "going concern"}


def score(title):
    """−1…+1 (léxico financeiro simples e transparente). Devolve (nota, nº de termos estruturais)."""
    w = re.findall(r"[a-z\-']+", title.lower())
    s = sum(POS.get(x, 0) for x in w) - sum(NEG.get(x, 0) for x in w)
    low = " ".join(w)
    st = sum(1 for k in STRUCT if k in low)
    return max(-1.0, min(1.0, s / 4)), st


def label(v):
    return "pos" if v >= 0.2 else "neg" if v <= -0.2 else "neu"


def summarize(items):
    """items: [{'title':..}] → agregado de sentimento + sinais estruturais."""
    if not items:
        return {"n": 0, "label": None}
    sc = [score(a["title"]) for a in items]
    m = sum(s for s, _ in sc) / len(sc)
    return {"n": len(sc), "mean": round(m, 2), "label": label(m), "pos": sum(1 for s, _ in sc if s >= .2), "neg": sum(1 for s, _ in sc if s <= -.2), "struct": sum(1 for _, k in sc if k)}


def tag(items):
    for a in items:
        a["s"] = label(score(a["title"])[0])
    return items


def drop_verdict(drawdown, summ, q):
    """Queda recente: reação exagerada vs problema estrutural (heurística: sentimento + termos estruturais + qualidade das contas)."""
    if drawdown is None or drawdown > -12 or not summ or not summ.get("n"):
        return None
    weak = (q or {}).get("qscore") is not None and q["qscore"] < 50
    if summ.get("struct", 0) >= 2 or (summ["label"] == "neg" and weak):
        return {"k": "estrutural", "t": "Possível problema estrutural: notícias negativas com termos graves" + (" e contas fracas." if weak else ".")}
    if summ["label"] in ("neg", "neu") and not weak and (q or {}).get("qscore") is not None and q["qscore"] >= 65:
        return {"k": "exagero", "t": "Possível reação exagerada: queda sem notícias estruturais e com contas sólidas. Confirma nas notícias abaixo."}
    return {"k": "incerto", "t": "Queda sem causa clara nas notícias: investiga antes de decidir."}


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
