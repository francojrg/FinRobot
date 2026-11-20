"""
Wertet die Vorhersagen des Forecasters aus (forecasts/forecast_log.csv), sobald eine Woche vergangen ist.

Ausfuehren (aus dem FinRobot-Ordner):
    python ai_in_finance/scripts/score_forecasts.py

Je Vorhersage: Kurs am Prognosetag vs. Schlusskurs 5 Handelstage spaeter.
Kennzahlen: Trefferquote der Richtung, mittlerer absoluter Fehler (in Prozentpunkten, gegen die Mitte der
vorhergesagten Spanne), Anteil der Bewegungen innerhalb der Spanne, und zum Vergleich der S&P 500 (^GSPC).
Ergebnis: forecasts/forecast_scores.csv
"""
import csv
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

AIF = Path(__file__).resolve().parents[1]
LOG = AIF / "forecasts" / "forecast_log.csv"
OUT = AIF / "forecasts" / "forecast_scores.csv"


def realized(ticker, start, days=5):
    h = yf.Ticker(ticker).history(start=start, end=(datetime.fromisoformat(start) + timedelta(days=14)).date().isoformat())
    closes = h["Close"].dropna()
    if len(closes) <= days:
        return None
    return float(closes.iloc[days] / closes.iloc[0] - 1) * 100, str(closes.index[days].date())


def main():
    if not LOG.exists():
        print("Noch keine Vorhersagen (forecast_log.csv fehlt).")
        return
    rows = list(csv.DictReader(open(LOG, encoding="utf-8")))
    scored = []
    for r in rows:
        if not r.get("close_date"):
            continue
        res = realized(r["ticker"], r["close_date"])
        if res is None:
            continue
        move, end_date = res
        bench = realized("^GSPC", r["close_date"])
        mid = float(r["mid_pct"]) if r.get("mid_pct") not in (None, "", "None") else None
        lo = float(r["low_pct"]) if r.get("low_pct") not in (None, "", "None") else None
        hi = float(r["high_pct"]) if r.get("high_pct") not in (None, "", "None") else None
        sign = {"UP": 1, "DOWN": -1, "FLAT": 0}.get(r.get("direction"), None)
        hit = None if sign is None else (sign == (1 if move > 0 else -1 if move < 0 else 0))
        in_range = None
        if sign and lo is not None and hi is not None:
            in_range = lo <= sign * move <= hi
        scored.append({**r, "end_date": end_date, "realized_pct": round(move, 2),
                       "sp500_pct": None if bench is None else round(bench[0], 2),
                       "direction_hit": hit, "abs_error_pp": None if mid is None else round(abs(move - mid), 2),
                       "within_range": in_range})
    if not scored:
        print("Noch keine Vorhersage ist eine Woche alt.")
        return
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(scored[0]))
        w.writeheader()
        w.writerows(scored)
    hits = [s["direction_hit"] for s in scored if s["direction_hit"] is not None]
    errs = [s["abs_error_pp"] for s in scored if s["abs_error_pp"] is not None]
    inr = [s["within_range"] for s in scored if s["within_range"] is not None]
    print(f"Ausgewertet: {len(scored)} Vorhersagen")
    if hits:
        print(f"Richtung getroffen: {sum(hits)}/{len(hits)} ({sum(hits) / len(hits) * 100:.0f}%)")
    if errs:
        print(f"Mittlerer absoluter Fehler: {sum(errs) / len(errs):.2f} Prozentpunkte")
    if inr:
        print(f"Bewegung innerhalb der Spanne: {sum(inr)}/{len(inr)}")
    print(f"Details: {OUT}")


if __name__ == "__main__":
    main()
