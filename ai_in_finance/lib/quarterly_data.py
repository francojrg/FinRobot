"""
Daten fuer den Earnings & Thesis Reviewer (eigene Erweiterung).

Alles hier ist deterministisch (Python rechnet, kein LLM):
- Scorecard: Kennzahlen des letzten Quartals vs. Vorjahresquartal und vs. Geschaeftsjahr aus dem 10-K,
  mit Richtung (gut/schlecht je nach Kennzahl).
- Pressemitteilung zu den Quartalszahlen: 8-K mit Item 2.02, Anhang 99.1, kostenlos ueber SEC EDGAR.
- 10-Q-Abschnitte (MD&A, Risikofaktoren): ueber sec-api (je 1 Call, danach Cache).
- Ausgangsbasis: Key Takeaways, Summary und Risiken aus dem letzten Annual Report des Agenten.
"""
import glob
import json
import os
import re
from html import unescape
from pathlib import Path

import pandas as pd

AIF = Path(__file__).resolve().parents[1]


def _ticker(symbol):
    import yfinance as yf
    return yf.Ticker(symbol)


def _num(x):
    try:
        f = float(x)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _row(df, names, col):
    if df is None or df.empty or col not in df.columns:
        return None
    for n in names:
        if n in df.index:
            v = _num(df.loc[n, col])
            if v is not None:
                return v
    return None


def _get(t, attr):
    try:
        df = getattr(t, attr)
        return df if isinstance(df, pd.DataFrame) and not df.empty else None
    except Exception:
        return None


REV = ["Total Revenue", "Operating Revenue"]
GP = ["Gross Profit"]
OPINC = ["Operating Income", "EBIT"]
OPEX = ["Operating Expense", "Total Operating Expenses"]
NI = ["Net Income", "Net Income Common Stockholders"]
OCF = ["Operating Cash Flow"]
CAPEX = ["Capital Expenditure"]
FCF = ["Free Cash Flow"]
CASH = ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"]
DEBT = ["Total Debt"]
CA, CL = ["Current Assets"], ["Current Liabilities"]
AR = ["Accounts Receivable", "Receivables"]
SHARES = ["Ordinary Shares Number", "Share Issued"]
EPS = ["Diluted EPS", "Basic EPS"]

# Kennzahl -> (Einheit, welche Richtung ist gut, Schwelle fuer "stabil")
METRICS = [
    ("Revenue growth y/y", "pct", "up", 0.02),
    ("Gross margin", "pct", "up", 0.005),
    ("Operating margin", "pct", "up", 0.01),
    ("Opex in % of revenue", "pct", "down", 0.01),
    ("Net margin", "pct", "up", 0.01),
    ("Free cash flow margin", "pct", "up", 0.02),
    ("Diluted EPS", "usd", "up", 0.005),
    ("Cash and short-term investments", "mn", "up", 0.03),
    ("Net cash (debt)", "mn", "up", 0.03),
    ("Current ratio", "x", "up", 0.05),
    ("Days sales outstanding", "days", "down", 2.0),
    ("Share count", "mn", "down", 0.005),
]


def _fcf(cf, col):
    v = _row(cf, FCF, col)
    if v is None:
        o, c = _row(cf, OCF, col), _row(cf, CAPEX, col)
        v = o + c if o is not None and c is not None else None
    return v


def _period_metrics(inc, bs, cf, col, prev_rev=None, days=91):
    rev = _row(inc, REV, col)
    d = {}
    if rev:
        gp, op, ni = _row(inc, GP, col), _row(inc, OPINC, col), _row(inc, NI, col)
        opex = _row(inc, OPEX, col)
        f = _fcf(cf, col) if cf is not None and col in cf.columns else None
        d["Revenue"] = rev / 1e6
        d["Revenue growth y/y"] = rev / prev_rev - 1 if prev_rev else None
        d["Gross margin"] = gp / rev if gp is not None else None
        d["Operating margin"] = op / rev if op is not None else None
        d["Opex in % of revenue"] = opex / rev if opex is not None else None
        d["Net margin"] = ni / rev if ni is not None else None
        d["Free cash flow margin"] = f / rev if f is not None else None
        ar = _row(bs, AR, col) if bs is not None and col in bs.columns else None
        d["Days sales outstanding"] = ar / rev * days if ar is not None else None
    d["Diluted EPS"] = _row(inc, EPS, col)
    if bs is not None and col in bs.columns:
        cash, debt = _row(bs, CASH, col), _row(bs, DEBT, col)
        d["Cash and short-term investments"] = cash / 1e6 if cash is not None else None
        d["Net cash (debt)"] = (cash - debt) / 1e6 if cash is not None and debt is not None else None
        ca, cl = _row(bs, CA, col), _row(bs, CL, col)
        d["Current ratio"] = ca / cl if ca and cl else None
        sh = _row(bs, SHARES, col)
        d["Share count"] = sh / 1e6 if sh else None
    return d


