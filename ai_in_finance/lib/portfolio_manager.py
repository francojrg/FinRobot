"""
Portfolio-Manager-Agent (eigene Erweiterung): Analyse, Optimierung und Backtest eines Portfolios als PDF-Report.

Arbeitsteilung wie bei den anderen Agenten: portfolio_engine.py rechnet alles (Risiko, Struktur, Stresstests,
Min-Variance / Max-Sharpe / HRP, Walk-forward-Backtest); der Agent interpretiert, hinterfragt die Modelle und
formuliert Empfehlungen. Nur fuer Lehrzwecke, keine Anlageberatung.
"""
import json
import math
import os
from datetime import date
from pathlib import Path
from textwrap import dedent
from typing import Annotated, List
from xml.sax.saxutils import escape

import autogen
import numpy as np
from finrobot.toolkits import register_toolkits

from . import performance as pf
from . import portfolio_engine as pe
from . import transactions as tr
from .style import STYLE_RULES
from . import agent_settings as _AS  # Prompts/Parameter aus der App (research/agent_settings.json)

_ROUNDS = {}


# --------------------------------------------------------------- Charts
def _charts(a, bt, base, color, perf=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from finrobot.functional.reportlab import _tint
    tint, grey = _tint(color, 0.55), "#9AA5B1"
    paths = {}

    def style(ax):
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.grid(axis="y", color="#E5E5E5", lw=0.6)
        ax.set_axisbelow(True)
        ax.tick_params(labelsize=7.5)

    # 1) Wertentwicklung vs. Benchmarks
    fig, ax = plt.subplots(figsize=(9, 3.2))
    pc = a["port_curve"]
    ax.plot(pc.index, pc / pc.iloc[0] * 100, color=color, lw=1.8, label="Portfolio (today's weights)")
    for (name, t), c in zip(pe.BENCHMARKS.items(), (grey, tint)):
        s = a["prices"][t].reindex(pc.index).dropna()
        if len(s) > 50:
            ax.plot(s.index, s / s.iloc[0] * 100, color=c, lw=1.2, label=f"{name} (EUR)")
    ax.legend(fontsize=7.5, frameon=False)
    ax.set_ylabel("Rebased to 100", fontsize=7.5)
    style(ax)
    fig.tight_layout()
    paths["perf"] = base + "_perf.png"
    fig.savefig(paths["perf"], dpi=200)
    plt.close(fig)

    # 2) Sektoren
    sec = a["structure"]["sector"]
    fig, ax = plt.subplots(figsize=(4.6, 2.9))
    ax.barh(list(sec)[::-1], [v * 100 for v in list(sec.values())[::-1]], color=color)
    for i, v in enumerate(list(sec.values())[::-1]):
        ax.text(v * 100 + 0.5, i, f"{v * 100:.0f}%", va="center", fontsize=7)
    ax.set_xlabel("% of portfolio", fontsize=7.5)
    style(ax)
    ax.grid(axis="x", color="#E5E5E5", lw=0.6)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    paths["sector"] = base + "_sectors.png"
    fig.savefig(paths["sector"], dpi=200)
    plt.close(fig)

    # 3) Gewicht vs. Risikobeitrag
    pos = sorted(a["positions"], key=lambda p: p["risk_contrib"])
    fig, ax = plt.subplots(figsize=(4.6, 3.6))
    y = np.arange(len(pos))
    ax.barh(y + 0.2, [p["weight"] * 100 for p in pos], 0.4, color=tint, label="Weight")
    ax.barh(y - 0.2, [p["risk_contrib"] * 100 for p in pos], 0.4, color=color, label="Share of risk")
    ax.set_yticks(y)
    ax.set_yticklabels([p["ticker"] for p in pos], fontsize=7)
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    ax.set_xlabel("%", fontsize=7.5)
    style(ax)
    ax.grid(axis="x", color="#E5E5E5", lw=0.6)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    paths["risk"] = base + "_risk.png"
    fig.savefig(paths["risk"], dpi=200)
    plt.close(fig)

    # 4) Korrelationen
    corr = a["corr"]
    fig, ax = plt.subplots(figsize=(4.6, 3.9))
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("c", ["#FFFFFF", tint, color])
    im = ax.imshow(corr.values, cmap=cmap, vmin=0, vmax=1)
    ax.set_xticks(range(len(corr)))
    ax.set_xticklabels(corr.columns, rotation=90, fontsize=6)
    ax.set_yticks(range(len(corr)))
    ax.set_yticklabels(corr.columns, fontsize=6)
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, f"{corr.values[i, j]:.1f}", ha="center", va="center", fontsize=5,
                    color="white" if corr.values[i, j] > 0.6 else "#333333")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02).ax.tick_params(labelsize=6)
    fig.tight_layout()
    paths["corr"] = base + "_corr.png"
    fig.savefig(paths["corr"], dpi=200)
    plt.close(fig)

    # 5) Effizienzlinie mit Portfolios
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    fr = sorted(a["frontier"])
    ax.plot([v * 100 for v, _ in fr], [r * 100 for _, r in fr], color=grey, lw=1.2, label="Efficient frontier (model)")
    marks = {"current": ("Current", color, "o"), "min_variance": ("Min variance", "#2D8A4E", "s"),
             "max_sharpe": ("Max Sharpe", "#B7791F", "^"), "hrp": ("HRP", "#6D1A36", "D"),
             "equal_weight": ("Equal weight", "#5A6472", "v")}
    for k, (lab, c, mk) in marks.items():
        st = a["opt_stats"][k]
        ax.scatter(st["vol"] * 100, st["exp_return"] * 100, color=c, marker=mk, s=40, label=lab, zorder=3)
    ax.set_xlabel("Volatility p.a. (%)", fontsize=7.5)
    ax.set_ylabel("Expected return p.a. (%)", fontsize=7.5)
    ax.legend(fontsize=6.5, frameon=False)
    style(ax)
    fig.tight_layout()
    paths["frontier"] = base + "_frontier.png"
    fig.savefig(paths["frontier"], dpi=200)
    plt.close(fig)

    # 6) Backtest
    if bt and bt.get("curves"):
        fig, ax = plt.subplots(figsize=(9, 3.2))
        cols = {"Current weights (rebalanced)": color, "Equal weight": "#5A6472", "Min variance": "#2D8A4E",
                "Max Sharpe": "#B7791F", "HRP": "#6D1A36", "MSCI ACWI (EUR)": grey}
        for k, cv in bt["curves"].items():
            ax.plot(cv.index, cv / cv.iloc[0] * 100, lw=1.6 if k.startswith("Current") else 1.1,
                    color=cols.get(k, "#333333"), ls="--" if k.startswith("MSCI") else "-", label=k)
        ax.legend(fontsize=7, frameon=False, ncol=3)
        ax.set_ylabel("Rebased to 100", fontsize=7.5)
        style(ax)
        fig.tight_layout()
        paths["backtest"] = base + "_backtest.png"
        fig.savefig(paths["backtest"], dpi=200)
        plt.close(fig)
    if perf:
        paths.update(_perf_charts(perf, base, color, tint, grey, style, plt))
    return paths


