"""
Briefing-Agent: eine Seite pro Woche ueber alle Agenten - wo ist eine Entscheidung noetig, wo sollte man sich
einlesen, wo ist nichts zu tun.

Arbeitsteilung wie bei den anderen Agenten:
- Python sammelt die Ergebnisse der anderen Agenten aus den Dateien (Thesen-Protokoll und Earnings Reviews,
  News-Signale und Thesis Alerts, Committee, Forecaster, Portfolio-Snapshot des Portfolio Managers) und legt mit
  festen Regeln fest, welche Position in welche Stufe faellt (decide / read / no action) und warum.
- Das Sprachmodell schreibt nur die Texte (was ist passiert, warum zaehlt es, naechster Schritt) und darf die Stufen
  nicht aendern. Danach automatischer Faktencheck mit einer Korrekturrunde.

Ergebnis: reports/brief_<modell>/brief_<datum>.pdf und research/briefs/brief_<datum>.json (Ausloeser, fuer die
Evaluation: hat der Brief die richtigen Faelle gefunden?).
"""
import glob
import json
import os
from datetime import date, timedelta
from pathlib import Path
from textwrap import dedent
from typing import Annotated, List
from xml.sax.saxutils import escape

import pandas as pd

from .style import STYLE_RULES
from . import agent_settings as _AS  # Prompts/Parameter aus der App (research/agent_settings.json)

AIF = Path(__file__).resolve().parents[1]
REPORTS = AIF / "reports"
RESEARCH = AIF / "research"
SNAPSHOT = RESEARCH / "portfolio_snapshot.json"
LEVELS = {"decide": 3, "read": 2, "none": 1}
LEVEL_LABEL = {"decide": "Decision needed", "read": "Read up", "none": "No action"}
_ROUNDS = {}


# =============================================================== Portfolio-Snapshot (schreibt der Portfolio Manager)
def _user_status(t, triggers):
    """Status/Notiz aus dem Handlungsbedarf der App (nur solange keine neuen Ausloeser dazugekommen sind)."""
    try:
        from .action_state import status
        s_ = status(t, triggers)
    except Exception:
        return None
    if not s_:
        return None
    label = {"done": "marked as handled", "seen": "acknowledged, no action yet", "hidden": "dismissed"}.get(s_["state"])
    return f"{label} by the user on {s_.get('date')}" + (f", user note: \"{s_['note'][:300]}\"" if s_.get("note") else "")


