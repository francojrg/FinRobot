"""
Earnings Preview (Beta): eine Seite vor anstehenden Quartalszahlen.

Eingaben (nur vorhandene Daten, keine neuen Quellen): Konsens fuer das laufende Quartal, Revisionen und letzte
Ueberraschungen (Yahoo, [1]), Thesen mit Signposts und Status aus dem Thesen-Protokoll sowie der Ausblick aus dem
letzten Earnings Review ([2]) und der KPI-Verlauf ([3]). Ein Modellaufruf schreibt: worauf achten (3-5 Punkte mit
Schwelle), Bull/Base/Bear-Szenario mit Folgen fuer die Thesen und die wichtigsten KPIs. Jede Zahl wird gegen die
Eingaben geprueft (wie im Chat). Ergebnis: research/previews/<TICKER>_<Termin>.json.
"""
import glob
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from . import agent_settings as _AS  # Prompts/Parameter aus der App (research/agent_settings.json)

AIF = Path(__file__).resolve().parents[1]
DIR = AIF / "research" / "previews"
HORIZON_DAYS = 14


def path_for(t, when):
    return DIR / f"{t.upper()}_{when}.json"


def latest(t):
    fs = sorted(glob.glob(str(DIR / f"{t.upper()}_*.json")))
    if not fs:
        return None
    try:
        return json.load(open(fs[-1], encoding="utf-8"))
    except Exception:
        return None


def upcoming_earnings(tickers, today=None):
    """{ticker: datum} fuer Quartalszahlen in den naechsten HORIZON_DAYS Tagen (Yahoo-Kalender, Zwischenspeicher)."""
    from .events import events
    today = today or date.today()
    end = (today + timedelta(days=HORIZON_DAYS)).isoformat()
    out = {}
    try:
        for x in events(tickers).get("upcoming", []):
            if x.get("type") == "Quarterly results" and today.isoformat() <= x["date"] <= end:
                out.setdefault(x["ticker"].upper(), x["date"])
    except Exception:
        pass
    return out


def _quarter_consensus(t):
    from finrobot.functional import outlook as o
    tk = o._ticker(t)
    rev, eps = o._get(tk, "revenue_estimate"), o._get(tk, "earnings_estimate")
    try:
        info = tk.info or {}
    except Exception:
        info = {}
    q = {}
    for name, df, scale in (("revenue", rev, 1e6), ("eps", eps, 1)):
        if df is None or "0q" not in df.index:
            continue
        g = lambda c: o._cell(df, "0q", c)
        q[name] = {"avg": g("avg"), "low": g("low"), "high": g("high"), "n": g("numberOfAnalysts"),
                   "year_ago": g("yearAgoRevenue") if name == "revenue" else g("yearAgoEps"), "growth": g("growth")}
        for k in ("avg", "low", "high", "year_ago"):
            if q[name][k] is not None and name == "revenue":
                q[name][k] = q[name][k] / scale
    foreign = info.get("financialCurrency") and info.get("currency") and info["financialCurrency"] != info["currency"]
    return q, (info.get("financialCurrency") or "USD"), bool(foreign)