def _perf_charts(perf, base, color, tint, grey, style, plt):
    import matplotlib.ticker
    matplotlib = __import__("matplotlib")
    paths = {}
    # 7) Depotwert mit Kaeufen/Verkaeufen, eingezahltem Kapital und ACWI mit denselben Zahlungen
    v, inv, bv = perf["value"], perf["invested"], perf["bench_value"]
    v = v.loc[perf["start"]:]
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(v.index, v / 1000, color=color, lw=1.8, label="Portfolio value")
    ax.plot(v.index, bv.reindex(v.index) / 1000, color=grey, lw=1.2, label="MSCI ACWI with the same cash flows")
    ax.plot(v.index, inv.reindex(v.index) / 1000, color=tint, lw=1.1, ls="--", drawstyle="steps-post",
            label="Net invested capital")
    for kind, mk, col in (("buy", "^", "#2D8A4E"), ("sell", "v", "#C0392B")):
        pts = [(d, eur) for d, k, _, eur in perf["trades"] if k == kind and d in v.index]
        if pts:
            sizes = np.clip(np.array([e for _, e in pts]) / max(e for _, e in pts) * 90, 18, 90)
            ax.scatter([d for d, _ in pts], [v.loc[d] / 1000 for d, _ in pts], marker=mk, s=sizes, color=col,
                       edgecolor="white", lw=0.5, zorder=4, label=f"{kind.capitalize()} (size = amount)")
    ax.set_ylabel("EUR thousand", fontsize=7.5)
    ax.legend(fontsize=7, frameon=False, ncol=3, loc="upper left")
    style(ax)
    fig.tight_layout()
    paths["perf_value"] = base + "_perf_value.png"
    fig.savefig(paths["perf_value"], dpi=200)
    plt.close(fig)

    # 8) TTWROR vs. ACWI und Gegenszenario "keine Trades"
    fig, ax = plt.subplots(figsize=(9, 3.0))
    c, b = perf["ttwror_curve"], perf["bench_curve"]
    ax.plot(c.index, (c - 1) * 100, color=color, lw=1.8, label="Portfolio TTWROR")
    ax.plot(b.index, (b - 1) * 100, color=grey, lw=1.2, label="MSCI ACWI (EUR)")
    if perf["mode"] == "cash account":
        sc = perf["sec_curve"]
        ax.plot(sc.index, (sc - 1) * 100, color=color, lw=1.0, ls=":", label="Invested capital only (excl. cash)")
    nc = perf["ns_curve"]
    ax.plot(nc.index, (nc - 1) * 100, color=tint, lw=1.1, ls="--", label="Never sold (same buys, no sales)")
    ax.axhline(0, color="#BBBBBB", lw=0.6)
    ax.set_ylabel("Cumulative return (%)", fontsize=7.5)
    ax.legend(fontsize=7, frameon=False, loc="upper left", ncol=2)
    style(ax)
    fig.tight_layout()
    paths["perf_tw"] = base + "_perf_tw.png"
    fig.savefig(paths["perf_tw"], dpi=200)
    plt.close(fig)

    # 9) Wirkung der Entscheidungen (beste/schlechteste)
    dec = sorted(perf["decisions"], key=lambda x: x["impact_eur"])
    if dec:
        sel = dec[:5] + [d for d in dec[-5:] if d not in dec[:5]]
        fig, ax = plt.subplots(figsize=(9, 0.24 * len(sel) + 0.8))
        lab = [f"{d['date']} {d['type']} {d['ticker']}" for d in sel]
        ax.barh(range(len(sel)), [d["impact_eur"] for d in sel],
                color=["#2D8A4E" if d["impact_eur"] >= 0 else "#C0392B" for d in sel])
        ax.set_yticks(range(len(sel)))
        ax.set_yticklabels(lab, fontsize=8)
        ax.tick_params(axis="x", labelsize=8)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.axvline(0, color="#888888", lw=0.6)
        ax.set_xlabel("Value added vs. MSCI ACWI (EUR): buys over the holding period, sells over the next 12 months",
                      fontsize=8)
        style(ax)
        ax.grid(axis="x", color="#E5E5E5", lw=0.6)
        ax.grid(axis="y", visible=False)
        fig.tight_layout()
        paths["decisions"] = base + "_decisions.png"
        fig.savefig(paths["decisions"], dpi=200)
        plt.close(fig)
    return paths


