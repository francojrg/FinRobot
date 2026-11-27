"""
FinGPT-Forecaster, wie im FinRobot-Tutorial (tutorials_advanced/agent_fingpt_forecaster.ipynb), mit kleinen
Ergaenzungen fuer die Auswertung.

Original: Ein "Market_Analyst" holt Firmenprofil, News und Basis-Kennzahlen (Finnhub) sowie Kursdaten (Yahoo),
nennt 2-4 positive Entwicklungen und 2-4 Bedenken und sagt die Kursbewegung der naechsten Woche grob voraus
(z. B. "up 2-3%").

Ergaenzungen:
- Modell ueber OpenRouter; Ticker statt Firmenname; Datum automatisch.
- Feste Schlusszeile "PREDICTION: UP|DOWN <von>-<bis>%", damit die Vorhersage maschinell auswertbar ist.
- Jede Vorhersage wird mit Schlusskurs am Prognosetag in forecasts/forecast_log.csv protokolliert;
  scripts/score_forecasts.py prueft sie eine Woche spaeter gegen den tatsaechlichen Kurs.
- Optional (extended=True): zusaetzlich Konsens, Revisionen und Quality Scores (outlook.py).
- Ab v3: News und Profil ueber lib/news_tools.py (neueste News ohne Duplikate, neutrales Profil).
"""
import csv
import os
import re
from datetime import date, datetime
from pathlib import Path

import autogen
from . import agent_settings as _AS  # Prompts/Parameter aus der App (research/agent_settings.json)
from finrobot.data_source import FinnHubUtils, YFinanceUtils
from finrobot.toolkits import register_toolkits

from . import news_tools
from .outlook_tools import get_consensus_and_liquidity

AIF = Path(__file__).resolve().parents[1]
LOG = AIF / "forecasts" / "forecast_log.csv"
PROMPT_VERSION = "v3"
# v1: Formatbeispiel mit Zahlen ("DOWN 1-2%") -> Modell uebernahm die Spanne fast immer
# v2: Format ohne Zahlenbeispiel
# v3: zusaetzlich neueste News ohne Duplikate statt Zufallsauswahl, neutrales Firmenprofil (lib/news_tools.py)
PRED_RE = re.compile(r"PREDICTION:\s*(UP|DOWN|FLAT)\s*(?:by\s*)?(\d+(?:\.\d+)?)?\s*(?:-|to|–)?\s*(\d+(?:\.\d+)?)?\s*%?", re.I)

SYSTEM = ("As a Market Analyst, one must possess strong analytical and problem-solving abilities, collect necessary "
          "financial information and aggregate them based on client's requirement. For coding tasks, only use the "
          "functions you have been provided with. Reply TERMINATE when the task is done.")


def build_forecaster(llm_config, extended=False):
    analyst = autogen.AssistantAgent(name="Market_Analyst", system_message=_AS.get("forecast.system", SYSTEM), llm_config=llm_config)
    user_proxy = autogen.UserProxyAgent(
        name="User_Proxy",
        is_termination_msg=lambda x: x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE"),
        human_input_mode="NEVER",
        max_consecutive_auto_reply=10,
        code_execution_config=False,
    )
    tools = [
        {"function": news_tools.get_company_profile, "name": "get_company_profile",
         "description": "get a company's profile information"},
        {"function": news_tools.get_company_news, "name": "get_company_news",
         "description": "retrieve the most recent market news related to designated company"},
        {"function": FinnHubUtils.get_basic_financials, "name": "get_financial_basics",
         "description": "get latest financial basics for a designated company"},
        {"function": YFinanceUtils.get_stock_data, "name": "get_stock_data",
         "description": "retrieve stock price data for designated ticker symbol"},
    ]
    if extended:
        tools.append({"function": get_consensus_and_liquidity, "name": "get_consensus_and_liquidity",
                      "description": get_consensus_and_liquidity.__doc__})
    register_toolkits(tools, analyst, user_proxy)
    return analyst, user_proxy


def forecast_message(ticker, today=None):
    today = today or date.today().isoformat()
    return (f"Use all the tools provided to retrieve information available for {ticker} upon {today}. Analyze the positive "
            f"developments and potential concerns of {ticker} with 2-4 most important factors respectively and keep them "
            "concise. Most factors should be inferred from company related news. "
            f"Then make a rough prediction (e.g. up/down by 2-3%) of the {ticker} stock price movement for next week. "
            "Provide a summary analysis to support your prediction. End your answer with one line in the format "
            "'PREDICTION: <UP|DOWN|FLAT> <low>-<high>%' with direction and range taken from your own analysis "
            "(the format shows the structure only; any direction and size is allowed), followed by TERMINATE.")


def parse_prediction(text):
    m = None
    for m in PRED_RE.finditer(text or ""):
        pass
    if not m:
        return None
    direction = m.group(1).upper()
    lo = float(m.group(2)) if m.group(2) else None
    hi = float(m.group(3)) if m.group(3) else lo
    sign = {"UP": 1, "DOWN": -1, "FLAT": 0}[direction]
    mid = None if lo is None else sign * (lo + hi) / 2
    return {"direction": direction, "low": lo, "high": hi, "mid_pct": mid}


def _last_close(ticker):
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="5d")
        return float(h["Close"].dropna().iloc[-1]), str(h.index[-1].date())
    except Exception:
        return None, None


def forecast(llm_config, ticker, model_name="", extended=False, out_dir=None):
    ticker = ticker.upper()
    analyst, user_proxy = build_forecaster(llm_config, extended)
    user_proxy.initiate_chat(analyst, message=forecast_message(ticker) + _AS.extra("forecast.extra"), cache=None)
    msgs = analyst.chat_messages.get(user_proxy, [])  # aus Sicht des Analysten: eigene Nachrichten = "assistant"
    answer = ""
    for m in reversed(msgs):
        c = str(m.get("content") or "")
        if m.get("role") == "assistant" and "PREDICTION" in c.upper():
            answer = c
            break
    if not answer:
        answer = next((str(m.get("content")) for m in reversed(msgs) if m.get("role") == "assistant" and m.get("content")), "")
    pred = parse_prediction(answer)
    close, close_date = _last_close(ticker)
    out_dir = Path(out_dir or AIF / "forecasts")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    md = out_dir / f"{ticker}_{stamp}_forecast.md"
    md.write_text(f"# Forecast {ticker} ({stamp})\n\n{answer}\n", encoding="utf-8")
    header = ["timestamp", "ticker", "model", "extended", "direction", "low_pct", "high_pct", "mid_pct",
              "close", "close_date", "answer_file", "prompt_version"]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if LOG.exists():  # aeltere Protokolle ohne prompt_version-Spalte ergaenzen (= v1)
        rows = list(csv.reader(open(LOG, encoding="utf-8")))
        if rows and "prompt_version" not in rows[0]:
            with open(LOG, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(rows[0] + ["prompt_version"])
                w.writerows(r + ["v1"] for r in rows[1:] if r)
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(header)
        w.writerow([stamp, ticker, model_name, extended, (pred or {}).get("direction", "n/a"),
                    (pred or {}).get("low"), (pred or {}).get("high"), (pred or {}).get("mid_pct"),
                    close, close_date, md.name, PROMPT_VERSION])
    print(f"\nVorhersage: {pred}  |  Schlusskurs {close} ({close_date})  |  gespeichert: {md}")
    return answer, pred
