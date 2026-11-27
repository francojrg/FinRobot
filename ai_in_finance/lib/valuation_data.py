"""
Bewertung, Bilanzqualitaet und Peer-Vergleich je Firma fuer die Firmenseite (eigene Erweiterung).

- Reverse DCF, implizite Rendite und Quality Scores rechnet finrobot/functional/outlook.py deterministisch aus
  Yahoo Finance (dieselben Werte wie im PDF des Annual Reports). Die App rechnet den Reverse DCF zusaetzlich live
  im Browser nach, wenn man die Annahmen verschiebt (gleiche Formel).
- Peers: die vom Annual-Report-Agenten gewaehlten und begruendeten Peer-Ticker; Kennzahlen von Yahoo Finance.
- KI-Basisfall: ein Modellaufruf schlaegt Wachstum, Zielmarge, WACC und ewiges Wachstum vor, begruendet aus dem
  Annual Report; die Zahlen werden auf plausible Bereiche begrenzt.
Zwischenspeicher: research/valuation/<TICKER>.json (Daten, 24 h) und <TICKER>_case.json (KI-Basisfall).
"""
import ast
import json
import re
import time
from datetime import datetime
from pathlib import Path
from . import agent_settings as _AS  # Prompts/Parameter aus der App (research/agent_settings.json)

AIF = Path(__file__).resolve().parents[1]
STORE = AIF / "research" / "valuation"
TTL = 24 * 3600