# --------------------------------------------------------------- PDF
def _build_pdf(a, bt, pdf_path, title, texts, fc, portfolio_file, perf=None, tx_files=None, research=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import (HRFlowable, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)
    from finrobot.functional.reportlab import REPORT_BRAND, REPORT_COLOR, _heading_font, _paragraphs, _scaled_image, _tint

    NAVY, PANEL, GREY = colors.HexColor(REPORT_COLOR), colors.HexColor(_tint(REPORT_COLOR, 0.93)), colors.HexColor("#5A6472")
    page_w, page_h = A4
    m = 1.6 * cm
    usable = page_w - 2 * m
    ss = getSampleStyleSheet()
    hf = _heading_font()
    body = ParagraphStyle("BodyP", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.2,
                          alignment=TA_JUSTIFY, spaceAfter=5)
    small = ParagraphStyle("SmallP", parent=body, fontSize=7, leading=9, textColor=GREY, alignment=0)
    cell = ParagraphStyle("CellP", parent=body, fontSize=7.6, leading=9.4, alignment=0, spaceAfter=0)
    cell_r = ParagraphStyle("CellRP", parent=cell, alignment=2)
    cell_w = ParagraphStyle("CellWP", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    cell_wr = ParagraphStyle("CellWRP", parent=cell_w, alignment=2)
    h1 = ParagraphStyle("H1P", parent=body, fontName=hf, fontSize=20, leading=24, textColor=NAVY, alignment=0)
    h2 = ParagraphStyle("H2P", parent=body, fontName=hf, fontSize=13, leading=16, textColor=NAVY, alignment=0,
                        spaceBefore=8, spaceAfter=2)
    head = ParagraphStyle("HeadP", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=14.5, alignment=0)
    exh = ParagraphStyle("ExhP", parent=cell, fontName="Helvetica-Bold", textColor=NAVY, fontSize=8.5, spaceBefore=6,
                         spaceAfter=3)
    line = TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("LINEBELOW", (0, -1), (-1, -1), 0.8, NAVY),
                       ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_tint(REPORT_COLOR, 0.96))]),
                       ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 1.8),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)])
    exno = [0]
    P, X = pe._p, pe._x

    def heading(t):
        return [Paragraph(t, h2), HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceBefore=1, spaceAfter=5)]

    def exhibit(t):
        exno[0] += 1
        return Paragraph(f"Exhibit {exno[0]}: {t}", exh)

    def source(t):
        return Paragraph(f"Source: {t}", small)

    def table(rows, widths, first_left=True, left=()):
        lf = lambda i: (i == 0 and first_left) or i in left
        out = [[Paragraph(str(c), (cell_w if lf(i) else cell_wr)) for i, c in enumerate(rows[0])]]
        for r in rows[1:]:
            out.append([Paragraph(str(c), cell if lf(i) else cell_r) for i, c in enumerate(r)])
        t = Table(out, colWidths=widths, repeatRows=1)
        t.setStyle(line)
        return t

    paths = _charts(a, bt, os.path.splitext(pdf_path)[0], REPORT_COLOR, perf)
    st = a["stats"]
    content = [Paragraph(escape(title), h1), Spacer(1, 3), Paragraph(escape(texts["headline"]), head), Spacer(1, 2),
               Paragraph(f"{len(a['tickers'])} positions | base currency EUR | benchmark MSCI ACWI (and FTSE All-World) | "
                         f"data as of {a['date']} [1] | Generated by {REPORT_BRAND}", small), Spacer(1, 8)]
    # Seite 1
    left_w, right_w = usable * 0.52, usable * 0.44
    inner = right_w - 14
    kd = [["Key figures", ""], ["Portfolio value (EUR)", f"{a['values'].sum():,.0f}"],
          ["Positions / effective number", f"{len(a['tickers'])} / {a['structure']['effective_n']:.1f}"],
          [f"CAGR {a['years_hist']}y (MSCI ACWI)", f"{P(st.get('cagr'))} ({P(st.get('bench_cagr'))})"],
          ["Volatility / max drawdown", f"{P(st.get('vol'))} / {P(st.get('max_dd'))}"],
          ["Sharpe / Sortino", f"{X(st.get('sharpe'))} / {X(st.get('sortino'))}"],
          ["Beta / tracking error", f"{X(st.get('beta'))} / {P(st.get('tracking_error'))}"],
          ["Top 5 positions", P(a["structure"]["top5"])]]
    if perf:
        kd.insert(4, ["Realised TTWROR p.a. (ACWI)", f"{P(perf['ttwror_pa'])} ({P(perf['bench_tw_pa'])})"])
        kd.insert(5, ["Realised MWR p.a. (ACWI)", f"{P(perf['mwr'])} ({P(perf['bench_mwr'])})"])
    kt = Table([[Paragraph(r[0], cell_w if i == 0 else cell), Paragraph(r[1], cell_wr if i == 0 else cell_r)]
                for i, r in enumerate(kd)], colWidths=[inner * 0.58, inner * 0.42])
    kt.setStyle(TableStyle(line.getCommands() + [("SPAN", (0, 0), (-1, 0))]))
    right = [exhibit("Key figures (today's weights)"), kt, source("Yahoo Finance [1], own calculations"), Spacer(1, 6),
             exhibit("Sector allocation"), _scaled_image(paths["sector"], inner, 5.0 * cm), source("Yahoo Finance [1]")]
    panel = Table([[right]], colWidths=[right_w])
    panel.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    row = Table([[heading("Summary") + _paragraphs(texts["summary"], body), "", panel]],
                colWidths=[left_w, usable - left_w - right_w, right_w])
    row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")] +
                            [(k, (0, 0), (-1, -1), 0) for k in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]))
    content += [row, Spacer(1, 6), KeepTogether([
        exhibit(f"Performance over {a['years_hist']} years with today's weights vs. benchmarks (EUR)"),
        _scaled_image(paths["perf"], usable, 6.2 * cm),
        source("Yahoo Finance [1]; dividend-adjusted prices converted to EUR. Today's weights applied to the past, so "
               "this is not the realised performance" + (" (see Actual Performance &amp; Decisions)." if perf else
                                                          " (no trading history provided)."))])]
    # Positionen
    rows = [["Position", "Sector", "Weight", "1y return", "Volatility", "Risk share", "Fwd P/E", "PEG", "Growth", "Upside"]]
    for p in sorted(a["positions"], key=lambda x: -x["weight"]):
        rows.append([f"<b>{escape(p['ticker'])}</b> {escape(str(p['name'])[:22])}", escape(str(p["sector"])[:18]),
                     P(p["weight"]), P(p["ret_1y"]), P(p["vol"]), P(p["risk_contrib"]), X(p["forward_pe"], 1),
                     X(p["peg"]), P(p["revenue_growth"]), P(p["upside"])])
    if perf:
        content += [PageBreak()] + _perf_section(perf, paths, texts, heading, exhibit, source, table, body, usable, line,
                                                 PANEL, NAVY, P, escape, _paragraphs, _scaled_image, KeepTogether, Table,
                                                 TableStyle, cm)
    w0 = usable * 0.24
    content += [PageBreak()] + heading("Positions") + [
        exhibit("Positions: weight, return, risk and valuation"),
        table(rows, [w0, usable * 0.15] + [(usable - w0 - usable * 0.15) / 8] * 8),
        source("Yahoo Finance [1]; risk share = contribution to portfolio variance (Ledoit-Wolf covariance); upside = "
               "consensus mean target vs. current price; PEG and growth as reported by Yahoo.")]
    if research:
        content += [_research_table(research, a, exhibit, source, table, usable, escape)]
    # Risiko
    pair = Table([[[exhibit("Weight vs. share of portfolio risk"), _scaled_image(paths["risk"], usable * 0.48, 7.2 * cm)],
                   [exhibit("Correlation of daily returns"), _scaled_image(paths["corr"], usable * 0.48, 7.2 * cm)]]],
                 colWidths=[usable * 0.5, usable * 0.5])
    pair.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")] +
                             [(k, (0, 0), (-1, -1), 0) for k in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]))
    content += heading("Risk") + _paragraphs(texts["risk_commentary"], body) + [pair, source(
        f"Yahoo Finance [1], {a['years_hist']} years of daily returns; own calculations.")]
    if a["stress"]:
        rows = [["Scenario", "Period", "Portfolio", "MSCI ACWI", "Difference"]]
        for x in a["stress"]:
            rows.append([x["scenario"], f"{x['from']} to {x['to']}", P(x["portfolio"]), P(x["benchmark"]),
                         P(x["portfolio"] - x["benchmark"])])
        content += [KeepTogether([exhibit("Stress tests: today's portfolio in past market shocks"),
                                  table(rows, [usable * 0.26, usable * 0.26, usable * 0.16, usable * 0.16, usable * 0.16]),
                                  source("Yahoo Finance [1]; price change of today's holdings over each period, in EUR.")])]
    # Optimierung
    keys = ["current", "min_variance", "max_sharpe", "hrp", "equal_weight"]
    rows = [["Position"] + [pe.OPT_NAMES[k] for k in keys]]
    order = np.argsort(-a["opt"]["current"])
    for i in order:
        rows.append([a["tickers"][i]] + [P(a["opt"][k][i]) for k in keys])
    for lab, key, f in (("Expected return", "exp_return", P), ("Volatility", "vol", P), ("Sharpe", "sharpe", X),
                        ("Turnover vs current", "turnover", P)):
        rows.append([f"<b>{lab}</b>"] + [f"<b>{f(a['opt_stats'][k][key])}</b>" for k in keys])
    tw = table(rows, [usable * 0.24] + [usable * 0.152] * 5)
    n = len(rows)
    tw.setStyle(TableStyle(line.getCommands() + [("LINEABOVE", (0, n - 4), (-1, n - 4), 0.8, NAVY),
                                                 ("BACKGROUND", (0, n - 4), (-1, -1), PANEL)]))
    content += [PageBreak()] + heading("Optimization") + _paragraphs(texts["optimization_commentary"], body) + [
        KeepTogether([exhibit("Target weights by method"), tw, source(
            f"Own calculations [1]. Long-only, max {P(a['cap'], 0)} per position and {P(a['sector_cap'], 0)} per sector "
            "(HRP: position cap only); "
            f"covariance: Ledoit-Wolf (shrinkage {a['cov_shrink']:.2f}); expected returns: 50% historical + 50% CAPM "
            "(beta x 5% equity risk premium). Model outputs are sensitive to estimation error.")]),
        KeepTogether([exhibit("Efficient frontier and portfolios (model view)"),
                      _scaled_image(paths["frontier"], usable * 0.6, 7 * cm), source("Own calculations [1]")])]
    # Backtest
    if bt and bt.get("stats"):
        rows = [["Strategy", "CAGR", "Volatility", "Sharpe", "Max drawdown", "Turnover p.a."]]
        for k, s in bt["stats"].items():
            rows.append([k, P(s.get("cagr")), P(s.get("vol")), X(s.get("sharpe")), P(s.get("max_dd")),
                         P(s.get("turnover_pa"), 0) if "turnover_pa" in s else "-"])
        content += heading("Backtest") + _paragraphs(texts["backtest_commentary"], body) + [KeepTogether([
            exhibit(f"Walk-forward backtest {bt['start']} to {bt['end']} (EUR)"), _scaled_image(paths["backtest"], usable, 6.2 * cm),
            table(rows, [usable * 0.30] + [usable * 0.14] * 5),
            source(f"Own calculations [1]: quarterly rebalancing, {bt['lookback_years']}-year lookback, {bt['cost_bps']} bp "
                   "costs per trade; each method uses only data available at the rebalancing date. Uses today's holdings "
                   "(hindsight in stock selection): it compares weighting methods, not stock picking."
                   + (f" Excluded for lack of price history: {', '.join(bt['excluded'])}." if bt.get("excluded") else ""))])]
    content += heading("Recommendations") + _paragraphs(texts["recommendations"], body)
    content.append(Paragraph("For academic purposes only; not investment advice.", small))
    # Quellen
    refs = [f"Yahoo Finance via yfinance: daily dividend-adjusted prices, FX rates (EUR), company data and consensus "
            f"targets, retrieved {a['date']}.",
            (f"Portfolio file: {escape(os.path.basename(portfolio_file))}." if portfolio_file else
             "Holdings reconstructed from the transaction exports."),
            "Methods: Ledoit &amp; Wolf (2004), A well-conditioned estimator for large-dimensional covariance matrices; "
            "Lopez de Prado (2016), Building diversified portfolios that outperform out of sample (HRP); "
            "Markowitz (1952), Portfolio selection."]
    if research:
        refs.append("[R] Research pipeline: theses from the annual report agent, thesis log of the earnings reviewer, "
                    "investment committee votes, weekly forecaster log and news-tracker signals.")
    if perf:
        refs.insert(2, "Transaction exports: " + escape(", ".join(os.path.basename(f) for f in (tx_files or []))) +
                    "; TTWROR = daily chained returns excluding external cash flows, MWR = internal rate of return (XIRR).")
    content += heading("Sources") + [Paragraph(f"[{i}] {r}", ParagraphStyle(f"RefP{i}", parent=body, fontSize=8.5, alignment=0,
                                                                             leading=11, leftIndent=14, firstLineIndent=-14))
                                     for i, r in enumerate(refs, 1)]
    rate = f"{fc['match_rate'] * 100:.0f}%" if fc["match_rate"] is not None else "n/a"
    content += heading("Appendix: Automated Fact Check") + [Paragraph(
        f"Every number in the agent's text was compared with the calculated data [1]: {fc['matched']} of {fc['total_claims']} "
        f"found ({rate}). Not found does not automatically mean wrong (e.g. derived figures).", small)]
    if fc["unmatched"]:
        rows = [["Section", "Figure", "Context"]] + [[escape(u["section"]), escape(u["text"]), escape(u["context"])]
                                                     for u in fc["unmatched"][:40]]
        t_ = table(rows, [usable * 0.18, usable * 0.12, usable * 0.70])
        t_.setStyle(TableStyle(line.getCommands() + [("VALIGN", (0, 0), (-1, -1), "TOP")]))
        content.append(t_)
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
        canv.drawString(m, page_h - 0.72 * cm, "PORTFOLIO REVIEW")
        canv.setFont("Helvetica", 9)
        canv.drawRightString(page_w - m, page_h - 0.72 * cm, gen)
        _footer(canv, d)
        canv.restoreState()

    def _later(canv, d):
        canv.saveState()
        canv.setFillColor(NAVY)
        canv.setFont("Helvetica-Bold", 8)
        canv.drawString(m, page_h - 1.0 * cm, escape(title))
        canv.setFont("Helvetica", 8)
        canv.setFillColor(GREY)
        canv.drawRightString(page_w - m, page_h - 1.0 * cm, f"Portfolio Review  |  {gen}")
        canv.setStrokeColor(NAVY)
        canv.line(m, page_h - 1.15 * cm, page_w - m, page_h - 1.15 * cm)
        _footer(canv, d)
        canv.restoreState()

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=m, rightMargin=m, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    doc.build(content, onFirstPage=_first, onLaterPages=_later)


