# BLUMBÖRG – Kurzanleitung

Research-Agenten für ein Aktienportfolio: Annual Reports (10-K/20-F), Thesis Tracker Quartal für Quartal, Earnings
Reviews, News, Portfolio Review und ein Weekly Brief mit dem Handlungsbedarf. Installation: siehe `INSTALLATION.md`.
Die Oberfläche ist Englisch; ein **(i)** neben einer Überschrift erklärt die Funktion beim Überfahren mit der Maus.
Keine Anlageberatung.

## Start
**`Start BLUMBÖRG.bat`** (oder die Desktop-Verknüpfung) öffnet die App im Browser. Oben die Index-Leiste (DAX, S&P 500,
MSCI World, EUR/USD, Gold, Bitcoin, Ether, US- und Bund-Renditen), links das **aktive Portfolio** – dort wechselt man
zwischen eigenen Portfolios und dem **DEMO-Depot** (Valley Forge, aus 13F-Meldungen nachgebaut). Kurse und Termine sind
live; alle Analysen zeigen den Stand des letzten Laufs.

## Seiten

**Today**
- **Overview** – Depotwert, Action needed (Kacheln mit Erledigt / Gesehen / Ausblenden und Notiz), Thesen-Bilanz,
  nächste Quartalszahlen, Kalender, wichtigste Meldungen, Weekly Brief als PDF oder mit Faktencheck.
- **News** – Woche im Überblick, Themen, Signale und Storylines je Titel, alle Meldungen; rechts Interesting Reads
  (Beta), Bank research und Podcasts/Videos (eigene Quellen unter „Manage sources“).

**Analysis**
- **Portfolio** – Depotwert und Wertentwicklung (1M bis Max), Positionen als Treemap und Allokation, Tabelle,
  Transaktionen, Dividenden, Watchlist.
- **Portfolio analysis** – Rendite gegen den MSCI ACWI, Beiträge, Struktur, Risiko, Optimierung mit Backtest (Beta),
  eigene Entscheidungen, Welt-ETF-Vergleich, ETF-Durchschau, Portfolio Review des Agenten.
- **Company research** – je Firma: Reports (PDF oder mit Faktencheck: grün gefunden, gelb anderer Zusammenhang, rot
  nicht gefunden), neueste Zahlen, Thesen, KPI-Charts mit YoY/QoQ, **Thesis tracker** (Meilensteine und Status je
  Quartal), **Reverse DCF** mit Reglern und KI-Basisfall, **Financial quality** (Piotroski, Altman, Beneish),
  **Peer comparison**, Earnings Preview (Beta). Unten „Rebuild reports“ und das Investment Committee (Beta).
- **Ask** (Beta) – Fragen an die eigenen Reports, Antworten mit Quellen und Faktencheck.

**System**
- **Setup and automation** – *Analysis*: Portfolio wählen (gespeichert, Datei oder Upload), Plan mit Dauer und Kosten,
  Start, Fortschritt. *Portfolios*: umbenennen, entfernen, zusammenfassen. *Automation*: tägliche Prüfung mit
  Monatsbudget; führt nur aus, was fällig ist.
- **Agents** – je Agent Zweck, Quellen, Ergebnis, Modell, Prompts, Zusatzanweisungen und Parameter; Versionen und Reset.
- **Log** – Läufe mit Kosten und Fehlern, Chat-Fragen, Evaluation (Stichprobe labeln), **Tools** (Skripte per Knopf).
- **Settings** – Setup-Guide mit allen Schlüsseln (Links, Test-Knöpfe), Modelle, Schriftgröße, Interessen.

## Was wann neu berechnet wird
| Schritt | neu, wenn … |
|---|---|
| Annual Report | ein neuerer 10-K/20-F vorliegt (oder per „Rebuild reports“) |
| Quarter Records (Thesis Tracker) | für ein Quartal seit dem 10-K noch kein Record existiert |
| Earnings Review | neue Quartalszahlen seit dem letzten Review |
| Prognose (Beta) | die letzte älter als 6 Tage ist |
| Earnings Preview (Beta) | Quartalszahlen in den nächsten 14 Tagen anstehen |
| News | die letzte Zusammenfassung älter als 6 Tage ist oder Titel fehlen |
| Portfolio Review, Brief | bei jedem Lauf |

Reports gehören zur Firma, nicht zum Portfolio: Wer das Portfolio wechselt oder Portfolios zusammenfasst, bekommt
vorhandene Reports sofort; Brief, Review und News-Digest werden je Portfolio gespeichert.

## Beta-Funktionen
Optimierung, Investment Committee, Ask, Prognosen, Earnings Preview und Interesting Reads sind als **Beta**
gekennzeichnet: vereinfachte Modelle bzw. Ergebnisse, die noch nicht systematisch ausgewertet sind.

## Datenschutz
Portfolio-Dateien, Uploads, Ergebnisse zum eigenen Depot, eigene Prompt-Änderungen und Schlüssel bleiben lokal und
sind von Git ausgeschlossen.
