"""
Multi-Quarter Earnings & Thesis Reviewer (zweite Variante neben earnings_reviewer.py).

Unterschied zur ersten Variante: Statt nur das neueste Quartal deckt dieses Update ALLE Quartale seit dem
Jahresbericht ab (z. B. Q1-Q3), mit Verlauf:
- Scorecard mit einer Spalte je Quartal (jeweils vs. Vorjahresquartal), Year-to-date vs. Vorjahres-YTD und Trend.
- KPIs je Quartal, von Python berechnet und gegen die Quellen geprueft.
- Thesen-Check mit Status je Quartal (z. B. Q1 intact -> Q2 weakened).
- Thesen-Protokoll (reports/thesis_logs/<TICKER>_thesis_log.json): jedes Update haengt seinen Stand an, das
  naechste Update liest ihn und schreibt ihn fort. So entsteht ueber die Zeit eine Kette, ohne rueckwirkende Laeufe.

Beide Varianten sind unabhaengig: eigene Datei, eigenes Notebook, eigener Ausgabeordner (Zusatz "_multi").
"""
import json
import os
from datetime import date
from textwrap import dedent
from typing import Annotated, List
from xml.sax.saxutils import escape

import autogen
from finrobot.toolkits import register_toolkits

from . import quarterly_data as qd
from .earnings_reviewer import STATUSES, _arrow_font, _kpi_text, get_annual_report_baseline
from .outlook_tools import get_consensus_and_liquidity

_ROUNDS = {}


def _fy_end(ticker, fyear):
    sc = qd.multi_quarter_scorecard(ticker, fyear)
    return sc.get("fy_end"), sc


# --------------------------------------------------------------- Tools
def get_thesis_log(ticker_symbol: Annotated[str, "ticker symbol"]) -> str:
    """Thesis statuses recorded by earlier earnings updates for this company (empty if this is the first update)."""
    log = qd.load_thesis_log(ticker_symbol)
    if not log:
        return "No earlier thesis log: this is the first earnings update since the annual report."
    last = log[-1]
    lines = [f"THESIS LOG: {len(log)} earlier update(s); latest from {last['date']} covering {', '.join(last['quarters'])} "
             "(cite as [4]):"]
    for t in last["theses"]:
        hist = ", ".join(f"{q}: {s}" for q, s in t.get("statuses", {}).items())
        lines.append(f"- {t['thesis']} (signpost: {t.get('signpost', '-')}) -> {hist}")
    return "\n".join(lines)


def get_multi_quarter_scorecard(
    ticker_symbol: Annotated[str, "ticker symbol"],
    fyear: Annotated[str, "fiscal year of the annual report baseline, e.g. '2025'"],
) -> str:
    """Every quarter since the annual report: key metrics per quarter vs. the year-ago quarter, year-to-date vs. prior
    year-to-date, and the trend across the quarters, judged from a shareholder's point of view."""
    return qd.multi_scorecard_text(ticker_symbol, fyear)


def get_earnings_releases(
    ticker_symbol: Annotated[str, "ticker symbol"],
    fyear: Annotated[str, "fiscal year of the annual report baseline, e.g. '2025'"],
) -> str:
    """Texts of all quarterly earnings press releases (8-K, Item 2.02, exhibit 99.1) filed since the annual report."""
    fy_end, _ = _fy_end(ticker_symbol, fyear)
    if not fy_end:
        return "Fiscal year end not found; cannot select the releases."
    rels = qd.earnings_releases_since(ticker_symbol, fy_end)
    parts = []
    for r in rels:
        if r.get("error"):
            parts.append(f"(release not available: {r['error']})")
        else:
            parts.append(f"=== EARNINGS RELEASE filed {r['filing_date']} ({r.get('url', '')}; cite as [1]) ===\n{r['text']}")
    return "\n\n".join(parts)


def get_10q_mdna(
    ticker_symbol: Annotated[str, "ticker symbol"],
    fyear: Annotated[str, "fiscal year of the annual report baseline, e.g. '2025'"],
) -> str:
    """MD&A of every Form 10-Q since the annual report, plus the risk factor update of the latest 10-Q."""
    fy_end, _ = _fy_end(ticker_symbol, fyear)
    if not fy_end:
        return "Fiscal year end not found; cannot select the 10-Qs."
    try:
        qs = qd.tenqs_since(ticker_symbol, fy_end)
    except Exception as e:
        return f"10-Qs not available ({e})."
    if not qs:
        return "No Form 10-Q filed since the annual report."
    out = []
    for q in qs:
        secs = "\n\n".join(f"[{k}]\n{v}" for k, v in q["sections"].items())
        out.append(f"=== FORM 10-Q, quarter ended {q['report_date']} (filed {q['filing_date']}; cite as [2]) ===\n{secs}")
    return "\n\n".join(out)


