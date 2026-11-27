"""
Daten fuer die Home-Seite der App: sammelt alles aus den vorhandenen Agenten-Ergebnissen
(Weekly Brief, Portfolio-Dashboard, Termine, News, Pipeline-Protokoll) und einen kleinen Kursabruf
fuer die Tagesbewegung. Python rechnet, die Home-Komponente zeigt nur an.
"""
import glob
import json
import re
import time
from datetime import date, timedelta
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
RESEARCH = AIF / "research"
QUOTES = RESEARCH / "quotes.json"

EVENT_DE = {"Quarterly results": "Earnings", "Ex-dividend": "Ex-dividend",
            "Dividend payment": "Dividend payment", "Announced in the news": "Announced"}
STATUS_RANK = {"broken": 3, "weakened": 2, "intact": 1, "strengthened": 0}


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _newest(pattern):
    files = sorted(glob.glob(str(pattern)))
    return Path(files[-1]) if files else None


def _clean(s):
    """Quellenmarker wie [1] aus Agententexten entfernen."""
    return re.sub(r"\s*\[\d+(?:,\s*\d+)*\]", "", str(s or "")).strip()


def _num(v):
    return v if isinstance(v, (int, float)) and v == v else None


# ------------------------------------------------------------------ Kurse (Tagesbewegung)
def quotes(tickers, max_age_min=15, refresh=False, cache_path=None):
    """{ticker: {"price", "chg"}} aus Yahoo, zwischengespeichert. Ohne Netz: letzter Stand oder leer.
    cache_path: eigene Cache-Datei (z. B. fuer die Watchlist), sonst research/quotes.json."""
    QUOTES = Path(cache_path) if cache_path else globals()["QUOTES"]
    tickers = sorted({t.upper() for t in tickers})
    cache = _load(QUOTES) or {}
    fresh = time.time() - cache.get("ts", 0) < max_age_min * 60
    failed_recently = time.time() - cache.get("fail_ts", 0) < 5 * 60  # ohne Netz nicht bei jedem Seitenaufruf neu versuchen
    if cache.get("tickers") == tickers and (fresh or failed_recently) and not refresh:
        return cache
    out = {}
    try:
        import yfinance as yf
        df = yf.download(tickers, period="7d", interval="1d", progress=False, auto_adjust=False,
                         group_by="ticker", threads=True)
        for t in tickers:
            try:
                s = (df[t]["Close"] if len(tickers) > 1 else df["Close"]).dropna()
                if len(s) >= 2:
                    out[t] = {"price": float(s.iloc[-1]), "chg": float(s.iloc[-1] / s.iloc[-2] - 1),
                              "asof": str(s.index[-1].date())}
            except Exception:
                continue
    except Exception:
        pass
    if not out:
        c = cache if cache.get("tickers") == tickers else {"tickers": tickers, "ts": 0, "data": {}}
        c["fail_ts"] = time.time()
        try:
            QUOTES.parent.mkdir(parents=True, exist_ok=True)
            json.dump(c, open(QUOTES, "w", encoding="utf-8"), indent=1)
        except Exception:
            pass
        return c
    c = {"tickers": tickers, "ts": time.time(), "updated": time.strftime("%Y-%m-%d %H:%M"), "data": out}
    try:
        QUOTES.parent.mkdir(parents=True, exist_ok=True)
        json.dump(c, open(QUOTES, "w", encoding="utf-8"), indent=1)
    except Exception:
        pass
    return c


# ------------------------------------------------------------------ Bausteine
def _last_run():
    f = _newest(RESEARCH / "pipeline_runs" / "*.json")
    d = _load(f) if f else None
    if not d:
        return None
    steps = d.get("steps") or []
    ok = sum(1 for s in steps if s.get("ok", s.get("status") == "ok"))
    return {"stamp": d.get("finished") or d.get("started"), "steps": len(steps), "ok": ok,
            "cost": _num(d.get("cost_usd"))}


def _curve(c):
    if not c or not c.get("dates"):
        return None
    return {"d": c["dates"], "v": [round(x, 2) if _num(x) is not None else None for x in c["values"]]}