def _perf_section(perf, paths, texts, heading, exhibit, source, table, body, usable, line, PANEL, NAVY, P, escape,
                  _paragraphs, _scaled_image, KeepTogether, Table, TableStyle, cm):
    out = heading("Actual Performance &amp; Decisions") + _paragraphs(texts.get("performance_commentary") or "", body)
    diff = perf["final_value"] - perf["bench_final_value"]
    ns = perf["never_sold"]
    rows = [["Measure", "Portfolio", "Comparison", "Difference"],
            ["Value today (EUR) vs. same cash flows in MSCI ACWI", f"{perf['final_value']:,.0f}",
             f"{perf['bench_final_value']:,.0f}", f"{diff:,.0f}"],
            ["MWR / IRR p.a. since start vs. MSCI ACWI (same flows)", P(perf["mwr"]), P(perf["bench_mwr"]),
             P(perf["mwr"] - perf["bench_mwr"]) if perf["mwr"] is not None and perf["bench_mwr"] is not None else "n/a"],
            ["Securities only (excl. cash): TTWROR cumulative vs. never sold", P(ns["actual_ttwror"]), P(ns["ttwror"]),
             P(ns["actual_ttwror"] - ns["ttwror"])],
            ["Securities only: MWR p.a. vs. never sold", P(ns["actual_mwr"]), P(ns["mwr"]),
             P(ns["actual_mwr"] - ns["mwr"]) if ns["actual_mwr"] is not None and ns["mwr"] is not None else "n/a"],
            ["Net invested capital (EUR)", f"{perf['net_invested']:,.0f}", "-", "-"],
            ["Dividends received / fees paid (EUR)", f"{perf['dividends_total']:,.0f} / {perf['fees_total']:,.0f}", "-", "-"]]
    prow = [["Period", "From", "Portfolio TTWROR", "MSCI ACWI", "Difference", "MWR", "P/L (EUR)"]]
    allp = perf["periods"] + perf["calendar_years"]
    for r in allp:
        u = " p.a." if r["annualized"] else ""
        prow.append([f"<b>{r['period']}</b>" if r in perf["periods"] else r["period"], r["start"], P(r["ttwror"]) + u,
                     P(r["bench"]) + u, P(r["diff"]) + u, P(r["mwr"]) + u, f"{r['pl_eur']:,.0f}"])
    ptab = table(prow, [usable * 0.16, usable * 0.13, usable * 0.16, usable * 0.14, usable * 0.14, usable * 0.13,
                        usable * 0.14])
    npd = len(perf["periods"])
    ptab.setStyle(TableStyle(line.getCommands() + [("LINEABOVE", (0, npd + 1), (-1, npd + 1), 0.8, NAVY)]))
    out += [KeepTogether([exhibit(f"Portfolio value, trades and invested capital ({perf['start']} to {perf['end']})"),
                          _scaled_image(paths["perf_value"], usable, 6.4 * cm),
                          source("Transaction exports and Yahoo Finance [1]; values in EUR; triangles mark buys (green) and "
                                 "sells (red). The ACWI line invests every external cash flow on the same day.")]),
            KeepTogether([exhibit("Returns by period vs. MSCI ACWI (EUR)"), ptab,
                          source("Own calculations [1]. TTWROR (time-weighted) measures the investment decisions independent "
                                 "of deposits and withdrawals; MWR (money-weighted) is what the invested money earned, "
                                 "including timing. Periods longer than one year annualized. P/L = change in value minus "
                                 "net inflows. Mode: " + perf["mode"] + ".")]),
            KeepTogether([exhibit("Realised result, cash drag and the 'never sold' counterfactual"),
                          table(rows, [usable * 0.46, usable * 0.18, usable * 0.18, usable * 0.18]),
                          source("Own calculations [1]. 'Securities only' ignores cash held at the broker; 'never sold' keeps "
                                 "every share bought (same buys, no sales) and measures the effect of all sell decisions.")]),
            KeepTogether([exhibit("Time-weighted return vs. benchmark, cash drag and 'never sold' counterfactual"),
                          _scaled_image(paths["perf_tw"], usable, 5.6 * cm), source("Own calculations [1]")])]
    open_, closed, other = pf.condensed_positions(perf)
    pos = open_ + closed + ([other] if other else [])
    rows = [["Position", "Status", "Value", "Unrealised", "Realised", "Dividends", "Total P/L", "Share of P/L", "IRR p.a."]]
    for p in pos:
        rows.append([f"<b>{escape(p['ticker'])}</b>", "open" if p["open"] else "closed", f"{p['market_value']:,.0f}",
                     f"{p['unrealized']:,.0f}", f"{p['realized']:,.0f}", f"{p['dividends']:,.0f}", f"{p['total_pl']:,.0f}",
                     P(p["contribution"]), P(p["irr"])])
    out += [KeepTogether([exhibit("Profit and loss by position (EUR)"),
                          table(rows, [usable * 0.15, usable * 0.09] + [usable * 0.76 / 7] * 7),
                          source("Own calculations [1]: average-cost method; realised after fees and taxes as booked; "
                                 "IRR on each position's own cash flows. Open positions first, then the five best and worst "
                                 "closed positions" + ("; remaining closed positions aggregated." if other else "."))])]
    dec = sorted(perf["decisions"], key=lambda x: -x["impact_eur"])
    if dec:
        sel = dec[:5] + [d for d in dec[-5:] if d not in dec[:5]]
        rows = [["Trade", "Amount", "Days", "Stock", "ACWI", "Excess", "Value added"]]
        for d in sel:
            rows.append([f"{d['date']} <b>{d['type']}</b> {escape(d['ticker'])}", f"{d['eur']:,.0f}",
                         f"{d['days']}" + (f" ({d['held']})" if d.get("held") else ""), P(d["ret_stock"]),
                         P(d["ret_bench"]), P(d["excess"]), f"{d['impact_eur']:,.0f}"])
        buys = [d for d in dec if d["type"] == "buy"]
        sells = [d for d in dec if d["type"] == "sell"]
        note = []
        if buys:
            note.append(f"{sum(d['excess'] > 0 for d in buys)} of {len(buys)} buys beat the ACWI over their holding period")
        if sells:
            note.append(f"{sum(d['excess'] > 0 for d in sells)} of {len(sells)} sells were followed by underperformance "
                        f"within 12 months")
        items = [exhibit("Best and worst decisions vs. MSCI ACWI (EUR)")]
        if paths.get("decisions"):
            items.append(_scaled_image(paths["decisions"], usable, 6.0 * cm))
        items += [table(rows, [usable * 0.28, usable * 0.11, usable * 0.15] + [usable * 0.115] * 4),
                  source("Own calculations [1], total-return prices. Buy = stock minus ACWI over the actual holding period "
                         "(FIFO until sold, otherwise until today); sell = ACWI minus stock over the 12 months after the "
                         "sale; value added = amount x excess. " + "; ".join(note) + ".")]
        out.append(KeepTogether(items))
    out += _letter_sections(perf, texts, heading, exhibit, source, table, body, usable, P, escape, _paragraphs,
                            KeepTogether)
    if perf["warnings"]:
        out.append(Paragraph_small("Data notes: " + escape(" | ".join(perf["warnings"][:6]))))
    return out