# --------------------------------------------------------------- KPIs je Quartal
def evaluate_kpis_multi(kpis, labels, sources):
    from finrobot.functional.fact_check import check_claim, extract_claims
    out = []
    for k in kpis or []:
        unit = str(k.get("unit", "")).strip()
        good = str(k.get("good_direction", "up")).lower().strip()
        good = good if good in ("up", "down") else "up"
        vals, prior = k.get("values") or {}, k.get("prior_values") or {}
        cells, checks = [], []
        for lab in labels:
            cur, pri = qd._num(vals.get(lab)), qd._num(prior.get(lab))
            for v in (cur, pri):
                if v is not None:
                    cl = extract_claims(_kpi_text(v, unit))
                    checks.append(bool(cl) and all(check_claim(c, sources) for c in cl))
            if cur is None or pri is None:
                cells.append({"value": cur, "prior": pri, "change": None, "verdict": "n/a"})
                continue
            change = cur - pri if "%" in unit else (cur / pri - 1 if pri else None)
            thr = 0.5 if "%" in unit else 0.02
            if change is None or abs(change) < thr:
                verdict = "stable"
            else:
                verdict = "better" if (change > 0) == (good == "up") else "worse"
            cells.append({"value": cur, "prior": pri, "change": change, "verdict": verdict})
        out.append({"name": str(k.get("name", "")), "unit": unit, "good_direction": good, "cells": cells,
                    "verified": "yes" if checks and all(checks) else ("partial" if any(checks) else "no")})
    return out


