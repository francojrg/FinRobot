"""
Firmen-Sicht der App: Report-Archiv (jeder Annual Report und jedes Earnings Review wird mit Datum abgelegt, statt
beim naechsten Lauf ueberschrieben zu werden) und die Daten fuer das Firmen-Dashboard (Kennzahlen je Quartal,
Thesen-Verlauf, Kernaussagen, News, Termine, Reports). Python rechnet, die Oberflaeche zeigt nur an.

Archiv: reports/archive/<TICKER>/<id>/ mit build_args, Faktencheck, PDF; Verzeichnis reports/archive/index.json.
"""
import glob
import hashlib
import json
import os
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
REPORTS = AIF / "reports"
RESEARCH = AIF / "research"
ARCH = REPORTS / "archive"
INDEX = ARCH / "index.json"
STATUS_RANK = {"broken": 3, "weakened": 2, "intact": 1, "strengthened": 0}


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _num(v):
    return v if isinstance(v, (int, float)) and v == v else None


def _clean(s):
    return re.sub(r"\s*\[\d+(?:\]\[\d+)*(?:,\s*\d+)*\]", "", str(s or "")).strip()


def _md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


# =============================================================== aktuelle Reports finden
def current_reports():
    """[(ticker, kind, build_args)] fuer alle aktuellen Annual Reports (je Geschaeftsjahr) und Earnings Reviews.
    Evaluations-Varianten (_eval) werden nicht archiviert."""
    out = []
    for p in glob.glob(str(REPORTS / "*" / "*build_args.json")):
        folder = Path(p).parent.name
        if "_eval" in folder or folder in ("archive", "site", "baseline", "prototypes"):
            continue
        m = re.match(r"([A-Z0-9.\-]+?)_(\d{4})_", folder)
        if m and "earnings" not in folder:
            out.append((m.group(1), "annual", p, m.group(2)))
            continue
        m = re.match(r"([A-Z0-9.\-]+?)_earnings(_multi)?_", folder)
        if m:
            out.append((m.group(1), "earnings", p, None))
    return out


def _fc_path(args):
    base = args[: -len("_build_args.json")]
    for suf in ("_factcheck_recheck.json", "_factcheck.json"):
        if Path(base + suf).exists():
            return base + suf
    return None


def _pdf_path(args):
    base = args[: -len("_build_args.json")]
    if Path(base + ".pdf").exists():
        return base + ".pdf"
    pdfs = glob.glob(str(Path(args).parent / "*.pdf"))
    return max(pdfs, key=os.path.getmtime) if pdfs else None


def _summary(t, kind, args, fy):
    """Kurzfassung eines Reports fuer Archiv-Kachel und Vergleich."""
    a = _load(args) or {}
    fc = _load(_fc_path(args) or "") or {}
    e = {"ticker": t, "kind": kind, "fy": fy or a.get("fyear"),
         "date": date.fromtimestamp(os.path.getmtime(args)).isoformat(),
         "fc_matched": fc.get("matched"), "fc_total": fc.get("total_claims")}
    if kind == "annual":
        e["title"] = f"Annual Report FY{e['fy']}" if e["fy"] else "Annual Report"
        e["headline"] = _clean((a.get("key_takeaways") or [""])[0]) if a.get("key_takeaways") else \
            _clean(a.get("investment_summary", ""))[:220]
        e["theses"] = [{"thesis": _clean(x.get("thesis")), "status": "baseline", "evidence": _clean(x.get("evidence"))}
                       for x in a.get("investment_theses") or [] if isinstance(x, dict)]
        e["filing_date"] = a.get("filing_date")
    else:
        q = sorted({k for x in a.get("thesis_check") or [] for k in (x.get("statuses") or {})} |
                   {k for x in a.get("company_kpis") or [] if isinstance(x, dict) for k in (x.get("values") or {})},
                   key=_qkey)
        e["title"] = "Earnings Review" + (f" bis {q[-1]}" if q else "")
        e["quarters"] = q
        e["headline"] = _clean(a.get("headline"))
        e["theses"] = [{"thesis": _clean(x.get("thesis")), "status": x.get("current_status"),
                        "statuses": x.get("statuses") or {}, "evidence": _clean(x.get("evidence"))}
                       for x in a.get("thesis_check") or [] if isinstance(x, dict)]
        e["kpis"] = [{"name": k.get("name"), "unit": k.get("unit"), "values": k.get("values") or {},
                      "good": k.get("good_direction", "up")}
                     for k in a.get("company_kpis") or [] if isinstance(k, dict)]
    return e


def _qkey(q):
    m = re.match(r"Q(\d)\s*FY(\d{4})", str(q))
    return (int(m.group(2)), int(m.group(1))) if m else (0, 0)


# =============================================================== Archiv
def load_index():
    return _load(INDEX) or []


