# BLUMBÖRG – Projektkarte: wo was liegt

Stand 27.11.2026. In VS Code: diese Datei öffnen und mit `Strg+Shift+V` die Vorschau anzeigen. Die Links springen direkt zur Datei. Weitere Hilfen: `Strg+P` öffnet eine Datei über den Namen, `Strg+Shift+F` sucht im ganzen Projekt (z. B. nach `SYSTEM =` für alle Prompts), und die Gliederung („Outline“ links unten) zeigt alle Funktionen einer Datei.

---

## 1. Die drei großen Ordner im Repository `FinRobot/`

| Ordner | Was drin ist | Anfassen? |
|---|---|---|
| **`ai_in_finance/`** | **Unser Projekt**: App, eigene Agenten, Daten, Reports, Evaluation | ja – hier passiert alles |
| `finrobot_autogen/` | FinRobot-Bibliothek (Basis). Darin einige eigene Erweiterungen, siehe Abschnitt 6 | selten |
| `finrobot_equity/`, `finrobot_desktop/` | weitere Teile des Original-Repos | nein |

---

## 2. `ai_in_finance/` im Überblick

```
ai_in_finance/
├── app/            Die Streamlit-App (Oberfläche)
├── lib/            Die Logik: alle Agenten, Datenabrufe, Berechnungen
├── scripts/        Kommandozeilen-Skripte: Pipeline, Evaluation, Tests
├── portfolios/     Portfolio-Dateien (Muster im Repo, eigene Exporte privat)
├── reports/        Ergebnisse der Agenten je Firma (PDF + Daten), Archiv
├── research/       App-Zustand und Zwischenspeicher (privat, nicht in Git)
├── news/           News-Speicher (privat, nicht in Git)
├── forecasts/      Wochenprognosen und deren Auswertung
├── eval/           Evaluation für den Bericht
├── notebooks/      Jupyter-Notebooks (Evaluation, Tutorials)
├── notes/          Notizen
├── showcase_…/     Schnappschuss für die Präsentation
├── _nicht_im_showcase/  private Unterlagen (nicht in Git)
└── *.bat           Start, Desktop-Verknüpfung, Tests (Doppelklick)
```

---

## 3. Die App – `app/`

| Datei | Inhalt |
|---|---|
| [app/app.py](app/app.py) | **Hauptdatei**: alle Seiten (Overview, News, Portfolio, Company research, Ask, Setup mit Analysis/Portfolios/Automation, Agents, Log mit Tools, Settings), Header, Portfolio-Umschalter in der Seitenleiste, Navigation (`PAGE_DEFS` ganz unten), CSS ganz oben |
| [app/home_view.py](app/home_view.py) | Overview-Seite (Kacheln, Treemap, Termine); enthält auch das **gemeinsame CSS** der Komponenten (`CSS`) |
| [app/portfolio_view.py](app/portfolio_view.py) | Portfolio und Portfolio analysis (Charts, Positionen, Risiko, Optimierung) |
| [app/company_view.py](app/company_view.py) | Company research: Firmenkacheln, Firmenseite, KPI-Charts, Thesis Tracker, Bewertungskarten (`VAL_JS`) |
| [app/news_view.py](app/news_view.py) | News-Seite |
| [app/brief_view.py](app/brief_view.py) | Weekly-Brief-Ansicht und „Action needed“-Kacheln |
| `app/assets/` | Logo (`blumboerg.png`, `.ico`) |

Aufbau jeder `*_view.py`: oben `CSS`, dann `JS` (der Browser-Teil als Text), unten die Python-Funktion `render_…`, die die Daten übergibt.

---

## 4. Die Logik – `lib/`

### Agenten (schreiben mit dem Sprachmodell)