def _letter_sections(perf, texts, heading, exhibit, source, table, body, usable, P, escape, _paragraphs, KeepTogether):
    """Attribution, Umschlag/Kosten, Ausstiege, Fehler und Lehren (Aufbau nach Fundsmith, Pershing, Greenlight, Giverny)."""
    out = []
    c = perf.get("costs")
    if c and perf.get("attribution"):
        big = [x for x in perf["attribution"] if x["contribution"] is not None and abs(x["contribution"]) >= 0.005]
        small = [x for x in perf["attribution"] if x not in big]
        rows = [["Position", "P/L (EUR)", "Contribution"]]
        det = [x for x in big if x["pl_eur"] < 0]
        con = sorted([x for x in big if x["pl_eur"] >= 0], key=lambda x: -x["pl_eur"])
        for grp, lab in ((det, "Detractors"), (con, "Contributors")):
            if grp:
                rows.append([f"<b>{lab}</b>", "", ""])
            for x in grp:
                rows.append([escape(x["ticker"]), f"{x['pl_eur']:,.0f}", P(x["contribution"])])
        if small:
            rows.append([f"{len(small)} other positions (each below 0.5%)", f"{sum(x['pl_eur'] for x in small):,.0f}",
                         P(sum(x["contribution"] or 0 for x in small))])
        rows.append(["<b>Total</b>", f"<b>{c['total_pl']:,.0f}</b>", f"<b>{P(c['total_contribution'])}</b>"])
        crow = [["Turnover and costs", "Value"], ["Purchases / sales (EUR)", f"{c['purchases']:,.0f} / {c['sales']:,.0f}"],
                ["Trades", str(c["n_trades"])], ["Turnover (lower of purchases and sales / avg. value)", P(c["turnover"])],
                ["Fees (EUR, % of avg. value)", f"{c['fees']:,.0f} ({P(c['fees_pct'])})"], ["Taxes (EUR)", f"{c['taxes']:,.0f}"]]
        out.append(KeepTogether([exhibit(f"Attribution and costs, last 12 months ({c['start']} to {c['end']})"),
                                 _side_by_side(table(rows, [usable * 0.26, usable * 0.12, usable * 0.13]),
                                               table(crow, [usable * 0.30, usable * 0.15]), usable),
                                 source("Own calculations [1]: P/L = change in position value minus net purchases (incl. "
                                        "dividends received); contribution in % of the average portfolio value; positions "
                                        "below 0.5% aggregated. Turnover = lower of purchases and sales / average value.")]))
    ex = perf.get("exits") or []
    if ex:
        rows = [["Position", "Held", "Invested", "Total P/L", "IRR", "Stock vs ACWI (held)", "After sale vs ACWI"]]
        for e in ex[:8]:
            rows.append([f"<b>{escape(e['ticker'])}</b>", f"{e['first_buy']} to {e['last_sell']}", f"{e['invested']:,.0f}",
                         f"{e['total_pl']:,.0f}", P(e["irr"]),
                         f"{P(e['stock_held'])} vs {P(e['acwi_held'])}" if e["stock_held"] is not None else "n/a",
                         f"{P(e['stock_after'])} vs {P(e['acwi_after'])}" if e["stock_after"] is not None else "n/a"])
        out.append(KeepTogether([exhibit("Exits: fully sold positions in review (most recent first)"),
                                 table(rows, [usable * 0.11, usable * 0.21, usable * 0.10, usable * 0.10, usable * 0.09,
                                              usable * 0.195, usable * 0.195]),
                                 source("Own calculations [1], total-return prices in EUR: 'held' from the first purchase "
                                        "to the last sale, 'after sale' from the last sale until today.")]))
    mk = perf.get("mistakes") or []
    if mk or texts.get("mistakes_and_lessons"):
        out += heading("Mistakes and Lessons") + _paragraphs(texts.get("mistakes_and_lessons") or "", body)
        if mk:
            rows = [["Decision", "Amount", "Stock vs ACWI", "Value lost", "Rationale at the time"]]
            for d in mk:
                rows.append([f"{d['date']} <b>{d['type']}</b> {escape(d['ticker'])}", f"{d['eur']:,.0f}",
                             f"{P(d['ret_stock'])} vs {P(d['ret_bench'])}", f"{-d['impact_eur']:,.0f}",
                             escape(d.get("note") or "not recorded")])
            out.append(KeepTogether([table(rows, [usable * 0.24, usable * 0.10, usable * 0.18, usable * 0.11, usable * 0.37],
                                           left=(4,)),
                                     source("Weakest decisions vs MSCI ACWI [1]: buys over the holding period, sales over "
                                            "the 12 months after. Rationale from portfolios/decision_notes.csv where "
                                            "recorded.")]))
    return out


