"""Streamlit: embebe index.html com os dados. Base = data.js (gerado por fetch.py / GitHub Actions);
preços do universo inteiro são renovados a cada 10 min (≈10 s); a análise completa tem preços ao vivo por WebSocket no browser.
As caches são chaveadas pelo conteúdo dos ficheiros (mtime/tamanho): um novo deploy invalida-as de imediato, sem ficar preso a dados velhos.

Ecrã: a página do Streamlit fica sem cabeçalho, margens nem scroll próprio e o iframe ocupa a janela toda (100dvh: PC, tablet e telemóvel);
o index.html trata do resto com as suas media queries. Sem recarga automática (a app voltava ao início de 10 em 10 min e a página escurecia
durante a renovação); os preços ao vivo vêm por WebSocket e uma sessão nova já apanha a cache de 10 min."""
import copy, json, pathlib
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Radar de Investimento", layout="wide", initial_sidebar_state="collapsed")
HERE = pathlib.Path(__file__).parent

# ponytail: um só iframe na página, por isso o seletor `iframe` basta; se vier um segundo componente, restringir pelo data-testid
st.markdown("""<style>
html,body,.stApp{background:#070b16!important}
header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],footer,#MainMenu{display:none!important}
[data-testid="stMainBlockContainer"],.block-container{padding:0!important;max-width:100%!important}
[data-testid="stVerticalBlock"]{gap:0!important}
[data-testid="stAppViewContainer"],[data-testid="stMain"],section.main{overflow:hidden!important}
[data-testid="stTextInput"]{position:fixed!important;left:-9999px!important;top:0!important;height:1px!important;overflow:hidden!important}
iframe{display:block;width:100%!important;height:100vh!important;height:100dvh!important;border:0!important}
</style>""", unsafe_allow_html=True)


def sig(*names):
    return tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in (HERE / n for n in names) if p.exists())


@st.cache_data(ttl=3600, show_spinner="A carregar a base de dados…")
def base(key):  # `key` (sem _) entra na chave da cache: um ficheiro novo invalida-a (com `_sig` o Streamlit ignorava-o)
    p = HERE / "data.js"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")[len("window.DATA="):])
    import fetch  # sem data.js: gera tudo (vários minutos)
    return fetch.build()


@st.cache_data(ttl=600, show_spinner="A renovar preços do mercado…")
def fresh(key):
    d = copy.deepcopy(base(key))
    try:
        import fetch
        fetch.rerank(d)
        return fetch.refresh_rows(d)
    except Exception:
        d["source"] = {"name": "Snapshot guardado", "ok": False, "mode": "stale"}
        return d  # se o Yahoo falhar, mostra a base com a data real de atualização


@st.cache_data(ttl=600, show_spinner=False)
def extra(qs):  # separador Posições: ações fora das 2658 (nome ou ticker) resolvidas no Yahoo; o index.html pede-as por um campo escondido
    import lookup
    return lookup.many(list(qs))


st.text_input("lk", key="lk", label_visibility="collapsed")  # ponte iframe -> Python: o index.html escreve aqui os nomes/tickers a procurar
s = sig("data.js", "index.html", "fetch.py", "quality.py", "benchmarks.py")
html = (HERE / "index.html").read_text(encoding="utf-8")
raw = "window.DATA=" + json.dumps(fresh(s), separators=(",", ":")).replace("</", "<\\/")
lk = tuple(x.strip() for x in st.session_state.get("lk", "").split(",") if x.strip())[:8]
ex = "window.EXTRA=" + json.dumps(extra(lk) if lk else {}).replace("</", "<\\/") + ";"
components.html(html.replace('<script src="data.js"></script>', "<script>" + ex + raw + "</script>"), height=900, scrolling=True)