def _outlook():
    """finrobot/functional/outlook.py direkt laden (ohne das schwere finrobot-Paket mit autogen/RAG)."""
    import importlib.util
    import sys
    if "blumboerg_outlook" in sys.modules:
        return sys.modules["blumboerg_outlook"]
    path = AIF.parent / "finrobot_autogen" / "finrobot" / "functional" / "outlook.py"
    spec = importlib.util.spec_from_file_location("blumboerg_outlook", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["blumboerg_outlook"] = mod
    spec.loader.exec_module(mod)
    return mod


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _num(x):
    try:
        v = float(x)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _annual_args(t):
    """build_args des neuesten Annual Reports (oder {})."""
    from .company_data import current_reports
    rows = sorted([r for r in current_reports() if r[0] == t and r[1] == "annual"], key=lambda r: r[3] or "")
    return (_load(rows[-1][2]) or {}) if rows else {}


def _peer_list(args):
    p = args.get("peer_tickers")
    if isinstance(p, str):
        try:
            p = ast.literal_eval(p)
        except Exception:
            p = re.findall(r"[A-Z][A-Z0-9.\-]{0,9}", p)
    return [str(x).upper().strip() for x in (p or []) if str(x).strip()][:6]


def _peer_row(sym):
    import yfinance as yf
    try:
        i = yf.Ticker(sym).info or {}
    except Exception:
        i = {}
    rev, ebitda = _num(i.get("totalRevenue")), _num(i.get("ebitda"))
    fcf = _num(i.get("freeCashflow"))
    debt, cash = _num(i.get("totalDebt")) or 0.0, _num(i.get("totalCash")) or 0.0
    return {"t": sym, "name": i.get("shortName") or i.get("longName") or sym,
            "mcap": (_num(i.get("marketCap")) or 0) / 1e9 or None, "cur": i.get("currency"),
            "growth": _num(i.get("revenueGrowth")), "gm": _num(i.get("grossMargins")),
            "om": _num(i.get("operatingMargins")), "fcfm": fcf / rev if fcf is not None and rev else None,
            "roe": _num(i.get("returnOnEquity")), "evs": _num(i.get("enterpriseToRevenue")),
            "eve": _num(i.get("enterpriseToEbitda")), "fpe": _num(i.get("forwardPE")),
            "nde": (debt - cash) / ebitda if ebitda and ebitda > 0 else None}


def _market(t):
    """Marktkapitalisierung in Berichtswaehrung (Mio.), Aktienzahl, Kurs, Waehrung."""
    import yfinance as yf
    _fx_to_fin = _outlook()._fx_to_fin
    tk = yf.Ticker(t)
    i = tk.info or {}
    fx = _fx_to_fin(i) or 1.0
    mc = _num(i.get("marketCap"))
    return {"mcap": mc * fx / 1e6 if mc else None, "price": _num(i.get("currentPrice") or i.get("regularMarketPrice")),
            "cur": i.get("currency"), "fin_cur": i.get("financialCurrency"), "shares": _num(i.get("sharesOutstanding"))}


def compute(t):
    """Alle Daten neu abrufen (Yahoo Finance, etwa 10-20 Sekunden) und speichern."""
    ol = _outlook()
    t = t.upper()
    args = _annual_args(t)
    fy = None
    m = re.search(r"_(\d{4})_annual", str(args.get("save_path") or ""))
    if m:
        fy = m.group(1)
    out = {"t": t, "asof": datetime.now().isoformat(timespec="minutes"), "fy": fy, "errors": {}}
    for key, fn in (("rdcf", lambda: ol.reverse_dcf(t)), ("irr", lambda: ol.implied_irr(t)),
                    ("quality", lambda: ol.quality_scores(t)), ("consensus", lambda: ol.get_consensus(t)),
                    ("market", lambda: _market(t))):
        try:
            out[key] = fn()
        except Exception as e:
            out[key] = None
            out["errors"][key] = str(e)[:160]
    rd = out.get("rdcf") or {}
    for k in ("grid",):                          # Strings wie '> 100%' bleiben, sonst JSON-tauglich
        rd.pop(k, None)
    peers = _peer_list(args)
    out["peer_note"] = str(args.get("competitors_analysis") or "")[:1400]
    out["peers"] = [_peer_row(s) for s in [t] + peers] if peers else []
    if not out.get("market") and not any((out.get(k) or {}).get(x) for k, x in (("rdcf", "ev"), ("quality", "piotroski"))):
        raise RuntimeError("Yahoo Finance returned no data (no internet connection?)")   # nichts Leeres speichern
    STORE.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(STORE / f"{t}.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    return out


def payload(t, refresh=False):
    """Gespeicherte Daten plus KI-Basisfall; refresh=True ruft neu ab. None, wenn noch nichts gespeichert ist."""
    t = t.upper()
    d = None if refresh else _load(STORE / f"{t}.json")
    if refresh:
        d = compute(t)
    if not d:
        return None
    d["case"] = _load(STORE / f"{t}_case.json")
    d["stale"] = bool(d.get("asof")) and (time.time() - datetime.fromisoformat(d["asof"]).timestamp() > TTL)
    return d


def is_cached(t):
    return (STORE / f"{t.upper()}.json").exists()


CASE_PROMPT = """You are an equity analyst. Propose a base case for a simple 10-year reverse DCF of {t}, grounded ONLY in
the research below. The model: revenue grows at a constant rate g for {years} years, the free-cash-flow margin moves
linearly from today's {m0:.1%} to a target margin, discounted at a WACC, terminal value with perpetual growth.

Market data: enterprise value {ev:,.0f} m, last fiscal-year revenue {rev0:,.0f} m, model WACC {wacc:.1%} (risk-free
{rf:.2%} + beta {beta:.2f} x 5%), revenue growth implied by today's price {ig}, 3-year historical revenue CAGR {hist},
analyst consensus revenue growth next fiscal years: {cons}.

Research from the latest annual report:
{research}

Return JSON only:
{{"growth": <10-year revenue CAGR as decimal>, "margin": <target FCF margin as decimal>, "wacc": <decimal>,
"terminal": <perpetual growth as decimal, 0.015-0.035>, "rationale": "<3 short sentences in English: why this growth,
why this margin, how it compares with what the market implies>"}}"""


def _clip(v, lo, hi, default):
    v = _num(v)
    return default if v is None else min(max(v, lo), hi)


def suggest_case(t, model=None, llm=None):
    """KI-Basisfall (ein Modellaufruf, etwa 0,2 Cent). Rueckgabe und Speicherung als <TICKER>_case.json."""
    from .chat import call_llm
    t = t.upper()
    d = payload(t) or compute(t)
    rd = d.get("rdcf") or {}
    if not rd or rd.get("error"):
        raise RuntimeError(f"reverse DCF not available ({(rd or {}).get('error') or 'no data'})")
    args = _annual_args(t)
    research = "\n\n".join(f"{k.replace('_', ' ').title()}: {str(args.get(k))[:1500]}" for k in
                           ("investment_summary", "operating_results", "market_position", "risk_assessment",
                            "investment_theses") if args.get(k))
    fmt = lambda v: v if isinstance(v, str) else ("n/a" if v is None else f"{v:.1%}")
    cons = ", ".join(f"FY{y.get('fy')}: {fmt(y.get('growth'))}" for y in (d.get("consensus") or {}).get("years") or []) or "n/a"
    model = model or _AS.model("valuation")
    prompt = _AS.get("valuation.case", CASE_PROMPT).format(t=t, years=rd.get("years", 10), m0=rd.get("m0") or 0, ev=rd.get("ev") or 0,
                                rev0=rd.get("rev0") or 0, wacc=rd.get("wacc") or 0.09, rf=rd.get("rf") or 0.0425,
                                beta=rd.get("beta") or 1.0, ig=fmt(rd.get("implied_g")), hist=fmt(rd.get("hist_cagr3")),
                                cons=cons, research=research or "(no annual report available)")
    raw, cost = (llm or call_llm)([{"role": "user", "content": prompt}], model=model, max_tokens=700)
    m = re.search(r"\{.*\}", raw or "", re.S)
    j = json.loads(m.group(0)) if m else {}
    case = {"growth": _clip(j.get("growth"), -0.10, 0.40, None), "margin": _clip(j.get("margin"), 0.0, 0.50, rd.get("m_target")),
            "wacc": _clip(j.get("wacc"), 0.05, 0.16, rd.get("wacc")), "terminal": _clip(j.get("terminal"), 0.0, 0.04, 0.025),
            "rationale": str(j.get("rationale") or "")[:700], "created": datetime.now().isoformat(timespec="minutes"),
            "model": model, "cost": cost}
    if case["growth"] is None:
        raise RuntimeError("the model returned no usable growth rate")
    STORE.mkdir(parents=True, exist_ok=True)
    json.dump(case, open(STORE / f"{t}_case.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:                                         # Kosten protokollieren, damit das Monatsbudget sie zaehlt
        with open(AIF / "research" / "app_costs.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "what": f"valuation case {t}",
                                "cost": cost, "model": model}) + "\n")
    except Exception:
        pass
    return case
