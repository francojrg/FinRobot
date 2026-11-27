"""
Pruefung des Pruefers: Wie oft haelt der Faktencheck eine FALSCHE Zahl fuer belegt?

Methode: Jede Zahl, die im Report als "gefunden" gilt und auch gegen die Ressourcen im Report-Ordner gefunden wird, wird
20-mal um 10-50 % nach oben oder unten verfaelscht (gleiche Art, Einheit und Nachkommastellen) und erneut mit
check_claim geprueft. Falsch-positiv-Rate (FPR) = Anteil der verfaelschten Zahlen, die trotzdem als gefunden gelten.
Erkennungsrate = 1 - FPR.

Zwei Modi (25.11.2026): "nur Zahl" (bisheriger Check) und "Kontext" (Zahl UND passende Woerter in der Naehe, siehe
fact_check.CONTEXT_KINDS). Fuer den Kontextmodus zaehlen nur Zahlen, die auch unverfaelscht mit Kontext belegt sind;
ctx_kept zeigt, wie viele der per Zahl belegten Angaben das sind. Die vom Agenten mitgeschriebene run_log.txt zaehlt
nicht als Quelle (sie enthaelt die Entwuerfe des Reports selbst).

Quellen offline: die Ressourcen-Dateien im Report-Ordner (10-K-Abschnitte und Finanztabellen, ohne die vom Modell
geschriebenen *_analysis.txt). Der echte Check nutzt mehr Quellen (Yahoo, Konsens, Peers) -> diese FPR ist eine
Untergrenze. Kein API-Aufruf.

Ausfuehren (aus dem FinRobot-Ordner):
    python ai_in_finance/scripts/factcheck_fpr.py                       # alle Annual-Report-Ordner
    python ai_in_finance/scripts/factcheck_fpr.py --reports GOOG_2025_claude-haiku-5.5 RKLB_2025_claude-haiku-5.5_eval
Ergebnis: ai_in_finance/eval/fpr_results.csv
"""
import argparse
import copy
import csv
import glob
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIF = ROOT / "ai_in_finance"
sys.path.insert(0, str(ROOT / "finrobot_autogen"))


def perturb(c, f):
    from finrobot.functional.fact_check import _decimals
    d = c["decimals"]
    v = round(c["value"] * f, d)
    if v == c["value"]:
        v = round(c["value"] * (f + (0.1 if f > 1 else -0.1)), d)
    c2 = copy.deepcopy(c)
    c2["value"] = v
    if c2.get("money_mn") is not None and c["value"]:
        c2["money_mn"] = c["money_mn"] * v / c["value"]
    c2["decimals"] = d if d else _decimals(str(v)) if isinstance(v, float) and v != int(v) else 0
    return c2


def report_fpr(folder, n=20, seed=7):
    from finrobot.functional.fact_check import CONTEXT_KINDS, SourceIndex, check_claim
    fcs = [p for p in glob.glob(str(folder / "*_factcheck.json")) if not p.endswith("_round1.json")]
    if not fcs:
        return None
    fc = json.load(open(fcs[0], encoding="utf-8"))
    src = SourceIndex("[offline] report resources")
    files = [p for p in glob.glob(str(folder / "*.txt")) if not p.endswith("_analysis.txt")
             and not p.endswith("run_log.txt")]
    for p in files:
        src.add_text(open(p, encoding="utf-8", errors="ignore").read())
    base = [c for c in fc.get("claims", []) if c.get("source") and check_claim(c, [src])]
    pseudo = sum(1 for c in base if c["kind"] == "plain"
                 and re.search(rf"{re.escape(c['text'])}-[KQ]\b", c.get("context", "")))
    out = {"report": folder.name, "claims_found": sum(1 for c in fc.get("claims", []) if c.get("source")),
           "claims_found_offline": len(base), "resource_files": len(files), "pseudo_claims_10K_10Q": pseudo}
    for tag, ck in (("", None), ("ctx_", CONTEXT_KINDS)):
        rnd = random.Random(seed)
        pool = base if ck is None else [c for c in base if check_claim(c, [src], ck) is not None]
        tot, hit, by = 0, 0, {}
        for c in pool:
            for _ in range(n):
                f = 1 + rnd.choice([-1, 1]) * rnd.uniform(0.10, 0.50)
                ok = check_claim(perturb(c, f), [src], ck) is not None
                tot += 1
                hit += ok
                k = by.setdefault(c["kind"], [0, 0])
                k[0] += 1
                k[1] += ok
        out.update({f"{tag}kept": len(pool), f"{tag}perturbations": tot,
                    f"{tag}fpr": round(hit / tot, 3) if tot else None,
                    f"{tag}detection_rate": round(1 - hit / tot, 3) if tot else None,
                    **{f"{tag}fpr_{k}": round(v[1] / v[0], 3) for k, v in by.items() if v[0]},
                    **{f"{tag}kept_{k}": sum(1 for c in pool if c["kind"] == k) for k in ("money", "pct", "plain", "multiple")}})
    out["perturbations"] = out.pop("perturbations")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports", nargs="*", help="Ordnernamen unter ai_in_finance/reports (Standard: alle Annual Reports)")
    ap.add_argument("--n", type=int, default=20)
    a = ap.parse_args()
    if a.reports:
        folders = [AIF / "reports" / r for r in a.reports]
    else:
        folders = [Path(p) for p in sorted(glob.glob(str(AIF / "reports" / "*_*_*")))
                   if re.match(r"^[A-Z.]+_\d{4}_", Path(p).name) and glob.glob(str(Path(p) / "*_factcheck.json"))]
    rows = []
    for f in folders:
        r = report_fpr(f, n=a.n)
        if r and r["perturbations"]:
            rows.append(r)
            print(f"{r['report']:45} offline belegt {r['claims_found_offline']:>4} von {r['claims_found']:>4} | "
                  f"FPR nur Zahl {r['fpr'] * 100:5.1f}% | mit Kontext {(r['ctx_fpr'] or 0) * 100:5.1f}% "
                  f"({r['ctx_kept']} Zahlen mit Kontext belegt)")
        elif r:
            print(f"{f.name}: keine Ressourcen-Dateien oder keine offline belegten Zahlen - uebersprungen")
    if rows:
        out = AIF / "eval" / "fpr_results.csv"
        out.parent.mkdir(exist_ok=True)
        fields = list(dict.fromkeys(k for r in rows for k in r))
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)
        print(f"\nGespeichert: {out}")


if __name__ == "__main__":
    main()
