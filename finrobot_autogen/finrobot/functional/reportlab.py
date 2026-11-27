import os
import traceback
from reportlab.lib import colors
from reportlab.lib import pagesizes
from reportlab.platypus import (
    SimpleDocTemplate,
    Frame,
    Paragraph,
    Image,
    PageTemplate,
    FrameBreak,
    Spacer,
    Table,
    TableStyle,
    NextPageTemplate,
    PageBreak,
)
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT

from ..data_source import FMPUtils, YFinanceUtils
from .analyzer import ReportAnalysisUtils
from typing import Annotated, List


# ---------------------------------------------------------------------------
# Angepasstes Layout (v3): Seite 1 = links Investment Summary (Text), rechts Charts
# und Key Data, unten Financial Metrics. Ab Seite 2 die fuenf Abschnitte in voller
# Breite, am Ende das Quellenverzeichnis [1]-[4]. Das Original-Layout bleibt in
# build_annual_report erhalten, wird aber nicht mehr aufgerufen.
# ---------------------------------------------------------------------------
# >>> Name deines Report-Tools: hier aendern <<<
REPORT_BRAND = "Franci's FINRobot"
# >>> Akzentfarbe des Reports (Hex). Vorschlaege: "#0B2545" Navy, "#0F4C5C" Petrol,
#     "#1B4D3E" Tannengruen, "#6D1A36" Bordeaux, "#2F3B45" Anthrazit
REPORT_COLOR = "#0F4C5C"

# Selbstkorrektur: nach dem ersten PDF bekommt der Agent die nicht belegten Zahlen zurueck (eine Runde).
# Abschalten fuer Vergleichslaeufe: Umgebungsvariable FINROBOT_SELF_CORRECT=0
_BUILD_ROUNDS = {}


def SELF_CORRECT():
    return os.environ.get("FINROBOT_SELF_CORRECT", "1") != "0"


def _momentum_chart(mo, path, color):
    """Earnings Momentum als Chart: links EPS-Konsens im Zeitverlauf, rechts Schaetzung vs. Ist der letzten Quartale."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    tint = _tint(color, 0.6)
    panels = (1 if mo["trend"] else 0) + (1 if mo["surprises"] else 0)
    fig, axes = plt.subplots(1, panels, figsize=(9.2, 3.1), squeeze=False)
    axes = list(axes[0])
    plt.rcParams.update({"font.size": 8})
    if mo["trend"]:
        ax = axes.pop(0)
        labels = ["90d ago", "60d ago", "30d ago", "7d ago", "Today"]
        for tr_, ls, mk in zip(mo["trend"], ("-", "--"), ("o", "s")):
            ys = [tr_.get("d90"), tr_.get("d60"), tr_.get("d30"), tr_.get("d7"), tr_.get("current")]
            pts = [(i, y) for i, y in enumerate(ys) if y is not None]
            if not pts:
                continue
            ax.plot([p_[0] for p_ in pts], [p_[1] for p_ in pts], ls, marker=mk, color=color, lw=1.6, ms=4,
                    label=f"{tr_['period'].replace(' fiscal year', ' FY')}  (up/down 30d: "
                          f"{int(tr_.get('up30') or 0)}/{int(tr_.get('down30') or 0)})")
            ax.annotate(f"{pts[-1][1]:.2f}", pts[-1], xytext=(5, 0), textcoords="offset points", va="center",
                        fontsize=7.5, color=color)
        ax.set_xticks(range(5))
        ax.set_xticklabels(labels, fontsize=7.5)
        ax.set_title("EPS consensus: revisions", fontsize=9, color=color, loc="left", fontweight="bold")
        ax.legend(fontsize=7, frameon=False, loc="best")
        ax.set_xlim(-0.3, 4.6)
    if mo["surprises"]:
        ax = axes.pop(0)
        q = list(reversed(mo["surprises"]))  # chronologisch
        x = list(range(len(q)))
        est = [s_["estimate"] for s_ in q]
        act = [s_["actual"] for s_ in q]
        pe = [(i, v) for i, v in zip(x, est) if v is not None]
        pa = [(i, v) for i, v in zip(x, act) if v is not None]
        ax.plot([p_[0] for p_ in pe], [p_[1] for p_ in pe], "--", marker="o", mfc="white", mec=color, color=tint,
                lw=1.2, ms=5, label="Estimate")
        ax.plot([p_[0] for p_ in pa], [p_[1] for p_ in pa], "-", color=color, lw=1.6, zorder=2)
        GREEN, RED = "#2D8A4E", "#B42318"
        sc = lambda sp_: color if sp_ is None or abs(sp_) < 0.005 else (GREEN if sp_ > 0 else RED)
        ax.scatter([i for i, v in zip(x, act) if v is not None], [v for v in act if v is not None], s=34, zorder=3,
                   color=[sc(s_["surprise"]) for s_ in q if s_["actual"] is not None], edgecolors="white", linewidths=0.6)
        ax.plot([], [], "o", color=GREEN, ms=5, label="Actual: beat")
        ax.plot([], [], "o", color=RED, ms=5, label="Actual: miss")
        vals = [v for v in est + act if v is not None] or [0]
        lo, hi = min(vals), max(vals)
        pad = (hi - lo) * 0.25 or 0.02
        for i, s_ in enumerate(q):
            if s_["surprise"] is None or s_["actual"] is None:
                continue
            above = s_["actual"] >= (s_["estimate"] if s_["estimate"] is not None else s_["actual"])
            ax.annotate(f"{s_['surprise'] * 100:+.0f}%", (i, s_["actual"]), xytext=(0, 9 if above else -13),
                        textcoords="offset points", ha="center", fontsize=7.5, fontweight="bold",
                        color=sc(s_["surprise"]))
        ax.set_ylim(lo - pad, hi + pad)
        ax.set_xlim(-0.4, len(q) - 0.6)
        ax.set_xticks(list(x))
        ax.set_xticklabels([s_["quarter"][:7] for s_ in q], fontsize=7.5)
        from matplotlib.ticker import FormatStrFormatter as _F
        ax.yaxis.set_major_formatter(_F("%.2f"))
        ax.set_title("EPS surprises", fontsize=9, color=color, loc="left", fontweight="bold")
        ax.legend(fontsize=7, frameon=False, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=3, borderaxespad=0.2,
                  handletextpad=0.3, columnspacing=0.8)
    for ax in fig.axes:
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.tick_params(labelsize=7.5)
        ax.grid(axis="y", color="#E5E5E5", lw=0.6)
        ax.set_axisbelow(True)
    fig.tight_layout(w_pad=3)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path


def _num_cell(v):
    """Tabellenwert ('62.3%', '1,234', 25.4, 'n/m') als float oder None."""
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _revenue_margin_chart(metrics, con, path, color):
    """Zwei kleine Panels (keine zweite y-Achse): links Umsatz je Geschaeftsjahr, Konsensjahre heller;
    rechts EBITDA-Marge. Werte aus der Kennzahlentabelle (Yahoo) und dem Konsens (Yahoo)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    years = [c for c in sorted(metrics.columns)]
    rev = [_num_cell(metrics.at["Revenue", c]) if "Revenue" in metrics.index else None for c in years]
    mar = [_num_cell(metrics.at["EBITDA Margin", c]) if "EBITDA Margin" in metrics.index else None for c in years]
    est = [(f"{y['fy']}E", y["rev"]) for y in (con or {}).get("years", []) if y.get("rev")]
    labels = [f"FY{str(c)[-2:]}" for c in years] + [f"FY{e[0][2:4]}E" for e in est]
    vals = rev + [e[1] for e in est]
    if not any(v for v in vals):
        return None
    tint = _tint(color, 0.55)
    plt.rcParams.update({"font.size": 8})
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.2, 2.7), gridspec_kw={"width_ratios": [1.5, 1]})
    big = max(v or 0 for v in vals) >= 10_000
    scale, unit = (1000, "bn") if big else (1, "mn")
    xs = range(len(labels))
    a1.bar(xs, [(v or 0) / scale for v in vals], width=0.55,
           color=[color] * len(rev) + [tint] * len(est), edgecolor="white", linewidth=1)
    for x, v in zip(xs, vals):
        if v:
            a1.text(x, v / scale, f"{v / scale:,.1f}" if big else f"{v:,.0f}", ha="center", va="bottom", fontsize=7,
                    color="#333")
    a1.set_xticks(list(xs))
    a1.set_xticklabels(labels)
    a1.set_title(f"Revenue ({unit}, reporting currency; E = consensus)", loc="left", fontsize=8.5)
    pts = [(i, m) for i, m in enumerate(mar) if m is not None]
    if pts:
        a2.plot([p[0] for p in pts], [p[1] for p in pts], color=color, marker="o", lw=1.8, ms=4)
        for i, m in pts:
            a2.text(i, m, f"{m:.1f}%", ha="center", va="bottom", fontsize=7, color="#333")
        lo, hi = min(p[1] for p in pts), max(p[1] for p in pts)
        a2.set_ylim(min(0, lo - 5), hi + max(5, (hi - lo) * 0.3))
    a2.set_xticks(range(len(years)))
    a2.set_xlim(-0.5, len(years) - 0.5)
    a2.set_xticklabels([f"FY{str(c)[-2:]}" for c in years])
    a2.set_title("EBITDA margin (%)", loc="left", fontsize=8.5)
    for ax in (a1, a2):
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.spines["left"].set_color("#bbb")
        ax.spines["bottom"].set_color("#bbb")
        ax.tick_params(colors="#444")
        ax.yaxis.grid(True, color="#eee")
        ax.set_axisbelow(True)
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close(fig)
    return path


def _leverage_table(ticker_symbol, max_fy, n=3):
    """Verschuldung und Deckung je Geschaeftsjahr aus den Yahoo-Abschluessen: [(Jahr, {kennzahl: wert})]."""
    import pandas as pd
    try:
        inc, bs = YFinanceUtils.get_income_stmt(ticker_symbol), YFinanceUtils.get_balance_sheet(ticker_symbol)
    except Exception:
        return []

    def g(df, names, c):
        for nm in names:
            if df is not None and nm in df.index and c in df.columns and pd.notna(df.at[nm, c]):
                return float(df.at[nm, c])
        return None
    cols = sorted([c for c in inc.columns if c in bs.columns and (max_fy is None or pd.Timestamp(c).year <= max_fy)])[-n:]
    out = []
    for c in cols:
        ebitda = g(inc, ["EBITDA", "Normalized EBITDA"], c)
        ebit = g(inc, ["EBIT", "Operating Income"], c)
        intr = g(inc, ["Interest Expense", "Interest Expense Non Operating"], c)
        debt = g(bs, ["Total Debt"], c) or 0.0
        cash = g(bs, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"], c) or 0.0
        ca, cl = g(bs, ["Current Assets"], c), g(bs, ["Current Liabilities"], c)
        eq, ta = g(bs, ["Stockholders Equity", "Common Stock Equity"], c), g(bs, ["Total Assets"], c)
        nd = debt - cash
        out.append((pd.Timestamp(c).year, {
            "nd_ebitda": None if not ebitda or ebitda <= 0 else nd / ebitda,
            "coverage": None if not intr or not ebit or abs(intr) < 1 else ebit / abs(intr),
            "current": None if not ca or not cl else ca / cl,
            "equity_ratio": None if not eq or not ta else eq / ta,
            "net_debt": nd}))
    return out


def _kpi_strip(ticker_symbol, info, metrics, own_fy, con, theses, usable, PANEL, NAVY, cell):
    """Sechs Kacheln: Kurs, Boersenwert, EV/EBITDA, FCF-Rendite, vom Kurs eingepreistes Wachstum, Thesen."""
    from reportlab.lib.units import cm
    from .outlook import reverse_dcf, _fx_to_fin
    cur = info.get("currency") or "USD"
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "TWD": "NT$"}.get(cur, cur + " ")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    lo, hi = info.get("fiftyTwoWeekLow"), info.get("fiftyTwoWeekHigh")
    mc = info.get("marketCap")
    big = lambda v: "n/a" if not v else (f"{sym}{v / 1e12:,.2f} tn" if v >= 1e12 else f"{sym}{v / 1e9:,.0f} bn")
    ev_row = [(_num_cell(metrics.at["EV/EBITDA", c]), c) for c in sorted(metrics.columns)] if "EV/EBITDA" in metrics.index else []
    ev_vals = [v for v, _ in ev_row if v is not None]
    ev_now = ev_row[-1][0] if ev_row else None
    fcf = _num_cell(metrics.at["FCF", own_fy]) if "FCF" in metrics.index and own_fy in metrics.columns else None
    fx = _fx_to_fin(info)
    mc_fin = mc * fx / 1e6 if mc and fx else None
    fcf_y = fcf / mc_fin if fcf is not None and mc_fin else None
    try:
        rd = reverse_dcf(ticker_symbol, fy=int(own_fy)) if str(own_fy).isdigit() else {"error": "n/a"}
    except Exception:
        rd = {"error": "n/a"}
    g = rd.get("implied_g") if not rd.get("error") and isinstance(rd.get("implied_g"), float) else None
    cg = (con.get("years") or [{}])[0].get("growth") if con else None
    tiles = [
        ("Price", f"{sym}{price:,.2f}" if price else "n/a", f"52w {lo:,.0f}–{hi:,.0f}" if lo and hi else ""),
        ("Market cap", big(mc), cur),
        (f"EV/EBITDA FY{str(own_fy)[-2:]}", f"{ev_now:.1f}x" if ev_now else "n/a",
         f"avg. {len(ev_vals)}y {sum(ev_vals) / len(ev_vals):.1f}x" if len(ev_vals) > 1 else ""),
        ("FCF yield", f"{fcf_y * 100:.1f}%" if fcf_y is not None else "n/a", "FCF / market cap"),
        ("Price implies", f"{g * 100:.1f}% p.a." if g is not None else "n/a",
         (f"consensus {cg * 100:.1f}%" if cg is not None else "10y revenue growth")),
        ("Theses", str(len(theses or [])), "signposts p. 2"),
    ]
    lab = ParagraphStyle("KpiL", parent=cell, fontSize=6.8, leading=8, textColor=colors.HexColor("#5A6472"))
    val = ParagraphStyle("KpiV", parent=cell, fontName="Helvetica-Bold", fontSize=11.5, leading=13.5, textColor=NAVY)
    sub_ = ParagraphStyle("KpiS", parent=cell, fontSize=6.6, leading=8, textColor=colors.HexColor("#5A6472"))
    cells = [[Paragraph(l_, lab), Paragraph(v_, val), Paragraph(s_, sub_)] for l_, v_, s_ in tiles]
    gap = 0.18 * cm
    w = (usable - 5 * gap) / 6
    row, widths = [], []
    for i, c_ in enumerate(cells):
        row.append(c_)
        widths.append(w)
        if i < 5:
            row.append("")
            widths.append(gap)
    t = Table([row], colWidths=widths)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5),
             ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    style += [("BACKGROUND", (2 * i, 0), (2 * i, 0), PANEL) for i in range(6)]
    t.setStyle(TableStyle(style))
    return t


