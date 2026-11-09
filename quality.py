"""Camada institucional: demonstrações financeiras (10-K/anuais), qualidade (Piotroski/Altman/Beneish), ROIC vs custo de capital,
DCF inverso, múltiplos vs história própria, revisões e dispersão de analistas. Tudo vem do Yahoo Finance; cada bloco indica a fonte/ano."""
import math
import numpy as np
import pandas as pd

RF, ERP = 0.04, 0.05


def _v(df, names, k=0):
    """valor da linha `names` (1.º nome existente) no ano k (0 = mais recente); None se falta"""
    if df is None or df.empty or k >= df.shape[1]:
        return None
    for n in ([names] if isinstance(names, str) else names):
        if n in df.index:
            x = df.iloc[:, k][n] if not isinstance(df.loc[n], pd.DataFrame) else None
            if x is not None and not pd.isna(x):
                return float(x)
    return None


def _div(a, b):
    return None if a is None or b in (None, 0) else a / b


def _pc(a, b):
    x = _div(a, b)
    return None if x is None else 100 * x


def _r(x, n=2):
    return None if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else round(float(x), n)


def piotroski(fin, bs, cf):
    """9 testes (0/1) comparando o último ano com o anterior. Devolve (pontos, nº testes avaliáveis)."""
    ta0, ta1, ta2 = _v(bs, "Total Assets", 0), _v(bs, "Total Assets", 1), _v(bs, "Total Assets", 2)
    ni0, ni1 = _v(fin, ["Net Income", "Net Income Common Stockholders"], 0), _v(fin, ["Net Income", "Net Income Common Stockholders"], 1)
    cfo0 = _v(cf, "Operating Cash Flow", 0)
    roa0, roa1 = _div(ni0, ta1 or ta0), _div(ni1, ta2 or ta1)
    ltd0, ltd1 = _v(bs, ["Long Term Debt", "Total Debt"], 0), _v(bs, ["Long Term Debt", "Total Debt"], 1)
    cr0, cr1 = _div(_v(bs, "Current Assets", 0), _v(bs, "Current Liabilities", 0)), _div(_v(bs, "Current Assets", 1), _v(bs, "Current Liabilities", 1))
    sh0, sh1 = _v(bs, ["Ordinary Shares Number", "Share Issued"], 0), _v(bs, ["Ordinary Shares Number", "Share Issued"], 1)
    rev0, rev1 = _v(fin, "Total Revenue", 0), _v(fin, "Total Revenue", 1)
    gm0, gm1 = _div(_v(fin, "Gross Profit", 0), rev0), _div(_v(fin, "Gross Profit", 1), rev1)
    at0, at1 = _div(rev0, ta1 or ta0), _div(rev1, ta2 or ta1)
    tests = {
        "Lucro positivo": None if ni0 is None else ni0 > 0,
        "Fluxo de caixa operacional positivo": None if cfo0 is None else cfo0 > 0,
        "Rentabilidade dos ativos a subir": None if roa0 is None or roa1 is None else roa0 > roa1,
        "Caixa operacional > lucro (lucros de qualidade)": None if cfo0 is None or ni0 is None else cfo0 > ni0,
        "Dívida de longo prazo não aumentou (relativa aos ativos)": None if ltd0 is None or ltd1 is None or not ta0 or not ta1 else ltd0 / ta0 <= ltd1 / ta1,
        "Liquidez corrente a subir": None if cr0 is None or cr1 is None else cr0 > cr1,
        "Sem emissão de novas ações": None if sh0 is None or sh1 is None else sh0 <= sh1 * 1.005,
        "Margem bruta a subir": None if gm0 is None or gm1 is None else gm0 > gm1,
        "Eficiência (vendas/ativos) a subir": None if at0 is None or at1 is None else at0 > at1,
    }
    ok = {k: v for k, v in tests.items() if v is not None}
    return sum(ok.values()), len(ok), {k: (None if v is None else bool(v)) for k, v in tests.items()}


