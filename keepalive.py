"""Abre a app num browser a sério (o Streamlit só conta visitas com browser) e acorda-a se estiver a dormir."""
import sys

from playwright.sync_api import sync_playwright

url = sys.argv[1]
with sync_playwright() as p:
    page = p.chromium.launch().new_page()
    page.goto(url, timeout=90_000)
    page.wait_for_timeout(15_000)
    wake = page.get_by_role("button", name="get this app back up")
    if wake.count():
        print("a dormir: a acordar")
        wake.first.click()
        page.wait_for_timeout(90_000)  # arranque da app
    else:
        page.wait_for_timeout(30_000)  # fica uns segundos "a ver" para contar como visita
    print("título:", page.title())