def _assess(metric, now, before):
    unit, good, thr = next((u, g, t) for m, u, g, t in METRICS if m == metric)
    if now is None or before is None:
        return None, "n/a"
    diff = now - before
    rel = diff if unit in ("pct", "usd", "days") else (diff / abs(before) if before else 0)
    if unit == "x":
        rel = diff
    if abs(rel) < thr:
        return 0, "stable"
    up = diff > 0
    return (1 if up else -1), ("better" if (up and good == "up") or (not up and good == "down") else "worse")


def quarterly_scorecard(symbol, fyear=None):
    """
    Letztes Quartal vs. Vorjahresquartal (gleiche Saison) und vs. Geschaeftsjahr aus dem 10-K.
    Rueckgabe: {"quarter", "year_ago", "fy", "rows": [{metric, unit, fy, year_ago, quarter, dir, verdict}], "error"}
    """
    out = {"error": None, "rows": []}
    t = _ticker(symbol)
    qi, qb, qc = _get(t, "quarterly_income_stmt"), _get(t, "quarterly_balance_sheet"), _get(t, "quarterly_cashflow")
    ai, ab, ac = _get(t, "income_stmt"), _get(t, "balance_sheet"), _get(t, "cashflow")
    if qi is None:
        out["error"] = "no quarterly statements on Yahoo Finance"
        return out
    qcols = sorted(c for c in qi.columns if _row(qi, REV, c))
    if not qcols:
        out["error"] = "no quarterly revenue on Yahoo Finance"
        return out
    q = qcols[-1]
    ya = [c for c in qcols if abs((pd.Timestamp(q) - pd.Timedelta(days=365) - pd.Timestamp(c)).days) <= 45]
    q4 = ya[0] if ya else None
    q8 = None
    if q4 is not None:
        y2 = [c for c in qcols if abs((pd.Timestamp(q4) - pd.Timedelta(days=365) - pd.Timestamp(c)).days) <= 45]
        q8 = y2[0] if y2 else None
    now = _period_metrics(qi, qb, qc, q, prev_rev=_row(qi, REV, q4) if q4 is not None else None)
    before = _period_metrics(qi, qb, qc, q4, prev_rev=_row(qi, REV, q8) if q8 is not None else None) if q4 is not None else {}
    fyd, fy_label = {}, None
    if ai is not None:
        acols = sorted(c for c in ai.columns if _row(ai, REV, c))
        if fyear is not None:
            acols = [c for c in acols if pd.Timestamp(c).year <= int(fyear)]
        if acols:
            fc = acols[-1]
            prev = [c for c in acols if pd.Timestamp(c).year == pd.Timestamp(fc).year - 1]
            fyd = _period_metrics(ai, ab, ac, fc, prev_rev=_row(ai, REV, prev[-1]) if prev else None, days=365)
            fy_label = f"FY{pd.Timestamp(fc).year}"
    for metric, unit, good, thr in METRICS:
        n, b = now.get(metric), before.get(metric)
        d, verdict = _assess(metric, n, b)
        out["rows"].append({"metric": metric, "unit": unit, "good": good, "fy": fyd.get(metric),
                            "year_ago": b, "quarter": n, "dir": d, "verdict": verdict})
    out.update({"quarter": str(pd.Timestamp(q).date()), "year_ago": str(pd.Timestamp(q4).date()) if q4 is not None else None,
                "fy": fy_label, "revenue_q": now.get("Revenue"), "revenue_ya": before.get("Revenue")})
    return out


def fmt_val(v, unit):
    if v is None:
        return "n/a"
    if unit == "pct":
        return f"{v * 100:.1f}%"
    if unit == "usd":
        return f"{v:.2f}"
    if unit == "x":
        return f"{v:.2f}x"
    if unit == "days":
        return f"{v:.0f}"
    return f"({abs(v):,.1f})" if v < 0 else f"{v:,.1f}"


