"""
Konsensschaetzungen und Liquiditaet (eigene Erweiterung, nicht Teil von FinRobot).

Quelle: Yahoo Finance via yfinance. Alle Zahlen werden hier deterministisch berechnet.
Das LLM bekommt sie nur als Text (Tool-Output) und liefert selbst keine Zahlen fuer die Tabellen.

Wichtig fuer die Interpretation:
- Konsensschaetzungen und Quartalsdaten sind Stand Abruf (heute), also NACH dem 10-K.
- Forward-Multiples (P/E, EV/Sales auf Schaetzungen) nutzen den aktuellen Kurs und EV.
"""

import math
from datetime import date, datetime, timezone

import pandas as pd


def _ticker(symbol):
    """Eigene Funktion, damit Tests ein Fake-Objekt einsetzen koennen."""
    import yfinance as yf
    return yf.Ticker(symbol)


def _num(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def _get(obj, attr):
    try:
        df = getattr(obj, attr)
        return df if isinstance(df, pd.DataFrame) and not df.empty else None
    except Exception:
        return None


def _row(df, names, col):
    if df is None or col not in df.columns:
        return None
    for n in names:
        if n in df.index:
            v = _num(df.loc[n, col])
            if v is not None:
                return v
    return None


def _cell(df, idx, col):
    if df is None or idx not in df.index or col not in df.columns:
        return None
    return _num(df.loc[idx, col])


CASH = ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"]
DEBT = ["Total Debt"]
FCF = ["Free Cash Flow"]
OCF = ["Operating Cash Flow"]
CAPEX = ["Capital Expenditure"]
CA = ["Current Assets"]
CL = ["Current Liabilities"]
SHARES = ["Ordinary Shares Number", "Share Issued"]


# --------------------------------------------------------------- Konsens
def _label_current_fy(t, rev):
    """Welches Geschaeftsjahr ist '0y'? Abgleich yearAgoRevenue mit den Ist-Umsaetzen, sonst Yahoo-Info."""
    inc = _get(t, "income_stmt")
    ya = _cell(rev, "0y", "yearAgoRevenue")
    if inc is not None and ya and "Total Revenue" in inc.index:
        for c in inc.columns:
            v = _num(inc.loc["Total Revenue", c])
            if v and abs(v - ya) / abs(v) < 0.03:
                return pd.Timestamp(c).year + 1
    try:
        lfy = (t.info or {}).get("lastFiscalYearEnd")
        if lfy:
            return datetime.fromtimestamp(int(lfy), tz=timezone.utc).year + 1
    except Exception:
        pass
    return None


def get_consensus(symbol, last_fy=None):
    """
    Konsens fuer das laufende und das naechste Geschaeftsjahr.
    Rueckgabe: {"years": [{"fy", "rev", "rev_low", "rev_high", "rev_n", "growth", "eps", "eps_low", "eps_high",
                "eps_n", "pe", "ev_sales"}], "methodology", "price", "error"}; Geldbetraege in Mio.
    """
    out = {"years": [], "methodology": None, "price": None, "error": None}
    t = _ticker(symbol)
    rev, eps = _get(t, "revenue_estimate"), _get(t, "earnings_estimate")
    if rev is None and eps is None:
        out["error"] = "no consensus estimates available on Yahoo Finance"
        return out
    fy0 = _label_current_fy(t, rev)
    if fy0 is None:
        out["error"] = "fiscal year of the consensus estimates could not be determined"
        return out
    if last_fy is not None and fy0 != int(last_fy) + 1:
        out["error"] = (f"consensus estimates refer to FY{fy0} onwards and do not follow directly on the analyzed "
                        f"FY{last_fy}; omitted")
        return out
    try:
        info = t.info or {}
    except Exception:
        info = {}
    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    ev = _num(info.get("enterpriseValue"))
    out["price"] = price
    if eps is not None and "methodology" in eps.columns:
        out["methodology"] = str(eps["methodology"].dropna().iloc[0]) if eps["methodology"].notna().any() else None
    for k, fy in (("0y", fy0), ("+1y", fy0 + 1)):
        r = _cell(rev, k, "avg")
        e = _cell(eps, k, "avg")
        if r is None and e is None:
            continue
        mn = lambda v: None if v is None else v / 1e6
        y = {"fy": fy, "rev": mn(r), "rev_low": mn(_cell(rev, k, "low")), "rev_high": mn(_cell(rev, k, "high")),
             "rev_n": _cell(rev, k, "numberOfAnalysts"), "growth": _cell(rev, k, "growth"),
             "eps": e, "eps_low": _cell(eps, k, "low"), "eps_high": _cell(eps, k, "high"),
             "eps_n": _cell(eps, k, "numberOfAnalysts")}
        y["pe"] = price / e if price and e and e > 0 else None
        y["ev_sales"] = ev / r if ev and r and r > 0 else None
        out["years"].append(y)
    # Wachstum des +1y-Jahres gegen 0y, falls Yahoo keins liefert
    if len(out["years"]) == 2 and out["years"][1]["growth"] is None and out["years"][0]["rev"] and out["years"][1]["rev"]:
        out["years"][1]["growth"] = out["years"][1]["rev"] / out["years"][0]["rev"] - 1
    if not out["years"]:
        out["error"] = "no annual consensus estimates available on Yahoo Finance"
    return out


# --------------------------------------------------------------- Liquiditaet
def _fcf(cf, col):
    v = _row(cf, FCF, col)
    if v is None:
        o, c = _row(cf, OCF, col), _row(cf, CAPEX, col)
        v = o + c if o is not None and c is not None else None
    return v


def _liq_column(bs, col, fcf, shares_prev):
    cash, debt = _row(bs, CASH, col), _row(bs, DEBT, col)
    ca, cl = _row(bs, CA, col), _row(bs, CL, col)
    shares = _row(bs, SHARES, col)
    mn = lambda v: None if v is None else v / 1e6
    d = {"cash": mn(cash), "debt": mn(debt),
         "net_cash": mn(cash - debt) if cash is not None and debt is not None else None,
         "fcf": mn(fcf), "current_ratio": ca / cl if ca and cl else None,
         "shares": mn(shares),
         "share_change": shares / shares_prev - 1 if shares and shares_prev else None}
    if fcf is None or cash is None:
        d["runway"] = None
    elif fcf < 0:
        d["runway"] = cash / -fcf
    else:
        d["runway"] = "self-funded"
    return d


def get_liquidity(symbol, fy=None):
    """
    Liquiditaet zum Geschaeftsjahresende (10-K) und, falls neuer, zum letzten Quartal.
    Rueckgabe: {"columns": [(label, dict)], "error"}; Betraege und Aktien in Mio., FCF beim Quartal = TTM.
    """
    out = {"columns": [], "error": None}
    t = _ticker(symbol)
    bs, cf = _get(t, "balance_sheet"), _get(t, "cashflow")
    if bs is None:
        out["error"] = "no balance sheet data on Yahoo Finance"
        return out
    cols = sorted(bs.columns)
    pick = [c for c in cols if fy is None or pd.Timestamp(c).year == int(fy)]
    if not pick:
        out["error"] = f"no balance sheet for FY{fy} on Yahoo Finance"
        return out
    c = pick[-1]
    prev = [p for p in cols if pd.Timestamp(p).year == pd.Timestamp(c).year - 1]
    shares_prev = _row(bs, SHARES, prev[-1]) if prev else None
    out["columns"].append((f"FY{pd.Timestamp(c).year} (10-K)",
                           _liq_column(bs, c, _fcf(cf, c) if cf is not None and c in cf.columns else None, shares_prev)))

    qbs, qcf = _get(t, "quarterly_balance_sheet"), _get(t, "quarterly_cashflow")
    if qbs is not None:
        cq = max(qbs.columns)
        if pd.Timestamp(cq) > pd.Timestamp(c) + pd.Timedelta(days=20):
            ttm = None
            if qcf is not None:
                last4 = [q for q in sorted(qcf.columns, reverse=True) if pd.Timestamp(q) <= pd.Timestamp(cq)][:4]
                vals = [_fcf(qcf, q) for q in last4]
                if len(vals) == 4 and all(v is not None for v in vals):
                    ttm = sum(vals)
            year_ago = [q for q in qbs.columns
                        if abs((pd.Timestamp(cq) - pd.Timedelta(days=365) - pd.Timestamp(q)).days) <= 45]
            sp = _row(qbs, SHARES, year_ago[0]) if year_ago else None
            out["columns"].append((f"Latest quarter ({pd.Timestamp(cq).date()})", _liq_column(qbs, cq, ttm, sp)))
    return out


# --------------------------------------------------------------- Reverse DCF
DCF_YEARS = 10
TERMINAL_GROWTH = 0.025
ERP = 0.05


def _risk_free():
    """Rendite 10-jaehriger US-Staatsanleihen (^TNX), sonst 4.25 %."""
    try:
        h = _ticker("^TNX").history(period="10d")
        v = _num(h["Close"].dropna().iloc[-1])
        if v and 0.5 < v < 15:
            return v / 100, "10y US Treasury (^TNX)"
    except Exception:
        pass
    return 0.0425, "assumed 4.25%"


def _dcf_value(rev0, m0, m_target, g, wacc, years=DCF_YEARS, tg=TERMINAL_GROWTH):
    """Barwert der FCF: Umsatz waechst konstant mit g, FCF-Marge laeuft linear von m0 zu m_target."""
    pv, r = 0.0, rev0
    for t in range(1, years + 1):
        r *= 1 + g
        m = m0 + (m_target - m0) * t / years
        pv += r * m / (1 + wacc) ** t
    tv = r * m_target * (1 + tg) / (wacc - tg)
    return pv + tv / (1 + wacc) ** years


def _solve_growth(ev, rev0, m0, m_target, wacc, lo=-0.30, hi=1.00):
    f = lambda g: _dcf_value(rev0, m0, m_target, g, wacc) - ev
    if f(lo) > 0:
        return f"< {lo * 100:.0f}%"
    if f(hi) < 0:
        return f"> {hi * 100:.0f}%"
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if f(mid) < 0 else (lo, mid)
    return (lo + hi) / 2


def reverse_dcf(symbol, fy=None):
    """
    Welches konstante Umsatzwachstum ueber 10 Jahre rechtfertigt den aktuellen Unternehmenswert?
    Vereinfachungen (bewusst): WACC = risikofreier Zins + Beta x 5 % (nur Eigenkapital), FCF-Marge laeuft
    linear vom letzten Geschaeftsjahr zur Zielmarge, ewiges Wachstum 2.5 %.
    """
    out = {"error": None}
    t = _ticker(symbol)
    inc, cf = _get(t, "income_stmt"), _get(t, "cashflow")
    try:
        info = t.info or {}
    except Exception:
        info = {}
    if inc is None or "Total Revenue" not in inc.index:
        out["error"] = "no revenue data"
        return out
    cols = [c for c in sorted(inc.columns) if _num(inc.loc["Total Revenue", c])]
    pick = [c for c in cols if fy is None or pd.Timestamp(c).year == int(fy)]
    if not pick:
        out["error"] = f"no revenue for FY{fy}"
        return out
    c = pick[-1]
    rev0 = _num(inc.loc["Total Revenue", c])
    fcf = _fcf(cf, c) if cf is not None and c in cf.columns else None
    ev = _num(info.get("enterpriseValue"))
    if ev is None or ev <= 0 or fcf is None:
        out["error"] = "enterprise value or free cash flow not available"
        return out
    rf, rf_src = _risk_free()
    beta_raw = _num(info.get("beta"))
    beta = min(max(beta_raw if beta_raw else 1.2, 0.6), 2.5)
    wacc = min(max(rf + beta * ERP, 0.07), 0.15)
    m0 = fcf / rev0
    m_target = m0 if m0 > 0.15 else 0.15
    m_target = min(m_target, 0.45)
    g = _solve_growth(ev, rev0, m0, m_target, wacc)
    # Historisches 3-Jahres-Wachstum
    hist = None
    prev = [p for p in cols if pd.Timestamp(p).year == pd.Timestamp(c).year - 3]
    if prev:
        r3 = _num(inc.loc["Total Revenue", prev[-1]])
        hist = (rev0 / r3) ** (1 / 3) - 1 if r3 and r3 > 0 else None
    margins = [0.10, 0.15, 0.20, 0.25, 0.30]
    if all(abs(m_ - m_target) > 1e-9 for m_ in margins):
        nearest = min(margins, key=lambda m_: abs(m_ - m_target))
        margins = sorted([m_ for m_ in margins if m_ != nearest] + [m_target])
    waccs = [wacc + d for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    grid = [[_solve_growth(ev, rev0, m0, m_, w_) for w_ in waccs] for m_ in margins]
    out.update({"fy": pd.Timestamp(c).year, "ev": ev / 1e6, "rev0": rev0 / 1e6, "fcf0": fcf / 1e6, "m0": m0,
                "m_target": m_target, "rf": rf, "rf_src": rf_src, "beta": beta, "beta_raw": beta_raw, "wacc": wacc,
                "tg": TERMINAL_GROWTH, "years": DCF_YEARS, "implied_g": g, "hist_cagr3": hist,
                "rev_end": rev0 / 1e6 * (1 + g) ** DCF_YEARS if isinstance(g, float) else None,
                "grid_margins": margins, "grid_waccs": waccs, "grid": grid})
    return out


def fmt_g(v):
    return v if isinstance(v, str) else ("n/a" if v is None else f"{v * 100:.1f}%")


# --------------------------------------------------------------- Implizite Rendite (IRR)
def implied_irr(symbol, fy=None):
    """
    Welche jaehrliche Rendite erhaelt ein Kaeufer zum aktuellen Unternehmenswert, wenn der Konsens eintrifft?
    Jahre 1-2: Konsensumsatz; danach sinkt das Wachstum linear bis Jahr 10 auf 2.5 %;
    FCF-Marge wie im Reverse DCF (linear zur Zielmarge); Endwert mit 2.5 % ewigem Wachstum.
    """
    out = {"error": None}
    rd = reverse_dcf(symbol, fy)
    if rd.get("error"):
        out["error"] = rd["error"]
        return out
    con = get_consensus(symbol, last_fy=rd["fy"])
    ys = [y for y in con.get("years", []) if y.get("rev")]
    if len(ys) < 2:
        out["error"] = con.get("error") or "consensus revenue for two years not available"
        return out
    rev = [ys[0]["rev"], ys[1]["rev"]]
    g2 = ys[1]["rev"] / ys[0]["rev"] - 1
    n = DCF_YEARS
    for t_ in range(3, n + 1):
        g = g2 + (TERMINAL_GROWTH - g2) * (t_ - 2) / (n - 2)
        rev.append(rev[-1] * (1 + g))
    m0, mt = rd["m0"], rd["m_target"]
    fcf = [r * (m0 + (mt - m0) * (i + 1) / n) for i, r in enumerate(rev)]
    ev = rd["ev"]

    def pv(r):
        v = sum(f / (1 + r) ** (i + 1) for i, f in enumerate(fcf))
        return v + fcf[-1] * (1 + TERMINAL_GROWTH) / (r - TERMINAL_GROWTH) / (1 + r) ** n

    lo, hi = TERMINAL_GROWTH + 0.005, 0.60
    if pv(lo) < ev:
        irr = f"< {lo * 100:.1f}%"
    elif pv(hi) > ev:
        irr = f"> {hi * 100:.0f}%"
    else:
        for _ in range(80):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if pv(mid) > ev else (lo, mid)
        irr = (lo + hi) / 2
    out.update({"irr": irr, "wacc": rd["wacc"], "rev_path": rev, "g_year2": g2, "fy": rd["fy"],
                "spread": irr - rd["wacc"] if isinstance(irr, float) else None})
    return out


# --------------------------------------------------------------- Revisionen und Ueberraschungen
def estimate_momentum(symbol):
    """EPS-Revisionen (Konsens heute vs. vor 30/90 Tagen, Anzahl Anhebungen/Senkungen) und Ueberraschungen."""
    out = {"error": None, "trend": [], "surprises": []}
    t = _ticker(symbol)
    tr, rv, hist = _get(t, "eps_trend"), _get(t, "eps_revisions"), _get(t, "earnings_history")
    for k, label in (("0y", "current fiscal year"), ("+1y", "next fiscal year")):
        cur, d30, d90 = _cell(tr, k, "current"), _cell(tr, k, "30daysAgo"), _cell(tr, k, "90daysAgo")
        if cur is None:
            continue
        out["trend"].append({"period": label, "current": cur, "d30": d30, "d90": d90,
                             "d7": _cell(tr, k, "7daysAgo"), "d60": _cell(tr, k, "60daysAgo"),
                             "up30": _cell(rv, k, "upLast30days"), "down30": _cell(rv, k, "downLast30days")})
    if hist is not None:
        h = hist.sort_index(ascending=False).head(4)
        for idx, r in h.iterrows():
            est, act = _num(r.get("epsEstimate")), _num(r.get("epsActual"))
            if est is None and act is None:
                continue
            sp = _num(r.get("surprisePercent"))
            if sp is not None and abs(sp) > 3:  # falls Yahoo Prozentpunkte statt Anteil liefert
                sp = sp / 100
            out["surprises"].append({"quarter": str(pd.Timestamp(idx).date()) if not isinstance(idx, str) else idx,
                                     "estimate": est, "actual": act, "surprise": sp})
    if not out["trend"] and not out["surprises"]:
        out["error"] = "no estimate revisions or earnings history on Yahoo Finance"
    return out


# --------------------------------------------------------------- Qualitaets-Scores
def _r(df, names, col):
    return _row(df, names if isinstance(names, list) else [names], col)


def quality_scores(symbol, fy=None):
    """
    Piotroski F-Score (0-9), Altman Z-Score (Originalformel) und Beneish M-Score aus den Jahresabschluessen
    (Yahoo Finance). Fehlende Posten -> Kriterium 'n/a', Score ueber die verfuegbaren Kriterien.
    """
    out = {"error": None}
    t = _ticker(symbol)
    inc, bs, cf = _get(t, "income_stmt"), _get(t, "balance_sheet"), _get(t, "cashflow")
    if inc is None or bs is None:
        out["error"] = "financial statements not available"
        return out
    cols = sorted(c for c in bs.columns if c in inc.columns)
    pick = [c for c in cols if fy is None or pd.Timestamp(c).year == int(fy)]
    if not pick:
        out["error"] = f"statements for FY{fy} not available"
        return out
    c = pick[-1]
    prev = [p for p in cols if pd.Timestamp(p).year == pd.Timestamp(c).year - 1]
    if not prev:
        out["error"] = "prior-year statements not available"
        return out
    p = prev[-1]
    cfc = (lambda col: _row(cf, OCF, col) if cf is not None and col in cf.columns else None)

    def v(df, names, col):
        return _r(df, names, col)

    TA = ["Total Assets"]
    NI = ["Net Income", "Net Income Common Stockholders"]
    LTD = ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"]
    REV = ["Total Revenue"]
    GP = ["Gross Profit"]
    COGS = ["Cost Of Revenue"]
    ta1, ta0 = v(bs, TA, c), v(bs, TA, p)
    ni1, ni0 = v(inc, NI, c), v(inc, NI, p)
    cfo1 = cfc(c)
    rev1, rev0 = v(inc, REV, c), v(inc, REV, p)

    def ratio(a, b):
        return a / b if a is not None and b not in (None, 0) else None

    roa1, roa0 = ratio(ni1, ta1), ratio(ni0, ta0)
    lev1, lev0 = ratio(v(bs, LTD, c) or 0.0, ta1), ratio(v(bs, LTD, p) or 0.0, ta0)
    cr1, cr0 = ratio(v(bs, CA, c), v(bs, CL, c)), ratio(v(bs, CA, p), v(bs, CL, p))
    sh1, sh0 = v(bs, SHARES, c), v(bs, SHARES, p)
    gm1, gm0 = ratio(v(inc, GP, c), rev1), ratio(v(inc, GP, p), rev0)
    at1, at0 = ratio(rev1, ta1), ratio(rev0, ta0)  # Umsatz / Bilanzsumme

    def test(name, a, b, op):
        if a is None or b is None:
            return {"criterion": name, "pass": None}
        return {"criterion": name, "pass": bool(op(a, b))}

    crit = [
        test("Return on assets > 0", roa1, 0, lambda a, b: a > b),
        test("Operating cash flow > 0", cfo1, 0, lambda a, b: a > b),
        test("Return on assets improved", roa1, roa0, lambda a, b: a > b),
        test("Operating cash flow > net income", cfo1, ni1, lambda a, b: a > b),
        test("Leverage (long-term debt / assets) lower", lev1, lev0, lambda a, b: a < b),
        test("Current ratio improved", cr1, cr0, lambda a, b: a > b),
        test("No increase in share count", sh1, sh0, lambda a, b: a <= b * 1.005),
        test("Gross margin improved", gm1, gm0, lambda a, b: a > b),
        test("Asset turnover improved", at1, at0, lambda a, b: a > b),
    ]
    avail = [x for x in crit if x["pass"] is not None]
    out["piotroski"] = {"score": sum(x["pass"] for x in avail), "available": len(avail), "criteria": crit}

    # Altman Z (Originalformel, Marktwert des Eigenkapitals = aktuelle Marktkapitalisierung)
    try:
        info = t.info or {}
    except Exception:
        info = {}
    wc = v(bs, ["Working Capital"], c)
    if wc is None and v(bs, CA, c) is not None and v(bs, CL, c) is not None:
        wc = v(bs, CA, c) - v(bs, CL, c)
    re_ = v(bs, ["Retained Earnings"], c)
    ebit = v(inc, ["EBIT", "Operating Income"], c)
    tl = v(bs, ["Total Liabilities Net Minority Interest", "Total Liabilities"], c)
    mve = _num(info.get("marketCap"))
    parts = [wc, re_, ebit, mve, tl, rev1, ta1]
    if all(x is not None for x in parts) and ta1 and tl:
        z = 1.2 * wc / ta1 + 1.4 * re_ / ta1 + 3.3 * ebit / ta1 + 0.6 * mve / tl + 1.0 * rev1 / ta1
        zone = "safe" if z > 2.99 else ("grey" if z >= 1.81 else "distress")
        out["altman"] = {"z": z, "zone": zone}
    else:
        out["altman"] = None

    # Beneish M-Score (8 Variablen)
    rec1, rec0 = v(bs, ["Accounts Receivable", "Receivables"], c), v(bs, ["Accounts Receivable", "Receivables"], p)
    cogs1, cogs0 = v(inc, COGS, c), v(inc, COGS, p)
    ppe1, ppe0 = v(bs, ["Net PPE"], c), v(bs, ["Net PPE"], p)
    ca1, ca0 = v(bs, CA, c), v(bs, CA, p)
    dep1 = v(cf, ["Depreciation And Amortization", "Depreciation Amortization Depletion"], c) if cf is not None else None
    dep0 = v(cf, ["Depreciation And Amortization", "Depreciation Amortization Depletion"], p) if cf is not None else None
    sga1, sga0 = v(inc, ["Selling General And Administration"], c), v(inc, ["Selling General And Administration"], p)
    cl1, cl0 = v(bs, CL, c), v(bs, CL, p)
    ltd1, ltd0 = v(bs, LTD, c) or 0.0, v(bs, LTD, p) or 0.0
    try:
        dsri = (rec1 / rev1) / (rec0 / rev0)
        gmi = ((rev0 - cogs0) / rev0) / ((rev1 - cogs1) / rev1)
        aqi = (1 - (ca1 + ppe1) / ta1) / (1 - (ca0 + ppe0) / ta0)
        sgi = rev1 / rev0
        depi = (dep0 / (dep0 + ppe0)) / (dep1 / (dep1 + ppe1))
        sgai = (sga1 / rev1) / (sga0 / rev0)
        lvgi = ((cl1 + ltd1) / ta1) / ((cl0 + ltd0) / ta0)
        tata = (ni1 - cfo1) / ta1
        m = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi
             - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
        out["beneish"] = {"m": m, "flag": m > -1.78}
    except (TypeError, ZeroDivisionError):
        out["beneish"] = None
    out["fy"] = pd.Timestamp(c).year
    return out


# --------------------------------------------------------------- Formatierung
def fmt_mn(v, dec=1):
    if v is None:
        return "n/a"
    return f"({abs(v):,.{dec}f})" if v < 0 else f"{v:,.{dec}f}"


def fmt_runway(v):
    if v is None:
        return "n/a"
    if isinstance(v, str):
        return v
    return f"{v:.1f} years"


def fmt_pct(v, sign=True):
    return "n/a" if v is None else (f"{v * 100:+.1f}%" if sign else f"{v * 100:.1f}%")


def _money(v):
    if v is None:
        return "n/a"
    return f"-${abs(v):,.1f} million" if v < 0 else f"${v:,.1f} million"


def _usd(v):
    return "n/a" if v is None else (f"-${abs(v):.2f}" if v < 0 else f"${v:.2f}")


def _x(v, empty="n/a"):
    return empty if v is None else f"{v:.1f}x"


def _shares(v):
    return "n/a" if v is None else f"{v:,.1f} million"


def outlook_text(symbol, fyear):
    """Text fuer den Agenten: Konsens [3] und Liquiditaet [2]."""
    today = date.today().isoformat()
    lines = []
    try:
        con = get_consensus(symbol, last_fy=int(fyear))
    except Exception as e:
        con = {"years": [], "error": f"error: {e}"}
    lines.append(f"CONSENSUS ESTIMATES (Yahoo Finance, retrieved {today}, i.e. after the 10-K filing; cite as [3]):")
    if con["error"]:
        lines.append(f"- not available: {con['error']}. Do not state any estimates.")
    for y in con["years"]:
        n = f", {int(y['rev_n'])} analysts" if y["rev_n"] else ""
        rng = f" (range {_money(y['rev_low'])} to {_money(y['rev_high'])}{n})" if y["rev_low"] is not None else ""
        eps = _usd(y["eps"])
        erng = (f" (range {_usd(y['eps_low'])} to {_usd(y['eps_high'])})"
                if y["eps_low"] is not None and y["eps_high"] is not None else "")
        lines.append(
            f"- FY{y['fy']}E: revenue {_money(y['rev'])}{rng}, growth {fmt_pct(y['growth'])}; EPS {eps}{erng}; "
            f"forward P/E {_x(y['pe'], 'n/m')}; EV/Sales {_x(y['ev_sales'])}")
    if con.get("price"):
        lines.append(f"- Forward multiples use the current share price of ${con['price']:.2f} and the current "
                     f"enterprise value. EPS methodology: {con.get('methodology') or 'Yahoo default'}.")
    try:
        liq = get_liquidity(symbol, fy=int(fyear))
    except Exception as e:
        liq = {"columns": [], "error": f"error: {e}"}
    lines.append("")
    lines.append("LIQUIDITY AND FUNDING (Yahoo Finance balance sheet and cash flow; cite as [2]):")
    if liq["error"]:
        lines.append(f"- not available: {liq['error']}")
    for label, d in liq["columns"]:
        fcf_label = "TTM free cash flow" if label.startswith("Latest") else "free cash flow"
        lines.append(
            f"- {label}: cash and short-term investments {_money(d['cash'])}, total debt {_money(d['debt'])}, "
            f"net cash {_money(d['net_cash'])}, {fcf_label} {_money(d['fcf'])}, "
            f"cash runway at that burn {fmt_runway(d['runway'])}, current ratio "
            f"{_x(d['current_ratio'])}, shares outstanding {_shares(d['shares'])}, change in share count y/y "
            f"{fmt_pct(d['share_change'])}")
    lines.append("")
    lines.append("REVERSE DCF (own calculation from Yahoo Finance data [2][3]; current enterprise value, i.e. after the 10-K):")
    try:
        r = reverse_dcf(symbol, fy=int(fyear))
    except Exception as e:
        r = {"error": f"error: {e}"}
    if r.get("error"):
        lines.append(f"- not available: {r['error']}")
    else:
        lines.append(
            f"- The current enterprise value of {_money(r['ev'])} implies revenue growth of {fmt_g(r['implied_g'])} per year "
            f"for {r['years']} years (FY{r['fy']} revenue {_money(r['rev0'])}"
            + (f" -> about {_money(r['rev_end'])} in FY{r['fy'] + r['years']}" if r["rev_end"] else "") + "), "
            f"assuming the free cash flow margin moves from {fmt_pct(r['m0'], sign=False)} to {fmt_pct(r['m_target'], sign=False)} "
            f"by year {r['years']}, a WACC of {fmt_pct(r['wacc'], sign=False)} ({r['rf_src']} {fmt_pct(r['rf'], sign=False)} + beta "
            f"{r['beta']:.2f} x 5.0% equity risk premium) and {fmt_pct(r['tg'], sign=False)} terminal growth.")
        lines.append(f"- For comparison: historical 3-year revenue CAGR {fmt_g(r['hist_cagr3'])}. "
                     "Compare the implied growth with the consensus growth above and with the historical growth. "
                     "This is a simplified, illustrative model, not a price target.")
    try:
        ir = implied_irr(symbol, fy=int(fyear))
    except Exception as e:
        ir = {"error": str(e)}
    if not ir.get("error"):
        sp = "" if ir["spread"] is None else f" ({ir['spread'] * 100:+.1f} percentage points vs the WACC)"
        lines.append(f"- Implied return (IRR): buying at the current enterprise value and assuming consensus revenue for "
                     f"two years, growth fading to 2.5% by year 10 and the same margin path yields {fmt_g(ir['irr'])} "
                     f"per year{sp}.")
    lines.append("")
    lines.append("ESTIMATE REVISIONS AND EARNINGS SURPRISES (Yahoo Finance, retrieved today; cite as [3]):")
    try:
        mo = estimate_momentum(symbol)
    except Exception as e:
        mo = {"error": str(e), "trend": [], "surprises": []}
    if mo["error"]:
        lines.append(f"- not available: {mo['error']}")
    for tr_ in mo["trend"]:
        ch = "" if not tr_["d90"] else f", change vs 90 days ago {((tr_['current'] - tr_['d90']) / abs(tr_['d90'])) * 100:+.1f}%"
        lines.append(f"- EPS consensus {tr_['period']}: {_usd(tr_['current'])} today, {_usd(tr_['d30'])} 30 days ago, "
                     f"{_usd(tr_['d90'])} 90 days ago{ch}; analysts raising/cutting in last 30 days: "
                     f"{int(tr_['up30'] or 0)}/{int(tr_['down30'] or 0)}")
    for su_ in mo["surprises"]:
        sp_ = "n/a" if su_["surprise"] is None else f"{su_['surprise'] * 100:+.1f}%"
        lines.append(f"- Quarter ending {su_['quarter']}: EPS {_usd(su_['actual'])} vs estimate {_usd(su_['estimate'])} "
                     f"(surprise {sp_})")
    lines.append("")
    lines.append("FINANCIAL QUALITY SCORES (own calculation from Yahoo Finance statements; cite as [2]):")
    try:
        q = quality_scores(symbol, fy=int(fyear))
    except Exception as e:
        q = {"error": str(e)}
    if q.get("error"):
        lines.append(f"- not available: {q['error']}")
    else:
        pi = q["piotroski"]
        failed = [x["criterion"] for x in pi["criteria"] if x["pass"] is False]
        lines.append(f"- Piotroski F-Score: {pi['score']} of {pi['available']} available criteria"
                     + (f"; failed: {', '.join(failed)}" if failed else ""))
        if q["altman"]:
            lines.append(f"- Altman Z-Score: {q['altman']['z']:.2f} ({q['altman']['zone']} zone; >2.99 safe, <1.81 distress; "
                         "designed for manufacturers, less reliable for young growth companies)")
        if q["beneish"]:
            lines.append(f"- Beneish M-Score: {q['beneish']['m']:.2f} ("
                         + ("above -1.78: statistical warning sign for earnings manipulation; not proof" if q["beneish"]["flag"]
                            else "below -1.78: no statistical warning sign") + ")")
    lines.append("")
    lines.append("Note: the latest-quarter column and all consensus figures are dated after the 10-K. "
                 "Say so when you use them.")
    return "\n".join(lines)