# --------------------------------------------------------------- PDF
def _build_pdf(ticker, fyear, pdf_path, headline, summary, results, thesis, risks, outlook, sc, kpis, rels, tenqs,
               baseline, fc, labels):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from finrobot.functional.outlook import estimate_momentum
    from finrobot.functional.reportlab import (REPORT_BRAND, REPORT_COLOR, _company_name, _heading_font,
                                               _momentum_chart, _paragraphs, _scaled_image, _tint)

    NAVY, PANEL, GREY = colors.HexColor(REPORT_COLOR), colors.HexColor(_tint(REPORT_COLOR, 0.93)), colors.HexColor("#5A6472")
    GREEN, RED, AMBER = "#2D8A4E", "#B42318", "#B7791F"
    VC = {"better": GREEN, "worse": RED, "stable": "#5A6472", "n/a": "#5A6472", "improving": GREEN,
          "deteriorating": RED}
    SC = {"intact": REPORT_COLOR, "strengthened": GREEN, "weakened": AMBER, "broken": RED}
    page_w, page_h = A4
    m = 1.6 * cm
    usable = page_w - 2 * m
    ss = getSampleStyleSheet()
    hf = _heading_font()
    body = ParagraphStyle("BodyM", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.2,
                          alignment=TA_JUSTIFY, spaceAfter=5)
    small = ParagraphStyle("SmallM", parent=body, fontSize=7, leading=9, textColor=GREY, alignment=0)
    cell = ParagraphStyle("CellM", parent=body, fontSize=7.8, leading=9.6, alignment=0, spaceAfter=0)
    cell_r = ParagraphStyle("CellRM", parent=cell, alignment=2)
    cell_w = ParagraphStyle("CellWM", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    cell_wr = ParagraphStyle("CellWRM", parent=cell_w, alignment=2)
    h1 = ParagraphStyle("H1M", parent=body, fontName=hf, fontSize=20, leading=24, textColor=NAVY, alignment=0)
    h2 = ParagraphStyle("H2M", parent=body, fontName=hf, fontSize=13, leading=16, textColor=NAVY, alignment=0,
                        spaceBefore=8, spaceAfter=2)
    head = ParagraphStyle("HeadM", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=14.5, alignment=0)
    exh = ParagraphStyle("ExhM", parent=cell, fontName="Helvetica-Bold", textColor=NAVY, fontSize=8.5, spaceBefore=6,
                         spaceAfter=3)
    line = TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("LINEBELOW", (0, -1), (-1, -1), 0.8, NAVY),
                       ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_tint(REPORT_COLOR, 0.96))]),
                       ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 2),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 2)])
    af = _arrow_font()
    name = _company_name(ticker)
    exno = [0]

    def heading(t):
        return [Paragraph(t, h2), HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceBefore=1, spaceAfter=5)]

    def exhibit(t):
        exno[0] += 1
        return Paragraph(f"Exhibit {exno[0]}: {t}", exh)

    def source(t):
        return Paragraph(f"Source: {t}", small)

    def colored(txt, verdict):
        return f"<font color='{VC.get(verdict, '#5A6472')}'><b>{txt}</b></font>"

    span = f"{labels[0]} to {labels[-1]}" if len(labels) > 1 else labels[0]
    content = [Paragraph(f"{escape(name)} <font size=12 color='#5A6472'>({ticker})</font>", h1), Spacer(1, 3),
               Paragraph(escape(headline), head), Spacer(1, 2),
               Paragraph(f"Covers {span} since the {sc.get('fy', 'FY')} 10-K | {len([r for r in rels if not r.get('error')])} "
                         f"earnings release(s) [1], {len(tenqs)} Form 10-Q [2] | Generated by {REPORT_BRAND}", small),
               Spacer(1, 8)]

    # Seite 1: Summary + Panel (Thesenstatus aktuell, Momentum-Chart)
    left_w, right_w = usable * 0.52, usable * 0.44
    inner = right_w - 14
    counts = {s_: sum(1 for t_ in thesis if t_["current_status"] == s_) for s_ in STATUSES}
    st_rows = [[Paragraph("Thesis status (latest)", cell_w), Paragraph("Count", cell_wr)]]
    for s_ in STATUSES:
        st_rows.append([Paragraph(f"<font color='{SC[s_]}'><b>{s_.capitalize()}</b></font>", cell),
                        Paragraph(str(counts[s_]), cell_r)])
    st = Table(st_rows, colWidths=[inner * 0.7, inner * 0.3])
    st.setStyle(line)
    right = [exhibit("Investment theses after the latest quarter"), st, source("Assessment by the agent; see thesis check")]
    try:
        mo = estimate_momentum(ticker)
        if mo["trend"] or mo["surprises"]:
            img = _momentum_chart(mo, os.path.splitext(pdf_path)[0] + "_momentum.png", REPORT_COLOR)
            right += [Spacer(1, 6), exhibit("Estimate revisions and EPS surprises"), _scaled_image(img, inner, 6.2 * cm),
                      source(f"Yahoo Finance [3], retrieved {date.today().isoformat()}")]
    except Exception:
        pass
    panel = Table([[right]], colWidths=[right_w])
    panel.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    row = Table([[heading("Summary") + _paragraphs(summary, body), "", panel]],
                colWidths=[left_w, usable - left_w - right_w, right_w])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")] +
                            [(k, (0, 0), (-1, -1), 0) for k in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]))
    content += [row, Spacer(1, 8)]

    # Scorecard ueber alle Quartale
    if sc.get("rows"):
        nq = len(labels)
        hdr = ["Metric", sc.get("fy", "FY")] + [f"{q['label']}<br/><font size=6>vs {q['year_ago_end'] or 'n/a'}</font>"
                                                for q in sc["quarters"]] + ["YTD vs PY", "Trend"]
        rows = [[Paragraph(h_, cell_w if i == 0 else cell_wr) for i, h_ in enumerate(hdr)]]
        for r in sc["rows"]:
            u = r["unit"]
            arrow = {1: "▲", -1: "▼", 0: "►"}
            qcells = []
            for c in r["quarters"]:
                a = arrow.get(c["dir"], "")
                sym = f"<font name='{af}' color='{VC.get(c['verdict'])}'>{a}</font> " if af and a else ""
                qcells.append(Paragraph(f"{sym}{qd.fmt_val(c['value'], u)}", cell_r))
            ytd = r["ytd"]
            ytd_txt = ("n/a" if not ytd else
                       (colored(f"{qd.fmt_val(ytd['value'], u)} vs {qd.fmt_val(ytd['year_ago'], u)}", ytd["verdict"])
                        if ytd["year_ago"] is not None else qd.fmt_val(ytd["value"], u)))
            rows.append([Paragraph(r["metric"] + (" (USD mn)" if u == "mn" else ""), cell),
                         Paragraph(qd.fmt_val(r["fy"], u), cell_r)] + qcells +
                        [Paragraph(ytd_txt, cell_r), Paragraph(colored(r["trend"], r["trend"]), cell_r)])
        w_metric, w_fy, w_ytd, w_tr = usable * 0.25, usable * 0.10, usable * 0.17, usable * 0.12
        w_q = (usable - w_metric - w_fy - w_ytd - w_tr) / max(nq, 1)
        tb = Table(rows, colWidths=[w_metric, w_fy] + [w_q] * nq + [w_ytd, w_tr], repeatRows=1)
        tb.setStyle(line)
        content += [KeepTogether([exhibit(f"Scorecard: every quarter since the {sc.get('fy', 'FY')} 10-K"), tb,
                                  source("Yahoo Finance quarterly and annual statements [3], own calculations. Arrows: each "
                                         "quarter vs. the same quarter a year earlier, green = better and red = worse for "
                                         "shareholders. YTD vs PY: sum of the quarters vs. the same quarters a year earlier "
                                         "(only where all year-ago quarters are available). Trend: first vs. latest quarter.")])]

    # KPIs je Quartal
    if kpis:
        hdr = ["KPI"] + labels + ["Verified"]
        rows = [[Paragraph(h_, cell_w if i == 0 else cell_wr) for i, h_ in enumerate(hdr)]]
        for k in kpis:
            u = k["unit"]
            fk = (lambda v: "n/a" if v is None else (f"{v:,.1f}%" if "%" in u else f"{v:,.2f}".rstrip("0").rstrip(".")))
            cells = []
            for c in k["cells"]:
                ch = "" if c["change"] is None else (f" ({c['change']:+.1f} pp)" if "%" in u else f" ({c['change'] * 100:+.0f}%)")
                cells.append(Paragraph(colored(f"{fk(c['value'])}{ch}", c["verdict"]) if c["verdict"] != "n/a"
                                       else fk(c["value"]), cell_r))
            ver = {"yes": f"<font color='{GREEN}'>yes</font>", "partial": f"<font color='{AMBER}'><b>partly</b></font>"}.get(
                k["verified"], f"<font color='{RED}'><b>no</b></font>")
            rows.append([Paragraph(f"{escape(k['name'])} <font color='#5A6472'>({escape(u)}, good if {k['good_direction']})</font>",
                                   cell)] + cells + [Paragraph(ver, cell_r)])
        w0, wv = usable * 0.32, usable * 0.10
        tk = Table(rows, colWidths=[w0] + [(usable - w0 - wv) / len(labels)] * len(labels) + [wv])
        tk.setStyle(line)
        content += [KeepTogether([exhibit("Company-specific KPIs per quarter (change vs. year-ago quarter)"), tk,
                                  source("Values extracted by the agent from the earnings releases [1] and 10-Qs [2]; change "
                                         "and colour calculated by Python. Verified: 'yes' = all values found in [1] or [2], "
                                         "'partly' = some, 'no' = none.")])]

    content += heading("Results and drivers") + _paragraphs(results, body)

    # Thesen mit Status je Quartal
    hdr = ["Thesis (annual report)", "Signpost"] + labels + ["Evidence"]
    rows = [[Paragraph(h_, cell_w) for h_ in hdr]]
    for t_ in thesis:
        st_cell = ParagraphStyle("StM", parent=cell, fontSize=7)
        sts = [Paragraph(f"<font color='{SC.get(t_['statuses'].get(l_, ''), '#5A6472')}'><b>{t_['statuses'].get(l_, '-')}</b></font>",
                         st_cell) for l_ in labels]
        rows.append([Paragraph(escape(t_["thesis"]), cell), Paragraph(escape(t_.get("signpost", "") or "-"), cell)] + sts +
                    [Paragraph(escape(t_["evidence"]), cell)])
    w_t, w_s, w_st = usable * 0.22, usable * 0.16, usable * (0.12 if len(labels) <= 2 else 0.105)
    tt = Table(rows, colWidths=[w_t, w_s] + [w_st] * len(labels) + [usable - w_t - w_s - w_st * len(labels)], repeatRows=1)
    tt.setStyle(TableStyle(line.getCommands() + [("VALIGN", (0, 0), (-1, -1), "TOP")]))
    content += [KeepTogether(heading("Thesis check") + [
        exhibit("Investment theses: status per quarter since the annual report"), tt,
        source(f"Annual report of the agent [4] ({escape(baseline.get('path', 'n/a'))}) and thesis log; earnings releases [1], "
               "10-Qs [2], Yahoo Finance [3]")])]
    content += heading("Risk update") + _paragraphs(risks, body)
    content += heading("Outlook and estimates") + _paragraphs(outlook, body)

    # Quellen
    today = date.today().isoformat()
    refs = []
    rel_ok = [r for r in rels if not r.get("error")]
    refs.append("Earnings releases (Form 8-K, Item 2.02, exhibit 99.1), SEC EDGAR: " +
                ("; ".join(f"filed {r['filing_date']}, {escape(r.get('url', ''))}" for r in rel_ok) if rel_ok else "not available") + ".")
    refs.append("Forms 10-Q (MD&amp;A; risk factors of the latest 10-Q via sec-api.io): " +
                ("; ".join(f"quarter ended {q['report_date']}, filed {q['filing_date']}, {escape(q['url'])}" for q in tenqs)
                 if tenqs else "not available") + ".")
    refs.append(f"Yahoo Finance: quarterly and annual statements, consensus estimates, revisions and earnings history for "
                f"{ticker}, retrieved {today} via yfinance.")
    refs.append(f"Annual report generated by {REPORT_BRAND}: {escape(baseline.get('path', 'n/a'))} (10-K filed "
                f"{baseline.get('filing_date', 'n/a')}); thesis log {escape(str(qd.thesis_log_path(ticker).name))}.")
    content += heading("Sources") + [Paragraph(f"[{i}] {r}", ParagraphStyle(f"RefM{i}", parent=body, fontSize=8.5, alignment=0,
                                                                             leading=11, leftIndent=14, firstLineIndent=-14))
                                     for i, r in enumerate(refs, 1)]
    # Faktencheck
    rate = f"{fc['match_rate'] * 100:.0f}%" if fc["match_rate"] is not None else "n/a"
    content += heading("Appendix: Automated Fact Check") + [
        Paragraph("Every number in the text was compared with the sources [1]-[4] (within rounding). 'Not found' does not "
                  "automatically mean wrong (e.g. derived figures) and requires manual review.", small), Spacer(1, 4)]
    rows = [[Paragraph("Summary", cell_w), ""], [Paragraph("Numeric claims checked", cell), Paragraph(str(fc["total_claims"]), cell_r)],
            [Paragraph("Found in sources", cell), Paragraph(f"{fc['matched']} ({rate})", cell_r)]]
    for src_, n_ in fc["by_source"].items():
        rows.append([Paragraph(f"&nbsp;&nbsp;thereof {escape(src_)}", cell), Paragraph(str(n_), cell_r)])
    t_ = Table(rows, colWidths=[usable * 0.6, usable * 0.2])
    t_.setStyle(line)
    content.append(t_)
    if fc["unmatched"]:
        rows = [[Paragraph(h_, cell_w) for h_ in ("Section", "Figure", "Context")]]
        for u_ in fc["unmatched"][:40]:
            rows.append([Paragraph(escape(u_["section"]), cell), Paragraph(escape(u_["text"]), cell),
                         Paragraph(escape(u_["context"]), cell)])
        t_ = Table(rows, colWidths=[usable * 0.18, usable * 0.12, usable * 0.70], repeatRows=1)
        t_.setStyle(TableStyle(line.getCommands() + [("VALIGN", (0, 0), (-1, -1), "TOP")]))
        content += [Spacer(1, 6), Paragraph("Figures not found in the sources (manual review)", exh), t_]

    gen = date.today().strftime("%d %B %Y")

    def _footer(canv, d):
        canv.setStrokeColor(colors.HexColor(_tint(REPORT_COLOR, 0.75)))
        canv.line(m, 1.25 * cm, page_w - m, 1.25 * cm)
        canv.setFont("Helvetica", 7)
        canv.setFillColor(GREY)
        canv.drawString(m, 0.85 * cm, f"Generated by {REPORT_BRAND} - for academic purposes only, not investment advice")
        canv.drawRightString(page_w - m, 0.85 * cm, f"Page {d.page}")

    def _first(canv, d):
        canv.saveState()
        canv.setFillColor(NAVY)
        canv.rect(0, page_h - 1.15 * cm, page_w, 1.15 * cm, stroke=0, fill=1)
        canv.setFillColor(colors.white)
        canv.setFont("Helvetica-Bold", 9)
        canv.drawString(m, page_h - 0.72 * cm, "EARNINGS & THESIS UPDATE  |  MULTI-QUARTER")
        canv.setFont("Helvetica", 9)
        canv.drawRightString(page_w - m, page_h - 0.72 * cm, gen)
        _footer(canv, d)
        canv.restoreState()

    def _later(canv, d):
        canv.saveState()
        canv.setFillColor(NAVY)
        canv.setFont("Helvetica-Bold", 8)
        canv.drawString(m, page_h - 1.0 * cm, f"{name} ({ticker})")
        canv.setFont("Helvetica", 8)
        canv.setFillColor(GREY)
        canv.drawRightString(page_w - m, page_h - 1.0 * cm, f"Earnings & Thesis Update (multi-quarter)  |  {gen}")
        canv.setStrokeColor(NAVY)
        canv.line(m, page_h - 1.15 * cm, page_w - m, page_h - 1.15 * cm)
        _footer(canv, d)
        canv.restoreState()

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=m, rightMargin=m, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    doc.build(content, onFirstPage=_first, onLaterPages=_later)


