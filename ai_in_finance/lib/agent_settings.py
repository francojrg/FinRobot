"""
Agenten in der App bearbeiten (eigene Erweiterung): Prompts, Zusatzanweisungen, Parameter und Modell je Agent.

- Die Standardtexte bleiben im Code (z. B. SYSTEM in lib/brief_agent.py). Aenderungen aus der App liegen nur lokal in
  research/agent_settings.json und ueberschreiben den Standard zur Laufzeit; "Reset" stellt ihn wieder her.
- Jede gespeicherte Fassung bleibt in der Versionsliste (je Prompt die letzten 20).
- Vorlagen mit Platzhaltern ({t}, {label}, ...) werden beim Speichern geprueft: alle Platzhalter des Standards muessen
  erhalten bleiben, keine neuen dazukommen, Klammern muessen stimmen. Sonst wuerde der Agent beim naechsten Lauf
  abstuerzen.
- Gemeinsame Stilregeln (lib/style.py): eine Aenderung ersetzt den Standardtext in allen Prompts, die ihn enthalten.
- Der Faktencheck haengt nicht an Prompts und laesst sich hier nicht abschalten.
"""
import importlib
import json
import string
from datetime import datetime
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
STORE = AIF / "research" / "agent_settings.json"


def _p(key, label, module, attr, template=False, help_=""):
    return {"key": key, "label": label, "module": module, "attr": attr, "template": template, "help": help_}


def _x(key, label, default, kind="pct", lo=0.0, hi=1.0, step=0.01, help_=""):
    return {"key": key, "label": label, "default": default, "kind": kind, "lo": lo, "hi": hi, "step": step, "help": help_}