def reset_build_rounds():
    """Vor jedem neuen Agenten-Lauf aufrufen (zaehlt die PDF-Builds je Datei)."""
    _BUILD_ROUNDS.clear()


def _tint(hex_color, share_white):
    """Mischt eine Farbe mit Weiss (share_white 0..1) fuer Kasten- und Linienfarben."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    mix = lambda c: round(c + (255 - c) * share_white)
    return "#{:02X}{:02X}{:02X}".format(mix(r), mix(g), mix(b))

def _heading_font():
    """Georgia Bold fuer Ueberschriften, falls installiert (Windows/macOS); sonst Times-Bold."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    if "Georgia-Bold" in pdfmetrics.getRegisteredFontNames():
        return "Georgia-Bold"
    candidates = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "georgiab.ttf"),
        "/Library/Fonts/Georgia Bold.ttf", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/msttcorefonts/Georgia_Bold.ttf",
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont("Georgia-Bold", path))
                return "Georgia-Bold"
            except Exception:
                pass
    return "Times-Bold"

CITATION_GUIDE = (
    " Cite sources inline with numbers: [1] = the 10-K filing, [2] = Yahoo Finance financial statements and prices,"
    " [3] = analyst consensus (rating, target price), [4] = peer company financials."
    " Separate 2-4 paragraphs with a blank line."
)


def _scaled_image(path, max_width, max_height=None):
    from reportlab.lib.utils import ImageReader
    if not path or not os.path.isfile(path):
        return Paragraph(f"<i>Chart not available ({path})</i>", getSampleStyleSheet()["Normal"])
    w, h = ImageReader(path).getSize()
    scale = max_width / w
    if max_height and h * scale > max_height:
        scale = max_height / h
    return Image(path, width=w * scale, height=h * scale)


def _paragraphs(text, style):
    import html as _html
    out = []
    # Modelle uebergeben Absatzwechsel manchmal als Text "\\n" statt als echten Zeilenumbruch
    text = str(text).replace("\r", "").replace("\\n", "\n")
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        out.append(Paragraph(_html.escape(para, quote=False), style))
    return out


def _annual_form(ticker_symbol, filing_date):
    """'10-K' oder bei auslaendischen Emittenten '20-F'/'40-F' (fuer Beschriftungen)."""
    return ((_tenk_reference(ticker_symbol, filing_date) or {}).get("form") or "10-K").replace("/A", "")


def _tenk_method(ticker_symbol, tenk):
    """Wie die 10-K-Abschnitte gewonnen wurden (Quellenverzeichnis): eigene EDGAR-Zerlegung oder frueher sec-api.io."""
    try:
        from ..data_source.sec_utils import CACHE_PATH
        fy = str((tenk or {}).get("report_date") or "")[:4]
        p_ = os.path.join(CACHE_PATH, "sec_utils", f"{ticker_symbol}_{fy}_7.txt")
        if os.path.exists(p_):
            with open(p_, encoding="utf-8") as f_:
                if f_.read(1) == "[":
                    return "Items 1, 1A and 7 parsed from the EDGAR document"
    except Exception:
        pass
    return "Items 1, 1A and 7 retrieved via sec-api.io"


def _tenk_reference(ticker_symbol, filing_date):
    """Sucht das 10-K mit dem angegebenen Einreichungsdatum in EDGAR (fuer das Quellenverzeichnis)."""
    try:
        from ..data_source.fmp_utils import _find_10k
        y = int(str(filing_date)[:4])
        for fy in (str(y - 1), str(y), "latest"):
            try:
                hit = _find_10k(ticker_symbol, fy)
            except Exception:
                continue
            if hit.get("filing_date") == str(filing_date) or fy == "latest":
                return hit
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Eigene Ergaenzungen: Segmenttabelle, Peer-Tabelle, Faktencheck-Anhang
# ---------------------------------------------------------------------------
def _parse_segments(segment_data):
    """segment_data: JSON-Liste [{"segment": str, "prior_revenue": float, "current_revenue": float}] in USD Mio."""
    import json
    if not segment_data or not str(segment_data).strip():
        return []
    data = json.loads(segment_data) if isinstance(segment_data, str) else segment_data
    rows = []
    for d in data:
        rows.append({"segment": str(d["segment"]),
                     "prior": float(d["prior_revenue"]) if d.get("prior_revenue") not in (None, "") else None,
                     "current": float(d["current_revenue"])})
    return rows


def _company_name(sym):
    try:
        inf = YFinanceUtils.get_stock_info(sym) or {}
        return inf.get("longName") or inf.get("shortName") or sym
    except Exception:
        return sym


def _peer_tickers_from_text(text, own):
    import re
    found = []
    for t in re.findall(r"\(([A-Z]{1,5})\)", str(text)):
        if t != own and t not in found:
            found.append(t)
    return found


def _latest(df, row):
    if df is None or df.empty or row not in df.index:
        return "n/a"
    return df.loc[row, sorted(df.columns)[-1]]


def _fcf_margin(df):
    try:
        f, r = float(_latest(df, "FCF")), float(_latest(df, "Revenue"))
        return f"{f / r * 100:.1f}%" if r else "n/a"
    except (TypeError, ValueError):
        return "n/a"


def _collect_sources(ticker_symbol, filing_date, metrics, key_data, peer_metrics):
    """Baut die Quellen-Indizes fuer den Faktencheck aus genau den Daten, die der Agent bekam."""
    import glob
    from .fact_check import SourceIndex
    from ..data_source.sec_utils import CACHE_PATH

    s1 = SourceIndex("[1] 10-K")
    tenk = _tenk_reference(ticker_symbol, filing_date)
    fy = (tenk or {}).get("report_date", "")[:4] or "*"
    files = glob.glob(os.path.join(CACHE_PATH, "sec_utils", f"{ticker_symbol}_{fy}_*.txt"))
    for f in files:
        with open(f, encoding="utf-8", errors="ignore") as fh:
            s1.add_text(fh.read())

    def _df(src, df, prefix="", raw_usd=False):
        """Tabellenwerte mit Zeilen- und Spaltenname als Notiz (Kontext fuer den Faktencheck und den Tooltip)."""
        for row in df.index:
            for col in df.columns:
                v = df.at[row, col]
                col_s = str(col)[:10] if hasattr(col, "year") else str(col)
                note = f"{prefix}{row} {col_s}: "
                if raw_usd:
                    try:
                        src.add_raw_usd(v, note=note + f"{float(v):,.0f} USD")
                    except (TypeError, ValueError):
                        pass
                else:
                    src.add_value(v, note=note + str(v))

    s2 = SourceIndex("[2] Yahoo Finance")
    for getter in (YFinanceUtils.get_income_stmt, YFinanceUtils.get_balance_sheet, YFinanceUtils.get_cash_flow):
        try:
            _df(s2, getter(ticker_symbol), raw_usd=True)
        except Exception:
            pass
    try:
        _df(s2, metrics)
    except Exception:
        for v in metrics.values.flatten():
            s2.add_value(v)
    for v in key_data.values():
        s2.add_text(str(v))
    try:
        for row in ("Diluted EPS", "Basic EPS"):
            inc = YFinanceUtils.get_income_stmt(ticker_symbol)
            if row in inc.index:
                for v in inc.loc[row].values:
                    s2.add_value(v)
    except Exception:
        pass

    s4 = SourceIndex("[4] Peer data")
    for sym, df in peer_metrics.items():
        try:
            _df(s4, df, prefix=f"{sym} ")
        except Exception:
            for v in df.values.flatten():
                s4.add_value(v)
        try:
            for getter in (YFinanceUtils.get_income_stmt, YFinanceUtils.get_cash_flow):
                _df(s4, getter(sym), prefix=f"{sym} ", raw_usd=True)
        except Exception:
            pass
    return [s1, s2, s4], len(files)


def _factcheck_flowables(fc, n_tenk_files, styles, usable, heading=None):
    from xml.sax.saxutils import escape
    h2, body, small, cell, cell_r, line = styles
    H = heading or (lambda t, space_before=10: [Spacer(1, space_before), Paragraph(t, h2)])
    out = H("Appendix: Automated Fact Check", 14) + [
           Paragraph(
               "Every number in the report text was compared with the data the agent received: the 10-K sections [1], "
               "the company's Yahoo Finance data [2] and the peer data [4]. A match means the figure appears in a source "
               "(within rounding). 'Not found' does not automatically mean wrong: the figure may be derived (e.g. a ratio "
               "computed by the model) and requires manual review. Ticker names are checked against the official company names.",
               small), Spacer(1, 6)]
    rate = f"{fc['match_rate'] * 100:.0f}%" if fc["match_rate"] is not None else "n/a"
    rows = [[Paragraph("<font color='white'><b>Summary</b></font>", cell), ""],
            [Paragraph("Numeric claims checked", cell), Paragraph(str(fc["total_claims"]), cell_r)],
            [Paragraph("Found in sources", cell), Paragraph(f"{fc['matched']} ({rate})", cell_r)]]
    for src, n in fc["by_source"].items():
        rows.append([Paragraph(f"&nbsp;&nbsp;thereof {escape(src)}", cell), Paragraph(str(n), cell_r)])
    for k, v in fc["by_kind"].items():
        rows.append([Paragraph(f"Type '{k}': found / total", cell), Paragraph(f"{v['matched']} / {v['total']}", cell_r)])
    rows.append([Paragraph("Name/ticker mismatches", cell), Paragraph(str(len(fc["name_issues"])), cell_r)])
    if n_tenk_files == 0:
        rows.append([Paragraph("<font color='#c62828'>Warning: no cached 10-K text found, source [1] not checked</font>", cell), ""])
    t = Table(rows, colWidths=[usable * 0.6, usable * 0.2])
    t.setStyle(line)
    out += [t, Spacer(1, 8)]

    if fc["name_issues"]:
        out += H("Name/ticker mismatches")
        for i in fc["name_issues"]:
            out.append(Paragraph(
                f"<font color='#c62828'><b>{escape(i['written'])} ({i['ticker']})</b></font>: official name is "
                f"<b>{escape(i['official'])}</b> (section: {escape(i['section'])}).", body))

    if fc["unmatched"]:
        from reportlab.platypus import CondPageBreak as _CPB
        out.append(_CPB(4 * 28.35))
        out += H("Figures not found in the sources (manual review)")
        rows = [[Paragraph("<font color='white'><b>Section</b></font>", cell), Paragraph("<font color='white'><b>Figure</b></font>", cell), Paragraph("<font color='white'><b>Context</b></font>", cell)]]
        for u in fc["unmatched"][:45]:
            rows.append([Paragraph(escape(u["section"]), cell), Paragraph(escape(u["text"]), cell),
                         Paragraph(escape(u["context"]), cell)])
        t = Table(rows, colWidths=[usable * 0.18, usable * 0.12, usable * 0.70], repeatRows=1)
        t.setStyle(TableStyle(line.getCommands() + [("VALIGN", (0, 0), (-1, -1), "TOP"),
                                                    ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black)]))
        out.append(t)
        if len(fc["unmatched"]) > 45:
            out.append(Paragraph(f"... and {len(fc['unmatched']) - 45} more (see the JSON file next to the PDF).", small))
    return out


