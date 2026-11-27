# BLUMBÖRG – Kurzanleitung

Research-Agenten für ein Aktienportfolio: Annual Reports (10-K/20-F), Earnings Reviews je Quartal, News, Portfolio
Review und ein Brief mit dem Handlungsbedarf. Installation: siehe `INSTALLATION.md`. Keine Anlageberatung.

## Start
**`Start BLUMBÖRG.bat`** im Ordner `ai_in_finance` doppelklicken. Die App öffnet sich im Browser. Kurse und Termine
sind live; alle Analysen zeigen den Stand des letzten Laufs.

## Navigation

**Heute**
- **Überblick** – Depotwert mit Tagesänderung, offener Handlungsbedarf, Thesen-Bilanz, nächste Quartalszahlen; darüber
  Schlagzeile und Kurzfassung des Briefs (als **PDF** oder **mit Faktencheck**). Links der Handlungsbedarf als Kacheln
  (Status, Gewicht, Auslöser, Thesen-Punkte, Zahl der Meldungen); Klick auf eine Kachel zeigt Begründung, Thesen und Auslöser; **Erledigt / Gesehen / Ausblenden** mit Notiz. Ein Punkt kommt
  wieder, sobald ein neuer Auslöser dazukommt; die Notizen liest der Brief-Agent beim nächsten Brief mit.
  Rechts Termine, wichtigste Meldungen und neue Insights.
- **News** – rechts **Interesting Reads** (Beta: die KI wählt einmal pro Woche oder auf Knopfdruck 5–7 Beiträge,
  Podcasts und Videos passend zu Interessen, Depot und Watchlist; ein Modellaufruf, etwa 1–3 Cent), **Research der
  Banken** (neuester Beitrag je Quelle mit Erscheinungsdatum) und **Podcasts und Videos** (neue Folgen deiner Kanäle);
  unter „Quellen verwalten“ eigene Quellen eintragen. Links Woche im Überblick, Signale und Storylines je Titel
  (Auffälligkeiten unter jeder Zeile), alle Meldungen mit Quelle und Filter.

**Analyse**
- **Depot** – der tägliche Blick: Depotwert, heute, seit Jahresbeginn, 1 Jahr, Gewinn gesamt; Wertentwicklung (1M bis
  Max), Positionen als Kacheln und Allokation, Tabelle aller Positionen, **Transaktionen** (alle Buchungen, filterbar; nur
  mit Transaktionsdatei), **Dividenden** (erwartete Zahlungen der nächsten 12 Monate, Rendite je Titel, Ex-Tage) und die
  **Watchlist**.
- **Portfolio-Analyse** – Rendite gegen den MSCI ACWI (zeit- und geldgewichtet, Kalenderjahre), Beiträge je Titel,
  Struktur, Risiko, Stresstests und Optimierung mit Backtest (Beta), eigene Entscheidungen und Lernkurve,
  **ETF-Durchschau** (Top-10 und Sektoren der ETFs, Überschneidung mit Einzeltiteln) und der **Portfolio Review** des
  Agenten als Kurzfassung mit PDF.
- **Firmen-Research** – Dashboard je Titel: oben die Reports (öffnen sich direkt darunter), dann neueste Zahlen, Thesen,
  Termine, News und die KPIs je Quartal über alle Earnings Reviews. Reports öffnen sich als **PDF** oder
  **mit Faktencheck**: grün = Zahl und Zusammenhang in den Quellen gefunden, gelb = Zahl gefunden, aber in anderem
  Zusammenhang, rot = nicht gefunden; Maus über eine Zahl zeigt Quelle und Textstelle. Unten **„Reports neu
  erstellen“** und **„Committee starten“** (Beta). Darunter der **KPI-Verlauf** (firmenspezifische Kennzahlen aus allen
  Earnings Reviews) und vor Quartalszahlen die **Earnings Preview** (Beta): worauf achten, Bull/Base/Bear-Szenario.
- **Fragen** (Beta) – Fragen an die eigenen Reports, Antworten mit Quellen und Faktencheck.

**System**
- **Einrichtung und Automatik** – Reiter **Analyse**: Portfolio wählen oder hochladen, Umfang, Plan, Start, Fortschritt
  und „Lauf abbrechen“. Reiter **Automatik**: tägliche Prüfung zu einer Uhrzeit mit Monatsbudget; führt nur aus, was
  fällig ist (neue SEC-Einreichungen, News, wöchentlich Prognose, Portfolio Review und Brief).
- **Protokoll** – Läufe mit Kosten und Fehlern, Evaluation, Stichprobe labeln.
- **Einstellungen** – Schriftgröße (Klein bis Sehr groß), deine Interessen für die Lese-Auswahl, Schlüssel, Modelle.

## Was wann neu berechnet wird
| Schritt | neu, wenn … |
|---|---|
| Annual Report | ein neuerer 10-K/20-F vorliegt (oder per „Reports neu erstellen“) |
| Earnings Review | neue Quartalszahlen seit dem letzten Review |
| Prognose (Beta) | die letzte älter als 6 Tage ist |
| Earnings Preview (Beta) | Quartalszahlen in den nächsten 14 Tagen anstehen und es für den Termin noch keine gibt |
| News | die letzte Zusammenfassung älter als 6 Tage ist oder neue Titel fehlen |
| Portfolio Review, Brief | bei jedem Lauf |

Reports hängen am Ticker, nicht am Portfolio: Wer das Portfolio wechselt, bekommt vorhandene Reports sofort.

## Beta-Funktionen
Stresstests, Optimierung, Investment Committee, Fragen, Prognosen und Earnings Preview sind als **Beta** gekennzeichnet: vereinfachte
Modelle bzw. Ergebnisse, die noch nicht systematisch ausgewertet sind.

## Datenschutz
Portfolio-Dateien, Uploads, Ergebnisse zum eigenen Depot und Schlüssel bleiben lokal und sind von Git ausgeschlossen.
