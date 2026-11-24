"""
Pipeline (eigene Erweiterung): verbindet die Agenten zu einem Ablauf. Python entscheidet anhand des Zustands, was faellig
ist; die Agenten tauschen ihre Ergebnisse ueber Dateien aus (Annual Report -> Thesen -> Thesen-Protokoll ->
Committee/News/Portfolio Manager).

Je Titel (nur US-Werte mit SEC-Filings; andere bekommen News und Portfolio-Sicht):
  1. Annual Report      faellig, wenn ein neuerer 10-K vorliegt als der letzte Report des Agenten
  2. Earnings Review    faellig, wenn nach dem 10-K neue Quartalszahlen (8-K Item 2.02) gemeldet wurden, die noch nicht
                        im Thesen-Protokoll stehen (Multi-Quarter-Reviewer)
  3. Committee          faellig nach neuem Report/Review, bei News-Alarm (eskalierende Story, These in Frage gestellt)
                        oder wenn das letzte Votum aelter als committee_days ist; bekommt Thesen, Status und Signale
  4. Forecaster         woechentlich
Depot:
  5. News-Tracker       woechentlich
  6. Portfolio Manager  am Ende, mit der Research-Sicht je Position (Thesen-Status, Committee-Votum, News-Signale)

Erst planen (dry_run, ohne LLM), dann ausfuehren. Jeder Schritt laeuft isoliert (Fehler stoppen nicht den Rest),
Laufzeit und Kosten (OpenRouter) werden protokolliert: research/pipeline_runs/<Zeitstempel>.json/.md.
"""
import csv
import glob
import json
import os
import re
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

AIF = Path(__file__).resolve().parents[1]
FR = AIF.parent / "finrobot_autogen"
RESEARCH = AIF / "research"
REPORTS = AIF / "reports"
COMMITTEE_DIR = REPORTS / "committee"
FORECAST_LOG = AIF / "forecasts" / "forecast_log.csv"
STEP_ORDER = ["annual_report", "earnings_review", "committee", "forecast", "news", "portfolio", "brief"]
LLM_STEPS = {"annual_report", "earnings_review", "committee", "forecast", "news", "portfolio", "brief"}


# =============================================================== Modelle (wie scripts/run_eval.py)
def llm_config_for(model, reasoning="low", temperature=0.5, max_tokens=16000):
    base = json.load(open(FR / "OAI_CONFIG_LIST", encoding="utf-8"))
    entry = next((e for e in base if e.get("model") == model), None)
    if entry is None:
        tpl = next((e for e in base if "openrouter" in str(e.get("base_url", ""))), base[0])
        entry = dict(tpl, model=model)
    cfg = {"config_list": [entry], "timeout": 300, "temperature": temperature, "parallel_tool_calls": False,
           "max_tokens": max_tokens}
    if model.startswith("google/") and reasoning:
        cfg["extra_body"] = {"reasoning": {"effort": reasoning}}
    return cfg


def openrouter_usage(cfg):
    """Bisheriger Gesamtverbrauch des OpenRouter-Keys in USD (None, falls nicht abrufbar)."""
    entry = (cfg.get("config_list") or [{}])[0]
    if "openrouter" not in str(entry.get("base_url", "")):
        return None
    try:
        import requests
        r = requests.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {entry['api_key']}"},
                         timeout=20)
        return float(r.json()["data"]["usage"])
    except Exception:
        return None


# =============================================================== Zustand ermitteln
def is_us(ticker):
    return re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", ticker) is not None and not ticker.endswith("-EUR")


def edgar_status(symbol):
    """Ein EDGAR-Abruf je Titel: neuester 10-K (Geschaeftsjahr = Jahr des Stichtags) und alle 8-K Item 2.02."""
    import requests
    from finrobot.data_source.fmp_utils import _sec_headers, _ticker_to_cik
    cik = _ticker_to_cik().get(symbol.upper())
    if cik is None:
        return {"error": "no CIK (not an SEC filer)"}
    rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_sec_headers(), timeout=30).json()
    r = rec["filings"]["recent"]
    items = r.get("items") or [""] * len(r["form"])
    tenk = [(fd, rd) for f, fd, rd in zip(r["form"], r["filingDate"], r.get("reportDate", [""] * len(r["form"])))
            if f == "10-K" and rd]
    out = {"error": None, "releases": sorted(d for f, d, it in zip(r["form"], r["filingDate"], items)
                                             if f in ("8-K", "8-K/A") and "2.02" in str(it))}
    if tenk:
        fd, rd = max(tenk)
        out.update(tenk_filed=fd, tenk_period=rd, fyear=int(rd[:4]))
    return out