def _build_report_v3(ticker_symbol, pdf_path, summary, sections, share_img, val_img, filing_date,
                     peer_tickers=None, segments=None):
    from datetime import date
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepInFrame, CondPageBreak

    page_w, page_h = pagesizes.A4
    m = 1.6 * cm
    usable = page_w - 2 * m
    doc = SimpleDocTemplate(
        pdf_path, pagesize=pagesizes.A4,
        leftMargin=m, rightMargin=m, topMargin=m, bottomMargin=m,
        title=f"{ticker_symbol} Equity Research Report",
    )
    ss = getSampleStyleSheet()
    hfont = _heading_font()
    body = ParagraphStyle("BodyV3", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=7)
    body_s = ParagraphStyle("BodySV3", parent=body, fontSize=9.5, leading=13, spaceAfter=6)
    small = ParagraphStyle("SmallV3", parent=ss["Normal"], fontName="Helvetica",
                           fontSize=7.5, leading=9.5, textColor=colors.HexColor("#555555"))
    cell = ParagraphStyle("CellV3", parent=ss["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    cell_r = ParagraphStyle("CellRV3", parent=cell, alignment=2)
    title = ParagraphStyle("TitleV3", parent=ss["Title"], fontName=hfont,
                           fontSize=18, leading=22, alignment=TA_LEFT, spaceAfter=2)
    over = ParagraphStyle("OverV3", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8,
                          leading=10, textColor=colors.HexColor("#1f4e79"), spaceAfter=1)
    sub = ParagraphStyle("SubV3", parent=ss["Normal"], fontName="Helvetica",
                         fontSize=9, leading=12, textColor=colors.HexColor("#444444"), spaceAfter=8)
    h2 = ParagraphStyle("H2V3", parent=ss["Heading2"], fontName=hfont,
                        fontSize=13, leading=16, spaceBefore=8, spaceAfter=4)
    h3 = ParagraphStyle("H3V3", parent=ss["Heading3"], fontName=hfont,
                        fontSize=10.5, leading=13, spaceBefore=2, spaceAfter=3)
    ref = ParagraphStyle("RefV3", parent=ss["Normal"], fontName="Helvetica", fontSize=9, leading=12,
                         leftIndent=0.8 * cm, firstLineIndent=-0.8 * cm, spaceAfter=4)
    line = TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 1.2, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ])

    info = YFinanceUtils.get_stock_info(ticker_symbol) or {}
    name = info.get("shortName") or info.get("longName") or ticker_symbol
    currency = info.get("financialCurrency") or info.get("currency", "USD")   # Abschluss-, nicht Handelswaehrung (ADR)

    content = [
        Paragraph("EQUITY RESEARCH REPORT", over),
        Paragraph(f"{name} ({ticker_symbol})", title),
        Paragraph(f"Based on the {_annual_form(ticker_symbol, filing_date)} filed {filing_date} [1] &nbsp;|&nbsp; generated with {REPORT_BRAND}"
                  + ("" if "FinRobot" in REPORT_BRAND else " (built on FinRobot)"), sub),
    ]

    # --- Seite 1: links Text, rechts Charts und Key Data -------------------
    gap = 0.5 * cm
    left_w = usable * 0.52
    right_w = usable - left_w - gap
    row_h = 16.6 * cm

    left = [Paragraph("Investment Summary", h2)] + _paragraphs(summary, body_s)

    key_data = ReportAnalysisUtils.get_key_data(ticker_symbol, filing_date)
    kd_rows = [[Paragraph("<b>Key data</b>", h3), ""]]
    kd_rows += [[Paragraph(str(k), cell), Paragraph(str(v), cell_r)] for k, v in key_data.items()]
    kd = Table(kd_rows, colWidths=[right_w * 0.55, right_w * 0.45])
    kd.setStyle(line)
    right = [
        Paragraph("Share Performance", h3), _scaled_image(share_img, right_w, 4.6 * cm), Spacer(1, 0.2 * cm),
        kd,
        Paragraph("Prices as of the filing date [2]; rating and target price are the current analyst consensus [3].", small),
        Spacer(1, 0.25 * cm),
        Paragraph("Valuation", h3), _scaled_image(val_img, right_w, 6.4 * cm),
    ]
    row = Table(
        [[KeepInFrame(left_w, row_h, left, mode="shrink"), "", KeepInFrame(right_w, row_h, right, mode="shrink")]],
        colWidths=[left_w, gap, right_w],
    )
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    content += [row, Spacer(1, 0.3 * cm)]

    # --- Seite 1 unten: Financial Metrics -----------------------------------
    metrics = FMPUtils.get_financial_metrics(ticker_symbol, years=5)
    df = metrics.reset_index()
    df = df.rename(columns={"index": f"FY ({currency} mn)"})
    n = df.shape[1]
    first_w = usable * 0.28
    fm_rows = [[Paragraph("<b>Financial Metrics</b> [2]", h3)] + [""] * (n - 1)]
    fm_rows += [[Paragraph(f"<b>{c}</b>", cell if i == 0 else cell_r) for i, c in enumerate(df.columns)]]
    fmt = lambda v: f"<i>{v}</i>" if isinstance(v, str) and v.endswith("%") else str(v)
    fm_rows += [[Paragraph(fmt(v), cell if i == 0 else cell_r) for i, v in enumerate(r)] for r in df.values.tolist()]
    fm = Table(fm_rows, colWidths=[first_w] + [(usable - first_w) / (n - 1)] * (n - 1))
    fm.setStyle(TableStyle(line.getCommands() + [
        ("SPAN", (0, 0), (-1, 0)), ("LINEBELOW", (0, 1), (-1, 1), 0.6, colors.black),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#F3F4F6")]),
    ]))
    content += [fm, Paragraph("n/a = not available; n/m = not meaningful (e.g. multiple with negative denominator).", small),
                PageBreak()]

    # --- Ab Seite 2: Abschnitte ---------------------------------------------
    sec = dict(sections)
    own_fy = str(sorted(metrics.columns)[-1]) if len(metrics.columns) else "current"
    # Peer-Daten (fuer Tabelle und Faktencheck)
    peers = list(peer_tickers or []) or _peer_tickers_from_text(sec.get("Competitors Analysis", ""), ticker_symbol)
    peer_metrics, peer_errors = {}, []
    for ptk in peers:
        try:
            peer_metrics[ptk] = FMPUtils.get_financial_metrics(ptk, years=4)
        except Exception as e:
            peer_errors.append(f"{ptk}: {e}")
    names = {t_: _company_name(t_) for t_ in [ticker_symbol] + list(peer_metrics)}

    for heading, text in sections:
        content.append(Paragraph(heading, h2))
        content += _paragraphs(text, body)
        if heading == "Operating Results" and segments:
            prior_fy = str(int(own_fy) - 1) if own_fy.isdigit() else "prior"
            rows = [[Paragraph("<b>Segment revenue</b> [1]", h3), "", "", ""],
                    [Paragraph(f"<b>{c}</b>", cell if i == 0 else cell_r) for i, c in
                     enumerate([f"Segment ({currency} mn)", f"FY{prior_fy}", f"FY{own_fy}", "Growth"])]]
            for sg in segments:
                g = (sg["current"] / sg["prior"] - 1) * 100 if sg["prior"] else None
                rows.append([Paragraph(sg["segment"], cell),
                             Paragraph("n/a" if sg["prior"] is None else f"{sg['prior']:,.1f}", cell_r),
                             Paragraph(f"{sg['current']:,.1f}", cell_r),
                             Paragraph("n/a" if g is None else f"<i>{g:+.1f}%</i>", cell_r)])
            tot_p = sum(sg["prior"] for sg in segments if sg["prior"]) if all(sg["prior"] for sg in segments) else None
            tot_c = sum(sg["current"] for sg in segments)
            rows.append([Paragraph("<b>Total</b>", cell),
                         Paragraph("n/a" if tot_p is None else f"<b>{tot_p:,.1f}</b>", cell_r),
                         Paragraph(f"<b>{tot_c:,.1f}</b>", cell_r),
                         Paragraph("n/a" if not tot_p else f"<i><b>{(tot_c / tot_p - 1) * 100:+.1f}%</b></i>", cell_r)])
            tb = Table(rows, colWidths=[usable * 0.40, usable * 0.20, usable * 0.20, usable * 0.20])
            tb.setStyle(TableStyle(line.getCommands() + [("SPAN", (0, 0), (-1, 0)),
                                                         ("LINEBELOW", (0, 1), (-1, 1), 0.6, colors.black),
                                                         ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black)]))
            content += [Spacer(1, 4), tb, Spacer(1, 8)]
        if heading == "Competitors Analysis" and peer_metrics:
            cols = ["Company", "FY", f"Revenue ({currency} mn)", "Growth", "Gross margin", "EBITDA margin",
                    "FCF margin", "EV/Sales", "P/B"]
            rows = [[Paragraph("<b>Peer comparison, latest fiscal year</b> [2][4]", h3)] + [""] * 8,
                    [Paragraph(f"<b>{c}</b>", cell if i == 0 else cell_r) for i, c in enumerate(cols)]]
            for t_, m_ in [(ticker_symbol, metrics)] + list(peer_metrics.items()):
                vals = [f"{names.get(t_, t_)} ({t_})", str(sorted(m_.columns)[-1]), _latest(m_, "Revenue"),
                        _latest(m_, "Revenue Growth"), _latest(m_, "Gross Margin"), _latest(m_, "EBITDA Margin"),
                        _fcf_margin(m_), _latest(m_, "EV/Sales"), _latest(m_, "PB Ratio")]
                bold = t_ == ticker_symbol
                rows.append([Paragraph((f"<b>{v}</b>" if bold else str(v)) if i == 0 else
                                       (f"<i>{v}</i>" if str(v).endswith("%") else str(v)), cell if i == 0 else cell_r)
                             for i, v in enumerate(vals)])
            w0 = usable * 0.26
            tb = Table(rows, colWidths=[w0] + [(usable - w0) / 8] * 8)
            tb.setStyle(TableStyle(line.getCommands() + [("SPAN", (0, 0), (-1, 0)),
                                                         ("LINEBELOW", (0, 1), (-1, 1), 0.6, colors.black)]))
            content += [Spacer(1, 4), tb]
            note = "Fiscal year ends can differ between companies (e.g. Planet Labs ends in January)."
            if peer_errors:
                note += " Not available: " + "; ".join(peer_errors)
            content += [Paragraph(note, small), Spacer(1, 8)]

    # --- Quellenverzeichnis ---------------------------------------------------
    today = date.today().isoformat()
    tenk = _tenk_reference(ticker_symbol, filing_date)
    form_ = (tenk or {}).get("form", "10-K")
    how_ = ("Items 4, 3D and 5 parsed from the EDGAR document" if form_.startswith(("20-F", "40-F"))
            else _tenk_method(ticker_symbol, tenk))
    if tenk:
        u_ = str(tenk.get("url") or "")
        from xml.sax.saxutils import escape as _xe
        link_ = f"<link href='{_xe(u_)}' color='#185FA5'><u>{_xe(u_)}</u></link>" if u_.startswith("https://") else _xe(u_)
        r1 = (f"{name}, Form {form_} for the fiscal year ended {tenk.get('report_date', 'n/a')}, filed {tenk.get('filing_date')}, "
              f"SEC EDGAR, {link_} ({how_}).")
    else:
        r1 = f"{name}, Form {form_} filed {filing_date}, SEC EDGAR ({how_})."
    refs = [
        r1,
        f"Yahoo Finance: annual financial statements and daily share prices for {ticker_symbol}, retrieved {today} via yfinance.",
        f"Yahoo Finance: analyst recommendations and price targets for {ticker_symbol}, retrieved {today} (current consensus, not as of the filing date).",
        f"Yahoo Finance: annual financial statements of the peer companies named in the Competitors Analysis, retrieved {today}.",
    ]
    content += [CondPageBreak(6 * cm), Paragraph("Sources", h2)]
    content += [Paragraph(f"[{i}]&nbsp;&nbsp;{r}", ref) for i, r in enumerate(refs, 1)]

    # --- Anhang: automatischer Faktencheck -----------------------------------
    from .fact_check import run_fact_check, save_json
    fc_sections = [("Investment Summary", summary)] + list(sections)
    if segments:
        fc_sections.append(("Segment table", "; ".join(
            f"{sg['segment']}: ${sg['current']} million" + (f", prior ${sg['prior']} million" if sg["prior"] else "")
            for sg in segments)))
    srcs, n_tenk = _collect_sources(ticker_symbol, filing_date, metrics, key_data, peer_metrics)
    fc = run_fact_check(fc_sections, srcs, names)
    fc["peer_tickers"] = list(peer_metrics)
    save_json(fc, os.path.splitext(pdf_path)[0] + "_factcheck.json")
    content += _factcheck_flowables(fc, n_tenk, (h2, body, small, cell, cell_r, line), usable)

    def _footer(canv, d):
        canv.saveState()
        canv.setFont("Helvetica", 7.5)
        canv.setFillColor(colors.HexColor("#777777"))
        canv.drawString(m, 0.9 * cm, f"{name} ({ticker_symbol}) - {REPORT_BRAND} - for academic purposes only, not investment advice")
        canv.drawRightString(page_w - m, 0.9 * cm, f"Page {d.page}")
        canv.restoreState()

    doc.build(content, onFirstPage=_footer, onLaterPages=_footer)
    return (f"Annual report generated successfully. Fact check: {fc['matched']} of {fc['total_claims']} figures found "
            f"in the sources, {len(fc['name_issues'])} name/ticker mismatch(es). Details in the appendix of the PDF.")


