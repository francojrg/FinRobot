"""
Bereinigte Varianten zweier Finnhub-Tools aus FinRobot (eigene Ergaenzung, Prompt-Version v3 des Forecasters).

Probleme im Original (finrobot/data_source/finnhub_utils.py):
1. get_company_news zieht bei mehr als max_news_num Meldungen eine ZUFAELLIGE Auswahl MIT Zuruecklegen
   (random.choices): Duplikate moeglich, wichtige Meldungen fehlen, jeder Lauf sieht andere News.
   -> Hier: Duplikate (gleiche Schlagzeile) entfernen, die NEUESTEN max_news_num Meldungen nehmen.
2. get_company_profile bettet jede Firma in denselben Werbetext ein ("a leading entity", "one of the key
   players", "a dominant force ... continues to innovate") - unabhaengig von den Daten.
   -> Hier: nur die Fakten aus Finnhub, neutral formuliert.
"""
import os
from datetime import datetime
from typing import Annotated

import pandas as pd


def _client():
    import finnhub
    key = os.environ.get("FINNHUB_API_KEY")
    if not key:
        raise RuntimeError("FINNHUB_API_KEY ist nicht gesetzt (config_api_keys).")
    return finnhub.Client(api_key=key)


def get_company_news(
    symbol: Annotated[str, "ticker symbol"],
    start_date: Annotated[str, "start date of the news search period, yyyy-mm-dd"],
    end_date: Annotated[str, "end date of the news search period, yyyy-mm-dd"],
    max_news_num: Annotated[int, "maximum number of news to return, default to 10"] = 10,
) -> str:
    """retrieve the most recent market news (headline and summary) for a company, without duplicates"""
    news = _client().company_news(symbol, _from=start_date, to=end_date)
    seen, rows = set(), []
    for n in sorted(news, key=lambda x: x.get("datetime", 0), reverse=True):
        key = (n.get("headline") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append({"date": datetime.fromtimestamp(n["datetime"]).strftime("%Y-%m-%d %H:%M"),
                     "source": n.get("source", ""), "headline": n["headline"], "summary": n.get("summary", "")})
        if len(rows) >= int(max_news_num):
            break
    if not rows:
        return f"No company news found for {symbol} between {start_date} and {end_date}."
    df = pd.DataFrame(sorted(rows, key=lambda r: r["date"]))
    return (f"{len(df)} most recent news items for {symbol} ({start_date} to {end_date}; "
            f"{len(news)} found in total):\n" + df.to_string(index=False))


def get_company_profile(symbol: Annotated[str, "ticker symbol"]) -> str:
    """get a company's profile information (facts only)"""
    p = _client().company_profile2(symbol=symbol)
    if not p:
        return f"Failed to find company profile for symbol {symbol} from finnhub!"
    return (f"{p.get('name')} ({p.get('ticker')}, {p.get('exchange')}). Industry: {p.get('finnhubIndustry')}. "
            f"Country: {p.get('country')}. IPO: {p.get('ipo')}. Market capitalization: "
            f"{p.get('marketCapitalization', 0):,.0f} million {p.get('currency')}. Shares outstanding: "
            f"{p.get('shareOutstanding', 0):,.1f} million.")
