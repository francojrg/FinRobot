# BLUMBÖRG – Installation und erster Lauf

BLUMBÖRG ist ein System aus Research-Agenten für ein Aktienportfolio, aufgebaut auf FinRobot (AI4Finance Foundation).
Es liest ein Portfolio als CSV, erstellt zu jedem US-Titel einen Annual Report (10-K bzw. 20-F) und Earnings Reviews
seit dem letzten Jahresbericht, fasst die News zusammen, bewertet das Depot und schreibt einen Brief mit dem
Handlungsbedarf. Jede Zahl in den Reports wird automatisch gegen die Quellen geprüft.
Die App läuft lokal auf dem eigenen Rechner. Nur für akademische Zwecke, keine Anlageberatung.

## Was man braucht

| | Wofür | Kosten |
|---|---|---|
| Windows-PC mit **Python 3.11** (64-bit) | Laufzeitumgebung (macOS/Linux: siehe unten) | kostenlos |
| **OpenRouter-Schlüssel** – [openrouter.ai/keys](https://openrouter.ai/keys) | Sprachmodell der Agenten (Standard: Claude Haiku) | etwa 0,15 USD je Annual Report, 0,03–0,05 USD je Earnings Review; Ausgabelimit für den Schlüssel setzen |
| **SEC User Agent** – Name und E-Mail, z. B. `Max Mustermann max@uni-mannheim.de` | Pflichtangabe der SEC für Abrufe aus EDGAR | kostenlos, keine Anmeldung |
| **Finnhub-Schlüssel** – [finnhub.io/register](https://finnhub.io/register) | News, Firmenprofile, Peer-Vorschläge | kostenlos |

Nicht mehr nötig: sec-api.io und Financial Modeling Prep. Die Abschnitte der 10-K, 10-Q und 20-F liest BLUMBÖRG
selbst aus den Originaldokumenten bei SEC EDGAR.

## Einrichten (einmalig, etwa 10 Minuten)

1. **Python 3.11** installieren: [python.org/downloads](https://www.python.org/downloads/release/python-3119/), Windows-Installer
   64-bit, beim Installieren **„Add python.exe to PATH“** anhaken.
2. Den Code holen: Repository klonen (`git clone …`) oder auf GitHub als ZIP herunterladen und entpacken.
3. Im Ordner `ai_in_finance` **`setup.bat`** doppelklicken. Es legt eine Python-Umgebung (`.venv`) an, installiert die
   Pakete aus `requirements-app.txt` und erzeugt leere Konfigurationsdateien.
4. **`Start BLUMBÖRG.bat`** doppelklicken. Die App öffnet sich im Browser (http://localhost:8501).
5. In der App unter **Einstellungen** die drei Schlüssel eintragen und mit „OpenRouter-Schlüssel testen“ prüfen.
   Die Schlüssel bleiben lokal in `finrobot_autogen/config_api_keys` und `OAI_CONFIG_LIST` (nicht in Git).

## Erster Lauf mit dem Musterdepot (etwa 1,5 Stunden, gut 1,50 USD)

1. **Einrichtung und Automatik → Analyse** öffnen, unter „Vorhandene Datei“ das
   **Musterdepot Valley Forge, nachgebaut ab 13F-Meldung (Transaktionen)** wählen.
   Es bildet die Positionen des Fonds Valley Forge Capital seit 2016 aus den öffentlichen 13F-Meldungen nach
   (selbstfinanziert mit 100.000 Startkapital, 10 aktuelle Titel, darunter ASML und TSMC mit Form 20-F).
2. **Plan erstellen**: zeigt je Titel, welche Agenten fällig sind, mit Dauer und Kosten.
3. **Analyse starten**. Der Lauf geht im Hintergrund weiter, auch wenn man die Seite wechselt; mit
   „Lauf abbrechen“ lässt er sich stoppen (fertige Schritte bleiben erhalten).
4. Danach: **Überblick**, **Portfolio**, **Firmen** und **News** ansehen (siehe `ANLEITUNG_APP.md`).

## Eigenes Portfolio

Unter **Analyse → Datei hochladen** eine CSV wählen. Erkannt werden:

| Form | Beispiel | Ergebnis |
|---|---|---|
| Gewichte | `ticker,weight` → `AAPL,40` (in % oder als Anteil) | Analyse mit fiktivem Depotwert |
| Stückzahlen | `ticker,shares` → `AAPL,10` | Analyse mit aktuellem Depotwert |
| Transaktionen | Export von Trade Republic, Scalable Capital, Smartbroker+ oder `date,type,ticker,shares,price,…` | zusätzlich Depotverlauf, Rendite gegen den MSCI ACWI, Beiträge, eigene Entscheidungen |

Semikolon oder Komma, deutsche Zahlen (`1.234,5`), Prozentzeichen, deutsche Spaltennamen (Gewicht, Anteil, Stück)
und ISINs statt Tickern werden erkannt; Aktiensplits rechnet die App heraus. Die Datei bleibt lokal unter
`portfolios/uploads/` (nicht in Git). Reports, die es für einen Titel schon gibt, werden wiederverwendet – nur
Fehlendes oder Veraltetes wird neu erstellt. Europäische Titel ohne SEC-Bericht bekommen keine Reports, aber News,
Portfolio Review und Brief.

## Tests (ohne Kosten, ohne Sprachmodell)

| Datei | Prüft |
|---|---|
| `Test Upload.bat` | 19 typische CSV-Varianten (Formate, Fehlerfälle) |
| `Test App.bat` | öffnet jede Seite der App mit allen Musterdateien und meldet Abstürze |
| `Test SEC-Abschnitte.bat` | Zerlegung echter 10-K und 10-Q aus EDGAR |
| `Test Vergleich sec-api.bat` | eigene Zerlegung gegen die früheren Abschnitte von sec-api.io |
| `Test 20-F.bat` | ausländische Emittenten (ASML, TSMC) |
| `Test Insights.bat` | Insights-Watchlist an echten Seiten |

Die Ergebnisse stehen jeweils auch unter `ai_in_finance/eval/`.

## Häufige Probleme

- **„Python 3.11 wurde nicht gefunden“**: Python 3.11 installieren (nicht 3.12 oder neuer), PATH anhaken, `setup.bat` erneut.
- **Lauf scheitert sofort**: Schlüssel unter Einstellungen prüfen; ohne OpenRouter-Guthaben laufen keine Agenten.
- **Ein Ticker hat keine Kurse**: Yahoo-Schreibweise verwenden (z. B. `SAP.DE`, `BRK-B`, `7203.T`); die App warnt beim Planen.
- **Port 8501 belegt**: altes Fenster der App schließen oder `streamlit run ai_in_finance/app/app.py --server.port 8502`.

## macOS oder Linux

```
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r ai_in_finance/requirements-app.txt
python -c "import site,os;p=[s for s in site.getsitepackages() if s.endswith('site-packages')][0];open(os.path.join(p,'finrobot_local.pth'),'w').write(os.path.abspath('finrobot_autogen'))"
cp finrobot_autogen/config_api_keys_sample finrobot_autogen/config_api_keys
echo "[]" > finrobot_autogen/OAI_CONFIG_LIST
streamlit run ai_in_finance/app/app.py
```
(Aus dem Hauptordner des Repositorys ausführen. Die .bat-Tests entsprechen `python ai_in_finance/scripts/test_*.py`.)
