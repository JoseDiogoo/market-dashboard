"""Streamlit: corre fetch.build() (cache 1h) e embebe index.html. Tempo real = WebSocket Finnhub no browser."""
import json, os, pathlib
import streamlit as st
import streamlit.components.v1 as components
import fetch

st.set_page_config(page_title="Terminal de Análise Fundamental", layout="wide")


@st.cache_data(ttl=3600, show_spinner="A obter dados do mercado (screeners + fundamentais)…")
def data():
    return fetch.build()


def key():
    try:
        return st.secrets["FINNHUB_KEY"]
    except Exception:
        return os.environ.get("FINNHUB_KEY", "")


safe = lambda o: json.dumps(o).replace("</", "<\\/")
html = pathlib.Path(__file__).with_name("index.html").read_text(encoding="utf-8")
html = html.replace('<script src="config.js" onerror="void 0"></script>', f"<script>window.FINNHUB_KEY={safe(key())}</script>")
html = html.replace('<script src="data.js"></script>', f"<script>window.DATA={safe(data())}</script>")
components.html(html, height=3200, scrolling=True)
