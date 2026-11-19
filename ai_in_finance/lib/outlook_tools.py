"""
Agent-Tool: Konsensschaetzungen und Liquiditaet (eigene Erweiterung).

Die Zahlen berechnet finrobot/functional/outlook.py deterministisch aus Yahoo-Finance-Daten.
Dieselben Werte erscheinen im PDF als Exhibit 3 (E-Spalten) und als Liquiditaets-Exhibit,
und sie fliessen in den Faktencheck ein.
"""
from typing import Annotated

from finrobot.functional.outlook import outlook_text


def get_consensus_and_liquidity(
    ticker_symbol: Annotated[str, "ticker symbol, e.g. 'RKLB'"],
    fyear: Annotated[str, "fiscal year of the analyzed 10-K, e.g. '2025'"],
) -> str:
    """
    Analyst consensus estimates (revenue and EPS for the current and next fiscal year, forward multiples)
    and liquidity/funding data (cash, debt, net cash, free cash flow burn, cash runway, current ratio,
    share count change) at the 10-K fiscal year end and the latest quarter. Use it for the key takeaways,
    the investment summary and the valuation/funding discussion. Consensus figures are cited as [3],
    balance sheet and cash flow figures as [2]; both are dated after the 10-K.
    """
    try:
        return outlook_text(ticker_symbol, fyear)
    except Exception as e:
        return f"Consensus and liquidity data not available ({e}). Do not state any estimates."
