"""
FMPUtils – Ersatz-Implementierung ohne FMP.

Hintergrund: FinRobot rief die alten FMP-Endpunkte (/api/v3, /api/v4) auf. Diese sind fuer
neue Konten gesperrt (403 "Legacy Endpoint"), und der kostenlose Plan der neuen /stable-API
deckt Kennzahlen nur fuer ausgewaehlte Ticker ab (402 "Premium Query Parameter", z. B. RKLB).

Diese Version behaelt Klassen- und Methodennamen bei, damit der Rest von FinRobot
unveraendert funktioniert, holt die Daten aber aus kostenlosen Quellen:
  * SEC EDGAR (Originalquelle) fuer 10-K-Link und Einreichungsdatum
  * Yahoo Finance (yfinance) fuer Abschluesse, Kurse und Analysten-Kursziel

Grundsatz: Fehlt ein Wert, wird er als "n/a" ausgewiesen oder es wird ein klarer Fehler
ausgeloest. Es wird nie still ein Ersatzwert eingesetzt.

Voraussetzung: Umgebungsvariable SEC_USER_AGENT (Name + Kontakt, von der SEC verlangt),
z. B. als Eintrag in config_api_keys.
"""

import os
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated, List

import pandas as pd
import requests
import yfinance as yf

from ..utils import get_next_weekday

NA = "n/a"


# ---------------------------------------------------------------- SEC EDGAR
def _sec_headers() -> dict:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError(
            "SEC_USER_AGENT ist nicht gesetzt. Bitte in config_api_keys eintragen "
            '(z. B. "SEC_USER_AGENT": "Vorname Nachname kontakt@beispiel.de").'
        )
    return {"User-Agent": ua}


@lru_cache(maxsize=1)
def _ticker_to_cik() -> dict:
    r = requests.get(
        "https://www.sec.gov/files/company_tickers.json", headers=_sec_headers(), timeout=30
    )
    r.raise_for_status()
    return {v["ticker"].upper(): int(v["cik_str"]) for v in r.json().values()}


def _find_10k(ticker_symbol: str, fyear: str) -> dict:
    """Sucht ein 10-K in EDGAR. fyear = Geschaeftsjahr (Periodenende) oder 'latest'."""
    cik = _ticker_to_cik().get(ticker_symbol.upper())
    if cik is None:
        raise ValueError(
            f"Ticker '{ticker_symbol}' ist bei der SEC nicht registriert. "
            "Nicht-US-Firmen ohne SEC-Berichte (z. B. Euronext-Werte) haben kein 10-K."
        )
    r = requests.get(
        f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_sec_headers(), timeout=30
    )
    r.raise_for_status()
    rec = r.json()["filings"]["recent"]
    filings = [
        {"form": f, "filing_date": d, "report_date": rd, "accession": a, "doc": p}
        for f, d, rd, a, p in zip(
            rec["form"], rec["filingDate"], rec["reportDate"],
            rec["accessionNumber"], rec["primaryDocument"],
        )
        if f in ("10-K", "10-K/A")
    ]
    originals = [f for f in filings if f["form"] == "10-K"] or filings
    if not originals:
        raise ValueError(f"Keine 10-K-Einreichung fuer {ticker_symbol} in EDGAR gefunden.")
    if str(fyear).lower() == "latest":
        hit = originals[0]
    else:
        hits = [f for f in originals if f["report_date"][:4] == str(fyear)]
        if not hits:
            available = sorted({f["report_date"][:4] for f in originals}, reverse=True)
            raise ValueError(
                f"Kein 10-K fuer Geschaeftsjahr {fyear} von {ticker_symbol}. "
                f"Verfuegbare Geschaeftsjahre: {available}"
            )
        hit = hits[0]
    hit["url"] = (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{hit['accession'].replace('-', '')}/{hit['doc']}"
    )
    return hit


# ---------------------------------------------------------------- Helfer
def _val(df: pd.DataFrame, row: str, col):
    """Einzelwert als float oder None (fehlende Zeile, Spalte oder NaN)."""
    if df is None or df.empty or row not in df.index or col not in df.columns:
        return None
    v = df.at[row, col]
    return None if pd.isna(v) else float(v)


def _first(df, rows, col):
    for r in rows:
        v = _val(df, r, col)
        if v is not None:
            return v
    return None


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def _price_on_or_before(prices: pd.Series, date) -> float | None:
    if prices is None or prices.empty:
        return None
    date = pd.Timestamp(date)
    if prices.index.tz is not None:
        date = date.tz_localize(prices.index.tz)
    sub = prices[prices.index <= date]
    return None if sub.empty else float(sub.iloc[-1])


def _fmt_mn(v):
    return NA if v is None else round(v / 1e6)


