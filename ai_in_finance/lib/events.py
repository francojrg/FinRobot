"""
Termine fuer die Home-Seite der App:
- Quartalszahlen, Ex-Dividende und Dividendenzahlung (Yahoo-Kalender)
- aus den News erkannte Ankuendigungen (Konferenzen, Investor Days, Hauptversammlungen, Webcasts); das ist ein Fund in
  den gesammelten Meldungen, keine vollstaendige Liste.
Ergebnis wird in research/events.json zwischengespeichert (6 Stunden).
"""
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
CACHE = AIF / "research" / "events.json"
EVENT_RE = re.compile(r"(investor day|capital markets day|analyst day|annual (general )?meeting|shareholder meeting|"
                      r"\bAGM\b|conference|to present|will present|fireside chat|webcast|earnings call|keynote|"
                      r"to host|will host)", re.I)


def _d(x):
    try:
        import pandas as pd
        return pd.Timestamp(x).date()
    except Exception:
        return None


def yahoo_calendar(tickers):
    out = []
    try:
        import yfinance as yf
    except Exception:
        return out
    for t in tickers:
        try:
            cal = yf.Ticker(t).calendar or {}
        except Exception:
            continue
        if not isinstance(cal, dict):
            continue
        ed = cal.get("Earnings Date")
        ed = ed if isinstance(ed, (list, tuple)) else [ed]
        if ed and ed[0] is not None and _d(ed[0]):
            out.append({"date": _d(ed[0]).isoformat(), "ticker": t, "type": "Quarterly results",
                        "detail": "estimated" if len(ed) > 1 else "", "source": "Yahoo Finance"})
        for k, lab in (("Ex-Dividend Date", "Ex-dividend"), ("Dividend Date", "Dividend payment")):
            if cal.get(k) is not None and _d(cal[k]):
                out.append({"date": _d(cal[k]).isoformat(), "ticker": t, "type": lab, "detail": "",
                            "source": "Yahoo Finance"})
    return out


def news_announcements(tickers, days=30):
    """Meldungen der letzten Tage, die einen Termin ankuendigen (Stichwortsuche in den gesammelten News)."""
    try:
        from . import news_tracker as nt
        store = nt.load_store()
    except Exception:
        return []
    tick = {t.upper() for t in tickers}
    since = (date.today() - timedelta(days=days)).isoformat()
    out, seen = [], set()
    for s in store:
        if s.get("ticker", "").upper() not in tick or s.get("date", "")[:10] < since or not s.get("relevant", True):
            continue
        txt = f"{s.get('title', '')} {s.get('summary', '')}"
        m = EVENT_RE.search(txt)
        if not m:
            continue
        key = (s["ticker"], s.get("title", "")[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": s["date"][:10], "ticker": s["ticker"], "type": "Announced in the news",
                    "detail": s.get("title", "")[:160], "url": s.get("url", ""), "source": s.get("source_type", "news")})
    return sorted(out, key=lambda x: x["date"], reverse=True)


def events(tickers, max_age_hours=6, refresh=False, cache_path=None):
    """{"upcoming": [...], "announced": [...], "updated": ...} fuer die Positionen.
    cache_path: eigene Cache-Datei (z. B. Watchlist), damit sich Home und Watchlist nicht gegenseitig verdraengen."""
    CACHE = Path(cache_path) if cache_path else globals()["CACHE"]
    tickers = sorted({t.upper() for t in tickers})
    if CACHE.exists() and not refresh:
        try:
            c = json.load(open(CACHE, encoding="utf-8"))
            if c.get("tickers") == tickers and time.time() - c.get("ts", 0) < max_age_hours * 3600:
                return c
        except Exception:
            pass
    today = date.today().isoformat()
    cal = [e for e in yahoo_calendar(tickers) if e["date"] >= today]
    c = {"tickers": tickers, "ts": time.time(), "updated": time.strftime("%Y-%m-%d %H:%M"),
         "upcoming": sorted(cal, key=lambda x: x["date"]), "announced": news_announcements(tickers)}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(c, open(CACHE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return c
