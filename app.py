"""Streamlit: embebe index.html com os dados. Base = data.js (gerado por fetch.py / GitHub Actions);
preços do universo inteiro são renovados a cada 10 min (≈10 s); a análise completa tem preços ao vivo por WebSocket no browser."""
import copy, json, pathlib
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Radar de Investimento", layout="wide")
HERE = pathlib.Path(__file__).parent


@st.cache_data(ttl=3600, show_spinner="A carregar a base de dados…")
def base():
    p = HERE / "data.js"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")[len("window.DATA="):])
    import fetch  # sem data.js: gera tudo (vários minutos)
    return fetch.build()


@st.cache_data(ttl=600, show_spinner="A renovar preços do mercado…")
def fresh():
    d = copy.deepcopy(base())
    try:
        import fetch
        return fetch.refresh_rows(d)
    except Exception:
        return d  # se o Yahoo falhar, mostra a base com a data real de atualização


@st.fragment(run_every=600)
def view():
    html = (HERE / "index.html").read_text(encoding="utf-8")
    raw = "window.DATA=" + json.dumps(fresh(), separators=(",", ":")).replace("</", "<\\/")
    components.html(html.replace('<script src="data.js"></script>', "<script>" + raw + "</script>"), height=950, scrolling=True)


view()
