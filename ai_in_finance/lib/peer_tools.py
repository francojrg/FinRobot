"""
Eigenes Tool: Peer-Kandidaten automatisch finden.

Ablauf: Finnhub liefert Unternehmen aus derselben Branche (kostenloser Endpunkt /stock/peers).
Fuer jeden Kandidaten werden Name, Branche, Land, Marktkapitalisierung und Umsatz von Yahoo
Finance ergaenzt. Der Agent waehlt daraus die vergleichbarsten Peers aus und begruendet die Wahl.
Faellt Finnhub aus, bekommt der Agent einen klaren Hinweis statt still erfundener Peers.
"""
import os
from typing import Annotated

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
    }


def get_peer_candidates(
    ticker_symbol: Annotated[str, "ticker symbol of the company under analysis"],
    max_candidates: Annotated[int, "maximum number of candidates to return, default 12"] = 12,
) -> str:
    """Find candidate peer companies (same industry, via Finnhub) with name, industry, country, market cap and revenue from Yahoo Finance. Use it before the competitor analysis to choose 3 comparable, US-listed peers with available financials, and state briefly why you chose them."""
    try:
        import finnhub
        key = os.environ.get("FINNHUB_API_KEY")
        if not key:
            return "Peer search not possible: FINNHUB_API_KEY is not set in config_api_keys. Ask the user for peer tickers."
        candidates = finnhub.Client(api_key=key).company_peers(ticker_symbol) or []
    except Exception as e:
        return f"Peer search failed ({type(e).__name__}: {e}). Do not invent peers; ask the user for peer tickers."
    candidates = [c for c in candidates if c and c.upper() != ticker_symbol.upper()][:max_candidates]
    if not candidates:
        return "Finnhub returned no peer candidates. Do not invent peers; ask the user for peer tickers."
    own = _profile(ticker_symbol)
    rows = [own] + [_profile(c) for c in candidates]
    lines = ["ticker | name | industry | country | market cap (USD bn) | revenue (USD bn) | revenue growth"]
    for r in rows:
        mark = " (company under analysis)" if r["ticker"] == ticker_symbol else ("" if r["has_data"] else " (no revenue data, avoid)")
        lines.append(f"{r['ticker']} | {r['name']}{mark} | {r['industry']} | {r['country']} | "
                     f"{r['market_cap_bn']} | {r['revenue_bn']} | {r['revenue_growth']}")
    lines.append("")
    lines.append("Choose the 3 most comparable peers by business model and size. Prefer companies with revenue data. "
                 "Use exactly these ticker symbols and names; do not add companies that are not in this list.")
    return "\n".join(lines)
