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
api_key = st.text_input("\U0001F511 OpenAI API Key", type="password")
if not api_key:
    st.warning("Bitte gib deinen OpenAI API Key ein.")
    st.stop()
client = openai.OpenAI(api_key=api_key)

# --- Session State vorbereiten ---
if "urls" not in st.session_state:
    st.session_state.urls = []
if "start_analysis" not in st.session_state:
    st.session_state.start_analysis = False

# --- UI: URL-Eingabe ---
st.title("\U0001F50D Seitentyp-Kategorisierung")
input_mode = st.radio("\U0001F4C5 URLs eingeben, CSV oder Sitemap?", ["Manuell eingeben", "CSV hochladen", "Sitemap URL"])

if input_mode == "Manuell eingeben":
    input_text = st.text_area("✏️ Gib die URLs ein (eine pro Zeile)")
    if input_text:
        st.session_state.urls = [url.strip() for url in input_text.splitlines() if url.strip()]
    if st.button("\U0001F680 Analyse starten"):
        st.session_state.start_analysis = True

elif input_mode == "CSV hochladen":
    file = st.file_uploader("\U0001F4C4 CSV mit URLs hochladen (Spalte A ab Zeile 2)", type=["csv"])
    if file:
        df = pd.read_csv(file)
        st.session_state.urls = df.iloc[1:, 0].dropna().tolist()
    if st.button("\U0001F680 Analyse starten"):
        st.session_state.start_analysis = True

elif input_mode == "Sitemap URL":
    sitemap_url = st.text_input("🌐 Sitemap- oder Sitemap-Index-URL eingeben")
    exclude_dirs = st.text_area("🚫 Verzeichnisse ausschließen (ein Verzeichnis pro Zeile)", value="")
    include_dirs = st.text_area("✅ Nur diese Verzeichnisse einschließen (optional)", value="")

    import xml.etree.ElementTree as ET

elif input_mode == "Sitemap URL":
    sitemap_url = st.text_input("🌐 Sitemap- oder Sitemap-Index-URL eingeben")
    exclude_dirs = st.text_area("🚫 Verzeichnisse ausschließen (ein Verzeichnis pro Zeile)", value="")
    include_dirs = st.text_area("✅ Nur diese Verzeichnisse einschließen (optional)", value="")

    elif input_mode == "Sitemap URL":
    sitemap_url = st.text_input("🌐 Sitemap- oder Sitemap-Index-URL eingeben")
    exclude_dirs = st.text_area("🚫 Verzeichnisse ausschließen (ein Verzeichnis pro Zeile)", value="")
    include_dirs = st.text_area("✅ Nur diese Verzeichnisse einschließen (optional)", value="")

    elif input_mode == "Sitemap URL":
    sitemap_url = st.text_input("🌐 Sitemap- oder Sitemap-Index-URL eingeben")
    exclude_dirs = st.text_area("🚫 Verzeichnisse ausschließen (ein Verzeichnis pro Zeile)", value="")
    include_dirs = st.text_area("✅ Nur diese Verzeichnisse einschließen (optional)", value="")

    def get_urls_from_sitemap(url):
        collected_urls = []
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            xml = res.content.decode("utf-8")
            if "<sitemapindex" in xml:
                matches = re.findall(r"<loc>(.*?)</loc>", xml)
                for sm in matches:
                    collected_urls.extend(get_urls_from_sitemap(sm))
            else:
                collected_urls.extend(re.findall(r"<loc>(.*?)</loc>", xml))
        except Exception as e:
            st.error(f"Fehler beim Abrufen der Sitemap: {e}")
        return collected_urls

    if st.button("🚀 Analyse starten"):
        if sitemap_url:
            urls = get_urls_from_sitemap(sitemap_url)
            if exclude_dirs:
                excludes = [e.strip() for e in exclude_dirs.splitlines() if e.strip()]
                urls = [u for u in urls if not any(x in u for x in excludes)]
            if include_dirs:
                includes = [i.strip() for i in include_dirs.splitlines() if i.strip()]
                urls = [u for u in urls if any(x in u for x in includes)]
            st.session_state.urls = urls
            st.session_state.start_analysis = True
        else:
            st.warning("Bitte gib eine gültige Sitemap-URL ein.")