def altman(fin, bs, mcap):
    ta, tl = _v(bs, "Total Assets"), _v(bs, "Total Liabilities Net Minority Interest")
    wc, re_, ebit, rev = _v(bs, "Working Capital"), _v(bs, "Retained Earnings"), _v(fin, ["EBIT", "Operating Income"]), _v(fin, "Total Revenue")
    if None in (ta, tl, wc, re_, ebit, rev, mcap) or not ta or not tl:
        return None
    return 1.2 * wc / ta + 1.4 * re_ / ta + 3.3 * ebit / ta + 0.6 * mcap / tl + 1.0 * rev / ta


def beneish(fin, bs, cf):
    """M-score de 8 variáveis; sinal de alerta acima de −1,78. None se faltarem dados."""
    g = lambda d, n, k: _v(d, n, k)
    rec = lambda k: g(bs, ["Receivables", "Accounts Receivable", "Gross Accounts Receivable"], k)
    try:
        rev0, rev1 = g(fin, "Total Revenue", 0), g(fin, "Total Revenue", 1)
        cogs0, cogs1 = g(fin, ["Cost Of Revenue", "Reconciled Cost Of Revenue"], 0), g(fin, ["Cost Of Revenue", "Reconciled Cost Of Revenue"], 1)
        sga0, sga1 = g(fin, "Selling General And Administration", 0), g(fin, "Selling General And Administration", 1)
        ta0, ta1 = g(bs, "Total Assets", 0), g(bs, "Total Assets", 1)
        ca0, ca1 = g(bs, "Current Assets", 0), g(bs, "Current Assets", 1)
        ppe0, ppe1 = g(bs, "Net PPE", 0), g(bs, "Net PPE", 1)
        dep0, dep1 = g(cf, ["Depreciation And Amortization", "Depreciation Amortization Depletion"], 0), g(cf, ["Depreciation And Amortization", "Depreciation Amortization Depletion"], 1)
        tl0, tl1 = g(bs, "Total Liabilities Net Minority Interest", 0), g(bs, "Total Liabilities Net Minority Interest", 1)
        ni0, cfo0 = g(fin, "Net Income", 0), g(cf, "Operating Cash Flow", 0)
        r0, r1 = rec(0), rec(1)
        vals = [rev0, rev1, cogs0, cogs1, ta0, ta1, ca0, ca1, ppe0, ppe1, dep0, dep1, tl0, tl1, ni0, cfo0, r0, r1]
        if any(v is None for v in vals) or min(rev0, rev1, ta0, ta1) <= 0:
            return None
        sga0, sga1 = sga0 or 0.0, sga1 or 0.0
        dsri = (r0 / rev0) / (r1 / rev1) if r1 else 1.0
        gmi = ((rev1 - cogs1) / rev1) / ((rev0 - cogs0) / rev0) if rev0 != cogs0 else 1.0
        aq = lambda ca, ppe, ta: 1 - (ca + ppe) / ta
        aqi = aq(ca0, ppe0, ta0) / aq(ca1, ppe1, ta1) if aq(ca1, ppe1, ta1) else 1.0
        sgi = rev0 / rev1
        depi = (dep1 / (dep1 + ppe1)) / (dep0 / (dep0 + ppe0)) if dep0 and dep1 and (dep0 + ppe0) and (dep1 + ppe1) else 1.0
        sgai = (sga0 / rev0) / (sga1 / rev1) if sga1 else 1.0
        lvgi = (tl0 / ta0) / (tl1 / ta1)
        tata = (ni0 - cfo0) / ta0
        m = -4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi
        return m if abs(m) < 50 else None
    except Exception:
        return None


def implied_growth(fcf, shares, netdebt, price, rate=0.09, tg=0.03, yrs=10):
    """DCF inverso: crescimento anual do FCF (10 anos, a decair para 3%) que justifica o preço atual. Bisseção."""
    def val(g):
        cash, pv = fcf, 0.0
        for y in range(1, yrs + 1):
            cash *= 1 + g + (tg - g) * (y - 1) / (yrs - 1)
            pv += cash / (1 + rate) ** y
        pv += cash * (1 + tg) / (rate - tg) / (1 + rate) ** yrs
        return (pv - netdebt) / shares
    lo, hi = -0.15, 0.60
    if val(lo) > price or val(hi) < price:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if val(mid) < price else (lo, mid)
    return (lo + hi) / 2


