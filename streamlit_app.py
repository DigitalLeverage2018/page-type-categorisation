import streamlit as st
import pandas as pd
import requests
import openai
import extruct
import trafilatura
from bs4 import BeautifulSoup
import json
import re



import streamlit as st
import pandas as pd
import requests
import openai
import extruct
import trafilatura
from bs4 import BeautifulSoup
import json
import re

# --- Titel & Callout ---
st.set_page_config(page_title="Seiten Typ kategorisieren", layout="wide")
st.title("🔍 Seiten Typ kategorisieren")

with st.expander("ℹ️ Was macht dieses Tool?", expanded=True):
    st.markdown(
        """
        Dieses Tool analysiert Webseiten-URLs und erkennt automatisch den Seitentyp anhand von URL-Mustern, strukturierten Daten und KI.Für jede URL wird eine Hauptkategorie und ggf. eine Unterkategorie erstellt.
        """
    )

# --- OpenAI API Key ---
st.subheader("🔑 OpenAI API Key")
api_key = st.text_input("Bitte gib deinen API Key ein", type="password")
st.markdown("[💡 API-Key generieren](https://platform.openai.com/api-keys)", unsafe_allow_html=True)

if not api_key:
    st.warning("Bitte gib deinen OpenAI API Key ein.")
    st.stop()
client = openai.OpenAI(api_key=api_key)

# --- Eingabe URLs ---
st.subheader("📥 URLs eingeben")

input_text = st.text_area("✏️ URLs (eine pro Zeile eingeben)", height=150)
file = st.file_uploader("Oder lade eine CSV-Datei mit URLs hoch (Spalte A, ab Zeile 2)", type=["csv"])

urls = []
if input_text:
    urls = [url.strip() for url in input_text.splitlines() if url.strip()]
elif file:
    df = pd.read_csv(file)
    urls = df.iloc[1:, 0].dropna().tolist()

if urls:
    st.session_state.urls = urls

# --- Analyse starten Button ---
if st.button("🚀 Analyse starten"):
    st.session_state.start_analysis = True

# --- Analyse stoppen, wenn keine URLs oder Button nicht gedrückt ---
if "start_analysis" not in st.session_state or not st.session_state.start_analysis:
    st.stop()
if "urls" not in st.session_state or not st.session_state.urls:
    st.warning("❗ Bitte gib mindestens eine gültige URL ein.")
    st.stop()

urls = st.session_state.urls



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
    "Homepage": [r"^https?:\/\/[^\/]+\/?$", r"^https?:\/\/[^\/]+\/[a-z]{2,3}\/?$"],
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
    "Datenschutz": [r"/datenschutz", r"/privacy[-_]?policy", r"/rechtliches", r"/data[-_]?protection"],
    "Case Study": [r"/case[-_]?studies?", r"/cases?", r"/referenzen?/"],
    "Blog/Artikel": [r"/blog", r"/artikel", r"/post", r"/ratgeber"],
    "Newsbeitrag": [r"/news", r"/neuigkeiten"],
    "Sonstige Kategorie": [r"/themen/", r"/focus/", r"/special[s]?/"]
}

CONTENT_RELEVANT_TYPES = [
    "Blog/Artikel", "Newsbeitrag", "Kategorieseite", "Produktdetailseite",
    "Produktkategorie", "Service kategorie", "Serviceseite", "Sonstige Kategorie"
]

# GPT-Klassifikation für Ebene 2
def gpt_classify_subtype(url, title, desc, body):
    user_input = f"""
URL: {url}
Title: {title}
Description: {desc}
Body (Auszug): {body}
"""
    system_prompt = """
Bitte bestimme die zutreffende Unterkategorie aus dieser Liste und gib **nur die Unterkategorie als Antwort** zurück:

PLC-Pain Points, PLC-Kosten, PLC-How-Tos, PLC-Tools & Templates, PLC-Buyer’s Guides, PLC-Alternativen, PLC-Vergleiche, PLC-Listicles, PLC-Case Studies, PLC-Checklisten,
TLC-Opinion Piece, TLC-Industry Insight, TLC-Expert Voice, TLC-Personal Story, TLC-Data Insight, TLC-Essay,
Pressemitteilung, News & Updates, Glossarartikel, Sonstige, Unklar
"""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]
    )
    return response.choices[0].message.content.strip()

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
    for typ, patterns in HAUPTTYP_REGEX.items():
        for pattern in patterns:
            if re.search(pattern, url):
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
    system_prompt = "Bitte bestimme den zutreffendsten Seitentyp aus dieser Liste und gib **nur den Seitentyp als Antwort** zurück: Homepage, Kategorieseite, Suchergebnisseite, Stellenanzeige, Kontaktseite, Eventseite, AGB, Teamseite, Karriereseite, Glossarseite, Newsletter, Über uns, Standort, Blog/Artikel, Newsbeitrag, Produktdetailseite, Rezeptdetailseite, Produktkategorie, Rezeptkategorie, Service kategorie, sonstige Kategorie, Serviceseite, Datenschutz, Case Study. Wenn keiner passt, darfst du eine neue sinnvolle Kategorie vorschlagen."

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
status_text = st.empty()
total = len(urls)

for i, url in enumerate(urls):
    try:
        status_text.text(f"🔍 Analysiere URL {i+1} von {total}:")
        html, final_url = fetch_html(url)
        data = extract_structured_data(html, final_url)
        typ = classify_by_markup(data) or classify_by_url(final_url)

        title, desc = extract_meta(html)
        body = extract_main_text(html)

        if not typ:
            typ = gpt_classify(final_url, title, desc, body, data)

        if typ == "Produktdetailseite":
            subtype = "PLC-Produktseite"
        elif typ == "Serviceseite":
            subtype = "PLC-Serviceseite"
        elif typ in CONTENT_RELEVANT_TYPES:
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
st.download_button("📥 CSV herunterladen", csv, "seitentyp-analyse.csv", "text/csv")