| Agent | Datei | Prompt im Code |
|---|---|---|
| Annual Report | [lib/report_agent.py](lib/report_agent.py) | `ANALYST_SYSTEM`, `default_message()`; Basisrolle „Expert_Investor“ in `finrobot_autogen/finrobot/agents/agent_library.py` |
| Earnings Review (mehrere Quartale) | [lib/earnings_reviewer_multi.py](lib/earnings_reviewer_multi.py) | `SYSTEM`, `multi_reviewer_message()` |
| Earnings Review (nur letztes Quartal, ältere Variante) | [lib/earnings_reviewer.py](lib/earnings_reviewer.py) | `SYSTEM`, `reviewer_message()` |
| Thesis Tracker (Thesis Book, Quarter Records) | [lib/thesis_tracker.py](lib/thesis_tracker.py) | `BOOK_PROMPT`, `QPROMPT` |
| News Tracker | [lib/news_tracker.py](lib/news_tracker.py) | `CLASSIFY_SYSTEM` (Meldungen bewerten), `STORY_SYSTEM` (Storylines), `THEME_SYSTEM` (Themen), `SYSTEM` (Wochen-Digest) |
| Portfolio Manager | [lib/portfolio_manager.py](lib/portfolio_manager.py) | `SYSTEM`, Auftrag in `run_portfolio_review()` |
| Weekly Brief | [lib/brief_agent.py](lib/brief_agent.py) | `SYSTEM`; die **Regeln** (entscheiden / einlesen / ruhig, Positionslimit 10 %) in `collect()` |
| Investment Committee (Beta) | [lib/investment_committee.py](lib/investment_committee.py) | Rollen aus `finrobot_autogen/experiments/investment_group.py` |
| Prognose (Beta) | [lib/forecaster.py](lib/forecaster.py) | `SYSTEM`, `forecast_message()` |
| Earnings Preview (Beta) | [lib/earnings_preview.py](lib/earnings_preview.py) | `PROMPT` |
| Interesting Reads (Beta) | [lib/reads.py](lib/reads.py) | `PROMPT` |
| KI-Basisfall Reverse DCF | [lib/valuation_data.py](lib/valuation_data.py) | `CASE_PROMPT` |
| Chat („Ask“) | [lib/chat.py](lib/chat.py) | `SYSTEM` |
| **Gemeinsame Stilregeln aller Agenten** | [lib/style.py](lib/style.py) | `STYLE_RULES` |

### Ablauf und Steuerung

| Datei | Inhalt |
|---|---|
| [lib/pipeline.py](lib/pipeline.py) | **Was ist fällig?** (`plan()`), Reihenfolge der Schritte (`STEP_ORDER`), Ausführen (`_run_step()`, `run_pipeline()`) |
| [lib/app_backend.py](lib/app_backend.py) | Upload erkennen, Lauf im Hintergrund starten, Kosten-/Zeitschätzung (`EST`), Einstellungen und Schlüssel |
| [lib/automation.py](lib/automation.py) | Automatik: Takt je Agent, Monatsbudget, Windows-Aufgabe |
| [lib/portfolios.py](lib/portfolios.py) | **Mehrere Portfolios**: Liste, Wechsel (Arbeitsbereich je Portfolio sichern/zurücklegen), Zusammenfassen, DEMO-Depot |
| [lib/agent_settings.py](lib/agent_settings.py) | **Agents-Seite**: welche Prompts und Parameter es je Agent gibt (`AGENTS`), Änderungen aus der App, Prüfung der Platzhalter |
| [lib/tool_repair.py](lib/tool_repair.py) | repariert abgebrochene Tool-Aufrufe des Modells |

### Daten und Berechnungen (ohne Sprachmodell)

