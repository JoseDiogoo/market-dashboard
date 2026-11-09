"""Analisador de investimento: yfinance -> data.js. Uso: python fetch.py (ou fetch.build() no Streamlit)"""
import json, math, statistics, time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import yfinance as yf

# Universo curado (qualidade). cat: g = crescimento & tecnologia, d = dividendos & defensivas, v = valor/resiliência
UNIVERSE = {
    "GOOGL": "g", "MSFT": "g", "AAPL": "g", "NVDA": "g", "AVGO": "g", "ASML": "g", "AMAT": "g", "MU": "g", "QCOM": "g", "V": "g", "MA": "g", "LLY": "g",
    "MCD": "d", "KO": "d", "PEP": "d", "PG": "d", "WMT": "d", "COST": "d", "JNJ": "d", "PFE": "d", "MRK": "d", "ABBV": "d", "SNY": "d",
    "BRK-B": "v", "JPM": "v", "EQNR": "v", "HD": "v", "NKE": "v",
}
NOMES = {"GOOGL": "Alphabet (Google)", "MSFT": "Microsoft", "AAPL": "Apple", "NVDA": "Nvidia", "AVGO": "Broadcom", "ASML": "ASML", "AMAT": "Applied Materials", "MU": "Micron", "QCOM": "Qualcomm", "V": "Visa", "MA": "Mastercard", "LLY": "Eli Lilly",
         "MCD": "McDonald's", "KO": "Coca-Cola", "PEP": "PepsiCo", "PG": "Procter & Gamble", "WMT": "Walmart", "COST": "Costco", "JNJ": "Johnson & Johnson", "PFE": "Pfizer", "MRK": "Merck", "ABBV": "AbbVie", "SNY": "Sanofi",
         "BRK-B": "Berkshire Hathaway", "JPM": "JPMorgan Chase", "EQNR": "Equinor", "HD": "Home Depot", "NKE": "Nike"}
TAPE = {"^GSPC": "S&P 500", "^IXIC": "Nasdaq", "EURUSD=X": "EUR/USD"}