def _value_series(dash):
    """Depotwert in EUR (aus der Transaktionshistorie) oder, falls nicht vorhanden, Index ab 100."""
    perf = dash.get("performance") or {}
    cv = perf.get("curves") or {}
    if cv.get("value"):
        return {"kind": "eur", "value": _curve(cv["value"]), "bench": _curve(cv.get("bench_value")),
                "invested": _curve(cv.get("invested")), "twr": _curve(cv.get("ttwror")), "btwr": _curve(cv.get("bench"))}
    if dash.get("curve_port"):
        return {"kind": "index", "value": _curve(dash["curve_port"]), "bench": _curve(dash.get("curve_bench")),
                "invested": None}
    return None


def _wavg(positions, dpos, field):
    """Gewichteter Durchschnitt einer Kennzahl ueber die Positionen, die sie haben."""
    pts = [(p["w"], _num(dpos.get(p["t"], {}).get(field))) for p in positions]
    pts = [(w, v) for w, v in pts if v is not None and w]
    tw = sum(w for w, _ in pts)
    return sum(w * v for w, v in pts) / tw if tw > 0.5 * sum(p["w"] for p in positions or [{"w": 1}]) else None


def _top(d, n=6):
    items = sorted(((k, v) for k, v in (d or {}).items() if _num(v)), key=lambda x: -x[1])
    head = items[:n]
    rest = sum(v for _, v in items[n:])
    if rest > 0.0005:
        head.append(("Sonstige", rest))
    return [{"k": k, "v": round(v, 4)} for k, v in head]


def _ret_from(curve, start_iso):
    """Rendite einer Kurve ab dem ersten Datum >= start_iso bis zum Ende."""
    if not curve or not curve.get("dates"):
        return None
    pts = [(d, v) for d, v in zip(curve["dates"], curve["values"]) if _num(v) is not None]
    first = next(((d, v) for d, v in pts if d >= start_iso), None)
    if not first or not pts or first[1] == 0:
        return None
    return pts[-1][1] / first[1] - 1


def _index_periods(dash):
    """Zeitraum-Renditen aus der Kursreihe, wenn keine Transaktionshistorie vorliegt (Gewichte-Datei)."""
    cp, cb = dash.get("curve_port"), dash.get("curve_bench")
    if not cp or not cp.get("dates"):
        return []
    last = date.fromisoformat(cp["dates"][-1])
    out = []
    for name, start, ann in (("YTD", date(last.year, 1, 1), False), ("1 year", last - timedelta(days=365), False),
                             ("Since start", date.fromisoformat(cp["dates"][0]), False)):
        r, b = _ret_from(cp, start.isoformat()), _ret_from(cb, start.isoformat())
        out.append({"period": name, "ttwror": r, "bench": b, "annualized": ann})
    return out


def _brief_texts(brief_json):
    """Texte des Brief-Agenten genau zu diesem Brief (gleicher Name/Datum). Bricht der Schreibschritt ab (z. B.
    Ausgabelimit), gibt es keine Texte - frueher wurden dann die Texte eines aelteren Briefs angezeigt, unter Umstaenden
    von einem anderen Depot."""
    if not brief_json:
        return None, {}
    name = Path(brief_json).stem
    hits = sorted(glob.glob(str(AIF / "reports" / "brief_*" / f"{name}_build_args.json")), key=lambda f: Path(f).stat().st_mtime)
    return (hits[-1], _load(hits[-1]) or {}) if hits else (None, {})


