import streamlit as st
import pandas as pd
import requests
import openai
import extruct
import trafilatura
from bs4 import BeautifulSoup
import json
import re

# --- OpenAI Key ---
api_key = st.text_input("🔑 OpenAI API Key", type="password")
if not api_key:
    st.warning("Bitte gib deinen OpenAI API Key ein.")
    st.stop()
client = openai.OpenAI(api_key=api_key)

# --- UI: URL-Eingabe ---
st.title("🔍 Seitentyp-Kategorisierung")
input_mode = st.radio("📥 URLs eingeben oder CSV hochladen?", ["Manuell eingeben", "CSV hochladen"])

urls = []

if input_mode == "Manuell eingeben":
    input_text = st.text_area("✏️ Gib die URLs ein (eine pro Zeile)")
    if input_text:
        urls = [url.strip() for url in input_text.splitlines() if url.strip()]
elif input_mode == "CSV hochladen":
    file = st.file_uploader("📄 CSV mit URLs hochladen (Spalte A ab Zeile 2)", type=["csv"])
    if file:
        df = pd.read_csv(file)
        urls = df.iloc[1:, 0].dropna().tolist()

if not urls:
    st.stop()

# --- Typ-Zuordnungen ---
MARKUP_TYPE_TO_SEITENTYP = {
    "Recipe": "Rezeptseite", "Product": "Produktdetailseite",
    "NewsArticle": "Blog/Artikel", "BlogPosting": "Blog/Artikel", "Article": "Blog/Artikel",
    "FAQPage": "Blog/Artikel", "HowTo": "Blog/Artikel", "Event": "Eventseite",
    "JobPosting": "Stellenanzeige", "SearchResultsPage": "Suchergebnisseite",
    "CollectionPage": "Kategorieseite", "ContactPage": "Kontaktseite"
}

URL_PATTERNS = {
    "Rezeptseite": ["rezepte", "rezept", "recettes", "recipe"],
    "Produktdetailseite": ["produkt", "produit", "product", "angebote"],
    "Kategorieseite": ["kategorie", "category", "produkte", "shop"],
    "Suchergebnisseite": ["suche", "search", "s=", "q=", "query"],
    "Stellenanzeige": ["job", "stelle", "emploi", "career"],
    "Kontaktseite": ["kontakt", "contact", "hilfe"],
    "Eventseite": ["event", "veranstaltung", "webinar"],
    "Teamseite": ["team"],
    "Karriereübersicht": ["karriere", "career-overview"],
    "Glossarseite": ["glossar", "lexikon", "glossary"],
    "Newsletter-Landingpage": ["newsletter"],
    "Downloadseite / Whitepaper": ["whitepaper", "downloads", "ebook"],
    "Über uns": ["ueber-uns", "about-us"],
    "Standortseite / Filialseite": ["standort", "filiale", "location"],
    "Blog/Artikel": ["blog", "artikel", "ratgeber", "faq", "wissen"]
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

def extract_meta(html):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title else ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
    return title, description

def extract_main_text(html):
    result = trafilatura.extract(html, include_comments=False, include_tables=False)
    return result.strip()[:1000] if result else ""

def gpt_classify(url, title, desc, body, data):
    user_input = f"""
URL: {url}
Title: {title}
Description: {desc}
Strukturierte Daten: {json.dumps(data)}
Body (Auszug): {body}
"""
    system_prompt = "Bitte bestimme den zutreffendsten Seitentyp aus dieser Liste und gib **nur den Seitentyp als Antwort** zurück: Startseite, Sprachstartseite, Blog/Artikel, Glossarseite, Produktdetailseite, Kategorieseite, Rezeptseite, Eventseite, Stellenanzeige, Karriereübersicht, Über uns, Kontaktseite, Teamseite, Standortseite / Filialseite, Downloadseite / Whitepaper, Newsletter-Landingpage, 404 / Fehlerseite. Wenn keiner passt, darfst du eine neue sinnvolle Kategorie vorschlagen."

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
    )
    return response.choices[0].message.content.strip()

# --- Analyse starten ---
results = []
with st.spinner("🔍 Analysiere Seiten..."):
    for url in urls:
        try:
            html, final_url = fetch_html(url)
            data = extract_structured_data(html, final_url)
            typ = classify_by_markup(data) or classify_by_url(final_url)

            if not typ:
                title, desc = extract_meta(html)
                body = extract_main_text(html)
                typ = gpt_classify(final_url, title, desc, body, data)

            results.append({"URL": final_url, "Seitentyp": typ})
        except Exception as e:
            results.append({"URL": url, "Seitentyp": f"Fehler: {e}"})

# --- Ergebnis anzeigen ---
df = pd.DataFrame(results)
st.success("✅ Analyse abgeschlossen")
st.dataframe(df)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button("📥 CSV herunterladen", csv, "seitentyp-analyse.csv", "text/csv")
