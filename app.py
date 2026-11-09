"""Streamlit: corre fetch.build() (cache 1h) e embebe index.html. Tempo real = WebSocket do Yahoo no browser."""
import json, pathlib
import streamlit as st
import streamlit.components.v1 as components
import fetch

st.set_page_config(page_title="Terminal de Análise Fundamental", layout="wide")


@st.cache_data(ttl=3600, show_spinner="A obter dados do mercado (screeners + fundamentais)…")
def data():
    return fetch.build()


safe = lambda o: json.dumps(o).replace("</", "<\\/")
html = pathlib.Path(__file__).with_name("index.html").read_text(encoding="utf-8")
html = html.replace('<script src="data.js"></script>', f"<script>window.DATA={safe(data())}</script>")
components.html(html, height=900, scrolling=True)
