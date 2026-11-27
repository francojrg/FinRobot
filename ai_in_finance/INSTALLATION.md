# BLUMBÖRG – Installation und erster Lauf

BLUMBÖRG ist ein System aus Research-Agenten für ein Aktienportfolio, aufgebaut auf FinRobot (AI4Finance Foundation).
Es erstellt zu jedem US-Titel einen Annual Report (10-K bzw. 20-F), verfolgt die Investment-Thesen Quartal für Quartal,
fasst die News zusammen, bewertet das Depot und schreibt einen Weekly Brief mit dem Handlungsbedarf. Jede Zahl in den
Reports wird automatisch gegen die Quellen geprüft. Die App läuft lokal auf dem eigenen Rechner; die Oberfläche ist
Englisch. Nur für akademische Zwecke, keine Anlageberatung.

---

## Schnellstart (Windows, etwa 15 Minuten)

1. **Python 3.11 installieren** – [Windows-Installer 64-bit](https://www.python.org/downloads/release/python-3119/).
   Beim Installieren **„Add python.exe to PATH“** anhaken. (Nicht 3.12 oder neuer.)
2. **Code herunterladen** – [ZIP von GitHub](https://github.com/francojrg/FinRobot/archive/refs/heads/master.zip)
   entpacken, oder mit Git: `git clone https://github.com/francojrg/FinRobot.git`
3. **`setup.bat`** im Ordner `ai_in_finance` doppelklicken (einmalig, 5–10 Minuten: legt die Python-Umgebung an und
   installiert die Pakete).
4. **`Desktop-Verknuepfung erstellen.bat`** doppelklicken (optional) – danach startet BLUMBÖRG über das Logo auf dem
   Desktop. Sonst **`Start BLUMBÖRG.bat`**. Die App öffnet sich im Browser (http://localhost:8501).
5. Die App startet beim ersten Mal auf **Settings** mit einem **Setup-Guide**: drei Schlüssel eintragen (siehe unten),
   jeweils **Save** und **Test**.
6. **Erster Test mit dem DEMO-Depot:** im Setup-Guide **„Go to Analysis“** → Portfolio **„DEMO · Valley Forge (13F)“**
   → **Create plan** → **Start analysis**. Der Lauf geht im Hintergrund weiter (etwa 1–1,5 Stunden, rund 1–3 USD – weniger, wenn Reports für die Titel schon im Repository liegen).

## Die drei Schlüssel

| | Wo | Kosten | Wofür |
|---|---|---|---|
| **OpenRouter** (Pflicht) | Konto anlegen, [Guthaben aufladen](https://openrouter.ai/credits), dann [Schlüssel erstellen](https://openrouter.ai/keys) | Prepaid ab 5 USD; etwa 0,10 USD je Annual Report, 2–4 Cent je Quartal | Sprachmodell aller Agenten (Standard: Claude Haiku) |
| **SEC User Agent** (Pflicht) | kein Konto – einfach Name und E-Mail eintragen, z. B. `Jane Doe jane@uni.edu` ([Regeln der SEC](https://www.sec.gov/os/accessing-edgar-data)) | kostenlos | Abrufe der 10-K, 10-Q und 8-K bei SEC EDGAR |
| **Finnhub** (empfohlen) | [registrieren](https://finnhub.io/register), Schlüssel steht im [Dashboard](https://finnhub.io/dashboard) | kostenlos | Firmen-News, Peer-Vorschläge |

**Tipp:** Auf openrouter.ai beim Schlüssel ein **Ausgabelimit** setzen (z. B. 20 USD). Ist es erreicht, scheitern die
Agenten mit „Key limit exceeded“ – dann Limit erhöhen und den Lauf neu starten (fertige Schritte bleiben erhalten).

**Ohne Schlüssel:** Yahoo Finance (Kurse, Abschlüsse, Konsens, ETF-Bestände) über die freie Bibliothek `yfinance` –
inoffiziell und verzögert, bei vielen Abfragen bremst Yahoo gelegentlich; Google News; SEC EDGAR; Deutsche Bundesbank
(Rendite 5-jähriger Bundesanleihen). sec-api.io und Financial Modeling Prep werden nicht mehr gebraucht.

Alle Schlüssel bleiben lokal in `finrobot_autogen/config_api_keys` und `OAI_CONFIG_LIST` und sind von Git
ausgeschlossen.

---

## Eigenes Portfolio

**Setup and automation → Analysis → Upload file**. Erkannt werden:

| Form | Beispiel | Ergebnis |
|---|---|---|
| Stückzahlen | `ticker,shares` → `AAPL,10` | Analyse mit aktuellem Depotwert |
| Transaktionen | Export von Trade Republic, Scalable Capital, Smartbroker+ oder `date,type,ticker,shares,price,…` | zusätzlich Depotverlauf, Rendite gegen den MSCI ACWI, Beiträge, eigene Entscheidungen |
| Gewichte | `ticker,weight` → `AAPL,40` | Analyse mit fiktivem Depotwert |

Semikolon oder Komma, deutsche Zahlen, deutsche Spaltennamen und ISINs statt Tickern werden erkannt. Jedes Portfolio
wird gespeichert; in der **Seitenleiste** wechselt man zwischen den eigenen Portfolios und dem DEMO-Depot, ohne neuen
Lauf. Unter **Setup and automation → Portfolios** lassen sich Portfolios umbenennen und zusammenfassen (z. B. Trade
Republic + Scalable). Firmen-Reports gelten für alle Portfolios – es wird nur Fehlendes neu erstellt. Europäische Titel
ohne SEC-Bericht bekommen News, Portfolio Review und Brief, aber noch keine Reports.

## Anpassen ohne Code

- **Agents** – je Agent: was er macht, welche Quellen er nutzt, Modell, Prompts, Zusatzanweisungen und Parameter
  (z. B. Positionslimit des Briefs). Änderungen bleiben lokal, jede Fassung wird gespeichert, „Reset to default“ stellt
  den Standard wieder her.
- **Log → Tools** – Wartungs-Skripte per Knopf: Prognosen auswerten, Evaluation, DEMO-Depot neu aus 13F bauen, App-Test.
- Eine Übersicht aller Ordner und Dateien steht in `PROJEKTKARTE.md`.

## Häufige Probleme

| Problem | Lösung |
|---|---|
| „Python 3.11 wurde nicht gefunden“ | Python 3.11 installieren (nicht 3.12+), PATH anhaken, `setup.bat` erneut |
| Agenten scheitern mit „Key limit exceeded“ / 402 | Guthaben oder Limit des OpenRouter-Schlüssels erhöhen, Lauf neu starten |
| Im Plan stehen alle Titel unter „Without SEC report“ | SEC User Agent unter Settings eintragen und **Test** drücken |
| Ein Ticker hat keine Kurse | Yahoo-Schreibweise verwenden (`SAP.DE`, `BRK-B`, `7203.T`); die App warnt beim Planen |
| Kurse/Kennzahlen fehlen kurzzeitig | Yahoo bremst gelegentlich – einige Minuten warten, Seite neu laden |
| Port 8501 belegt | altes Fenster der App schließen oder `streamlit run ai_in_finance/app/app.py --server.port 8502` |

## Tests (ohne Kosten, ohne Sprachmodell)

`Test Upload.bat` (CSV-Varianten), `Test App.bat` (jede Seite), `Test SEC-Abschnitte.bat`, `Test Vergleich sec-api.bat`,
`Test 20-F.bat` (ausländische Emittenten), `Test Insights.bat`. Ergebnisse unter `ai_in_finance/eval/`. Die meisten
laufen auch in der App unter **Log → Tools**.

## macOS oder Linux

Nicht getestet, sollte aber funktionieren (aus dem Hauptordner des Repositorys):

```
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r ai_in_finance/requirements-app.txt
python -c "import site,os;p=[s for s in site.getsitepackages() if s.endswith('site-packages')][0];open(os.path.join(p,'finrobot_local.pth'),'w').write(os.path.abspath('finrobot_autogen'))"
cp finrobot_autogen/config_api_keys_sample finrobot_autogen/config_api_keys
echo "[]" > finrobot_autogen/OAI_CONFIG_LIST
streamlit run ai_in_finance/app/app.py
```