def agent_report(symbol):
    """Neuester Annual Report des Agenten fuer den Titel (Ordner reports/<SYM>_<FY>_...)."""
    best = None
    for p in glob.glob(str(REPORTS / f"{symbol.upper()}_*" / "*build_args.json")):
        m = re.match(rf"{re.escape(symbol.upper())}_(\d{{4}})_", Path(p).parent.name)
        if not m:
            continue
        cand = {"fyear": int(m.group(1)), "path": str(Path(p).parent), "date": date.fromtimestamp(os.path.getmtime(p)).isoformat()}
        if best is None or (cand["fyear"], cand["date"]) > (best["fyear"], best["date"]):
            best = cand
    return best


def last_review(symbol):
    from .quarterly_data import load_thesis_log
    log = load_thesis_log(symbol.upper())
    if not log:
        return None
    e = log[-1]
    counts = {}
    for t in e.get("theses", []):
        s = t.get("current_status") or t.get("status") or "n/a"
        counts[s] = counts.get(s, 0) + 1
    return {"date": e.get("date"), "fyear": e.get("fyear"), "quarters": e.get("quarters", []), "status_counts": counts,
            "theses": e.get("theses", [])}


def last_committee(symbol):
    files = sorted(glob.glob(str(COMMITTEE_DIR / f"{symbol.upper()}_*_committee.md")))
    if not files:
        return None
    p = files[-1]
    txt = open(p, encoding="utf-8").read()
    tp = re.search(r"TARGET PRICE:\s*\$?\s*([\d.,]+)", txt)
    rec = re.search(r"RECOMMENDATION:\s*\**\s*(buy|hold|sell)", txt, re.I)
    m = re.search(r"_(\d{4}-\d{2}-\d{2})_committee", p)
    return {"date": m.group(1) if m else None, "path": p,
            "target": float(tp.group(1).replace(",", "")) if tp else None,
            "recommendation": rec.group(1).lower() if rec else None}


def last_forecast(symbol):
    if not FORECAST_LOG.exists():
        return None
    rows = [r for r in csv.DictReader(open(FORECAST_LOG, encoding="utf-8")) if r.get("ticker", "").upper() == symbol.upper()]
    if not rows:
        return None
    r = rows[-1]
    return {"date": r["timestamp"][:10], "direction": r.get("direction"), "low": r.get("low_pct"), "high": r.get("high_pct")}


def last_news(news_dir=None):
    """Signale des letzten News-Tracker-Laufs (news/signals_latest.json) und Datum des letzten Digests."""
    from . import news_tracker as nt
    p = Path(news_dir or nt.NEWS_DIR) / "signals_latest.json"
    sig = json.load(open(p, encoding="utf-8")) if p.exists() else {}
    digests = sorted(glob.glob(str(REPORTS / "news_*" / "*_news_digest.pdf")), key=os.path.getmtime)
    return {"date": date.fromtimestamp(os.path.getmtime(digests[-1])).isoformat() if digests else sig.get("date"),
            "signals": sig.get("signals", {}), "stories": sig.get("stories", {})}


def ticker_state(t, edgar=None):
    sym = t.split(".")[0] if not is_us(t) else t
    st = {"ticker": t, "us": is_us(t), "report": agent_report(sym), "review": last_review(sym),
          "committee": last_committee(sym), "forecast": last_forecast(sym)}
    if st["us"]:
        try:
            st["edgar"] = edgar(t) if edgar else edgar_status(t)
        except Exception as e:
            st["edgar"] = {"error": f"EDGAR request failed ({str(e)[:80]})"}
    return st


