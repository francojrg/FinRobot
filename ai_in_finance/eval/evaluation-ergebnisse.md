# Evaluation – Ergebnisse für den Bericht

Stand: 25.11.2026 (Kontextabgleich ergänzt) · Datenbasis: `eval/eval_results.csv`, `eval/fpr_results.csv`, Faktencheck-JSONs der Läufe vom 24.11.2026 (Claude Haiku 5.5 über OpenRouter, Temperatur 0,5, je ein Lauf pro Variante) · Abbildung: `eval_figure.png`

## Aufbau in einem Satz

Drei Varianten erstellen denselben Annual Report (Geschäftsjahr 2025) für Amazon, Alphabet und Mastercard: (1) Baseline mit einfachem Prompt ohne Tools, (2) Agent ohne Selbstkorrektur, (3) Agent mit Selbstkorrektur (SK: Faktencheck-Ergebnis geht einmal an den Agenten zurück, der den Report überarbeitet). Gemessen wird, welcher Anteil der Zahlen im Text sich in den Quellen (10-K, Finanztabellen, Marktdaten) wiederfindet, außerdem wie zuverlässig der Faktencheck selbst ist (Falsch-positiv-Test).

## Tabelle 1 – Trefferquote je Variante

| Firma | Baseline | Agent ohne SK | Agent mit SK, Runde 1 | Agent mit SK, final |
|---|---|---|---|---|
| AMZN | 80,6 % (29/36) | 91,1 % (164/180) | 90,6 % (145/160) | 100,0 % (153/153) |
| GOOG | 64,8 % (35/54) | 94,6 % (175/185) | 95,2 % (199/209) | 99,5 % (207/208) |
| MA | 78,4 % (29/37) | 94,7 % (143/151) | 98,1 % (155/158) | 100,0 % (157/157) |
| **Mittel** | **74,6 %** (42 Zahlen) | **93,5 %** (172 Zahlen) | **94,6 %** (176 Zahlen) | **99,8 %** (173 Zahlen) |

Ergänzend, mit älterer Faktencheck-Version gemessen (23.11.): RKLB 98,2 % → 100 % (Runde 1: 97,2 %), RBRK 98,2 % → 100 % (Runde 1: 96,3 %). Über alle fünf Firmen: ohne SK 95,4 %, mit SK 99,9 %.

**Lesart:**
- Tools und Datenzugang sind der größte Hebel: +19 Prozentpunkte gegenüber der Baseline, bei rund viermal so vielen Zahlen pro Report.
- Runde 1 mit SK (94,6 %) und der Lauf ohne SK (93,5 %) liegen gleichauf. Die Varianten unterscheiden sich also erst durch die Überarbeitung, nicht durch den Prompt.
- Die Selbstkorrektur hebt die Quote um etwa 5 Prozentpunkte auf nahezu 100 %.

## Tabelle 2 – Was die Selbstkorrektur tatsächlich ändert

| Firma | Nicht belegte Zahlen in Runde 1 | danach aus dem Text verschwunden | weiterhin im Text | Zahlen Runde 1 → final |
|---|---|---|---|---|
| AMZN | 15 | 15 | 0 | 160 → 153 |
| GOOG | 10 | 9 | 1 | 209 → 208 |
| MA | 3 | 3 | 0 | 158 → 157 |
| **Summe** | **28** | **27** | **1** | 527 → 518 |

**Lesart:** Die SK „findet“ keine Belege nachträglich, sie entfernt oder ersetzt nicht belegte Zahlen. Betroffen sind vor allem selbst berechnete Prozentwerte (Margen, Anteile, Wachstumsraten), die nicht wörtlich in den Quellen stehen. Ein Teil davon dürfte rechnerisch korrekt gewesen sein (Beispiel: eine operative Marge, die sich aus zwei belegten Beträgen ergibt). Die Trefferquote misst daher **Belegbarkeit, nicht Richtigkeit**. Klären lässt sich das nur mit der manuellen Stichprobe.

## Tabelle 3 – Prüfung des Prüfers (Falsch-positiv-Rate), mit und ohne Kontextabgleich

Methode: Jede als belegt gewertete Zahl wird 20-mal um 10–50 % verfälscht und erneut geprüft. FPR = Anteil der verfälschten Zahlen, die trotzdem als belegt gelten. Offline gemessen (Ressourcen-Dateien im Report-Ordner), daher eine Untergrenze. Basis: 6 Agent-Reports (AMZN, GOOG, MA, je mit und ohne SK).

Korrektur am 25.11.: Bisher zählte die vom Agenten mitgeschriebene `run_log.txt` als Quelle. Sie enthält aber die Report-Entwürfe selbst. Ohne sie sinkt die FPR des reinen Zahlenabgleichs von 46 % auf 39 %.

| Zahlentyp | nur Zahl (bisher) | Zahl + Kontext (neu) | mit Kontext belegt (von per Zahl belegt) |
|---|---|---|---|
| Geldbeträge | 20 % | 20 % (keine Kontextprüfung) | 323 von 323 |
| Prozentwerte | 53 % | **23 %** | 197 von 306 (64 %) |
| sonstige Zahlen | 53 % | **17 %** | 35 von 60 |
| **gesamt** | **39 %** | **23 %** | 558 von 706 |

