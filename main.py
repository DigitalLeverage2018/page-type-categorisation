# main.py

import os
import pandas as pd
import openai
import requests
import base64
import trafilatura
import extruct
import re
import asyncio
import tempfile
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from playwright.async_api import async_playwright

# 🔧 API-Key einlesen
openai.api_key = input("🔑 Bitte gib deinen OpenAI API Key ein: ").strip()

# 📥 CSV-Datei laden
csv_path = input("📄 Pfad zur CSV-Datei mit URLs (erste Spalte, ab Zeile 2): ").strip()
df = pd.read_csv(csv_path)
urls = df.iloc[1:, 0].dropna().tolist()

# 🔍 Mapping strukturierte Daten → Seitentyp
MARKUP_TYPE_TO_SEITENTYP = {
    "Recipe": "Rezeptseite",
    "Product": "Produktdetailseite",
    "NewsArticle": "Blog/Artikel",
    "BlogPosting": "Blog/Artikel",
    "Article": "Blog/Artikel",
    "FAQPage": "Blog/Artikel",
    "HowTo": "Blog/Artikel",
    "Event": "Eventseite",
    "JobPosting": "Jobdetailseite",
    "SearchResultsPage": "Suchergebnisseite",
    "CollectionPage": "Kategorieseite",
    "ContactPage": "Kontaktseite"
}

URL_PATTERNS = {
    "Rezeptseite": ["rezepte", "rezept", "recettes", "recette", "recipes", "recipe"],
    "Produktdetailseite": ["produkt", "produit", "product", "item", "angebote", "offers"],
    "Kategorieseite": ["kategorie", "categorie", "category", "produkte", "produits", "shop", "boutique", "magasin"],
    "Suchergebnisseite": ["suche", "recherche", "search", "s=", "q=", "query"],
    "Jobdetailseite": ["job", "stelle", "emploi", "poste", "career", "position"],
    "Kontaktseite": ["kontakt", "contact", "support", "hilfe", "aide", "assistance"],
    "Eventseite": ["event", "veranstaltung", "evenement", "manifestation", "webinar", "kalender", "calendrier"],
    "Teamseite": ["team"],
    "Karriereübersicht": ["karriere", "career-overview", "carriere"],
    "Glossarseite": ["glossar", "lexikon", "glossary"],
    "Newsletter-Landingpage": ["newsletter"],
    "Downloadseite / Whitepaper": ["whitepaper", "downloads", "ebook"],
    "Über uns": ["ueber-uns", "about-us", "a-propos"],
    "Standortseite / Filialseite": ["standort", "filiale", "location", "store-locator"],
    "Blog/Artikel": ["blog", "artikel", "article", "ratgeber", "guide", "tips", "conseils", "faq", "how-to", "wissen", "news", "actualites", "updates"]
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
    for seitentyp, patterns in URL_PATTERNS.items():
        if any(p in url for p in patterns):
            return seitentyp
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
    desc_tag = soup.find("meta", attrs={"name": "description"})
    description = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
    return title, description

def gpt_classify(url, title, description, body_text, structured_data, screenshot_b64):
    user_input = f"""
URL: {url}
Title: {title}
Description: {description}
Strukturierte Daten: {structured_data}
Body (Auszug): {body_text}
"""
    system_prompt = "Bitte bestimme anhand der folgenden Informationen, welcher dieser Seitentypen auf die Seite zutrifft. Wähle den **passendsten** aus dieser Liste und **verwende ihn exakt so, wie angegeben** (ohne Abwandlungen, Ergänzungen oder Varianten):Startseite, Sprachstartseite, Blog/Artikel, Glossarseite, Produktdetailseite, Kategorieseite, Rezeptseite, Eventseite, Stellenanzeige, Karriereübersicht, Über uns, Kontaktseite, Teamseite, Standortseite / Filialseite, Downloadseite / Whitepaper, Newsletter-Landingpage, 404 / Fehlerseite. Wenn **keiner dieser Typen auch nur annähernd passt**, darfst du **eine neue, sinnvolle Kategorie vorschlagen** – gib dann **nur die neue Kategorie als Antwort aus** (ohne Erklärung oder Mischform)."

    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": user_input},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
            ]}
        ]
    )
    return response.choices[0].message.content.strip()

async def analyze_urls(url_list):
    results = []
    for url in url_list:
        print(f"🔍 Analysiere: {url}")
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
                typ = gpt_classify(final_url, title, desc, body, data, b64)
                os.remove(screenshot_path)

            results.append({"URL": final_url, "Seitentyp": typ})
        except Exception as e:
            print(f"⚠️ Fehler bei {url}: {e}")
            results.append({"URL": url, "Seitentyp": "Fehler"})
    return results

def main():
    asyncio.run(run_analysis())

async def run_analysis():
    results = await analyze_urls(urls)
    df_out = pd.DataFrame(results)
    out_path = "seitentyp-analyse.csv"
    df_out.to_csv(out_path, index=False)
    print(f"✅ Analyse abgeschlossen: {out_path}")

if __name__ == "__main__":
    main()