# =============================================================== Planen
def plan(tickers, today=None, committee_days=30, forecast_days=6, news_days=6, edgar=None, news=None,
         with_portfolio=True, with_brief=True):
    """Welche Schritte sind faellig und warum (ohne LLM-Aufrufe)."""
    today = pd.Timestamp(today or date.today())
    news = news if news is not None else last_news()
    steps, states = [], {}
    for t in tickers:
        s = ticker_state(t, edgar)
        states[t] = s
        if not s["us"]:
            steps.append({"step": "skip", "ticker": t, "reason": "no SEC filings - covered by news tracker and portfolio view"})
            continue
        e = s.get("edgar") or {}
        if e.get("error"):
            steps.append({"step": "skip", "ticker": t, "reason": e["error"]})
            continue
        rep, rev, com, fc = s["report"], s["review"], s["committee"], s["forecast"]
        new_report = False
        if e.get("fyear") and (rep is None or e["fyear"] > rep["fyear"]):
            steps.append({"step": "annual_report", "ticker": t, "fyear": e["fyear"],
                          "reason": f"10-K FY{e['fyear']} filed {e['tenk_filed']}; "
                                    + (f"last agent report FY{rep['fyear']}" if rep else "no agent report yet")})
            new_report = True
        fy = e.get("fyear") or (rep or {}).get("fyear")
        cutoff = (pd.Timestamp(e["tenk_period"]) + pd.Timedelta(days=75)).date().isoformat() if e.get("tenk_period") else None
        rels = [d for d in e.get("releases", []) if cutoff and d > cutoff]
        new_rels = [d for d in rels if rev is None or rev.get("fyear") != fy or d > (rev.get("date") or "")]
        new_review = False
        if (rep or new_report) and new_rels:
            steps.append({"step": "earnings_review", "ticker": t, "fyear": fy,
                          "reason": f"{len(new_rels)} new quarterly release(s) since the 10-K (latest {new_rels[-1]})"
                                    + ("" if rev else "; no thesis log yet")})
            new_review = True
        sig = (news.get("signals") or {}).get(t, {})
        alarm = [f for f in sig.get("flags", []) if "escalating" in f or "divergence" in f]
        if alarm and com and news.get("date") and com["date"] >= str(news["date"]):
            alarm = []                                   # Committee hat nach diesem News-Lauf schon getagt
        why = []
        if new_report or new_review:
            why.append("new annual report / earnings review")
        if com is None:
            why.append("no committee vote yet")
        elif (today - pd.Timestamp(com["date"])).days > committee_days:
            why.append(f"last vote {com['date']} older than {committee_days} days")
        if alarm:
            why.append("news signal: " + "; ".join(alarm[:2]))
        if why and (rep or new_report):
            steps.append({"step": "committee", "ticker": t, "fyear": fy, "reason": "; ".join(why)})
        if fc is None or (today - pd.Timestamp(fc["date"])).days > forecast_days:
            steps.append({"step": "forecast", "ticker": t,
                          "reason": "no forecast yet" if fc is None else f"last forecast {fc['date']}"})
    uncovered = [t for t in tickers if t not in (news.get("signals") or {})]
    if news.get("date") is None or (today - pd.Timestamp(news["date"])).days > news_days:
        steps.append({"step": "news", "ticker": "portfolio",
                      "reason": "no digest yet" if news.get("date") is None else f"last digest {news['date']}"})
    elif uncovered:                                  # letzter Digest deckte andere Titel ab
        steps.append({"step": "news", "ticker": "portfolio",
                      "reason": "positions not covered by the last digest: " + ", ".join(uncovered[:6])})
    if with_portfolio:
        steps.append({"step": "portfolio", "ticker": "portfolio", "reason": "portfolio review with research view"})
    if with_brief:
        steps.append({"step": "brief", "ticker": "portfolio", "reason": "weekly brief across all agents (last step)"})
    order = {k: i for i, k in enumerate(STEP_ORDER + ["skip"])}
    tick_order = {t: i for i, t in enumerate(tickers)}
    late = ("news", "portfolio", "brief")
    steps.sort(key=lambda x: (x["step"] in late, order[x["step"]] if x["step"] in late
                              else tick_order.get(x["ticker"], 99), order[x["step"]]))
    return steps, states


def plan_table(steps):
    return pd.DataFrame([{"step": s["step"], "ticker": s["ticker"], "reason": s["reason"]} for s in steps])


