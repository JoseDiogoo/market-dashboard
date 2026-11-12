"""Gera research/damodaran.json (snapshot das médias por indústria do Aswath Damodaran, NYU Stern, empresas dos EUA).
Uso (uma vez por ano, requer `pip install xlrd`): python research/build_damodaran.py
Fontes: pages.stern.nyu.edu/~adamodar/pc/datasets/{margin,roc,vebitda}.xls  (folha "Industry Averages").
Campos: om = margem operacional pré-impostos (não ajustada); roic = retorno do capital após impostos (não ajustado, comparável ao ROIC calculado em quality.py);
eve = EV/EBITDA só com EBITDA positivo. São médias agregadas (empresas grandes pesam mais): servem de referência externa, não de mediana de pares."""
import io, json, pathlib, urllib.request
import pandas as pd

BASE = "https://pages.stern.nyu.edu/~adamodar/pc/datasets/"
OUT = pathlib.Path(__file__).with_name("damodaran.json")


def sheet(name):
    raw = urllib.request.urlopen(urllib.request.Request(BASE + name + ".xls", headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
    return pd.read_excel(io.BytesIO(raw), "Industry Averages", header=None)


def col(df, hdr_row, first, label_prefix, nth=0):
    """Índice da nth-ésima coluna cujo cabeçalho começa por label_prefix (falha alto se não existir: o Damodaran muda o layout)."""
    hits = [i for i, v in enumerate(df.iloc[hdr_row].tolist()) if str(v).startswith(label_prefix)]
    assert len(hits) > nth, f"coluna '{label_prefix}' não encontrada"
    return hits[nth]


def rows(df, hdr_row):
    return {str(r[0]): r for r in df.iloc[hdr_row + 1:].itertuples(index=False, name=None) if str(r[0]) != "nan"}


m, rc, ve = sheet("margin"), sheet("roc"), sheet("vebitda")
date = str(m.iloc[0, 1])[:10]
hm, hr, hv = 8, 7, 8
cm, cr, cv = col(m, hm, 0, "Pre-tax Unadjusted Ope"), col(rc, hr, 0, "Unadjusted after-tax R"), col(ve, hv, 0, "EV/EBITDA")
M, R, V = rows(m, hm), rows(rc, hr), rows(ve, hv)
f = lambda v: None if pd.isna(v) else round(float(v), 4)
out = {"date": date, "src": {"om": BASE + "margin.xls", "roic": BASE + "roc.xls", "eve": BASE + "vebitda.xls"},
       "note": "médias por indústria, empresas dos EUA (Damodaran, NYU Stern)",
       "ind": {k: {"n": int(M[k][1]), "om": f(M[k][cm]), "roic": f(R.get(k, [None] * 9)[cr]), "eve": f(V.get(k, [None] * 10)[cv])} for k in M}}
OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
print(date, len(out["ind"]), "indústrias ->", OUT)
