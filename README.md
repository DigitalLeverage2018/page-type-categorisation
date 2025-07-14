# 🧠 Seitentyp-Analyse-Tool

Dieses Tool analysiert eine Liste von URLs und bestimmt den jeweiligen **Seitentyp** mithilfe von strukturierten Daten, URL-Mustern, Inhaltsextraktion und GPT-4o.

## 🚀 Funktionen

- Erkennt strukturierte Daten (JSON-LD, Microdata, RDFa)
- Klassifiziert Seiten anhand von:
  - bekannten Markup-Typen
  - URL-Mustern
  - GPT-4o-Klassifizierung (inkl. Screenshot und Inhalt)
- Erstellt eine CSV mit URL + erkanntem Seitentyp

## 🔧 Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

## ▶️ Nutzung

```bash
python main.py
```

Du wirst nach zwei Eingaben gefragt:
1. Pfad zur CSV-Datei (z. B. `input.csv`)
2. Dein OpenAI API Key

**Input:**  
Eine CSV-Datei mit URLs in der ersten Spalte, ab Zeile 2.  
**Output:**  
Eine Datei `seitentyp-analyse.csv` mit URL und erkannter Seitentyp-Kategorie.

## 📥 Beispielhafte Eingabe

```csv
URL
https://example.com/rezept/schokoladenkuchen
https://example.com/produkt/tischlampe
```

## 🛡️ Datenschutz

Der Screenshot und Textauszug werden nur temporär für die GPT-Abfrage verwendet und nicht gespeichert.