def _side_by_side(left, right, usable):
    from reportlab.platypus import Table, TableStyle
    t = Table([[left, right]], colWidths=[usable * 0.53, usable * 0.47])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (0, 0), 10)]))
    return t


def _research_table(research, a, exhibit, source, table, usable, escape):
    """Research-Sicht je Position aus den anderen Agenten (Pipeline)."""
    from reportlab.platypus import KeepTogether
    col = {"intact": "#2D8A4E", "strengthened": "#2D8A4E", "weakened": "#C77700", "broken": "#C0392B"}
    rows = [["Position", "Weight", "Theses (status)", "Committee", "Forecast", "News signals"]]
    w = a["weights"]
    for t, v in sorted(research.items(), key=lambda kv: -float(w.get(kv[0], 0) or 0)):
        if v.get("thesis_status"):
            th = ", ".join(f"<font color='{col.get(k, '#5A6472')}'>{escape(k)} {n}</font>" for k, n in v["thesis_status"].items())
        elif v.get("theses"):
            th = f"{v['theses']} (FY{v['report_fy']}, not reviewed)"
        else:
            th = "-"
        c = v.get("committee") or {}
        com = f"{(c.get('recommendation') or 'n/a').upper()}" + (f", target {c['target']:,.0f}" if c.get("target") else "") + \
            (f" ({c['date']})" if c.get("date") else "") if c else "-"
        f = v.get("forecast") or {}
        fc_ = f"{f.get('direction')} ({f.get('low')}% to {f.get('high')}%)" if f else "-"
        news = "; ".join(v.get("news_flags") or []) or (f"sentiment {v['sentiment']:+.0f}" if v.get("sentiment") is not None else "-")
        rows.append([f"<b>{escape(t)}</b>", P_(w.get(t)), th, escape(com), escape(fc_), escape(news)])
    return KeepTogether([exhibit("Research view by position (annual report theses, earnings reviews, committee, "
                                 "forecaster, news tracker)"),
                         table(rows, [usable * 0.11, usable * 0.08, usable * 0.22, usable * 0.20, usable * 0.12,
                                      usable * 0.27]),
                         source("Agent outputs of the research pipeline [R]: thesis status from the latest earnings "
                                "review (thesis log), committee recommendation with 6-month target in the trading "
                                "currency, weekly forecast, flags of the latest news digest.")])


def P_(x):
    try:
        return f"{float(x) * 100:.1f}%"
    except (TypeError, ValueError):
        return "-"


def Paragraph_small(text):
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    return Paragraph(text, ParagraphStyle("PerfNote", fontName="Helvetica", fontSize=7, leading=9,
                                          textColor="#5A6472"))


