"""
Manuelle Stichprobe in der App labeln (eval/manual_review_sample.csv, erzeugt von scripts/eval_summary.py).

Je Zahl zeigt die App den Satz im Report und, falls der Faktencheck die Zahl gefunden hat, die Textstelle in der Quelle
(aus dem Faktencheck-JSON des Reports). Das Label landet in der Spalte manual_correct: 1 = Zahl stimmt im Kontext,
0 = falsch, u = nicht entscheidbar. Reihenfolge: fest gemischt (Seed), damit auch ein Teil der Stichprobe zufaellig ist.
Zeilen aus dem eigenen Broker-Portfolio werden nicht angezeigt (Demo mit Musterportfolio).
"""
import csv
import json
import random
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
SAMPLE = AIF / "eval" / "manual_review_sample.csv"
FIELDS = ["report", "group", "section", "figure", "matched_source", "context", "manual_correct"]
PRIVATE = ("portfolio_tr", "tr_portfolio")


def _rows():
    if not SAMPLE.exists():
        return []
    with open(SAMPLE, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write(rows):
    tmp = SAMPLE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(SAMPLE)


def _short(report):
    p = Path(str(report).replace("\\", "/"))
    parts = p.parts
    folder = parts[-2] if len(parts) >= 2 else p.stem
    if "archive" in parts:
        folder = parts[-2]
    return folder.replace("_claude-haiku-5.5", "").replace("claude-haiku-5.5", "").strip("_")


_FC_CACHE = {}


def _evidence(row):
    """Textstelle aus dem Faktencheck-JSON (gleiche Zahl, gleicher Kontext) oder None."""
    path = AIF / str(row["report"]).replace("\\", "/")
    if path not in _FC_CACHE:
        try:
            _FC_CACHE[path] = json.load(open(path, encoding="utf-8")).get("claims", [])
        except Exception:
            _FC_CACHE[path] = []
    claims = _FC_CACHE[path]
    hit = next((c for c in claims if c.get("text") == row["figure"] and c.get("context") == row["context"]), None) \
        or next((c for c in claims if c.get("text") == row["figure"] and c.get("section") == row["section"]), None)
    if not hit:
        return None, None
    ev, ctx = hit.get("evidence"), hit.get("context_ok")
    if ev is None or ctx is None:                 # aeltere Reports: Textstelle und Kontext offline nachrechnen
        src = _offline_source(path.parent)
        if src is not None:
            try:
                from finrobot.functional.fact_check import CONTEXT_KINDS, check_claim
                if check_claim(hit, [src]) is not None:
                    if ctx is None and hit.get("kind") in CONTEXT_KINDS:
                        ctx = check_claim(hit, [src], CONTEXT_KINDS) is not None
                    ev = ev or src.evidence(dict(hit, context_ok=ctx))
            except Exception:
                pass
    return ev, ctx


_SRC_CACHE = {}


def _offline_source(folder):
    """Ressourcen-Dateien des Report-Ordners als Quelle (wie im FPR-Test; ohne Modelltexte und run_log)."""
    if folder in _SRC_CACHE:
        return _SRC_CACHE[folder]
    src = None
    try:
        from finrobot.functional.fact_check import SourceIndex
        files = [p for p in folder.glob("*.txt") if not p.name.endswith("_analysis.txt") and p.name != "run_log.txt"]
        if files:
            src = SourceIndex("[offline] report resources")
            for p in files:
                src.add_text(p.read_text(encoding="utf-8", errors="ignore"), origin=f"{p.stem.replace('_', ' ')} (report resources)")
    except Exception:
        src = None
    _SRC_CACHE[folder] = src
    return src


def items(seed=42):
    """Alle Zeilen in fester Zufallsreihenfolge, mit Herkunft; private Zeilen ausgeblendet."""
    rows = _rows()
    order = list(range(len(rows)))
    random.Random(seed).shuffle(order)
    out = []
    for i in order:
        r = rows[i]
        if any(x in str(r["report"]) for x in PRIVATE):
            continue
        ev, ctx = _evidence(r) if r["group"] == "found" else (None, None)
        out.append({"i": i, "report": _short(r["report"]), "group": r["group"], "section": r["section"],
                    "figure": r["figure"], "context": r["context"], "source": r.get("matched_source") or "",
                    "evidence": ev, "context_ok": ctx, "label": (r.get("manual_correct") or "").strip()})
    return out


def set_label(i, value):
    rows = _rows()
    if 0 <= i < len(rows):
        rows[i]["manual_correct"] = value
        _write(rows)


def stats(its=None):
    its = items() if its is None else its
    lab = [x for x in its if x["label"] in ("1", "0")]
    f = [x for x in lab if x["group"] == "found"]
    n = [x for x in lab if x["group"] != "found"]
    share = lambda xs: (sum(x["label"] == "1" for x in xs) / len(xs)) if xs else None
    fc_ok = [x for x in f if x.get("context_ok") is True]
    fc_no = [x for x in f if x.get("context_ok") is False]
    return {"total": len(its), "labelled": len(lab), "unsure": sum(x["label"] == "u" for x in its),
            "found_n": len(f), "found_correct": share(f), "notfound_n": len(n), "notfound_correct": share(n),
            "ctx_ok_n": len(fc_ok), "ctx_ok_correct": share(fc_ok), "ctx_no_n": len(fc_no), "ctx_no_correct": share(fc_no)}