# --------------------------------------------------------------- Build-Tool
def build_multi_quarter_update(
    ticker_symbol: Annotated[str, "ticker symbol"],
    fyear: Annotated[str, "fiscal year of the annual report baseline, e.g. '2025'"],
    save_dir: Annotated[str, "folder in which to save the pdf"],
    headline: Annotated[str, "one-sentence headline on the quarters since the annual report (max. 25 words)"],
    summary: Annotated[str, "summary for page 1, 120-200 words, with citations [1]-[4]"],
    results_commentary: Annotated[str, "results and drivers, 300-450 words in 2-4 paragraphs: how the metrics and KPIs "
                                       "developed quarter by quarter (accelerating, stable, deteriorating) and why"],
    thesis_check: Annotated[List[dict], "one entry per thesis: {'thesis', 'signpost', 'statuses': {quarter label: "
                                        "'intact'|'strengthened'|'weakened'|'broken'} for every quarter label of the "
                                        "scorecard (e.g. 'Q1 FY2026'), 'evidence': 1-3 sentences with figures and citations}"],
    risk_update: Annotated[str, "risk update, 100-200 words: which risks materialised, eased or are new since the annual report"],
    outlook: Annotated[str, "outlook and estimates, 80-150 words: guidance, consensus revisions, what to watch next"],
    company_kpis: Annotated[List[dict], "3-6 company-specific KPIs, each {'name', 'unit' (e.g. 'USD mn', '%', 'count'), "
                                         "'good_direction' ('up' or 'down'), 'values': {quarter label: number}, "
                                         "'prior_values': {quarter label: number of the same quarter a year earlier}, "
                                         "'source'}; copy values exactly as stated in the releases or 10-Qs"] = None,
) -> str:
    """Build the multi-quarter earnings & thesis update PDF (with automated fact check and thesis log)."""
    from finrobot.functional.fact_check import SourceIndex, run_fact_check, save_json
    from finrobot.functional.outlook import outlook_text
    t = ticker_symbol.upper()
    sc = qd.multi_quarter_scorecard(t, fyear)
    if sc.get("error"):
        return f"PDF NOT generated: {sc['error']}."
    labels = [q["label"] for q in sc["quarters"]]
    problems = []
    for nm, txt, lo, hi in (("summary", summary, 80, 260), ("results_commentary", results_commentary, 180, 560),
                            ("risk_update", risk_update, 50, 260), ("outlook", outlook, 40, 200)):
        n = len(str(txt or "").split())
        if n < lo or n > hi:
            problems.append(f"{nm}: {n} words, expected {lo}-{hi}")
    for nm in ("thesis_check", "company_kpis"):
        v = locals()[nm]
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except Exception:
                problems.append(f"{nm} must be a list of objects")
                v = []
        if nm == "thesis_check":
            thesis_check = v
        else:
            company_kpis = v
    thesis = []
    for x in thesis_check or []:
        sts = {str(k): str(s_).lower().strip() for k, s_ in (x.get("statuses") or {}).items()}
        bad = [s_ for s_ in sts.values() if s_ not in STATUSES]
        if bad:
            problems.append(f"thesis statuses {bad} not in {STATUSES}")
        missing = [l_ for l_ in labels if l_ not in sts]
        if missing:
            problems.append(f"thesis '{str(x.get('thesis', ''))[:40]}': no status for {', '.join(missing)} "
                            f"(use exactly these quarter labels: {', '.join(labels)})")
        cur = sts.get(labels[-1], "intact")
        thesis.append({"thesis": str(x.get("thesis", "")), "signpost": str(x.get("signpost", "")),
                       "statuses": {l_: sts.get(l_, "-") for l_ in labels},
                       "current_status": cur if cur in STATUSES else "intact", "evidence": str(x.get("evidence", ""))})
    if not thesis:
        problems.append("thesis_check is empty")
    if problems:
        return "PDF NOT generated. Problems: " + "; ".join(problems) + ". Fix them and call build_multi_quarter_update again."

    os.makedirs(save_dir, exist_ok=True)
    pdf_path = os.path.join(save_dir, f"{t}_multi_quarter_update.pdf")
    json.dump(dict(ticker_symbol=t, fyear=fyear, save_dir=save_dir, headline=headline, summary=summary,
                   results_commentary=results_commentary, thesis_check=thesis, risk_update=risk_update,
                   outlook=outlook, company_kpis=company_kpis or []),
              open(os.path.splitext(pdf_path)[0] + "_build_args.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    try:
        rels = qd.earnings_releases_since(t, sc["fy_end"])
    except Exception as e:
        rels = [{"error": str(e)}]
    try:
        tenqs = qd.tenqs_since(t, sc["fy_end"])
    except Exception:
        tenqs = []
    baseline = qd.annual_baseline(t)
    s1, s2, s3, s4 = (SourceIndex("[1] Earnings releases"), SourceIndex("[2] Forms 10-Q"),
                      SourceIndex("[3] Yahoo Finance"), SourceIndex("[4] Annual report and thesis log"))
    s1.add_text("\n".join(r.get("text", "") for r in rels if not r.get("error")))
    s2.add_text("\n".join(v for q in tenqs for v in q["sections"].values()))
    s3.add_text(qd.multi_scorecard_text(t, fyear))
    try:
        s3.add_text(outlook_text(t, fyear))
        tk = qd._ticker(t)
        for attr in ("quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow"):
            df = qd._get(tk, attr)
            if df is not None:
                for v in df.values.flatten():
                    s3.add_raw_usd(v)
    except Exception:
        pass
    if not baseline.get("error"):
        s4.add_text(" ".join(baseline["takeaways"]) + " " + baseline["summary"] + " " + baseline["risks"])
    s4.add_text(json.dumps(qd.load_thesis_log(t)))
    srcs = [s1, s2, s3, s4]
    kpis = evaluate_kpis_multi(company_kpis, labels, [s1, s2])
    sections = [("Headline", headline), ("Summary", summary), ("Results and drivers", results_commentary),
                ("Thesis check", " ".join(f"{x['thesis']} {x['evidence']}" for x in thesis)),
                ("Risk update", risk_update), ("Outlook", outlook)]
    if kpis:
        sections.append(("Company KPIs", " ".join(
            f"{k['name']}: " + ", ".join(f"{_kpi_text(c['value'], k['unit'])} vs {_kpi_text(c['prior'], k['unit'])}"
                                       for c in k["cells"] if c["value"] is not None) + "." for k in kpis)))
    fc = run_fact_check(sections, srcs, None)
    key = os.path.abspath(pdf_path)
    _ROUNDS[key] = _ROUNDS.get(key, 0) + 1
    fc["build_round"] = _ROUNDS[key]
    base = os.path.splitext(pdf_path)[0]
    if fc["build_round"] == 1:
        save_json(fc, base + "_factcheck_round1.json")
    elif os.path.exists(base + "_factcheck_round1.json"):
        r1 = json.load(open(base + "_factcheck_round1.json", encoding="utf-8"))
        fc["round1"] = {k: r1.get(k) for k in ("total_claims", "matched", "match_rate")}
    save_json(fc, base + "_factcheck.json")
    try:
        _build_pdf(t, fyear, pdf_path, headline, summary, results_commentary, thesis, risk_update, outlook, sc, kpis,
                   rels, tenqs, baseline if not baseline.get("error") else {}, fc, labels)
    except Exception:
        import traceback
        return "PDF NOT generated:\n" + traceback.format_exc()[-1500:]
    msg = (f"Multi-quarter update generated: {pdf_path}. Fact check: {fc['matched']} of {fc['total_claims']} figures "
           "found in the sources.")
    unv = [k["name"] for k in kpis if k["verified"] != "yes"]
    if unv:
        msg += f" KPI values not (fully) found in the releases or 10-Qs: {', '.join(unv)}."
    if fc["build_round"] == 1 and (fc["unmatched"] or unv) and os.environ.get("FINROBOT_SELF_CORRECT", "1") != "0":
        items = [f"- [{u['section']}] {u['text']}: \"{' '.join(str(u.get('context', '')).split()).strip('. ')[:170]}\""
                 for u in fc["unmatched"][:25]]
        intro = ("these figures were not found in the sources:\n" + "\n".join(items) if items
                 else "all text figures were found, but some KPI values were not (see above).")
        msg += ("\n\nSELF-CHECK (one revision round): " + intro
                + "\n\nCorrect each to the value in your sources, remove it, or keep it only if it is a correct calculation "
                  "from source figures. Then call build_multi_quarter_update exactly once more with the revised texts. "
                  "After that, reply TERMINATE.")
    else:  # finale Version: Thesen-Protokoll fortschreiben
        qd.append_thesis_log(t, {"date": date.today().isoformat(), "fyear": fyear, "quarters": labels,
                                 "report": pdf_path,
                                 "theses": [{k: x[k] for k in ("thesis", "signpost", "statuses", "current_status")}
                                            for x in thesis]})
        msg += " Thesis log updated."
    return msg


# --------------------------------------------------------------- Agent
SYSTEM = dedent("""
    You are a senior equity research analyst writing an earnings and thesis update that covers every quarter since the
    company's annual report. Explain how the business developed quarter by quarter, judge each investment thesis per
    quarter against its signpost, and keep every number traceable to the sources. Never invent figures or guidance;
    if a tool returns no data, say so. Use tools one at a time. Reply TERMINATE when the update is built.
""").strip()


def build_multi_reviewer(llm_config, max_rounds=30):
    _ROUNDS.clear()
    analyst = autogen.AssistantAgent(name="Multi_Quarter_Reviewer", system_message=SYSTEM, llm_config=llm_config)
    proxy = autogen.UserProxyAgent(
        name="User_Proxy", human_input_mode="NEVER", max_consecutive_auto_reply=max_rounds,
        is_termination_msg=lambda x: str(x.get("content") or "").rstrip().rstrip("*.").endswith("TERMINATE"),
        code_execution_config=False)
    register_toolkits([get_annual_report_baseline, get_thesis_log, get_multi_quarter_scorecard, get_earnings_releases,
                       get_10q_mdna, get_consensus_and_liquidity, build_multi_quarter_update], analyst, proxy)
    return analyst, proxy


def multi_reviewer_message(ticker, fyear, save_dir):
    return dedent(f"""
        Write a multi-quarter earnings and thesis update for {ticker}. The annual report baseline covers fiscal year {fyear}.
        Steps:
        1. get_annual_report_baseline (theses with signposts) and get_thesis_log (statuses from earlier updates, if any).
        2. get_multi_quarter_scorecard (fyear {fyear}): note the exact quarter labels (e.g. "Q1 FY2026") and the trends.
        3. get_earnings_releases and get_10q_mdna (fyear {fyear}): drivers per quarter, guidance changes, new risks, and
           the company-specific KPIs (those in the signposts plus the company's own key business metrics) for every
           quarter and the same quarter a year earlier, exactly as stated.
        4. get_consensus_and_liquidity ({ticker}, {fyear}): revisions, surprises, liquidity, valuation.
        5. Call build_multi_quarter_update with save_dir "{save_dir}": headline, summary, results_commentary (quarter by
           quarter: what accelerated, held or deteriorated, and why), thesis_check (per thesis: signpost, a status for
           every quarter label, evidence), risk_update, outlook and company_kpis (3-6 KPIs with values per quarter label).
           If the thesis log has earlier statuses, keep them consistent unless new evidence justifies a change.
        Cite [1] earnings releases, [2] 10-Qs, [3] Yahoo Finance data, [4] annual report / thesis log.
        If build_multi_quarter_update returns a SELF-CHECK list, revise once as instructed and rebuild.
    """).strip()


def run_multi_review(llm_config, ticker, fyear, save_dir):
    analyst, proxy = build_multi_reviewer(llm_config)
    proxy.initiate_chat(analyst, message=multi_reviewer_message(ticker.upper(), fyear, save_dir), cache=None)
    return analyst, proxy
