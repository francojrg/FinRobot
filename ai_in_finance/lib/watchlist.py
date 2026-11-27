"""
Watchlist der App: Titel, die man beobachtet, ohne sie im Depot zu haben (research/app_watchlist.json, bleibt lokal).

- Bearbeiten im Portfolio-Reiter (hinzufuegen, Notiz, entfernen).
- Die Automatik nimmt die Watchlist mit (News, auf Wunsch Annual Report und Earnings Review), die News-Seite zeigt ihre
  Meldungen. Portfolio Review und Brief bleiben beim Depot.
"""
import json
import re
from datetime import date
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
PATH = AIF / "research" / "app_watchlist.json"
TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")


def load():
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except Exception:
        return []


def tickers():
    return [w["ticker"] for w in load()]


def _save(items):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    json.dump(items, open(PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def add(ticker, note=""):
    """Rueckgabe (ok, Meldung)."""
    t = str(ticker or "").strip().upper().replace(" ", "")
    if not TICKER_RE.match(t):
        return False, "Enter a ticker in Yahoo format, e.g. NVDA, ASML.AS or SAP.DE"
    items = load()
    if any(w["ticker"] == t for w in items):
        return False, f"{t} is already on the watchlist"
    items.append({"ticker": t, "note": str(note or "").strip()[:200], "added": date.today().isoformat()})
    _save(items)
    return True, f"{t} added"


def remove(ticker):
    _save([w for w in load() if w["ticker"] != str(ticker).upper()])


def set_note(ticker, note):
    items = load()
    for w in items:
        if w["ticker"] == str(ticker).upper():
            w["note"] = str(note or "").strip()[:200]
    _save(items)


def payload(portfolio=(), refresh=False):
    """Zeilen fuer das Widget: Kurs, Tagesveraenderung, naechste Zahlen, News der letzten 7 Tage, Research vorhanden."""
    items = load()
    if not items:
        return []
    ts = [w["ticker"] for w in items]
    quotes, events, news, reports = {}, {}, {}, set()
    try:
        from .home_data import quotes as _q
        quotes = (_q(ts, refresh=refresh, cache_path=AIF / "research" / "watchlist_quotes.json") or {}).get("data") or {}
    except Exception:
        pass
    try:
        from .events import events as _ev
        for e in (_ev(ts, cache_path=AIF / "research" / "watchlist_events.json") or {}).get("upcoming", []):
            if e.get("type") == "Quarterly results" and e["ticker"] not in events:
                events[e["ticker"]] = e["date"]
    except Exception:
        pass
    try:
        from .news_tracker import load_store
        since = date.fromordinal(date.today().toordinal() - 7).isoformat()
        for s in load_store():
            t = str(s.get("ticker", "")).upper()
            if t in ts and s.get("date", "")[:10] >= since and s.get("relevant", True):
                news[t] = news.get(t, 0) + 1
    except Exception:
        pass
    try:
        from .company_data import companies
        reports = {c["t"] for c in companies()}
    except Exception:
        pass
    port = {p.upper() for p in portfolio}
    return [{"t": w["ticker"], "note": w.get("note", ""), "added": w.get("added"),
             "price": (quotes.get(w["ticker"]) or {}).get("price"), "chg": (quotes.get(w["ticker"]) or {}).get("chg"),
             "earn": events.get(w["ticker"]), "news7": news.get(w["ticker"], 0), "report": w["ticker"] in reports,
             "in_portfolio": w["ticker"] in port} for w in items]
