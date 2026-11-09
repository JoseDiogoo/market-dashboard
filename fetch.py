"""Terminal fundamental: yfinance -> data.js. Uso: python fetch.py  (ou fetch.build() no Streamlit)"""
import json, time
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf

SCREENS = ["undervalued_large_caps", "undervalued_growth_stocks"]  # screeners dinâmicos do Yahoo; universo muda sozinho
PIN = ["MCD"]  # só o estudo de caso fica fixo
ARISTOCRATS = {"MCD", "KO", "JNJ", "PG", "PEP"}  # ponytail: lista manual, yfinance não expõe isto
CYC_WORDS = ("semiconductor", "homebuilder", "residential construction", "oil", "gas", "steel", "gold", "copper", "airlines", "cruise", "auto")


def universe(n=40):
    out = list(PIN)
    for s in SCREENS:
        try:
            out += [q["symbol"] for q in yf.screen(s, count=n)["quotes"]]
        except Exception as e:
            print("screen falhou", s, e)
    return list(dict.fromkeys(out))

# Texto escrito à mão (o yfinance não explica "o quê"/catalisadores/riscos). Conhecimento geral, rever periodicamente.
THESIS = {
 "MCD": ("Maior cadeia de restaurantes do mundo; ~95% das lojas são franchisadas, por isso recebe rendas e royalties muito estáveis.", "Promoções de valor, digitalização/fidelização, abertura de lojas, recompra de ações.", "Consumidor de baixos rendimentos mais fraco, custos de alimentos, dívida elevada (capital próprio negativo)."),
 "GOOGL": ("Dona do Google, YouTube, Android e Google Cloud. Vive de publicidade e cada vez mais de cloud/IA.", "Crescimento do Cloud, IA no motor de pesquisa, YouTube, recompra de ações.", "Regulação antitrust, concorrência de IA generativa, capex gigante em IA."),
 "MU": ("Produz memória (DRAM, HBM, NAND) para servidores de IA, telemóveis e PCs.", "Procura de memória HBM para IA, subida de preços de memória.", "Setor muito cíclico: lucros em pico podem fazer o P/E parecer baixo demais; abrandamento do capex de IA."),
 "AMAT": ("Fabrica equipamento usado para produzir chips (deposição, gravação).", "Novas fábricas de chips, IA, lógica avançada e memória.", "Restrições de exportação para a China, ciclo de capex dos fabricantes."),
 "SNY": ("Farmacêutica francesa: Dupixent (dermatologia/asma), vacinas, doenças raras.", "Dupixent a crescer, pipeline de novos fármacos.", "Perda de patentes, ensaios clínicos que falham, pressão de preços."),
 "EQNR": ("Petrolífera/gás norueguesa (controlada pelo Estado), grande fornecedora de gás à Europa.", "Preço de petróleo e gás, dividendos e recompras generosos.", "Preços de energia voláteis, transição energética, risco fiscal."),
 "PHM": ("Construtora de casas nos EUA (PulteGroup).", "Descida de juros, défice habitacional nos EUA.", "Juros altos travam a procura, custos de construção, setor cíclico."),
 "LEN": ("Uma das maiores construtoras de casas nos EUA (Lennar).", "Descida de juros, escassez de habitação.", "Margens em queda com incentivos, juros altos, setor cíclico."),
 "BTI": ("Tabaqueira britânica (Dunhill, Lucky Strike, Vuse), com dividendo alto.", "Produtos sem fumo (Vuse, Velo), dividendo e recompras.", "Declínio estrutural do cigarro, regulação, litigação."),
 "PDD": ("Dona da Temu e da Pinduoduo, e-commerce chinês de baixo preço.", "Expansão internacional da Temu, lucro forte.", "Tarifas e regras alfandegárias, concorrência chinesa, governação e risco regulatório."),
 "QCOM": ("Chips para telemóveis (Snapdragon) e licenças de patentes 5G; a expandir-se para carros e PCs com IA.", "Chips de IA no dispositivo, automóvel, diversificação além da Apple.", "Perda do cliente Apple (modems próprios), China, ciclo de smartphones."),
 "BRK-B": ("Holding de Warren Buffett: seguros (GEICO), caminhos-de-ferro, energia, indústria e uma carteira de ações.", "Enorme caixa para aquisições, seguros rentáveis, compra de ações.", "Sucessão de Buffett, dimensão torna o crescimento mais lento."),
 "DHI": ("Maior construtora de casas dos EUA (D.R. Horton), foco em casas de entrada.", "Descida de juros, falta de casas nos EUA.", "Juros altos, incentivos que apertam margens, setor cíclico."),
 "CTSH": ("Consultoria e outsourcing de TI (Cognizant), muita atividade para bancos e saúde.", "Projetos de IA e transformação digital.", "IA a reduzir horas faturáveis, orçamentos de clientes, vistos de trabalho."),
 "SU": ("Petrolífera canadiana de areias betuminosas (Suncor), com refinarias e postos Petro-Canada.", "Preço do petróleo, eficiência operacional, dividendo.", "Petróleo volátil, acidentes operacionais, risco climático/regulatório."),
 "KO": ("Coca-Cola: vende xarope/concentrado a engarrafadores em 200 países. Marca global.", "Preços, novos produtos sem açúcar, mercados emergentes.", "Menos consumo de açúcar, moeda forte, crescimento lento."),
 "JNJ": ("Farmacêutica e dispositivos médicos (Johnson & Johnson).", "Novos medicamentos oncologia/imunologia, dispositivos médicos.", "Processos judiciais (talco), perda de patentes, pressão de preços."),
 "PG": ("Procter & Gamble: Gillette, Pampers, Tide, Oral-B; produtos de consumo diário.", "Poder de preço, inovação de produto, produtividade.", "Marcas brancas, moeda forte, volumes fracos."),
 "V": ("Rede de pagamentos Visa: ganha uma pequena comissão em cada transação.", "Crescimento de pagamentos digitais e cross-border.", "Regulação de comissões, concorrência de pagamentos instantâneos."),
}


