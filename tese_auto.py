"""Tese em português gerada para qualquer ação a partir dos dados (sem texto em inglês). Cada frase cita os números em que se baseia."""

SECTOR = {"Technology": "tecnologia", "Financial Services": "serviços financeiros", "Healthcare": "saúde", "Consumer Cyclical": "consumo discricionário", "Communication Services": "comunicações e media",
          "Consumer Defensive": "consumo básico", "Energy": "energia", "Real Estate": "imobiliário", "Basic Materials": "materiais básicos", "Industrials": "indústria", "Utilities": "serviços públicos"}
IND = [("semiconductor", "semicondutores (chips)"), ("software", "software"), ("banks", "banca"), ("insurance", "seguros"), ("oil & gas", "petróleo e gás"), ("biotech", "biotecnologia"),
       ("drug manufactur", "medicamentos"), ("pharmac", "medicamentos"), ("medical", "dispositivos e serviços médicos"), ("health", "saúde"), ("aerospace", "aeroespacial e defesa"),
       ("auto", "automóveis"), ("airline", "transporte aéreo"), ("utilities", "eletricidade, gás e água"), ("reit", "imobiliário cotado (REIT)"), ("gold", "ouro"), ("steel", "aço"),
       ("chemical", "químicos"), ("copper", "cobre e metais"), ("beverage", "bebidas"), ("packaged food", "alimentação embalada"), ("restaurant", "restauração"), ("retail", "retalho"),
       ("telecom", "telecomunicações"), ("entertainment", "entretenimento"), ("credit services", "pagamentos e crédito"), ("asset management", "gestão de ativos"), ("capital markets", "mercados de capitais"),
       ("internet", "internet"), ("consumer electronics", "eletrónica de consumo"), ("household", "produtos domésticos"), ("tobacco", "tabaco"), ("apparel", "vestuário"), ("footwear", "calçado"),
       ("engineering", "engenharia e construção"), ("machinery", "maquinaria industrial"), ("electrical", "equipamento elétrico"), ("railroad", "ferrovias"), ("trucking", "transporte rodoviário"),
       ("marine", "transporte marítimo"), ("packaging", "embalagens"), ("building", "materiais de construção"), ("hotel", "hotelaria"), ("gambling", "jogos de fortuna e azar"),
       ("luxury", "artigos de luxo"), ("diagnostic", "diagnóstico médico"), ("information technology", "serviços de TI"), ("computer", "hardware informático"), ("communication equipment", "equipamento de comunicações"),
       ("electronic", "componentes eletrónicos"), ("solar", "energia solar"), ("uranium", "urânio"), ("coal", "carvão"), ("agricultur", "agricultura"), ("education", "educação"), ("waste", "gestão de resíduos"),
       ("staffing", "recursos humanos"), ("advertising", "publicidade"), ("broadcasting", "televisão e rádio"), ("publishing", "edição"), ("grocery", "supermercados"), ("discount stores", "grandes superfícies"),
       ("confectioner", "confeitaria"), ("farm", "equipamento agrícola"), ("tools", "ferramentas"), ("specialty", "negócio especializado")]
COUNTRY = {"United States": "nos EUA", "United Kingdom": "no Reino Unido", "Germany": "na Alemanha", "France": "em França", "Netherlands": "nos Países Baixos", "Switzerland": "na Suíça", "Spain": "em Espanha",
           "Italy": "em Itália", "Sweden": "na Suécia", "Denmark": "na Dinamarca", "Norway": "na Noruega", "Portugal": "em Portugal", "Belgium": "na Bélgica", "Ireland": "na Irlanda", "Finland": "na Finlândia",
           "Luxembourg": "no Luxemburgo", "Canada": "no Canadá", "China": "na China", "Taiwan": "em Taiwan", "Japan": "no Japão", "Israel": "em Israel", "Brazil": "no Brasil", "Bermuda": "nas Bermudas",
           "Cayman Islands": "nas Ilhas Caimão", "South Korea": "na Coreia do Sul", "Hong Kong": "em Hong Kong", "Singapore": "em Singapura", "Australia": "na Austrália", "Mexico": "no México", "Argentina": "na Argentina",
           "Uruguay": "no Uruguai", "Chile": "no Chile", "India": "na Índia", "Jersey": "em Jersey", "Austria": "na Áustria", "Greece": "na Grécia", "Panama": "no Panamá", "South Africa": "na África do Sul"}