# ------------------------------------------------------------------ Gesamtpaket
def home_payload(tickers=None, refresh=False, events_fn=None, news_fn=None):
    bj = _newest(RESEARCH / "briefs" / "brief_*.json")
    brief = _load(bj or "") or {}
    texts = _brief_texts(bj)[1]
    dash = _load(RESEARCH / "portfolio_dashboard.json") or {}
    bpos = brief.get("positions") or []
    tickers = [t.upper() for t in (tickers or [p["ticker"] for p in bpos] or
                                   [p["ticker"] for p in dash.get("positions") or []])]
    dpos = {p["ticker"].upper(): p for p in dash.get("positions") or []}
    items = {str(x.get("ticker", "")).upper(): x for x in texts.get("items") or []}
    q = quotes(tickers, refresh=refresh).get("data", {})

    # Positionen: Gewicht, Status, Thesen, Tagesbewegung
    positions, thesis_tally = [], {"intact": 0, "strengthened": 0, "weakened": 0, "broken": 0}
    seen = set()
    for p in bpos or [{"ticker": t, "level": "none"} for t in dpos]:
        t = p["ticker"].upper()
        seen.add(t)
        d = dpos.get(t, {})
        th = [x.get("status") for x in p.get("theses") or [] if x.get("status")]
        if not dpos or t in dpos:            # nur Titel im aktuellen Depot zaehlen
            for s in th:
                thesis_tally[s] = thesis_tally.get(s, 0) + 1
            if th:
                thesis_tally["firms"] = thesis_tally.get("firms", 0) + 1
                if all(s in ("intact", "strengthened") for s in th):
                    thesis_tally["firms_ok"] = thesis_tally.get("firms_ok", 0) + 1
        worst = max(th, key=lambda s: STATUS_RANK.get(s, 0)) if th else None
        positions.append({
            "t": t, "name": d.get("name") if d.get("name") and d.get("name") != t else p.get("name") or t,
            "w": _num(p.get("weight")) or _num(d.get("weight")) or 0, "level": p.get("level", "none"),
            "thesis": worst, "n_th": len(th), "sector": d.get("sector"), "value": _num(d.get("value_eur")),
            "ret1y": _num(d.get("ret_1y")) or _num(p.get("ret_1y")), "rc": _num(p.get("risk_contrib")) or _num(d.get("risk_contrib")),
            "chg": (q.get(t) or {}).get("chg"), "upside": _num(d.get("upside"))})
    positions.sort(key=lambda x: -x["w"])

    # Handlungsbedarf
    actions = []
    for p in bpos:
        if p.get("level") in ("decide", "read"):
            it = items.get(p["ticker"].upper(), {})
            trig = [x["text"] for x in p.get("triggers") or [] if x.get("level") == p["level"]] or \
                   [x["text"] for x in p.get("triggers") or []]
            actions.append({"t": p["ticker"].upper(), "level": p["level"], "w": _num(p.get("weight")),
                            "why": _clean(it.get("what") or (trig[0] if trig else "")),
                            "next": _clean(it.get("next_step")), "more": trig[1:3]})
    actions.sort(key=lambda a: (a["level"] != "decide", -(a["w"] or 0)))

    # Kennzahlen
    stats = dash.get("stats") or {}
    perf = dash.get("performance") or {}
    has_tx = _num(perf.get("final_value")) is not None
    period_list = perf.get("periods") or _index_periods(dash)
    periods = {x["period"]: x for x in period_list}
    # Ohne Transaktionen ist der EUR-Wert nur ein Rechenbetrag (z. B. 100.000 €), kein echter Depotwert
    value = _num(perf.get("final_value")) if has_tx else None
    notional = sum(p["value"] for p in positions if p["value"]) or None
    day_eur = day_pct = None
    if any(p["chg"] is not None for p in positions):
        day_pct = sum(p["w"] * p["chg"] for p in positions if p["chg"] is not None)
        day_eur = day_pct * value if value else None
    struct = dash.get("structure") or {}
    weights = sorted((p["w"] for p in positions), reverse=True)
    counts = {k: sum(p["level"] == k for p in positions) for k in ("decide", "read", "none")}
    trig_by = {p["ticker"].upper(): p.get("triggers") for p in bpos}
    counts["handled"] = sum(1 for a in actions if _act_status(a["t"], trig_by.get(a["t"])))
    counts["open"] = len(actions) - counts["handled"]

    # Termine
    upcoming, announced, ev_updated, next_earn = [], [], None, None
    try:
        if events_fn is None:
            from .events import events as events_fn
        e = events_fn(tickers, refresh=refresh)
        horizon = (date.today() + timedelta(days=45)).isoformat()
        upcoming = [{"date": x["date"], "t": x["ticker"], "type": EVENT_DE.get(x["type"], x["type"]),
                     "detail": x.get("detail", "")} for x in e.get("upcoming", []) if x["date"] <= horizon]
        announced = [{"date": x["date"], "t": x["ticker"], "title": x.get("detail", ""), "url": x.get("url", "")}
                     for x in e.get("announced", [])[:5]]
        ev_updated = e.get("updated")
        ne = next((x for x in sorted(e.get("upcoming", []), key=lambda x: x["date"]) if x["type"] == "Quarterly results" and x["date"] >= date.today().isoformat()), None)
        if ne:
            same = sorted({x["ticker"] for x in e.get("upcoming", []) if x["type"] == "Quarterly results" and x["date"] == ne["date"]})
            next_earn = {"date": ne["date"], "t": ne["ticker"], "type": "Earnings", "more": len(same) - 1}
    except Exception:
        pass
    week_end = (date.today() + timedelta(days=7)).isoformat()
    events_week = sum(1 for x in upcoming if x["date"] <= week_end)
    try:
        news_kpi = news_payload(tickers)["kpi"]
    except Exception:
        news_kpi = {}

    # News
    try:
        if news_fn is None:
            from .app_backend import notable_news as news_fn
        news = [{"date": s.get("date", "")[:10], "t": s.get("ticker", ""), "title": s.get("title", ""),
                 "url": s.get("url", ""), "dir": s.get("direction", "neutral"), "car": _num(s.get("car01")),
                 "mat": s.get("materiality", 1), "pub": s.get("publisher") or ""} for s in news_fn(tickers, days=10, limit=8)]
    except Exception:
        news = []

    return {
        "asof": brief.get("date") or dash.get("date"), "name": dash.get("title") or "Portfolio",
        "headline": _clean(texts.get("headline")), "summary": _clean(texts.get("summary")),
        "brief_text_missing": bool(brief) and not texts,
        "kpi": {
            "value": value, "value_kind": "eur" if has_tx else None, "notional": notional,
            "day_eur": day_eur, "day_pct": day_pct,
            "ytd": _num((periods.get("YTD") or {}).get("ttwror")), "ytd_bench": _num((periods.get("YTD") or {}).get("bench")),
            "y1": _num((periods.get("1 year") or {}).get("ttwror")), "y1_bench": _num((periods.get("1 year") or {}).get("bench")),
            "cagr": _num(stats.get("cagr")), "bench_cagr": _num(stats.get("bench_cagr")),
            "counts": counts, "beta": _num(stats.get("beta")), "max_dd": _num(stats.get("max_dd")),
            "vol": _num(stats.get("vol")), "sharpe": _num(stats.get("sharpe")), "var95": _num(stats.get("var95_1d")),
            "top3": sum(weights[:3]) if weights else None, "eff_n": _num(struct.get("effective_n")),
            "theses": thesis_tally, "next_earn": next_earn, "events_week": events_week, "news": news_kpi,
            "dividends": _num(perf.get("dividends_total")), "fees": _num(perf.get("fees_total")),
            "invested": _num(perf.get("net_invested")), "mwr": _num(perf.get("mwr")),
            "fwd_pe": _wavg(positions, dpos, "forward_pe"), "upside": _wavg(positions, dpos, "upside"),
            "growth": _wavg(positions, dpos, "revenue_growth"),
        },
        "periods": [{"p": x["period"], "r": _num(x.get("ttwror")), "b": _num(x.get("bench")),
                     "ann": bool(x.get("annualized"))} for x in period_list],
        "series": _value_series(dash),
        "alloc": [{"k": p["t"], "v": round(p["w"], 4)} for p in positions],
        "struct": {"Sector": _top(struct.get("sector")), "Country": _top(struct.get("country")),
                   "Currency": _top(struct.get("currency"))},
        "risk": {"stress": [{"s": x["scenario"], "p": _num(x.get("portfolio")), "b": _num(x.get("benchmark"))}
                            for x in dash.get("stress") or []],
                 "rc": sorted([{"t": p["t"], "w": p["w"], "rc": p["rc"]} for p in positions if p["rc"] is not None],
                              key=lambda x: -x["rc"])[:5]},
        "positions": positions, "actions": actions, "upcoming": upcoming[:8], "announced": announced,
        "news": news, "events_updated": ev_updated, "run": _last_run(), "gaps": brief.get("gaps") or [],
        "quotes_asof": max((v.get("asof", "") for v in q.values()), default=None),
    }


