"""
Earnings & Thesis Reviewer (eigener Agent).

Frage: Was hat sich seit dem Jahresbericht veraendert, und haelt die Investment-These noch?

Ablauf:
1. Ausgangsbasis: Key Takeaways, Summary und Risiken aus dem letzten Annual Report des Agenten.
2. Scorecard (Python): letztes Quartal vs. Vorjahresquartal vs. Geschaeftsjahr, Richtung gut/schlecht je Kennzahl.
3. Quellen: Pressemitteilung zu den Zahlen (8-K, Item 2.02, EDGAR), 10-Q (MD&A, Risikofaktoren; sec-api),
   Konsens, Revisionen und Ueberraschungen (Yahoo).
4. Der Agent erklaert die Treiber, prueft jede These (intact / strengthened / weakened / broken) und schreibt
   ein 2-3-seitiges Earnings Update. Faktencheck und eine Runde Selbstkorrektur wie beim Annual Report.
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
from .outlook_tools import get_consensus_and_liquidity

STATUSES = ("intact", "strengthened", "weakened", "broken")
_ROUNDS = {}


# --------------------------------------------------------------- Tools fuer den Agenten
def get_annual_report_baseline(ticker_symbol: Annotated[str, "ticker symbol"]) -> str:
    """Key takeaways, investment summary and risk section of the agent's latest annual report on this company:
    the investment theses to be checked against the new quarter."""
    b = qd.annual_baseline(ticker_symbol)
    if b["error"]:
        return f"Baseline not available: {b['error']}."
    if b.get("theses"):
        tk = "\n".join(f"- T{i + 1}: {t['thesis']}\n  evidence: {t['evidence']}\n  signpost: {t['signpost']}\n"
                       f"  invalidation: {t['invalidation']}" for i, t in enumerate(b["theses"]))
        head_ = "Investment theses with signposts (check each signpost against the new quarter)"
    else:
        tk = "\n".join(f"- T{i + 1}: {t}" for i, t in enumerate(b["takeaways"])) or "(no key takeaways stored)"
        head_ = "Key takeaways (older report without structured theses; treat them as the theses to check)"
    return (f"ANNUAL REPORT BASELINE ({b['path']}, based on the 10-K filed {b['filing_date']}; cite as [4]).\n"
            f"{head_}:\n{tk}\n\nKey takeaways:\n" + "\n".join(f"- {t}" for t in b["takeaways"]) +
            f"\n\nInvestment summary:\n{b['summary']}\n\nRisk assessment:\n{b['risks']}")


def get_quarterly_scorecard(
    ticker_symbol: Annotated[str, "ticker symbol"],
    fyear: Annotated[str, "fiscal year of the annual report baseline, e.g. '2025'"],
) -> str:
    """Latest quarter vs. year-ago quarter vs. last fiscal year for key metrics, with the direction judged
    (better / worse / stable) from a shareholder's point of view."""
    return qd.scorecard_text(ticker_symbol, fyear)


def get_earnings_release(ticker_symbol: Annotated[str, "ticker symbol"]) -> str:
    """Text of the latest quarterly earnings press release (Form 8-K, Item 2.02, exhibit 99.1) from SEC EDGAR,
    including management commentary and guidance."""
    try:
        r = qd.earnings_release(ticker_symbol)
    except Exception as e:
        return f"Earnings release not available ({e})."
    if r.get("error"):
        return f"Earnings release not available: {r['error']}."
    return f"EARNINGS RELEASE (8-K filed {r['filing_date']}, {r.get('url', '')}; cite as [1]):\n\n{r['text']}"


def get_10q_sections(ticker_symbol: Annotated[str, "ticker symbol"]) -> str:
    """MD&A and risk factor updates from the latest Form 10-Q (SEC)."""
    try:
        r = qd.tenq_sections(ticker_symbol)
    except Exception as e:
        return f"10-Q not available ({e})."
    if r.get("error"):
        return f"10-Q not available: {r['error']}."
    parts = [f"[{k}]\n{v}" for k, v in r["sections"].items()]
    return (f"FORM 10-Q for the quarter ended {r['report_date']} (filed {r['filing_date']}; cite as [2]):\n\n"
            + "\n\n".join(parts))