def ind_pt(industry, sector):
    low = (industry or "").lower()
    for k, v in IND:
        if k in low:
            return v
    return SECTOR.get(sector, "negócios diversos")


def f1(x):
    return f"{x:.1f}".replace(".", ",")


def pe_txt(x):
    return f1(x) if x is not None else "–"


def gen(i, t):
    """i = info do Yahoo; t = dicionário da análise (já com q, score, risk, etc.). Devolve {faz, barata, saude, cat, riscos}."""
    q = t.get("q") or {}
    name, cur = t["name"].strip(" -"), t.get("cur") or ""
    fcur = i.get("financialCurrency") or cur
    ctry = COUNTRY.get(i.get("country"), f"em {i.get('country')}" if i.get("country") else "")
    ind = ind_pt(i.get("industry"), i.get("sector"))
    mc = (t.get("mcap") or 0) / 1e9
    emp = i.get("fullTimeEmployees")
    ser = q.get("series") or []
    s1 = f"{name} é uma empresa de {ind}" + (f" sediada {ctry}" if ctry else "") + f", com {f1(mc)} mil milhões de {cur} de capitalização" + (f" e cerca de {emp:,} trabalhadores".replace(",", " ") if emp else "") + "."
    s2 = ""
    if ser and ser[-1].get("rev"):
        last = ser[-1]
        rev_b = last["rev"] / 1e3
        s2 = f" No exercício de {last['y']} faturou cerca de {f1(rev_b)} mil milhões de {fcur}" + (f", com margem operacional de {f1(last['om'])}%" if last.get("om") is not None else "")
        if q.get("rev_cagr") is not None:
            s2 += f"; as vendas cresceram {f1(q['rev_cagr'])}% ao ano desde {ser[0]['y']}"
        s2 += "."
    faz = s1 + s2

    barata = []
    dd = t.get("drawdown")
    if dd is not None:
        barata.append(f"Está {abs(dd):.0f}% abaixo do máximo de 12 meses." if dd <= -8 else "Está perto do máximo de 12 meses: o preço já subiu bastante, a margem de erro é menor.")
    hp, nm = q.get("hist_pe"), q.get("norm") or {}
    if hp and hp.get("vs_mean") is not None:
        barata.append(f"P/E de {pe_txt(hp['now'])} vs média própria de {pe_txt(hp['mean'])} ({hp['n']} anos): " + ("abaixo do habitual." if hp["vs_mean"] <= -10 else "acima do habitual." if hp["vs_mean"] >= 25 else "em linha com o habitual."))
    if nm.get("cyc") and nm.get("pe"):
        barata.append(f"Como é um negócio cíclico, o P/E que interessa é o normalizado (lucro médio de {nm.get('years')} anos): {pe_txt(nm['pe'])}" + (", muito acima do P/E atual: os lucros de hoje estão em pico, por isso o desconto pode ser ilusório." if nm.get("peak") else "."))
    if t.get("upside") is not None:
        barata.append(f"Os analistas apontam para {t['target']:.2f} {cur} ({t['upside']:+.0f}% face ao preço)." if t.get("target") else "")
    if t.get("dcf_ok") and t.get("dcf_up") is not None:
        barata.append(f"O DCF simples estima {t['dcf']:.2f} {cur} ({t['dcf_up']:+.0f}%).")
    if t.get("fcfy") is not None and t["fcfy"] > 0:
        barata.append(f"Rendimento de caixa livre de {f1(t['fcfy'])}% sobre o preço.")
    barata = [x for x in barata if x]

    saude = []
    pf, al, ro, be = q.get("piotroski"), q.get("altman"), q.get("roic"), q.get("beneish")
    if pf:
        saude.append(f"Piotroski {pf['score']}/{pf['of']}: " + ("balanço e resultados fortes e a melhorar." if pf["score"] >= 7 else "saúde financeira mediana." if pf["score"] >= 4 else "sinais de fragilidade nas contas."))
    if al:
        saude.append("Altman Z " + f1(al["z"]) + ": " + {"segura": "risco de falência muito baixo.", "cinzenta": "zona cinzenta, a acompanhar.", "perigo": "zona de perigo."}[al["zone"]])
    if t.get("nd") is not None:
        saude.append(f"Dívida líquida de {f1(t['nd'])}× o EBITDA" + (": folgada." if t["nd"] < 1.5 else ": moderada." if t["nd"] < 3 else ": elevada."))
    if ro:
        saude.append(f"ROIC de {f1(ro['now'])}% vs custo de capital de {f1(ro['wacc'])}%: " + ("a empresa cria valor." if ro["spread"] > 0 else "o capital rende menos do que custa."))
    du = q.get("dupont")
    if du and None not in (du["roe"][0], du["roe"][1]):
        drv = max((("margem", abs(du["nm"][1] - du["nm"][0]) / max(abs(du["nm"][0]), 1)), ("rotação dos ativos", abs(du["at"][1] - du["at"][0]) / max(du["at"][0], .01)), ("alavancagem", abs(du["lev"][1] - du["lev"][0]) / max(du["lev"][0], .01))), key=lambda x: x[1])[0]
        saude.append(f"ROE de {f1(du['roe'][0])}% ({du['y0']}) para {f1(du['roe'][1])}% ({du['y1']}); a maior alteração veio da {drv}.")
    if be and be["flag"]:
        saude.append("Atenção: o modelo de Beneish assinala um padrão contabilístico a investigar.")
    if q.get("moat"):
        saude.append(f"Vantagem competitiva (proxy quantitativa): {q['moat']}.")

    cat = []
    an = q.get("analysts") or {}
    if an.get("rev90") is not None and an["rev90"] >= 2:
        cat.append(f"Estimativas de lucro a subir ({an['rev90']:+.1f}% em 90 dias).")
    pe, fpe = i.get("trailingPE"), i.get("forwardPE")
    if pe and fpe and 0 < fpe < pe:
        cat.append(f"O mercado espera lucros {100 * (pe / fpe - 1):.0f}% mais altos nos próximos 12 meses (P/E projetado {f1(fpe)} vs {f1(pe)} atual).")
    if q.get("eps_cagr") and q["eps_cagr"] > 8:
        cat.append(f"Histórico de lucro por ação a crescer {f1(q['eps_cagr'])}% ao ano.")
    ins = q.get("insiders")
    if ins and ins.get("label") == "compras":
        cat.append(f"Administradores e diretores compraram ações nos últimos 6 meses ({ins['buy_tx']} compras vs {ins['sell_tx']} vendas).")
    if an.get("beats") and an["beats"] >= 3:
        cat.append(f"Superou as estimativas em {an['beats']} dos últimos {an['of']} trimestres: próximos resultados podem voltar a surpreender.")
    if i.get("dividendYield") and i["dividendYield"] >= 2 and (t.get("payout") or 0) < 80:
        cat.append(f"Dividendo de {f1(i['dividendYield'])}% com payout sustentável ({t.get('payout')}%).")

    riscos = []
    if nm.get("peak"):
        riscos.append("Lucros em pico de ciclo: se os preços/volumes normalizarem, o lucro pode cair muito.")
    elif nm.get("cyc"):
        riscos.append("Negócio cíclico: os lucros oscilam com o ciclo económico.")
    if hp and hp.get("vs_mean", 0) >= 25:
        riscos.append("Avaliação exigente face à própria história: pouco espaço para desilusões.")
    if t.get("nd") is not None and t["nd"] >= 3:
        riscos.append("Dívida elevada face ao EBITDA.")
    if an.get("disp") is not None and an["disp"] > 80:
        riscos.append("Analistas muito divididos nos alvos de preço.")
    if an.get("rev90") is not None and an["rev90"] <= -3:
        riscos.append(f"Estimativas de lucro a descer ({an['rev90']:+.1f}% em 90 dias).")
    if ins and ins.get("label") == "vendas":
        riscos.append(f"Insiders a vender de forma consistente ({ins['sell_tx']} vendas vs {ins['buy_tx']} compras em 6 meses).")
    if t.get("vol") and t["vol"] >= 45:
        riscos.append(f"Volatilidade alta (~{t['vol']}% ao ano).")
    if (t.get("cons") or {}).get("total", 99) < 8:
        riscos.append("Poucos analistas a acompanhar: consenso menos fiável.")
    return {"faz": faz, "barata": barata, "saude": saude, "cat": cat, "riscos": riscos}