# --------------------------------------------------------------- Agent und Tools
def make_tools(state):
    """Tools mit Zugriff auf die einmal berechnete Analyse (state: analysis, backtest, Pfade)."""

    def get_portfolio_analysis() -> str:
        """Structure, performance, risk, positions, stress tests and optimizer results of the portfolio."""
        return pe.analysis_text(state["analysis"])

    def get_backtest() -> str:
        """Walk-forward backtest of the weighting methods (current, equal weight, min variance, max Sharpe, HRP)."""
        return pe.backtest_text(state["backtest"]) if state.get("backtest") else "Backtest not available."

    def get_research_views() -> str:
        """Research view by position from the other agents: thesis status (earnings reviews), investment committee
        recommendation and target, weekly forecast and news-tracker signals."""
        from .pipeline import research_text
        return research_text(state["research"]) if state.get("research") else "No research views available."

    def get_actual_performance() -> str:
        """Realised performance from the transaction history: TTWROR, MWR/IRR, same-cash-flow MSCI ACWI benchmark,
        P/L by position and the effect of each buy/sell decision vs the index."""
        return pf.performance_text(state["performance"]) if state.get("performance") else \
            "No transaction history provided - performance is hypothetical (today's weights)."

    def build_portfolio_review(
        headline: Annotated[str, "one-sentence headline (max. 25 words)"],
        summary: Annotated[str, "summary for page 1, 120-200 words: performance vs benchmark, main risks, key recommendation"],
        risk_commentary: Annotated[str, "risk, 150-300 words: concentration, risk contributions vs weights, correlations, "
                                        "currency and sector exposure, stress tests"],
        optimization_commentary: Annotated[str, "optimization, 150-300 words: what each method proposes and why, and where "
                                                "you distrust the model (estimation error, concentration, turnover)"],
        backtest_commentary: Annotated[str, "backtest, 80-200 words: which method held up out of sample and the limits"],
        recommendations: Annotated[str, "recommendations, 100-250 words: concrete, prioritised rebalancing ideas within the "
                                        "constraints, each with its rationale"],
        performance_commentary: Annotated[str, "only if a transaction history exists, 150-300 words: returns vs MSCI "
                                               "ACWI over YTD, 1, 3 and 5 years and since start, the named causes of any "
                                               "shortfall, the 12-month attribution (detractors first, then contributors), "
                                               "TTWROR vs MWR (timing), cash drag, turnover and costs, the 'never sold' "
                                               "counterfactual and material data notes; "
                                               "otherwise empty"] = "",
        mistakes_and_lessons: Annotated[str, "only if a transaction history exists, 60-250 words: the weakest decisions "
                                             "from MISTAKE CANDIDATES and EXITS (what was decided, what happened vs the "
                                             "index, the value lost) and one concrete lesson each; use the recorded notes "
                                             "for the reasoning at the time and say 'no rationale recorded' otherwise; "
                                             "otherwise empty"] = "",
    ) -> str:
        """Build the portfolio review PDF (with automated fact check)."""
        from finrobot.functional.fact_check import SourceIndex, run_fact_check, save_json
        texts = dict(headline=headline, summary=summary, risk_commentary=risk_commentary,
                     optimization_commentary=optimization_commentary, backtest_commentary=backtest_commentary,
                     recommendations=recommendations)
        perf = state.get("performance")
        if perf:
            texts["performance_commentary"] = performance_commentary
            texts["mistakes_and_lessons"] = mistakes_and_lessons
        problems = []
        for nm, lo, hi in (("summary", 80, 260), ("risk_commentary", 100, 380), ("optimization_commentary", 100, 380),
                           ("backtest_commentary", 50, 260), ("recommendations", 60, 320)) + \
                ((("performance_commentary", 100, 380), ("mistakes_and_lessons", 40 if perf.get("mistakes") else 0, 300))
                 if perf else ()):
            n = len(str(texts[nm] or "").split())
            if n < lo or n > hi:
                problems.append(f"{nm}: {n} words, expected {lo}-{hi}")
        if problems:
            return "PDF NOT generated. Problems: " + "; ".join(problems) + ". Fix them and call build_portfolio_review again."
        a, bt = state["analysis"], state.get("backtest")
        os.makedirs(state["save_dir"], exist_ok=True)
        pdf_path = os.path.join(state["save_dir"], f"{state['name']}_portfolio_review.pdf")
        json.dump(texts, open(os.path.splitext(pdf_path)[0] + "_build_args.json", "w", encoding="utf-8"), indent=2,
                  ensure_ascii=False)
        src = SourceIndex("[1] Calculated portfolio data")
        src.add_text(pe.analysis_text(a))
        if bt:
            src.add_text(pe.backtest_text(bt))
        if perf:
            src.add_text(pf.performance_text(perf))
        if state.get("research"):
            from .pipeline import research_text
            src.add_text(research_text(state["research"]))
        fc = run_fact_check([(k.replace("_", " ").capitalize(), v) for k, v in texts.items()], [src], None)
        key = os.path.abspath(pdf_path)
        _ROUNDS[key] = _ROUNDS.get(key, 0) + 1
        base = os.path.splitext(pdf_path)[0]
        if _ROUNDS[key] == 1:
            save_json(fc, base + "_factcheck_round1.json")
        save_json(fc, base + "_factcheck.json")
        try:
            _build_pdf(a, bt, pdf_path, state["title"], texts, fc, state["portfolio_file"], perf, state.get("tx_files"),
                       state.get("research"))
        except Exception:
            import traceback
            return "PDF NOT generated:\n" + traceback.format_exc()[-1500:]
        msg = f"Portfolio review generated: {pdf_path}. Fact check: {fc['matched']} of {fc['total_claims']} figures found."
        if _ROUNDS[key] == 1 and fc["unmatched"] and os.environ.get("FINROBOT_SELF_CORRECT", "1") != "0":
            items = [f"- [{u['section']}] {u['text']}: \"{' '.join(str(u.get('context', '')).split()).strip('. ')[:170]}\""
                     for u in fc["unmatched"][:25]]
            msg += ("\n\nSELF-CHECK (one revision round): these figures were not found in the calculated data:\n" +
                    "\n".join(items) + "\n\nCorrect each, remove it, or keep it only if it is a correct calculation. Then call "
                    "build_portfolio_review exactly once more with the revised texts. After that, reply TERMINATE.")
        return msg

    return [get_portfolio_analysis, get_backtest, get_actual_performance, get_research_views, build_portfolio_review]


SYSTEM = dedent("""
    You are a portfolio manager reviewing a client portfolio (base currency EUR, benchmark MSCI ACWI). All figures come
    from the calculated data; never invent numbers. Treat optimizer outputs as model suggestions: point out estimation
    error, concentration and turnover, and do not follow a model blindly. Recommendations must respect the stated
    constraints and are for academic purposes, not investment advice. When a transaction history exists, judge the
    client's past decisions honestly (what worked, what did not, timing) without hindsight moralising. Use tools one at
    a time; reply TERMINATE when done.
""").strip() + "\n" + STYLE_RULES


NOTES_FILE = Path(__file__).resolve().parents[1] / "portfolios" / "decision_notes.csv"


def load_performance(transaction_files, notes_file=NOTES_FILE):
    """Broker-Exporte einlesen, ISINs aufloesen, Performance berechnen. Gibt (perf, tx, issues) zurueck."""
    files = [transaction_files] if isinstance(transaction_files, str) else list(transaction_files)
    tx, issues = tr.read_all(files)
    if tx.empty:
        raise ValueError("no usable transactions found: " + "; ".join(issues[:5]))
    tx, unresolved = tr.attach_tickers(tx)
    if unresolved:
        issues.append(f"ISINs without Yahoo ticker (add to portfolios/isin_map.csv): {', '.join(unresolved)}")
    print(f"{len(tx)} Buchungen aus {len(files)} Datei(en); Performance wird berechnet ...")
    perf = pf.analyze_transactions(tx)
    perf["warnings"] = issues + perf["warnings"]
    perf["transactions"] = tr.compact(tx)
    n = pf.attach_notes(perf, notes_file)
    if n:
        print(f"{n} Entscheidungsnotizen zugeordnet ({os.path.basename(str(notes_file))})")
    return perf, tx, issues