def save_portfolio_snapshot(a, perf=None, name="portfolio", title="Portfolio", path=SNAPSHOT):
    """Gewichte, Risikoanteile, Sektoren und Kerndaten der Performance fuer den Briefing-Agenten."""
    snap = {"date": a.get("date") or date.today().isoformat(), "name": name, "title": title, "cap": a.get("cap"),
            "sector_cap": a.get("sector_cap"),
            "positions": {p["ticker"]: {k: p.get(k) for k in ("name", "sector", "weight", "risk_contrib", "ret_1y", "vol",
                                                               "upside")} for p in a.get("positions", [])},
            "structure": {k: a.get("structure", {}).get(k) for k in ("sector", "top5", "effective_n")}}
    if perf:
        per = {r["period"]: {k: r.get(k) for k in ("ttwror", "bench", "diff", "mwr")} for r in perf.get("periods") or []
               if r}
        snap["performance"] = {"start": perf.get("start"), "ttwror_pa": perf.get("ttwror_pa"),
                               "bench_ttwror_pa": perf.get("bench_ttwror_pa"), "periods": per,
                               "mistakes": [{k: d.get(k) for k in ("date", "type", "ticker", "impact_eur", "kind")}
                                            for d in perf.get("mistakes") or []][:5]}
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(snap, open(path, "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=float)
    return snap


def load_snapshot(path=SNAPSHOT):
    return json.load(open(path, encoding="utf-8")) if Path(path).exists() else None


# =============================================================== Eingaben aus den anderen Agenten
def _review_evidence(review):
    """Belege je These aus dem Earnings Review, auf den das Thesen-Protokoll verweist (build_args.json daneben)."""
    p = str((review or {}).get("report") or "").replace("\\", "/")
    if not p:
        return {}
    cands = [Path(os.path.splitext(str(b))[0] + "_build_args.json") for b in (Path(p), AIF / "notebooks" / p, AIF / p)]
    cands += [Path(h) for h in glob.glob(str(REPORTS / "**" / (Path(os.path.splitext(str(p))[0]).name + "_build_args.json")),
                                         recursive=True)]
    ba = next((c for c in cands if c.exists()), None)
    if not ba:
        return {}
    try:
        args = json.load(open(ba, encoding="utf-8"))
    except Exception:
        return {}
    return {str(x.get("thesis", ""))[:120]: str(x.get("evidence", "")) for x in args.get("thesis_check") or []}


def _latest_digest():
    """Thesis Alerts und Positionsnotizen des neuesten News-Digests."""
    files = sorted(glob.glob(str(REPORTS / "news_*" / "*_news_digest_build_args.json")), key=os.path.getmtime)
    if not files:
        return {"date": None, "alerts": {}, "notes": {}}
    p = files[-1]
    a = json.load(open(p, encoding="utf-8"))
    alerts, notes = {}, {}
    for x in a.get("thesis_alerts") or []:
        alerts.setdefault(str(x.get("ticker", "")).upper(), []).append(x)
    for x in a.get("position_notes") or []:
        notes[str(x.get("ticker", "")).upper()] = x
    d = os.path.basename(p)[5:15] if os.path.basename(p).startswith("news_") else None
    return {"date": d, "alerts": alerts, "notes": notes}


def next_earnings(ticker):
    """Naechster Termin fuer Quartalszahlen (Yahoo); None, wenn unbekannt."""
    try:
        import yfinance as yf
        cal = yf.Ticker(ticker).calendar
        d = cal.get("Earnings Date") if isinstance(cal, dict) else None
        d = d[0] if isinstance(d, (list, tuple)) and d else d
        return pd.Timestamp(d).date().isoformat() if d is not None else None
    except Exception:
        return None


def _review_tail(review):
    """Status der Thesen im letzten Quartal: (These, Status, Verlauf)."""
    out = []
    for t in (review or {}).get("theses", []):
        st = (t.get("current_status") or t.get("status") or "n/a").lower()
        hist = t.get("statuses") or {}
        out.append({"thesis": str(t.get("thesis", "")), "signpost": str(t.get("signpost", "")), "status": st,
                    "history": hist})
    return out


def _tracker_tail(sym):
    """Thesen-Status aus dem Thesis Tracker (Quarter Records), falls vorhanden: (Thesen, Quartal, Datum, Hinweise)."""
    try:
        from .thesis_tracker import tracker
        tr = tracker(sym)
    except Exception:
        return None
    if not tr.get("book") or not tr.get("records"):
        return None
    theses = [{"thesis": x["thesis"], "signpost": x["signpost"], "status": x["status"] or "n/a",
               "history": {c["q"]: c["status"] for c in x["timeline"] if c["status"]}} for x in tr["theses"]]
    checks = [f"{x['id']} {x['short']}: {x['check']}" for x in tr["theses"] if x.get("check")]
    last = tr["records"][-1]
    return {"theses": theses, "label": last["label"], "end": last["end"], "checks": checks}


def collect(tickers, today=None, earnings=None, snapshot=None, news=None, digest=None, cap=None, stale_days=120,
            earnings_window=14):
    """Alle Ausloeser je Position und fuer das Portfolio. earnings: dict {ticker: datum} oder Funktion (Standard: Yahoo)."""
    from . import pipeline as pl
    today = pd.Timestamp(today or date.today())
    snapshot = snapshot if snapshot is not None else load_snapshot()
    news = news if news is not None else pl.last_news()
    digest = digest if digest is not None else _latest_digest()
    pos_snap = (snapshot or {}).get("positions", {})
    cap = cap or _AS.param("brief.cap", None) or (snapshot or {}).get("cap") or 0.10
    stale_days = _AS.param("brief.stale_days", stale_days)
    earnings_window = _AS.param("brief.earnings_window", earnings_window)
    get_e = earnings if callable(earnings) else (lambda t: (earnings or {}).get(t)) if earnings is not None else next_earnings
    sig_all = news.get("signals") or {}
    rows, gaps = [], []
    universe = list(dict.fromkeys(list(tickers) + [t for t in pos_snap if t not in tickers]))
    for t in universe:
        sym = t.split(".")[0] if not pl.is_us(t) else t
        ps = pos_snap.get(t, {})
        w, rc = ps.get("weight"), ps.get("risk_contrib")
        review = pl.last_review(sym)
        theses = _review_tail(review)
        trk = _tracker_tail(sym)                  # Thesis Tracker: Quartal fuer Quartal, hat Vorrang vor dem Sammel-Review
        if trk:
            theses = trk["theses"]
        ev = _review_evidence(_last_log(sym))
        com, fc, rep = pl.last_committee(sym), pl.last_forecast(sym), pl.agent_report(sym)
        sig = sig_all.get(t, {})
        flags = sig.get("flags") or []
        stories = (news.get("stories") or {}).get(t) or []
        alerts = digest["alerts"].get(t.upper(), [])
        e_date = get_e(t) if t in tickers else None
        trig = []

        def add(level, code, text, src):
            trig.append({"level": level, "code": code, "text": text, "source": src})

        broken = [x for x in theses if x["status"] == "broken"]
        weak = [x for x in theses if x["status"] == "weakened"]
        rev_src = f"thesis tracker {trk['label']}" if trk else (f"earnings review {review['date']}" if review else "")
        for c in (trk or {}).get("checks", []):
            add("read", "thesis_milestones", f"Thesis tracker: {c}"[:220], rev_src)
        for x in broken:
            add("decide", "thesis_broken", f"Thesis broken: {x['thesis'][:140]}", rev_src)
        if w is not None and w > cap + 1e-9:
            if broken or weak:
                parts = ([f"{len(broken)} thesis broken"] if broken else []) + ([f"{len(weak)} weakened"] if weak else [])
                add("decide", "overweight_weak_thesis", f"Weight {w * 100:.1f}% is above the {cap * 100:.0f}% position "
                    f"limit while " + " and ".join(parts), "portfolio snapshot")
            else:
                add("read", "overweight", f"Weight {w * 100:.1f}% is above the {cap * 100:.0f}% position limit",
                    "portfolio snapshot")
        if com and com.get("recommendation") == "sell":
            add("decide", "committee_sell", f"Investment committee voted sell on {com['date']}"
                + (f" (6-month target {com['target']:.2f})" if com.get("target") else ""), f"committee {com['date']}")
        for a in alerts:
            st = str(a.get("status", "")).lower()
            if st in ("challenged", "at risk"):
                add("decide" if st == "challenged" else "read", "news_thesis_alert",
                    f"News {st} a thesis: {str(a.get('thesis', ''))[:100]} - {str(a.get('evidence', ''))[:160]}",
                    f"news digest {digest['date']}")
        for x in weak:
            add("read", "thesis_weakened", f"Thesis weakened: {x['thesis'][:140]}", rev_src)
        if w and rc and rc >= 1.3 * w and rc >= 0.12:
            add("read", "risk_concentration", f"Share of portfolio risk {rc * 100:.1f}% vs weight {w * 100:.1f}%",
                "portfolio snapshot")
        for f in flags:
            if f.startswith("escalating story"):
                add("read", "story_escalating", f[0].upper() + f[1:], f"news signals {news.get('date')}")
            elif f.startswith("divergence"):
                add("read", "news_price_divergence", f[0].upper() + f[1:]
                    + (f" (stock vs MSCI ACWI {sig['period_ar'] * 100:+.1f}%)" if sig.get("period_ar") is not None else ""),
                    f"news signals {news.get('date')}")
            elif f.startswith("news volume") or f.startswith("first notable"):
                add("read", "news_volume", f[0].upper() + f[1:], f"news signals {news.get('date')}")
            elif f.startswith("negative analyst"):
                add("read", "analyst_negative", "Negative analyst revisions over 90 days", f"news signals {news.get('date')}")
            elif f.startswith("positive analyst"):
                add("none", "analyst_positive", "Positive analyst revisions over 90 days", f"news signals {news.get('date')}")
        if e_date:
            dd = (pd.Timestamp(e_date) - today).days
            if 0 <= dd <= earnings_window:
                add("read", "earnings_soon", f"Quarterly results expected on {e_date} (in {dd} days)", "Yahoo Finance")
        for x in theses:
            if x["status"] == "strengthened":
                add("none", "thesis_strengthened", f"Thesis strengthened: {x['thesis'][:140]}", rev_src)
        # Datenluecken
        if t in tickers and pl.is_us(t) and not rep:
            gaps.append(f"{t}: no annual report of the agent yet")
        if review and (today - pd.Timestamp(review["date"])).days > stale_days:
            gaps.append(f"{t}: last earnings review {review['date']} is older than {stale_days} days")
        if t in tickers and pl.is_us(t) and rep and not review:
            gaps.append(f"{t}: annual report exists but no earnings review yet")
        if t in tickers and t not in sig_all:
            gaps.append(f"{t}: not covered by the latest news run")
        level = max((x["level"] for x in trig), key=lambda k: LEVELS[k], default="none")
        rows.append({"ticker": t, "name": ps.get("name"), "weight": w, "risk_contrib": rc, "ret_1y": ps.get("ret_1y"),
                     "level": level, "triggers": trig, "theses": theses, "evidence": ev,
                     "review_date": review["date"] if review else None, "committee": com, "forecast": fc,
                     "sentiment": sig.get("sentiment"), "period_ar": sig.get("period_ar"),
                     "stories": stories[:3], "news_note": digest["notes"].get(t.upper()), "next_earnings": e_date})
    rows.sort(key=lambda r: (-LEVELS[r["level"]], -(r["weight"] or 0)))
    port = []
    st = (snapshot or {}).get("structure") or {}
    sc = (snapshot or {}).get("sector_cap") or 0.35
    for s, v in (st.get("sector") or {}).items():
        if v and v > sc + 1e-9:
            port.append({"level": "read", "text": f"Sector {s} at {v * 100:.1f}% is above the {sc * 100:.0f}% sector limit"})
    if st.get("top5") and st["top5"] > 0.6:
        port.append({"level": "read", "text": f"Top five positions hold {st['top5'] * 100:.1f}% of the portfolio"})
    perf = (snapshot or {}).get("performance") or {}
    one = (perf.get("periods") or {}).get("1Y") or (perf.get("periods") or {}).get("1 year")
    if one and one.get("diff") is not None and one["diff"] <= -0.05:
        port.append({"level": "read", "text": f"Last 12 months: portfolio {one['ttwror'] * 100:+.1f}% vs MSCI ACWI "
                                              f"{one['bench'] * 100:+.1f}% (TTWROR)"})
    if snapshot is None:
        gaps.append("no portfolio snapshot yet: run the portfolio manager (pipeline step 'portfolio') first")
    elif (today - pd.Timestamp(snapshot["date"])).days > 8:
        gaps.append(f"portfolio snapshot from {snapshot['date']} is more than a week old")
    if not news.get("date"):
        gaps.append("no news run yet")
    elif (today - pd.Timestamp(str(news["date"]))).days > 8:
        gaps.append(f"latest news run {news['date']} is more than a week old")
    return {"date": today.date().isoformat(), "cap": cap, "positions": rows, "portfolio": port, "gaps": gaps,
            "snapshot_date": (snapshot or {}).get("date"), "news_date": news.get("date"), "digest_date": digest.get("date"),
            "performance": perf or None, "structure": st or None, "sector_cap": sc}


def _last_log(sym):
    from .quarterly_data import load_thesis_log
    log = load_thesis_log(sym.upper())
    return log[-1] if log else None


def _p(x, d=1):
    return f"{x * 100:.{d}f}%" if isinstance(x, (int, float)) else "n/a"


def brief_lines(data):
    """Eingaben als Zeilen mit Herkunft [(Text, Herkunft)] - Grundlage fuer das Sprachmodell und den Faktencheck."""
    L = []
    add = lambda text, origin=None: L.append((text, origin))
    snap, nd, dd = data["snapshot_date"], data["news_date"], data["digest_date"]
    add(f"WEEKLY BRIEF INPUTS as of {data['date']} (portfolio snapshot {snap}, news signals "
        f"{nd}, news digest {dd}; position limit {_p(data['cap'], 0)}). The level of each "
        f"position is set by fixed rules and must not be changed. Cite as [1].", "Brief rules")
    for lvl in ("decide", "read", "none"):
        rs = [r for r in data["positions"] if r["level"] == lvl]
        add(f"\n{LEVEL_LABEL[lvl].upper()} ({len(rs)} positions):")
        for r in rs:
            t = r["ticker"]
            add(f"- {t}" + (f" ({r['name']})" if r.get("name") else "") + f": weight {_p(r['weight'])}, "
                f"share of risk {_p(r['risk_contrib'])}, 1-year return {_p(r['ret_1y'])}", f"{t} · Portfolio snapshot {snap}")
            for tr in r["triggers"]:
                add(f"    trigger [{tr['level']}] {tr['text']} ({tr['source']})", f"{t} · {str(tr['source'])[:1].upper()}{str(tr['source'])[1:]}")
            us = _user_status(t, r["triggers"]) if lvl in ("decide", "read") else None
            if us:
                add(f"    user status: {us}. Acknowledge it in one short clause (e.g. 'held deliberately since ...') and do "
                    "not demand the same decision again; the level stays as set by the rules", f"{t} · User notes")
            if r["theses"]:
                add(f"    theses after the earnings review of {r['review_date']}: " + "; ".join(
                    f"{x['thesis'][:90]} = {x['status']}" for x in r["theses"]), f"{t} · Earnings review {r['review_date']}")
            for x in r["theses"]:
                e = r["evidence"].get(x["thesis"][:120])
                if e and x["status"] in ("broken", "weakened", "strengthened"):
                    add(f"    evidence ({x['status']}): {e[:400]}", f"{t} · Earnings review {r['review_date']}, thesis evidence")
            if r.get("news_note"):
                add(f"    news digest note: {str(r['news_note'].get('note', ''))[:300]}", f"{t} · News digest {dd}")
            if r.get("stories"):
                add("    developing stories: " + "; ".join(f"{s['title']} ({s['status']})" for s in r["stories"]),
                    f"{t} · News tracker stories {nd}")
            if r.get("period_ar") is not None:
                add(f"    stock vs MSCI ACWI in the news week: {r['period_ar'] * 100:+.1f}%", f"{t} · News signals {nd}")
            if r.get("forecast"):
                f = r["forecast"]
                add(f"    weekly forecast {f['date']}: {f['direction']} {f.get('low')}-{f.get('high')}% "
                    f"(low reliability: the forecaster gave the same range for all positions)", f"{t} · Forecaster {f['date']}")
            if r.get("next_earnings"):
                add(f"    next quarterly results: {r['next_earnings']}", f"{t} · Yahoo Finance calendar")
    st = data.get("structure") or {}
    if st:
        add("\nPORTFOLIO STRUCTURE: top five positions " + _p(st.get("top5")) + ", effective number of positions "
            + (f"{st['effective_n']:.1f}" if st.get("effective_n") else "n/a") + "; sectors: " + ", ".join(
                f"{k} {_p(v)}" for k, v in (st.get("sector") or {}).items()) + f"; sector limit {_p(data.get('sector_cap'), 0)}",
            f"Portfolio snapshot {snap}")
    if data["portfolio"]:
        add("\nPORTFOLIO-LEVEL TRIGGERS:")
        for x in data["portfolio"]:
            add(f"- [{x['level']}] {x['text']}", f"Portfolio snapshot {snap}")
    perf = data.get("performance") or {}
    if perf.get("periods"):
        add("\nREALISED PERFORMANCE (TTWROR vs MSCI ACWI): " + "; ".join(
            f"{k} {_p(v.get('ttwror'))} vs {_p(v.get('bench'))}" for k, v in perf["periods"].items()),
            "Portfolio manager, transaction history")
    if data["gaps"]:
        add("\nDATA GAPS (say what is missing, do not fill it): " + " | ".join(data["gaps"]), "Data gaps")
    return L


def brief_text(data):
    """Eingaben fuer das Sprachmodell (und Quelle fuer den Faktencheck)."""
    return "\n".join(text for text, _ in brief_lines(data))


def brief_source(data, label="[1] Agent outputs"):
    """Faktencheck-Quelle mit Herkunft je Zeile (welcher Agent, welches Datum)."""
    from finrobot.functional.fact_check import SourceIndex
    src = SourceIndex(label)
    for text, origin in brief_lines(data):
        try:
            src.add_text(text, origin=origin)
        except TypeError:  # aeltere fact_check-Version ohne Herkunft
            src.add_text(text)
    return src


def recheck_brief(brief_json, build_args_json, out_path=None):
    """Faktencheck eines vorhandenen Briefs neu rechnen (offline, ohne Sprachmodell), z. B. mit Herkunftsangaben."""
    from finrobot.functional.fact_check import run_fact_check, save_json
    data = json.load(open(brief_json, encoding="utf-8"))
    texts = json.load(open(build_args_json, encoding="utf-8"))
    fc = run_fact_check(_sections(texts), [brief_source(data)], None)
    if out_path:
        save_json(fc, out_path)
    return fc


def _sections(texts):
    secs = [("Headline", texts.get("headline", "")), ("Summary", texts.get("summary", "")),
            ("No action", texts.get("no_action_note") or ""), ("Portfolio", texts.get("portfolio_note") or "")]
    for x in texts.get("items") or []:
        for k in ("what", "why", "next_step"):
            secs.append((f"{x.get('ticker')} {k}", str(x.get(k, ""))))
    return secs


# =============================================================== PDF
def _build_pdf(pdf_path, title, texts, data, fc):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from finrobot.functional.reportlab import REPORT_BRAND, REPORT_COLOR, _heading_font, _paragraphs, _tint

    NAVY, GREY = colors.HexColor(REPORT_COLOR), colors.HexColor("#5A6472")
    LCOL = {"decide": colors.HexColor("#B03A2E"), "read": colors.HexColor("#B9770E"), "none": colors.HexColor("#2D8A4E")}
    page_w, page_h = A4
    m = 1.6 * cm
    usable = page_w - 2 * m
    ss = getSampleStyleSheet()
    hf = _heading_font()
    body = ParagraphStyle("BodyB", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.2,
                          alignment=TA_JUSTIFY, spaceAfter=5)
    small = ParagraphStyle("SmallB", parent=body, fontSize=7, leading=9, textColor=GREY, alignment=0)
    cell = ParagraphStyle("CellB", parent=body, fontSize=7.6, leading=9.4, alignment=0, spaceAfter=0)
    cell_w = ParagraphStyle("CellWB", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    h1 = ParagraphStyle("H1B", parent=body, fontName=hf, fontSize=20, leading=24, textColor=NAVY, alignment=0)
    h2 = ParagraphStyle("H2B", parent=body, fontName=hf, fontSize=13, leading=16, textColor=NAVY, alignment=0,
                        spaceBefore=8, spaceAfter=2)
    head = ParagraphStyle("HeadB", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=14.5, alignment=0)
    item_h = ParagraphStyle("ItemB", parent=body, fontName="Helvetica-Bold", fontSize=10, leading=13, alignment=0,
                            spaceBefore=4, spaceAfter=1)
    exh = ParagraphStyle("ExhB", parent=cell, fontName="Helvetica-Bold", textColor=NAVY, fontSize=8.5, spaceBefore=6,
                         spaceAfter=3)
    line = TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("LINEBELOW", (0, -1), (-1, -1), 0.8, NAVY),
                       ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_tint(REPORT_COLOR, 0.96))]),
                       ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 2)])

    def heading(t):
        return [Paragraph(t, h2), HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceBefore=1, spaceAfter=5)]

    def badge(lvl):
        return f"<font color='{LCOL[lvl].hexval().replace('0x', '#')}'><b>{LEVEL_LABEL[lvl]}</b></font>"

    pos = data["positions"]
    n = {k: sum(r["level"] == k for r in pos) for k in LEVELS}
    content = [Paragraph(escape(title), h1), Spacer(1, 3), Paragraph(escape(texts["headline"]), head), Spacer(1, 2),
               Paragraph(f"As of {data['date']} | {len(pos)} positions: {n['decide']} decision needed, {n['read']} read up, "
                         f"{n['none']} no action | Generated by {REPORT_BRAND}", small), Spacer(1, 6)]
    content += _paragraphs(texts["summary"], body)
    rows = [["Position", "Weight", "Level", "Why (rule-based triggers)"]]
    for r in pos:
        why = "<br/>".join(escape(x["text"]) for x in sorted(r["triggers"], key=lambda x: -LEVELS[x["level"]])[:4]) or \
            "no trigger"
        rows.append([f"<b>{escape(r['ticker'])}</b>", _p(r["weight"]), badge(r["level"]), why])
    t = Table([[Paragraph(str(c), cell_w if i == 0 else cell) for c in row] for i, row in enumerate(rows)],
              colWidths=[usable * 0.11, usable * 0.09, usable * 0.16, usable * 0.64], repeatRows=1)
    t.setStyle(line)
    content += [Paragraph("Exhibit 1: Action board", exh), t,
                Paragraph("Source: rule-based triggers from the outputs of the other agents [1]; levels are set by code, "
                          "not by the language model.", small)]
    items = {str(x.get("ticker", "")).upper(): x for x in texts.get("items") or []}
    for lvl, title_ in (("decide", "Decision Needed"), ("read", "Read Up")):
        rs = [r for r in pos if r["level"] == lvl]
        if not rs:
            continue
        first = True
        for r in rs:
            it = items.get(r["ticker"].upper(), {})
            block = [Paragraph(f"{escape(r['ticker'])}" + (f" - {escape(r['name'])}" if r.get("name") else "") +
                               f"  <font size=8 color='#5A6472'>weight {_p(r['weight'])}</font>", item_h)]
            for lab, k in (("What happened", "what"), ("Why it matters", "why"), ("Next step", "next_step")):
                if it.get(k):
                    block.append(Paragraph(f"<b>{lab}:</b> {escape(str(it[k]))}", body))
            src = sorted({x["source"] for x in r["triggers"] if x["source"]})
            if src:
                block.append(Paragraph("Based on: " + escape("; ".join(src)), small))
            content.append(KeepTogether((heading(title_) if first else []) + block))
            first = False
    quiet = [r for r in pos if r["level"] == "none"]
    if quiet:
        content += heading("No Action This Week") + [Paragraph(escape(texts.get("no_action_note") or "") + (" " if
                    texts.get("no_action_note") else "") + "Positions: " + ", ".join(escape(r["ticker"]) for r in quiet) +
                    ".", body)]
    if data["portfolio"] or texts.get("portfolio_note"):
        content += heading("Portfolio") + _paragraphs(texts.get("portfolio_note") or "", body)
        if data["portfolio"]:
            content.append(Paragraph("Rule-based portfolio triggers: " + escape("; ".join(x["text"] for x in data["portfolio"])),
                                     small))
    if data["gaps"]:
        content += heading("Data Gaps") + [Paragraph("- " + escape(g), cell) for g in data["gaps"]]
    content += heading("How This Brief Is Made") + [Paragraph(
        "Decision needed: a thesis marked broken in the latest earnings review, a position above the position limit while "
        "a thesis is weakened or broken, a sell vote of the investment committee, or news that challenges a thesis. Read up: "
        "a weakened thesis, a position above the limit, risk share well above weight, an escalating news story, news and "
        "price moving in opposite directions, unusual news volume, negative analyst revisions, or quarterly results within "
        "14 days. The weekly forecaster is shown for context only. The language model writes the explanations; it cannot "
        "change the levels. For academic purposes only; not investment advice.", small)]
    refs = [f"Outputs of the research agents as of {data['date']}: thesis log and earnings reviews, annual report theses, "
            f"news signals ({data['news_date']}) and news digest ({data['digest_date']}), investment committee, weekly "
            f"forecaster, portfolio snapshot of the portfolio manager ({data['snapshot_date']}); earnings dates from Yahoo "
            f"Finance."]
    content += heading("Sources") + [Paragraph(f"[1] {escape(refs[0])}", ParagraphStyle("RefB", parent=body, fontSize=8.5,
                                                                                         alignment=0, leading=11))]
    rate = f"{fc['match_rate'] * 100:.0f}%" if fc["match_rate"] is not None else "n/a"
    content += [Spacer(1, 4), Paragraph(f"Automated fact check: {fc['matched']} of {fc['total_claims']} figures in the "
                                        f"agent's text were found in the inputs [1] ({rate}).", small)]
    gen = date.today().strftime("%d %B %Y")

    def deco(canv, d):
        canv.saveState()
        canv.setFillColor(NAVY)
        if d.page == 1:
            canv.rect(0, page_h - 1.15 * cm, page_w, 1.15 * cm, stroke=0, fill=1)
            canv.setFillColor(colors.white)
            canv.setFont("Helvetica-Bold", 9)
            canv.drawString(m, page_h - 0.72 * cm, "WEEKLY BRIEF")
            canv.setFont("Helvetica", 9)
            canv.drawRightString(page_w - m, page_h - 0.72 * cm, gen)
        else:
            canv.setFont("Helvetica-Bold", 8)
            canv.drawString(m, page_h - 1.0 * cm, escape(title))
            canv.setFont("Helvetica", 8)
            canv.setFillColor(GREY)
            canv.drawRightString(page_w - m, page_h - 1.0 * cm, f"Weekly Brief  |  {gen}")
            canv.setStrokeColor(NAVY)
            canv.line(m, page_h - 1.15 * cm, page_w - m, page_h - 1.15 * cm)
        canv.setStrokeColor(colors.HexColor(_tint(REPORT_COLOR, 0.75)))
        canv.line(m, 1.25 * cm, page_w - m, 1.25 * cm)
        canv.setFont("Helvetica", 7)
        canv.setFillColor(GREY)
        canv.drawString(m, 0.85 * cm, f"Generated by {REPORT_BRAND} - for academic purposes only, not investment advice")
        canv.drawRightString(page_w - m, 0.85 * cm, f"Page {d.page}")
        canv.restoreState()

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=m, rightMargin=m, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    doc.build(content, onFirstPage=deco, onLaterPages=deco)