# ------------------------------------------------------------------ Portfolio-Seite
STRAT_DE = {"current": "Current weights", "min_variance": "Minimum variance", "max_sharpe": "Max Sharpe",
            "hrp": "HRP (risk parity)", "equal_weight": "Equal weight",
            "Current weights (rebalanced)": "Current weights", "Equal weight": "Equal weight",
            "Min variance": "Minimum variance", "Max Sharpe": "Max Sharpe", "HRP": "HRP (risk parity)",
            "MSCI ACWI (EUR)": "MSCI ACWI (EUR)"}


def _warn_de(w):
    """Datenhinweise der Performance-Rechnung auf Deutsch und knapp; None = weglassen (doppelt)."""
    import re as _re
    m = _re.match(r"ISINs without Yahoo ticker.*?:\s*(.+)$", w)
    if m:
        return ("No Yahoo quote (usually certificates, warrants or delisted stocks): " + m.group(1)
                + ". Buys, sells and dividends are included; the holding itself is not valued.")
    if _re.match(r"\d+ bookings in \d+ instruments without Yahoo price", w):
        return None
    m = _re.match(r"(\d{4}-\d{2}-\d{2}) (buy|sell) (\S+): trade price EUR ([\d.,]+) vs market close EUR ([\d.,]+)", w)
    if m:
        return (f"{m.group(1)} {m.group(2)} {m.group(3)}: execution price €{m.group(4)} differs strongly from the close "
                f"€{m.group(5)} – check the ticker mapping or a split")
    m = _re.match(r"(\d{4}-\d{2}-\d{2}) sell (\S+): (\S+) shares but only (\S+) held", w)
    if m:
        return (f"{m.group(1)} sell {m.group(2)}: {m.group(3)} shares sold but only {m.group(4)} held according to the export "
                f"(incomplete history?)")
    m = _re.match(r"(\S+): daily price move of (\S+) on (\S+)", w)
    if m:
        return f"{m.group(1)}: price jump of {m.group(2)} on {m.group(3)} in the Yahoo data (often genuine for meme stocks)"
    return w