AGENTS = [
    {"key": "annual_report", "name": "Annual Report", "desc": "Reads the 10-K and market data and writes the annual report with 3–4 investment theses and signposts.",
     "prompts": [_p("annual.analyst", "Analysis tools – system prompt", "lib.report_agent", "ANALYST_SYSTEM",
                    help_="Used by the analysis tools that turn 10-K text and financial tables into the report sections.")],
     "extra": "annual.extra", "params": []},
    {"key": "quarter_review", "name": "Quarter records (Thesis Tracker)", "desc": "Turns theses into measurable milestones (thesis book) and reviews every quarter separately.",
     "prompts": [_p("thesis.book", "Thesis book prompt", "lib.thesis_tracker", "BOOK_PROMPT", True),
                 _p("thesis.quarter", "Quarter record prompt", "lib.thesis_tracker", "QPROMPT", True)],
     "extra": None, "params": []},
    {"key": "earnings_review", "name": "Earnings Review", "desc": "Covers all quarters since the 10-K as a PDF report with a thesis status per quarter.",
     "prompts": [_p("earnings.system", "System prompt", "lib.earnings_reviewer_multi", "SYSTEM")],
     "extra": "earnings.extra", "params": []},
    {"key": "news", "name": "News Tracker", "desc": "Rates news (relevance, direction, materiality), links stories, writes the weekly digest.",
     "prompts": [_p("news.classify", "Rating news items", "lib.news_tracker", "CLASSIFY_SYSTEM"),
                 _p("news.story", "Linking stories", "lib.news_tracker", "STORY_SYSTEM"),
                 _p("news.theme", "Themes", "lib.news_tracker", "THEME_SYSTEM"),
                 _p("news.digest", "Weekly digest", "lib.news_tracker", "SYSTEM")],
     "extra": None, "params": []},
    {"key": "portfolio", "name": "Portfolio Manager", "desc": "Writes the portfolio review from the calculated performance, risk, optimisation and backtest.",
     "prompts": [_p("portfolio.system", "System prompt", "lib.portfolio_manager", "SYSTEM")],
     "extra": "portfolio.extra",
     "params": [_x("portfolio.cap", "Max weight per stock in the optimisation", 0.10, lo=0.03, hi=0.5),
                _x("portfolio.sector_cap", "Max weight per sector in the optimisation", 0.35, lo=0.1, hi=1.0)]},
    {"key": "brief", "name": "Weekly Brief", "desc": "Rule-based triggers (decide / read up / calm) per position; the model explains them.",
     "prompts": [_p("brief.system", "System prompt", "lib.brief_agent", "SYSTEM")],
     "extra": None,
     "params": [_x("brief.cap", "Position limit (above = trigger)", 0.10, lo=0.03, hi=0.5,
                   help_="A position above this weight triggers 'read up' (or 'decide' with a weakened thesis)."),
                _x("brief.stale_days", "Research counts as stale after (days)", 120, kind="int", lo=30, hi=400, step=10),
                _x("brief.earnings_window", "Flag upcoming results within (days)", 14, kind="int", lo=3, hi=45, step=1)]},
    {"key": "committee", "name": "Investment Committee (Beta)", "desc": "CIO and three analyst groups debate and vote. Roles come from FinRobot's experiments config.",
     "prompts": [], "extra": "committee.extra", "params": []},
    {"key": "forecast", "name": "Forecast (Beta)", "desc": "Weekly direction forecast with a range (FinGPT-Forecaster).",
     "prompts": [_p("forecast.system", "System prompt", "lib.forecaster", "SYSTEM")], "extra": "forecast.extra", "params": []},
    {"key": "preview", "name": "Earnings Preview (Beta)", "desc": "One page before quarterly results: what to watch and three scenarios.",
     "prompts": [_p("preview.prompt", "Prompt", "lib.earnings_preview", "PROMPT", True)], "extra": None, "params": []},
    {"key": "reads", "name": "Interesting Reads (Beta)", "desc": "Picks 5–7 reads, podcasts or videos from real candidates.",
     "prompts": [_p("reads.prompt", "Prompt", "lib.reads", "PROMPT", True)], "extra": None, "params": []},
    {"key": "valuation", "name": "AI base case (Reverse DCF)", "desc": "Proposes growth, margin, WACC and terminal growth from the annual report.",
     "prompts": [_p("valuation.case", "Prompt", "lib.valuation_data", "CASE_PROMPT", True)], "extra": None, "params": []},
    {"key": "chat", "name": "Chat (Ask)", "desc": "Answers questions from your own research with sources.",
     "prompts": [_p("chat.system", "System prompt", "lib.chat", "SYSTEM")], "extra": None, "params": []},
    {"key": "style", "name": "Style rules (all agents)", "desc": "Shared writing rules, derived from investor letters. A change applies to every prompt that contains them.",
     "prompts": [_p("style.rules", "Style rules", "lib.style", "STYLE_RULES")], "extra": None, "params": []},
]
INFO = {'annual_report': {'what': 'Writes the equity research report for one company after each new 10-K (or 20-F): business, market position, results, risks, competitors, valuation and 3–4 investment theses, each with evidence, a measurable signpost and what would prove it wrong.', 'sources': '10-K sections (business, risk factors, MD&A) straight from SEC EDGAR; financial statements, prices, consensus, liquidity, reverse DCF and quality scores from Yahoo Finance; peer candidates from Finnhub with Yahoo data.', 'output': 'PDF report plus all texts as data (reports/<TICKER>_<YEAR>_…); every number is fact-checked against the sources, with one self-correction round. Afterwards valuation data, AI base case and thesis book are refreshed.', 'when': 'When a new annual report is filed at the SEC, or when you rebuild it.'}, 'quarter_review': {'what': 'Thesis tracker. The thesis book turns each thesis into 1–3 measurable milestones and a fixed KPI list. Then every quarter since the 10-K – including Q4 – is reviewed on its own: KPIs, guidance, management messages and a status per thesis.', 'sources': "The 8-K earnings release and the 10-Q of exactly that quarter (SEC EDGAR), quarterly statements from Yahoo Finance, the thesis book and the previous quarter's statuses.", 'output': "Thesis book (reports/thesis_books/) and one quarter record per quarter (reports/quarter_records/<TICKER>/). Python checks the milestones and flags when they contradict the model's status; the Weekly Brief uses these statuses.", 'when': 'For every quarter without a record, before the earnings review.'}, 'earnings_review': {'what': 'Earnings and thesis update covering all quarters since the 10-K: how the business developed quarter by quarter, results vs. prior year, company-specific KPIs, a status per thesis per quarter, risks and outlook.', 'sources': '8-K earnings releases and 10-Q MD&A since the 10-K (SEC EDGAR), the multi-quarter scorecard from Yahoo statements, consensus and revisions from Yahoo, the theses of the annual report and the thesis log.', 'output': 'PDF report (reports/<TICKER>_earnings_multi_…), KPI history for the charts and the thesis log; fact check with one self-correction round.', 'when': 'When new quarterly results are filed at the SEC.'}, 'news': {'what': 'Collects news on your holdings, removes duplicates, rates each item (relevance, direction, materiality, category) and links related items into stories. Once a week it writes the digest with themes and the market backdrop.', 'sources': 'Finnhub, Yahoo Finance, Google News RSS and SEC 8-K filings; price reaction vs. the index computed by Python (day 0 to 1).', 'output': 'News store (news/), signals and stories per holding, weekly digest as PDF and on the News page.', 'when': 'Daily for new items (or on the schedule set under Automation); digest weekly.'}, 'portfolio': {'what': 'Writes the portfolio review: performance, risk, structure, optimisation and backtest, your decisions, and recommendations that take thesis status, committee votes and news signals into account.', 'sources': 'Calculated by Python from your transactions or weights: value in EUR, time- and money-weighted return vs. MSCI ACWI, contributions, risk, stress tests, optimisation and walk-forward backtest (prices from Yahoo Finance); research views of the other agents.', 'output': 'Portfolio review PDF, the dashboard data behind the Portfolio pages and the snapshot for the Weekly Brief.', 'when': 'Weekly, and after new quarterly results or an annual report.'}, 'brief': {'what': 'One page per week across all agents: where a decision is needed, where you should read up, where nothing is to do. Fixed rules decide the level; the model explains what happened, why it matters and what to do next.', 'sources': 'Thesis tracker / earnings reviews, committee votes, forecasts, news signals and stories, upcoming results, the portfolio snapshot (weights, risk) and your notes from Done/Seen.', 'output': 'Weekly brief PDF and the action tiles on the Overview page.', 'when': 'Weekly, and after new quarterly results or an annual report.'}, 'committee': {'what': "A CIO and three analyst groups (configured in FinRobot's experiments) debate the company and vote: buy, hold or sell with a 6-month target price. Beta: slow and often without a target.", 'sources': 'Annual report, earnings reviews, news signals and stories from the other agents, plus Yahoo data tools.', 'output': 'Final report and full transcript (reports/committee/).', 'when': 'Only when switched on; then after new reports or when the last vote is older than the schedule.'}, 'forecast': {'what': 'Weekly direction forecast with a range (e.g. up 1–3%) and the main positive and negative factors – the FinGPT-Forecaster from the FinRobot tutorial.', 'sources': 'Company news from Finnhub, prices and basic financials from Yahoo Finance.', 'output': 'Forecast per company (forecasts/) – scored after five trading days (Log → Tools → Score forecasts).', 'when': 'Weekly (schedule under Automation).'}, 'preview': {'what': 'One page before quarterly results: what has to be reported for the theses to hold, thresholds to watch and three scenarios (bull, base, bear).', 'sources': 'Only existing data: consensus and revisions from Yahoo, your theses and signposts, the KPI history, the last earnings review.', 'output': 'Earnings preview on the company page; numbers checked against the inputs.', 'when': 'Up to 14 days before quarterly results.'}, 'reads': {'what': 'Picks 5–7 interviews, podcasts, videos or deep dives worth your time and says why in one sentence. It can only choose real candidates, never invent links.', 'sources': 'Your insight sources (bank research, blogs, YouTube channels, podcasts) and a Google News search on your holdings, watchlist and interests.', 'output': 'Interesting reads on the News page.', 'when': 'Once a week, or with the button on the News page.'}, 'valuation': {'what': 'Proposes a base case for the reverse DCF: revenue growth, target free-cash-flow margin, WACC and perpetual growth, with a short rationale, compared with what the market price implies.', 'sources': 'The annual report texts (summary, results, market position, risks, theses), the reverse DCF inputs and consensus growth from Yahoo Finance.', 'output': "AI base case on the company page ('Apply AI case' sets the sliders).", 'when': 'After each annual report, or with the button on the company page.'}, 'chat': {'what': 'Answers your questions about holdings and reports. Python first finds the relevant passages in your own results; the model answers only from them, with sources. It can suggest a run but never starts one itself.', 'sources': 'Your reports, quarter records, the Weekly Brief, news and portfolio data.', 'output': 'Answer with numbered sources; every number checked (green found, red not found).', 'when': 'When you ask a question on the Ask page.'}, 'style': {'what': 'Shared writing rules for all agents: lead with the result and the numbers, discuss problems before successes, give every number its context, name what would prove a view wrong, no promotional words, never invent facts – derived from investor letters (Fundsmith, Giverny, Pershing Square, Greenlight).', 'sources': '—', 'output': 'Inserted into the prompts of the writing agents.', 'when': 'Every run.'}}
for _a in AGENTS:
    _a.update(INFO.get(_a["key"], {}))
