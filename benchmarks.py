"""Referências estatísticas por setor/indústria (ponto A): substitui limiares fixos por percentis reais dos pares analisados
e pela média da indústria do Damodaran (NYU Stern, EUA; snapshot em research/damodaran.json).
Só usa dados que já existem em T (análise profunda): zero números inventados. Convenções (evidência B): medianas em vez de médias, grupo mínimo de pares,
excluir valores absurdos (múltiplos <=0 ou >100×)."""
import bisect, json, math, pathlib

MIN_IND = 8   # pares mínimos para usar a indústria; senão usa o setor (a literatura prática pede 5-15 pares; abaixo de 5 a estatística não vale)
DAM_MIN_N = 15  # grupos do Damodaran com menos empresas são ruído (ex.: 8 empresas com prejuízo dão margem negativa)
MIN_SEC = 8
# (chave, rótulo, direção: +1 = quanto mais alto melhor, -1 = quanto mais baixo melhor/mais barato, extrator, limites válidos)
def _g(t, *p):
    for k in p:
        t = t.get(k) if isinstance(t, dict) else None
    return t
METRICS = [
    ("om", "Margem operacional", +1, lambda t: t.get("om"), (-100, 100)),
    ("roic", "ROIC", +1, lambda t: _g(t, "q", "roic", "now"), (-100, 500)),
    ("eve", "EV/EBITDA", -1, lambda t: t.get("eve"), (0.01, 100)),
    ("nd", "Dívida líquida/EBITDA", -1, lambda t: t.get("nd"), (-50, 50)),
    ("fpe", "P/E projetado", -1, lambda t: t.get("fpe"), (0.01, 100)),
    ("fcfy", "FCF yield", +1, lambda t: t.get("fcfy"), (-50, 50)),
    ("rg", "Crescimento das vendas", +1, lambda t: t.get("rg"), (-100, 500)),
    ("eg", "Crescimento do lucro", +1, lambda t: t.get("eg"), (-500, 1000)),
]
FIN_SKIP = {"om", "roic", "eve", "nd", "fcfy"}  # bancos, seguradoras, REITs: EBITDA/ROIC/dívida líquida não são comparáveis

