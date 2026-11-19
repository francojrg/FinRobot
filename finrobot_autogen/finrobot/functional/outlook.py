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
    lines.append("Note: the latest-quarter column and all consensus figures are dated after the 10-K. "
                 "Say so when you use them.")
    return "\n".join(lines)