def archive_reports(build_pages=True):
    """Legt neue oder geaenderte Reports mit Datum im Archiv ab (bereits archivierte werden erkannt, md5)."""
    idx = load_index()
    known = {e["md5"] for e in idx}
    added = []
    for t, kind, args, fy in current_reports():
        try:
            h = _md5(args)
        except OSError:
            continue
        if h in known:
            continue
        e = _summary(t, kind, args, fy)
        e["md5"] = h
        e["id"] = f"{t}_{kind}_{e['date']}_{h[:6]}".replace(".", "-")
        dest = ARCH / t / e["id"]
        dest.mkdir(parents=True, exist_ok=True)
        stem = Path(args).name[: -len("_build_args.json")]
        shutil.copy2(args, dest / Path(args).name)
        fc = _fc_path(args)
        if fc:
            shutil.copy2(fc, dest / (stem + "_factcheck.json"))
        pdf = _pdf_path(args)
        if pdf:
            shutil.copy2(pdf, dest / Path(pdf).name)
            e["pdf"] = str((dest / Path(pdf).name).relative_to(AIF)).replace("\\", "/")
        e["args"] = str((dest / Path(args).name).relative_to(AIF)).replace("\\", "/")
        idx.append(e)
        known.add(h)
        added.append(e)
    if added:
        ARCH.mkdir(parents=True, exist_ok=True)
        json.dump(idx, open(INDEX, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    if build_pages:
        archive_pages(idx)
    return added


def archive_pages(idx=None, out_dir=None):
    """Je Archiv-Eintrag eine Report-Seite (mit Faktencheck-Markierung) unter reports/site/archive_<id>.html."""
    from .html_site import report_page
    out_dir = Path(out_dir or REPORTS / "site")
    out_dir.mkdir(parents=True, exist_ok=True)
    for e in idx or load_index():
        name = out_dir / f"archive_{e['id']}.html"
        if name.exists():
            continue
        args = AIF / e["args"]
        if not args.exists():
            continue
        stem = args.name[: -len("_build_args.json")]
        rep = {"args": str(args), "factcheck": str(args.parent / (stem + "_factcheck.json")),
               "agent": "Annual report agent" if e["kind"] == "annual" else "Earnings reviewer",
               "title": f"{e['ticker']} {e['title']}", "slug": f"archive_{e['id']}", "ticker": e["ticker"],
               "date": e["date"],
               "pdf_rel": os.path.relpath(AIF / e["pdf"], out_dir).replace("\\", "/") if e.get("pdf") else None}
        try:
            report_page(rep, out_dir)
        except Exception as ex:
            print(f"Archivseite {e['id']} nicht erzeugt: {ex}")


# =============================================================== Firmenliste und Firmen-Dashboard
def _brief():
    files = sorted(glob.glob(str(RESEARCH / "briefs" / "brief_*.json")))
    return _load(files[-1]) if files else {}


def companies():
    """Kacheln fuer den Research-Reiter: alle Firmen mit Reports, Depotpositionen zuerst."""
    idx = load_index()
    brief = _brief() or {}
    bpos = {p["ticker"].upper(): p for p in brief.get("positions") or []}
    dash = _load(RESEARCH / "portfolio_dashboard.json") or {}
    dpos = {p["ticker"].upper(): p for p in dash.get("positions") or []}
    tick = list(dict.fromkeys(list(bpos) + sorted({e["ticker"] for e in idx})))
    out = []
    for t in tick:
        es = sorted([e for e in idx if e["ticker"] == t], key=lambda e: e["date"], reverse=True)
        last_e = next((e for e in es if e["kind"] == "earnings"), None)
        last_a = next((e for e in es if e["kind"] == "annual"), None)
        th = [x.get("status") for x in (last_e or {}).get("theses") or [] if x.get("status")]
        tally = {s: th.count(s) for s in ("strengthened", "intact", "weakened", "broken")}
        b, d = bpos.get(t, {}), dpos.get(t, {})
        out.append({"t": t, "name": b.get("name") or (d.get("name") if d.get("name") != t else None) or t,
                    "in_portfolio": t in bpos, "w": _num(b.get("weight")) or _num(d.get("weight")),
                    "level": b.get("level"), "tally": tally, "n_reports": len(es),
                    "last": es[0]["date"] if es else None,
                    "headline": (last_e or last_a or {}).get("headline") or "",
                    "has_annual": bool(last_a), "has_earnings": bool(last_e),
                    "fc": [(e["fc_matched"], e["fc_total"]) for e in es[:1]][0] if es else None})
    return out


def _kpi_hist(t):
    """Firmen-KPIs als Zeitreihe ueber alle Earnings Reviews (siehe kpi_history)."""
    try:
        from .kpi_history import history
        return history(t, min_points=2)
    except Exception:
        return []


def _thesis_rows(t, last_e, last_a):
    """Thesen mit Status je Quartal (Thesen-Log + Earnings Review) und Ausgangsbeleg aus dem Annual Report."""
    rows = []
    log = _load(REPORTS / "thesis_logs" / f"{t}_thesis_log.json") or []
    latest = log[-1] if log else {}
    src = (last_e or {}).get("theses") or [{"thesis": x.get("thesis"), "status": x.get("current_status"),
                                             "statuses": x.get("statuses") or {}} for x in latest.get("theses") or []]
    base = {re.sub(r"^T\d+:\s*", "", x["thesis"] or "")[:60].lower(): x for x in (last_a or {}).get("theses") or []}
    for x in src:
        key = re.sub(r"^T\d+:\s*", "", x.get("thesis") or "")[:60].lower()
        b = base.get(key) or {}
        sig = next((y.get("signpost") for y in latest.get("theses") or [] if (y.get("thesis") or "")[:60] ==
                    (x.get("thesis") or "")[:60]), None)
        rows.append({"thesis": x.get("thesis"), "status": x.get("status"), "statuses": x.get("statuses") or {},
                     "evidence": x.get("evidence") or "", "baseline": b.get("evidence") or "", "signpost": _clean(sig)})
    if not rows and last_a:
        rows = [{"thesis": x["thesis"], "status": "baseline", "statuses": {}, "evidence": "",
                 "baseline": x.get("evidence") or "", "signpost": ""} for x in last_a.get("theses") or []]
    return rows


def _tracker(t, news):
    try:
        from .thesis_tracker import tracker
        return tracker(t, news=news)
    except Exception as e:
        return {"error": str(e)[:160]}


def company_payload(t):
    t = t.upper()
    idx = load_index()
    es = sorted([e for e in idx if e["ticker"] == t], key=lambda e: (e["date"], e["kind"]), reverse=True)
    last_e = next((e for e in es if e["kind"] == "earnings"), None)
    last_a = next((e for e in es if e["kind"] == "annual"), None)
    ea = _load(AIF / last_e["args"]) if last_e else {}
    aa = _load(AIF / last_a["args"]) if last_a else {}
    brief = _brief() or {}
    b = next((p for p in brief.get("positions") or [] if p["ticker"].upper() == t), {})
    dash = _load(RESEARCH / "portfolio_dashboard.json") or {}
    d = next((p for p in dash.get("positions") or [] if p["ticker"].upper() == t), {})
    q = (_load(RESEARCH / "quotes.json") or {}).get("data", {}).get(t, {})

    kpis = []
    for k in (ea or {}).get("company_kpis") or []:
        vals = k.get("values") or {}
        qs = sorted(vals, key=_qkey)
        pv = k.get("prior_values") or {}
        kpis.append({"name": k.get("name"), "unit": k.get("unit"), "good": k.get("good_direction", "up"),
                     "q": qs, "v": [_num(vals[x]) for x in qs], "p": [_num(pv.get(x)) for x in qs],
                     "src": k.get("source")})

    news = []
    try:
        from .app_backend import notable_news
        news = [{"date": s.get("date", "")[:10], "title": s.get("title", ""), "url": s.get("url", ""),
                 "dir": s.get("direction", "neutral"), "car": _num(s.get("car01"))}
                for s in notable_news([t], days=30, limit=8)]
    except Exception:
        pass
    ev = _load(RESEARCH / "events.json") or {}
    today = date.today().isoformat()
    events = [x for x in ev.get("upcoming", []) if x.get("ticker", "").upper() == t and x["date"] >= today][:5]
    stories = []
    try:
        from . import pipeline as pl
        stories = [{"title": s.get("title"), "status": s.get("status"), "since": s.get("since")}
                   for s in (pl.last_news().get("stories") or {}).get(t, [])][:4]
    except Exception:
        pass
    forecast = None
    try:
        from . import pipeline as pl
        forecast = pl.last_forecast(t)
    except Exception:
        pass

    return {
        "t": t, "name": b.get("name") or (d.get("name") if d.get("name") != t else None) or t,
        "sector": d.get("sector"), "w": _num(b.get("weight")) or _num(d.get("weight")), "level": b.get("level"),
        "triggers": [{"level": x.get("level"), "text": x.get("text"), "source": x.get("source")}
                     for x in b.get("triggers") or []],
        "chg": _num(q.get("chg")), "ret1y": _num(d.get("ret_1y")) or _num(b.get("ret_1y")),
        "rc": _num(b.get("risk_contrib")) or _num(d.get("risk_contrib")),
        "pe": _num(d.get("forward_pe")), "upside": _num(d.get("upside")), "growth": _num(d.get("revenue_growth")),
        "headline": _clean((ea or {}).get("headline")), "summary": _clean((ea or {}).get("summary")),
        "outlook": _clean((ea or {}).get("outlook")), "risk_update": _clean((ea or {}).get("risk_update")),
        "takeaways": [_clean(x) for x in (aa or {}).get("key_takeaways") or []][:5],
        "annual_summary": _clean((aa or {}).get("investment_summary")),
        "annual_fy": (last_a or {}).get("fy"), "earnings_date": (last_e or {}).get("date"),
        "annual_date": (last_a or {}).get("date"), "quarters": (last_e or {}).get("quarters") or [],
        "kpis": kpis, "kpi_hist": _kpi_hist(t), "theses": _thesis_rows(t, last_e, last_a),
        "news": news, "events": events, "stories": stories, "forecast": forecast, "tracker": _tracker(t, news),
        "reports": [{k: e.get(k) for k in ("id", "kind", "date", "title", "headline", "fy", "fc_matched", "fc_total",
                                           "theses", "kpis", "quarters", "pdf")} for e in es],
    }