# Yahoo industry -> (nome Damodaran, financeira?)
YMAP = {
    "Advertising Agencies": ("Advertising", 0), "Aerospace & Defense": ("Aerospace/Defense", 0), "Airlines": ("Air Transport", 0),
    "Asset Management": ("Investments & Asset Management", 1), "Auto & Truck Dealerships": ("Retail (Automotive)", 0),
    "Auto Manufacturers": ("Auto & Truck", 0), "Auto Parts": ("Auto Parts", 0), "Banks - Diversified": ("Bank (Money Center)", 1),
    "Banks - Regional": ("Banks (Regional)", 1), "Beverages - Brewers": ("Beverage (Alcoholic)", 0),
    "Beverages - Non-Alcoholic": ("Beverage (Soft)", 0), "Beverages - Wineries & Distilleries": ("Beverage (Alcoholic)", 0),
    "Biotechnology": ("Drugs (Biotechnology)", 0), "Building Materials": ("Building Materials", 0),
    "Capital Markets": ("Brokerage & Investment Banking", 1), "Communication Equipment": ("Telecom. Equipment", 0),
    "Computer Hardware": ("Computers/Peripherals", 0), "Consulting Services": ("Business & Consumer Services", 0),
    "Consumer Electronics": ("Electronics (Consumer & Office)", 0), "Credit Services": ("Financial Svcs. (Non-bank & Insurance)", 1),
    "Diagnostics & Research": ("Healthcare Support Services", 0), "Discount Stores": ("Retail (General)", 0),
    "Drug Manufacturers - General": ("Drugs (Pharmaceutical)", 0), "Drug Manufacturers - Specialty & Generic": ("Drugs (Pharmaceutical)", 0),
    "Electrical Equipment & Parts": ("Electrical Equipment", 0), "Electronic Components": ("Electronics (General)", 0),
    "Electronic Gaming & Multimedia": ("Software (Entertainment)", 0), "Electronics & Computer Distribution": ("Retail (Distributors)", 0),
    "Engineering & Construction": ("Engineering/Construction", 0), "Entertainment": ("Entertainment", 0),
    "Farm & Heavy Construction Machinery": ("Machinery", 0), "Farm Products": ("Farming/Agriculture", 0),
    "Financial Conglomerates": ("Financial Svcs. (Non-bank & Insurance)", 1), "Food Distribution": ("Food Wholesalers", 0),
    "Footwear & Accessories": ("Shoe", 0), "Furnishings, Fixtures & Appliances": ("Furn/Home Furnishings", 0), "Gold": ("Precious Metals", 0),
    "Grocery Stores": ("Retail (Grocery and Food)", 0), "Health Information Services": ("Heathcare Information and Technology", 0),
    "Healthcare Plans": ("Healthcare Support Services", 0), "Home Improvement Retail": ("Retail (Building Supply)", 0),
    "Household & Personal Products": ("Household Products", 0), "Industrial Distribution": ("Retail (Distributors)", 0),
    "Information Technology Services": ("Computer Services", 0), "Insurance - Diversified": ("Insurance (General)", 1),
    "Insurance - Life": ("Insurance (Life)", 1), "Insurance - Property & Casualty": ("Insurance (Prop/Cas.)", 1),
    "Insurance - Reinsurance": ("Reinsurance", 1), "Insurance - Specialty": ("Insurance (General)", 1),
    "Integrated Freight & Logistics": ("Transportation", 0), "Internet Content & Information": ("Software (Internet)", 0),
    "Internet Retail": ("Retail (General)", 0), "Leisure": ("Recreation", 0), "Lodging": ("Hotel/Gaming", 0), "Luxury Goods": ("Apparel", 0),
    "Marine Shipping": ("Shipbuilding & Marine", 0), "Medical Care Facilities": ("Hospitals/Healthcare Facilities", 0),
    "Medical Devices": ("Healthcare Products", 0), "Medical Distribution": ("Healthcare Support Services", 0),
    "Medical Instruments & Supplies": ("Healthcare Products", 0), "Oil & Gas E&P": ("Oil/Gas (Production and Exploration)", 0),
    "Oil & Gas Integrated": ("Oil/Gas (Integrated)", 0), "Oil & Gas Midstream": ("Oil/Gas Distribution", 0),
    "Other Industrial Metals & Mining": ("Metals & Mining", 0), "Packaged Foods": ("Food Processing", 0),
    "Packaging & Containers": ("Packaging & Container", 0), "Paper & Paper Products": ("Paper/Forest Products", 0),
    "Publishing": ("Publishing & Newspapers", 0), "REIT - Diversified": ("R.E.I.T.", 1), "REIT - Healthcare Facilities": ("R.E.I.T.", 1),
    "REIT - Mortgage": ("R.E.I.T.", 1), "REIT - Retail": ("Retail (REITs)", 1), "Railroads": ("Transportation (Railroads)", 0),
    "Real Estate - Development": ("Real Estate (Development)", 0), "Real Estate Services": ("Real Estate (Operations & Services)", 0),
    "Rental & Leasing Services": ("Business & Consumer Services", 0), "Residential Construction": ("Homebuilding", 0),
    "Restaurants": ("Restaurant/Dining", 0), "Scientific & Technical Instruments": ("Electronics (General)", 0),
    "Semiconductor Equipment & Materials": ("Semiconductor Equip", 0), "Semiconductors": ("Semiconductor", 0),
    "Software - Application": ("Software (System & Application)", 0), "Software - Infrastructure": ("Software (System & Application)", 0),
    "Specialty Business Services": ("Business & Consumer Services", 0), "Specialty Chemicals": ("Chemical (Specialty)", 0),
    "Specialty Industrial Machinery": ("Machinery", 0), "Specialty Retail": ("Retail (Special Lines)", 0), "Steel": ("Steel", 0),
    "Telecom Services": ("Telecom. Services", 0), "Tobacco": ("Tobacco", 0), "Travel Services": ("Hotel/Gaming", 0), "Trucking": ("Trucking", 0),
    "Utilities - Diversified": ("Utility (General)", 0), "Utilities - Independent Power Producers": ("Power", 0),
    "Utilities - Regulated Electric": ("Utility (General)", 0), "Utilities - Regulated Water": ("Utility (Water)", 0),
    "Waste Management": ("Environmental & Waste Services", 0),
}
DAM = json.loads((pathlib.Path(__file__).parent / "research" / "damodaran.json").read_text(encoding="utf-8"))