| Datei | Inhalt |
|---|---|
| [lib/quarterly_data.py](lib/quarterly_data.py) | Quartalszahlen, Scorecards, 8-K-Pressemitteilungen und 10-Q von SEC EDGAR, Thesen-Protokoll |
| [lib/portfolio_engine.py](lib/portfolio_engine.py) | Portfolio einlesen, Risiko, Optimierung, Backtest |
| [lib/performance.py](lib/performance.py) | echte Performance aus Transaktionen (Depotwert, TWR/MWR, Benchmark mit gleichen Zahlungen) |
| [lib/transactions.py](lib/transactions.py) | Broker-Exporte einlesen (Trade Republic, Scalable, Smartbroker), ISIN → Ticker |
| [lib/valuation_data.py](lib/valuation_data.py) | Reverse DCF, Quality Scores, Peers für die Firmenseite |
| [lib/kpi_history.py](lib/kpi_history.py) | KPI-Verlauf aus allen Earnings Reviews |
| [lib/dividends.py](lib/dividends.py), [lib/etf_lookthrough.py](lib/etf_lookthrough.py) | Dividendenkalender, ETF-Durchschau und Welt-ETF-Vergleich |
| [lib/events.py](lib/events.py), [lib/market_strip.py](lib/market_strip.py) | Termine; Index-Leiste im Header |
| [lib/insights.py](lib/insights.py), [lib/news_tools.py](lib/news_tools.py) | Insights-Quellen (Banken, YouTube, Podcasts); Finnhub-News |
| [lib/peer_tools.py](lib/peer_tools.py), [lib/outlook_tools.py](lib/outlook_tools.py), [lib/tenk_search.py](lib/tenk_search.py) | Werkzeuge für den Annual-Report-Agenten |

### Daten für die App-Seiten

| Datei | Inhalt |
|---|---|
| [lib/home_data.py](lib/home_data.py) | sammelt alles für Overview, Portfolio, News und Brief |
| [lib/company_data.py](lib/company_data.py) | Firmenseite und Report-Archiv |
| [lib/html_site.py](lib/html_site.py) | statische HTML-Seiten (Archiv, Faktencheck-Ansicht) |
| [lib/action_state.py](lib/action_state.py), [lib/watchlist.py](lib/watchlist.py), [lib/labeling.py](lib/labeling.py) | Erledigt/Gesehen-Status, Watchlist, Labeln der Stichprobe |

---

## 5. Wo Ergebnisse gespeichert werden

| Was | Wo | In Git? |
|---|---|---|
| Annual Reports je Firma (PDF, `*_build_args.json` = alle Texte, `*_factcheck.json`) | `reports/<TICKER>_<JAHR>_<modell>_pipeline/` | ja |
| Earnings Reviews | `reports/<TICKER>_earnings_multi_<modell>/` | ja |
| Thesis Books / Quarter Records | `reports/thesis_books/`, `reports/quarter_records/<TICKER>/` | ja |
| Thesen-Protokoll | `reports/thesis_logs/` | ja |
| Archiv aller früheren Reports | `reports/archive/` | ja |
| Portfolio Review, Weekly Brief, News-Digest (PDF) | `reports/portfolio_*/`, `reports/brief_*/`, `reports/news_*/` | **nein** (privat) |
| Portfolio-Dashboard, Brief-Daten, Kurse, Bewertungsdaten, App-Läufe, Kosten, Einstellungen | `research/` (z. B. `portfolio_dashboard.json`, `briefs/`, `valuation/`, `app_runs/`, `pipeline_runs/`, `ui_settings.json`) | **nein** |
| Gespeicherte Portfolios und ihre Arbeitsbereiche | `research/portfolios/` | **nein** |
| Eigene Prompt-Änderungen, Parameter, Modell je Agent | `research/agent_settings.json` | **nein** |
| Ausgaben der Tools (Log → Tools) | `research/tool_runs/` | **nein** |
| News-Speicher | `news/` | **nein** |
| Prognosen | `forecasts/` | ja |
| Evaluation (Bericht) | `eval/` (`summary.md`, Grafiken) | teilweise |
| Eigene Broker-Exporte | `portfolios/traderepublic.csv`, `ScalableCapital.csv`, `Smartbroker*.csv` | **nein** |
| Musterportfolios (Valley Forge, Big Tech) | `portfolios/sample_*.csv` | ja |
| API-Schlüssel | `finrobot_autogen/config_api_keys`, `OAI_CONFIG_LIST` | **nein** |