PROMPTS = {p["key"]: p for a in AGENTS for p in a["prompts"]}
PARAMS = {x["key"]: x for a in AGENTS for x in a["params"]}


# =============================================================== Speicher
def load():
    try:
        d = json.load(open(STORE, encoding="utf-8"))
    except Exception:
        d = {}
    for k in ("prompts", "extras", "params", "models", "history"):
        d.setdefault(k, {})
    return d


def _save(d):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def default(key):
    """Standardtext aus dem Code (Modul wird erst hier importiert)."""
    p = PROMPTS[key]
    return str(getattr(importlib.import_module(p["module"]), p["attr"]))


# =============================================================== Lesen (von den Agenten zur Laufzeit)
def get(key, dflt):
    """Prompt fuer den Agenten: Aenderung aus der App oder Standard; geaenderte Stilregeln werden eingesetzt."""
    try:
        d = load()
    except Exception:
        return dflt
    text = d["prompts"].get(key) or dflt
    style = d["prompts"].get("style.rules")
    if style and key != "style.rules":
        try:
            from .style import STYLE_RULES
            text = text.replace(STYLE_RULES, style)
        except Exception:
            pass
    return text


def extra(key):
    """Zusatzanweisungen fuer den Auftrag eines Agenten (leer, wenn keine)."""
    try:
        t = (load()["extras"].get(key) or "").strip()
    except Exception:
        t = ""
    return f"\n\nAdditional instructions from the user (follow them unless they conflict with the rules above):\n{t}" if t else ""


