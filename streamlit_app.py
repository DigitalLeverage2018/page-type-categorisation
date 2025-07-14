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
input_mode = st.radio("📅 URLs eingeben, CSV oder Sitemap?", ["Manuell eingeben", "CSV hochladen", "Sitemap URL"])

urls = []

if input_mode == "Manuell eingeben":
    input_text = st.text_area("✏️ Gib die URLs ein (eine pro Zeile)")
    if input_text:
        urls = [url.strip() for url in input_text.splitlines() if url.strip()]
elelif input_mode == "CSV hochladen":
    file = st.file_uploader("📄 CSV mit URLs hochladen (Spalte A ab Zeile 2)", type=["csv"])
    if file:
        df = pd.read_csv(file)
        urls = df.iloc[1:, 0].dropna().tolist()
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

    if sitemap_url:
        urls = get_urls_from_sitemap(sitemap_url)
        if exclude_dirs:
            excludes = [e.strip() for e in exclude_dirs.splitlines() if e.strip()]
            urls = [u for u in urls if not any(x in u for x in excludes)]
        if include_dirs:
            includes = [i.strip() for i in include_dirs.splitlines() if i.strip()]
            urls = [u for u in urls if any(x in u for x in includes)]

if not urls:
    st.stop()

# --- Button zum Starten der Analyse ---
if not st.button("🚀 Analyse starten"):
    st.stop()

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
    "Kategorieseite": [r"/kategorie[n]?/", r"/categories?/", r"/cat[eé]gories?/", r"/produkte[n]?/", r"/products?/", r"/produits?/"],
    "Produktkategorie": [r"/produkt[-_]?kategorie[n]?/", r"/product[-_]?categories?/", r"/cat[eé]gorie[-_]?produit[s]?"],
    "Rezeptkategorie": [r"/rezept[-_]?kategorie[n]?/", r"/recette[s]?[-_]?cat[eé]gorie[s]?/"],
    "Service kategorie": [r"/dienstleistungen?/", r"/services?/", r"/prestations?[-_]?de?[-_]?service/"],
    "Suchergebnisseite": [r"[?&](q|s|search|query|recherche)=", r"/suche", r"/search", r"/recherche"],
    "Produktdetailseite": [r"/produkt[e]?[-/]?\w+", r"/product[-/]?\w+", r"/produit[-/]?\w+"],
    "Rezeptdetailseite": [r"/rezept[-/]?\w+", r"/recette[-/]?\w+"],
    "Serviceseite": [r"/service[-/]?\w+", r"/dienstleistung[-/]?\w+", r"/prestation[-/]?\w+"],
    "Stellenanzeige": [r"/job[s]?[-/]?", r"/stellenangebote?/", r"/emplois?/", r"/karriere/"],
    "Kontaktseite": [r"/kontakt", r"/contact", r"/nous[-_]?contacter", r"/contactez[-_]?nous"],
    "Eventseite": [r"/event[s]?[-/]?", r"/veranstaltungen?/", r"/\u00e9v\u00e9nements?/"],
    "Teamseite": [r"/team", r"/ueber-uns/team", r"/equipe"],
    "Karriereseite": [r"/karriere", r"/careers?", r"/emplois?[-_]?chez[-_]?nous"],
    "Glossarseite": [r"/glossar", r"/lexikon", r"/glossaire", r"/glossary"],
    "Newsletter": [r"/newsletter", r"/newsletters", r"/lettre[-_]?d[-_]?information"],
    "\u00dcber uns": [r"/ueber[-_]?uns", r"/about[-_]?us", r"/\u00e0[-_]?propos"],
    "Standort": [r"/standort", r"/filiale", r"/location[s]?", r"/magasin"],
    "AGB": [r"/agb", r"/terms[-_]?and[-_]?conditions", r"/conditions[-_]?g[eé]n[eé]rales"],
    "Blog/Artikel": [r"/blog", r"/artikel", r"/post", r"/ratgeber", r"/faq", r"/wissen", r"/conseils", r"/article", r"/magazine"],
    "Newsbeitrag": [r"/news", r"/neuigkeiten", r"/actualit[eé]s", r"/press(e|room)"],
    "Sonstige Kategorie": [r"/themen/", r"/focus/", r"/special[s]?/", r"/dossiers?/", r"/welten/"]
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
    system_prompt = "Bitte bestimme den zutreffendsten Seitentyp aus dieser Liste und gib **nur den Seitentyp als Antwort** zurück: Homepage, Kategorieseite, Suchergebnisseite, Stellenanzeige, Kontaktseite, Eventseite, AGB, Teamseite, Karriereseite, Glossarseite, Newsletter, Über uns, Standort, Blog/Artikel, Newsbeitrag, Produktdetailseite, Rezeptdetailseite, Produktkategorie, Rezeptkategorie, Service kategorie, sonstige kategorie, Serviceseite. Wenn keiner passt, darfst du eine neue sinnvolle Kategorie vorschlagen."

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
st.download_button("📅 CSV herunterladen", csv, "seitentyp-analyse.csv", "text/csv")
