"""
Ergebnis der Evaluation fuer den Kursbericht: fasst alle Messungen in einer Markdown-Datei und einer Grafik zusammen.

Liest (sofern vorhanden):
- *_factcheck.json der Annual Reports (Agent: Eval-Laeufe mit und ohne Selbstkorrektur, Notebook-Laeufe) und der
  Baseline-Texte (reports/baseline)
- eval/fpr_results.csv (Pruefung des Pruefers), eval/manual_review_sample.csv (manuelle Stichprobe)
- reports/*/run_meta.json (Kosten, Laufzeit), research/pipeline_runs/*.json (Kosten je Agent), forecasts/forecast_scores.csv

Ausfuehren (aus dem FinRobot-Ordner):  python ai_in_finance/scripts/eval_report.py
Ergebnis: ai_in_finance/eval/summary.md und eval/summary_chart.png
"""
import csv
import glob
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIF = ROOT / "ai_in_finance"
EVAL = AIF / "eval"


def _pseudo(c):
    """'10' aus '10-K' / '10-Q' wird vom Faktencheck als Zahl gezaehlt - keine echte Aussage."""
    return c.get("kind") == "plain" and re.search(rf"(?<![\d.]){re.escape(c['text'])}-[KQ]\b", c.get("context", "")) is not None


def fc_stats(path):
    fc = json.load(open(path, encoding="utf-8"))
    claims = fc.get("claims") or []
    real = [c for c in claims if not _pseudo(c)]
    r1 = (fc.get("round1") or {}).get("match_rate")
    return {"claims": fc.get("total_claims"), "matched": fc.get("matched"), "rate": fc.get("match_rate"),
            "rate_round1": r1, "pseudo": len(claims) - len(real),
            "rate_adj": round(sum(1 for c in real if c.get("source")) / len(real), 3) if real else None,
            "name_issues": len(fc.get("name_issues") or [])}


def classify(folder, fname):
    n = folder.name
    if folder.name == "baseline":
        return "baseline (plain prompt)"
    if not re.match(r"^[A-Z.]+_\d{4}_", n):
        return None
    if n.endswith("_eval_nosc"):
        return "agent, no self-correction"
    if n.endswith("_eval"):
        return "agent, with self-correction"
    return "agent (notebook/pipeline)"


def pct(x):
    return f"{x * 100:.1f}%" if isinstance(x, (int, float)) else "-"


