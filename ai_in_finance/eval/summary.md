# Evaluation - Zusammenfassung

Automatisch erzeugt von `scripts/eval_report.py`. Trefferquote = Anteil der Zahlen im Text, die der Faktencheck in den Quellen findet. 'bereinigt' = ohne Pseudo-Zahlen wie das '10' in '10-K'.

## 1. Agent gegen Baseline und Wirkung der Selbstkorrektur (Annual Reports)

| Firma | Variante | Zahlen | Trefferquote | bereinigt | Runde 1 | Pseudo-Zahlen | Sek. | USD |
|---|---|---|---|---|---|---|---|---|
| AMZN | baseline (plain prompt) | 36 | 80.6% | 80.6% | - | 0 | - | - |
| AMZN | agent, no self-correction | 180 | 91.1% | 91.1% | - | 0 | 269.2 | 0.0502 |
| AMZN | agent, with self-correction | 153 | 100.0% | 100.0% | 90.6% | 0 | 235.3 | 0.0367 |
| AMZN | agent (notebook/pipeline) | 194 | 91.2% | 90.8% | 91.2% | 9 | - | - |
| GOOG | baseline (plain prompt) | 54 | 64.8% | 64.8% | - | 0 | - | - |
| GOOG | agent, no self-correction | 185 | 94.6% | 94.6% | - | 0 | 257.6 | 0.0448 |
| GOOG | agent, with self-correction | 208 | 99.5% | 99.5% | 95.2% | 0 | 300.4 | 0.0531 |
| GOOG | agent (notebook/pipeline) | 210 | 96.2% | 96.0% | 96.2% | 9 | - | - |
| MA | baseline (plain prompt) | 37 | 78.4% | 78.4% | - | 0 | - | - |
| MA | agent, no self-correction | 151 | 94.7% | 94.7% | - | 0 | 184.9 | 0.033 |
| MA | agent, with self-correction | 157 | 100.0% | 100.0% | 98.1% | 0 | 260.3 | 0.0706 |
| MA | agent (notebook/pipeline) | 175 | 100.0% | 100.0% | 96.5% | 9 | - | - |
| MSFT | agent (notebook/pipeline) | 208 | 94.7% | 94.5% | 92.8% | 8 | - | - |
| RBRK | agent, no self-correction | 165 | 98.2% | 98.1% | 98.2% | 4 | 365.6 | 0.1283 |
| RBRK | agent, with self-correction | 163 | 100.0% | 100.0% | 96.3% | 6 | 328.6 | 0.108 |
| RBRK | agent (notebook/pipeline) | 151 | 96.7% | 96.5% | 95.3% | 8 | - | - |
| RBRK | agent (notebook/pipeline) | 199 | 97.0% | 96.9% | 96.5% | 6 | - | - |
| RKLB | agent, no self-correction | 164 | 98.2% | 98.1% | - | 4 | 222.1 | 0.0665 |
| RKLB | agent, with self-correction | 141 | 100.0% | 100.0% | 97.2% | 6 | 229.5 | 0.0458 |
| RKLB | agent (notebook/pipeline) | 141 | 98.6% | 98.6% | - | 1 | - | - |
| TMO | agent (notebook/pipeline) | 215 | 99.5% | 99.5% | 97.7% | 10 | - | - |

**Mittelwerte je Variante:**

| Variante | Reports | Trefferquote | bereinigt | Runde 1 |
|---|---|---|---|---|
| baseline (plain prompt) | 3 | 74.6% | 74.6% | - |
| agent, no self-correction | 5 | 95.4% | 95.3% | 98.2% |
| agent, with self-correction | 5 | 99.9% | 99.9% | 95.5% |
| agent (notebook/pipeline) | 8 | 96.7% | 96.6% | 95.2% |

## 2. Pruefung des Pruefers (verfaelschte Zahlen)