def scorecard_text(symbol, fyear=None):
    sc = quarterly_scorecard(symbol, fyear)
    if sc["error"]:
        return f"Quarterly scorecard not available: {sc['error']}."
    lines = [f"QUARTERLY SCORECARD for {symbol.upper()} (Yahoo Finance statements; cite as [3]). Latest quarter ended "
             f"{sc['quarter']}, compared with the same quarter a year earlier ({sc['year_ago'] or 'n/a'}) and with "
             f"{sc['fy'] or 'the last fiscal year'} from the 10-K. Revenue latest quarter: {fmt_val(sc['revenue_q'], 'mn')} million "
             f"(year-ago quarter {fmt_val(sc['revenue_ya'], 'mn')} million). Verdict = direction judged against what is good "
             "for shareholders (e.g. rising margins = better, rising share count = worse):"]
    for r in sc["rows"]:
        u = r["unit"]
        lines.append(f"- {r['metric']}: {sc['fy'] or 'FY'} {fmt_val(r['fy'], u)}, year-ago quarter {fmt_val(r['year_ago'], u)}, "
                     f"latest quarter {fmt_val(r['quarter'], u)} -> {r['verdict']}")
    return "\n".join(lines)


# --------------------------------------------------------------- Pressemitteilung (8-K, Item 2.02)
def _html_to_text(html):
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _qend_near(rd):
    """Stichtag nahe einem Quartalsende (auch 13-Wochen-Quartale wie bei ASML: 28.09., 29.06., 30.03.)."""
    try:
        d = pd.Timestamp(rd)
    except Exception:
        return False
    return (d.month in (3, 6, 9, 12) and d.day >= 24) or (d.month in (1, 4, 7, 10) and d.day <= 3)


def results_filings(r):
    """Einreichungen zu Quartalszahlen, neueste zuerst: [(Einreichung, Accession, Form, Stichtag, Dokument)].
    US-Emittenten: 8-K mit Item 2.02. Auslaendische Emittenten (20-F) melden Quartalszahlen per 6-K ohne Item-Nummer:
    6-K zu einem Quartalsstichtag, 7-75 Tage danach eingereicht; je Stichtag zuerst Dokumente mit Stichwort
    (results/quarter/earnings), dann die frueheste Einreichung ab 12 Tagen (vorher kommen z. B. Monatsumsaetze).
    Weitere Kandidaten desselben Stichtags bleiben als Ersatz in der Liste (Form '6-K alt')."""
    n = len(r["form"])
    items = r.get("items") or [""] * n
    docs = r.get("primaryDocument") or [""] * n
    descs = r.get("primaryDocDescription") or [""] * n
    rds = r.get("reportDate") or [""] * n
    out, six = [], {}
    for f, d, a, it, rd, doc, ds in zip(r["form"], r["filingDate"], r["accessionNumber"], items, rds, docs, descs):
        if f in ("8-K", "8-K/A") and "2.02" in str(it):
            out.append((d, a, f, rd, doc))
        elif f in ("6-K", "6-K/A") and rd and _qend_near(rd):
            lag = (pd.Timestamp(d) - pd.Timestamp(rd)).days
            if 7 <= lag <= 75:
                kw = bool(re.search(r"result|earning|quarter|interim", f"{doc} {ds}", re.I))
                six.setdefault(rd, []).append((not kw, lag < 12, d, a, f, rd, doc))
    for rd, xs in six.items():
        xs.sort()
        for i, x in enumerate(xs):
            out.append((x[2], x[3], x[4] if i == 0 else "6-K alt", x[5], x[6]))
    return sorted(out, key=lambda x: x[0], reverse=True)


def _looks_like_results(text):
    """Grobe Pruefung, ob ein 6-K-Dokument Quartalszahlen enthaelt (und nicht z. B. Monatsumsatz oder HV)."""
    low = text[:20000].lower()
    return ("quarter" in low or "three months" in low) and any(w in low for w in ("net income", "net sales", "revenue",
                                                                                   "gross margin", "earnings per"))


