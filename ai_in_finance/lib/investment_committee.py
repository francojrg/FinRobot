"""
Investment Committee: FinRobots Experiment "portfolio_optimization.py" (finrobot_autogen/experiments),
uebertragen auf unsere Umgebung.

Was das Original macht (trotz des Dateinamens kein klassischer Portfolio-Optimierer):
Ein Chief Investment Officer (CIO) leitet drei Analystengruppen (Market Sentiment, Risk Assessment,
Fundamental) mit je einem Senior Analyst als Gruppenleiter. Auftraege laufen hierarchisch ueber
verschachtelte Chats ("[Name] Auftrag"). Ergebnis: Bewertung, 6-Monats-Kursziel und Empfehlung fuer eine Aktie.

Anpassungen gegenueber dem Original (alles andere - Rollen, Hierarchie, Workflow-Klassen - unveraendert):
- Gruppen-Konfiguration wird aus experiments/investment_group.py geladen und nur ergaenzt.
- Modell ueber OpenRouter statt gpt-4-0125-preview.
- RAG ueber eine fest eingetragene PDD-20-F-URL ersetzt durch Stichwortsuche im gecachten 10-K der gewaehlten
  Firma (das Original uebergibt zudem versehentlich ein Tupel an register_function und laeuft so nicht).
- Reddit-Tool entfernt (keine Reddit-Zugangsdaten noetig); Finnhub-News bleiben.
- Zusaetzliches Tool fuer Risk und Fundamental: Konsens, Liquiditaet, Reverse DCF, Quality Scores (outlook.py).
- Firma, Datum und Geschaeftsjahr sind Parameter statt fest "PDD, 2023-04-26".
- Keine Ausfuehrung von generiertem Python-Code auf dem Rechner (code_execution_config=False); Agenten nutzen Tools.
"""
import copy
import json
import os
import sys
from datetime import date
from pathlib import Path
from textwrap import dedent

import autogen
from autogen import register_function

from finrobot.agents.workflow import MultiAssistant, MultiAssistantWithLeader

from .outlook_tools import get_consensus_and_liquidity
from .tenk_search import make_tenk_search

FR = Path(__file__).resolve().parents[2] / "finrobot_autogen"
WITH_LEADER = {"Market Sentiment Analysts": True, "Risk Assessment Analysts": True, "Fundamental Analysts": True}


def _load_group_config():
    """Originale Gruppen-Konfiguration aus FinRobots experiments-Ordner."""
    sys.path.insert(0, str(FR / "experiments"))
    try:
        from investment_group import group_config  # noqa: E402
    finally:
        sys.path.pop(0)
    return copy.deepcopy(group_config)


def _patch_toolkits(cfg):
    """Reddit entfernen, eigenes Tool fuer Risk/Fundamental ergaenzen."""
    for gname, g in cfg["groups"].items():
        for variant in ("with_leader", "without_leader"):
            for emp in g[variant]["employees"]:
                tools = [t for t in emp.get("toolkits", []) if getattr(t, "__name__", "") != "get_reddit_posts"]
                if gname in ("Risk Assessment Analysts", "Fundamental Analysts"):
                    tools.append(get_consensus_and_liquidity)
                emp["toolkits"] = tools
    return cfg


def build_committee(llm_config, ticker, fyear, max_auto_reply=20):
    # Leiter-Agenten haben keine Tools; manche APIs lehnen parallel_tool_calls ohne Tools ab
    llm_config = {k: v for k, v in llm_config.items() if k != "parallel_tool_calls"}
    cfg = _patch_toolkits(_load_group_config())
    user_proxy = autogen.UserProxyAgent(
        name="User",
        human_input_mode="NEVER",
        is_termination_msg=lambda x: x.get("content", "") and "TERMINATE" in x.get("content", ""),
        max_consecutive_auto_reply=max_auto_reply,
        code_execution_config=False,
    )
    search_10k = make_tenk_search(ticker, fyear)
    representatives, groups = [], []
    for group_name, single in cfg["groups"].items():
        members = single["with_leader"] if WITH_LEADER.get(group_name) else single["without_leader"]
        members["agents"] = members.pop("employees")
        cls = MultiAssistantWithLeader if WITH_LEADER.get(group_name) else MultiAssistant
        group = cls(members, llm_config=llm_config, user_proxy=user_proxy)
        for agent in group.agents:
            register_function(search_10k, caller=agent, executor=group.user_proxy, name="search_10k",
                              description=search_10k.__doc__)
        representatives.append(group.representative)
        groups.append(group)
    main = MultiAssistantWithLeader({"leader": cfg["CIO"], "agents": representatives},
                                    llm_config=llm_config, user_proxy=user_proxy)
    return main, groups, user_proxy