# =============================================================== Research-Sicht (fuer Portfolio Manager und Committee)
def research_views(tickers, news=None):
    """Je Position: Thesen-Status (Thesen-Protokoll), letztes Committee-Votum (mit Upside zum Kurs), letzter Forecast,
    News-Signale und aktive Stories."""
    news = news if news is not None else last_news()
    out = {}
    for t in tickers:
        sym = t if is_us(t) else t.split(".")[0]
        rep, rev, com, fc = agent_report(sym), last_review(sym), last_committee(sym), last_forecast(sym)
        sig = (news.get("signals") or {}).get(t, {})
        v = {"ticker": t, "report_fy": rep["fyear"] if rep else None,
             "theses": None, "thesis_status": None, "committee": None, "forecast": None,
             "news_flags": sig.get("flags", []), "sentiment": sig.get("sentiment"),
             "sentiment_4w": sig.get("sentiment_4w"), "active_stories": sig.get("active_stories")}
        if rev:
            v["thesis_status"] = rev["status_counts"]
            v["theses"] = len(rev["theses"])
            v["review_date"] = rev["date"]
        elif rep:
            from .quarterly_data import annual_baseline
            b = annual_baseline(sym)
            v["theses"] = len(b.get("theses") or [])
        if com:
            v["committee"] = {"date": com["date"], "recommendation": com["recommendation"], "target": com["target"]}
        if fc:
            v["forecast"] = fc
        out[t] = v
    return out


def research_text(views):
    lines = ["RESEARCH VIEW by position (from the other agents: annual report theses, thesis log of the earnings reviewer, "
             "investment committee, weekly forecaster, news tracker; cite as [R]):"]
    for t, v in views.items():
        parts = []
        if v["thesis_status"]:
            parts.append("thesis status " + ", ".join(f"{k} {n}" for k, n in v["thesis_status"].items())
                         + f" (review {v.get('review_date')})")
        elif v["theses"]:
            parts.append(f"{v['theses']} theses from the FY{v['report_fy']} annual report, not yet reviewed")
        else:
            parts.append("no annual report / theses")
        c = v["committee"]
        if c:
            parts.append(f"committee {c['date']}: {c['recommendation'] or 'n/a'}"
                         + (f", 6-month target {c['target']:,.2f} (trading currency)" if c.get("target") else ""))
        f = v["forecast"]
        if f:
            parts.append(f"weekly forecast {f['date']}: {f['direction']} ({f.get('low')}% to {f.get('high')}%)")
        if v["news_flags"]:
            parts.append("news flags: " + "; ".join(v["news_flags"][:3]))
        if v.get("sentiment") is not None:
            parts.append(f"news sentiment {v['sentiment']:+.0f}")
        lines.append(f"- {t}: " + " | ".join(parts))
    return "\n".join(lines)


def committee_context(t):
    """Kontext fuer das Committee: Thesen mit Status, letzte News-Signale und Stories, letzter Forecast."""
    from .news_tracker import theses_text
    v = research_views([t])[t]
    news = last_news()
    lines = ["RESEARCH CONTEXT from the firm's other agents (use it, but verify figures with your tools):",
             theses_text(t)]
    rev = last_review(t)
    if rev:
        lines.append(f"Thesis log (earnings reviewer, {rev['date']}, quarters {', '.join(rev['quarters'])}): " +
                     "; ".join(f"'{x.get('thesis', '')[:90]}' -> {x.get('current_status')}" for x in rev["theses"]))
    st = (news.get("stories") or {}).get(t) or []
    if st:
        lines.append("Developing stories (news tracker): " + "; ".join(f"{x['title']} ({x['status']})" for x in st[:5]))
    if v["news_flags"]:
        lines.append("News signals: " + "; ".join(v["news_flags"]))
    if v["forecast"]:
        f = v["forecast"]
        lines.append(f"Latest weekly forecast {f['date']}: {f['direction']} ({f.get('low')}% to {f.get('high')}%)")
    lines.append("In the final deliverable, state for each investment thesis whether your analysis supports it.")
    return "\n".join(lines)


