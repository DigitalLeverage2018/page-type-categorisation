import streamlit as st
import pandas as pd
import openai
import asyncio
import tempfile
import os
import requests
import base64
import trafilatura
import extruct
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from playwright.async_api import async_playwright

st.set_page_config(page_title="Seitentyp-Kategorisierung", layout="wide")
st.title("🔍 Seitentyp-Kategorisierung")

# Eingabe: OpenAI API Key & URLs
api_key = st.text_input("🔑 OpenAI API Key", type="password")
url_text = st.text_area("📋 URLs einfügen (eine pro Zeile)", height=200)

# URLs vorbereiten
urls = [line.strip() for line in url_text.splitlines() if line.strip()]

# Klassifizierungsregeln
MARKUP_TYPE_TO_SEITENTYP = {
    "Recipe": "Rezeptseite", "Product": "Produktdetailseite",
    "NewsArticle": "Blog/Artikel", "BlogPosting": "Blog/Artikel", "Article": "Blog/Artikel",
    "FAQPage": "Blog/Artikel", "HowTo": "Blog/Artikel", "Event": "Eventseite",
    "JobPosting": "Jobdetailseite", "SearchResultsPage": "Suchergebnisseite",
    "CollectionPage": "Kategorieseite", "ContactPage": "Kontaktseite"
}

URL_PATTERNS = {
    "Rezeptseite": ["rezepte", "rezept"], "Produktdetailseite": ["produkt", "product"],
    "Kategorieseite": ["kategorie", "category"], "Suchergebnisseite": ["suche", "search"],
    "Jobdetailseite": ["job", "stelle"], "Kontaktseite": ["kontakt", "contact"],
    "Eventseite": ["event", "veranstaltung"], "Glossarseite": ["glossar", "lexikon"],
    "Blog/Artikel": ["blog", "artikel", "ratgeber", "wissen"]
}

def is_homepage(url):
    path = re.sub(r'^https?:\/\/[^\/]+', '', url).strip().lower()
    return bool(re.match(r'^\/([a-z]{2,3}(?:-[a-z]{2,3})?)?\/?$', path))

def fetch_html(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    return response.text, response.url

def extract_structured_data(html, base_url):
    return extruct.extract(html, base_url=base_url, syntaxes=["json-ld", "microdata", "rdfa"], uniform=True)

def classify_by_markup(data):
    types = []
    for syntax in data.values():
        for item in syntax:
            if "@type" in item:
                t = item["@type"]
                types.extend(t if isinstance(t, list) else [t])
    for t in types:
        if t in MARKUP_TYPE_TO_SEITENTYP:
            return MARKUP_TYPE_TO_SEITENTYP[t]
    return None

def classify_by_url(url):
    url = url.lower()
    if is_homepage(url):
        return "Startseite"
    for typ, patterns in URL_PATTERNS.items():
        if any(p in url for p in patterns):
            return typ
    return None

async def create_screenshot(url, path):
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, timeout=60000)
        await page.screenshot(path=path, full_page=True)
        await browser.close()

def encode_image(path):
    with open(path, "rb") as img:
        return base64.b64encode(img.read()).decode("utf-8")

def extract_main_text(html):
    result = trafilatura.extract(html, include_comments=False, include_tables=False)
    return result.strip()[:1000] if result else ""

def extract_meta(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title else ""
    desc = soup.find("meta", attrs={"name": "description"})
    return title, desc["content"].strip() if desc and desc.get("content") else ""

def gpt_classify(url, title, description, body, structured_data, screenshot_b64, api_key):
    openai.api_key = api_key
    prompt = f"""
URL: {url}
Title: {title}
Description: {description}
Strukturierte Daten: {structured_data}
Body (Auszug): {body}
"""
    system = "Bestimme anhand der Informationen den genauesten Seitentyp..."
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
            ]}
        ]
    )
    return response.choices[0].message.content.strip()

async def analyze_urls(urls, api_key):
    results = []
    for url in urls:
        try:
            html, final_url = fetch_html(url)
            data = extract_structured_data(html, final_url)
            typ = classify_by_markup(data) or classify_by_url(final_url)

            if not typ:
                title, desc = extract_meta(html)
                body = extract_main_text(html)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    screenshot_path = tmp.name
                await create_screenshot(final_url, screenshot_path)
                b64 = encode_image(screenshot_path)
                typ = gpt_classify(final_url, title, desc, body, data, b64, api_key)
                os.remove(screenshot_path)

            results.append({"URL": final_url, "Seitentyp": typ})
        except Exception as e:
            results.append({"URL": url, "Seitentyp": f"Fehler: {e}"})
    return results

# Ausführen
if api_key and urls:
    if st.button("🚀 Analyse starten"):
        with st.spinner("Bitte warten..."):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            df_out = pd.DataFrame(loop.run_until_complete(analyze_urls(urls, api_key)))
            st.success("✅ Analyse abgeschlossen")
            st.dataframe(df_out)

            csv = df_out.to_csv(index=False).encode("utf-8")
            st.download_button("📥 CSV herunterladen", data=csv, file_name="seitentyp-analyse.csv", mime="text/csv")


