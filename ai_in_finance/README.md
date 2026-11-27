# AI in Finance – BLUMBÖRG (eigene Agenten auf Basis von FinRobot)

Dieser Ordner enthaelt alles, was im Rahmen des Kursprojekts **neu** entstanden ist. Die
Original-Tutorials von FinRobot liegen unveraendert unter `finrobot_autogen/tutorials_*`.

**Installation und erster Lauf:** `INSTALLATION.md` · **Bedienung der App:** `ANLEITUNG_APP.md`

## Struktur

| Ordner | Inhalt |
|---|---|
| `notebooks/` | `annual_report_agent.ipynb` (Annual Report), `investment_committee.ipynb` (CIO + 3 Analystengruppen, aus FinRobot `experiments/portfolio_optimization.py`), `fingpt_forecaster.ipynb` (Wochenprognose, aus FinRobot-Tutorial), `earnings_reviewer.ipynb` (Quartals-Update, neuestes Quartal), `earnings_reviewer_multi.ipynb` (alle Quartale seit dem 10-K, Thesen-Protokoll), `portfolio_manager.ipynb` (Portfolio-Analyse, Optimierung, Backtest, echte Performance aus Broker-Exporten), `news_tracker.ipynb` (woechentlicher News-Digest mit Thesenbezug), `pipeline.ipynb` (alle Agenten in einem Ablauf) |
| `lib/` | Eigene Agenten und Tools (`report_agent.py`, `investment_committee.py`, `forecaster.py`, `peer_tools.py`, `outlook_tools.py`, `tenk_search.py`, `news_tools.py`, `earnings_reviewer.py`, `earnings_reviewer_multi.py`, `quarterly_data.py`, `portfolio_engine.py`, `portfolio_manager.py`, `transactions.py`, `performance.py`, `news_tracker.py`, `pipeline.py`)
| `portfolios/` | Portfolio-Dateien (CSV: ticker + weight oder shares), z. B. `sample_portfolio.csv`; Transaktions-Exporte (Scalable Capital, Trade Republic, Smartbroker+ oder Vorlage `sample_transactions.csv`) und `isin_map.csv` (ISIN -> Yahoo-Ticker). Broker-Exporte, Uploads und `isin_map.csv` sind gitignored und bleiben lokal; nur die Musterdateien `sample_*.csv` liegen im Repository | |
| `forecasts/` | Protokoll der Forecaster-Vorhersagen und Auswertung (`scripts/score_forecasts.py`) |
| `reports/` | Erzeugte Reports und Faktencheck-JSONs; `reports/prototypes/` = fruehe Versionen |
| `notes/` | Belege fuer den Kurs-Report (z. B. Halluzinationen im Original) |
| `scripts/` | Diagnose- und Testskripte; Evaluation: `run_eval.py` (Batch-Laeufe mit Kosten/Laufzeit), `factcheck_text.py` (Baseline-Text pruefen), `eval_summary.py` (Ergebnistabelle + Stichprobe) |
| `eval/` | Ergebnisse der Evaluation (CSV) |

## Anpassungen an FinRobot selbst (`finrobot_autogen/finrobot/`)

Einige Fehler und veraltete Teile mussten direkt in der Bibliothek behoben werden. Alle Stellen
sind im Code mit `Angepasst` kommentiert; der Originalzustand ist ueber Git nachvollziehbar.