# =============================================================== Ausfuehren
def _run_step(step, cfgs, ctx):
    t, k = step["ticker"], step["step"]
    if k == "annual_report":
        from . import report_agent
        from finrobot.functional.reportlab import reset_build_rounds
        tag = cfgs["writer"]["config_list"][0]["model"].split("/")[-1]
        work_abs = REPORTS / f"{t}_{step['fyear']}_{tag}_pipeline"
        work_abs.mkdir(parents=True, exist_ok=True)
        reset_build_rounds()
        agent = report_agent.build_agent(cfgs["writer"], max_rounds=ctx.get("max_rounds", 30))
        msg = report_agent.default_message(t, step["fyear"], os.path.relpath(work_abs, ctx["cwd"]).replace("\\", "/"))
        agent.user_proxy.initiate_chat(agent.assistant, message=msg, cache=None, max_turns=60)
        pdfs = [p for p in glob.glob(str(work_abs / "*.pdf")) if os.path.getmtime(p) >= ctx["t0"]]
        return {"output": pdfs[-1] if pdfs else None, "ok": bool(pdfs)}
    if k == "earnings_review":
        from .earnings_reviewer_multi import run_multi_review
        tag = cfgs["writer"]["config_list"][0]["model"].split("/")[-1]
        save = REPORTS / f"{t}_earnings_multi_{tag}"
        run_multi_review(cfgs["writer"], t, step["fyear"], os.path.relpath(save, ctx["cwd"]).replace("\\", "/"))
        after = last_review(t)
        ok = bool(after) and after.get("date") == date.today().isoformat()
        return {"output": str(save), "ok": ok}
    if k == "committee":
        from .investment_committee import run_committee
        final = run_committee(cfgs["committee"], t, step["fyear"], str(COMMITTEE_DIR), context=committee_context(t))
        c = last_committee(t)
        return {"output": (c or {}).get("path"), "ok": bool(final and "TARGET PRICE" in final),
                "recommendation": (c or {}).get("recommendation"), "target": (c or {}).get("target")}
    if k == "forecast":
        from .forecaster import forecast
        forecast(cfgs["forecast"], t, model_name=cfgs["forecast"]["config_list"][0]["model"])
        f = last_forecast(t)
        return {"output": str(FORECAST_LOG), "ok": bool(f and f["date"] == date.today().isoformat()),
                "direction": (f or {}).get("direction")}
    if k == "news":
        from . import news_tracker as nt
        wl = ctx.get("watchlist")
        tag = cfgs["writer"]["config_list"][0]["model"].split("/")[-1]
        st = nt.run_news_tracker(cfgs["writer"], cfgs["classifier"], watchlist=wl, days=7,
                                 save_dir=os.path.relpath(REPORTS / f"news_{tag}", ctx["cwd"]).replace("\\", "/"))
        pdf = REPORTS / f"news_{tag}" / f"{st['name']}_news_digest.pdf"
        return {"output": str(pdf), "ok": pdf.exists()}
    if k == "portfolio":
        from .portfolio_manager import run_portfolio_review
        tag = cfgs["writer"]["config_list"][0]["model"].split("/")[-1]
        save = REPORTS / f"portfolio_{ctx.get('name', 'pipeline')}_{tag}"
        views = research_views(ctx["tickers"])
        run_portfolio_review(cfgs["writer"], ctx.get("portfolio_file"), os.path.relpath(save, ctx["cwd"]).replace("\\", "/"),
                             name=ctx.get("name", "pipeline"), title=ctx.get("title", "Portfolio Review"),
                             transaction_files=ctx.get("transaction_files"), research=views,
                             holdings_files=ctx.get("holdings_files"))
        pdf = save / f"{ctx.get('name', 'pipeline')}_portfolio_review.pdf"
        return {"output": str(pdf), "ok": pdf.exists() and os.path.getmtime(pdf) >= ctx["t0"]}
    if k == "brief":
        from .brief_agent import run_brief
        tag = cfgs["writer"]["config_list"][0]["model"].split("/")[-1]
        save = REPORTS / f"brief_{tag}"
        name = f"brief_{date.today().isoformat()}"
        run_brief(cfgs["writer"], ctx["tickers"], os.path.relpath(save, ctx["cwd"]).replace("\\", "/"), name=name)
        pdf = save / f"{name}.pdf"
        return {"output": str(pdf), "ok": pdf.exists() and os.path.getmtime(pdf) >= ctx["t0"]}
    raise ValueError(k)