def _clean(x, lo_hi):
    return float(x) if isinstance(x, (int, float)) and math.isfinite(x) and lo_hi[0] <= x <= lo_hi[1] else None


def _q(v, p):  # percentil por interpolação linear (v ordenado)
    k = (len(v) - 1) * p
    f = math.floor(k)
    return v[f] + (v[min(f + 1, len(v) - 1)] - v[f]) * (k - f)


def _fin(t):
    return bool(YMAP.get(t.get("industry"), (None, 0))[1])


def peer_stats(T):
    """Valores ordenados por métrica para cada setor e indústria (só análise profunda, só pares com a métrica comparável)."""
    st = {"sec": {}, "ind": {}}
    for t in T.values():
        fin = _fin(t)
        for k, _, _, ex, lim in METRICS:
            if fin and k in FIN_SKIP:
                continue
            v = _clean(ex(t), lim)
            if v is None:
                continue
            for lvl, g in (("sec", t.get("sector")), ("ind", t.get("industry"))):
                if g:
                    st[lvl].setdefault(g, {}).setdefault(k, []).append(v)
    for lvl in st.values():
        for g in lvl.values():
            for k in g:
                g[k].sort()
    return st


def bench(t, st):
    """Por métrica: valor, grupo de pares usado, n, quartis, percentil do valor e referência Damodaran. {} se não houver nada comparável."""
    out, fin = {}, _fin(t)
    dn, _ = YMAP.get(t.get("industry"), (None, 0))
    dam = DAM["ind"].get(dn) if dn else None
    for k, label, d, ex, lim in METRICS:
        if fin and k in FIN_SKIP:
            continue
        v = _clean(ex(t), lim)
        if v is None:
            continue
        ind = st["ind"].get(t.get("industry"), {}).get(k, [])
        sec = st["sec"].get(t.get("sector"), {}).get(k, [])
        grp, vals, name = (("ind", ind, t.get("industry")) if len(ind) >= MIN_IND else ("sec", sec, t.get("sector")) if len(sec) >= MIN_SEC else (None, [], None))
        if not grp:
            continue
        lo, eq = bisect.bisect_left(vals, v), bisect.bisect_right(vals, v)
        pct = round(100 * (lo + eq) / 2 / len(vals))  # percentil por posto médio (0-100); quanto mais alto, maior o valor
        e = {"v": round(v, 2), "grp": grp, "name": name, "n": len(vals), "q": [round(_q(vals, p), 2) for p in (.25, .5, .75)], "pct": pct}
        if dam and dam["n"] >= DAM_MIN_N and dam.get(k) is not None and k in ("om", "roic", "eve"):
            e["dam"] = {"name": dn, "v": round(dam[k] * (1 if k == "eve" else 100), 2), "n": dam["n"]}
        out[k] = e
    return out


def finalize(T):
    st = peer_stats(T)
    for t in T.values():
        t["bench"] = bench(t, st)
    return {"dam_date": DAM["date"]}