def _fmt_ratio(v, positive_only=False):
    if v is None or (positive_only and v <= 0):
        return NA if v is None else "n/m"
    return round(v, 2)


def _fmt_pct(v):
    return NA if v is None else "{}%".format(round(v * 100, 1))


def metrics_from_frames(inc, bs, cf, prices, years: int = 4) -> pd.DataFrame:
    """Berechnet die Kennzahlen-Tabelle aus Jahresabschluessen (Spalten = Stichtage).
    Getrennt von den Downloads, damit sie ohne Internet testbar ist."""
    # Geschaeftsjahre ohne Umsatz (Yahoo liefert teils leere Spalten) werden verworfen
    inc = inc[[c for c in inc.columns if _val(inc, "Total Revenue", c) is not None]]
    cols = sorted(inc.columns, reverse=True)[:years]
    out = {}
    for i, c in enumerate(cols):
        rev = _val(inc, "Total Revenue", c)
        prev_c = sorted(inc.columns, reverse=True)[i + 1] if i + 1 < len(inc.columns) else None
        prev_rev = _val(inc, "Total Revenue", prev_c) if prev_c is not None else None
        gp = _val(inc, "Gross Profit", c)
        ebitda = _first(inc, ["EBITDA", "Normalized EBITDA"], c)
        ebit = _first(inc, ["EBIT", "Operating Income"], c)
        ni = _first(inc, ["Net Income", "Net Income Common Stockholders"], c)
        eps = _first(inc, ["Diluted EPS", "Basic EPS"], c)
        tax = _val(inc, "Tax Rate For Calcs", c)
        shares = _first(bs, ["Ordinary Shares Number", "Share Issued"], c) or _first(
            inc, ["Diluted Average Shares", "Basic Average Shares"], c
        )
        equity = _first(bs, ["Stockholders Equity", "Common Stock Equity"], c)
        debt = _val(bs, "Total Debt", c) or 0.0
        cash = _first(bs, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"], c) or 0.0
        invested = _val(bs, "Invested Capital", c)
        fcf = _val(cf, "Free Cash Flow", c)
        if fcf is None:
            ocf, capex = _val(cf, "Operating Cash Flow", c), _val(cf, "Capital Expenditure", c)
            fcf = None if ocf is None or capex is None else ocf + capex
        price = _price_on_or_before(prices, c)
        mcap = None if price is None or shares is None else price * shares
        ev = None if mcap is None else mcap + debt - cash
        nopat = None if ebit is None else ebit * (1 - (tax or 0.0))

        out[str(pd.Timestamp(c).year)] = {
            "Revenue": _fmt_mn(rev),
            "Revenue Growth": _fmt_pct(_div(None if rev is None or prev_rev is None else rev - prev_rev, prev_rev)),
            "Gross Profit": _fmt_mn(gp),
            "Gross Margin": _fmt_pct(_div(gp, rev)),
            "EBITDA": _fmt_mn(ebitda),
            "EBITDA Margin": _fmt_pct(_div(ebitda, rev)),
            "FCF": _fmt_mn(fcf),
            "FCF Conversion": _fmt_ratio(_div(fcf, ni)) if (ni or 0) > 0 else "n/m",
            "ROIC": _fmt_pct(_div(nopat, invested)),
            "EV/EBITDA": _fmt_ratio(_div(ev, ebitda), positive_only=True) if (ebitda or 0) > 0 else "n/m",
            "EV/Sales": _fmt_ratio(_div(ev, rev), positive_only=True),
            "PE Ratio": _fmt_ratio(_div(price, eps), positive_only=True) if (eps or 0) > 0 else "n/m",
            "PB Ratio": _fmt_ratio(_div(mcap, equity), positive_only=True) if (equity or 0) > 0 else "n/m",
        }
    df = pd.DataFrame(out)
    return df.sort_index(axis=1)


def _load_frames(ticker_symbol: str):
    t = yf.Ticker(ticker_symbol)
    inc, bs, cf = t.income_stmt, t.balance_sheet, t.cashflow
    if inc is None or inc.empty:
        raise ValueError(f"Yahoo Finance liefert keine Jahresabschluesse fuer '{ticker_symbol}'.")
    start = (min(inc.columns) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    hist = t.history(start=start, auto_adjust=False)
    prices = hist["Close"] if not hist.empty else pd.Series(dtype=float)
    return inc, bs, cf, prices


# ---------------------------------------------------------------- Klasse (Schnittstelle wie FinRobot)
class FMPUtils:

    def get_target_price(
        ticker_symbol: Annotated[str, "ticker symbol"],
        date: Annotated[str, "date of the target price, should be 'yyyy-mm-dd'"],
    ) -> str:
        """Get the analyst consensus target price for a given stock (current Yahoo Finance consensus; historical values are not available)."""
        info = yf.Ticker(ticker_symbol).info or {}
        mean, low, high = info.get("targetMeanPrice"), info.get("targetLowPrice"), info.get("targetHighPrice")
        if mean is None:
            return "Not Given"
        rng = f" (range {low:.2f} - {high:.2f})" if low and high else ""
        return f"{mean:.2f}{rng}, current consensus as of {datetime.now():%Y-%m-%d}, not as of {date}"

    def get_sec_report(
        ticker_symbol: Annotated[str, "ticker symbol"],
        fyear: Annotated[
            str,
            "fiscal year of the 10-K report (period end), should be 'yyyy' or 'latest'. Default to 'latest'",
        ] = "latest",
    ) -> str:
        """Get the url and filing date of the 10-K report for a given stock and fiscal year from SEC EDGAR"""
        hit = _find_10k(ticker_symbol, fyear)
        return (
            f"Link: {hit['url']}\nFiling Date: {hit['filing_date']}\n"
            f"Fiscal Period End: {hit['report_date']}"
        )

    def get_historical_market_cap(
        ticker_symbol: Annotated[str, "ticker symbol"],
        date: Annotated[str, "date of the market cap, should be 'yyyy-mm-dd'"],
    ) -> float:
        """Get the market capitalization for a given stock on a given date (close price x shares from the latest balance sheet before that date)"""
        date = get_next_weekday(date)
        t = yf.Ticker(ticker_symbol)
        hist = t.history(start=(date - timedelta(days=10)).strftime("%Y-%m-%d"),
                         end=(date + timedelta(days=1)).strftime("%Y-%m-%d"), auto_adjust=False)
        price = _price_on_or_before(hist["Close"] if not hist.empty else None, date)
        bs = t.balance_sheet
        cols = [c for c in (bs.columns if bs is not None else []) if pd.Timestamp(c) <= pd.Timestamp(date)]
        shares = _first(bs, ["Ordinary Shares Number", "Share Issued"], max(cols)) if cols else None
        if shares is None:
            shares = (t.info or {}).get("sharesOutstanding")
        if price is None or shares is None:
            raise ValueError(f"Marktkapitalisierung fuer {ticker_symbol} am {date:%Y-%m-%d} nicht bestimmbar (Kurs oder Aktienzahl fehlt).")
        return price * shares

    def get_historical_bvps(
        ticker_symbol: Annotated[str, "ticker symbol"],
        target_date: Annotated[str, "date of the BVPS, should be 'yyyy-mm-dd'"],
    ) -> float:
        """Get the book value per share from the latest balance sheet on or before a given date"""
        bs = yf.Ticker(ticker_symbol).balance_sheet
        cols = [c for c in (bs.columns if bs is not None else []) if pd.Timestamp(c) <= pd.Timestamp(target_date)]
        if not cols:
            raise ValueError(f"Keine Bilanz fuer {ticker_symbol} vor {target_date} verfuegbar.")
        c = max(cols)
        bvps = _div(_first(bs, ["Stockholders Equity", "Common Stock Equity"], c),
                    _first(bs, ["Ordinary Shares Number", "Share Issued"], c))
        if bvps is None:
            raise ValueError(f"BVPS fuer {ticker_symbol} zum {c:%Y-%m-%d} nicht bestimmbar.")
        return bvps

    def get_financial_metrics(
        ticker_symbol: Annotated[str, "ticker symbol"],
        years: Annotated[int, "number of the years to search from, default to 4"] = 4,
    ) -> pd.DataFrame:
        """Get the financial metrics for a given stock for the last 'years' fiscal years (Yahoo Finance; usually max. 4 years)"""
        return metrics_from_frames(*_load_frames(ticker_symbol), years=years)

    def get_competitor_financial_metrics(
        ticker_symbol: Annotated[str, "ticker symbol"],
        competitors: Annotated[List[str], "list of competitor ticker symbols (e.g. 'NOC', not company names)"],
        years: Annotated[int, "number of the years to search from, default to 4"] = 4,
    ) -> dict:
        """Get financial metrics for the company and its competitors (ticker symbols required)."""
        all_data, failed = {}, []
        for symbol in [ticker_symbol] + list(competitors):
            try:
                all_data[symbol] = FMPUtils.get_financial_metrics(symbol, years)
            except Exception as e:
                failed.append(f"{symbol}: {e}")
        if failed:
            raise ValueError(
                "Kennzahlen nicht abrufbar fuer: " + "; ".join(failed)
                + ". Hinweis: Es werden Ticker-Symbole benoetigt (z. B. 'NOC'), keine Firmennamen."
            )
        return all_data


if __name__ == "__main__":
    from finrobot.utils import register_keys_from_json

    register_keys_from_json("config_api_keys")
    print(FMPUtils.get_sec_report("RKLB", "2025"))
    print(FMPUtils.get_financial_metrics("RKLB"))