_TX_CACHE = {}


def _transactions_fallback():
    """Buchungsliste aus den Exporten des letzten App-Laufs, falls das Dashboard sie (noch) nicht enthaelt."""
    try:
        runs = sorted(p for p in (RESEARCH / "app_runs").glob("*.json") if not p.stem.endswith("_done"))
        for p in reversed(runs):
            files = [f for f in (_load(p) or {}).get("transaction_files") or [] if Path(f).exists()]
            if not files:
                continue
            key = tuple((f, Path(f).stat().st_mtime) for f in files)
            if key not in _TX_CACHE:
                from . import transactions as tr
                tx, _ = tr.read_all(files)
                tx, _ = tr.attach_tickers(tx)
                _TX_CACHE.clear()
                _TX_CACHE[key] = tr.compact(tx)
            return _TX_CACHE[key]
    except Exception:
        pass
    return []


def portfolio_payload():
    """Daten fuer die Portfolio-Detailseite (aus research/portfolio_dashboard.json, ergaenzt um den Brief-Status)."""
    dash = _load(RESEARCH / "portfolio_dashboard.json") or {}
    if not dash:
        return None
    brief = _load(_newest(RESEARCH / "briefs" / "brief_*.json") or "") or {}
    lvl = {p["ticker"].upper(): p.get("level") for p in brief.get("positions") or []}
    worst = {}
    for p in brief.get("positions") or []:
        th = [x.get("status") for x in p.get("theses") or [] if x.get("status")]
        if th:
            worst[p["ticker"].upper()] = max(th, key=lambda s: STATUS_RANK.get(s, 0))
    perf = dash.get("performance") or {}
    pp = {p["ticker"].upper(): p for p in perf.get("positions") or []}
    q = (_load(QUOTES) or {}).get("data", {})
    pos = []
    for p in dash.get("positions") or []:
        t = p["ticker"].upper()
        x = pp.get(t, {})
        pos.append({"t": t, "name": p.get("name") if p.get("name") != t else None, "sector": p.get("sector"),
                    "w": _num(p.get("weight")), "value": _num(x.get("market_value")) or _num(p.get("value_eur")),
                    "ret1y": _num(p.get("ret_1y")), "vol": _num(p.get("vol")), "rc": _num(p.get("risk_contrib")),
                    "pe": _num(p.get("forward_pe")), "upside": _num(p.get("upside")), "growth": _num(p.get("revenue_growth")),
                    "cost": _num(x.get("cost_open")), "unreal": _num(x.get("unrealized")), "real": _num(x.get("realized")),
                    "div": _num(x.get("dividends")), "pl": _num(x.get("total_pl")), "irr": _num(x.get("irr")),
                    "chg": _num((q.get(t) or {}).get("chg")), "level": lvl.get(t), "thesis": worst.get(t)})
    pos.sort(key=lambda x: -(x["w"] or 0))
    has_tx = _num(perf.get("final_value")) is not None
    bt = dash.get("backtest") or {}
    return {
        "date": dash.get("date"), "title": "Portfolio", "mode": "tx" if has_tx else "weights",
        "cap": dash.get("cap"), "sector_cap": dash.get("sector_cap"), "years_hist": dash.get("years_hist"),
        "stats": dash.get("stats") or {}, "bench_stats": dash.get("bench_stats") or {},
        "stress": dash.get("stress") or [], "struct": dash.get("structure") or {},
        "positions": pos,
        "series": _value_series(dash),
        "periods": [{"p": x["period"], "r": _num(x.get("ttwror")), "b": _num(x.get("bench")),
                     "mwr": _num(x.get("mwr")), "pl": _num(x.get("pl_eur")), "ann": bool(x.get("annualized"))}
                    for x in (perf.get("periods") or _index_periods(dash))],
        "years": [{"p": x["period"], "r": _num(x.get("ttwror")), "b": _num(x.get("bench")), "pl": _num(x.get("pl_eur"))}
                  for x in perf.get("calendar_years") or []],
        "perf": {k: perf.get(k) for k in ("final_value", "net_invested", "mwr", "ttwror", "ttwror_pa", "bench_tw_pa",
                                          "bench_mwr", "max_dd", "n_trades", "fees_total", "dividends_total", "start",
                                          "end", "years", "bench_final_value")} if has_tx else None,
        "never_sold": perf.get("never_sold") if has_tx else None,
        "attribution": perf.get("attribution") or [], "decisions": perf.get("decisions") or [],
        "mistakes": perf.get("mistakes") or [], "exits": perf.get("exits") or [], "costs": perf.get("costs") or {},
        "warnings": [x for x in (_warn_de(w) for w in perf.get("warnings") or []) if x],
        "tx": (perf.get("transactions") or _transactions_fallback()) if has_tx else [],
        "opt": [{"k": k, "name": STRAT_DE.get(k, k), **(v or {})} for k, v in (dash.get("opt_stats") or {}).items()],
        "opt_w": {STRAT_DE.get(k, k): v for k, v in (dash.get("opt_weights") or {}).items()},
        "bt": {"start": bt.get("start"), "end": bt.get("end"),
               "stats": [{"name": STRAT_DE.get(k, k), **(v or {})} for k, v in (bt.get("stats") or {}).items()],
               "curves": [{"name": STRAT_DE.get(k, k), **(_curve(v) or {})} for k, v in (bt.get("curves") or {}).items()]},
    }