| Datei | Aenderung | Grund |
|---|---|---|
| `data_source/fmp_utils.py` | FMP ersetzt durch SEC EDGAR + Yahoo Finance; `n/a`/`n/m` statt Fantasiewerten; EV/Sales | FMP-Legacy-Endpunkte fuer neue Konten gesperrt (403/402) |
| `data_source/sec_utils.py` | HTML-Entities umwandeln, UTF-8 | Sonderzeichen, Windows-Kodierung |
| `agents/workflow.py` | Shadow-Agent: 1 statt 2 Runden; Ergebnis als "ANALYSIS RESULT (tool output)" gekennzeichnet; `parallel_tool_calls` fuer Shadow entfernt | Analysen gingen verloren bzw. wurden vom Modell als selbst erfunden verworfen |
| `agents/utils.py` | Erkennung paralleler Tool-Aufrufe, UTF-8 | Absturz bei mehreren Pfaden |
| `functional/analyzer.py` | 52-Wochen-Spanne korrigiert; Peer-Namen aus Daten; fest kodierte Jahre im Prompt entfernt | Fehler im Original |
| `functional/charting.py` | Kurs-Chart 3 Jahre; Bewertungs-Chart (KGV- bzw. EV/Sales-Band + FCF-Rendite) | KGV bei Verlusten sinnlos |
| `functional/reportlab.py` | Neues Layout, Investment Summary, Quellen [1]-[4], Segment-/Peer-Tabelle, Plausibilitaetspruefung, Faktencheck-Anhang | Lesbarkeit, Nachpruefbarkeit |
| `functional/fact_check.py` | **neu**: automatischer Faktencheck | Kern des Projekts |
| `data_source/finnhub_utils.py` | `get_basic_financials`: Fehler im Original behoben (dict waehrend Iteration veraendert, leere Reihen) | Tool lieferte bei jeder Spaltenauswahl nur Fehler |
| `functional/outlook.py` | **neu**: Analystenkonsens (Umsatz, EPS, Forward-Multiples) und Liquiditaet (Cash, Schulden, FCF, Cash Runway, Verwaesserung) und Reverse DCF aus Yahoo, deterministisch berechnet | Sell-Side-Standard: Prognosen und Finanzierung; Zahlen nicht vom LLM |

## Architektur des eigenen Agenten (`lib/report_agent.py`)

Im Original schreiben die Analyse-Tools nur eine Auftragsdatei; ein zweiter "Shadow"-Agent verfasst
die Analyse in einem verschachtelten Chat, und das Ergebnis erscheint als eigene Nachricht des
Haupt-Agenten. Claude Haiku hielt diese Analysen fuer selbst erfunden und verwarf sie. Im eigenen
Agenten rufen die Analyse-Tools das Modell deshalb direkt auf und geben die Analyse als
**Tool-Ergebnis** zurueck ("ANALYSIS RESULT ..."), zusaetzlich gespeichert als `*_analysis.txt`.
Die Peer-Suche (`lib/peer_tools.py`) kombiniert Finnhub-Branchenpeers mit vom Agenten vorgeschlagenen
Tickern, sortiert nach Groessenaehnlichkeit und zeigt eine Kurzbeschreibung des Geschaeftsmodells.

## Nutzung
1. VS Code: `ai_in_finance/notebooks/annual_report_agent.ipynb` oeffnen, Kernel `.venv` waehlen.
2. In Zelle 2/3 Modell, Ticker, Geschaeftsjahr und ggf. Peers setzen.
3. Run All. Ergebnis liegt in `ai_in_finance/reports/<TICKER>_<FY>_<Modell>/`.

## Echte Performance aus Transaktionen (`lib/transactions.py`, `lib/performance.py`)

- Import: Broker-CSV wird automatisch erkannt (Scalable: bekannte Kopfzeile; Trade Republic: Transaktionsexport seit April 2026; Smartbroker+ und andere: deutsche/englische Spaltennamen, `;`/`,`, Dezimalkomma). Unbekannte Buchungstypen werden gemeldet, nicht geraten.
- ISIN -> Ticker ueber yfinance (bevorzugt Xetra), gespeichert in `portfolios/isin_map.csv` (von Hand korrigierbar).
- Kennzahlen (alles in EUR, deterministisch in Python): TTWROR (taeglich verkettet, ohne externe Zahlungen), MWR/IRR (XIRR), MSCI ACWI mit denselben Zahlungen, Gewinn/Verlust je Position (Durchschnittskosten), Wirkung jedes Kaufs/Verkaufs vs. ACWI, Gegenszenario ohne Trades.
- Datenqualitaet: Splits ueber Yahoo, fehlende Einzahlungen als implizite Einzahlung, Kursabweichung > 25 % als Warnung (falscher Ticker), Cash-Konto je Broker-Datei.
- Im Report: Seite "Actual Performance & Decisions" und Tool `get_actual_performance` fuer den Agenten.