def earnings_release(symbol, max_chars=30000):
    """Neueste Pressemitteilung zu Quartalszahlen (8-K Item 2.02, Exhibit 99.1) aus EDGAR, mit Cache.
    Jeder Schritt meldet bei Problemen einen klaren Grund (statt still leer zu bleiben)."""
    import requests
    from finrobot.data_source.fmp_utils import _sec_headers, _ticker_to_cik
    try:
        h = _sec_headers()
        cik = _ticker_to_cik().get(symbol.upper())
    except Exception as e:
        return {"error": f"SEC access failed ({e})"}
    if cik is None:
        return {"error": f"{symbol} is not registered with the SEC"}
    try:
        rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=h, timeout=30).json()
    except Exception as e:
        return {"error": f"EDGAR submissions request failed ({e})"}
    r = rec["filings"]["recent"]
    found = results_filings(r)
    hits = [(d, a) for d, a, f, rd, doc in found]
    if not hits:
        return {"error": "no 8-K with Item 2.02 (results of operations) or quarterly 6-K in the recent EDGAR filings"}
    if any(f.startswith("6-K") for _, _, f, _, _ in found):     # 6-K: Ersatzkandidaten und Inhaltspruefung
        # neuester Stichtag zuerst, darin der bevorzugte Kandidat (nicht 'alt'), dann nach Einreichungsdatum
        order = sorted(found, key=lambda x: (x[3], x[2] != "6-K alt", [-int(c) for c in x[0].replace("-", "")]),
                       reverse=True)
        for d, a, f, rd, doc in order[:6]:
            res = _fetch_exhibit99(cik, h, d, a, symbol, max_chars, form=f)
            if not res.get("error"):
                return res
        return {"error": "no quarterly 6-K with results text found"}
    last_err = ""
    for fdate, acc in hits[:3]:  # neueste zuerst; falls eine Einreichung kein Exhibit 99 hat, die naechste
        cache = AIF / "reports" / "earnings_cache" / f"{symbol.upper()}_{fdate}_ex99.txt"
        if cache.exists():
            url_f = cache.with_suffix(".url")
            return {"error": None, "filing_date": fdate, "text": cache.read_text(encoding="utf-8")[:max_chars],
                    "url": url_f.read_text(encoding="utf-8") if url_f.exists() else ""}
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
        files = []
        try:
            idx = requests.get(f"{base}/index.json", headers=h, timeout=30).json()
            files = [i["name"] for i in idx["directory"]["item"]]
        except Exception as e:
            last_err = f"filing index not readable ({e})"
            try:  # Ersatz: HTML-Index der Einreichung
                html = requests.get(f"{base}/{acc}-index.htm", headers=h, timeout=30).text
                files = [x.split("/")[-1] for x in re.findall(r'href="([^"]+)"', html)]
            except Exception:
                pass
        ex = [f for f in files if re.search(r"ex(hibit)?[^0-9/]{0,2}99", f, re.I) and f.lower().endswith((".htm", ".html", ".txt"))]
        if not ex:
            last_err = last_err or f"8-K filed {fdate} has no exhibit 99 document"
            continue
        url = f"{base}/{sorted(ex)[0]}"
        try:
            text = _html_to_text(requests.get(url, headers=h, timeout=60).text)
        except Exception as e:
            last_err = f"exhibit download failed ({e})"
            continue
        if len(text) < 500:
            last_err = f"exhibit {url} is (almost) empty"
            continue
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(text, encoding="utf-8")
        cache.with_suffix(".url").write_text(url, encoding="utf-8")
        return {"error": None, "filing_date": fdate, "text": text[:max_chars], "url": url}
    return {"error": last_err or "earnings release not found"}