# ------------------------------------------------------------------ News-Seite
def news_payload(tickers, days=21):
    """News-Seite: nur Titel des aktuellen Portfolios (andere Watchlist-Titel aus frueheren Laeufen bleiben aussen vor)."""
    tick = {t.upper() for t in tickers}
    sig = _load(AIF / "news" / "signals_latest.json") or {}
    since = (date.today() - timedelta(days=days)).isoformat()
    items = []
    try:
        from .news_tracker import load_store
        for s in load_store():
            t = str(s.get("ticker", "")).upper()
            if t not in tick or s.get("date", "")[:10] < since or not s.get("relevant", True) or "materiality" not in s:
                continue
            items.append({"date": s["date"][:16], "t": t, "title": s.get("title", ""), "url": s.get("url", ""),
                          "dir": s.get("direction", "neutral"), "mat": s.get("materiality", 1),
                          "cat": s.get("category", ""), "car": _num(s.get("car01")), "pub": s.get("publisher") or s.get("source_type", ""),
                          "sum": _clean(s.get("summary", ""))[:280]})
    except Exception:
        pass
    items.sort(key=lambda x: (x["date"], x["mat"]), reverse=True)
    stories = [{"t": t, **x} for t, xs in (sig.get("stories") or {}).items() if t.upper() in tick for x in xs]
    stories.sort(key=lambda x: ({"escalating": 0, "developing": 1, "new": 2}.get(x.get("status"), 3), x.get("last_update", "")), reverse=False)
    themes = []
    for th in sig.get("themes") or []:
        tt = [t for t in th.get("tickers") or [] if t.upper() in tick]
        if tt:
            themes.append({"theme": th.get("theme"), "tickers": tt, "explanation": _clean(th.get("explanation")),
                           "risk": th.get("risk")})
    signals = []
    for t, v in (sig.get("signals") or {}).items():
        if t.upper() in tick:
            signals.append({"t": t, "n": v.get("n_notable"), "sent": v.get("sentiment"), "sent4": v.get("sentiment_4w"),
                            "ar": _num(v.get("period_ar")), "analyst": _num(v.get("analyst_net")),
                            "stories": v.get("active_stories"), "vol": _num(v.get("volume_ratio")),
                            "flags": [f for f in v.get("flags") or []]})
    signals.sort(key=lambda x: -(x["n"] or 0))
    nd = _newest(AIF / "reports" / "news_*" / "*_news_digest_build_args.json")
    dg = _load(nd) if nd else {}
    digest = None
    if dg:
        digest = {"date": Path(nd).name[5:15], "headline": _clean(dg.get("headline")), "summary": _clean(dg.get("summary")),
                  "market": _clean(dg.get("market_context")), "analysts": _clean(dg.get("analyst_commentary")),
                  "notes": [{"t": str(x.get("ticker", "")).upper(), "note": _clean(x.get("note")), "action": x.get("action")}
                            for x in dg.get("position_notes") or [] if str(x.get("ticker", "")).upper() in tick],
                  "covers": sorted({str(x.get("ticker", "")).upper() for x in dg.get("position_notes") or []} & tick)}
    week = [x for x in items if x["date"][:10] >= (date.today() - timedelta(days=7)).isoformat()]
    keep = [x for x in items if x["mat"] >= 2][:220] + [x for x in items if x["mat"] < 2][:60]
    keep.sort(key=lambda x: (x["date"], x["mat"]), reverse=True)
    return {"date": sig.get("date"), "tickers": sorted(tick), "items": keep, "stories": stories,
            "themes": themes, "signals": signals, "digest": digest,
            "kpi": {"week": len(week), "notable": sum(1 for x in week if x["mat"] >= 2),
                    "pos": sum(1 for x in week if x["dir"] == "positive" and x["mat"] >= 2),
                    "neg": sum(1 for x in week if x["dir"] == "negative" and x["mat"] >= 2),
                    "stories": len(stories), "escalating": sum(1 for x in stories if x.get("status") == "escalating")}}