# Teses em português. Estrutura: faz, barata (contexto geral da compressão de preço/múltiplo), cat (catalisadores 6-18 meses), riscos.
# ponytail: texto escrito à mão (o yfinance não tem isto); contexto geral e estrutural, confirma sempre nas notícias.
TESE = {
 "GOOGL": ("Dona do Google, do YouTube, do Android e da Google Cloud. Ganha dinheiro sobretudo com anúncios e cada vez mais com serviços de nuvem e IA.",
           ["Receio de que a IA generativa (chatbots) roube utilizadores à pesquisa tradicional.", "Pressão regulatória e processos antitrust nos EUA e na Europa."],
           ["Crescimento acelerado do Google Cloud e da procura por IA.", "IA integrada na pesquisa a aumentar o valor de cada anúncio.", "Recompra de ações e dividendo crescente."],
           ["Decisões judiciais que obriguem a separar negócios ou mudar acordos.", "Investimento enorme em IA que pode demorar a dar retorno."]),
 "MSFT": ("Vende o Windows e o Office, a nuvem Azure e ferramentas de IA (Copilot) a empresas de todo o mundo, com contratos recorrentes.",
          ["Mercado preocupado com o custo gigante dos centros de dados para IA.", "Múltiplo exigente: o preço já assume muito crescimento."],
          ["Azure a crescer com a procura de IA.", "Copilot a ser vendido a milhões de utilizadores empresariais."],
          ["Capex de IA sem retorno proporcional.", "Dependência de parcerias (OpenAI) e concorrência na nuvem."]),
 "AAPL": ("Fabrica o iPhone, o Mac e o iPad e ganha cada vez mais com serviços (App Store, iCloud, Apple Music) que têm margens altas.",
          ["Crescimento de vendas de iPhone mais lento.", "Tarifas e regulação sobre a App Store."],
          ["Ciclo de renovação de iPhones com IA.", "Serviços a crescer com margens elevadas e recompras massivas."],
          ["Tarifas e dependência da cadeia de produção na Ásia.", "Atraso na IA face aos concorrentes."]),
 "NVDA": ("Desenha os chips (GPUs) que treinam e executam quase toda a IA moderna. É o fornecedor dominante dos grandes centros de dados.",
          ["Receio de que o investimento em IA abrande e deixe de crescer ao ritmo atual.", "Restrições de exportação para a China."],
          ["Novas gerações de chips e encomendas dos grandes clientes de nuvem.", "Expansão para IA empresarial e soberana."],
          ["Clientes a desenvolver chips próprios.", "Ação muito sensível a qualquer sinal de abrandamento do capex em IA."]),
 "AVGO": ("Fabrica chips de rede e personalizados para IA (para os gigantes da nuvem) e software empresarial (VMware).",
          ["Valorização muito elevada após a corrida da IA.", "Dependência de poucos clientes grandes."],
          ["Chips de IA personalizados a crescer.", "Integração do VMware a aumentar margens."],
          ["Concentração em poucos clientes.", "Dívida das aquisições."]),
 "ASML": ("Única empresa do mundo que faz as máquinas de litografia EUV, sem as quais não se fabricam chips avançados.",
          ["Receios com a China e com o ciclo de investimento das fábricas.", "Encomendas irregulares de trimestre para trimestre."],
          ["Novas fábricas de chips para IA.", "Máquinas de nova geração (High-NA) a entrar em produção."],
          ["Restrições de exportação.", "Ciclo dos semicondutores."]),
 "AMAT": ("Fabrica o equipamento que as fábricas usam para produzir chips: deposição, gravação e inspeção.",
          ["Restrições de exportação para a China pesam nas vendas.", "Setor cíclico, depende do investimento dos fabricantes."],
          ["Construção de novas fábricas para IA e memória.", "Chips mais complexos precisam de mais equipamento."],
          ["Nova ronda de restrições à China.", "Corte de investimento dos clientes."]),
 "MU": ("Produz memória (DRAM, HBM, NAND) usada em servidores de IA, telemóveis e computadores.",
        ["Setor muito cíclico: o preço sobe muito quando a memória escasseia e cai quando há excesso.", "O P/E parece baixo porque os lucros estão em máximos de ciclo."],
        ["Procura de memória HBM para IA.", "Preços de memória a subir."],
        ["Inversão do ciclo com excesso de oferta.", "Concorrência asiática (Samsung, SK Hynix)."]),
 "QCOM": ("Fabrica os chips Snapdragon dos telemóveis Android e recebe licenças de patentes 5G. Expande-se para carros e PCs.",
          ["Perda gradual do cliente Apple, que desenvolve modems próprios.", "Dependência do ciclo de smartphones."],
          ["Chips para PCs com IA e automóvel.", "Diversificação para além dos telemóveis."],
          ["Apple deixar de comprar modems.", "Disputas de licenciamento."]),
 "V": ("Gere a rede de pagamentos com cartão e ganha uma pequena comissão em cada transação feita em todo o mundo.",
       ["Regulação sobre comissões e litígios com comerciantes.", "Concorrência de pagamentos instantâneos."],
       ["Crescimento contínuo de pagamentos digitais e viagens.", "Novos serviços de valor acrescentado."],
       ["Limites regulatórios às comissões.", "Concorrência de novas redes de pagamento."]),
 "MA": ("Rede de pagamentos concorrente da Visa: ganha comissões por cada pagamento com cartão.",
        ["Regulação e processos sobre comissões.", "Múltiplo exigente."],
        ["Mais pagamentos digitais e internacionais.", "Serviços de dados e segurança."],
        ["Pressão regulatória.", "Novos sistemas de pagamento diretos."]),
 "LLY": ("Farmacêutica dona dos medicamentos de perda de peso e diabetes (Mounjaro, Zepbound), das vendas que mais crescem no setor.",
         ["Preços muito altos após a corrida dos medicamentos de obesidade.", "Pressão sobre os preços dos fármacos nos EUA."],
         ["Procura crescente por tratamentos de obesidade.", "Novos medicamentos e novas indicações em testes."],
         ["Concorrência de outras farmacêuticas.", "Pressão regulatória sobre preços."]),
 "MCD": ("Maior cadeia de restaurantes do mundo. Cerca de 95% das lojas são de franqueados, que pagam rendas e royalties muito estáveis.",
         ["Consumidores de rendimento mais baixo a cortar nas refeições fora de casa.", "Receio de abrandamento do consumo e de custos de alimentação."],
         ["Promoções de valor e fidelização digital a trazer clientes.", "Abertura de novas lojas e recompra de ações."],
         ["Dívida elevada e capital próprio negativo.", "Consumo fraco prolongado."]),
 "KO": ("Vende concentrado de bebidas a engarrafadores em mais de 200 países. Uma das marcas mais conhecidas do mundo.",
        ["Crescimento lento e consumidores a reduzir o açúcar.", "Dólar forte reduz lucros no estrangeiro."],
        ["Aumentos de preço e novos produtos sem açúcar.", "Mercados emergentes."],
        ["Mudança de hábitos de consumo.", "Moeda forte."]),
 "PEP": ("Dona da Pepsi, das batatas Lay's, dos Doritos e da Quaker. Bebidas e snacks vendidos em todo o mundo.",
         ["Volumes fracos e consumidores sensíveis ao preço.", "Pressão sobre as margens."],
         ["Recuperação de volumes e eficiência de custos.", "Dividendo crescente há décadas."],
         ["Consumo fraco prolongado.", "Aumento de custos."]),
 "PG": ("Fabrica produtos de consumo diário: fraldas Pampers, detergente Tide, lâminas Gillette, pasta Oral-B.",
        ["Crescimento de volumes fraco e concorrência das marcas brancas.", "Dólar forte."],
        ["Inovação de produto e aumentos de preço seletivos.", "Dividendo crescente há mais de 60 anos."],
        ["Perda de quota para marcas mais baratas.", "Custos de matérias-primas."]),
 "WMT": ("Maior retalhista do mundo, com lojas físicas, comércio eletrónico e publicidade. Beneficia quando os consumidores procuram preços baixos.",
         ["Avaliação mais alta do que o histórico.", "Tarifas podem pressionar margens."],
         ["Comércio eletrónico e publicidade a crescer.", "Ganho de clientes de rendimento mais alto."],
         ["Tarifas e custos.", "Concorrência da Amazon."]),
 "COST": ("Vende em armazéns por subscrição (cartão de sócio). Margens baixas nos produtos, lucro nas quotas anuais muito fiéis.",
          ["Múltiplo muito alto face ao crescimento.", "Crescimento de vendas a abrandar."],
          ["Aumento das quotas e abertura de armazéns.", "Fidelidade muito alta dos clientes."],
          ["Preço da ação já exige muito.", "Consumo fraco."]),
 "JNJ": ("Farmacêutica e de dispositivos médicos (Johnson & Johnson). Negócio diversificado e defensivo.",
         ["Processos judiciais (talco) e pressão sobre preços de fármacos.", "Perda de patentes de produtos importantes."],
         ["Novos medicamentos em oncologia e imunologia.", "Dispositivos médicos a crescer."],
         ["Litígios que custem mais do previsto.", "Falhas em ensaios clínicos."]),
 "PFE": ("Farmacêutica com vacinas, oncologia e medicamentos para o coração. Em reestruturação depois da quebra das vendas de COVID.",
         ["Vendas de COVID desapareceram e várias patentes expiram.", "Poucos fármacos novos de grande dimensão."],
         ["Aquisições e novos medicamentos em oncologia.", "Dividendo alto à espera de recuperação."],
         ["Perda de patentes.", "Pipeline que não entrega."]),
 "MRK": ("Farmacêutica dona do Keytruda (tratamento do cancro) e de vacinas.",
         ["Receio com o fim da patente do Keytruda.", "Vendas das vacinas mais fracas, sobretudo na China."],
         ["Versão subcutânea do Keytruda e novos medicamentos.", "Aquisições para renovar o portfólio."],
         ["Queda das vendas quando a patente expirar.", "Pressão sobre preços."]),
 "ABBV": ("Farmacêutica dona do Humira, do Skyrizi e do Rinvoq (imunologia), com um dividendo elevado.",
          ["Queda do Humira por concorrência de genéricos.", "Dívida elevada."],
          ["Skyrizi e Rinvoq a compensar a queda do Humira.", "Dividendo crescente."],
          ["Substituição mais lenta que o previsto.", "Pressão regulatória sobre preços."]),
 "SNY": ("Farmacêutica francesa: o Dupixent (dermatologia e asma), vacinas e doenças raras são os maiores motores de receita.",
         ["Dependência do Dupixent e fim de patentes futuras.", "Ensaios clínicos que desiludiram em alguns programas."],
         ["Dupixent a crescer em novas indicações.", "Novos fármacos do pipeline."],
         ["Ensaios que falham.", "Pressão sobre preços na Europa e nos EUA."]),
 "BRK-B": ("Holding de Warren Buffett: seguros (GEICO), caminhos-de-ferro, energia, indústria e uma carteira enorme de ações, com muita caixa.",
           ["Dimensão enorme limita o crescimento.", "Dúvidas sobre a sucessão de Buffett."],
           ["Muita caixa para aproveitar quedas do mercado.", "Seguros e negócios operacionais a gerar lucros estáveis."],
           ["Transição de gestão.", "Retornos menores devido à dimensão."]),
 "JPM": ("Maior banco dos EUA. Ganha com crédito, gestão de ativos, banca de investimento e cartões.",
         ["Juros em queda reduzem margens de crédito.", "Receio de crédito mal parado numa economia mais fraca."],
         ["Banca de investimento e trading em recuperação.", "Capital sólido e recompras."],
         ["Recessão e aumento do crédito malparado.", "Regulação mais dura."]),
 "EQNR": ("Petrolífera e produtora de gás da Noruega (controlada pelo Estado). Grande fornecedora de gás à Europa, com dividendos generosos.",
          ["Preços de petróleo e gás voláteis.", "Transição energética pesa no sentimento."],
          ["Dividendos e recompras ligados ao preço do gás.", "Novos projetos de produção."],
          ["Queda do preço da energia.", "Risco fiscal e regulatório."]),
 "HD": ("Maior retalhista de bricolage e obras de casa dos EUA. Vende a particulares e a profissionais da construção.",
        ["Juros altos travam a compra e as obras em casas.", "Mercado imobiliário lento."],
        ["Descida dos juros a relançar obras e vendas de casas.", "Compras de profissionais a crescer."],
        ["Juros altos por mais tempo.", "Consumo fraco em grandes obras."]),
 "NKE": ("Dona da Nike e da Jordan, a maior marca de desporto do mundo. Está em recuperação sob uma nova estratégia.",
         ["Vendas em queda e perda de quota para marcas mais recentes.", "Tarifas pesam nas margens."],
         ["Novos produtos e recuperação de canais de venda.", "Ajuste de stocks e margens a melhorar."],
         ["Recuperação que não chega.", "Concorrência de marcas emergentes."]),
}

