"""
Thesis Tracker (eigene Erweiterung): verfolgt jede Investment-These Quartal fuer Quartal.

Ablauf
1. Thesis Book (einmal je Annual Report): ein Modellaufruf macht aus den Thesen des Annual Reports messbare
   Meilensteine ("ARR growth >= 10 % YoY") und legt eine feste KPI-Liste fest (Name, Einheit, gute Richtung).
   Gleiche KPI-Namen in jedem Quartal -> saubere Zeitreihen.
2. Quarter Record (je Quartal, auch Q4): ein Modellaufruf liest die Pressemitteilung (8-K) und das 10-Q genau dieses
   Quartals und liefert KPIs (Namen aus dem Thesis Book), Guidance, Kernaussagen des Managements, Status und Beleg je
   These. Jede Zahl wird gegen die Quellen geprueft (Faktencheck wie bei den Reports). Fehlende Quartale seit dem
   10-K werden einzeln nachgeholt.
3. Auswertung (Python, ohne Modell): Meilensteine je Quartal erfuellt / verfehlt, Status-Verlauf je These,
   Widerspruch zwischen Modellurteil und Meilensteinen, Fruehwarnungen aus den News zwischen den Quartalen.
Ablage: reports/thesis_books/<T>.json, reports/quarter_records/<T>/<T>_Q1_FY2026.json
"""
import json
import re
from datetime import date, datetime
from pathlib import Path
from . import agent_settings as _AS  # Prompts/Parameter aus der App (research/agent_settings.json)

AIF = Path(__file__).resolve().parents[1]
BOOKS = AIF / "reports" / "thesis_books"
QREC = AIF / "reports" / "quarter_records"
STATUSES = ("strengthened", "intact", "weakened", "broken")
STD = {"Revenue growth y/y": "%", "Gross margin": "%", "Operating margin": "%", "Net margin": "%",
       "Free cash flow margin": "%", "Diluted EPS": "USD"}


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def _num(x):
    try:
        v = float(str(x).replace(",", "").replace("%", "")) if isinstance(x, str) else float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _json(raw):
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        raise RuntimeError("the model returned no JSON")
    return json.loads(m.group(0))


def _log_cost(what, cost, model):
    try:
        with open(AIF / "research" / "app_costs.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "what": what, "cost": cost,
                                "model": model}) + "\n")
    except Exception:
        pass


def _annual(t):
    from .valuation_data import _annual_args
    return _annual_args(t)


def _theses(args):
    th = args.get("investment_theses") or []
    if isinstance(th, str):
        try:
            import ast
            th = ast.literal_eval(th)
        except Exception:
            th = []
    out = []
    for x in th:
        if isinstance(x, dict) and (x.get("thesis") or x.get("text")):
            out.append({"thesis": str(x.get("thesis") or x.get("text")), "signpost": str(x.get("signpost") or x.get("watch") or "")})
        elif isinstance(x, str):
            out.append({"thesis": x, "signpost": ""})
    return out


# =============================================================== 1. Thesis Book
def book_path(t):
    return BOOKS / f"{t.upper()}.json"


def load_book(t):
    return _load(book_path(t))


BOOK_PROMPT = """You turn the investment theses of an equity research annual report on {t} (fiscal year {fy}) into a
thesis book that can be tracked every quarter.

Theses from the annual report:
{theses}

KPIs that can be tracked each quarter (use ONLY these names, spelled exactly):
{kpis}

Return JSON only:
{{"theses": [{{"id": "T1", "short": "<max 8 words>", "milestones": [{{"kpi": "<name from the list>",
"measure": "level" or "yoy", "op": ">=" or "<=", "threshold": <number>, "text": "<e.g. ARR growth >= 10% YoY>"}}]}}],
"kpis": [{{"name": "<name from the list>", "definition": "<one short line>"}}]}}

Rules: one entry per thesis in the same order (T1, T2, ...). 1-3 milestones per thesis that would show the thesis is
on track, each tied to its signpost where possible. "level" compares the reported value itself (for % metrics in
percentage points, e.g. 35 for a 35% margin); "yoy" compares growth versus the same quarter a year earlier in percent
(e.g. 10 for +10%). Thresholds must be realistic given the research text. Choose 4-8 KPIs for the "kpis" list: all
KPIs used in milestones plus the most important other ones."""


