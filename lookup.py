"""Procura on-demand (backend Streamlit) de ações fora das 2658 do data.js: nome ou ticker -> símbolo, preço, setor, moeda e câmbio para USD.
Só Yahoo Finance via yfinance (sem chaves). Devolve {consulta_em_maiúsculas: {k, name, px, cur, fx, sec}}; consultas sem resultado ficam de fora."""
import re

import yfinance as yf

import fetch


def one(q):
    q = q.strip()
    sym = q.upper() if re.fullmatch(r"[A-Za-z0-9.\-]{1,12}", q) else None
    if not sym:  # nome da empresa: primeira ação/ETF dos resultados de pesquisa
        hits = [x for x in (yf.Search(q, max_results=6).quotes or []) if x.get("quoteType") in ("EQUITY", "ETF")]
        if not hits:
            return None
        sym = hits[0]["symbol"]
    i = yf.Ticker(sym).info
    px, cur = i.get("currentPrice") or i.get("regularMarketPrice"), i.get("currency")
    if not px or not cur:
        return None
    f = fetch.fx_of(cur)
    if not f:
        return None
    return {"k": sym, "name": i.get("longName") or i.get("shortName") or sym, "px": float(px), "cur": cur,
            "fx": f * fetch.SUB.get(cur, (cur, 1))[1], "sec": i.get("sector") or ("ETF/Fundo" if i.get("quoteType") == "ETF" else "Outro")}


def many(queries):
    out = {}
    for q in queries[:8]:  # limite: cada consulta são 2-3 pedidos ao Yahoo
        try:
            r = one(q)
        except Exception:
            r = None
        if r:
            out[q.strip().upper()] = r
    return out
