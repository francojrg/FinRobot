"""
ETF-Durchschau: Was steckt in den ETFs des Depots, und wo doppelt es sich mit Direktanlagen?

Yahoo liefert je ETF kostenlos die 10 groessten Positionen und die Sektoraufteilung (funds_data), nicht alle
Bestandteile. Gesamtgewicht eines Titels = Direktgewicht + Summe(ETF-Gewicht x Anteil im ETF). Der durchleuchtete
Teil (Summe der Top-10-Anteile) wird ausgewiesen, damit klar ist, wie viel des ETF-Anteils sichtbar ist.
Bei vielen europaeischen UCITS-ETFs hat Yahoo keine Bestandsdaten; die werden als "ohne Daten" gemeldet.
Zwischenspeicher research/etf_lookthrough.json (24 Stunden).
"""
import json
import time
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
CACHE = AIF / "research" / "etf_lookthrough.json"
SECTOR_DE = {"technology": "Technology", "financial_services": "Financials", "healthcare": "Health care",
             "consumer_cyclical": "Consumer cyclical", "communication_services": "Communication",
             "industrials": "Industrials", "consumer_defensive": "Consumer staples", "energy": "Energy",
             "basic_materials": "Materials", "realestate": "Real estate", "real_estate": "Real estate",
             "utilities": "Utilities"}
YF_SECTOR = {"Technology": "technology", "Financial Services": "financial_services", "Healthcare": "healthcare",
             "Consumer Cyclical": "consumer_cyclical", "Communication Services": "communication_services",
             "Industrials": "industrials", "Consumer Defensive": "consumer_defensive", "Energy": "energy",
             "Basic Materials": "basic_materials", "Real Estate": "realestate", "Utilities": "utilities"}


def fund_data(t):
    """quoteType, Name, Top-10 [(symbol, name, anteil)], Sektoren {sektor: anteil} fuer einen Ticker."""
    import yfinance as yf
    tk = yf.Ticker(t)
    out = {"type": None, "name": None, "top": [], "sectors": {}}
    try:
        info = tk.info or {}
        out["type"], out["name"] = info.get("quoteType"), info.get("shortName") or info.get("longName")
    except Exception:
        pass
    if out["type"] not in ("ETF", "MUTUALFUND"):
        return out
    try:
        fd = tk.funds_data
        th = fd.top_holdings
        if th is not None and len(th):
            col = next((c for c in th.columns if "percent" in c.lower()), th.columns[-1])
            ncol = next((c for c in th.columns if "name" in c.lower()), None)
            out["top"] = [(str(i).upper(), str(r[ncol]) if ncol else str(i), float(r[col])) for i, r in th.iterrows()]
        sw = fd.sector_weightings or {}
        out["sectors"] = {k: float(v) for k, v in sw.items() if v}
    except Exception:
        pass
    return out


def _norm(t):
    t = str(t).upper()
    return t.replace(".", "-") if len(t.split(".")[-1]) == 1 else t.split(".")[0] if t.endswith((".DE", ".F", ".AS", ".MI", ".PA", ".L", ".SW")) else t


def compute(positions, funds):
    """positions: [{ticker, name, weight (Anteil), sector}], funds: {ticker: fund_data(...)}."""
    etfs = [p for p in positions if (funds.get(p["ticker"]) or {}).get("type") in ("ETF", "MUTUALFUND")]
    direct = [p for p in positions if p not in etfs]
    exp, names, via = {}, {}, {}
    for p in direct:
        k = _norm(p["ticker"])
        exp.setdefault(k, {"direct": 0.0, "etf": 0.0})["direct"] += float(p.get("weight") or 0)
        names[k] = p.get("name") or p["ticker"]
    etf_rows = []
    for e in etfs:
        f = funds.get(e["ticker"]) or {}
        w = float(e.get("weight") or 0)
        cov = sum(x[2] for x in f.get("top") or [])
        etf_rows.append({"t": e["ticker"], "name": f.get("name") or e.get("name") or e["ticker"], "w": w,
                         "covered": cov or None, "n_top": len(f.get("top") or []), "has_data": bool(f.get("top"))})
        for sym, nm, pct in f.get("top") or []:
            k = _norm(sym)
            exp.setdefault(k, {"direct": 0.0, "etf": 0.0})["etf"] += w * pct
            names.setdefault(k, nm)
            via.setdefault(k, []).append(e["ticker"])
    rows = [{"t": k, "name": names.get(k, k), "direct": v["direct"] or None, "etf": v["etf"] or None,
             "total": v["direct"] + v["etf"], "via": via.get(k, []), "overlap": v["direct"] > 0 and v["etf"] > 0}
            for k, v in exp.items()]
    rows.sort(key=lambda r: -r["total"])
    sectors = {}
    for p in direct:
        s = YF_SECTOR.get(p.get("sector") or "", None)
        if s:
            sectors.setdefault(s, {"direct": 0.0, "etf": 0.0})["direct"] += float(p.get("weight") or 0)
    for e in etfs:
        w = float(e.get("weight") or 0)
        for s, v in ((funds.get(e["ticker"]) or {}).get("sectors") or {}).items():
            sectors.setdefault(s, {"direct": 0.0, "etf": 0.0})["etf"] += w * v
    sec = sorted([{"s": SECTOR_DE.get(k, k), "direct": v["direct"], "etf": v["etf"], "total": v["direct"] + v["etf"]}
                  for k, v in sectors.items()], key=lambda x: -x["total"])
    etf_w = sum(r["w"] for r in etf_rows)
    seen = sum(r["w"] * (r["covered"] or 0) for r in etf_rows)
    return {"etfs": etf_rows, "rows": rows, "sectors": sec, "etf_weight": etf_w,
            "covered_share": seen / etf_w if etf_w else None, "overlaps": [r for r in rows if r["overlap"]]}


