"""
Fasst alle Evaluationslaeufe zusammen:
- reports/*/run_meta.json (Agenten-Laeufe aus run_eval.py)
- alle *_factcheck.json (Agenten-Reports und Baseline-Texte aus factcheck_text.py)

Ausfuehren (aus dem FinRobot-Ordner):
    python ai_in_finance/scripts/eval_summary.py [--sample 15]

Erzeugt in ai_in_finance/eval/:
- eval_results.csv            eine Zeile pro Report (Kennzahlen fuer den Kursbericht)
- manual_review_sample.csv    Zufallsstichprobe gefundener und nicht gefundener Zahlen zum Selbstpruefen
                              (Spalte manual_correct ausfuellen: 1 = Zahl stimmt im Kontext, 0 = falsch)
"""
import argparse
import csv
import glob
import json
import os
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIF = ROOT / "ai_in_finance"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=15, help="Stichprobe je Report und Gruppe (gefunden/nicht gefunden)")
    a = ap.parse_args()
    out_dir = AIF / "eval"
    out_dir.mkdir(exist_ok=True)
    rows, sample = [], []
    rnd = random.Random(42)
    for fc_path in sorted(glob.glob(str(AIF / "reports" / "**" / "*_factcheck.json"), recursive=True)):
        if "prototypes" in fc_path or fc_path.endswith("_round1.json"):
            continue
        fc = json.load(open(fc_path, encoding="utf-8"))
        folder = Path(fc_path).parent
        meta_p = folder / "run_meta.json"
        meta = json.load(open(meta_p, encoding="utf-8")) if meta_p.exists() and fc.get("kind") != "baseline" else {}
        rel = os.path.relpath(fc_path, AIF)
        kind = fc.get("kind") or ("agent (eval run)" if meta else "agent (notebook)")
        by_kind = fc.get("by_kind", {})
        row = {
            "report": rel, "type": kind,
            "company": meta.get("company") or fc.get("ticker") or folder.name.split("_")[0],
            "model": meta.get("model") or ("-" if kind == "baseline" else folder.name.split("_", 2)[-1]),
            "claims": fc["total_claims"], "matched": fc["matched"],
            "match_rate": fc["match_rate"], "name_issues": len(fc["name_issues"]),
            "self_correct": fc.get("self_correct"), "build_round": fc.get("build_round"),
            "match_rate_round1": (fc.get("round1") or {}).get("match_rate"),
            "money_rate": _rate(by_kind.get("money")), "pct_rate": _rate(by_kind.get("pct")),
            "success": meta.get("success"), "seconds": meta.get("seconds"), "cost_usd": meta.get("cost_usd"),
            "tool_calls": meta.get("n_tool_calls"), "tool_errors": meta.get("n_tool_errors"),
            "build_attempts": meta.get("build_attempts"),
            "prompt_tokens": meta.get("prompt_tokens"), "completion_tokens": meta.get("completion_tokens"),
        }
        rows.append(row)
        claims = fc.get("claims") or fc.get("unmatched", [])
        found = [c for c in claims if c.get("source")]
        missing = [c for c in claims if not c.get("source")]
        for group, lst in (("found", found), ("not found", missing)):
            for c in rnd.sample(lst, min(a.sample, len(lst))):
                sample.append({"report": rel, "group": group, "section": c.get("section"), "figure": c.get("text"),
                               "matched_source": c.get("source") or "", "context": c.get("context"),
                               "manual_correct": ""})
    # Abgebrochene Laeufe ohne Faktencheck trotzdem aufnehmen
    for meta_p in glob.glob(str(AIF / "reports" / "*" / "run_meta.json")):
        meta = json.load(open(meta_p, encoding="utf-8"))
        if not meta.get("success"):
            rows.append({"report": os.path.relpath(meta_p, AIF), "type": "agent (eval run, failed)",
                         "company": meta["company"], "model": meta["model"], "success": False,
                         "seconds": meta.get("seconds"), "cost_usd": meta.get("cost_usd"),
                         "tool_calls": meta.get("n_tool_calls"), "tool_errors": meta.get("n_tool_errors"),
                         "build_attempts": meta.get("build_attempts")})
    if not rows:
        print("Keine Faktencheck-Dateien gefunden.")
        return
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with open(out_dir / "eval_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    with open(out_dir / "manual_review_sample.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["report", "group", "section", "figure", "matched_source", "context",
                                          "manual_correct"])
        w.writeheader()
        w.writerows(sample)
    print(f"{'Report':55} {'Typ':22} {'Modell':22} {'Zahlen':>7} {'Quote':>6} {'Namen':>5} {'Sek.':>6} {'USD':>6}")
    for r in rows:
        q = f"{r['match_rate'] * 100:.0f}%" if r.get("match_rate") is not None else "-"
        print(f"{r['report'][:55]:55} {r['type'][:22]:22} {str(r.get('model'))[:22]:22} {str(r.get('claims', '-')):>7} "
              f"{q:>6} {str(r.get('name_issues', '-')):>5} {str(r.get('seconds') or '-'):>6} {str(r.get('cost_usd') or '-'):>6}")
    print(f"\nGespeichert: {out_dir / 'eval_results.csv'} und {out_dir / 'manual_review_sample.csv'}")


def _rate(d):
    return round(d["matched"] / d["total"], 3) if d and d.get("total") else None


if __name__ == "__main__":
    main()