def sc(v, lo, hi):  # 0..1, None se faltar dado
    return None if v is None else max(0.0, min(1.0, (v - lo) / (hi - lo)))


def avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.5  # sem dados = neutro


def r(v, n=2):
    return None if v is None else round(float(v), n)


def pct(v):
    return None if v is None else v * 100


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
        # Pilares (25 pts cada). ponytail: pesos fixos simples; afinar se quiseres.
        val = avg([sc(30 - fpe, 0, 22) if fpe and fpe > 0 else None, sc(20 - eve, 0, 14) if eve and eve > 0 else None, sc(fcfy, 0, 8), sc(up, 0, 30)])
        rent = avg([sc(roe, 5, 25), sc(om, 5, 30)])
        solv = avg([None if nd is None else sc(4 - nd, 0, 4)])
        grow = avg([sc(eg, -10, 20), sc(rg, -5, 15)])
        score = round(25 * (val + rent + solv + grow))
        dd = (p / hi - 1) * 100
        bounce = (p / lo - 1) * 100
        trap = [m for ok, m in [(eg is not None and eg < 0, "lucros a cair"), (om is not None and om < 8, "margem operacional baixa"),
                                (nd is not None and nd > 4, "dívida alta"), (fcfy is not None and fcfy <= 0, "fluxo de caixa negativo")] if ok]
        cheap = dd <= -15 or (up is not None and up >= 15)
        dy = i.get("dividendYield")
        badges = []
        if score >= 65 and up is not None and up >= 15:
            badges.append(["Forte Compra", "good"])
        if dd <= -15:
            badges.append([f"Desconto de {abs(dd):.0f}% vs máx.", "info"])
        if bounce >= 15 and dd <= -10:
            badges.append([f"Já recuperou {bounce:.0f}% da mínima", "info"])
        if sym in ARISTOCRATS:
            badges.append(["Dividend Aristocrat", "good"])
        elif (dy or 0) >= 3:
            badges.append([f"Dividendo {dy:.1f}%", "info"])
        if nd is not None and nd < 1:
            badges.append(["Balanço sólido", "good"])
        if any(w in (i.get("industry") or "").lower() for w in CYC_WORDS):
            badges.append(["Cíclica: P/E baixo pode enganar", "warn"])
        if cheap and trap:
            badges.append(["⚠ Possível value trap", "warn"])
        news = []
        for n in (t.news or [])[:8]:
            c = n.get("content", n)
            url = (c.get("canonicalUrl") or {}).get("url") or c.get("link")
            if c.get("title") and url:
                news.append({"title": c["title"], "link": url, "src": (c.get("provider") or {}).get("displayName", ""), "date": (c.get("pubDate") or "")[:10]})
        return sym, {
            "name": i.get("longName") or sym, "sector": i.get("sector"), "price": r(p), "low": r(lo), "high": r(hi), "target": r(tgt),
            "fair": r(tgt or p), "upside": r(up, 1), "drawdown": r(dd, 1), "bounce": r(bounce, 1), "rec": i.get("recommendationKey"), "analysts": i.get("numberOfAnalystOpinions"),
            "pe": r(i.get("trailingPE"), 1), "fpe": r(fpe, 1), "peg": r(i.get("trailingPegRatio") or i.get("pegRatio")), "dy": r(dy, 2),
            "eve": r(eve, 1), "roe": r(roe, 1), "om": r(om, 1), "nd": r(nd, 1), "fcfy": r(fcfy, 1), "eg": r(eg, 1), "rg": r(rg, 1),
            "score": score, "pillars": [round(25 * x) for x in (val, rent, solv, grow)], "badges": badges, "trap": trap, "cheap": cheap,
            "thesis": THESIS.get(sym) or ((i.get("longBusinessSummary") or "Sem descrição.")[:420] + " (resumo do Yahoo, em inglês)", "Consulta o relatório e as notícias da empresa.", "Consulta o relatório (secção Risk Factors do 10-K)."), "hist": [[d.strftime("%Y-%m-%d"), round(float(v), 2)] for d, v in h.items()], "news": news}
    except Exception as e:
        print("falhou", sym, e)
        return sym, None


def build():
    with ThreadPoolExecutor(6) as ex:
        T = {s: d for s, d in ex.map(one, universe()) if d}
    try:
        fx = float(yf.Ticker("EURUSD=X").history(period="5d")["Close"].iloc[-1])
    except Exception:
        fx = None
    top = sorted(T, key=lambda s: (-T[s]["score"], -(T[s]["upside"] or -99)))[:10]
    return {"updated": time.strftime("%Y-%m-%d %H:%M"), "eurusd": r(fx, 4), "top10": top, "tickers": T}


if __name__ == "__main__":
    d = build()
    open("data.js", "w", encoding="utf-8").write("window.DATA=" + json.dumps(d).replace("</", "<\\/"))
    print(len(d["tickers"]), "ações · TOP:", ", ".join(f"{s} {d['tickers'][s]['score']}" for s in d["top10"]))