# --------------------------------------------------------------- Firmenspezifische KPIs
def _kpi_text(v, unit):
    u = (unit or "").strip().lower()
    if v is None:
        return ""
    if "%" in u or "percent" in u:
        return f"{v}%"
    if u in ("usd mn", "usd million", "$ mn", "$m", "usd m", "million usd", "usd millions"):
        return f"${v} million"
    if u in ("usd bn", "usd billion", "$bn", "$ bn", "billion usd"):
        return f"${v} billion"
    if u in ("usd", "$"):
        return f"${v}"
    return f"{v}"


def evaluate_kpis(kpis, sources):
    """Veraenderung und Urteil rechnet Python; jeder Wert wird gegen Pressemitteilung/10-Q geprueft."""
    from finrobot.functional.fact_check import check_claim, extract_claims
    out = []
    for k in kpis or []:
        name = str(k.get("name", "")).strip()
        unit = str(k.get("unit", "")).strip()
        cur, pri = qd._num(k.get("current")), qd._num(k.get("prior"))
        good = str(k.get("good_direction", "up")).lower().strip()
        good = good if good in ("up", "down") else "up"
        verified = []
        for v in (cur, pri):
            if v is None:
                continue
            cl = extract_claims(_kpi_text(v, unit))
            verified.append(bool(cl) and all(check_claim(c, sources) for c in cl))
        if cur is None or pri is None:
            change, verdict, d = None, "n/a", None
        else:
            change = cur - pri if "%" in unit else (cur / pri - 1 if pri else None)
            thr = 0.5 if "%" in unit else 0.02
            if change is None or abs(change) < thr:
                verdict, d = "stable", 0
            else:
                d = 1 if change > 0 else -1
                verdict = "better" if (d > 0) == (good == "up") else "worse"
        out.append({"name": name, "unit": unit, "current": cur, "prior": pri, "period": str(k.get("period", "")),
                    "good_direction": good, "why": str(k.get("why", "")), "source": str(k.get("source", "")),
                    "change": change, "verdict": verdict, "dir": d,
                    "verified": ("yes" if verified and all(verified) else "partial" if any(verified) else "no")})
    return out