Kontextabgleich: Neben der Zahl muss auch ein aussagekräftiges Wort aus dem Report-Satz in der Nähe der Zahl in der Quelle stehen. Dafür reicht ein seltenes Wort (z. B. „cloud“, „value-added“) oder zwei gemeinsame Wörter (z. B. „revenue“ plus Veränderungswort wie „up 15 %“). Wie selten ein Wort ist, wird je Quelle gemessen (log N/df über alle Zahlen-Fundstellen). Synonyme wie sales/revenue oder profit/income werden zusammengefasst. Die Parameter wurden an diesen 6 Reports gewählt (Fenster 8 Wörter, Schwellen 1,4 / 2,2 / 1,8). Sie sind also nicht an unabhängigen Daten validiert.

**Lesart:**
- Der Kontext halbiert die Fehlerquote bei Prozentwerten und sonstigen Zahlen. Geldbeträge sind ohnehin trennscharf.
- Preis: Ein Drittel der per Zahl belegten Prozentwerte gilt nur noch als „Zahl gefunden, Zusammenhang abweichend“. Eine Stichprobe dieser Fälle zeigt überwiegend echte Fehlzuordnungen des alten Checks. Beispiele: „Cloud operating margin 14 %“ war belegt durch „R&D in % vom Umsatz 14 %“, „11,0 % WACC“ durch „Cost of revenues +11 %“. Daneben stehen extern berechnete Werte (Reverse DCF, Peer-ROIC), die offline nicht vorliegen.
- Bleibende Schwäche sind Tabellen mit mehreren Jahresspalten. Eine Zahl aus dem Vorjahr derselben Zeile gilt weiter als belegt, weil Wort und Zahl passen. Lösen ließe sich das nur, indem man die Tabellen parst.
- In der App erscheint das als dritte Stufe: grün (Zahl und Kontext), gelb (nur Zahl), rot (nicht gefunden). Der Tooltip zeigt die Textstelle mit markierter Zahl und den gemeinsamen Wörtern. Die Trefferquote für die Selbstkorrektur der Agenten bleibt der reine Zahlenabgleich, die strengere Quote steht zusätzlich im Faktencheck-JSON (`context_match_rate`).
- Für die manuelle Stichprobe zeigt die Label-Ansicht beide Gruppen getrennt („Kontext passt: richtig“ gegen „Nur Zahl: richtig“). Damit lässt sich prüfen, ob gelb wirklich häufiger falsch ist.

## Tabelle 4 – Kosten und Laufzeit

| | Agent ohne SK | Agent mit SK | Differenz |
|---|---|---|---|
| Laufzeit (Mittel) | 237 s | 265 s | +12 % |
| Kosten (Mittel) | 0,043 USD | 0,054 USD | +25 % |
| Spanne Kosten | 0,033–0,050 USD | 0,037–0,071 USD | |
| Tool-Fehler (Summe) | 6 | 6 | 0 |
| Build-Versuche | je 2 | je 3 | +1 |

Kosten je Agent im Pipeline-Betrieb (Mittel pro Lauf): Annual Report 0,10 USD (449 s), Earnings Review 0,04 USD (152 s, 16 Läufe), News 0,04 USD, Forecast 0,01 USD, Portfolio 0,01 USD, Brief 0,01 USD, Investment Committee 1,28 USD (55 min, 1 von 2 Läufen erfolgreich). Pro Firma kosten Annual Report und ein Earnings Review zusammen rund 0,15 USD; das Committee ist der einzige teure Baustein.

## Faktencheck des Brief-Agenten (Entwicklungsstufen)

| Stufe | belegt / geprüft |
|---|---|
| erste Version | 81 / 90 |
| Einheiten in Quellen erkannt (bn/mn) | 90 / 90 |
| Pseudo-Zahlen ausgeblendet (Datumsangaben, Formularnummern) | 83 / 83 |

## Einschränkungen (für den Methodenteil)

- Kleine Stichprobe: drei Firmen (plus zwei mit älterer Check-Version), je ein Lauf. Bei Temperatur 0,5 schwanken Zahlenanzahl und Kosten deutlich (z. B. 0,037 vs. 0,071 USD mit SK).
- Die Baseline schreibt nur ein Viertel so viele Zahlen. Ihre Trefferquote ist deshalb nicht direkt vergleichbar mit der des Agenten.
- Trefferquote ≠ Richtigkeit (siehe Tabelle 2 und 3). Die manuelle Stichprobe (`eval/manual_review_sample.csv`) ist noch nicht gelabelt.
- Die Prognosegüte des Forecasters (`score_forecasts.py`) lässt sich frühestens am 27.11. auswerten.

## Kernaussagen (Vorschlag für Abstract/Fazit)

1. Datenzugang über Tools senkt den Anteil nicht belegter Zahlen von etwa 25 % auf 5–7 %.
2. Die Selbstkorrektur bringt die Belegquote auf nahezu 100 %, und zwar durch Entfernen statt durch Nachbelegen. Sie kostet etwa 25 % mehr.
3. Der reine Zahlenabgleich ist das schwächste Glied: 39 % der verfälschten Zahlen rutschen durch, bei Prozentwerten mehr als die Hälfte. Ein Kontextabgleich (Zahl plus passende Wörter in der Quelle) senkt das auf 23 %, kostet aber ein Drittel der per Zahl belegten Prozentwerte, die meisten davon Fehlzuordnungen des alten Checks.