def _build_report_v4(ticker_symbol, pdf_path, summary, sections, share_img, val_img, filing_date,
                     peer_tickers=None, segments=None, takeaways=None, theses=None):
    from datetime import date
    from xml.sax.saxutils import escape as _esc
    from reportlab.lib.units import cm
    from reportlab.platypus import KeepInFrame, CondPageBreak
    import pandas as pd
    from .outlook import get_consensus, get_liquidity, outlook_text, fmt_mn, fmt_runway, fmt_pct, reverse_dcf, fmt_g, implied_irr, estimate_momentum, quality_scores

    page_w, page_h = pagesizes.A4
    m = 1.6 * cm
    usable = page_w - 2 * m
    NAVY, PANEL, RULE, GREY = (colors.HexColor(REPORT_COLOR), colors.HexColor(_tint(REPORT_COLOR, 0.93)),
                               colors.HexColor(_tint(REPORT_COLOR, 0.75)), colors.HexColor("#5A6472"))
    doc = SimpleDocTemplate(
        pdf_path, pagesize=pagesizes.A4,
        leftMargin=m, rightMargin=m, topMargin=2.0 * cm, bottomMargin=1.6 * cm,
        title=f"{ticker_symbol} Equity Research Report",
    )
    ss = getSampleStyleSheet()
    hfont = _heading_font()
    body = ParagraphStyle("BodyV3", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=7)
    body_s = ParagraphStyle("BodySV3", parent=body, fontSize=9.5, leading=13, spaceAfter=6)
    small = ParagraphStyle("SmallV3", parent=ss["Normal"], fontName="Helvetica",
                           fontSize=7.5, leading=9.5, textColor=colors.HexColor("#555555"))
    cell = ParagraphStyle("CellV3", parent=ss["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    cell_r = ParagraphStyle("CellRV3", parent=cell, alignment=2)
    title = ParagraphStyle("TitleV3", parent=ss["Title"], fontName=hfont, textColor=NAVY,
                           fontSize=20, leading=24, alignment=TA_LEFT, spaceAfter=2)
    headline = ParagraphStyle("HeadlineV4", parent=ss["Normal"], fontName=hfont, fontSize=11.5, leading=15,
                              textColor=colors.HexColor("#1F2933"), spaceAfter=4)
    exh = ParagraphStyle("ExhV4", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10,
                         textColor=NAVY, spaceBefore=2, spaceAfter=2)
    src_style = ParagraphStyle("SrcV4", parent=ss["Normal"], fontName="Helvetica", fontSize=6.8, leading=8.5,
                               textColor=GREY, spaceBefore=1, spaceAfter=4)
    cell_w = ParagraphStyle("CellWV4", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10,
                            textColor=colors.white)
    over = ParagraphStyle("OverV3", parent=ss["Normal"], fontName="Helvetica-Bold", fontSize=8,
                          leading=10, textColor=colors.HexColor("#1f4e79"), spaceAfter=1)
    sub = ParagraphStyle("SubV3", parent=ss["Normal"], fontName="Helvetica",
                         fontSize=9, leading=12, textColor=colors.HexColor("#444444"), spaceAfter=8)
    h2 = ParagraphStyle("H2V3", parent=ss["Heading2"], fontName=hfont, textColor=NAVY,
                        fontSize=12.5, leading=15, spaceBefore=0, spaceAfter=0)
    h3 = ParagraphStyle("H3V3", parent=ss["Heading3"], fontName=hfont,
                        fontSize=10.5, leading=13, spaceBefore=2, spaceAfter=3)
    ref = ParagraphStyle("RefV3", parent=ss["Normal"], fontName="Helvetica", fontSize=9, leading=12,
                         leftIndent=0.8 * cm, firstLineIndent=-0.8 * cm, spaceAfter=4)
    line = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
        ("LINEBELOW", (0, -1), (-1, -1), 1.0, NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
    ])

    def heading(text, space_before=10):
        t = Table([[Paragraph(text, h2)]], colWidths=[usable])
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 1.2, NAVY),
                               ("LEFTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                               ("TOPPADDING", (0, 0), (-1, -1), 0)]))
        return [Spacer(1, space_before), t, Spacer(1, 5)]

    def exhibit(num, text):
        return Paragraph(f"Exhibit {num}: {text}", exh)

    def source(text):
        return Paragraph(f"Source: {text}", src_style)

    info = YFinanceUtils.get_stock_info(ticker_symbol) or {}
    name = info.get("shortName") or info.get("longName") or ticker_symbol
    currency = info.get("financialCurrency") or info.get("currency", "USD")   # Abschluss-, nicht Handelswaehrung (ADR)
    sector = " / ".join(x for x in [info.get("sector"), info.get("industry")] if x) or "Equity Research"
    exchange = info.get("exchange") or ""
    import re as _re
    first_sentence = _re.split(r"(?<=[.!?])\s", str(summary).strip(), maxsplit=1)[0]
    first_sentence = _re.sub(r"\s*\[\d+\](\[\d+\])*", "", first_sentence)

    content = [
        Paragraph(f"{_esc(name)} <font size=12 color='#5A6472'>({ticker_symbol}{', ' + exchange if exchange else ''})</font>", title),
        Paragraph(_esc(first_sentence), headline),
        Paragraph(f"Based on the {_annual_form(ticker_symbol, filing_date)} filed {filing_date} [1] &nbsp;|&nbsp; {_esc(sector)} &nbsp;|&nbsp; Generated by {_esc(REPORT_BRAND)}", sub),
    ]

    # --- Seite 1: links Text, rechts Charts und Key Data -------------------
    gap = 0.5 * cm
    left_w = usable * 0.52
    right_w = usable - left_w - gap
    # Hoehe des Kastens: 13.7 cm bei einzeiliger Kopfzeile; jede weitere Zeile von Schlagzeile/Unterzeile zieht ab,
    # damit Exhibit 3 auf Seite 1 bleibt (sonst steht es allein auf Seite 2)
    extra = sum(p_.wrap(usable, 10 * cm)[1] for p_ in content[1:3]) - (headline.leading + sub.leading)
    row_h = max(11.0 * cm, 13.7 * cm - max(0.0, extra))

    from reportlab.platypus import HRFlowable

    def col_heading(text):
        # Ueberschrift mit Linie ueber die volle Spaltenbreite (HRFlowable passt sich der Breite an)
        return [Paragraph(text, h2), HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceBefore=2, spaceAfter=5)]
    left = []
    if takeaways:
        bullet = ParagraphStyle("BulletV5", parent=body_s, leftIndent=9, bulletIndent=0, spaceAfter=4,
                                bulletFontName="Helvetica-Bold", bulletColor=NAVY)
        left += col_heading("Key Takeaways") + [Paragraph(_esc(t_), bullet, bulletText="\u2022") for t_ in takeaways]
        left += [Spacer(1, 6)]
    left += col_heading("Investment Summary") + _paragraphs(summary, body_s)

    key_data = ReportAnalysisUtils.get_key_data(ticker_symbol, filing_date)
    pad = 0.25 * cm
    inner = right_w - 2 * pad
    kd_rows = [[Paragraph("Key data", cell_w), ""]]
    short = lambda k, v: str(v).split(", current")[0].replace("range ", "") if k == "Target Price" else str(v)
    labels = {"52 Week Price Range (USD)": "52-week range (USD)", "6m avg daily vol (USDmn)": "6m avg. daily vol. (USD mn)",
              "Market Cap (USDmn)": "Market cap (USD mn)", "Closing Price (USD)": "Closing price (USD)",
              "Target Price": "Consensus target (USD)", "Rating": "Consensus rating"}
    kd_rows += [[Paragraph(labels.get(k, str(k)), cell), Paragraph(short(k, v), cell_r)] for k, v in key_data.items()]
    kd = Table(kd_rows, colWidths=[inner * 0.52, inner * 0.48])
    kd.setStyle(TableStyle(line.getCommands() + [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                                                  ("TOPPADDING", (0, 0), (-1, -1), 1.3), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3)]))
    fixed = [exhibit(1, "Share price vs S&amp;P 500, rebased to 100"), source("Yahoo Finance [2]"), kd,
             source(f"Prices at the filing date [2]; rating/target: consensus as of {date.today().isoformat()} [3]"),
             exhibit(2, "Valuation: multiple band and FCF yield"),
             source("Yahoo Finance [2], own calculations")]
    # Charts so gross wie moeglich: Resthoehe des Kastens auf die beiden Bilder verteilen
    fixed_h = sum(f_.wrap(inner, 100 * cm)[1] + f_.getSpaceBefore() + f_.getSpaceAfter() for f_ in fixed)
    avail = row_h - 2 * pad - fixed_h - 0.2 * cm

    def _ratio(path_, default):
        try:
            from reportlab.lib.utils import ImageReader
            w_, h_ = ImageReader(path_).getSize()
            return h_ / w_
        except Exception:
            return default
    h1_full, h2_full = inner * _ratio(share_img, 0.5), inner * _ratio(val_img, 0.7)
    f_img = min(1.0, avail / (h1_full + h2_full))  # beide Charts gleich stark verkleinern, falls noetig
    img_h1, img_h2 = h1_full * f_img, h2_full * f_img
    right = [fixed[0], _scaled_image(share_img, inner, img_h1), fixed[1], fixed[2], fixed[3],
             fixed[4], _scaled_image(val_img, inner, img_h2), fixed[5]]
    panel = Table([[KeepInFrame(inner, row_h - 2 * pad, right, mode="shrink")]], colWidths=[right_w])
    panel.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                               ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad)]))
    row = Table(
        [[KeepInFrame(left_w, row_h, left, mode="shrink"), "", panel]],
        colWidths=[left_w, gap, right_w],
    )
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                             ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    content += [row, Spacer(1, 0.3 * cm)]

    # --- Seite 1 unten: Financial Metrics -----------------------------------
    metrics = FMPUtils.get_financial_metrics(ticker_symbol, years=5)
    # Nur Geschaeftsjahre bis einschliesslich des analysierten 10-K zeigen (sonst mischt der Report z. B. das
    # 10-K fuer FY2025 mit Yahoo-Zahlen fuer FY2026, wenn dieses schon berichtet ist)
    try:
        hit_ = _tenk_reference(ticker_symbol, filing_date)
        tenk_fy = int(str(hit_["report_date"])[:4]) if hit_ and hit_.get("report_date") else None
    except Exception:
        tenk_fy = None
    if tenk_fy:
        keep_ = [c_ for c_ in metrics.columns if str(c_)[:4].isdigit() and int(str(c_)[:4]) <= tenk_fy]
        if keep_:
            metrics = metrics[keep_]
    own_fy = str(sorted(metrics.columns)[-1]) if len(metrics.columns) else "current"
    tbl = metrics.copy()
    # EPS-Zeile (Ist-Werte aus der GuV)
    eps_hist = {}
    try:
        inc_ = YFinanceUtils.get_income_stmt(ticker_symbol)
        for c_ in inc_.columns:
            for r_ in ("Diluted EPS", "Basic EPS"):
                if r_ in inc_.index and pd.notna(inc_.loc[r_, c_]):
                    eps_hist[str(pd.Timestamp(c_).year)] = f"{float(inc_.loc[r_, c_]):.2f}"
                    break
    except Exception:
        pass
    pos = list(tbl.index).index("EBITDA Margin") + 1 if "EBITDA Margin" in tbl.index else len(tbl.index)
    eps_row = pd.DataFrame([[eps_hist.get(str(c_), "n/a") for c_ in tbl.columns]], index=["EPS (diluted)"],
                           columns=tbl.columns)
    tbl = pd.concat([tbl.iloc[:pos], eps_row, tbl.iloc[pos:]])
    # Konsens-Spalten (E)
    try:
        con = get_consensus(ticker_symbol, last_fy=int(own_fy)) if own_fy.isdigit() else {"years": [], "error": "no fiscal year"}
    except Exception as e:
        con = {"years": [], "error": str(e), "price": None, "methodology": None}
    n_hist = tbl.shape[1]
    for y in con["years"]:
        vals = {r_: "\u2013" for r_ in tbl.index}
        if y["rev"] is not None:
            vals["Revenue"] = round(y["rev"])
        if y["growth"] is not None:
            vals["Revenue Growth"] = f"{round(y['growth'] * 100, 1)}%"
        if y["eps"] is not None and con.get("eps_comparable", True):   # ADR-EPS in USD passt nicht zur EUR-Historie
            vals["EPS (diluted)"] = f"{y['eps']:.2f}"
        if y["ev_sales"] is not None:
            vals["EV/Sales"] = round(y["ev_sales"], 2)
        vals["PE Ratio"] = round(y["pe"], 2) if y["pe"] is not None else ("n/m" if y["eps"] is not None else "\u2013")
        tbl[f"{y['fy']}E"] = pd.Series(vals)
    df = tbl.reset_index()
    df = df.rename(columns={"index": f"FY ({currency} mn)"})
    n = df.shape[1]
    first_w = usable * 0.28
    cell_wr = ParagraphStyle("CellWRV4", parent=cell_w, alignment=2)
    fm_rows = [[Paragraph(str(c), cell_w if i == 0 else cell_wr) for i, c in enumerate(df.columns)]]
    fmt = lambda v: f"<i>{v}</i>" if isinstance(v, str) and v.endswith("%") else str(v)
    fm_rows += [[Paragraph(fmt(v), cell if i == 0 else cell_r) for i, v in enumerate(r)] for r in df.values.tolist()]
    fm = Table(fm_rows, colWidths=[first_w] + [(usable - first_w) / (n - 1)] * (n - 1))
    est_style = []
    if con["years"]:
        est_style = [("BACKGROUND", (n_hist + 1, 1), (-1, -1), PANEL),
                     ("LINEBEFORE", (n_hist + 1, 0), (n_hist + 1, -1), 0.8, NAVY)]
    fm.setStyle(TableStyle(line.getCommands() + [
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_tint(REPORT_COLOR, 0.96))]),
        ("TOPPADDING", (0, 0), (-1, -1), 0.9), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9),
    ] + est_style))
    fm_note = ("Yahoo Finance [2], own calculations. n/a = not available; n/m = not meaningful "
               "(e.g. multiple with negative denominator).")
    if con["years"]:
        price_txt = f" at the current share price of {con['price']:.2f}" if con.get("price") else " at the current share price"
        meth = f", EPS {con['methodology']}" if con.get("methodology") else ""
        fm_note += (f" E = analyst consensus (mean) retrieved {date.today().isoformat()} [3]{meth}; "
                    f"forward P/E and EV/Sales{price_txt}. \u2013 = no consensus available.")
    elif con.get("error"):
        fm_note += f" Consensus estimates not shown: {con['error']}."
    from reportlab.platypus import KeepTogether
    content += [KeepTogether([exhibit(3, "Financial metrics and consensus estimates" if con["years"] else "Financial metrics"),
                              fm, source(fm_note)]),
                PageBreak()]
    # --- Kennzahlenleiste unter dem Titel (deterministisch, Quellen [2][3]) --
    try:
        strip = _kpi_strip(ticker_symbol, info, metrics, own_fy, con, theses, usable, PANEL, NAVY, cell)
        if strip is not None:
            content.insert(3, strip)
            content.insert(4, Spacer(1, 0.25 * cm))
    except Exception as e_:
        print(f"Kennzahlenleiste nicht erstellt: {e_}")

    # --- Ab Seite 2: Abschnitte ---------------------------------------------
    sec = dict(sections)
    ex_no = [3]

    def next_ex():
        ex_no[0] += 1
        return ex_no[0]
    # Peer-Daten (fuer Tabelle und Faktencheck)
    peers = list(peer_tickers or []) or _peer_tickers_from_text(sec.get("Competitors Analysis", ""), ticker_symbol)
    peer_metrics, peer_errors = {}, []
    for ptk in peers:
        try:
            peer_metrics[ptk] = FMPUtils.get_financial_metrics(ptk, years=4)
        except Exception as e:
            peer_errors.append(f"{ptk}: {e}")
    names = {t_: _company_name(t_) for t_ in [ticker_symbol] + list(peer_metrics)}

    if theses:
        rows = [[Paragraph(h_, cell_w) for h_ in ("Thesis", "Evidence", "Signpost (what we watch)", "What would prove it wrong")]]
        for th_ in theses:
            rows.append([Paragraph(f"<b>{_esc(th_['thesis'])}</b>", cell), Paragraph(_esc(th_["evidence"]), cell),
                         Paragraph(_esc(th_["signpost"]), cell), Paragraph(_esc(th_["invalidation"]), cell)])
        tth = Table(rows, colWidths=[usable * 0.27, usable * 0.29, usable * 0.22, usable * 0.22], repeatRows=1)
        tth.setStyle(TableStyle(line.getCommands() + [("VALIGN", (0, 0), (-1, -1), "TOP")]))
        content += heading("Investment Thesis") + [exhibit(next_ex(), "Investment theses, signposts and invalidation"), tth,
                                                   source("Agent's assessment based on the 10-K [1] and market data [2][3]; "
                                                          "signposts are checked in the earnings and thesis updates.")]

    for sec_title, text in sections:
        content += heading(sec_title)
        content += _paragraphs(text, body)
        if sec_title == "Operating Results" and segments:
            prior_fy = str(int(own_fy) - 1) if own_fy.isdigit() else "prior"
            rows = [[Paragraph(c, cell_w if i == 0 else cell_wr) for i, c in
                     enumerate([f"Segment ({currency} mn)", f"FY{prior_fy}", f"FY{own_fy}", "Growth"])]]
            for sg in segments:
                g = (sg["current"] / sg["prior"] - 1) * 100 if sg["prior"] else None
                rows.append([Paragraph(sg["segment"], cell),
                             Paragraph("n/a" if sg["prior"] is None else f"{sg['prior']:,.1f}", cell_r),
                             Paragraph(f"{sg['current']:,.1f}", cell_r),
                             Paragraph("n/a" if g is None else f"<i>{g:+.1f}%</i>", cell_r)])
            tot_p = sum(sg["prior"] for sg in segments if sg["prior"]) if all(sg["prior"] for sg in segments) else None
            tot_c = sum(sg["current"] for sg in segments)
            rows.append([Paragraph("<b>Total</b>", cell),
                         Paragraph("n/a" if tot_p is None else f"<b>{tot_p:,.1f}</b>", cell_r),
                         Paragraph(f"<b>{tot_c:,.1f}</b>", cell_r),
                         Paragraph("n/a" if not tot_p else f"<i><b>{(tot_c / tot_p - 1) * 100:+.1f}%</b></i>", cell_r)])
            tb = Table(rows, colWidths=[usable * 0.40, usable * 0.20, usable * 0.20, usable * 0.20])
            tb.setStyle(TableStyle(line.getCommands() + [("LINEABOVE", (0, -1), (-1, -1), 0.8, NAVY)]))
            content += [KeepTogether([Spacer(1, 4), exhibit(next_ex(), "Segment revenue"), tb,
                                      source("10-K [1]; growth: own calculation")])]
        if sec_title == "Operating Results":
            try:
                liq = get_liquidity(ticker_symbol, fy=int(own_fy)) if own_fy.isdigit() else {"columns": []}
            except Exception:
                liq = {"columns": []}
            if liq["columns"]:
                ratio = lambda v: "n/a" if v is None else f"{v:.1f}x"
                pct_i = lambda v: "n/a" if v is None else f"<i>{fmt_pct(v)}</i>"
                spec = [("Cash and short-term investments", "cash", fmt_mn), ("Total debt", "debt", fmt_mn),
                        ("Net cash / (net debt)", "net_cash", fmt_mn), ("Free cash flow", "fcf", fmt_mn),
                        ("Cash runway at this FCF burn", "runway", fmt_runway), ("Current ratio", "current_ratio", ratio),
                        ("Shares outstanding (mn)", "shares", fmt_mn), ("Change in share count y/y", "share_change", pct_i)]
                rows = [[Paragraph(c, cell_w if i == 0 else cell_wr) for i, c in
                         enumerate([f"Liquidity and funding ({currency} mn)"] + [l_ for l_, _ in liq["columns"]])]]
                for lab, key, f_ in spec:
                    rows.append([Paragraph(lab, cell)] + [Paragraph(f_(d_[key]), cell_r) for _, d_ in liq["columns"]])
                k = len(liq["columns"])
                tb = Table(rows, colWidths=[usable * 0.40] + [usable * 0.30] * k, hAlign="LEFT")
                tb.setStyle(TableStyle(line.getCommands() + [("LINEABOVE", (0, 3), (-1, 3), 0.8, NAVY)]))
                note = ("Yahoo Finance [2], own calculations. Runway = cash and short-term investments / negative free "
                        "cash flow; 'self-funded' if free cash flow is positive.")
                if k > 1:
                    note += (f" Latest quarter: retrieved {date.today().isoformat()}, i.e. after the 10-K; "
                             "free cash flow is the trailing twelve months.")
                content += [KeepTogether([Spacer(1, 4), exhibit(next_ex(), "Liquidity and funding"), tb, source(note)])]
            try:
                img_rm = _revenue_margin_chart(metrics, con, os.path.splitext(pdf_path)[0] + "_revenue_margin.png",
                                               REPORT_COLOR)
            except Exception as e_:
                img_rm = None
                print(f"Umsatz-Margen-Chart nicht erstellt: {e_}")
            if img_rm:
                content += [KeepTogether([Spacer(1, 4), exhibit(next_ex(), "Revenue and EBITDA margin"),
                                          _scaled_image(img_rm, usable, 6.0 * cm),
                                          source(f"Yahoo Finance [2]; E = analyst consensus (mean) [3], retrieved "
                                                 f"{date.today().isoformat()}. Revenue in {currency}.")])]
            try:
                mo = estimate_momentum(ticker_symbol)
            except Exception:
                mo = {"error": "n/a", "trend": [], "surprises": []}
            if mo["trend"] or mo["surprises"]:
                try:
                    img_p = _momentum_chart(mo, os.path.splitext(pdf_path)[0] + "_earnings_momentum.png", REPORT_COLOR)
                    chart = _scaled_image(img_p, usable, 6.5 * cm)
                except Exception:
                    chart = None
                note = (f"Yahoo Finance [3], retrieved {date.today().isoformat()}, i.e. after the 10-K. Left: mean EPS "
                        "estimate for the current and next fiscal year over the last 90 days; in brackets the number of "
                        "analysts raising/cutting in the last 30 days. Right: reported EPS vs consensus, with surprise in %.")
                if chart is not None:
                    content += [KeepTogether([Spacer(1, 4), exhibit(next_ex(), "Earnings momentum: estimate revisions and surprises"),
                                              chart, source(note)])]
        if sec_title == "Risk Assessment":
            lev = _leverage_table(ticker_symbol, int(own_fy) if own_fy.isdigit() else None)
            if lev:
                xf = lambda v: "n/a" if v is None else (f"{v:.1f}x" if v >= 0 else "net cash")
                spec_l = [("Net debt / EBITDA", "nd_ebitda", xf),
                          ("Interest coverage (EBIT / interest)", "coverage", lambda v: "n/a" if v is None else f"{v:.0f}x"),
                          ("Current ratio", "current", lambda v: "n/a" if v is None else f"{v:.1f}"),
                          ("Equity ratio (equity / total assets)", "equity_ratio",
                           lambda v: "n/a" if v is None else f"<i>{v * 100:.0f}%</i>")]
                rows = [[Paragraph(c_, cell_w if i == 0 else cell_wr) for i, c_ in
                         enumerate(["Leverage and coverage"] + [f"FY{y_}" for y_, _ in lev])]]
                for lab_, key_, f_ in spec_l:
                    rows.append([Paragraph(lab_, cell)] + [Paragraph(f_(d_[key_]), cell_r) for _, d_ in lev])
                tb = Table(rows, colWidths=[usable * 0.40] + [usable * 0.15] * len(lev), hAlign="LEFT")
                tb.setStyle(TableStyle(line.getCommands()))
                content += [KeepTogether([Spacer(1, 4), exhibit(next_ex(), "Balance sheet: leverage and coverage"), tb,
                                          source("Yahoo Finance [2], own calculations. Net debt = total debt - cash and "
                                                 "short-term investments; 'net cash' if negative. n/a: item not reported.")])]
            try:
                q = quality_scores(ticker_symbol, fy=int(own_fy)) if own_fy.isdigit() else {"error": "n/a"}
            except Exception:
                q = {"error": "n/a"}
            if not q.get("error"):
                half = usable * 0.55
                pi = q["piotroski"]
                r_ = [[Paragraph(f"Piotroski F-Score: FY{q['fy']} vs FY{q['fy'] - 1}", cell_w), Paragraph("Result", cell_wr)]]
                res_style = []
                for i, cr_ in enumerate(pi["criteria"], start=1):
                    txt = ("n/a" if cr_["pass"] is None else
                           (f'<font color="{REPORT_COLOR}"><b>Pass</b></font>' if cr_["pass"] else
                            '<font color="#9B2226"><b>Fail</b></font>'))
                    r_.append([Paragraph(cr_["criterion"], cell), Paragraph(txt, cell_r)])
                    if cr_["pass"] is not None:
                        res_style.append(("TEXTCOLOR", (1, i), (1, i), NAVY if cr_["pass"] else colors.HexColor("#9B2226")))
                r_.append([Paragraph("<b>Score</b>", cell), Paragraph(f"<b>{pi['score']} / {pi['available']}</b>", cell_r)])
                tp = Table(r_, colWidths=[half * 0.78, half * 0.22])
                tp.setStyle(TableStyle(line.getCommands() + [("BACKGROUND", (0, len(r_) - 1), (-1, len(r_) - 1), PANEL)]))
                w2 = usable * 0.41
                r2 = [[Paragraph("Score", cell_w), Paragraph("Value", cell_wr), Paragraph("Reading", cell_w)]]
                if q["altman"]:
                    r2.append([Paragraph("Altman Z", cell), Paragraph(f"{q['altman']['z']:.2f}", cell_r),
                               Paragraph(f"{q['altman']['zone']} zone (&gt;2.99 safe, &lt;1.81 distress)", cell)])
                if q["beneish"]:
                    r2.append([Paragraph("Beneish M", cell), Paragraph(f"{q['beneish']['m']:.2f}", cell_r),
                               Paragraph("warning sign (&gt; -1.78)" if q["beneish"]["flag"] else "no warning sign (&lt; -1.78)", cell)])
                blocks = [tp]
                if len(r2) > 1:
                    t2_ = Table(r2, colWidths=[w2 * 0.27, w2 * 0.2, w2 * 0.53])
                    t2_.setStyle(TableStyle(line.getCommands()))
                    blocks.append(t2_)
                row_ = Table([[blocks[0], "", blocks[1] if len(blocks) > 1 else ""]], colWidths=[half, usable * 0.04, w2])
                row_.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                          ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                note = ("Own calculation from Yahoo Finance statements [2]. Piotroski: one point per criterion met. "
                        "Altman Z (original formula) uses the current market capitalisation and is designed for "
                        "manufacturers; less reliable for young growth companies. Beneish M: statistical screen for "
                        "earnings manipulation, not proof.")
                content += [KeepTogether([Spacer(1, 4), exhibit(next_ex(), "Financial quality scores"), row_, source(note)])]
        if sec_title == "Competitors Analysis" and peer_metrics:
            def _cur(t_):
                try:
                    import yfinance as yf
                    return (yf.Ticker(t_).info or {}).get("financialCurrency") or "USD"
                except Exception:
                    return "USD"
            curs = {t_: _cur(t_) for t_ in [ticker_symbol] + list(peer_metrics)}
            mixed = len(set(curs.values())) > 1          # z. B. ASML (EUR) gegen US-Peers (USD)
            cols = ["Company", "FY", "Sales (mn)" if mixed else f"Sales ({currency} mn)", "Growth", "Gross margin",
                    "EBITDA margin", "FCF margin", "EV/ Sales", "Fwd EV/ Sales", "P/B"]
            hdr_s = ParagraphStyle("PeerHdrV5", parent=cell_wr, fontSize=7.2, leading=8.6)
            rows = [[Paragraph(c, cell_w if i == 0 else hdr_s) for i, c in enumerate(cols)]]

            def _fwd(t_):
                try:
                    ys = get_consensus(t_)["years"]
                    return "n/a" if not ys or ys[0]["ev_sales"] is None else round(ys[0]["ev_sales"], 2)
                except Exception:
                    return "n/a"
            for t_, m_ in [(ticker_symbol, metrics)] + list(peer_metrics.items()):
                vals = [f"{names.get(t_, t_)} ({t_})" + (f" · {curs.get(t_)}" if mixed else ""),
                        str(sorted(m_.columns)[-1]), _latest(m_, "Revenue"),
                        _latest(m_, "Revenue Growth"), _latest(m_, "Gross Margin"), _latest(m_, "EBITDA Margin"),
                        _fcf_margin(m_), _latest(m_, "EV/Sales"), _fwd(t_), _latest(m_, "PB Ratio")]
                bold = t_ == ticker_symbol
                rows.append([Paragraph((f"<b>{v}</b>" if bold else str(v)) if i == 0 else
                                       (f"<i>{v}</i>" if str(v).endswith("%") else str(v)), cell if i == 0 else cell_r)
                             for i, v in enumerate(vals)])
            w0 = usable * 0.26
            w0, w_fy = usable * 0.25, usable * 0.06
            tb = Table(rows, colWidths=[w0, w_fy] + [(usable - w0 - w_fy) / 8] * 8)
            tb.setStyle(TableStyle(line.getCommands() + [("BACKGROUND", (0, 1), (-1, 1), PANEL)]))
            note = ("Yahoo Finance [2][4], own calculations. Fiscal year ends can differ between companies. "
                    "Fwd EV/Sales: current enterprise value / consensus revenue for the current fiscal year [3].")
            if mixed:
                note += (" Sales in each company's reporting currency (shown after the name); ratios are currency-neutral "
                         "(market values converted into the reporting currency).")
            if peer_errors:
                note += " Not available: " + "; ".join(peer_errors)
            content += [KeepTogether([Spacer(1, 4), exhibit(next_ex(), "Peer comparison, latest fiscal year"), tb, source(note)])]
            hist_rows = [[Paragraph(c_, cell_w if i == 0 else cell_wr) for i, c_ in
                          enumerate(["EV/EBITDA", "FY t", "t-3", "t-2", "t-1", "t", "EBITDA margin t", "ROIC t"])]]
            for t_, m_ in [(ticker_symbol, metrics)] + list(peer_metrics.items()):
                cs = sorted(m_.columns)[-4:]
                evs = [m_.at["EV/EBITDA", c_] if "EV/EBITDA" in m_.index else "n/a" for c_ in cs]
                evs = ["n/a"] * (4 - len(evs)) + [f"{_num_cell(v):.1f}x" if _num_cell(v) is not None else str(v) for v in evs]
                vals = [f"{names.get(t_, t_)} ({t_})", str(cs[-1]) if cs else "n/a"] + evs + [
                    _latest(m_, "EBITDA Margin"), _latest(m_, "ROIC")]
                bold = t_ == ticker_symbol
                hist_rows.append([Paragraph((f"<b>{v}</b>" if bold else str(v)) if i == 0 else
                                            (f"<i>{v}</i>" if str(v).endswith("%") else str(v)), cell if i == 0 else cell_r)
                                  for i, v in enumerate(vals)])
            w0h, wfy = usable * 0.28, usable * 0.08
            th_ = Table(hist_rows, colWidths=[w0h, wfy] + [(usable - w0h - wfy) / 6] * 6)
            th_.setStyle(TableStyle(line.getCommands() + [("BACKGROUND", (0, 1), (-1, 1), PANEL),
                                                          ("LINEBEFORE", (2, 0), (2, -1), 0.6, NAVY)]))
            content += [KeepTogether([Spacer(1, 4), exhibit(next_ex(), "Peer multiples over the last four fiscal years"),
                                      th_, source("Yahoo Finance [2][4], own calculations. t = latest fiscal year of each "
                                                  "company (column FY t); EV at the fiscal year end. Shows whether a "
                                                  "valuation premium is new or persistent.")])]
        if sec_title == "Competitors Analysis":
            try:
                rd = reverse_dcf(ticker_symbol, fy=int(own_fy)) if own_fy.isdigit() else {"error": "no fiscal year"}
            except Exception as e:
                rd = {"error": str(e)}
            if not rd.get("error"):
                p_ = lambda v: fmt_pct(v, sign=False)
                inputs = [
                    (f"Enterprise value, current ({currency} mn)", fmt_mn(rd["ev"], 0)),
                    (f"Revenue FY{rd['fy']} ({currency} mn)", fmt_mn(rd["rev0"])),
                    (f"FCF margin FY{rd['fy']}", p_(rd["m0"])),
                    (f"FCF margin in year {rd['years']} (assumed)", p_(rd["m_target"])),
                    ("WACC", f"{p_(rd['wacc'])}"),
                    ("&nbsp;&nbsp;risk-free rate / beta / ERP", f"{p_(rd['rf'])} / {rd['beta']:.2f} / 5.0%"),
                    ("Terminal growth", p_(rd["tg"])),
                    (f"<b>Implied revenue CAGR, {rd['years']} years</b>", f"<b>{fmt_g(rd['implied_g'])}</b>"),
                    (f"Implied revenue FY{rd['fy'] + rd['years']} ({currency} mn)",
                     fmt_mn(rd["rev_end"], 0) if rd["rev_end"] else "n/a"),
                    ("Historical revenue CAGR, 3 years", fmt_g(rd["hist_cagr3"])),
                ]
                try:
                    ir = implied_irr(ticker_symbol, fy=int(own_fy))
                except Exception:
                    ir = {"error": "n/a"}
                irr_row = None
                if not ir.get("error"):
                    irr_row = len(inputs) + 1
                    inputs.append(("<b>Implied return (IRR), consensus path</b>", f"<b>{fmt_g(ir['irr'])}</b>"))
                    if ir["spread"] is not None:
                        inputs.append(("&nbsp;&nbsp;vs WACC", f"{ir['spread'] * 100:+.1f} pp"))
                for y_ in con["years"]:
                    inputs.append((f"Consensus revenue growth FY{y_['fy']}E", fmt_g(y_["growth"])))
                left_w2 = usable * 0.50
                t1 = Table([[Paragraph(f"Inputs and result", cell_w), ""]] +
                           [[Paragraph(a_, cell), Paragraph(b_, cell_r)] for a_, b_ in inputs],
                           colWidths=[left_w2 * 0.66, left_w2 * 0.34])
                t1.setStyle(TableStyle(line.getCommands() + [("SPAN", (0, 0), (-1, 0)),
                                                             ("BACKGROUND", (0, 8), (-1, 8), PANEL)]
                                       + ([("BACKGROUND", (0, irr_row), (-1, irr_row), PANEL)] if irr_row else [])))
                right_w2 = usable * 0.46
                hdr = [Paragraph("FCF margin \\ WACC", cell_w)] + [Paragraph(p_(w_), cell_wr) for w_ in rd["grid_waccs"]]
                g_rows = [hdr]
                base_r = next(i_ for i_, m_ in enumerate(rd["grid_margins"]) if abs(m_ - rd["m_target"]) < 1e-9)
                for m_, row_ in zip(rd["grid_margins"], rd["grid"]):
                    g_rows.append([Paragraph(p_(m_), cell)] + [Paragraph(f"<i>{fmt_g(v_)}</i>", cell_r) for v_ in row_])
                t2 = Table(g_rows, colWidths=[right_w2 * 0.25] + [right_w2 * 0.15] * 5)
                t2.setStyle(TableStyle(line.getCommands() + [
                    ("BACKGROUND", (3, base_r + 1), (3, base_r + 1), PANEL),
                    ("BOX", (3, base_r + 1), (3, base_r + 1), 0.8, NAVY)]))
                cap = ParagraphStyle("CapV5", parent=cell, fontName="Helvetica-Bold", textColor=NAVY, spaceAfter=3)
                both = Table([[t1, "", [Paragraph(f"Implied {rd['years']}-year revenue CAGR: sensitivity", cap), t2]]],
                             colWidths=[left_w2, usable * 0.04, right_w2])
                both.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                          ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                          ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                note = (f"Own calculation from Yahoo Finance data [2][3]. Solves for the constant revenue growth over "
                        f"{rd['years']} years at which the present value of free cash flow equals the current enterprise value. "
                        f"The FCF margin moves linearly from FY{rd['fy']} to the assumed margin; WACC = 10-year US Treasury "
                        f"yield + beta x 5.0% equity risk premium (simplified, equity only). Highlighted: base case. "
                        f"IRR: discount rate at which consensus revenue for two years, growth fading linearly to 2.5% by "
                        f"year {rd['years']} and the same margin path equal the current enterprise value. "
                        f"Illustrative model, not a price target.")
                content += [KeepTogether([Spacer(1, 6), exhibit(next_ex(), "Reverse DCF: growth implied by the current valuation"),
                                          both, source(note)])]

    # --- Quellenverzeichnis ---------------------------------------------------
    today = date.today().isoformat()
    tenk = _tenk_reference(ticker_symbol, filing_date)
    form_ = (tenk or {}).get("form", "10-K")
    how_ = ("Items 4, 3D and 5 parsed from the EDGAR document" if form_.startswith(("20-F", "40-F"))
            else _tenk_method(ticker_symbol, tenk))
    if tenk:
        u_ = str(tenk.get("url") or "")
        from xml.sax.saxutils import escape as _xe
        link_ = f"<link href='{_xe(u_)}' color='#185FA5'><u>{_xe(u_)}</u></link>" if u_.startswith("https://") else _xe(u_)
        r1 = (f"{name}, Form {form_} for the fiscal year ended {tenk.get('report_date', 'n/a')}, filed {tenk.get('filing_date')}, "
              f"SEC EDGAR, {link_} ({how_}).")
    else:
        r1 = f"{name}, Form {form_} filed {filing_date}, SEC EDGAR ({how_})."
    refs = [
        r1,
        f"Yahoo Finance: annual and quarterly financial statements and daily share prices for {ticker_symbol}, retrieved {today} via yfinance.",
        f"Yahoo Finance: analyst recommendations, price targets and consensus estimates (revenue, EPS) for {ticker_symbol} and its peers, retrieved {today} (current consensus, not as of the filing date).",
        f"Yahoo Finance: annual financial statements of the peer companies named in the Competitors Analysis, retrieved {today}.",
    ]
    content += [CondPageBreak(6 * cm)] + heading("Sources")
    content += [Paragraph(f"[{i}]&nbsp;&nbsp;{r}", ref) for i, r in enumerate(refs, 1)]
    content.append(Paragraph("Report generated with an agent workflow built on the open-source FinRobot framework "
                             "(AI4Finance Foundation, Apache 2.0) with own extensions.", src_style))

    # --- Anhang: automatischer Faktencheck -----------------------------------
    from .fact_check import run_fact_check, save_json
    fc_sections = ([("Key Takeaways", " ".join(takeaways))] if takeaways else []) + [("Investment Summary", summary)] + list(sections)
    if theses:
        fc_sections.append(("Investment Thesis", " ".join(f"{t_['thesis']} {t_['evidence']} {t_['signpost']} {t_['invalidation']}"
                                                          for t_ in theses)))
    if segments:
        fc_sections.append(("Segment table", "; ".join(
            f"{sg['segment']}: ${sg['current']} million" + (f", prior ${sg['prior']} million" if sg["prior"] else "")
            for sg in segments)))
    srcs, n_tenk = _collect_sources(ticker_symbol, filing_date, metrics, key_data, peer_metrics)
    try:
        from .fact_check import SourceIndex
        s3 = SourceIndex("[2][3] Liquidity and consensus")
        s3.add_text(outlook_text(ticker_symbol, own_fy))
        for v_ in tbl.values.flatten():
            s3.add_value(v_)
        srcs.insert(2, s3)
    except Exception:
        pass
    fc = run_fact_check(fc_sections, srcs, names)
    fc["peer_tickers"] = list(peer_metrics)
    base_ = os.path.splitext(pdf_path)[0]
    key_ = os.path.abspath(pdf_path)
    _BUILD_ROUNDS[key_] = _BUILD_ROUNDS.get(key_, 0) + 1
    build_round = _BUILD_ROUNDS[key_]
    fc["build_round"] = build_round
    fc["self_correct"] = SELF_CORRECT()
    if build_round == 1:
        save_json(fc, base_ + "_factcheck_round1.json")
    elif os.path.exists(base_ + "_factcheck_round1.json"):
        import json as _json
        r1 = _json.load(open(base_ + "_factcheck_round1.json", encoding="utf-8"))
        fc["round1"] = {k_: r1.get(k_) for k_ in ("total_claims", "matched", "match_rate")}
        fc["round1"]["name_issues"] = len(r1.get("name_issues", []))
    save_json(fc, base_ + "_factcheck.json")
    content += _factcheck_flowables(fc, n_tenk, (h2, body, small, cell, cell_r, line), usable, heading)

    gen_date = date.today().strftime("%d %B %Y")

    def _footer(canv, d):
        canv.setStrokeColor(RULE); canv.setLineWidth(0.5)
        canv.line(m, 1.25 * cm, page_w - m, 1.25 * cm)
        canv.setFont("Helvetica", 7); canv.setFillColor(GREY)
        canv.drawString(m, 0.85 * cm, f"Generated by {REPORT_BRAND} - for academic purposes only, not investment advice")
        canv.drawRightString(page_w - m, 0.85 * cm, f"Page {d.page}")

    def _first(canv, d):
        canv.saveState()
        canv.setFillColor(NAVY); canv.rect(0, page_h - 1.15 * cm, page_w, 1.15 * cm, stroke=0, fill=1)
        canv.setFillColor(colors.white); canv.setFont("Helvetica-Bold", 9)
        canv.drawString(m, page_h - 0.72 * cm, "EQUITY RESEARCH")
        canv.setFont("Helvetica", 9)
        canv.drawString(m + 3.3 * cm, page_h - 0.72 * cm, f"|   {sector}")
        canv.drawRightString(page_w - m, page_h - 0.72 * cm, gen_date)
        _footer(canv, d)
        canv.restoreState()

    def _later(canv, d):
        canv.saveState()
        canv.setFillColor(NAVY); canv.setFont("Helvetica-Bold", 8)
        canv.drawString(m, page_h - 1.0 * cm, f"{name} ({ticker_symbol})")
        canv.setFont("Helvetica", 8); canv.setFillColor(GREY)
        canv.drawRightString(page_w - m, page_h - 1.0 * cm, f"Equity Research  |  {gen_date}")
        canv.setStrokeColor(NAVY); canv.setLineWidth(1)
        canv.line(m, page_h - 1.15 * cm, page_w - m, page_h - 1.15 * cm)
        _footer(canv, d)
        canv.restoreState()

    doc.build(content, onFirstPage=_first, onLaterPages=_later)
    msg = (f"Annual report generated successfully. Fact check: {fc['matched']} of {fc['total_claims']} figures found "
           f"in the sources, {len(fc['name_issues'])} name/ticker mismatch(es). Details in the appendix of the PDF.")
    if fc.get("round1"):
        r1 = fc["round1"]
        msg += f" Revision round completed (before revision: {r1['matched']} of {r1['total_claims']} figures found)."
    if build_round == 1 and SELF_CORRECT() and (fc["unmatched"] or fc["name_issues"]):
        items = [f"- [{u_['section']}] {u_['text']}: \"{' '.join(str(u_.get('context', '')).split()).strip('. ')[:170]}\""
                 for u_ in fc["unmatched"][:25]]
        items += [f"- [{n_['section']}] name '{n_['written']}' for ticker {n_['ticker']}; official name: {n_['official']}"
                  for n_ in fc["name_issues"][:10]]
        msg += ("\n\nSELF-CHECK (one revision round): the automated fact check could not find these figures or names "
                "in the source data:\n" + "\n".join(items) +
                "\n\nFor each item: correct it to the value in your sources (10-K analysis results and tool outputs), "
                "remove it, or keep it only if it is a correct calculation from source figures (e.g. a growth rate or "
                "difference). Never invent replacements. Then call build_annual_report exactly once more with the "
                "revised texts and otherwise the same arguments. After that, reply TERMINATE.")
    return msg