---

## 6. Eigene Änderungen in der FinRobot-Bibliothek (`finrobot_autogen/finrobot/`)

| Datei | Was wir dort gebaut haben |
|---|---|
| `functional/fact_check.py` | **Faktencheck** (Zahlen extrahieren, in Quellen suchen, Kontextwörter) |
| `functional/outlook.py` | Konsens, Liquidität, Reverse DCF, implizite Rendite, Quality Scores |
| `functional/reportlab.py` | PDF-Layout des Annual Reports (`build_annual_report`) |
| `data_source/edgar_sections.py` | 10-K/10-Q-Abschnitte selbst von SEC EDGAR (Ersatz für sec-api) |
| `data_source/annual_20f.py` | ausländische Emittenten (20-F) |

---

## 7. Skripte und Doppelklick-Dateien

| Datei | Wofür |
|---|---|
| `Start BLUMBÖRG.bat` | App starten (auch über die Desktop-Verknüpfung) |
| `Desktop-Verknuepfung erstellen.bat` | Verknüpfung mit Logo anlegen |
| `Test App.bat` | öffnet jede Seite der App und meldet Abstürze ([scripts/test_app.py](scripts/test_app.py)) |
| `Musterdepot 13F bauen.bat` | Valley-Forge-Musterdepot aus 13F-Meldungen ([scripts/build_13f_portfolio.py](scripts/build_13f_portfolio.py)) |
| [scripts/run_app_pipeline.py](scripts/run_app_pipeline.py) | der Hintergrundlauf, den „Start analysis“ startet |
| [scripts/run_scheduled.py](scripts/run_scheduled.py) | der tägliche Automatik-Lauf |
| [scripts/score_forecasts.py](scripts/score_forecasts.py) | Prognosen nach einer Woche auswerten |
| [scripts/eval_summary.py](scripts/eval_summary.py), [scripts/eval_report.py](scripts/eval_report.py) | Evaluation zusammenfassen (Bericht) |
| [scripts/run_eval.py](scripts/run_eval.py), [scripts/run_baseline.py](scripts/run_baseline.py) | Evaluationsläufe, Baseline mit einfachem Prompt |
| [scripts/factcheck_fpr.py](scripts/factcheck_fpr.py) | wie oft der Faktencheck sich irrt |
| [scripts/compare_sec_api.py](scripts/compare_sec_api.py) | eigene SEC-Zerlegung gegen sec-api |

---

## 8. Häufige Fragen

- **„Ich will einen Prompt ändern“** → in der App unter *Agents* (Prompts, Zusatzanweisungen, Parameter, Modell; Versionen und Reset). Der Standardtext steht weiter im Code (Tabelle in Abschnitt 4); Änderungen aus der App liegen in `research/agent_settings.json`.
- **„Ich will ein Skript ausführen“** → in der App unter *Log → Tools* (Prognosen auswerten, Evaluation, 13F-Musterdepot, App-Test …).
- **„Wo liegen meine Portfolios?“** → Liste in `research/portfolios/index.json`, je Portfolio ein Arbeitsbereich `research/portfolios/<id>/ws/` (Brief, Review, Dashboard, News-Digest). Firmen-Reports sind für alle Portfolios dieselben.
- **„Warum steht eine Position auf Decide?“** → Regeln in `collect()` in [lib/brief_agent.py](lib/brief_agent.py).
- **„Was kostet ein Lauf, und was läuft wann?“** → `EST` in [lib/app_backend.py](lib/app_backend.py), `plan()` in [lib/pipeline.py](lib/pipeline.py).
- **„Wo kommt die Zahl X her?“** → in der App über die Zahl fahren (Faktencheck), oder `*_factcheck.json` im Report-Ordner.
- **„Wo ist das Design?“** → CSS oben in [app/app.py](app/app.py) (Header, Sidebar) und `CSS` in [app/home_view.py](app/home_view.py) (Karten, Farben).