def prepare_portfolio_data(portfolio_file=None, transaction_files=None, holdings_files=None, research=None,
                           name="portfolio", title="Portfolio Review", years_hist=3, rf=0.02, cap=0.10, sector_cap=0.35,
                           run_backtest=True, prices=None, curr=None, fund=None, analysis=None, backtest=None,
                           performance=None):
    """Nur der Python-Teil des Portfolio Reviews: Performance, Analyse, Backtest; speichert Snapshot (Brief) und
    Dashboard (App). Kein Sprachmodell. Rueckgabe: (analysis, backtest, performance, tx_files, hold_files)."""
    a, bt, perf = analysis, backtest, performance
    tx_files = [transaction_files] if isinstance(transaction_files, str) else list(transaction_files or [])
    if perf is None and tx_files:
        perf, _, _ = load_performance(tx_files)
    hold_files = [holdings_files] if isinstance(holdings_files, str) else list(holdings_files or [])
    extra = []
    if hold_files:
        extra, iss = tr.read_all_holdings(hold_files)
        for i in iss:
            print("Hinweis:", i)
        print(f"{len(extra)} Positionen aus Positions-Exporten ({', '.join(os.path.basename(f) for f in hold_files)})")
        if perf is not None:
            perf["warnings"] = perf.get("warnings", []) + [
                f"Positions from {', '.join(os.path.basename(f) for f in hold_files)} have no transaction history: "
                f"included in analysis, risk and optimization, not in the realised performance"]
    if a is None:
        if portfolio_file:
            portfolio = tr.merge_positions(pe.load_portfolio(portfolio_file), extra) if extra and all(
                "shares" in x for x in pe.load_portfolio(portfolio_file)) else pe.load_portfolio(portfolio_file)
        elif perf or extra:
            portfolio = tr.merge_positions(pf.holdings_portfolio(perf) if perf else [], extra)
        else:
            raise ValueError("need portfolio_file, transaction_files or holdings_files")
        print("Analyse wird berechnet (Kurse, Risiko, Optimierung) ...")
        a = pe.analyze(portfolio, years_hist=years_hist, rf=rf, cap=cap, sector_cap=sector_cap, prices=prices,
                       curr=curr, fund=fund)
    if run_backtest and bt is None:
        print("Walk-forward-Backtest wird berechnet ...")
        sectors = [a["fund"][t]["sector"] for t in a["tickers"]]
        bt = pe.backtest(a["prices"], a["tickers"], a["weights"][a["tickers"]].values, rf=rf, cap=cap,
                         sectors=sectors, sector_cap=sector_cap)
    try:                                            # fuer den Briefing-Agenten
        from .brief_agent import save_portfolio_snapshot
        save_portfolio_snapshot(a, perf, name=name, title=title)
    except Exception as e:
        print(f"Portfolio-Snapshot nicht gespeichert: {e}")
    try:                                            # fuer das Portfolio-Dashboard (reports/site/portfolio.html)
        from .html_site import save_portfolio_data
        save_portfolio_data(a, bt, perf, {t: v for t, v in (research or {}).items() if t in set(a["tickers"])},
                            name=name, title=title)
    except Exception as e:
        print(f"Dashboard-Daten nicht gespeichert: {e}")
    return a, bt, perf, tx_files, hold_files


def run_portfolio_review(llm_config, portfolio_file=None, save_dir="reports/portfolio", name="portfolio",
                         title="Portfolio Review", years_hist=3, rf=0.02, cap=0.10, sector_cap=0.35, run_backtest=True,
                         prices=None, curr=None, fund=None, analysis=None, backtest=None, transaction_files=None,
                         performance=None, research=None, holdings_files=None):
    """Berechnet Analyse und Backtest (Python) und laesst den Agenten den Report schreiben.
    holdings_files: Positions-Exporte ohne Kaufhistorie (z. B. Smartbroker+ Depotpositionen); gehen in Analyse,
    Risiko und Optimierung ein, nicht in die Performance-Rechnung.
    analysis/backtest/performance koennen vorab berechnet uebergeben werden (spart Downloads).
    transaction_files: Broker-Exporte (Scalable, Trade Republic, Smartbroker+, Vorlage). Ohne portfolio_file wird der
    aktuelle Bestand aus den Transaktionen genommen."""
    _ROUNDS.clear()
    a, bt, perf, tx_files, hold_files = prepare_portfolio_data(
        portfolio_file, transaction_files=transaction_files, holdings_files=holdings_files, research=research,
        name=name, title=title, years_hist=years_hist, rf=rf, cap=cap, sector_cap=sector_cap, run_backtest=run_backtest,
        prices=prices, curr=curr, fund=fund, analysis=analysis, backtest=backtest, performance=performance)
    tx_files = tx_files + hold_files
    state = {"analysis": a, "backtest": bt, "performance": perf, "tx_files": tx_files, "save_dir": save_dir,
             "name": name, "title": title, "portfolio_file": portfolio_file,
             "research": {t: v for t, v in (research or {}).items() if t in set(a["tickers"])} or None}
    agent = autogen.AssistantAgent(name="Portfolio_Manager", system_message=_AS.get("portfolio.system", SYSTEM), llm_config=llm_config)
    proxy = autogen.UserProxyAgent(
        name="User_Proxy", human_input_mode="NEVER", max_consecutive_auto_reply=15, code_execution_config=False,
        is_termination_msg=lambda x: str(x.get("content") or "").rstrip().rstrip("*.").endswith("TERMINATE"))
    register_toolkits(make_tools(state), agent, proxy)
    if perf:
        msg = ("Review the portfolio. 1) Call get_portfolio_analysis, get_backtest and get_actual_performance. 2) Call "
               "build_portfolio_review with headline, summary, risk_commentary, optimization_commentary, "
               "backtest_commentary, recommendations, performance_commentary and mistakes_and_lessons. The summary "
               "must state the realised TTWROR and MWR vs the MSCI ACWI. ")
    else:
        msg = ("Review the portfolio. 1) Call get_portfolio_analysis and get_backtest. 2) Call build_portfolio_review with "
               "headline, summary, risk_commentary, optimization_commentary, backtest_commentary and recommendations. ")
    if state["research"]:
        msg += ("Also call get_research_views: the recommendations must take the thesis status, committee votes and news "
                "signals of the positions into account (e.g. weakened or broken theses, sell votes). ")
    msg += "Cite figures exactly as given and mark them [1]. If the tool returns a SELF-CHECK list, revise once and rebuild."
    msg += _AS.extra("portfolio.extra")
    try:
        proxy.initiate_chat(agent, message=msg, cache=None)
    finally:
        _save_transcript(proxy.chat_messages.get(agent, []), save_dir, name)
    pdf = os.path.join(save_dir, f"{name}_portfolio_review.pdf")
    print(f"\nPDF: {pdf}" if os.path.exists(pdf) else
          f"\nKein PDF erzeugt - Verlauf in {os.path.join(save_dir, name + '_transcript.md')} pruefen.")
    return state


def _save_transcript(messages, save_dir, name):
    """Verlauf inkl. Tool-Aufrufe und -Antworten (zur Fehlersuche)."""
    os.makedirs(save_dir, exist_ok=True)
    with open(os.path.join(save_dir, f"{name}_transcript.md"), "w", encoding="utf-8") as f:
        for m in messages:
            f.write(f"## {m.get('role')} {m.get('name') or ''}\n\n")
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                f.write(f"TOOL CALL {fn.get('name')}: {str(fn.get('arguments'))[:20000]}\n\n")
            for tr_ in m.get("tool_responses") or []:
                f.write(f"TOOL RESPONSE: {str(tr_.get('content'))[:20000]}\n\n")
            if m.get("content"):
                f.write(str(m["content"])[:20000] + "\n\n")