def run_pipeline(steps, cfgs, tickers, transaction_files=None, portfolio_file=None, watchlist=None, max_steps=None,
                 only=None, name="pipeline", title="Portfolio Review", runner=None, holdings_files=None):
    """Fuehrt die geplanten Schritte der Reihe nach aus (Fehler isoliert) und schreibt ein Protokoll.
    cfgs: {"writer", "committee", "forecast", "classifier"} (llm_configs). max_steps begrenzt die LLM-Schritte,
    only z. B. {"forecast", "news"}. runner: Ersatzfunktion fuer Tests."""
    runner = runner or _run_step
    todo = [s for s in steps if s["step"] != "skip" and (not only or s["step"] in only)]
    if max_steps is not None and len(todo) > max_steps:
        keep = todo[:max_steps]
        if not any(s["step"] == "portfolio" for s in keep) and any(s["step"] == "portfolio" for s in todo):
            keep = keep[:-1] + [next(s for s in todo if s["step"] == "portfolio")] if keep else keep
        print(f"Budget: {len(keep)} von {len(todo)} Schritten werden ausgefuehrt (max_steps={max_steps}).")
        todo = keep
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    RESEARCH.mkdir(parents=True, exist_ok=True)
    (RESEARCH / "pipeline_runs").mkdir(exist_ok=True)
    log = {"started": stamp, "tickers": tickers, "steps": []}
    ctx = {"cwd": os.getcwd(), "tickers": tickers, "transaction_files": transaction_files, "portfolio_file": portfolio_file,
           "holdings_files": holdings_files,
           "watchlist": watchlist, "name": name, "title": title}
    usage0 = openrouter_usage(cfgs["writer"])
    for i, s in enumerate(todo, 1):
        print(f"\n{'=' * 80}\n[{i}/{len(todo)}] {s['step']} {s['ticker']}: {s['reason']}\n{'=' * 80}")
        t0 = time.time()
        ctx["t0"] = t0
        u0 = openrouter_usage(cfgs["writer"])
        rec = dict(s)
        try:
            rec.update(runner(s, cfgs, ctx))
        except Exception as e:
            rec.update(ok=False, error=f"{type(e).__name__}: {str(e)[:300]}", trace=traceback.format_exc()[-1500:])
            print(f"FEHLER in {s['step']} {s['ticker']}: {rec['error']}")
        rec["seconds"] = round(time.time() - t0)
        u1 = openrouter_usage(cfgs["writer"])
        rec["cost_usd"] = round(u1 - u0, 4) if u0 is not None and u1 is not None else None
        log["steps"].append(rec)
        _write_log(log, stamp)
    usage1 = openrouter_usage(cfgs["writer"])
    log["finished"] = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    log["cost_usd"] = round(usage1 - usage0, 4) if usage0 is not None and usage1 is not None else None
    log["research_views"] = research_views(tickers)
    _write_log(log, stamp)
    try:                                            # HTML-Dashboard (ohne LLM): reports/site/index.html
        from .html_site import build_site
        log["dashboard"] = build_site(tickers)
    except Exception as e:
        print(f"Dashboard nicht erzeugt: {e}")
    print(f"\nProtokoll: {RESEARCH / 'pipeline_runs' / (stamp + '.md')}")
    return log


def _write_log(log, stamp):
    base = RESEARCH / "pipeline_runs" / stamp
    json.dump(log, open(str(base) + ".json", "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
    lines = [f"# Pipeline-Lauf {log['started']}", "", "| # | Schritt | Titel | Grund | Ergebnis | Sekunden | Kosten (USD) |",
             "|---|---|---|---|---|---|---|"]
    for i, s in enumerate(log["steps"], 1):
        res = "ok" if s.get("ok") else ("Fehler: " + s.get("error", "kein Ergebnis"))
        if s.get("recommendation"):
            res += f" ({s['recommendation']}, Ziel {s.get('target')})"
        if s.get("direction"):
            res += f" ({s['direction']})"
        lines.append(f"| {i} | {s['step']} | {s['ticker']} | {s['reason']} | {res} | {s.get('seconds', '')} | "
                     f"{s.get('cost_usd') if s.get('cost_usd') is not None else 'n/a'} |")
    if log.get("cost_usd") is not None:
        lines += ["", f"Gesamtkosten: USD {log['cost_usd']}"]
    if log.get("research_views"):
        lines += ["", "## Research-Sicht je Position", "", research_text(log["research_views"])]
    open(str(base) + ".md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