def payload(positions, refresh=False, max_age_h=24):
    tickers = sorted(p["ticker"] for p in positions)
    c = {}
    try:
        c = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        pass
    if not refresh and c.get("tickers") == tickers and time.time() - c.get("ts", 0) < max_age_h * 3600:
        funds = c.get("funds", {})
    else:
        funds = {}
        for t in tickers:
            try:
                funds[t] = fund_data(t)
            except Exception:
                funds[t] = {}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        json.dump({"tickers": tickers, "ts": time.time(), "funds": funds}, open(CACHE, "w", encoding="utf-8"), indent=1)
    return compute(positions, funds)


# ------------------------------------------------------------------ Vergleich mit einem Welt-ETF
# Stellvertreter mit Bestandsdaten bei Yahoo (die UCITS-Varianten haben dort meist keine): VT bildet den FTSE Global
# All Cap ab (FTSE All-World plus Nebenwerte, praktisch gleiche Top-10 und Sektoren), ACWI den MSCI ACWI, URTH den
# MSCI World.
WORLD = {"FTSE All-World": "VT", "MSCI ACWI": "ACWI", "MSCI World": "URTH"}
_ALIAS = {"GOOG": "GOOGL", "BRK-A": "BRK-B", "FOXA": "FOX"}


def world_compare(positions, index="FTSE All-World", refresh=False, max_age_h=24 * 7):
    """Depot gegen einen Welt-ETF: Top-10 des Index mit deinem Gewicht, Ueber-/Untergewichte, Sektoren."""
    proxy = WORLD.get(index, "VT")
    c = {}
    try:
        c = json.load(open(CACHE, encoding="utf-8"))
    except Exception:
        pass
    w = (c.get("world") or {}).get(proxy)
    if refresh or not w or time.time() - w.get("ts", 0) > max_age_h * 3600:
        w = {"ts": time.time(), "data": fund_data(proxy)}
        c.setdefault("world", {})[proxy] = w
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        json.dump(c, open(CACHE, "w", encoding="utf-8"), indent=1)
    f = w["data"] or {}
    key = lambda t: _ALIAS.get(_norm(t), _norm(t))
    mine, names = {}, {}
    for p in positions:
        k = key(p["ticker"])
        mine[k] = mine.get(k, 0.0) + float(p.get("weight") or 0)
        names[k] = p.get("name") or p["ticker"]
    top = {}
    for sym, nm, pct in f.get("top") or []:
        k = key(sym)
        top[k] = top.get(k, 0.0) + pct
        names.setdefault(k, nm)
    rows = [{"t": k, "name": names.get(k, k), "index": v, "mine": mine.get(k, 0.0), "diff": mine.get(k, 0.0) - v}
            for k, v in top.items()]
    rows.sort(key=lambda r: -r["index"])
    extra = sorted([{"t": k, "name": names.get(k, k), "mine": v} for k, v in mine.items() if k not in top and v > 0],
                   key=lambda r: -r["mine"])
    sec_mine = {}
    for p in positions:
        s = YF_SECTOR.get(p.get("sector") or "")
        if s:
            sec_mine[s] = sec_mine.get(s, 0.0) + float(p.get("weight") or 0)
    secs = sorted({*sec_mine, *(f.get("sectors") or {})}, key=lambda s: -((f.get("sectors") or {}).get(s, 0)))
    sectors = [{"s": SECTOR_DE.get(s, s), "mine": sec_mine.get(s, 0.0), "index": (f.get("sectors") or {}).get(s, 0.0)}
               for s in secs]
    return {"index": index, "proxy": proxy, "name": f.get("name"), "has_data": bool(f.get("top")),
            "rows": rows, "extra": extra[:8], "sectors": sectors,
            "overlap": sum(min(r["mine"], r["index"]) for r in rows), "top10_share": sum(r["index"] for r in rows),
            "mine_in_top": sum(r["mine"] for r in rows)}