def param(key, dflt):
    try:
        v = load()["params"].get(key)
    except Exception:
        v = None
    return dflt if v is None else v


def model(agent, dflt=None):
    try:
        return load()["models"].get(agent) or dflt
    except Exception:
        return dflt


# =============================================================== Schreiben (aus der App)
def _fields(text):
    out = set()
    for _, name, _, _ in string.Formatter().parse(text):
        if name is not None:
            out.add(name.split(".")[0].split("[")[0])
    return out


def validate(key, text):
    """Fehlertext oder None."""
    if not str(text).strip():
        return "The prompt is empty."
    if PROMPTS[key]["template"]:
        try:
            new = _fields(text)
        except ValueError as e:
            return f"Braces do not match ({e}). Literal braces must be doubled: {{{{ and }}}}."
        old = _fields(default(key))
        miss, extra_ = old - new, new - old
        if miss:
            return "These placeholders must stay in the text: " + ", ".join("{" + m + "}" for m in sorted(miss))
        if extra_:
            return ("Unknown placeholders (the agent cannot fill them): " + ", ".join("{" + m + "}" for m in sorted(extra_))
                    + ". Write literal braces as {{ and }}.")
    return None


def _hist(d, key, text):
    h = d["history"].setdefault(key, [])
    h.append({"ts": datetime.now().isoformat(timespec="minutes"), "text": text})
    d["history"][key] = h[-20:]


def set_prompt(key, text):
    err = validate(key, text)
    if err:
        raise ValueError(err)
    d = load()
    if text.strip() == default(key).strip():
        d["prompts"].pop(key, None)
    else:
        d["prompts"][key] = text
    _hist(d, key, text)
    _save(d)


def reset_prompt(key):
    d = load()
    d["prompts"].pop(key, None)
    _hist(d, key, "(reset to default)")
    _save(d)


def set_extra(key, text):
    d = load()
    if str(text or "").strip():
        d["extras"][key] = str(text).strip()
    else:
        d["extras"].pop(key, None)
    _hist(d, key, str(text or ""))
    _save(d)


def set_param(key, value):
    d = load()
    x = PARAMS[key]
    if value is None or value == x["default"]:
        d["params"].pop(key, None)
    else:
        v = int(value) if x["kind"] == "int" else float(value)
        d["params"][key] = min(max(v, x["lo"]), x["hi"])
    _save(d)


def set_model(agent, m):
    d = load()
    if m:
        d["models"][agent] = m
    else:
        d["models"].pop(agent, None)
    _save(d)


def history(key):
    return list(reversed(load()["history"].get(key, [])))


def changed(agent):
    """Hat der Nutzer bei diesem Agenten etwas geaendert? (fuer die Markierung in der Liste)"""
    d = load()
    a = next(x for x in AGENTS if x["key"] == agent)
    return (any(p["key"] in d["prompts"] for p in a["prompts"]) or bool(a["extra"] and d["extras"].get(a["extra"]))
            or any(x["key"] in d["params"] for x in a["params"]) or bool(d["models"].get(agent)))
