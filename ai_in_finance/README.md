# AI in Finance – eigene Agenten auf Basis von FinRobot

Dieser Ordner enthaelt alles, was im Rahmen des Kursprojekts **neu** entstanden ist. Die
Original-Tutorials von FinRobot liegen unveraendert unter `finrobot_autogen/tutorials_*`.

## Struktur

| Ordner | Inhalt |
|---|---|
| `notebooks/` | `annual_report_agent.ipynb` (Annual Report), `investment_committee.ipynb` (CIO + 3 Analystengruppen, aus FinRobot `experiments/portfolio_optimization.py`), `fingpt_forecaster.ipynb` (Wochenprognose, aus FinRobot-Tutorial), `earnings_reviewer.ipynb` (Quartals-Update, neuestes Quartal), `earnings_reviewer_multi.ipynb` (alle Quartale seit dem 10-K, Thesen-Protokoll) |
| `lib/` | Eigene Agenten und Tools (`report_agent.py`, `investment_committee.py`, `forecaster.py`, `peer_tools.py`, `outlook_tools.py`, `tenk_search.py`, `news_tools.py`, `earnings_reviewer.py`, `earnings_reviewer_multi.py`, `quarterly_data.py`) |
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