def sc(v, lo, hi):
    return None if v is None else max(0.0, min(1.0, (v - lo) / (hi - lo)))
def avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.5
def r(v, n=2):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), n)
def pct(v):
    return None if v is None else v * 100

def dcf(fcf, g, shares, netdebt, rate=0.09, tg=0.03, yrs=10):
    cash, pv = fcf, 0.0
    for y in range(1, yrs + 1):
        cash *= 1 + g + (tg - g) * (y - 1) / (yrs - 1)
        pv += cash / (1 + rate) ** y
    pv += cash * (1 + tg) / (rate - tg) / (1 + rate) ** yrs
    return (pv - netdebt) / shares

BUYWORDS = ("buy", "overweight", "outperform", "positive", "accumulate", "add")

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
            firms.append({"f": x["Firm"], "g": x["ToGrade"], "pt": r(x["currentPriceTarget"], 0) if x["currentPriceTarget"] else None, "buy": str(x["ToGrade"]).lower() in BUYWORDS or any(w in str(x["ToGrade"]).lower() for w in BUYWORDS)})
    except Exception:
        pass
    return {**c, "total": tot, "buy_pct": bp, "label": label, "mean": r(mean), "firms": firms}

def one(sym):
    try:
        t = yf.Ticker(sym)
        i = t.info
        h = t.history(period="1y")["Close"].dropna()
        p = i.get("currentPrice") or float(h.iloc[-1])
        lo, hi = i.get("fiftyTwoWeekLow") or float(h.min()), i.get("fiftyTwoWeekHigh") or float(h.max())
        ebitda, debt, cash, mcap = i.get("ebitda"), i.get("totalDebt"), i.get("totalCash"), i.get("marketCap")
        nd = (debt - cash) / ebitda if ebitda and debt is not None and cash is not None and ebitda > 0 else None
        fcfy = i["freeCashflow"] / mcap * 100 if i.get("freeCashflow") is not None and mcap else None
        tgt = i.get("targetMeanPrice")
        up = (tgt / p - 1) * 100 if tgt else None
        fpe, eve = i.get("forwardPE"), i.get("enterpriseToEbitda")
        roe, om = pct(i.get("returnOnEquity")), pct(i.get("operatingMargins"))
        eg, rg = pct(i.get("earningsGrowth")), pct(i.get("revenueGrowth"))
        val = avg([sc(30 - fpe, 0, 22) if fpe and fpe > 0 else None, sc(20 - eve, 0, 14) if eve and eve > 0 else None, sc(fcfy, 0, 8), sc(up, 0, 30)])
        rent = avg([sc(roe, 5, 25), sc(om, 5, 30)])
        solv = avg([None if nd is None else sc(4 - nd, 0, 4)])
        grow = avg([sc(eg, -10, 20), sc(rg, -5, 15)])
        score = round(25 * (val + rent + solv + grow))
        # DCF simples (g limitado a 8%); não se aplica a financeiras
        shares = mcap / p if mcap else None
        fin = i.get("sector") == "Financial Services"
        g = 0.03 if eg is None and rg is None else min(0.08, max(0.0, avg([sc(eg, 0, 15) and eg / 100, sc(rg, 0, 15) and rg / 100])))
        dcfv = None
        if not fin and shares and i.get("freeCashflow") and i["freeCashflow"] > 0:
            dcfv = dcf(i["freeCashflow"], g, shares, (debt or 0) - (cash or 0))
            dcfv = dcfv if dcfv > 0 else None
        # Preço justo = média de alvo e DCF (se o DCF for plausível: 0.5x–2x do preço), senão só o alvo
        parts = [x for x in (tgt, dcfv if dcfv and 0.5 * p <= dcfv <= 2 * p else None) if x]
        fair = sum(parts) / len(parts) if parts else None
        buy_below = fair * 0.85 if fair else None  # margem de segurança de 15%
        # Risco pela volatilidade anual (desvio-padrão dos retornos diários)
        vol = float(h.pct_change().std() * math.sqrt(252) * 100)
        risk = "Baixo" if vol < 22 else "Médio" if vol < 35 else "Alto"
        news = []
        for n in (t.news or [])[:6]:
            c = n.get("content", n)
            url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
            if c.get("title") and url:
                news.append({"title": c["title"], "link": url, "src": (c.get("provider") or {}).get("displayName", ""), "date": (c.get("pubDate") or "")[:10]})
        co = consenso(t, i)
        f = TESE[sym]
        return sym, {
            "name": NOMES.get(sym, i.get("longName") or sym), "cat": UNIVERSE[sym], "sector": i.get("sector"), "price": r(p), "low": r(lo), "high": r(hi),
            "d1": r((p / float(h.iloc[-2]) - 1) * 100, 2) if len(h) > 1 else None, "m1": r((p / float(h.iloc[-22]) - 1) * 100, 1) if len(h) > 22 else None,
            "drawdown": r((p / hi - 1) * 100, 1), "target": r(tgt), "tlow": r(i.get("targetLowPrice")), "thigh": r(i.get("targetHighPrice")),
            "upside": r(up, 1), "dcf": r(dcfv), "dcf_ok": bool(dcfv and 0.5 * p <= dcfv <= 2 * p), "dcf_up": r((dcfv / p - 1) * 100, 1) if dcfv else None, "fair": r(fair), "buy_below": r(buy_below),
            "zone": "buy" if buy_below and p <= buy_below else "wait", "cons": co, "risk": risk, "vol": r(vol, 0),
            "dy": r(i.get("dividendYield"), 2), "payout": r(pct(i.get("payoutRatio")), 0), "pe": r(i.get("trailingPE"), 1), "fpe": r(fpe, 1), "eve": r(eve, 1),
            "roe": r(roe, 1), "om": r(om, 1), "nd": r(nd, 1), "fcfy": r(fcfy, 1), "eg": r(eg, 1), "rg": r(rg, 1), "score": score, "mcap": mcap,
            "tese": {"faz": f[0], "barata": f[1], "cat": f[2], "riscos": f[3]},
            "hist": [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in h.items()], "news": news}
    except Exception as e:
        print("falhou", sym, e)
        return sym, None