def analyze(t, i, p, mcap, beta, hist5, fin_sector):
    """Devolve o bloco `q` (qualidade + história + analistas) de uma ação. Nunca levanta exceção."""
    out = {"src": "Yahoo Finance (demonstrações anuais, equivalentes aos 10-K/relatórios anuais)"}
    try:
        fin, bs, cf = t.financials, t.balance_sheet, t.cashflow
    except Exception:
        fin = bs = cf = None
    cur, fcur = i.get("currency"), i.get("financialCurrency")
    same = fcur is None or fcur == cur
    n = 0 if fin is None or fin.empty else fin.shape[1]
    out["fy"] = [str(c.year) for c in fin.columns[:5]] if n else []
    out["fy_end"] = str(fin.columns[0].date()) if n else None
    out["fin"] = bool(fin_sector)

    # ---- séries anuais (mais antigo → mais recente)
    ser = []
    for k in range(min(n, 5) - 1, -1, -1):
        rev = _v(fin, "Total Revenue", k)
        ebit = _v(fin, ["EBIT", "Operating Income"], k)
        gp = _v(fin, "Gross Profit", k)
        ni = _v(fin, ["Net Income", "Net Income Common Stockholders"], k)
        eps = _v(fin, ["Diluted EPS", "Basic EPS"], k)
        fcf = _v(cf, "Free Cash Flow", k)
        tax = _div(_v(fin, "Tax Provision", k), _v(fin, "Pretax Income", k))
        tax = 0.21 if tax is None or not (0 <= tax <= 0.4) else tax
        ic = _v(bs, "Invested Capital", k)
        roic = _div(ebit * (1 - tax), ic) if ebit is not None and ic and ic > 0 else None
        d = fin.columns[k]
        pe_h = None
        if same and eps and eps > 0 and hist5 is not None and len(hist5):
            try:
                px = float(hist5[hist5.index <= pd.Timestamp(d).tz_localize(None)].iloc[-1])
                pe_h = px / eps if 0 < px / eps < 500 else None
            except Exception:
                pe_h = None
        ser.append({"y": d.year, "rev": _r(None if rev is None else rev / 1e6, 0), "gm": _r(_pc(gp, rev), 1), "om": _r(_pc(ebit, rev), 1), "nm": _r(_pc(ni, rev), 1),
                    "fcfm": _r(_pc(fcf, rev), 1), "eps": _r(eps, 2), "roic": _r(None if roic is None else 100 * roic, 1), "pe": _r(pe_h, 1)})
    out["series"] = ser

    def cagr(key):
        v = [(s["y"], s[key]) for s in ser if s[key] is not None and s[key] > 0]
        if len(v) >= 3 and v[-1][0] > v[0][0]:
            return 100 * ((v[-1][1] / v[0][1]) ** (1 / (v[-1][0] - v[0][0])) - 1)
        return None
    out["rev_cagr"], out["eps_cagr"] = _r(cagr("rev"), 1), _r(cagr("eps"), 1)

    # ---- história própria: P/E atual vs P/E nos fins de exercício anteriores
    pe_now = i.get("trailingPE")
    pes = [s["pe"] for s in ser[:-1] if s["pe"]] if len(ser) > 1 else []
    pes_all = [s["pe"] for s in ser if s["pe"]]
    if pe_now and 0 < pe_now < 500 and len(pes_all) >= 3 and same:
        m, sd = float(np.mean(pes_all)), float(np.std(pes_all))
        out["hist_pe"] = {"now": _r(pe_now, 1), "mean": _r(m, 1), "min": _r(min(pes_all), 1), "max": _r(max(pes_all), 1), "n": len(pes_all),
                          "vs_mean": _r(100 * (pe_now / m - 1), 0), "z": _r((pe_now - m) / sd, 1) if sd > 0 else None,
                          "pctl": _r(100 * sum(1 for x in pes_all if x <= pe_now) / len(pes_all), 0)}
    # margens: atual vs média própria
    oms = [s["om"] for s in ser if s["om"] is not None]
    if len(oms) >= 3:
        out["hist_om"] = {"now": oms[-1], "mean": _r(float(np.mean(oms)), 1), "min": min(oms), "max": max(oms)}

    # ---- qualidade
    if n >= 2 and not fin_sector:
        f, nt, det = piotroski(fin, bs, cf)
        out["piotroski"] = {"score": f, "of": nt, "tests": det}
    z = altman(fin, bs, mcap) if n and same and not fin_sector else None
    if z is not None:
        out["altman"] = {"z": _r(z, 2), "zone": "segura" if z > 2.99 else "cinzenta" if z > 1.81 else "perigo"}
    m = beneish(fin, bs, cf) if n >= 2 and same and not fin_sector else None
    if m is not None:
        out["beneish"] = {"m": _r(m, 2), "flag": m > -1.78}

    # ---- ROIC vs custo de capital (WACC)
    roic_now = next((s["roic"] for s in reversed(ser) if s["roic"] is not None), None) if not fin_sector else None
    b = beta if beta is not None else (i.get("beta") or 1.0)
    b = max(0.3, min(2.0, b))
    ke = RF + b * ERP
    debt = i.get("totalDebt") or 0
    ie = _v(fin, "Interest Expense", 0)
    kd = max(0.03, min(0.08, _div(abs(ie), debt))) if ie and debt else 0.045
    tx = 0.21
    wd = debt / (debt + mcap) if mcap and debt and same else 0.0
    wacc = (1 - wd) * ke + wd * kd * (1 - tx)
    out["wacc"] = _r(100 * wacc, 1)
    if roic_now is not None and same:
        out["roic"] = {"now": roic_now, "wacc": _r(100 * wacc, 1), "spread": _r(roic_now - 100 * wacc, 1)}

    # ---- DCF inverso
    fcf0 = i.get("freeCashflow")
    shares = mcap / p if mcap and p else None
    if not fin_sector and same and fcf0 and fcf0 > 0 and shares:
        g = implied_growth(fcf0, shares, (i.get("totalDebt") or 0) - (i.get("totalCash") or 0), p)
        if g is not None:
            out["reverse"] = {"g": _r(100 * g, 1), "rev_cagr": out["rev_cagr"], "eps_cagr": out["eps_cagr"]}

    # ---- analistas: dispersão, revisões, surpresas
    tm, tl, th, na = i.get("targetMeanPrice"), i.get("targetLowPrice"), i.get("targetHighPrice"), i.get("numberOfAnalystOpinions")
    an = {"n": na}
    if tm and tl and th and tm > 0 and 0.3 <= tm / p <= 3.5:
        an["disp"] = _r(100 * (th - tl) / tm, 0)
    try:
        et = t.eps_trend
        row = et.loc["0y"] if "0y" in et.index else None
        if row is not None and row["current"] and row["90daysAgo"]:
            an["rev90"] = _r(100 * (row["current"] / row["90daysAgo"] - 1) if row["90daysAgo"] > 0 else None, 1)
            an["rev30"] = _r(100 * (row["current"] / row["30daysAgo"] - 1) if row["30daysAgo"] and row["30daysAgo"] > 0 else None, 1)
    except Exception:
        pass
    try:
        er = t.eps_revisions.loc["0y"]
        an["up30"], an["down30"] = int(er["upLast30days"]), int(er["downLast30days"])
    except Exception:
        pass
    try:
        eh = t.earnings_history.dropna(subset=["surprisePercent"]).tail(4)
        if len(eh) >= 2:
            an["beats"], an["of"] = int((eh["epsActual"] > eh["epsEstimate"]).sum()), len(eh)
            an["surprise"] = _r(100 * float(eh["surprisePercent"].mean()), 1)
    except Exception:
        pass
    out["analysts"] = an
    out.update(_verdict(out, i, p, tm))
    return out