def build_context(t):
    """Eingabetext mit Quellenmarken [1]-[3] und ob es genug Material gibt."""
    from finrobot.functional.outlook import estimate_momentum
    from .kpi_history import history
    from .quarterly_data import load_thesis_log
    lines = []
    try:
        q, cur, foreign = _quarter_consensus(t)
    except Exception:
        q, cur, foreign = {}, "USD", False
    lines.append(f"[1] CONSENSUS FOR THE QUARTER TO BE REPORTED (Yahoo Finance, retrieved {date.today().isoformat()}):")
    if q.get("revenue"):
        r = q["revenue"]
        lines.append(f"- Revenue estimate: {r['avg']:,.1f} million (range {r['low'] or 0:,.1f} to {r['high'] or 0:,.1f}, "
                     f"{int(r['n'] or 0)} analysts); year-ago quarter {r['year_ago'] or 0:,.1f} million"
                     + (f"; growth {r['growth'] * 100:+.1f}%" if r.get("growth") is not None else "")
                     + (f" (currency as reported by Yahoo; reporting currency {cur})" if foreign else f" ({cur})"))
    if q.get("eps"):
        e = q["eps"]
        lines.append(f"- EPS estimate: {e['avg']:.2f} (range {e['low'] or 0:.2f} to {e['high'] or 0:.2f}, {int(e['n'] or 0)} analysts);"
                     f" year-ago quarter {e['year_ago'] or 0:.2f}" + (f"; growth {e['growth'] * 100:+.1f}%" if e.get("growth") is not None else ""))
    if not q:
        lines.append("- no quarterly consensus available")
    try:
        mo = estimate_momentum(t)
        for tr in mo.get("trend", []):
            if tr.get("current") is not None:
                lines.append(f"- EPS consensus {tr['period']}: {tr['current']:.2f} today, {tr['d90'] if tr['d90'] is not None else 'n/a'} 90 days ago;"
                             f" analysts raising/cutting in 30 days: {int(tr.get('up30') or 0)}/{int(tr.get('down30') or 0)}")
        for su in mo.get("surprises", [])[:4]:
            if su.get("actual") is not None and su.get("estimate") is not None:
                lines.append(f"- Quarter ending {su['quarter']}: EPS {su['actual']:.2f} vs estimate {su['estimate']:.2f}"
                             + (f" (surprise {su['surprise'] * 100:+.1f}%)" if su.get("surprise") is not None else ""))
    except Exception:
        pass
    log = load_thesis_log(t)
    lines.append("")
    lines.append("[2] INVESTMENT THESES (thesis log of the earnings reviewer) AND LAST OUTLOOK:")
    if log:
        e = log[-1]
        for th in e.get("theses", []):
            lines.append(f"- {th.get('thesis', '')[:220]} | signpost: {th.get('signpost', '')[:260]} | status: "
                         f"{th.get('current_status')} (history: {', '.join(f'{k}={v}' for k, v in (th.get('statuses') or {}).items())})")
    else:
        lines.append("- no thesis log yet")
    ba = sorted(glob.glob(str(AIF / "reports" / f"{t.upper()}_earnings_multi_*" / "*_build_args.json")), key=os.path.getmtime)
    if ba:
        try:
            outlook = json.load(open(ba[-1], encoding="utf-8")).get("outlook")
            if outlook:
                lines.append(f"- Outlook in the last earnings review: {str(outlook)[:900]}")
        except Exception:
            pass
    lines.append("")
    lines.append("[3] COMPANY KPIs PER QUARTER (from the earnings reviews):")
    try:
        for k in history(t)[:6]:
            lines.append(f"- {k['name']} ({k['unit']}): " + ", ".join(f"{lab} {v:,.1f}" for lab, v in k["points"][-6:]))
    except Exception:
        pass
    return "\n".join(lines), bool(q or log)


PROMPT = """You prepare a one-page earnings preview for {t}, reporting on {when}. Use ONLY the figures in SOURCES and cite
them as [1], [2] or [3]. Do not invent consensus figures, guidance or KPIs. Answer with JSON only:
{{"headline": one sentence (max 25 words) on what decides the reaction,
 "consensus_note": 1-2 sentences on the consensus and its recent revisions,
 "watch": [3-5 items {{"item": metric or topic, "why": why it matters for the theses, "threshold": the level that
          would confirm or break the thesis, from the signposts or consensus}}],
 "scenarios": [{{"case": "bull"}}, {{"case": "base"}}, {{"case": "bear"}}] each with "what" (what would have to be
          reported), "thesis_impact" (which thesis strengthens or weakens) and "signal" (what management commentary
          would indicate this case),
 "kpis": [up to 4 KPI names from [3] to check first]}}
Write in English, be concrete, keep each field short."""


def _parse_json(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON in the answer")
    return json.loads(m.group(0))


def run(t, when, model=None, llm=None):
    """Preview erstellen und speichern. Rueckgabe: das gespeicherte Dict."""
    from finrobot.functional.fact_check import SourceIndex, run_fact_check
    from .chat import call_llm
    ctx, enough = build_context(t)
    if not enough:
        raise RuntimeError("not enough material for a preview (no consensus and no thesis log)")
    msgs = [{"role": "system", "content": "You are a sell-side equity analyst. Precise, sourced, no hype."},
            {"role": "user", "content": _AS.get("preview.prompt", PROMPT).format(t=t.upper(), when=when) + "\n\nSOURCES:\n" + ctx}]
    raw, cost = (llm or call_llm)(msgs, model=model, max_tokens=1800)
    d = _parse_json(raw)
    texts = [("Headline", d.get("headline", "")), ("Consensus", d.get("consensus_note", ""))]
    texts += [(f"Watch {i}", " ".join(str(w.get(k, "")) for k in ("item", "why", "threshold")))
              for i, w in enumerate(d.get("watch") or [], 1)]
    texts += [(f"Scenario {s.get('case')}", " ".join(str(s.get(k, "")) for k in ("what", "thesis_impact", "signal")))
              for s in d.get("scenarios") or []]
    src = SourceIndex("[1-3] preview inputs")
    src.add_text(ctx)
    fc = run_fact_check(texts, [src], None)
    out = {"ticker": t.upper(), "earnings_date": when, "created": datetime.now().isoformat(timespec="seconds"),
           "model": model, "cost": cost, **{k: d.get(k) for k in ("headline", "consensus_note", "watch", "scenarios", "kpis")},
           "fc": {"matched": fc.get("matched"), "total": fc.get("total_claims"),
                  "unmatched": [c.get("text") for c in fc.get("claims", []) if not c.get("source")][:12]},
           "inputs": ctx}
    DIR.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(path_for(t, when), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return out