def build():
    with ThreadPoolExecutor(6) as ex:
        T = {s: d for s, d in ex.map(one, UNIVERSE) if d}
    try:
        fx = float(yf.Ticker("EURUSD=X").history(period="5d")["Close"].iloc[-1])
    except Exception:
        fx = None
    # Ranking de oportunidade: 40% qualidade + 30% upside até ao alvo + 30% % de analistas em compra, menos penalização por risco
    for t in T.values():
        t["rank"] = round(0.4 * t["score"] + 0.3 * 100 * (sc(t["upside"], 0, 40) or 0) + 0.3 * (t["cons"]["buy_pct"] or 50) - {"Baixo": 0, "Médio": 4, "Alto": 12}[t["risk"]])
    order = sorted(T, key=lambda s: -T[s]["rank"])
    safe = [s for s in T if (T[s]["dy"] or 0) >= 2 and T[s]["risk"] != "Alto" and (T[s]["payout"] or 0) < 90 and (T[s]["fcfy"] or 0) > 0 and (T[s]["eg"] is None or T[s]["eg"] >= -5)]
    disc = [s for s in T if s != order[0] and T[s]["score"] >= 55 and (T[s]["cons"]["buy_pct"] or 0) >= 50 and T[s]["upside"]]
    hl = {"pick": order[0], "dividend": max(safe, key=lambda s: T[s]["dy"]) if safe else None, "discount": max(disc, key=lambda s: T[s]["upside"]) if disc else None}
    def quote(sym):
        try:
            c = yf.Ticker(sym).history(period="5d")["Close"].dropna()
            return sym, {"price": r(c.iloc[-1], 2), "prev": r(c.iloc[-2], 2)}
        except Exception:
            return sym, None
    with ThreadPoolExecutor(3) as ex:
        tape = {s: q for s, q in ex.map(quote, TAPE) if q}
    return {"updated": time.strftime("%Y-%m-%d %H:%M"), "eurusd": r(fx, 4), "order": order, "highlights": hl, "tickers": T, "tape": tape, "tape_names": TAPE}

if __name__ == "__main__":
    d = build()
    open("data.js", "w", encoding="utf-8").write("window.DATA=" + json.dumps(d).replace("</", "<\\/"))
    print(len(d["tickers"]), "ações · ordem:", ", ".join(f"{s} {d['tickers'][s]['rank']}" for s in d["order"][:10]), "· destaques:", d["highlights"])
