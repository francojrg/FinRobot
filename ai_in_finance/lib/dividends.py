"""
Dividendenkalender fuer das Portfolio: Dividendenrendite je Position, erwartete Zahlungen der naechsten 12 Monate
(Muster der letzten 12 Monate fortgeschrieben, angekuendigte Ex-Tage von Yahoo bevorzugt) und naechste Ex-Tage.

Rechnung in EUR ueber den Positionswert aus dem Portfolio Review: Zahlung = Positionswert x Dividende / Kurs
(Dividende und Kurs in derselben Waehrung, daher waehrungsneutral). Brutto, vor Quellen- und Abgeltungsteuer.
Zwischenspeicher research/dividends.json (12 Stunden).
"""
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
CACHE = AIF / "research" / "dividends.json"


def _load(p, default):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default


def ticker_dividends(t):
    """Yahoo: Dividenden der letzten 2 Jahre [(datum, betrag)], letzter Kurs, Waehrung, angekuendigter Ex-Tag."""
    import yfinance as yf
    tk = yf.Ticker(t)
    out = {"divs": [], "price": None, "currency": None, "next_ex": None, "pay_date": None, "type": None}
    try:
        s = tk.dividends
        if s is not None and len(s):
            s.index = s.index.tz_localize(None) if getattr(s.index, "tz", None) is not None else s.index
            cut = datetime.now() - timedelta(days=730)
            out["divs"] = [(d.date().isoformat(), float(v)) for d, v in s.items() if d.to_pydatetime() >= cut and v > 0]
    except Exception:
        pass
    try:
        fi = tk.fast_info
        out["price"] = float(fi.get("lastPrice") or fi.get("last_price") or 0) or None
        out["currency"] = fi.get("currency")
    except Exception:
        pass
    try:
        cal = tk.calendar or {}
        ex, pay = cal.get("Ex-Dividend Date"), cal.get("Dividend Date")
        out["next_ex"] = ex.isoformat() if hasattr(ex, "isoformat") else (str(ex) if ex else None)
        out["pay_date"] = pay.isoformat() if hasattr(pay, "isoformat") else (str(pay) if pay else None)
    except Exception:
        pass
    try:
        out["type"] = (tk.info or {}).get("quoteType")
    except Exception:
        pass
    return out


def _freq(divs_12m):
    n = len(divs_12m)
    return {0: None, 1: "annual", 2: "semi-annual", 3: "quarterly", 4: "quarterly"}.get(n, "monthly" if n >= 10 else f"{n}x a year")


def compute(positions, raw, today=None):
    """positions: [{ticker, name, value_eur, weight}], raw: {ticker: ticker_dividends(...)} -> Kalender-Daten."""
    today = today or date.today()
    y_ago = (today - timedelta(days=365)).isoformat()
    months = {}
    rows = []
    for p in positions:
        t = p["ticker"]
        r = raw.get(t) or {}
        val = float(p.get("value_eur") or 0)
        price = r.get("price")
        last12 = [(d, a) for d, a in r.get("divs") or [] if d > y_ago]
        dps = sum(a for _, a in last12)
        yld = dps / price if price and dps else 0.0
        income = val * yld
        nxt = r.get("next_ex") if r.get("next_ex") and r["next_ex"] >= today.isoformat() else None
        # Projektion: jede Zahlung der letzten 12 Monate ein Jahr spaeter
        proj = []
        for d, a in last12:
            pd_ = (date.fromisoformat(d) + timedelta(days=365))
            if pd_ <= today:
                continue
            eur = val * a / price if price else 0.0
            proj.append((pd_.isoformat(), eur))
            key = pd_.strftime("%Y-%m")
            m = months.setdefault(key, {"eur": 0.0, "items": {}})
            m["eur"] += eur
            m["items"][t] = m["items"].get(t, 0.0) + eur
        if not nxt and proj:
            nxt = min(d for d, _ in proj)
        rows.append({"t": t, "name": p.get("name") or t, "w": p.get("weight"), "value": val or None,
                     "yield": yld or None, "dps": dps or None, "currency": r.get("currency"), "income": income or None,
                     "freq": _freq(last12), "next_ex": nxt, "announced": bool(r.get("next_ex") and r["next_ex"] >= today.isoformat()),
                     "etf": r.get("type") == "ETF"})
    rows.sort(key=lambda x: -(x["income"] or 0))
    keys = [(today.replace(day=1) + timedelta(days=32 * i)).strftime("%Y-%m") for i in range(12)]
    cal = [{"m": k, "eur": round(months.get(k, {}).get("eur", 0.0), 2),
            "items": {a: round(b, 2) for a, b in sorted(months.get(k, {}).get("items", {}).items(), key=lambda x: -x[1])}}
           for k in keys]
    total_val = sum(float(p.get("value_eur") or 0) for p in positions)
    total = sum(r["income"] or 0 for r in rows)
    upcoming = sorted([r for r in rows if r["next_ex"]], key=lambda r: r["next_ex"])[:6]
    return {"rows": rows, "months": cal, "total_eur": round(total, 2), "yield": total / total_val if total_val else None,
            "payers": sum(1 for r in rows if r["income"]), "upcoming": upcoming}


def payload(positions, refresh=False, max_age_h=12):
    """Mit Zwischenspeicher; positions wie in compute()."""
    tickers = sorted(p["ticker"] for p in positions)
    c = _load(CACHE, {})
    if not refresh and c.get("tickers") == tickers and time.time() - c.get("ts", 0) < max_age_h * 3600:
        raw = c.get("raw", {})
    else:
        raw = {}
        for t in tickers:
            try:
                raw[t] = ticker_dividends(t)
            except Exception:
                raw[t] = {}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        json.dump({"tickers": tickers, "ts": time.time(), "raw": raw}, open(CACHE, "w", encoding="utf-8"), indent=1)
    return compute(positions, raw)