## News-Tracker (`lib/news_tracker.py`, `notebooks/news_tracker.ipynb`)

- Watchlist: aktuelle Bestaende aus den Transaktions-Exporten -> `portfolios/watchlist.csv` (Suchbegriff und `track` von Hand anpassbar; ETFs automatisch ausgeschlossen).
- Sammeln: Finnhub und SEC EDGAR 8-K (US-Werte), Yahoo Finance (alle), Google-News-RSS (deutsch + englisch); Relevanzfilter per Name/Ticker/Cashtag, Dubletten raus, Speicher `news/news_store.jsonl` (jede Meldung wird nur einmal klassifiziert).
- Klassifizieren (eigenes, guenstiges Modell, 25 Meldungen pro Aufruf, JSON): Kategorie, Richtung, Wesentlichkeit 1-3, betroffene Investment-These aus dem Annual Report / Thesen-Protokoll.
- Marktreaktion (Python): Ueberrendite ggue. MSCI ACWI am Tag 0 und Tag 0..+1 (EUR), Volumen ggue. 20-Tage-Median.
- Analystenaktionen getrennt von den News: Yahoo-Historie der Rating-/Kursziel-Aenderungen plus aus Schlagzeilen extrahierte Aktionen (ohne Doppelte), 90-Tage-Momentum, Konsens-Upside; Verlauf in `news/analyst_actions.jsonl`.
- Stories (`news/stories.json`): wesentliche Meldungen je Position zu Geschichten gebuendelt (neu / eskaliert / laufend / beruhigt / quiet), Querschnittsthemen ueber mehrere Positionen.
- Signale (Python, aus der gespeicherten Historie): News-Volumen ggue. eigenem Schnitt, Sentiment Woche / 4 Wochen, Divergenz News vs. Kurs, Analysten-Revisionen, Nachlauf 5/20 Tage nach wesentlichen Meldungen.
- Backfill (`nt.backfill`): einmaliger Rueckblick ueber Finnhub/8-K fuer US-Werte (Woche fuer Woche klassifiziert, Stories in zeitlicher Reihenfolge).
- Digest-Agent: Zusammenfassung, Signale, Stories, Themen, Thesen-Alarme, Notizen je Position (review / no action), wesentliche Meldungen mit Links, Analystenaktionen, Faktencheck mit einer Korrekturrunde; Verlauf in `*_transcript.md`.
- Evaluation: `export_label_sample()` (Stichprobe zum Labeln), `evaluate_labels()` (Trefferquote, Macro-F1, Uebereinstimmung mit der Marktreaktion).
- `news/`, `reports/portfolio_*/` und `reports/news_*/` sind gitignored (enthalten Depotinformationen).

## Pipeline (`lib/pipeline.py`, `notebooks/pipeline.ipynb`, `scripts/run_pipeline.py`)

- Python prueft je Titel den Zustand (EDGAR + eigene Dateien) und plant nur Faelliges, jeweils mit Begruendung:
  Annual Report (neuer 10-K), Earnings Review mehrerer Quartale (neue 8-K Item 2.02 seit dem 10-K, noch nicht im Thesen-Protokoll),
  Investment Committee (neuer Report/Review, News-Alarm, Votum aelter als 30 Tage), Forecaster und News-Tracker (woechentlich), Portfolio Manager (am Ende).
- Nicht-US-Titel (ohne SEC-Filings) laufen nur ueber News-Tracker und Portfolio Manager.
- Uebergaben: Committee bekommt Thesen, Thesen-Status, Stories und News-Signale als Kontext; der Portfolio Manager eine Research-Sicht je Position (Tool `get_research_views`, Tabelle im PDF).
- Erst Plan ohne LLM (`plan`), dann `run_pipeline` (Fehler isoliert, `max_steps` als Kostenbremse); Protokoll mit Laufzeit und Kosten in `research/pipeline_runs/`.
- Kommandozeile: `python scripts/run_pipeline.py --top 5 --dry-run` bzw. `--max-steps 8` (z. B. woechentlich per Aufgabenplanung).