# --------------------------------------------------------------- PDF
def _arrow_font():
    """Arial (Windows) enthaelt Pfeil-Dreiecke; sonst Text statt Symbol."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for path in (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf"),
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont("ArrowFont", path))
                return "ArrowFont"
            except Exception:
                pass
    return None


def _sources_for_check(ticker, fyear, release, tenq, baseline):
    from finrobot.functional.fact_check import SourceIndex
    from finrobot.functional.outlook import outlook_text
    s1 = SourceIndex("[1] Earnings release")
    s1.add_text(release.get("text", "") if release and not release.get("error") else "")
    s2 = SourceIndex("[2] Form 10-Q")
    if tenq and not tenq.get("error"):
        s2.add_text("\n".join(tenq["sections"].values()))
    s3 = SourceIndex("[3] Yahoo Finance")
    s3.add_text(qd.scorecard_text(ticker, fyear))
    try:
        s3.add_text(outlook_text(ticker, fyear))
    except Exception:
        pass
    try:
        t = qd._ticker(ticker)
        for attr in ("quarterly_income_stmt", "quarterly_balance_sheet", "quarterly_cashflow"):
            df = qd._get(t, attr)
            if df is not None:
                for v in df.values.flatten():
                    s3.add_raw_usd(v)
    except Exception:
        pass
    s4 = SourceIndex("[4] Annual report baseline")
    if baseline and not baseline.get("error"):
        s4.add_text(" ".join(baseline["takeaways"]) + " " + baseline["summary"] + " " + baseline["risks"])
    return [s1, s2, s3, s4]


def _build_pdf(ticker, fyear, pdf_path, headline, summary, results, thesis, risks, outlook,
               sc, release, tenq, baseline, fc, kpis=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    from finrobot.functional.reportlab import (REPORT_BRAND, REPORT_COLOR, _company_name, _heading_font,
                                               _momentum_chart, _paragraphs, _scaled_image, _tint)
    from finrobot.functional.outlook import estimate_momentum

    NAVY, PANEL, GREY = colors.HexColor(REPORT_COLOR), colors.HexColor(_tint(REPORT_COLOR, 0.93)), colors.HexColor("#5A6472")
    GREEN, RED, AMBER = colors.HexColor("#2D8A4E"), colors.HexColor("#B42318"), colors.HexColor("#B7791F")
    page_w, page_h = A4
    m = 1.6 * cm
    usable = page_w - 2 * m
    hf = _heading_font()
    ss = getSampleStyleSheet()
    body = ParagraphStyle("BodyE", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.2,
                          alignment=TA_JUSTIFY, spaceAfter=5)
    small = ParagraphStyle("SmallE", parent=body, fontSize=7, leading=9, textColor=GREY, alignment=0)
    cell = ParagraphStyle("CellE", parent=body, fontSize=8, leading=10, alignment=0, spaceAfter=0)
    cell_r = ParagraphStyle("CellRE", parent=cell, alignment=2)
    cell_w = ParagraphStyle("CellWE", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    cell_wr = ParagraphStyle("CellWRE", parent=cell_w, alignment=2)
    h1 = ParagraphStyle("H1E", parent=body, fontName=hf, fontSize=20, leading=24, textColor=NAVY, alignment=0)
    h2 = ParagraphStyle("H2E", parent=body, fontName=hf, fontSize=13, leading=16, textColor=NAVY, alignment=0,
                        spaceBefore=8, spaceAfter=2)
    head = ParagraphStyle("HeadE", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=14.5, alignment=0)
    exh = ParagraphStyle("ExhE", parent=cell, fontName="Helvetica-Bold", textColor=NAVY, fontSize=8.5, spaceBefore=6,
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

    qlabel = sc.get("quarter") or "latest quarter"
    content = [Paragraph(f"{escape(name)} <font size=12 color='#5A6472'>({ticker})</font>", h1), Spacer(1, 3),
               Paragraph(escape(headline), head), Spacer(1, 2),
               Paragraph(f"Quarter ended {qlabel} | earnings release filed {release.get('filing_date', 'n/a')} [1] | "
                         f"Generated by {REPORT_BRAND}", small), Spacer(1, 8)]

    # Seite 1: links Summary, rechts Thesen-Status + Momentum-Chart
    counts = {s_: sum(1 for t_ in thesis if t_["status"] == s_) for s_ in STATUSES}
    col_ = {"intact": NAVY, "strengthened": GREEN, "weakened": AMBER, "broken": RED}
    left_w, right_w = usable * 0.52, usable * 0.44
    left = heading("Summary") + _paragraphs(summary, body)
    inner = right_w - 14
    st_rows = [[Paragraph("Thesis status", cell_w), Paragraph("Count", cell_wr)]]
    for s_ in STATUSES:
        st_rows.append([Paragraph(f"<font color='#{col_[s_].hexval()[2:]}'><b>{s_.capitalize()}</b></font>", cell),
                        Paragraph(str(counts[s_]), cell_r)])
    st = Table(st_rows, colWidths=[inner * 0.7, inner * 0.3])
    st.setStyle(line)
    right = [exhibit("Investment theses from the annual report"), st,
             source("Assessment by the agent; details in the thesis check")]
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
    row = Table([[left, "", panel]], colWidths=[left_w, usable - left_w - right_w, right_w])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    content += [row, Spacer(1, 8)]

    # Scorecard
    if sc.get("rows"):
        hdr = ["Metric", sc.get("fy") or "FY (10-K)", f"Year-ago quarter ({sc.get('year_ago') or 'n/a'})",
               f"Latest quarter ({qlabel})", "Direction", "Verdict"]
        rows = [[Paragraph(h_, cell_w if i == 0 else cell_wr) for i, h_ in enumerate(hdr)]]
        for r in sc["rows"]:
            arrow = {1: "\u25B2", -1: "\u25BC", 0: "\u25BA"}.get(r["dir"], "")
            arrow_txt = {1: "up", -1: "down", 0: "flat"}.get(r["dir"], "n/a")
            vc = {"better": GREEN, "worse": RED, "stable": GREY}.get(r["verdict"], GREY)
            hexv = "#" + vc.hexval()[2:]
            d_cell = (f"<font name='{af}' color='{hexv}'>{arrow}</font>" if af and arrow else arrow_txt)
            u = r["unit"]
            rows.append([Paragraph(r["metric"] + (" (USD mn)" if u == "mn" else ""), cell),
                         Paragraph(qd.fmt_val(r["fy"], u), cell_r), Paragraph(qd.fmt_val(r["year_ago"], u), cell_r),
                         Paragraph(f"<b>{qd.fmt_val(r['quarter'], u)}</b>", cell_r), Paragraph(d_cell, cell_r),
                         Paragraph(f"<font color='{hexv}'><b>{r['verdict']}</b></font>", cell_r)])
        tb = Table(rows, colWidths=[usable * 0.28, usable * 0.13, usable * 0.17, usable * 0.17, usable * 0.11, usable * 0.14])
        tb.setStyle(line)
        content += [KeepTogether([exhibit("Scorecard: latest quarter vs. year-ago quarter and fiscal year"), tb,
                                  source("Yahoo Finance quarterly and annual statements [3], own calculations. Direction "
                                         "compares the latest quarter with the same quarter a year earlier (avoids seasonal "
                                         "effects); the verdict judges it from a shareholder's view (e.g. rising margins = "
                                         "better, rising share count or days sales outstanding = worse).")])]

    if kpis:
        rows = [[Paragraph(h_, cell_w if i < 1 else cell_wr) for i, h_ in
                 enumerate(["KPI", "Year-ago", "Latest", "Change", "Good if", "Verdict", "Verified"])]]
        for k in kpis:
            u = k["unit"]
            fmtk = (lambda v: "n/a" if v is None else (f"{v:,.1f}%" if "%" in u else f"{v:,.2f}".rstrip("0").rstrip(".")))
            ch = "n/a" if k["change"] is None else (f"{k['change']:+.1f} pp" if "%" in u else f"{k['change'] * 100:+.1f}%")
            vc = {"better": GREEN, "worse": RED, "stable": GREY}.get(k["verdict"], GREY)
            hexv = "#" + vc.hexval()[2:]
            ver = {"yes": "<font color='#2D8A4E'>yes</font>",
                   "partial": "<font color='#B7791F'><b>partly</b></font>"}.get(k["verified"], "<font color='#B42318'><b>no</b></font>")
            rows.append([Paragraph(f"{escape(k['name'])} <font color='#5A6472'>({escape(u)})</font>", cell),
                         Paragraph(fmtk(k["prior"]), cell_r), Paragraph(f"<b>{fmtk(k['current'])}</b>", cell_r),
                         Paragraph(ch, cell_r), Paragraph(k["good_direction"], cell_r),
                         Paragraph(f"<font color='{hexv}'><b>{k['verdict']}</b></font>", cell_r), Paragraph(ver, cell_r)])
        tk_ = Table(rows, colWidths=[usable * 0.30, usable * 0.12, usable * 0.12, usable * 0.12, usable * 0.09,
                                     usable * 0.12, usable * 0.13])
        tk_.setStyle(line)
        content += [KeepTogether([exhibit("Company-specific KPIs"), tk_,
                                  source("Values selected and extracted by the agent from the earnings release [1] and 10-Q [2]; "
                                         "change and verdict calculated by Python. Verified: 'yes' = both values found in [1] or [2], "
                                         "'partly' = one value found, 'no' = neither; unverified values need manual review.")])]

    content += heading("Results and drivers") + _paragraphs(results, body)

    # Thesen-Check
    rows = [[Paragraph(h_, cell_w) for h_ in ("Thesis (annual report)", "Signpost", "Status", "Evidence from the quarter")]]
    for t_ in thesis:
        c_ = "#" + col_[t_["status"]].hexval()[2:]
        rows.append([Paragraph(escape(t_["thesis"]), cell), Paragraph(escape(t_.get("signpost", "") or "-"), cell),
                     Paragraph(f"<font color='{c_}'><b>{t_['status']}</b></font>", cell),
                     Paragraph(escape(t_["evidence"]), cell)])
    tt = Table(rows, colWidths=[usable * 0.26, usable * 0.19, usable * 0.15, usable * 0.40], repeatRows=1)
    tt.setStyle(TableStyle(line.getCommands() + [("VALIGN", (0, 0), (-1, -1), "TOP")]))
    content += [KeepTogether(heading("Thesis check") + [exhibit("Investment theses from the annual report vs. the latest quarter"), tt,
                                          source(f"Annual report of the agent [4] ({escape(baseline.get('path', 'n/a'))}); "
                                                 "earnings release [1], 10-Q [2], Yahoo Finance [3]")])]
    content += heading("Risk update") + _paragraphs(risks, body)
    content += heading("Outlook and estimates") + _paragraphs(outlook, body)

    # Quellen
    today = date.today().isoformat()
    refs = [f"{escape(name)}, earnings release (Form 8-K, Item 2.02, exhibit 99.1), filed {release.get('filing_date', 'n/a')}, "
            f"SEC EDGAR, {escape(release.get('url', ''))}.",
            (f"{escape(name)}, Form 10-Q for the quarter ended {tenq.get('report_date')}, filed {tenq.get('filing_date')}, "
             f"{escape(tenq.get('url', ''))} (MD&amp;A and risk factors via sec-api.io).") if tenq and not tenq.get("error")
            else "Form 10-Q: not available.",
            f"Yahoo Finance: quarterly and annual statements, consensus estimates, revisions and earnings history for "
            f"{ticker}, retrieved {today} via yfinance.",
            f"Annual report generated by {REPORT_BRAND}: {escape(baseline.get('path', 'n/a'))} (10-K filed "
            f"{baseline.get('filing_date', 'n/a')})."]
    content += heading("Sources") + [Paragraph(f"[{i}] {r}", ParagraphStyle(f"Ref{i}", parent=body, fontSize=8.5, alignment=0,
                                                                             leading=11, leftIndent=14, firstLineIndent=-14))
                                     for i, r in enumerate(refs, 1)]

    # Faktencheck-Anhang
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
        canv.drawString(m, page_h - 0.72 * cm, "EARNINGS & THESIS UPDATE")
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
        canv.drawRightString(page_w - m, page_h - 1.0 * cm, f"Earnings & Thesis Update  |  {gen}")
        canv.setStrokeColor(NAVY)
        canv.line(m, page_h - 1.15 * cm, page_w - m, page_h - 1.15 * cm)
        _footer(canv, d)
        canv.restoreState()

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=m, rightMargin=m, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    doc.build(content, onFirstPage=_first, onLaterPages=_later)


def build_earnings_update(
    ticker_symbol: Annotated[str, "ticker symbol"],
    fyear: Annotated[str, "fiscal year of the annual report baseline, e.g. '2025'"],
    save_dir: Annotated[str, "folder in which to save the pdf"],
    headline: Annotated[str, "one-sentence headline on the quarter (max. 25 words)"],
    summary: Annotated[str, "summary for page 1, 120-200 words, with citations [1]-[4]"],
    results_commentary: Annotated[str, "results and drivers, 250-400 words in 2-3 paragraphs: explain the scorecard "
                                       "(what moved in the right or wrong direction and why), with citations"],
    thesis_check: Annotated[List[dict], "one entry per thesis (key takeaway) from the annual report: "
                                        "{'thesis': short restatement, 'status': 'intact'|'strengthened'|'weakened'|'broken', "
                                        "'evidence': 1-2 sentences with figures and citations}"],
    risk_update: Annotated[str, "risk update, 100-200 words: which risks from the annual report materialised, eased or are new"],
    outlook: Annotated[str, "outlook and estimates, 80-150 words: guidance, consensus revisions, what to watch next quarter"],
    company_kpis: Annotated[List[dict], "3-6 company-specific KPIs (those named in the thesis signposts and the company's "
                                         "own key business metrics), each {'name', 'unit' (e.g. 'USD mn', '%', 'count'), "
                                         "'current' (number, latest quarter), 'prior' (number, same quarter a year earlier), "
                                         "'period', 'good_direction' ('up' or 'down'), 'why' (one short reason), "
                                         "'source' ('[1]' or '[2]')}; copy the values exactly as stated in the source"] = None,
) -> str:
    """Build the earnings & thesis update PDF (with automated fact check)."""
    from finrobot.functional.fact_check import run_fact_check, save_json
    t = ticker_symbol.upper()
    problems = []
    for nm, txt, lo, hi in (("summary", summary, 80, 260), ("results_commentary", results_commentary, 150, 500),
                            ("risk_update", risk_update, 50, 260), ("outlook", outlook, 40, 200)):
        n = len(str(txt or "").split())
        if n < lo or n > hi:
            problems.append(f"{nm}: {n} words, expected {lo}-{hi}")
    if isinstance(thesis_check, str):
        try:
            thesis_check = json.loads(thesis_check)
        except Exception:
            problems.append("thesis_check must be a list of objects")
            thesis_check = []
    thesis = []
    for x in thesis_check or []:
        st = str(x.get("status", "")).lower().strip()
        if st not in STATUSES:
            problems.append(f"thesis status '{st}' not in {STATUSES}")
        thesis.append({"thesis": str(x.get("thesis", "")), "status": st if st in STATUSES else "intact",
                       "evidence": str(x.get("evidence", "")), "signpost": str(x.get("signpost", ""))})
    if not thesis:
        problems.append("thesis_check is empty")
    if isinstance(company_kpis, str):
        try:
            company_kpis = json.loads(company_kpis)
        except Exception:
            problems.append("company_kpis must be a list of objects")
            company_kpis = []
    if problems:
        return "PDF NOT generated. Problems: " + "; ".join(problems) + ". Fix them and call build_earnings_update again."

    os.makedirs(save_dir, exist_ok=True)
    pdf_path = os.path.join(save_dir, f"{t}_earnings_update.pdf")
    args = dict(ticker_symbol=t, fyear=fyear, save_dir=save_dir, headline=headline, summary=summary,
                results_commentary=results_commentary, thesis_check=thesis, risk_update=risk_update, outlook=outlook,
                company_kpis=company_kpis or [])
    json.dump(args, open(os.path.splitext(pdf_path)[0] + "_build_args.json", "w", encoding="utf-8"), indent=2,
              ensure_ascii=False)
    sc = qd.quarterly_scorecard(t, fyear)
    try:
        release = qd.earnings_release(t)
    except Exception as e:
        release = {"error": str(e)}
    try:
        tenq = qd.tenq_sections(t)
    except Exception as e:
        tenq = {"error": str(e)}
    baseline = qd.annual_baseline(t)
    srcs = _sources_for_check(t, fyear, release, tenq, baseline)
    kpis = evaluate_kpis(company_kpis, srcs[:2])
    sections = [("Headline", headline), ("Summary", summary), ("Results and drivers", results_commentary),
                ("Thesis check", " ".join(f"{x['thesis']} {x['evidence']}" for x in thesis)),
                ("Risk update", risk_update), ("Outlook", outlook)]
    if kpis:
        sections.append(("Company KPIs", " ".join(f"{k['name']}: {_kpi_text(k['current'], k['unit'])} vs "
                                                  f"{_kpi_text(k['prior'], k['unit'])}." for k in kpis)))
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
        _build_pdf(t, fyear, pdf_path, headline, summary, results_commentary, thesis, risk_update, outlook,
                   sc, release if not release.get("error") else {}, tenq, baseline if not baseline.get("error") else {}, fc,
                   kpis=kpis)
    except Exception:
        import traceback
        return "PDF NOT generated:\n" + traceback.format_exc()[-1500:]
    msg = (f"Earnings update generated: {pdf_path}. Fact check: {fc['matched']} of {fc['total_claims']} figures found "
           "in the sources.")
    unv = [f"{k['name']} ({'one value' if k['verified'] == 'partial' else 'both values'})" for k in kpis if k["verified"] != "yes"]
    if unv:
        msg += (f" KPI values not found in the earnings release or 10-Q: {', '.join(unv)}. Check them against the sources"
                " and correct them in the revision round if needed.")
    if fc["build_round"] == 1 and fc["unmatched"] and os.environ.get("FINROBOT_SELF_CORRECT", "1") != "0":
        items = [f"- [{u['section']}] {u['text']}: \"{' '.join(str(u.get('context', '')).split()).strip('. ')[:170]}\""
                 for u in fc["unmatched"][:25]]
        msg += ("\n\nSELF-CHECK (one revision round): these figures were not found in the sources:\n" + "\n".join(items)
                + "\n\nCorrect each to the value in your sources, remove it, or keep it only if it is a correct calculation "
                  "from source figures. Then call build_earnings_update exactly once more with the revised texts. "
                  "After that, reply TERMINATE.")
    return msg


# --------------------------------------------------------------- Agent
SYSTEM = dedent("""
    You are a senior equity research analyst writing an earnings and thesis update after a company's quarterly results.
    Your job: explain what changed since the annual report, judge whether each investment thesis still holds, and keep
    every number traceable to the sources. Never invent figures, companies or guidance; if a tool returns no data, say so.
    Use tools one at a time. Reply TERMINATE when the update is built.
