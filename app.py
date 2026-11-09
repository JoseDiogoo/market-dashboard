"""Streamlit: embebe index.html com os dados. Base = data.js (gerado por fetch.py / GitHub Actions);
preços do universo inteiro são renovados a cada 10 min (≈10 s); a análise completa tem preços ao vivo por WebSocket no browser.
As caches são chaveadas pelo conteúdo dos ficheiros (mtime/tamanho): um novo deploy invalida-as de imediato, sem ficar preso a dados velhos."""
import copy, json, pathlib
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="Radar de Investimento", layout="wide")
HERE = pathlib.Path(__file__).parent


def sig(*names):
    return tuple((p.stat().st_mtime_ns, p.stat().st_size) for p in (HERE / n for n in names) if p.exists())


@st.cache_data(ttl=3600, show_spinner="A carregar a base de dados…")
def base(_sig):
    p = HERE / "data.js"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")[len("window.DATA="):])
    import fetch  # sem data.js: gera tudo (vários minutos)
    return fetch.build()


@st.cache_data(ttl=600, show_spinner="A renovar preços do mercado…")
def fresh(_sig):
    d = copy.deepcopy(base(_sig))
    try:
        import fetch
        return fetch.refresh_rows(d)
    except Exception:
        d["source"] = {"name": "Snapshot guardado", "ok": False, "mode": "stale"}
        return d  # se o Yahoo falhar, mostra a base com a data real de atualização


@st.fragment(run_every=600)
def view():
    s = sig("data.js", "index.html", "fetch.py", "quality.py")
    html = (HERE / "index.html").read_text(encoding="utf-8")
    raw = "window.DATA=" + json.dumps(fresh(s), separators=(",", ":")).replace("</", "<\\/")
    components.html(html.replace('<script src="data.js"></script>', "<script>" + raw + "</script>"), height=950, scrolling=True)


view()