# --- Stopp, wenn Analyse nicht gestartet ---
if not st.session_state.start_analysis or not st.session_state.urls:
    st.stop()

urls = st.session_state.urls

# --- Hauptkategorien (Ebene 1) ---
MARKUP_TYPE_TO_SEITENTYP = {
    "Recipe": "Rezeptdetailseite", "Product": "Produktdetailseite",
    "NewsArticle": "Newsbeitrag", "BlogPosting": "Blog/Artikel", "Article": "Blog/Artikel",
    "FAQPage": "Blog/Artikel", "HowTo": "Blog/Artikel", "Event": "Eventseite",
    "JobPosting": "Stellenanzeige", "SearchResultsPage": "Suchergebnisseite",
    "CollectionPage": "Kategorieseite", "ContactPage": "Kontaktseite"
}

HAUPTTYP_REGEX = {
    "Homepage": [r"^https?:\\/\\/[^\\/]+\\/?$", r"^https?:\\/\\/[^\\/]+\\/[a-z]{2,3}\\/?$"],
    "Kategorieseite": [r"/kategorie[n]?/", r"/categories?/"],
    "Produktkategorie": [r"/produkt[-_]?kategorie[n]?/"],
    "Rezeptkategorie": [r"/rezept[-_]?kategorie[n]?/"],
    "Service kategorie": [r"/dienstleistungen?/", r"/services?/"],
    "Suchergebnisseite": [r"[?&](q|s|search|query|recherche)=", r"/suche", r"/search"],
    "Produktdetailseite": [r"/produkt[e]?[-/]?\\w+"],
    "Rezeptdetailseite": [r"/rezept[-/]?\\w+"],
    "Serviceseite": [r"/service[-/]?\\w+", r"/dienstleistung[-/]?\\w+"],
    "Stellenanzeige": [r"/job[s]?[-/]?", r"/stellenangebote?/"],
    "Kontaktseite": [r"/kontakt", r"/contact"],
    "Eventseite": [r"/event[s]?[-/]?", r"/veranstaltungen?/"],
    "Teamseite": [r"/team"],
    "Karriereseite": [r"/karriere", r"/careers?"],
    "Glossarseite": [r"/glossar", r"/lexikon"],
    "Newsletter": [r"/newsletter"],
    "Über uns": [r"/ueber[-_]?uns", r"/about[-_]?us"],
    "Standort": [r"/standort", r"/filiale", r"/location[s]?"],
    "AGB": [r"/agb", r"/terms[-_]?and[-_]?conditions"],
    "Blog/Artikel": [r"/blog", r"/artikel", r"/post", r"/ratgeber"],
    "Newsbeitrag": [r"/news", r"/neuigkeiten"],
    "Sonstige Kategorie": [r"/themen/", r"/focus/", r"/special[s]?/"]
}

CONTENT_RELEVANT_TYPES = [
    "Blog/Artikel", "Newsbeitrag", "Kategorieseite", "Produktdetailseite",
    "Produktkategorie", "Service kategorie", "Serviceseite", "Sonstige Kategorie"
]

# (Restlicher Code bleibt gleich...)
# --- Analyse starten ---
results = []
status_text = st.empty()
total = len(urls)

for i, url in enumerate(urls):
    status_text.text(f"\U0001F50D Analysiere URL {i+1} von {total}: {url}")
    try:
        html, final_url = fetch_html(url)
        data = extract_structured_data(html, final_url)
        typ = classify_by_markup(data) or classify_by_url(final_url)

        title, desc = extract_meta(html)
        body = extract_main_text(html)

        if not typ:
            typ = gpt_classify(final_url, title, desc, body, data)

        if typ in CONTENT_RELEVANT_TYPES:
            subtype = gpt_classify_subtype(final_url, title, desc, body)
        else:
            subtype = ""

        results.append({"URL": final_url, "Hauptkategorie": typ, "Unterkategorie": subtype})

    except Exception as e:
        results.append({"URL": url, "Hauptkategorie": f"Fehler: {e}", "Unterkategorie": ""})

# --- Ergebnis anzeigen ---
df = pd.DataFrame(results)
st.success("✅ Analyse abgeschlossen")
st.dataframe(df)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button("\U0001F4C5 CSV herunterladen", csv, "seitentyp-analyse.csv", "text/csv")