| Report | Zahlen offline | Falsch-positiv-Rate | Erkennungsrate | Geld | Prozent | sonstige |
|---|---|---|---|---|---|---|
| AMZN_2025_claude-haiku-5.5 | 154 | 41.0% | 59.0% | 16.4% | 59.2% | 72.5% |
| AMZN_2025_claude-haiku-5.5_eval | 153 | 38.4% | 61.6% | 15.3% | 62.8% | 44.6% |
| AMZN_2025_claude-haiku-5.5_eval_nosc | 164 | 40.5% | 59.5% | 19.8% | 60.2% | 55.8% |
| GOOG_2025_claude-haiku-5.5 | 116 | 37.2% | 62.8% | 18.3% | 40.9% | 93.3% |
| GOOG_2025_claude-haiku-5.5_eval | 207 | 47.2% | 52.8% | 24.0% | 73.8% | 54.0% |
| GOOG_2025_claude-haiku-5.5_eval_nosc | 175 | 46.6% | 53.4% | 23.3% | 66.8% | 56.8% |
| MA_2025_claude-haiku-5.5 | 121 | 56.9% | 43.1% | 20.6% | 69.1% | 75.8% |
| MA_2025_claude-haiku-5.5_eval | 157 | 51.8% | 48.2% | 31.6% | 64.4% | 41.7% |
| MA_2025_claude-haiku-5.5_eval_nosc | 143 | 52.8% | 47.2% | 23.3% | 69.8% | 47.2% |
| MSFT_2026_claude-haiku-5.5_pipeline | 137 | 42.4% | 57.6% | 12.0% | 58.6% | 67.4% |
| RBRK_2025_claude-haiku-5.5 | 112 | 36.3% | 63.7% | 23.9% | 32.9% | 83.6% |
| RBRK_2026_claude-haiku-5.5_eval | 163 | 47.5% | 52.5% | 29.2% | 60.7% | 68.1% |
| RBRK_2026_claude-haiku-5.5_eval_nosc | 162 | 47.6% | 52.4% | 31.7% | 58.5% | 66.2% |
| RBRK_2026_claude-haiku-5.5_pipeline | 156 | 46.0% | 54.0% | 26.9% | 51.4% | 79.0% |
| RKLB_2025_claude-haiku-5.5 | 124 | 43.8% | 56.2% | 23.1% | 48.1% | 71.6% |
| RKLB_2025_claude-haiku-5.5_eval | 141 | 47.5% | 52.5% | 29.4% | 53.1% | 79.2% |
| RKLB_2025_claude-haiku-5.5_eval_nosc | 161 | 45.8% | 54.2% | 26.0% | 53.9% | 75.7% |
| TMO_2025_claude-haiku-5.5_pipeline | 141 | 46.4% | 53.6% | 14.3% | 57.2% | 89.4% |

Lesart: Eine Falsch-positiv-Rate von 35 % heisst, dass jede dritte absichtlich falsche Zahl trotzdem als belegt gilt. Untergrenze, da offline weniger Quellen geprueft werden.

## 3. Manuelle Stichprobe

Noch nicht gelabelt (693 Zahlen in eval/manual_review_sample.csv).

## 4. Kosten und Laufzeit je Agent (Pipeline-Laeufe)

| Agent | Laeufe | erfolgreich | Sek. (Mittel) | USD (Mittel) | USD (Summe) |
|---|---|---|---|---|---|
| annual_report | 3 | 3 | 449 | 0.104 | 0.311 |
| brief | 3 | 3 | 36 | 0.009 | 0.028 |
| committee | 2 | 1 | 3300 | 1.283 | 2.566 |
| earnings_review | 16 | 16 | 152 | 0.037 | 0.587 |
| forecast | 6 | 6 | 21 | 0.011 | 0.068 |
| news | 1 | 1 | 186 | 0.043 | 0.043 |
| portfolio | 8 | 8 | 74 | 0.008 | 0.064 |
