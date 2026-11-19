"""
Eigener Annual-Report-Agent ("Expert_Investor" + Zusatztools), getrennt von den FinRobot-Tutorials.

Die Basis-Rolle kommt unveraendert aus FinRobots agent_library; hier werden nur Werkzeuge und
Anweisungen ergaenzt. So bleibt sichtbar, was von FinRobot stammt und was eigene Arbeit ist.
"""
import copy
from textwrap import dedent

from finrobot.agents.agent_library import library
from finrobot.agents.workflow import SingleAssistantShadow

from .peer_tools import get_peer_candidates


def make_agent_config():
    cfg = copy.deepcopy(library["Expert_Investor"])
    cfg["toolkits"] = list(cfg["toolkits"]) + [get_peer_candidates]
    cfg["profile"] = cfg["profile"].replace(
        "Reply TERMINATE when everything is settled.",
        "Never invent data, companies or tickers; if a tool fails, say so. "
        "Reply TERMINATE when everything is settled.",
    )
    return cfg


def build_agent(llm_config, max_rounds=30):
    return SingleAssistantShadow(
        make_agent_config(),
        llm_config,
        max_consecutive_auto_reply=max_rounds,
        human_input_mode="NEVER",
    )


def default_message(company, fyear, work_dir, peers=None):
    if peers:
        peer_line = f"For the competitor analysis use these ticker symbols: {', '.join(peers)}."
    else:
        peer_line = ("Before the competitor analysis, call get_peer_candidates and choose the 3 most comparable peers "
                     "from its list; state briefly why you chose them.")
    return dedent(f"""
        With the tools you've been provided, write an annual report based on {company}'s {fyear} 10-k report, format it into a pdf.
        Pay attention to the followings:
        - Explicitly explain your working plan before you kick off.
        - Use tools one by one for clarity, especially when asking for instructions.
        - All your file operations should be done in "{work_dir}".
        - Display any image in the chat once generated.
        - {peer_line}
        - Each of the five sections should be roughly 350-450 words, split into 2-4 paragraphs.
        - Also write an investment summary of 150-300 words for page 1.
        - Cite sources inline as [1] 10-K, [2] Yahoo Finance financials/prices, [3] analyst consensus, [4] peer financials.
        - When calling build_annual_report, pass peer_tickers with the chosen peers and segment_data with the segment
          revenues for the last two fiscal years as stated in the 10-K (USD millions).
        - Do not generate the pdf until all of this is fulfilled.
    """)