def build_book(t, model=None, llm=None):
    """Thesis Book aus dem neuesten Annual Report (ein Modellaufruf, etwa 0,3 Cent)."""
    from .chat import call_llm
    t = t.upper()
    args = _annual(t)
    th = _theses(args)
    if not th:
        raise RuntimeError(f"no annual report with theses for {t}; run the annual report first")
    fy = (re.search(r"_(\d{4})_annual", str(args.get("save_path") or "")) or [None, "?"])[1]
    avail = dict(STD)
    try:
        from .kpi_history import history
        for k in history(t, min_points=1):
            avail.setdefault(k["name"], k["unit"] or "")
    except Exception:
        pass
    for r in load_records(t):
        for k in r.get("kpis") or []:
            avail.setdefault(k["name"], k.get("unit") or "")
    model = model or _AS.model("quarter_review")
    prompt = _AS.get("thesis.book", BOOK_PROMPT).format(t=t, fy=fy, theses="\n".join(f"T{i}: {x['thesis']}\n   Signpost: {x['signpost'] or '-'}"
                                                             for i, x in enumerate(th, 1)),
                                kpis="\n".join(f"- {n} ({u or 'number'})" for n, u in avail.items()))
    raw, cost = (llm or call_llm)([{"role": "user", "content": prompt}], model=model, max_tokens=1600)
    j = _json(raw)
    names = {_norm(n): n for n in avail}
    theses = []
    for i, x in enumerate(th, 1):
        src = next((y for y in j.get("theses") or [] if str(y.get("id", "")).upper() == f"T{i}"), None) or \
            ((j.get("theses") or [])[i - 1] if len(j.get("theses") or []) >= i else {})
        ms = []
        for m in src.get("milestones") or []:
            n = names.get(_norm(m.get("kpi")))
            thr = _num(m.get("threshold"))
            if not n or thr is None:
                continue                                   # nur KPIs aus der Liste, nur Zahlen
            ms.append({"kpi": n, "measure": "yoy" if m.get("measure") == "yoy" else "level",
                       "op": "<=" if m.get("op") == "<=" else ">=", "threshold": thr, "unit": avail.get(n, ""),
                       "text": str(m.get("text") or f"{n} {m.get('op', '>=')} {thr}")[:90]})
        theses.append({"id": f"T{i}", "thesis": x["thesis"], "signpost": x["signpost"],
                       "short": str(src.get("short") or x["thesis"][:60])[:70], "milestones": ms[:3]})
    kpis = []
    for k in j.get("kpis") or []:
        n = names.get(_norm(k.get("name")))
        if n and n not in [x["name"] for x in kpis]:
            kpis.append({"name": n, "unit": avail.get(n, ""), "definition": str(k.get("definition") or "")[:140]})
    for th_ in theses:                                     # Meilenstein-KPIs immer in der Liste
        for m in th_["milestones"]:
            if m["kpi"] not in [x["name"] for x in kpis]:
                kpis.append({"name": m["kpi"], "unit": m["unit"], "definition": ""})
    book = {"ticker": t, "fyear": fy, "created": datetime.now().isoformat(timespec="minutes"), "model": model,
            "cost": cost, "annual_report": str(args.get("save_path") or ""), "theses": theses, "kpis": kpis}
    BOOKS.mkdir(parents=True, exist_ok=True)
    json.dump(book, open(book_path(t), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return book


# =============================================================== 2. Quarter Records
def load_records(t):
    out = [_load(p) for p in sorted((QREC / t.upper()).glob("*.json"))]
    return sorted([r for r in out if r and r.get("end")], key=lambda r: r["end"])


def missing_releases(t, releases, tenk_period):
    """Pressemitteilungen seit dem Geschaeftsjahresende (inkl. Q4), fuer die noch kein Quarter Record existiert."""
    have = {r.get("release_date") for r in load_records(t)}
    return sorted(d for d in releases if tenk_period and d > str(tenk_period) and d not in have)


def _label(end, fy_end):
    n = round((end - fy_end).days / 91.3)
    if n <= 0:
        return f"Q{4 + n} FY{fy_end.year}" if n > -4 else None
    return f"Q{(n - 1) % 4 + 1} FY{fy_end.year + 1 + (n - 1) // 4}"


QPROMPT = """You are an equity analyst tracking investment theses on {t} quarter by quarter. Review ONLY the quarter
{label} (quarter ended {end}) using the sources below. Never invent numbers; copy values exactly as reported.

THESIS BOOK
{book}

PREVIOUS STATUS (from the last quarter record): {prev}

COMPUTED METRICS FOR THE QUARTER (Yahoo Finance statements, vs. same quarter a year earlier)
{metrics}

EARNINGS RELEASE (8-K, filed {rel_date})
{release}

FORM 10-Q MD&A
{tenq}

Return JSON only:
{{"headline": "<max 22 words>", "summary": "<60-110 words on the quarter with figures>",
"kpis": [{{"name": "<KPI name from the thesis book, exactly>", "value": <number>, "prior": <same quarter a year
earlier or null>, "unit": "<unit>", "good_direction": "up" or "down", "source": "release" or "10-Q"}}],
"guidance": "<guidance given or changed this quarter, 1-2 sentences, or 'no guidance change'>",
"narrative": ["<3-5 key management messages this quarter, paraphrased, one sentence each>"],
"theses": [{{"id": "T1", "status": "strengthened|intact|weakened|broken", "evidence": "<1-2 sentences with figures>"}}],
"risks": ["<0-3 risks that emerged or grew this quarter>"]}}

Rules: report every thesis-book KPI the company disclosed for this quarter (skip those it did not report). Percent
values as numbers (12.5 for 12.5%), money in the unit stated. Keep statuses consistent with the previous status unless
this quarter's evidence justifies a change."""


def _sources(release_text, tenq_text, yahoo_text, raw_vals):
    from finrobot.functional.fact_check import SourceIndex
    s1, s2, s3 = SourceIndex("[1] Earnings release"), SourceIndex("[2] Form 10-Q"), SourceIndex("[3] Yahoo Finance")
    s1.add_text(release_text or "")
    s2.add_text(tenq_text or "")
    s3.add_text(yahoo_text or "")
    for v in raw_vals:
        try:
            s3.add_raw_usd(v)
        except Exception:
            pass
    return [s1, s2, s3]


def review_quarter(t, release_date, fyear, model=None, llm=None):
    """Einen Quarter Record fuer die Pressemitteilung vom release_date erstellen (ein Modellaufruf)."""
    import pandas as pd
    from . import quarterly_data as qd
    from .chat import call_llm
    t = t.upper()
    book = load_book(t) or build_book(t, model=model, llm=llm)
    tk = qd._ticker(t)
    qi, qb, qc, ai = (qd._get(tk, a) for a in ("quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow",
                                               "income_stmt"))
    if qi is None:
        raise RuntimeError("no quarterly statements on Yahoo Finance")
    rd = pd.Timestamp(release_date)
    qcols = sorted(c for c in qi.columns if qd._row(qi, qd.REV, c))
    cand = [c for c in qcols if pd.Timestamp(c) < rd and (rd - pd.Timestamp(c)).days <= 100]
    if not cand:
        raise RuntimeError(f"no quarter on Yahoo Finance matches the release of {release_date}")
    end = pd.Timestamp(cand[-1])
    fy_end = qd._fy_end(ai, fyear) or qd._fy_end(ai, None)
    label = _label(end, fy_end) if fy_end is not None else f"Q? {end.date()}"
    ya = qd._year_ago(qcols, end)
    ya2 = qd._year_ago(qcols, ya) if ya is not None else None
    m1 = qd._period_metrics(qi, qb, qc, end, prev_rev=qd._row(qi, qd.REV, ya) if ya is not None else None)
    m0 = qd._period_metrics(qi, qb, qc, ya, prev_rev=qd._row(qi, qd.REV, ya2) if ya2 is not None else None) if ya is not None else {}
    units = {m: u for m, u, _, _ in qd.METRICS}
    metrics = {k: {"value": m1.get(k), "year_ago": m0.get(k), "unit": units.get(k, "mn")} for k in m1}
    mtxt = "\n".join(f"- {k}: {qd.fmt_val(v['value'], v['unit'])} (year-ago {qd.fmt_val(v['year_ago'], v['unit'])})"
                     for k, v in metrics.items() if v["value"] is not None)
    rel = {}
    try:
        rels = qd.earnings_releases_since(t, (end - pd.Timedelta(days=75)).date().isoformat())
        ok = [r for r in rels if not r.get("error")]
        rel = next((r for r in ok if r.get("filing_date") == release_date), ok[0] if ok else {})
    except Exception as e:
        rel = {"error": str(e)}
    tenq = {}
    try:
        qs = qd.tenqs_since(t, (end - pd.Timedelta(days=12)).date().isoformat())
        tenq = next((q for q in qs if abs((pd.Timestamp(q["report_date"]) - end).days) <= 12), {})
    except Exception as e:
        tenq = {"error": str(e)}
    rtext = rel.get("text") or ""
    qtext = "\n\n".join((tenq.get("sections") or {}).values()) if tenq else ""
    if not rtext and not qtext:
        raise RuntimeError(f"neither the earnings release nor the 10-Q for {label} could be loaded")
    prev = load_records(t)
    prev = [r for r in prev if r["end"] < str(end.date())]
    prev_txt = "; ".join(f"{x['id']}: {x.get('status')}" for x in (prev[-1].get("theses") or [])) if prev else "none (first record)"
    btxt = "\n".join(f"{x['id']}: {x['thesis']} | signpost: {x['signpost'] or '-'} | milestones: "
                     + ("; ".join(m["text"] for m in x["milestones"]) or "-") for x in book["theses"])
    btxt += "\nKPIs: " + ", ".join(f"{k['name']} ({k['unit'] or 'number'})" for k in book["kpis"])
    model = model or _AS.model("quarter_review")
    prompt = _AS.get("thesis.quarter", QPROMPT).format(t=t, label=label, end=end.date(), book=btxt, prev=prev_txt, metrics=mtxt or "(not available)",
                            rel_date=rel.get("filing_date") or release_date, release=rtext[:16000] or "(not available)",
                            tenq=qtext[:11000] or "(no 10-Q for this quarter, e.g. the fourth quarter is covered by the 10-K)")
    raw, cost = (llm or call_llm)([{"role": "user", "content": prompt}], model=model, max_tokens=2200)
    j = _json(raw)
    # KPIs: nur Namen aus dem Thesis Book, Werte gegen die Quellen pruefen
    names = {_norm(k["name"]): k["name"] for k in book["kpis"]}
    raw_vals = []
    for df in (qi, qb, qc):
        if df is not None:
            raw_vals += [v for v in df.values.flatten()]
    srcs = _sources(rtext, qtext, mtxt, raw_vals)
    from .earnings_reviewer import evaluate_kpis
    kin = []
    for k in j.get("kpis") or []:
        n = names.get(_norm(k.get("name")))
        if n and _num(k.get("value")) is not None and n not in [x["name"] for x in kin]:
            kin.append({"name": n, "unit": str(k.get("unit") or ""), "current": _num(k.get("value")),
                        "prior": _num(k.get("prior")), "good_direction": k.get("good_direction") or "up",
                        "source": str(k.get("source") or "")})
    kpis = [{"name": e["name"], "unit": e["unit"], "value": e["current"], "prior": e["prior"],
             "good_direction": e["good_direction"], "verified": e["verified"], "source": e["source"]}
            for e in evaluate_kpis(kin, srcs)]
    theses = []
    ids = [x["id"] for x in book["theses"]]
    for x in j.get("theses") or []:
        i = str(x.get("id", "")).upper()
        st = str(x.get("status", "")).lower()
        if i in ids and i not in [y["id"] for y in theses]:
            theses.append({"id": i, "status": st if st in STATUSES else "intact", "evidence": str(x.get("evidence") or "")[:400]})
    narrative = [str(s)[:260] for s in (j.get("narrative") or [])][:5]
    sections = [("Summary", str(j.get("summary") or "")), ("Guidance", str(j.get("guidance") or "")),
                ("Management", " ".join(narrative)), ("Theses", " ".join(x["evidence"] for x in theses))]
    fc = {"matched": None, "total": None, "unmatched": []}
    try:
        from finrobot.functional.fact_check import run_fact_check
        r = run_fact_check(sections, srcs, None)
        fc = {"matched": r.get("matched"), "total": r.get("total_claims"),
              "unmatched": [{"section": u.get("section"), "text": u.get("text")} for u in (r.get("unmatched") or [])][:12]}
    except Exception as e:
        fc["error"] = str(e)[:160]
    rec = {"ticker": t, "label": label, "end": str(end.date()), "release_date": release_date, "fyear": str(fyear),
           "book_fy": book.get("fyear"),
           "created": datetime.now().isoformat(timespec="minutes"), "model": model, "cost": cost,
           "headline": str(j.get("headline") or "")[:200], "summary": str(j.get("summary") or "")[:1200],
           "guidance": str(j.get("guidance") or "")[:500], "narrative": narrative,
           "risks": [str(s)[:240] for s in (j.get("risks") or [])][:3], "theses": theses, "kpis": kpis,
           "metrics": {k: {"value": v["value"], "year_ago": v["year_ago"], "unit": v["unit"]} for k, v in metrics.items()},
           "fc": fc, "sources": {"release": rel.get("url"), "release_filed": rel.get("filing_date"),
                                 "tenq": tenq.get("url") if tenq else None}}
    (QREC / t).mkdir(parents=True, exist_ok=True)
    json.dump(rec, open(QREC / t / f"{t}_{label.replace(' ', '_')}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return rec


def review_missing(t, releases, tenk_period, fyear, model=None, llm=None, log=print):
    """Alle fehlenden Quartale seit dem 10-K einzeln nachholen. Rueckgabe: Liste der erstellten Records."""
    done = []
    for d in missing_releases(t, releases, tenk_period):
        try:
            r = review_quarter(t, d, fyear, model=model, llm=llm)
            done.append(r)
            log(f"{t}: quarter record {r['label']} (release {d}), fact check {r['fc'].get('matched')}/{r['fc'].get('total')}")
        except Exception as e:
            log(f"{t}: quarter record for release {d} failed: {e}")
    return done


# =============================================================== 3. Auswertung (ohne Modell)
def _value(rec, m):
    """Wert eines Meilensteins im Quartal: (Wert in der Einheit des Schwellenwerts, Beschriftung) oder (None, '')."""
    n = _norm(m["kpi"])
    k = next((x for x in rec.get("kpis") or [] if _norm(x["name"]) == n), None)
    if k is None and m["kpi"] in (rec.get("metrics") or {}):
        x = rec["metrics"][m["kpi"]]
        k = {"value": x.get("value"), "prior": x.get("year_ago"),
             "unit": "%" if x.get("unit") == "pct" else x.get("unit"), "_frac": x.get("unit") == "pct"}
    if not k or k.get("value") is None:
        return None, ""
    v, p = k["value"], k.get("prior")
    if m["measure"] == "yoy":
        if p in (None, 0):
            return None, ""
        if "%" in str(k.get("unit") or "") and not k.get("_frac"):
            return v - p, "pp"                             # Prozentwerte: Veraenderung in Prozentpunkten
        return (v / abs(p) - 1) * 100 if not k.get("_frac") else (v - p) * 100, "% YoY"
    return (v * 100 if k.get("_frac") else v), str(k.get("unit") or "")


def tracker(t, news=None):
    """Alles fuer die Firmenseite: Thesis Book, Quartale, Status-Verlauf, Meilensteine, Erzaehlung, Fruehwarnungen."""
    t = t.upper()
    book = load_book(t)
    recs = load_records(t)
    out = {"book": bool(book), "fyear": (book or {}).get("fyear"), "book_created": (book or {}).get("created"),
           "quarters": [r["label"] for r in recs], "theses": [], "records": [], "warnings": []}
    for r in recs:
        out["records"].append({"label": r["label"], "end": r["end"], "headline": r.get("headline"), "summary": r.get("summary"),
                               "guidance": r.get("guidance"), "narrative": r.get("narrative") or [], "risks": r.get("risks") or [],
                               "fc": r.get("fc") or {}, "release": (r.get("sources") or {}).get("release")})
    for th in (book or {}).get("theses") or []:
        tl = []
        for r in recs:
            same = r.get("book_fy") in (None, book.get("fyear"))      # Thesen eines aelteren Thesis Books nicht mischen
            x = next((y for y in r.get("theses") or [] if y["id"] == th["id"]), None) if same else None
            tl.append({"q": r["label"], "status": x["status"] if x else None, "evidence": x["evidence"] if x else ""})
        ms = []
        for m in th["milestones"]:
            cells = []
            for r in recs:
                v, u = _value(r, m)
                met = None if v is None else (v >= m["threshold"] if m["op"] == ">=" else v <= m["threshold"])
                cells.append({"q": r["label"], "v": v, "u": u, "met": met})
            ms.append({**m, "cells": cells})
        cur = next((c["status"] for c in reversed(tl) if c["status"]), None)
        last = [c[-1]["met"] for c in [m["cells"] for m in ms] if c and c[-1]["met"] is not None]
        mech = (sum(last) / len(last)) if last else None
        check = None
        if mech is not None and cur in ("intact", "strengthened") and mech < 0.5:
            check = "Most milestones were missed last quarter although the thesis is rated " + cur + "."
        elif mech is not None and cur in ("weakened", "broken") and mech == 1:
            check = "All milestones were met last quarter although the thesis is rated " + cur + "."
        out["theses"].append({"id": th["id"], "short": th["short"], "thesis": th["thesis"], "signpost": th["signpost"],
                              "status": cur, "timeline": tl, "milestones": ms, "met_share": mech, "check": check})
    # Fruehwarnungen zwischen den Quartalen: negative Meldungen seit dem letzten Quartalsbericht
    try:
        since = recs[-1]["release_date"] if recs else None
        for s in news or []:
            if s.get("dir") in ("negative", "down", "bearish") and (since is None or str(s.get("date", "")) > since):
                out["warnings"].append({"date": s.get("date"), "text": s.get("title"), "url": s.get("url")})
    except Exception:
        pass
    return out