def committee_task(ticker, fyear, today=None):
    today = today or date.today().isoformat()
    return dedent(f"""
        Subject: Evaluate Investment Potential and Determine 6-Month Target Price for {ticker}

        Task Description:

        Today is {today}. As the Chief Investment Officer, your task is to evaluate the potential investment in {ticker}
        based on its annual report (Form 10-K for fiscal year {fyear}) and recent market news. Coordinate with the
        Market Sentiment Analysts, Risk Assessment Analysts, and Fundamental Analysts to gather and analyze the
        relevant information. Your final deliverable should include a comprehensive evaluation, a 6-month target price
        for {ticker}'s stock, and a recommendation on whether to invest. This is an academic exercise, not investment advice.

        Notes (all members in your group should be informed):
        - Use only the provided tools (search_10k, company news, stock data, financial metrics, consensus and
          liquidity data). Do not write code. Do not invent figures; state the source of every number.

        [Coordinate with Market Sentiment Analysts]:
        Task: Analyze recent market sentiment around {ticker} based on company news of the last 1-3 months.
        Deliverable: A sentiment score based on positive and negative news, with the main drivers.

        [Coordinate with Risk Assessment Analysts]:
        Task: Assess financial and operational risks from the 10-K (risk factors, liquidity, debt, regulation, legal).
        Deliverable: A risk score with the key risks and the data behind them.

        [Coordinate with Fundamental Analysts]:
        Task: Analyze {ticker}'s financial health based on the 10-K and financial data.
        Deliverable: Key metrics such as growth, margins, return on assets, valuation multiples and consensus estimates.

        [Determine 6-Month Target Price]:
        Task: Based on the integrated analysis, calculate a 6-month target price and explain the method.

        [Final Deliverable]:
        Integrate the findings, give the 6-month target price, a recommendation (buy / hold / sell) with rationale,
        and end with a line "TARGET PRICE: <number>" and a line "RECOMMENDATION: <buy|hold|sell>".
    """).strip()


def run_committee(llm_config, ticker, fyear, out_dir, max_auto_reply=20, max_turns=30):
    """Startet das Komitee und speichert Abschlussbericht und Verlauf als Markdown."""
    ticker = ticker.upper()
    os.makedirs(out_dir, exist_ok=True)
    main, groups, user_proxy = build_committee(llm_config, ticker, fyear, max_auto_reply)
    task = committee_task(ticker, fyear)
    result = user_proxy.initiate_chat(main.representative, message=task, cache=None, max_turns=max_turns)
    history = user_proxy.chat_messages.get(main.representative, [])
    own = [m for m in main.representative.chat_messages.get(user_proxy, []) if m.get("role") == "assistant"]
    final = next((str(m.get("content")) for m in reversed(own) if "TARGET PRICE" in str(m.get("content", ""))), "")
    if not final and own:
        final = str(own[-1].get("content", ""))
    stamp = date.today().isoformat()
    base = Path(out_dir) / f"{ticker}_{stamp}"
    Path(str(base) + "_committee.md").write_text(f"# Investment Committee: {ticker} ({stamp})\n\n{final}\n", encoding="utf-8")
    with open(str(base) + "_transcript.md", "w", encoding="utf-8") as f:
        f.write(f"# Transcript: {ticker} ({stamp})\n\n")
        for m in history:
            f.write(f"## {m.get('name') or m.get('role')}\n\n{m.get('content') or ''}\n\n")
    usage = {}
    for a in [main.representative] + [g.representative for g in groups] + [x for g in groups for x in g.agents]:
        summ = getattr(getattr(a, "client", None), "total_usage_summary", None) or {}
        for k, v in summ.items():
            if isinstance(v, dict):
                usage["prompt_tokens"] = usage.get("prompt_tokens", 0) + v.get("prompt_tokens", 0)
                usage["completion_tokens"] = usage.get("completion_tokens", 0) + v.get("completion_tokens", 0)
    json.dump({"ticker": ticker, "fyear": fyear, "date": stamp, "messages": len(history), **usage},
              open(str(base) + "_meta.json", "w", encoding="utf-8"), indent=2)
    print(f"\nGespeichert: {base}_committee.md (Abschluss), _transcript.md (Verlauf), _meta.json")
    return final
