"""
KPI-Verlauf je Firma: die firmenspezifischen Kennzahlen aus allen Earnings Reviews (aktuell und Archiv) als
Zeitreihe. Jedes Review liefert die Quartale seit dem 10-K und die Vorjahresquartale; spaetere Reviews
ueberschreiben fruehere Werte desselben Quartals. Kennzahlen werden ueber den normalisierten Namen
zusammengefuehrt (Gross-/Kleinschreibung, Satzzeichen).
"""
import glob
import json
import os
import re
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
REPORTS = AIF / "reports"


def _norm(name):
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _unit(unit):
    """Einheit vereinheitlichen: Milliarden werden zu Millionen (Faktor 1000), damit Reviews mit 'USD bn' und
    'USD mn' in eine Reihe passen. Rueckgabe: (faktor, einheit)."""
    u = str(unit or "")
    if re.search(r"(?i)\b(bn|billion|billions|b)\b", u):
        return 1000.0, re.sub(r"(?i)\b(bn|billion|billions|b)\b", "mn", u)
    if re.search(r"(?i)\b(million|millions|m)\b", u):
        return 1.0, re.sub(r"(?i)\b(million|millions|m)\b", "mn", u)
    return 1.0, u


def _q(label):
    """'Q3 FY2026' -> (2026, 3); sonst None."""
    m = re.search(r"Q([1-4])\s*FY\s*(\d{4})", str(label), re.I)
    return (int(m.group(2)), int(m.group(1))) if m else None


def _files(ticker):
    t = ticker.upper()
    pats = [REPORTS / f"{t}_earnings_multi_*" / "*_build_args.json",
            REPORTS / "archive" / t / f"{t}_earnings_*" / "*_build_args.json"]
    fs = [f for p in pats for f in glob.glob(str(p))]
    return sorted(set(fs), key=os.path.getmtime)


def history(ticker, min_points=3):
    """[{name, unit, good, points: [(label, value)], latest_yoy}] sortiert nach Anzahl Punkte."""
    series = {}
    for f in _files(ticker):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        kpis = d.get("company_kpis") or []
        if isinstance(kpis, str):
            try:
                kpis = json.loads(kpis)
            except Exception:
                kpis = []
        for k in kpis:
            if not isinstance(k, dict) or not k.get("name"):
                continue
            fac, unit = _unit(k.get("unit"))
            s = series.setdefault(_norm(k["name"]), {"name": k["name"], "unit": unit,
                                                     "good": k.get("good_direction") or "up", "vals": {}})
            if s["vals"] and unit != s["unit"]:
                s["vals"] = {}                         # andere Einheit (z. B. % statt USD): neue Reihe statt Mischung
            s["name"], s["unit"] = k["name"], unit
            for lab, v in (k.get("prior_values") or {}).items():
                q = _q(lab)
                if q and isinstance(v, (int, float)):
                    s["vals"][(q[0] - 1, q[1])] = float(v) * fac
            for lab, v in (k.get("values") or {}).items():
                q = _q(lab)
                if q and isinstance(v, (int, float)):
                    s["vals"][q] = float(v) * fac
    out = []
    for s in series.values():
        pts = sorted(s["vals"].items())
        if len(pts) < min_points:
            continue
        last = pts[-1]
        prev = s["vals"].get((last[0][0] - 1, last[0][1]))
        yoy = (last[1] / prev - 1) if prev not in (None, 0) else None
        out.append({"name": s["name"], "unit": s["unit"], "good": s["good"],
                    "points": [(f"Q{q} FY{y}", v) for (y, q), v in pts], "latest_yoy": yoy})
    return sorted(out, key=lambda x: -len(x["points"]))