def main():
    EVAL.mkdir(exist_ok=True)
    rows = []
    for p in sorted(glob.glob(str(AIF / "reports" / "**" / "*_factcheck.json"), recursive=True)):
        if "archive" in Path(p).parts:  # Archivkopien der App nicht doppelt zaehlen
            continue
        if p.endswith("_round1.json") or "prototypes" in p:
            continue
        folder = Path(p).parent
        kind = classify(folder, Path(p).name)
        if not kind:
            continue
        company = (Path(p).name if kind.startswith("baseline") else folder.name).split("_")[0]
        meta_p = folder / "run_meta.json"
        meta = json.load(open(meta_p, encoding="utf-8")) if meta_p.exists() and not kind.startswith("baseline") else {}
        s = fc_stats(p)
        rows.append({"company": company, "kind": kind, "report": str(Path(p).relative_to(AIF)), **s,
                     "seconds": meta.get("seconds"), "cost_usd": meta.get("cost_usd")})
    L = ["# Evaluation - Zusammenfassung", "", "Automatisch erzeugt von `scripts/eval_report.py`. Trefferquote = Anteil der "
         "Zahlen im Text, die der Faktencheck in den Quellen findet. 'bereinigt' = ohne Pseudo-Zahlen wie das '10' in "
         "'10-K'.", ""]
    L += ["## 1. Agent gegen Baseline und Wirkung der Selbstkorrektur (Annual Reports)", "",
          "| Firma | Variante | Zahlen | Trefferquote | bereinigt | Runde 1 | Pseudo-Zahlen | Sek. | USD |",
          "|---|---|---|---|---|---|---|---|---|"]
    order = {"baseline (plain prompt)": 0, "agent, no self-correction": 1, "agent, with self-correction": 2,
             "agent (notebook/pipeline)": 3}
    for r in sorted(rows, key=lambda r: (r["company"], order.get(r["kind"], 9))):
        L.append(f"| {r['company']} | {r['kind']} | {r['claims']} | {pct(r['rate'])} | {pct(r['rate_adj'])} | "
                 f"{pct(r['rate_round1'])} | {r['pseudo']} | {r['seconds'] or '-'} | {r['cost_usd'] or '-'} |")
    agg = defaultdict(list)
    for r in rows:
        if r["rate"] is not None:
            agg[r["kind"]].append(r)
    L += ["", "**Mittelwerte je Variante:**", "", "| Variante | Reports | Trefferquote | bereinigt | Runde 1 |", "|---|---|---|---|---|"]
    for k in sorted(agg, key=lambda k: order.get(k, 9)):
        v = agg[k]
        m = lambda key: sum(x[key] for x in v if x[key] is not None) / max(1, sum(1 for x in v if x[key] is not None))
        L.append(f"| {k} | {len(v)} | {pct(m('rate'))} | {pct(m('rate_adj'))} | "
                 f"{pct(m('rate_round1')) if any(x['rate_round1'] is not None for x in v) else '-'} |")
    fpr = EVAL / "fpr_results.csv"
    if fpr.exists():
        fr = list(csv.DictReader(open(fpr, encoding="utf-8")))
        L += ["", "## 2. Pruefung des Pruefers (verfaelschte Zahlen)", "",
              "| Report | Zahlen offline | Falsch-positiv-Rate | Erkennungsrate | Geld | Prozent | sonstige |",
              "|---|---|---|---|---|---|---|"]
        for r in fr:
            L.append(f"| {r['report']} | {r['claims_found_offline']} | {pct(float(r['fpr']))} | "
                     f"{pct(float(r['detection_rate']))} | {pct(float(r['fpr_money'])) if r.get('fpr_money') else '-'} | "
                     f"{pct(float(r['fpr_pct'])) if r.get('fpr_pct') else '-'} | "
                     f"{pct(float(r['fpr_plain'])) if r.get('fpr_plain') else '-'} |")
        L.append("\nLesart: Eine Falsch-positiv-Rate von 35 % heisst, dass jede dritte absichtlich falsche Zahl trotzdem "
                 "als belegt gilt. Untergrenze, da offline weniger Quellen geprueft werden.")
    mr = EVAL / "manual_review_sample.csv"
    if mr.exists():
        m = list(csv.DictReader(open(mr, encoding="utf-8")))
        lab = [r for r in m if str(r.get("manual_correct", "")).strip() in ("0", "1")]
        if lab:
            f_ok = [r for r in lab if r["group"] == "found"]
            n_ok = [r for r in lab if r["group"] != "found"]
            L += ["", "## 3. Manuelle Stichprobe", "",
                  f"- Gelabelt: {len(lab)} von {len(m)} Zahlen",
                  f"- 'gefunden' und tatsaechlich korrekt: {sum(r['manual_correct'].strip() == '1' for r in f_ok)} von "
                  f"{len(f_ok)}",
                  f"- 'nicht gefunden', aber tatsaechlich korrekt (z. B. selbst berechnet): "
                  f"{sum(r['manual_correct'].strip() == '1' for r in n_ok)} von {len(n_ok)}"]
        else:
            L += ["", "## 3. Manuelle Stichprobe", "", f"Noch nicht gelabelt ({len(m)} Zahlen in eval/manual_review_sample.csv)."]
    cost = defaultdict(list)
    for p in glob.glob(str(AIF / "research" / "pipeline_runs" / "*.json")):
        try:
            for s in json.load(open(p, encoding="utf-8")).get("steps", []):
                cost[s["step"]].append((s.get("seconds"), s.get("cost_usd"), bool(s.get("ok"))))
        except Exception:
            pass
    if cost:
        L += ["", "## 4. Kosten und Laufzeit je Agent (Pipeline-Laeufe)", "",
              "| Agent | Laeufe | erfolgreich | Sek. (Mittel) | USD (Mittel) | USD (Summe) |", "|---|---|---|---|---|---|"]
        for k, v in sorted(cost.items()):
            secs = [x[0] for x in v if x[0] is not None]
            usd = [x[1] for x in v if x[1] is not None]
            L.append(f"| {k} | {len(v)} | {sum(x[2] for x in v)} | {sum(secs) / len(secs):.0f} | "
                     f"{(sum(usd) / len(usd)) if usd else 0:.3f} | {sum(usd):.3f} |" if secs else f"| {k} | {len(v)} | - | - | - | - |")
    fs = AIF / "forecasts" / "forecast_scores.csv"
    if fs.exists():
        sc = list(csv.DictReader(open(fs, encoding="utf-8")))
        L += ["", "## 5. Forecaster (Nachbau aus dem Paper)", "", f"{len(sc)} ausgewertete Prognosen; Details in "
              "forecasts/forecast_scores.csv."]
        if sc and "direction_hit" in sc[0]:
            hits = [r for r in sc if r.get("direction_hit") not in ("", None)]
            L.append(f"- Richtung getroffen: {sum(r['direction_hit'] in ('1', 'True', 'true') for r in hits)} von {len(hits)}")
    out = EVAL / "summary.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        comps = sorted({r["company"] for r in rows})
        kinds = [k for k in order if any(r["kind"] == k for r in rows)]
        cols = {"baseline (plain prompt)": "#B03A2E", "agent, no self-correction": "#B9770E",
                "agent, with self-correction": "#2D8A4E", "agent (notebook/pipeline)": "#0F4C5C"}
        fig, ax = plt.subplots(figsize=(8, 3.8))
        w = 0.8 / max(1, len(kinds))
        for i, k in enumerate(kinds):
            vals = []
            for c in comps:
                v = [r["rate_adj"] for r in rows if r["company"] == c and r["kind"] == k and r["rate_adj"] is not None]
                vals.append(sum(v) / len(v) * 100 if v else 0)
            ax.bar([j + i * w for j in range(len(comps))], vals, w, label=k, color=cols.get(k, "#888"))
        ax.set_xticks([j + w * (len(kinds) - 1) / 2 for j in range(len(comps))])
        ax.set_xticklabels(comps)
        ax.set_ylabel("Figures found in sources (%, adjusted)")
        ax.set_ylim(0, 105)
        ax.legend(fontsize=7, frameon=False, loc="lower right")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        fig.tight_layout()
        fig.savefig(EVAL / "summary_chart.png", dpi=160)
    except Exception as e:
        print(f"Grafik nicht erzeugt: {e}")
    print(out.read_text(encoding="utf-8"))
    print(f"Gespeichert: {out} und {EVAL / 'summary_chart.png'}")


if __name__ == "__main__":
    main()