""").strip()


def build_reviewer(llm_config, max_rounds=25):
    _ROUNDS.clear()
    analyst = autogen.AssistantAgent(name="Earnings_Reviewer", system_message=SYSTEM, llm_config=llm_config)
    proxy = autogen.UserProxyAgent(
        name="User_Proxy", human_input_mode="NEVER", max_consecutive_auto_reply=max_rounds,
        is_termination_msg=lambda x: str(x.get("content") or "").rstrip().rstrip("*.").endswith("TERMINATE"),
        code_execution_config=False)
    register_toolkits([get_annual_report_baseline, get_quarterly_scorecard, get_earnings_release, get_10q_sections,
                       get_consensus_and_liquidity, build_earnings_update], analyst, proxy)
    return analyst, proxy


def reviewer_message(ticker, fyear, save_dir):
    return dedent(f"""
        Write an earnings and thesis update for {ticker}. The annual report baseline covers fiscal year {fyear}.
        Steps:
        1. get_annual_report_baseline: the key takeaways are the theses to check.
        2. get_quarterly_scorecard (fyear {fyear}): what moved in the right or wrong direction.
        3. get_earnings_release and get_10q_sections: the reasons (management commentary, guidance, new risks), and the
           company-specific KPIs: those named in the thesis signposts plus the company's own key business metrics
           (e.g. backlog, ARR, bookings, users, launches). Take current and year-ago quarter values exactly as stated.
        4. get_consensus_and_liquidity ({ticker}, {fyear}): estimate revisions, surprises, liquidity, valuation.
        5. Call build_earnings_update with save_dir "{save_dir}": headline, summary, results_commentary (explain the
           scorecard and the KPIs: drivers of the better and worse metrics), thesis_check (one entry per thesis: its
           signpost, status intact / strengthened / weakened / broken judged against the signpost and invalidation,
           evidence), risk_update, outlook and company_kpis (3-6 KPIs as a list).
        Cite [1] earnings release, [2] 10-Q, [3] Yahoo Finance data, [4] annual report baseline.
        If build_earnings_update returns a SELF-CHECK list, revise once as instructed and rebuild.
    """).strip()


def run_review(llm_config, ticker, fyear, save_dir):
    analyst, proxy = build_reviewer(llm_config)
    proxy.initiate_chat(analyst, message=reviewer_message(ticker.upper(), fyear, save_dir), cache=None)
    return analyst, proxy
