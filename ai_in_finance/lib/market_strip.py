"""
Index-Leiste fuer den Header: DAX, S&P 500, MSCI World, EUR/USD, Gold, Bitcoin, Ether, US 5Y, US 10Y, DE 5Y.
Kurse von Yahoo Finance (verzoegert); Veraenderung = letzter Schlusskurs bzw. aktueller Kurs gegen den Vortag.
MSCI World ueber den iShares-ETF URTH als Stellvertreter (Yahoo fuehrt den Index selbst nicht).
Rendite 5-jaehriger Bundeswertpapiere von der Deutschen Bundesbank (Zinsstrukturkurve, taegliche Reihe BBSIS).
"""
import json
import re
import time
from pathlib import Path

ITEMS = [("DAX", "^GDAXI", "idx"), ("S&P 500", "^GSPC", "idx"), ("MSCI World", "URTH", "pct"),
         ("EUR/USD", "EURUSD=X", "fx"), ("Gold", "GC=F", "idx"), ("Bitcoin", "BTC-USD", "usd"),
         ("Ether", "ETH-USD", "usd"), ("US 5Y", "^FVX", "yld"), ("US 10Y", "^TNX", "yld")]
BUBA_DE5Y = ("https://api.statistiken.bundesbank.de/rest/data/BBSIS/"
             "D.I.ZST.ZI.EUR.S1311.B.A604.R05XX.R.A.A._Z._Z.A?detail=dataonly&lastNObservations=5")
CACHE = Path(__file__).resolve().parents[1] / "research" / "market_strip.json"
TTL = 15 * 60


def _de5y():
    """Rendite 5-jaehriger Bundeswertpapiere (Bundesbank): (letzter Wert, Vortag, Datum) oder None."""
    import requests
    r = requests.get(BUBA_DE5Y, timeout=12, headers={"Accept": "application/xml"})
    obs = re.findall(r'ObsDimension value="([\d-]+)"\s*/?>(?:</generic:ObsDimension>)?\s*<generic:ObsValue value="([-\d.]+)"', r.text)
    if len(obs) < 2:
        return None
    return float(obs[-1][1]), float(obs[-2][1]), obs[-1][0]


def _fetch():
    import yfinance as yf
    syms = [s for _, s, _ in ITEMS]
    df = yf.download(syms, period="7d", interval="1d", progress=False, threads=True, auto_adjust=False)["Close"]
    out = []
    for lab, sym, kind in ITEMS:
        try:
            s = df[sym].dropna()
            last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        except Exception:
            continue
        if kind == "yld" and last > 20:              # alte Yahoo-Notation: Rendite x 10
            last, prev = last / 10, prev / 10
        chg = (last - prev) if kind == "yld" else (last / prev - 1)
        out.append({"l": lab, "v": last, "c": chg, "k": kind, "d": str(s.index[-1])[:10]})
    try:
        de = _de5y()
        if de:
            out.append({"l": "DE 5Y", "v": de[0], "c": de[0] - de[1], "k": "yld", "d": de[2]})
    except Exception:
        pass
    return out


def quotes():
    """Liste {l: Label, v: Wert, c: Veraenderung, k: Art}; 15 Minuten zwischengespeichert, bei Fehler alter Stand."""
    try:
        c = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - c.get("ts", 0) < TTL and c.get("items"):
            return c["items"], c.get("asof")
    except Exception:
        c = {}
    try:
        items = _fetch()
        if items:
            asof = time.strftime("%H:%M")
            CACHE.write_text(json.dumps({"ts": time.time(), "asof": asof, "items": items}), encoding="utf-8")
            return items, asof
    except Exception:
        pass
    try:                                    # ohne Netz: erst in 5 Minuten wieder versuchen, alten Stand behalten
        CACHE.write_text(json.dumps({"ts": time.time() - TTL + 300, "asof": c.get("asof"), "items": c.get("items") or []}),
                         encoding="utf-8")
    except Exception:
        pass
    return c.get("items") or [], c.get("asof")


def html(items, asof=None):
    """Index-Leiste als HTML-Zeile."""
    from html import escape

    def val(x):
        if x["k"] == "fx":
            return f"{x['v']:.4f}"
        if x["k"] == "yld":
            return f"{x['v']:.2f}%"
        if x["k"] == "pct":
            return ""
        if x["k"] == "usd":
            return f"${x['v']:,.0f}"
        return f"{x['v']:,.0f}" if x["v"] >= 1000 else f"{x['v']:,.2f}"

    def chg(x):
        c = x["c"]
        txt = f"{c * 100:+.0f} bp" if x["k"] == "yld" else f"{c * 100:+.2f}%"
        return f"<span class='{'up' if c >= 0 else 'dn'}'>{txt.replace('-', '−')}</span>"

    cells = "".join(f"<span class='bt-i'><span class='bt-l'>{escape(x['l'])}</span> {val(x)} {chg(x)}</span>" for x in items)
    tail = f"<span class='bt-a'>delayed{(' · ' + asof) if asof else ''}</span>" if items else ""
    return f"<div class='bt' title='Yahoo Finance, delayed quotes; MSCI World via the iShares URTH ETF; DE 5Y = 5-year Bund yield from the Deutsche Bundesbank'>{cells}{tail}</div>"
