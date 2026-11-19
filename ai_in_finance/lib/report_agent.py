"""
Eigener Annual-Report-Agent ("Expert_Investor" + Zusatztools), getrennt von den FinRobot-Tutorials.

Die Basis-Rolle kommt aus FinRobots agent_library; hier werden Werkzeuge und Anweisungen
ergaenzt. So bleibt sichtbar, was von FinRobot stammt und was eigene Arbeit ist.

Wichtigste Aenderung gegenueber FinRobot: Die Analyse-Tools liefern die fertige Analyse direkt
als Tool-Ergebnis zurueck. Im Original schreiben sie nur eine Auftragsdatei, und ein zweiter
"Shadow"-Agent verfasst die Analyse in einem verschachtelten Chat. Dessen Ergebnis erscheint im
Gespraech als eigene Nachricht des Haupt-Agenten; vorsichtige Modelle (z. B. Claude Haiku)
halten es dann fuer selbst erfunden und verwerfen es. Als Tool-Ergebnis ist die Herkunft eindeutig.
"""
import copy
import functools
import inspect
from textwrap import dedent

import autogen
from finrobot.agents.agent_library import library
from finrobot.agents.workflow import SingleAssistant
from finrobot.functional.analyzer import ReportAnalysisUtils
from finrobot.functional.reportlab import ReportLabUtils

from .peer_tools import get_peer_candidates

# Analyse-Tools, die im Original nur eine Auftragsdatei schreiben
INSTRUCTION_TOOLS = [
    "analyze_income_stmt", "analyze_balance_sheet", "analyze_cash_flow", "analyze_segment_stmt",
    "income_summarization", "get_risk_assessment", "get_competitors_analysis",
    "analyze_business_highlights", "analyze_company_description",
]
PREFIX = "instruction & resources saved to "
ANALYST_SYSTEM = (
    "You are a senior equity research analyst. Answer the instruction using only the resources provided "
    "(10-K text and financial tables). Do not add facts that are not in the resources. Write in English prose."
)


def _analysis_llm_config(llm_config):
    cfg = {k: v for k, v in llm_config.items() if k not in ("parallel_tool_calls", "tools", "functions")}
    return cfg


def _wrap_analysis_tool(func, llm_config):
    client = autogen.OpenAIWrapper(**_analysis_llm_config(llm_config))

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = str(func(*args, **kwargs))
        if not result.startswith(PREFIX):
            return result  # z. B. Fehlermeldung: unveraendert durchreichen
        path = result[len(PREFIX):].strip()
        with open(path, encoding="utf-8") as f:
            instruction = f.read()
        response = client.create(messages=[{"role": "system", "content": ANALYST_SYSTEM},
                                           {"role": "user", "content": instruction}], cache=None)
        text = (client.extract_text_or_completion_object(response) or [""])[0] or ""
        analysis_path = path[:-4] + "_analysis.txt" if path.endswith(".txt") else path + "_analysis.txt"
        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(text)
        return (f"ANALYSIS RESULT (tool output, written from the 10-K text and financial tables in {path}; "
                f"also saved to {analysis_path}):\n\n{text}")

    return wrapper


def _ignore_unknown_kwargs(func):
    """Modelle erfinden gelegentlich Zusatzparameter (z. B. 'peer_tickers_placeholder'); das fuehrte zu einer
    Endlosschleife aus TypeErrors. Unbekannte Parameter werden ignoriert und im Ergebnis gemeldet."""
    allowed = set(inspect.signature(func).parameters)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        dropped = [k for k in kwargs if k not in allowed]
        result = func(*args, **{k: v for k, v in kwargs.items() if k in allowed})
        return f"{result} (Ignored unknown parameters: {', '.join(dropped)})" if dropped else result

    return wrapper


def make_agent_config(llm_config):
    cfg = copy.deepcopy(library["Expert_Investor"])
    tools = []
    for t in cfg["toolkits"]:
        if t is ReportAnalysisUtils:
            for name in dir(ReportAnalysisUtils):
                if name.startswith("_") or not callable(getattr(ReportAnalysisUtils, name)):
                    continue
                f = getattr(ReportAnalysisUtils, name)
                tools.append(_wrap_analysis_tool(f, llm_config) if name in INSTRUCTION_TOOLS else f)
        elif t is ReportLabUtils.build_annual_report:
            tools.append(_ignore_unknown_kwargs(t))
        else:
            tools.append(t)
    cfg["toolkits"] = tools + [get_peer_candidates]
    cfg["profile"] = cfg["profile"].replace(
        "Reply TERMINATE when everything is settled.",
        "Never invent data, companies or tickers; if a tool fails, say so. "
        "The analysis tools return their result as tool output starting with 'ANALYSIS RESULT'; these results are "
        "based on the 10-K text and financial tables and are your source material for the report sections. "
        "Reply TERMINATE when everything is settled.",
    )
    return cfg


def build_agent(llm_config, max_rounds=30):
    return SingleAssistant(
        make_agent_config(llm_config),
        llm_config,
        max_consecutive_auto_reply=max_rounds,
        human_input_mode="NEVER",
    )


def default_message(company, fyear, work_dir, peers=None):
    if peers:
        peer_line = f"For the competitor analysis use these ticker symbols: {', '.join(peers)}."
    else:
        peer_line = ("Before the competitor analysis, call get_peer_candidates. Pass extra_tickers with US-listed companies "
                     "that have a similar business model (e.g. listed competitors named in the 10-K). Choose the 3 most "
                     "comparable peers from the returned list, business model first, size second; state briefly why.")
    return dedent(f"""
        With the tools you've been provided, write an annual report based on {company}'s {fyear} 10-k report, format it into a pdf.
        Pay attention to the followings:
        - Explicitly explain your working plan before you kick off.
        - Use tools one by one for clarity.
        - All your file operations should be done in "{work_dir}".
        - {peer_line}
        - Use the analysis tools (income statement, balance sheet, cash flow, segments, business highlights,
          company description, risk assessment, competitors) and base the report on their ANALYSIS RESULT outputs.
        - Each of the five sections should be roughly 350-450 words, split into 2-4 paragraphs.
        - Also write an investment summary of 150-300 words for page 1.
        - Cite sources inline as [1] 10-K, [2] Yahoo Finance financials/prices, [3] analyst consensus, [4] peer financials.
        - When calling build_annual_report, pass peer_tickers with the chosen peers and segment_data with the segment
          revenues for the last two fiscal years as stated in the 10-K (USD millions).
        - Do not generate the pdf until all of this is fulfilled.
    """)