class ReportLabUtils:

    def build_annual_report(
        ticker_symbol: Annotated[str, "ticker symbol"],
        save_path: Annotated[str, "path to save the annual report pdf"],
        operating_results: Annotated[
            str,
            "a paragraph of text: the company's income summarization from its financial report" + CITATION_GUIDE,
        ],
        market_position: Annotated[
            str,
            "a paragraph of text: the company's current situation and end market (geography), major customers (blue chip or not), market share from its financial report, avoid similar sentences also generated in the business overview section, classify it into either of the two" + CITATION_GUIDE,
        ],
        business_overview: Annotated[
            str,
            "a paragraph of text: the company's description and business highlights from its financial report" + CITATION_GUIDE,
        ],
        risk_assessment: Annotated[
            str,
            "a paragraph of text: the company's risk assessment from its financial report" + CITATION_GUIDE,
        ],
        competitors_analysis: Annotated[
            str,
            "a paragraph of text: the company's competitors analysis from its financial report and competitors' financial report" + CITATION_GUIDE,
        ],
        share_performance_image_path: Annotated[
            str, "path to the share performance image"
        ],
        pe_eps_performance_image_path: Annotated[
            str, "path to the valuation chart image (from get_pe_eps_performance)"
        ],
        filing_date: Annotated[str, "filing date of the analyzed financial report"],
        investment_summary: Annotated[
            str,
            "the investment summary for page 1: 150-300 words with the key conclusions (business momentum, financial trajectory, valuation, main risks)" + CITATION_GUIDE,
        ],
        peer_tickers: Annotated[
            List[str], "ticker symbols of the peer companies used in the competitors analysis, e.g. ['LUNR', 'RDW', 'PL']"
        ] = None,
        segment_data: Annotated[
            str,
            'optional JSON list with segment revenue from the 10-K in USD millions, e.g. '
            '[{"segment": "Space Systems", "prior_revenue": 310.9, "current_revenue": 402.8}]. Use only figures stated in the 10-K.',
        ] = "",
        key_takeaways: Annotated[
            List[str],
            "3-4 short bullet points (max. 25 words each) for the 'Key takeaways' box on page 1: the most important "
            "conclusions (e.g. growth, profitability/funding, valuation vs consensus, key risk), each with a citation [1]-[4]",
        ] = None,
        investment_theses: Annotated[
            List[dict],
            "3-4 investment theses, each {'thesis': the view in one sentence (a claim that can turn out wrong), "
            "'evidence': why, with figures and a citation, 'signpost': the measurable KPI or event (with timing) that will "
            "confirm it, 'invalidation': what would prove it wrong}. Shown as a table and checked by the earnings reviewer.",
        ] = None,
    ) -> str:
        """
        Aggregate a company's business_overview, market_position, operating_results,
        risk assessment, competitors analysis and share performance, PE & EPS performance charts all into a PDF report.
        Also requires an investment_summary (150-300 words) for page 1. All text arguments must be final prose
        (not file paths) and should cite sources as [1]-[4]; the source list is added automatically.
        """
        # Angepasst: Plausibilitaetspruefung der Textabschnitte. Kleinere Modelle uebergeben hier
        # oft Dateipfade oder Platzhalter statt fertigem Text; das Original hat diese dann
        # woertlich ins PDF geschrieben. Jetzt wird das abgelehnt und dem Agenten erklaert.
        sections = {
            "operating_results": operating_results,
            "market_position": market_position,
            "business_overview": business_overview,
            "risk_assessment": risk_assessment,
            "competitors_analysis": competitors_analysis,
            "investment_summary": investment_summary,
        }
        problems = []
        for name, text in sections.items():
            t = (text or "").strip()
            if t.endswith(".txt") or t.startswith(("../", "./", "/")) or os.path.isfile(t):
                problems.append(f"{name}: ist ein Dateipfad ('{t[:80]}'), kein Text")
            elif len(t.split()) < 40:
                problems.append(f"{name}: nur {len(t.split())} Woerter ('{t[:80]}')")
        try:
            segments = _parse_segments(segment_data)
        except Exception as e:
            problems.append(f"segment_data: kein gueltiges JSON im erwarteten Format ({e})")
            segments = []
        takeaways = []
        if key_takeaways:
            if isinstance(key_takeaways, str):
                key_takeaways = [l_ for l_ in key_takeaways.splitlines() if l_.strip()]
            takeaways = [str(t_).strip().lstrip("-*\u2022 ").strip() for t_ in key_takeaways if str(t_).strip()]
            if not 3 <= len(takeaways) <= 5:
                problems.append(f"key_takeaways: {len(takeaways)} Punkte, erwartet 3-4")
            for t_ in takeaways:
                if len(t_.split()) > 40:
                    problems.append(f"key_takeaways: Punkt mit {len(t_.split())} Woertern, maximal 25 ('{t_[:60]}')")
        theses = []
        if investment_theses:
            if isinstance(investment_theses, str):
                try:
                    import json as _j
                    investment_theses = _j.loads(investment_theses)
                except Exception:
                    problems.append("investment_theses must be a list of objects")
                    investment_theses = []
            for x_ in investment_theses or []:
                th_ = {k_: str((x_ or {}).get(k_, "")).strip() for k_ in ("thesis", "evidence", "signpost", "invalidation")}
                missing = [k_ for k_, v_ in th_.items() if not v_]
                if missing:
                    problems.append(f"investment_theses: missing {', '.join(missing)} in '{th_['thesis'][:50]}'")
                if any(len(v_.split()) > 60 for v_ in th_.values()):
                    problems.append(f"investment_theses: field longer than 60 words in '{th_['thesis'][:50]}'")
                theses.append(th_)
            if not 2 <= len(theses) <= 5:
                problems.append(f"investment_theses: {len(theses)} entries, expected 3-4")
        if takeaways and len((investment_summary or "").split()) > 200:
            problems.append(f"investment_summary: {len(investment_summary.split())} Woerter, mit Key Takeaways maximal 180 "
                            "(passt sonst nicht auf Seite 1)")
        if len((investment_summary or "").split()) > 320:
            problems.append(f"investment_summary: {len(investment_summary.split())} Woerter, maximal 320 (passt sonst nicht auf Seite 1)")
        if problems:
            return (
                "PDF NOT generated. Each text argument must contain the final written paragraph "
                "(roughly 60-120 words), not a file path or placeholder. Problems: "
                + "; ".join(problems)
                + ". Write the paragraphs from the analyses you received, then call build_annual_report again."
            )

        # Angepasst: neues Layout (siehe _build_report_v2). Das Original folgt unveraendert darunter.
        try:
            pdf_path = (os.path.join(save_path, f"{ticker_symbol}_Equity_Research_report.pdf")
                        if os.path.isdir(save_path) else save_path)
            os.makedirs(os.path.dirname(pdf_path) or ".", exist_ok=True)
            # Argumente sichern: Grundlage fuer Neubau ohne LLM und fuer den Earnings/Thesis Reviewer
            try:
                import json as _json
                _json.dump({"ticker_symbol": ticker_symbol, "save_path": save_path, "filing_date": filing_date,
                            "investment_summary": investment_summary, "key_takeaways": takeaways,
                            "business_overview": business_overview, "market_position": market_position,
                            "operating_results": operating_results, "risk_assessment": risk_assessment,
                            "competitors_analysis": competitors_analysis, "peer_tickers": peer_tickers,
                            "segment_data": segment_data, "investment_theses": theses,
                            "share_performance_image_path": share_performance_image_path,
                            "pe_eps_performance_image_path": pe_eps_performance_image_path},
                           open(os.path.splitext(pdf_path)[0] + "_build_args.json", "w", encoding="utf-8"),
                           indent=2, ensure_ascii=False)
            except Exception:
                pass
            return _build_report_v4(
                ticker_symbol, pdf_path, investment_summary,
                [("Business Overview", business_overview), ("Market Position", market_position),
                 ("Operating Results", operating_results), ("Risk Assessment", risk_assessment),
                 ("Competitors Analysis", competitors_analysis)],
                share_performance_image_path, pe_eps_performance_image_path, filing_date,
                peer_tickers=peer_tickers, segments=segments, takeaways=takeaways or None,
                theses=theses or None,
            )
        except Exception:
            return traceback.format_exc()

        try:
            # 2. 创建PDF并插入图像
            # 页面设置
            page_width, page_height = pagesizes.A4
            left_column_width = page_width * 2 / 3
            right_column_width = page_width - left_column_width
            margin = 4

            # 创建PDF文档路径
            pdf_path = (
                os.path.join(save_path, f"{ticker_symbol}_Equity_Research_report.pdf")
                if os.path.isdir(save_path)
                else save_path
            )
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            doc = SimpleDocTemplate(pdf_path, pagesize=pagesizes.A4)
        


            # 定义两个栏位的Frame
            frame_left = Frame(
                margin,
                margin,
                left_column_width - margin * 2,
                page_height - margin * 2,
                id="left",
            )
            frame_right = Frame(
                left_column_width,
                margin,
                right_column_width - margin * 2,
                page_height - margin * 2,
                id="right",
            )

            single_frame = Frame(margin, margin, page_width-margin*2, page_height-margin*2, id='single')
            single_column_layout = PageTemplate(id='OneCol', frames=[single_frame])

            left_column_width_p2 = (page_width - margin * 3) // 2
            right_column_width_p2 = left_column_width_p2
            frame_left_p2 = Frame(
                margin,
                margin,
                left_column_width_p2 - margin * 2,
                page_height - margin * 2,
                id="left",
            )
            frame_right_p2 = Frame(
                left_column_width_p2,
                margin,
                right_column_width_p2 - margin * 2,
                page_height - margin * 2,
                id="right",
            )

            #创建PageTemplate，并添加到文档
            page_template = PageTemplate(
                id="TwoColumns", frames=[frame_left, frame_right]
            )
            page_template_p2 = PageTemplate(
                id="TwoColumns_p2", frames=[frame_left_p2, frame_right_p2]
            )

             #Define single column Frame
            single_frame = Frame(
                margin,
                margin,
                page_width - 2 * margin,
                page_height - 2 * margin,
                id="single",
            )

            # Create a PageTemplate with a single column
            single_column_layout = PageTemplate(id="OneCol", frames=[single_frame])

            doc.addPageTemplates([page_template, single_column_layout, page_template_p2])

            styles = getSampleStyleSheet()

            # 自定义样式
            custom_style = ParagraphStyle(
                name="Custom",
                parent=styles["Normal"],
                fontName="Helvetica",
                fontSize=10,
                # leading=15,
                alignment=TA_JUSTIFY,
            )

            title_style = ParagraphStyle(
                name="TitleCustom",
                parent=styles["Title"],
                fontName="Helvetica-Bold",
                fontSize=16,
                leading=20,
                alignment=TA_LEFT,
                spaceAfter=10,
            )

            subtitle_style = ParagraphStyle(
                name="Subtitle",
                parent=styles["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=14,
                leading=12,
                alignment=TA_LEFT,
                spaceAfter=6,
            )

            table_style2 = TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.white),
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 7),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 14),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    # 所有单元格左对齐
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    # 标题栏下方添加横线
                    ("LINEBELOW", (0, 0), (-1, 0), 2, colors.black),
                    # 表格最下方添加横线
                    ("LINEBELOW", (0, -1), (-1, -1), 2, colors.black),
                ]
            )

            name = YFinanceUtils.get_stock_info(ticker_symbol)["shortName"]

            # 准备左栏和右栏内容
            content = []
            # 标题
            content.append(
                Paragraph(
                    f"Equity Research Report: {name}",
                    title_style,
                )
            )

            # 子标题
            content.append(Paragraph("Business Overview", subtitle_style))
            content.append(Paragraph(business_overview, custom_style))

            content.append(Paragraph("Market Position", subtitle_style))
            content.append(Paragraph(market_position, custom_style))
            
            content.append(Paragraph("Operating Results", subtitle_style))
            content.append(Paragraph(operating_results, custom_style))

            # content.append(Paragraph("Summarization", subtitle_style))
            df = FMPUtils.get_financial_metrics(ticker_symbol, years=5)
            df.reset_index(inplace=True)
            currency = YFinanceUtils.get_stock_info(ticker_symbol)["currency"]
            df.rename(columns={"index": f"FY ({currency} mn)"}, inplace=True)
            table_data = [["Financial Metrics"]]
            table_data += [df.columns.to_list()] + df.values.tolist()

            col_widths = [(left_column_width - margin * 4) / df.shape[1]] * df.shape[1]
            table = Table(table_data, colWidths=col_widths)
            table.setStyle(table_style2)
            content.append(table)

            content.append(FrameBreak())  # 用于从左栏跳到右栏

            table_style = TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.white),
                    ("FONT", (0, 0), (-1, -1), "Helvetica", 8),
                    ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 12),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    # 第一列左对齐
                    ("ALIGN", (0, 1), (0, -1), "LEFT"),
                    # 第二列右对齐
                    ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                    # 标题栏下方添加横线
                    ("LINEBELOW", (0, 0), (-1, 0), 2, colors.black),
                ]
            )
            full_length = right_column_width - 2 * margin

            data = [
                ["FinRobot"],
                ["https://ai4finance.org/"],
                ["https://github.com/AI4Finance-Foundation/FinRobot"],
                [f"Report date: {filing_date}"],
            ]
            col_widths = [full_length]
            table = Table(data, colWidths=col_widths)
            table.setStyle(table_style)
            content.append(table)

            # content.append(Paragraph("", custom_style))
            content.append(Spacer(1, 0.15 * inch))
            key_data = ReportAnalysisUtils.get_key_data(ticker_symbol, filing_date)
            # 表格数据
            data = [["Key data", ""]]
            data += [[k, v] for k, v in key_data.items()]
            col_widths = [full_length // 3 * 2, full_length // 3]
            table = Table(data, colWidths=col_widths)
            table.setStyle(table_style)
            content.append(table)

            # 将Matplotlib图像添加到右栏

            # 历史股价
            data = [["Share Performance"]]
            col_widths = [full_length]
            table = Table(data, colWidths=col_widths)
            table.setStyle(table_style)
            content.append(table)

            plot_path = share_performance_image_path
            width = right_column_width
            height = width // 2
            content.append(Image(plot_path, width=width, height=height))

            # 历史PE和EPS
            data = [["PE & EPS"]]
            col_widths = [full_length]
            table = Table(data, colWidths=col_widths)
            table.setStyle(table_style)
            content.append(table)

            plot_path = pe_eps_performance_image_path
            width = right_column_width
            height = width // 2
            content.append(Image(plot_path, width=width, height=height))

            # # 开始新的一页
            content.append(NextPageTemplate("OneCol"))
            content.append(PageBreak())
            
            content.append(Paragraph("Risk Assessment", subtitle_style))
            content.append(Paragraph(risk_assessment, custom_style))

            content.append(Paragraph("Competitors Analysis", subtitle_style))
            content.append(Paragraph(competitors_analysis, custom_style))
            # def add_table(df, title):
            #     df = df.applymap(lambda x: "{:.2f}".format(x) if isinstance(x, float) else x)
            #     # df.columns = [col.strftime('%Y') for col in df.columns]
            #     # df.reset_index(inplace=True)
            #     # currency = ra.info['currency']
            #     df.rename(columns={"index": "segment"}, inplace=True)
            #     table_data = [[title]]
            #     table_data += [df.columns.to_list()] + df.values.tolist()

            #     table = Table(table_data)
            #     table.setStyle(table_style2)
            #     num_columns = len(df.columns)

            #     column_width = (page_width - 4 * margin) / (num_columns + 1)
            #     first_column_witdh = column_width * 2
            #     table._argW = [first_column_witdh] + [column_width] * (num_columns - 1)

            #     content.append(table)
            #     content.append(Spacer(1, 0.15 * inch))

            # if os.path.exists(f"{ra.project_dir}/outer_resource/"):
            #     Revenue10Q = pd.read_csv(
            #         f"{ra.project_dir}/outer_resource/Revenue10Q.csv",
            #     )
            #     # del Revenue10K['FY2018']
            #     # del Revenue10K['FY2019']
            #     add_table(Revenue10Q, "Revenue")

            #     Ratio10Q = pd.read_csv(
            #         f"{ra.project_dir}/outer_resource/Ratio10Q.csv",
            #     )
            #     # del Ratio10K['FY2018']
            #     # del Ratio10K['FY2019']
            #     add_table(Ratio10Q, "Ratio")

            #     Yoy10Q = pd.read_csv(
            #         f"{ra.project_dir}/outer_resource/Yoy10Q.csv",
            #     )
            #     # del Yoy10K['FY2018']
            #     # del Yoy10K['FY2019']
            #     add_table(Yoy10Q, "Yoy")

            #     plot_path = os.path.join(f"{ra.project_dir}/outer_resource/", "segment.png")
            #     width = page_width - 2 * margin
            #     height = width * 3 // 5
            #     content.append(Image(plot_path, width=width, height=height))

            # # 第二页及之后内容，使用单栏布局
            # df = ra.get_income_stmt()
            # df = df[df.columns[:3]]
            # def convert_if_money(value):
            #     if np.abs(value) >= 1000000:
            #         return value / 1000000
            #     else:
            #         return value

            # # 应用转换函数到DataFrame的每列
            # df = df.applymap(convert_if_money)

            # df.columns = [col.strftime('%Y') for col in df.columns]
            # df.reset_index(inplace=True)
            # currency = ra.info['currency']
            # df.rename(columns={'index': f'FY ({currency} mn)'}, inplace=True)  # 可选：重命名索引列为“序号”
            # table_data = [["Income Statement"]]
            # table_data += [df.columns.to_list()] + df.values.tolist()

            # table = Table(table_data)
            # table.setStyle(table_style2)
            # content.append(table)

            # content.append(FrameBreak())  # 用于从左栏跳到右栏

            # df = ra.get_cash_flow()
            # df = df[df.columns[:3]]

            # df = df.applymap(convert_if_money)

            # df.columns = [col.strftime('%Y') for col in df.columns]
            # df.reset_index(inplace=True)
            # currency = ra.info['currency']
            # df.rename(columns={'index': f'FY ({currency} mn)'}, inplace=True)  # 可选：重命名索引列为“序号”
            # table_data = [["Cash Flow Sheet"]]
            # table_data += [df.columns.to_list()] + df.values.tolist()

            # table = Table(table_data)
            # table.setStyle(table_style2)
            # content.append(table)
            # # content.append(Paragraph('This is a single column on the second page', custom_style))
            # # content.append(Spacer(1, 0.2*inch))
            # # content.append(Paragraph('More content in the single column.', custom_style))

            # 构建PDF文档
            doc.build(content)

            return "Annual report generated successfully."

        except Exception:
            return traceback.format_exc()