# =============================================================== Agent
def make_tools(state):
    data = state["data"]

    def get_brief_inputs() -> str:
        """All rule-based triggers by position (level fixed by code), thesis status with evidence, news notes, stories,
        portfolio-level triggers and data gaps."""
        return brief_text(data)

    def build_brief(
        headline: Annotated[str, "one sentence (max. 25 words): what needs attention this week"],
        summary: Annotated[str, "60-150 words: the decisions first, then what to read, then that the rest needs no "
                                "action; name positions and the key figures"],
        items: Annotated[List[dict], "one entry for EVERY position with level 'decide' or 'read': {ticker, what (max. 45 "
                                     "words: what happened, with figures), why (max. 40 words: why it matters for the "
                                     "thesis or the position size), next_step (max. 25 words: a concrete check or "
                                     "question, e.g. 'confirm or retire thesis T2 before trimming', never a buy/sell "
                                     "order)}"],
        no_action_note: Annotated[str, "optional, max. 40 words on the positions without action"] = "",
        portfolio_note: Annotated[str, "optional, max. 70 words on the portfolio-level triggers and performance"] = "",
    ) -> str:
        """Build the weekly brief PDF (with automated fact check)."""
        from finrobot.functional.fact_check import run_fact_check, save_json
        need = [r["ticker"].upper() for r in data["positions"] if r["level"] in ("decide", "read")]
        got = {str(x.get("ticker", "")).upper() for x in items or [] if isinstance(x, dict)}
        problems = []
        nw = len(summary.split())
        if not 40 <= nw <= 190:
            problems.append(f"summary: {nw} words, expected 60-150")
        miss = [t for t in need if t not in got]
        if miss:
            problems.append("items missing for: " + ", ".join(miss))
        extra = sorted(got - set(need))
        if extra:
            problems.append("items only for 'decide' or 'read' positions; remove: " + ", ".join(extra))
        for x in items or []:
            if isinstance(x, dict) and not all(x.get(k) for k in ("what", "why", "next_step")):
                problems.append(f"{x.get('ticker')}: what, why and next_step are required")
                break
        if problems:
            return "PDF NOT generated. Problems: " + "; ".join(problems) + ". Fix them and call build_brief again."
        texts = dict(headline=headline, summary=summary, items=items or [], no_action_note=no_action_note or "",
                     portfolio_note=portfolio_note or "")
        os.makedirs(state["save_dir"], exist_ok=True)
        pdf_path = os.path.join(state["save_dir"], f"{state['name']}.pdf")
        base = os.path.splitext(pdf_path)[0]
        json.dump(texts, open(base + "_build_args.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        fc = run_fact_check(_sections(texts), [brief_source(data)], None)
        key = os.path.abspath(pdf_path)
        _ROUNDS[key] = _ROUNDS.get(key, 0) + 1
        if _ROUNDS[key] == 1:
            save_json(fc, base + "_factcheck_round1.json")
        save_json(fc, base + "_factcheck.json")
        try:
            _build_pdf(pdf_path, state["title"], texts, data, fc)
        except Exception:
            import traceback
            return "PDF NOT generated:\n" + traceback.format_exc()[-1500:]
        msg = f"Weekly brief generated: {pdf_path}. Fact check: {fc['matched']} of {fc['total_claims']} figures found."
        if _ROUNDS[key] == 1 and fc["unmatched"] and os.environ.get("FINROBOT_SELF_CORRECT", "1") != "0":
            lst = [f"- [{u['section']}] {u['text']}: \"{' '.join(str(u.get('context', '')).split())[:170]}\""
                   for u in fc["unmatched"][:20]]
            msg += ("\n\nSELF-CHECK (one revision round): these figures were not found in the inputs:\n" + "\n".join(lst) +
                    "\n\nCorrect or remove each, then call build_brief exactly once more. After that, reply TERMINATE.")
        return msg

    return [get_brief_inputs, build_brief]


SYSTEM = dedent("""
    You write a one-page weekly brief for a private investor who runs several research agents. Your job is triage:
    tell the reader where a decision is needed, what to read and what can wait. The level of each position is fixed by
    rules in the inputs; never change it and never add positions. Explain each trigger in plain words with the figures
    from the inputs, say why it matters for the thesis or the position size, and propose one concrete next step (a check,
    a question or which report to read). Never give buy or sell orders; 'trim', 'add' or 'exit' may only appear as an
    option to consider. Say when data is missing. Use tools one at a time; reply TERMINATE when done.
""").strip() + "\n" + STYLE_RULES


def _save_transcript(messages, save_dir, name):
    os.makedirs(save_dir, exist_ok=True)
    with open(os.path.join(save_dir, f"{name}_transcript.md"), "w", encoding="utf-8") as f:
        for m in messages:
            f.write(f"## {m.get('role')} {m.get('name') or ''}\n\n")
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                f.write(f"TOOL CALL {fn.get('name')}: {str(fn.get('arguments'))[:20000]}\n\n")
            for r in m.get("tool_responses") or []:
                f.write(f"TOOL RESPONSE: {str(r.get('content'))[:20000]}\n\n")
            if m.get("content"):
                f.write(str(m["content"])[:20000] + "\n\n")


def run_brief(llm_config, tickers, save_dir="reports/brief", name=None, title="Weekly Brief", data=None, **collect_kw):
    """Ausloeser sammeln (Python), Briefing schreiben lassen (LLM), PDF mit Faktencheck."""
    import autogen
    from finrobot.toolkits import register_toolkits
    _ROUNDS.clear()
    name = name or f"brief_{date.today().isoformat()}"
    data = data or collect(tickers, **collect_kw)
    (RESEARCH / "briefs").mkdir(parents=True, exist_ok=True)
    json.dump(data, open(RESEARCH / "briefs" / f"{name}.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False,
              default=str)
    n = {k: sum(r["level"] == k for r in data["positions"]) for k in LEVELS}
    print(f"Ausloeser: {n['decide']} Entscheidung, {n['read']} einlesen, {n['none']} ohne Handlungsbedarf; "
          f"{len(data['gaps'])} Datenluecken")
    state = {"data": data, "save_dir": save_dir, "name": name, "title": title}
    agent = autogen.AssistantAgent(name="Brief_Writer", system_message=_AS.get("brief.system", SYSTEM), llm_config=llm_config)
    proxy = autogen.UserProxyAgent(
        name="User_Proxy", human_input_mode="NEVER", max_consecutive_auto_reply=8, code_execution_config=False,
        is_termination_msg=lambda x: str(x.get("content") or "").rstrip().rstrip("*.").endswith("TERMINATE"))
    register_toolkits(make_tools(state), agent, proxy)
    msg = ("Write this week's brief. 1) Call get_brief_inputs. 2) Call build_brief with headline, summary, one item per "
           "'decide' or 'read' position, no_action_note and portfolio_note. Cite figures exactly as given and mark them "
           "[1]. If the tool returns a SELF-CHECK list, revise once and rebuild.")
    try:
        proxy.initiate_chat(agent, message=msg, cache=None)
    finally:
        _save_transcript(proxy.chat_messages.get(agent, []), save_dir, name)
    pdf = os.path.join(save_dir, f"{name}.pdf")
    print(f"\nPDF: {pdf}" if os.path.exists(pdf) else
          f"\nKein PDF erzeugt - Verlauf in {os.path.join(save_dir, name + '_transcript.md')} pruefen.")
    return state
