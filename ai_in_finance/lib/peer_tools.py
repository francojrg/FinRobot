"""
Eigenes Tool: Peer-Kandidaten automatisch finden.

Ablauf: Finnhub liefert Unternehmen aus derselben Branche (kostenloser Endpunkt /stock/peers).
Fuer jeden Kandidaten werden Name, Branche, Land, Marktkapitalisierung und Umsatz von Yahoo
Finance ergaenzt. Der Agent waehlt daraus die vergleichbarsten Peers aus und begruendet die Wahl.
Faellt Finnhub aus, bekommt der Agent einen klaren Hinweis statt still erfundener Peers.
"""
import os
import math
from typing import Annotated, List

import yfinance as yf


def _fmt_bn(v):
    try:
        return f"{float(v) / 1e9:,.1f}"
    except (TypeError, ValueError):
        return "n/a"


def _profile(sym):
    try:
        info = yf.Ticker(sym).info or {}
    except Exception:
        info = {}
    growth = info.get("revenueGrowth")
    return {
        "ticker": sym,
        "name": info.get("longName") or info.get("shortName") or "n/a",
        "industry": info.get("industry") or "n/a",
        "country": info.get("country") or "n/a",
        "market_cap_bn": _fmt_bn(info.get("marketCap")),
        "revenue_bn": _fmt_bn(info.get("totalRevenue")),
        "revenue_growth": f"{growth * 100:.0f}%" if isinstance(growth, (int, float)) else "n/a",
        "has_data": info.get("totalRevenue") is not None,
        "business": " ".join((info.get("longBusinessSummary") or "n/a").split()[:28]) + "...",
        "_rev": info.get("totalRevenue"),
    }


def get_peer_candidates(
    ticker_symbol: Annotated[str, "ticker symbol of the company under analysis"],
    extra_tickers: Annotated[
        List[str],
        "optional additional US ticker symbols you consider relevant (e.g. listed competitors named in the 10-K); they are checked and added to the list",
    ] = None,
    max_candidates: Annotated[int, "maximum number of Finnhub candidates to check, default 12"] = 12,
) -> str:
    """Find candidate peer companies: same-industry companies from Finnhub plus optional extra tickers, each with name, industry, country, market cap, revenue and size relative to the company (from Yahoo Finance), sorted by size similarity. Use it before the competitor analysis to choose 3 comparable, US-listed peers with available financials (similar business model first, then size), and state briefly why you chose them."""
    note = ""
    try:
        import finnhub
        key = os.environ.get("FINNHUB_API_KEY")
        if not key:
            raise RuntimeError("FINNHUB_API_KEY is not set in config_api_keys")
        candidates = finnhub.Client(api_key=key).company_peers(ticker_symbol) or []
    except Exception as e:
        candidates = []
        note = f"Note: Finnhub peer search failed ({type(e).__name__}: {e}); only extra tickers were checked. "
        if not extra_tickers:
            return note + "Do not invent peers; ask the user for peer tickers or pass extra_tickers."
    candidates = [c for c in candidates if c and c.upper() != ticker_symbol.upper()][:max_candidates]
    for c in extra_tickers or []:
        c = c.strip().upper()
        if c and c != ticker_symbol.upper() and c not in candidates:
            candidates.append(c)
    if not candidates:
        return "No peer candidates found. Do not invent peers; ask the user for peer tickers."
    own = _profile(ticker_symbol)
    own_rev = own.pop("_rev")
    rows = []
    for c in candidates:
        r = _profile(c)
        rev = r.pop("_rev")
        r["size_ratio"] = (rev / own_rev) if rev and own_rev else None
        rows.append(r)
    rows.sort(key=lambda r: abs(math.log(r["size_ratio"])) if r["size_ratio"] else 99)
    lines = ["ticker | name | industry | country | market cap (USD bn) | revenue (USD bn) | revenue growth | revenue vs company | business",
             f"{own['ticker']} | {own['name']} (company under analysis) | {own['industry']} | {own['country']} | "
             f"{own['market_cap_bn']} | {own['revenue_bn']} | {own['revenue_growth']} | 1.0x | {own['business']}"]
    for r in rows:
        mark = "" if r["has_data"] else " (no revenue data, avoid)"
        ratio = f"{r['size_ratio']:.1f}x" if r["size_ratio"] else "n/a"
        lines.append(f"{r['ticker']} | {r['name']}{mark} | {r['industry']} | {r['country']} | "
                     f"{r['market_cap_bn']} | {r['revenue_bn']} | {r['revenue_growth']} | {ratio} | {r['business']}")
    lines.append("")
    if note:
        lines.append(note)
    lines.append("Finnhub groups companies by industry, so very large conglomerates can appear. Choose the 3 most comparable peers "
                 "by business model first and size second (see 'revenue vs company'). Prefer companies with revenue data. "
                 "Use exactly these ticker symbols and names; do not add companies that are not in this list.")
    return "\n".join(lines)