def _verdict(q, i, p, tm):
    """Pontuação de qualidade 0-100 + veredicto + razões em português (cada razão cita o número usado)."""
    pts, wts, why, risk, peak = 0.0, 0.0, [], [], False

    def add(v, w):
        nonlocal pts, wts
        if v is not None:
            pts += w * v
            wts += w
    pf = q.get("piotroski")
    if pf and pf["of"] >= 6:
        f = pf["score"] * 9 / pf["of"]
        add(f / 9, 3)
        (why if f >= 7 else risk if f <= 3 else []).append(f"Piotroski {pf['score']}/{pf['of']}: " + ("passa quase todos os testes de saúde financeira." if f >= 7 else "falha a maioria dos testes de saúde financeira."))
    al = q.get("altman")
    if al:
        add({"segura": 1, "cinzenta": 0.5, "perigo": 0}[al["zone"]], 2)
        if al["zone"] == "perigo":
            risk.append(f"Altman Z {al['z']}: zona de perigo (risco de dificuldades financeiras).")
        elif al["zone"] == "segura":
            why.append(f"Altman Z {al['z']}: balanço sólido, risco de falência baixo.")
    be = q.get("beneish")
    if be:
        add(0 if be["flag"] else 1, 1.5)
        if be["flag"]:
            risk.append(f"Beneish M {be['m']} (acima de −1,78): sinal de alerta contabilístico" + (" (pode ser falso alarme: crescimento muito rápido das vendas)." if (q.get("rev_cagr") or 0) > 30 else "."))
    ro = q.get("roic")
    if ro:
        add(max(0, min(1, (ro["spread"] + 5) / 20)), 3)
        (why if ro["spread"] >= 5 else risk if ro["spread"] < 0 else []).append(
            f"ROIC {ro['now']}% vs custo de capital {ro['wacc']}%: " + ("cria valor com folga." if ro["spread"] >= 5 else "rende menos do que o capital custa."))
    ho, hp = q.get("hist_om"), q.get("hist_pe")
    if ho and ho["now"] is not None and ho["mean"]:
        add(1 if ho["now"] >= ho["mean"] else 0.4, 1)
        if ho["now"] > max(ho["mean"] * 1.5, ho["mean"] + 10):
            peak = True
            risk.append(f"Margem operacional {ho['now']}% muito acima da sua média de {ho['mean']}%: possível pico de ciclo, o P/E baixo pode enganar.")
        elif ho["now"] < ho["mean"] - 3:
            risk.append(f"Margem operacional {ho['now']}% abaixo da sua média de {ho['mean']}%.")
    an = q.get("analysts") or {}
    if an.get("rev90") is not None:
        add(1 if an["rev90"] > 1 else 0.5 if an["rev90"] > -1 else 0, 1.5)
        if an["rev90"] <= -3:
            risk.append(f"Analistas cortaram a estimativa de lucro {abs(an['rev90'])}% nos últimos 90 dias.")
        elif an["rev90"] >= 3:
            why.append(f"Analistas subiram a estimativa de lucro {an['rev90']}% em 90 dias.")
    if an.get("disp") is not None and an["disp"] > 80:
        risk.append(f"Alvos dos analistas muito dispersos ({an['disp']}% do alvo médio): pouca concordância.")
    if an.get("beats") is not None and an["beats"] >= 3:
        why.append(f"Superou as estimativas de lucro em {an['beats']} dos últimos {an['of']} trimestres.")
    rv = q.get("reverse")
    if rv and rv.get("g") is not None:
        ref = rv.get("rev_cagr")
        if ref is not None and rv["g"] > ref + 6:
            risk.append(f"O preço atual exige ~{rv['g']}% de crescimento anual do FCF; a empresa cresceu {ref}%/ano nas vendas.")
        elif ref is not None and rv["g"] < ref - 2:
            why.append(f"O preço só exige ~{rv['g']}% de crescimento anual; a empresa cresceu {ref}%/ano.")
    score = round(100 * pts / wts) if wts >= 4 else None
    cheap = bool(hp and hp["vs_mean"] is not None and hp["vs_mean"] <= -10)
    dear = bool(hp and hp["vs_mean"] is not None and hp["vs_mean"] >= 25)
    if hp:
        (why if cheap else risk if dear else []).append(f"P/E {hp['now']} vs média própria {hp['mean']} ({hp['n']} anos): " + ("abaixo do habitual." if cheap else "acima do habitual." if dear else ""))
    trap = bool(cheap and ((score is not None and score < 45) or peak or len(risk) >= 2))
    if score is None:
        label = "Sem dados suficientes"
    elif trap:
        label = "Possível armadilha de valor"
    elif score >= 70 and not dear:
        label = "Qualidade sólida"
    elif score >= 70:
        label = "Boa empresa, preço exigente"
    elif score >= 50:
        label = "Qualidade média"
    else:
        label = "Qualidade fraca"
    return {"qscore": score, "qlabel": label, "trap": trap, "why": why[:5], "warn": risk[:5]}