# --------------------------------------------------------------- 10-Q (sec-api)
def latest_10q(symbol):
    import requests
    from finrobot.data_source.fmp_utils import _sec_headers, _ticker_to_cik
    cik = _ticker_to_cik().get(symbol.upper())
    rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_sec_headers(), timeout=30).json()
    r = rec["filings"]["recent"]
    for f, d, rd, a, doc in zip(r["form"], r["filingDate"], r["reportDate"], r["accessionNumber"], r["primaryDocument"]):
        if f == "10-Q":
            return {"filing_date": d, "report_date": rd,
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{a.replace('-', '')}/{doc}"}
    return None


def _tenq_section(q, symbol, item, cache):
    """Abschnitt eines 10-Q: eigene Zerlegung des EDGAR-Dokuments, sec-api nur als Rueckfall (Kontingent begrenzt)."""
    from finrobot.data_source.sec_utils import CACHE_PATH
    text = None
    try:
        from finrobot.data_source.edgar_sections import fetch_text, tenq_item
        full = fetch_text(q["url"], str(Path(CACHE_PATH) / "sec_utils" / "full" / f"{symbol.upper()}_{q['report_date']}_10q.txt"))
        seg = tenq_item(full, item)
        if seg:
            text = f"[10-Q {q['report_date']}, {item}; extracted from the EDGAR filing]\n" + seg
    except Exception:
        text = None
    if text is None:
        try:
            from sec_api import ExtractorApi
            text = unescape(ExtractorApi(os.environ["SEC_API_KEY"]).get_section(q["url"], item, "text"))
        except Exception as e:
            return f"(not available: {str(e)[:160]})"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def tenq_sections(symbol, max_chars=25000):
    """MD&A (Part I Item 2) und Risikofaktoren (Part II Item 1A) des neuesten 10-Q; je 1 sec-api-Call, dann Cache."""
    from finrobot.data_source.sec_utils import CACHE_PATH
    q = latest_10q(symbol)
    if not q:
        return {"error": "no 10-Q found in EDGAR"}
    out = {"error": None, **q, "sections": {}}
    for item, label in (("part1item2", "MD&A"), ("part2item1a", "Risk factors")):
        cache = Path(CACHE_PATH) / "sec_utils" / f"{symbol.upper()}_{q['report_date']}_10q_{item}.txt"
        if cache.exists():
            text = cache.read_text(encoding="utf-8")
        else:
            text = _tenq_section(q, symbol, item, cache)
        out["sections"][label] = text[:max_chars]
    return out


# --------------------------------------------------------------- Ausgangsbasis: Annual Report
def annual_baseline(symbol):
    """Takeaways, Summary und Risiken aus dem neuesten Annual Report des Agenten (build_args.json)."""
    sym = symbol.upper()
    # nur Annual-Report-Ordner <SYM>_<Jahr>_... (nicht <SYM>_earnings_multi_..., sonst wird ein Earnings Review zur Basis)
    cands = [p for p in glob.glob(str(AIF / "reports" / f"{sym}_*" / "*build_args.json"))
             if re.match(rf"{re.escape(sym)}_\d{{4}}_", Path(p).parent.name)]
    if not cands:
        return {"error": f"no annual report of the agent found for {symbol.upper()}; run the annual report agent first"}
    p = max(cands, key=os.path.getmtime)
    a = json.load(open(p, encoding="utf-8"))
    return {"error": None, "path": os.path.relpath(p, AIF), "filing_date": a.get("filing_date"),
            "takeaways": a.get("key_takeaways") or [], "summary": a.get("investment_summary", ""),
            "risks": a.get("risk_assessment", ""), "theses": a.get("investment_theses") or []}


# =============================================================== Mehrere Quartale (fuer den Multi-Quarter Reviewer)
def _fy_end(ai, fyear):
    """Bilanzstichtag des Geschaeftsjahres aus den Jahreszahlen (Yahoo)."""
    if ai is None:
        return None
    cols = sorted(c for c in ai.columns if _row(ai, REV, c))
    if fyear is not None:
        cols = [c for c in cols if pd.Timestamp(c).year <= int(fyear)]
    return pd.Timestamp(cols[-1]) if cols else None


def _year_ago(cols, q):
    hit = [c for c in cols if abs((pd.Timestamp(q) - pd.Timedelta(days=365) - pd.Timestamp(c)).days) <= 45]
    return hit[0] if hit else None


def _trend(metric, values):
    """Verlauf ueber die Quartale (erstes vs. letztes Quartal), aus Aktionaerssicht bewertet."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return "n/a"
    d, verdict = _assess(metric, vals[-1], vals[0])
    if d is None:
        return "n/a"
    if verdict == "stable":
        return "stable"
    return "improving" if verdict == "better" else "deteriorating"


def multi_quarter_scorecard(symbol, fyear):
    """
    Alle Quartale seit dem Geschaeftsjahresende des 10-K: je Kennzahl Wert pro Quartal mit Vorjahresvergleich,
    Year-to-date vs. Vorjahres-YTD (fuer Umsatz und Margen, soweit alle Vorjahresquartale vorliegen) und Trend.
    """
    out = {"error": None, "quarters": [], "rows": []}
    t = _ticker(symbol)
    qi, qb, qc = _get(t, "quarterly_income_stmt"), _get(t, "quarterly_balance_sheet"), _get(t, "quarterly_cashflow")
    ai, ab, ac = _get(t, "income_stmt"), _get(t, "balance_sheet"), _get(t, "cashflow")
    if qi is None:
        out["error"] = "no quarterly statements on Yahoo Finance"
        return out
    fy_end = _fy_end(ai, fyear)
    if fy_end is None:
        out["error"] = f"fiscal year {fyear} not found in the annual statements"
        return out
    qcols = sorted(c for c in qi.columns if _row(qi, REV, c))
    since = [c for c in qcols if pd.Timestamp(c) > fy_end + pd.Timedelta(days=20)]
    if not since:
        out["error"] = f"no quarter reported after the fiscal year end {fy_end.date()} yet"
        return out
    fy = fy_end.year
    labels = [f"Q{i + 1} FY{fy + 1}" for i in range(len(since))]
    per_q, per_ya = [], []
    for q in since:
        q4 = _year_ago(qcols, q)
        q8 = _year_ago(qcols, q4) if q4 is not None else None
        per_q.append(_period_metrics(qi, qb, qc, q, prev_rev=_row(qi, REV, q4) if q4 is not None else None))
        per_ya.append(_period_metrics(qi, qb, qc, q4, prev_rev=_row(qi, REV, q8) if q8 is not None else None)
                      if q4 is not None else {})
    fyd = {}
    if ai is not None:
        acols = sorted(c for c in ai.columns if _row(ai, REV, c) and pd.Timestamp(c) <= fy_end)
        prev = [c for c in acols if pd.Timestamp(c).year == fy - 1]
        fyd = _period_metrics(ai, ab, ac, acols[-1], prev_rev=_row(ai, REV, prev[-1]) if prev else None, days=365)
    # YTD (Summen der Quartale) vs. Vorjahres-YTD
    ytd = {}
    ya_cols = [_year_ago(qcols, q) for q in since]
    if all(c is not None for c in ya_cols):
        def s(names, cols, df):
            vals = [_row(df, names, c) for c in cols]
            return sum(vals) if all(v is not None for v in vals) else None
        r1, r0 = s(REV, since, qi), s(REV, ya_cols, qi)
        if r1 and r0:
            ytd["Revenue growth y/y"] = (r1 / r0 - 1, None)
            for metric, names in (("Gross margin", GP), ("Operating margin", OPINC), ("Net margin", NI)):
                a1, a0 = s(names, since, qi), s(names, ya_cols, qi)
                if a1 is not None and a0 is not None:
                    ytd[metric] = (a1 / r1, a0 / r0)
            if qc is not None:
                f1 = [_fcf(qc, c) if c in qc.columns else None for c in since]
                f0 = [_fcf(qc, c) if c in qc.columns else None for c in ya_cols]
                if all(v is not None for v in f1 + f0):
                    ytd["Free cash flow margin"] = (sum(f1) / r1, sum(f0) / r0)
            ytd["_revenue"] = (r1 / 1e6, r0 / 1e6)
    for metric, unit, good, thr in METRICS:
        cells = []
        for n_, b_ in zip(per_q, per_ya):
            d, verdict = _assess(metric, n_.get(metric), b_.get(metric))
            cells.append({"value": n_.get(metric), "year_ago": b_.get(metric), "dir": d, "verdict": verdict})
        y = ytd.get(metric)
        ytd_cell = None
        if y is not None:
            if metric == "Revenue growth y/y":
                ytd_cell = {"value": y[0], "year_ago": None, "verdict": "n/a"}
            else:
                d, verdict = _assess(metric, y[0], y[1])
                ytd_cell = {"value": y[0], "year_ago": y[1], "verdict": verdict}
        out["rows"].append({"metric": metric, "unit": unit, "good": good, "fy": fyd.get(metric), "quarters": cells,
                            "ytd": ytd_cell, "trend": _trend(metric, [c["value"] for c in cells])})
    out.update({"quarters": [{"label": l, "end": str(pd.Timestamp(q).date()),
                              "year_ago_end": str(pd.Timestamp(c).date()) if c is not None else None}
                             for l, q, c in zip(labels, since, ya_cols)],
                "fy": f"FY{fy}", "fy_end": str(fy_end.date()), "ytd_revenue": ytd.get("_revenue")})
    return out


def multi_scorecard_text(symbol, fyear):
    sc = multi_quarter_scorecard(symbol, fyear)
    if sc["error"]:
        return f"Multi-quarter scorecard not available: {sc['error']}."
    qs = ", ".join(f"{q['label']} (ended {q['end']})" for q in sc["quarters"])
    lines = [f"MULTI-QUARTER SCORECARD for {symbol.upper()} (Yahoo Finance statements; cite as [3]). Quarters since the "
             f"{sc['fy']} 10-K (fiscal year end {sc['fy_end']}): {qs}. Each quarter is compared with the same quarter a "
             "year earlier; verdict from a shareholder's view; trend = first vs. latest quarter."]
    if sc.get("ytd_revenue"):
        lines.append(f"Year-to-date revenue {fmt_val(sc['ytd_revenue'][0], 'mn')} million vs. "
                     f"{fmt_val(sc['ytd_revenue'][1], 'mn')} million in the prior-year period.")
    for r in sc["rows"]:
        u = r["unit"]
        qtxt = "; ".join(f"{q['label']} {fmt_val(c['value'], u)} (year-ago {fmt_val(c['year_ago'], u)}, {c['verdict']})"
                         for q, c in zip(sc["quarters"], r["quarters"]))
        ytd = (f"; YTD {fmt_val(r['ytd']['value'], u)} vs {fmt_val(r['ytd']['year_ago'], u)} ({r['ytd']['verdict']})"
               if r["ytd"] and r["ytd"]["year_ago"] is not None else
               (f"; YTD {fmt_val(r['ytd']['value'], u)}" if r["ytd"] else ""))
        lines.append(f"- {r['metric']}: {sc['fy']} {fmt_val(r['fy'], u)}; {qtxt}{ytd}; trend {r['trend']}")
    return "\n".join(lines)


def _fetch_exhibit99(cik, h, fdate, acc, symbol, max_chars, form="8-K"):
    """Text der Pressemitteilung (Exhibit 99). Bei 6-K ohne Exhibit 99: groesstes HTML-Dokument der Einreichung;
    6-K-Texte muessen nach Quartalszahlen aussehen (sonst Fehler, damit der naechste Kandidat probiert wird)."""
    import requests
    cache = AIF / "reports" / "earnings_cache" / f"{symbol.upper()}_{fdate}_ex99.txt"
    if cache.exists():
        url_f = cache.with_suffix(".url")
        return {"error": None, "filing_date": fdate, "text": cache.read_text(encoding="utf-8")[:max_chars],
                "url": url_f.read_text(encoding="utf-8") if url_f.exists() else ""}
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}"
    files, sizes = [], {}
    try:
        idx = requests.get(f"{base}/index.json", headers=h, timeout=30).json()
        files = [i["name"] for i in idx["directory"]["item"]]
        sizes = {i["name"]: int(i.get("size") or 0) for i in idx["directory"]["item"] if str(i.get("size", "")).isdigit()}
    except Exception:
        try:
            html = requests.get(f"{base}/{acc}-index.htm", headers=h, timeout=30).text
            files = [x.split("/")[-1] for x in re.findall(r'href="([^"]+)"', html)]
        except Exception as e:
            return {"error": f"filing index not readable ({e})", "filing_date": fdate}
    ex = [f for f in files if re.search(r"ex(hibit)?[^0-9/]{0,2}99", f, re.I) and f.lower().endswith((".htm", ".html", ".txt"))]
    if not ex and form.startswith("6-K"):          # 6-K: Mitteilung steht oft im Hauptdokument oder einem Anhang
        ex = sorted([f for f in files if f.lower().endswith((".htm", ".html")) and "index" not in f.lower()
                     and not re.match(r"R\d+\.htm", f)], key=lambda f: -sizes.get(f, 0))[:1]
    if not ex:
        return {"error": f"{form} filed {fdate} has no exhibit 99 document", "filing_date": fdate}
    url = f"{base}/{sorted(ex)[0] if not form.startswith('6-K') else ex[0]}"
    try:
        text = _html_to_text(requests.get(url, headers=h, timeout=60).text)
    except Exception as e:
        return {"error": f"exhibit download failed ({e})", "filing_date": fdate}
    if len(text) < 500:
        return {"error": f"exhibit {url} is (almost) empty", "filing_date": fdate}
    if form.startswith("6-K") and not _looks_like_results(text):
        return {"error": f"6-K filed {fdate} does not look like a results release", "filing_date": fdate}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    cache.with_suffix(".url").write_text(url, encoding="utf-8")
    return {"error": None, "filing_date": fdate, "text": text[:max_chars], "url": url}


def earnings_releases_since(symbol, after_date, max_chars=14000):
    """Alle Pressemitteilungen zu Quartalszahlen (8-K, Item 2.02), die nach after_date eingereicht wurden.
    Die Mitteilung zum Geschaeftsjahr selbst (kurz nach dem Stichtag) ist ausgeschlossen: Stichtag + 75 Tage."""
    import requests
    from finrobot.data_source.fmp_utils import _sec_headers, _ticker_to_cik
    try:
        h = _sec_headers()
        cik = _ticker_to_cik().get(symbol.upper())
        rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=h, timeout=30).json()
    except Exception as e:
        return [{"error": f"EDGAR request failed ({e})"}]
    r = rec["filings"]["recent"]
    cutoff = (pd.Timestamp(after_date) + pd.Timedelta(days=75)).date().isoformat()
    found = [x for x in results_filings(r) if x[0] > cutoff]
    if not found:
        return [{"error": f"no 8-K with Item 2.02 or quarterly 6-K filed after {cutoff}"}]
    if not any(f.startswith("6-K") for _, _, f, _, _ in found):
        return [_fetch_exhibit99(cik, h, d, a, symbol, max_chars) for d, a, _, _, _ in sorted(found)]
    out = []                                        # 6-K: je Quartalsstichtag den ersten Kandidaten mit Ergebnistext
    for rd in sorted({x[3] for x in found}):
        res = {"error": f"no results release for the quarter ended {rd}"}
        for d, a, f, rd_, doc in sorted([x for x in found if x[3] == rd], key=lambda x: (x[2] == "6-K alt", x[0])):
            res = _fetch_exhibit99(cik, h, d, a, symbol, max_chars, form=f)
            if not res.get("error"):
                break
        out.append(res)
    return out


def tenqs_since(symbol, after_date, max_chars=12000):
    """MD&A aller 10-Q nach after_date (je 1 sec-api-Call, dann Cache) und Risikofaktoren nur des neuesten."""
    import requests
    from finrobot.data_source.fmp_utils import _sec_headers, _ticker_to_cik
    from finrobot.data_source.sec_utils import CACHE_PATH
    cik = _ticker_to_cik().get(symbol.upper())
    rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_sec_headers(), timeout=30).json()
    r = rec["filings"]["recent"]
    qs = [{"filing_date": d, "report_date": rd, "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{a.replace('-', '')}/{doc}"}
          for f, d, rd, a, doc in zip(r["form"], r["filingDate"], r["reportDate"], r["accessionNumber"], r["primaryDocument"])
          if f == "10-Q" and rd > str(after_date)]
    qs = sorted(qs, key=lambda x: x["report_date"])
    out = []
    for i, q in enumerate(qs):
        items = [("part1item2", "MD&A")] + ([("part2item1a", "Risk factors")] if i == len(qs) - 1 else [])
        q["sections"] = {}
        for item, label in items:
            cache = Path(CACHE_PATH) / "sec_utils" / f"{symbol.upper()}_{q['report_date']}_10q_{item}.txt"
            if cache.exists():
                text = cache.read_text(encoding="utf-8")
            else:
                text = _tenq_section(q, symbol, item, cache)
            q["sections"][label] = text[:max_chars]
        out.append(q)
    return out


# --------------------------------------------------------------- Thesen-Protokoll
def thesis_log_path(symbol):
    return AIF / "reports" / "thesis_logs" / f"{symbol.upper()}_thesis_log.json"


def load_thesis_log(symbol):
    p = thesis_log_path(symbol)
    return json.load(open(p, encoding="utf-8")) if p.exists() else []


def append_thesis_log(symbol, entry):
    p = thesis_log_path(symbol)
    p.parent.mkdir(parents=True, exist_ok=True)
    log = load_thesis_log(symbol)
    log.append(entry)
    json.dump(log, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return p