# ------------------------------------------------------------------ Brief-Seite
def _act_status(t, triggers):
    try:
        from .action_state import status
        st_ = status(t, triggers)
        return {"state": st_["state"], "date": st_.get("date"), "note": st_.get("note", "")} if st_ else None
    except Exception:
        return None


def brief_payload(news_days=7):
    """Weekly Brief mit allen neuen Meldungen je Position; Texte mit Faktencheck-Markierung (Quelle im Tooltip)."""
    bj = _newest(RESEARCH / "briefs" / "brief_*.json")
    if not bj:
        return None
    data = _load(bj) or {}
    ba, texts = _brief_texts(bj)
    fc = {}
    if ba:
        base = str(ba)[: -len("_build_args.json")]
        for suf in ("_factcheck_recheck.json", "_factcheck.json"):
            if Path(base + suf).exists():
                fc = _load(base + suf) or {}
                break
    try:
        from .html_site import _claims_index, highlight
        bk, bt = _claims_index(fc)
        hl = lambda x: highlight(x, bk, bt) if x else ""
    except Exception:
        from html import escape
        hl = lambda x: f"<p>{escape(str(x))}</p>" if x else ""
    tickers = [p["ticker"].upper() for p in data.get("positions") or []]
    try:
        nw = news_payload(tickers, days=max(news_days, 7))
    except Exception:
        nw = {"items": [], "stories": [], "kpi": {}}
    since = (date.today() - timedelta(days=news_days)).isoformat()
    news_by = {}
    for x in nw.get("items") or []:
        if x["mat"] >= 2 and x["date"][:10] >= since:
            news_by.setdefault(x["t"], []).append(x)
    stories_by = {}
    for s in nw.get("stories") or []:
        stories_by.setdefault(s["t"].upper(), []).append(s)
    items = {str(x.get("ticker", "")).upper(): x for x in (texts or {}).get("items") or []}
    q = (_load(QUOTES) or {}).get("data", {})
    pos = []
    for p in data.get("positions") or []:
        t = p["ticker"].upper()
        it = items.get(t, {})
        pos.append({"t": t, "name": p.get("name"), "level": p.get("level", "none"), "w": _num(p.get("weight")),
                    "rc": _num(p.get("risk_contrib")), "chg": _num((q.get(t) or {}).get("chg")),
                    "what": hl(_clean(it.get("what"))), "why": hl(_clean(it.get("why"))), "next": hl(_clean(it.get("next_step"))),
                    "triggers": [{"level": x.get("level"), "text": x.get("text"), "source": x.get("source")} for x in p.get("triggers") or []],
                    "theses": [{"thesis": x.get("thesis"), "status": x.get("status")} for x in p.get("theses") or []],
                    "news": news_by.get(t, [])[:6], "n_news": len(news_by.get(t, [])),
                    "stories": [s for s in stories_by.get(t, []) if s.get("status") in ("escalating", "developing", "new")][:4],
                    "next_earnings": p.get("next_earnings"),
                    "act": _act_status(t, p.get("triggers")) if p.get("level") in ("decide", "read") else None})
    order = {"decide": 0, "read": 1, "none": 2}
    pos.sort(key=lambda x: (order.get(x["level"], 3), -(x["w"] or 0)))
    orig = fc.get("original") or {}
    return {"date": data.get("date"), "headline": hl(_clean((texts or {}).get("headline"))),
            "summary": hl(_clean((texts or {}).get("summary"))),
            "no_action": hl(_clean((texts or {}).get("no_action_note"))), "portfolio_note": hl(_clean((texts or {}).get("portfolio_note"))),
            "portfolio": [{"level": x.get("level"), "text": x.get("text")} for x in data.get("portfolio") or []],
            "gaps": data.get("gaps") or [], "positions": pos, "news_days": news_days,
            "kpi": {"decide": sum(1 for x in pos if x["level"] == "decide"), "read": sum(1 for x in pos if x["level"] == "read"),
                    "none": sum(1 for x in pos if x["level"] == "none"), "news": sum(len(v) for v in news_by.values()),
                    "fc_m": fc.get("matched"), "fc_t": fc.get("total_claims"), "fc_orig_m": orig.get("matched"),
                    "fc_orig_t": orig.get("total_claims")},
            "sources": {"snapshot": data.get("snapshot_date"), "news": data.get("news_date"), "digest": data.get("digest_date")}}
