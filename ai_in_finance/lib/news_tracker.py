"""
News-Tracker (eigene Erweiterung): sammelt News zu den Depotwerten, ordnet sie den Investment-Thesen zu und misst die
Marktreaktion. Woechentlicher Digest als PDF.

Arbeitsteilung wie bei den anderen Agenten:
1. Sammeln (Python): Finnhub (US), Yahoo Finance (auch Europa), SEC EDGAR 8-K (US, offizielle Meldungen),
   Google-News-RSS (deutsch + englisch). Dubletten raus, Relevanzfilter per Regel, Speicher news/news_store.jsonl
   (jede Meldung wird nur einmal klassifiziert).
2. Klassifizieren (guenstiges Modell, gebuendelt, JSON): Kategorie, Richtung, Wesentlichkeit, betroffene These.
3. Marktreaktion (Python): Ueberrendite ggue. MSCI ACWI am Tag 0 und Tag 0..+1 (EUR), Volumen ggue. 20-Tage-Median.
4. Digest (Agent): Thesen-Alarme, Notizen je Position, Handlungsbedarf (pruefen / kein Handlungsbedarf), Faktencheck.
Nur fuer Lehrzwecke, keine Anlageberatung.
"""
import csv
import hashlib
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from textwrap import dedent
from typing import Annotated, List
from urllib.parse import quote_plus
from xml.sax.saxutils import escape

import numpy as np
import pandas as pd

from . import portfolio_engine as pe
from .style import STYLE_RULES
from . import agent_settings as _AS  # Prompts/Parameter aus der App (research/agent_settings.json)

AIF = __import__("pathlib").Path(__file__).resolve().parents[1]
NEWS_DIR = AIF / "news"
STORE = NEWS_DIR / "news_store.jsonl"
WATCHLIST = AIF / "portfolios" / "watchlist.csv"
PROMPT_VERSION = "v3"
CATEGORIES = ["earnings", "guidance", "m&a", "management", "legal/regulatory", "product/business", "analyst rating",
              "capital markets", "macro/sector", "other"]
ITEMS_8K = {"1.01": "material agreement", "1.02": "termination of agreement", "2.01": "acquisition or disposal",
            "2.02": "results of operations", "2.05": "restructuring costs", "2.06": "impairment",
            "3.01": "delisting notice", "4.02": "non-reliance on financials", "5.02": "management change",
            "5.07": "shareholder vote", "7.01": "Regulation FD disclosure", "8.01": "other events"}
_ROUNDS = {}
ETF_WORDS = ("etf", "ucits", "ishares", "vanguard", "xtrackers", "amundi", "spdr", "lyxor", "msci", "s&p 500",
             "ftse", "stoxx", "wisdomtree", "etn", "core", "physical")
GENERIC = {"com", "inc", "corp", "corporation", "plc", "ag", "se", "sa", "nv", "ltd", "limited", "group", "holding", "holdings",
           "class", "the", "co", "company", "registered", "shares", "adr", "a", "b", "c", "and", "&", "de", "of"}


# =============================================================== Watchlist
def _clean_name(name):
    words = re.sub(r"[^\w&\- ]", " ", str(name or "")).split()
    keep = [w for w in words if w.lower() not in GENERIC]
    return " ".join(keep[:3]) or str(name or "")


def _is_fund(name, ticker):
    n = f" {str(name).lower()} "
    return any(f" {w} " in n or n.strip().startswith(w) for w in ETF_WORDS)


def build_watchlist(transaction_files=None, tickers=None, path=WATCHLIST, overwrite=False, holdings_files=None):
    """Watchlist aus den aktuellen Bestaenden der Transaktions-Exporte (oder einer Tickerliste) als CSV.
    Spalten: ticker,name,query,track (yes/no). Die Datei kann man von Hand anpassen (Suchbegriff, Titel ausschliessen)."""
    rows = []
    if transaction_files:
        from . import transactions as tr
        tx, _ = tr.read_all([str(f) for f in transaction_files])
        tx, _ = tr.attach_tickers(tx)
        sign = {"buy": 1, "transfer_in": 1, "deliver_in": 1, "sell": -1, "transfer_out": -1, "deliver_out": -1}
        tx = tx[tx["type"].isin(list(sign)) & (tx["ticker"] != "")]
        net = (tx["type"].map(sign) * tx["shares"]).groupby(tx["ticker"]).sum()
        names = tx.groupby("ticker")["name"].last()
        for t in sorted(net[net > 1e-6].index):
            nm = str(names.get(t) or t)
            rows.append({"ticker": t, "name": nm, "query": _clean_name(nm), "track": "no" if _is_fund(nm, t) else "yes"})
    if holdings_files:
        from . import transactions as tr
        have = {r["ticker"] for r in rows}
        for h in tr.read_all_holdings([str(f) for f in holdings_files])[0]:
            if h["ticker"] not in have:
                have.add(h["ticker"])
                rows.append({"ticker": h["ticker"], "name": h["name"] or h["ticker"], "query": _clean_name(h["name"] or h["ticker"]),
                             "track": "no" if _is_fund(h["name"] or "", h["ticker"]) else "yes"})
    for t in tickers or []:
        rows.append({"ticker": t.upper(), "name": t.upper(), "query": t.upper(), "track": "yes"})
    path = __import__("pathlib").Path(path)
    if path.exists() and not overwrite:
        old = {r["ticker"]: r for r in load_watchlist(path, only_tracked=False)}
        rows = [old.get(r["ticker"], r) for r in rows] + [r for t, r in old.items() if t not in {x["ticker"] for x in rows}]
    for r in rows:                                           # Suchbegriff unbrauchbar (ISIN, zu kurz) -> Yahoo-Name
        q = str(r.get("query") or "")
        if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", q) or len(q) < 3:
            better = _yahoo_name(r["ticker"]) or r["name"]
            r["query"] = _clean_name(better) if len(_clean_name(better)) >= 3 else better
            if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", str(r["name"])):
                r["name"] = better
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["ticker", "name", "query", "track"])
        w.writeheader()
        w.writerows(rows)
    return rows


def _yahoo_name(ticker):
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        return info.get("shortName") or info.get("longName")
    except Exception:
        return None


def load_watchlist(path=WATCHLIST, only_tracked=True):
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    return [r for r in rows if not only_tracked or str(r.get("track", "yes")).lower() != "no"]


def watchlist_from_tickers(tickers, path=WATCHLIST):
    """Watchlist-Eintraege fuer eine feste Tickerliste (z. B. Musterportfolio); Suchbegriff aus der Watchlist-Datei
    oder dem Yahoo-Namen."""
    wl = {w["ticker"]: w for w in load_watchlist(path, only_tracked=False)} if __import__("pathlib").Path(path).exists() else {}
    out = []
    for t in tickers:
        t = t.upper()
        if t in wl:
            out.append(wl[t])
            continue
        nm = _yahoo_name(t) or t
        q = _clean_name(nm)
        out.append({"ticker": t, "name": nm, "query": q if len(q) >= 3 else nm, "track": "yes"})
    return out


def top_watchlist(transaction_files, n=5, path=WATCHLIST, holdings_files=None):
    """Die n groessten offenen Positionen nach aktuellem Marktwert (Kurse von Yahoo, Splits beruecksichtigt),
    mit Suchbegriffen aus der Watchlist-Datei. holdings_files: Positions-Exporte ohne Kaufhistorie (Marktwert laut
    Export, bei gleichem Ticker addiert)."""
    pos = {}
    if transaction_files:
        from .portfolio_manager import load_performance
        perf, _, _ = load_performance([str(f) for f in transaction_files])
        for p in perf["positions"]:
            if p.get("open") and p["ticker"] != "Unpriced instruments":
                pos[p["ticker"]] = dict(p)
    if holdings_files:
        from . import transactions as tr
        for h in tr.read_all_holdings([str(f) for f in holdings_files])[0]:
            e = pos.setdefault(h["ticker"], {"ticker": h["ticker"], "name": h["name"], "market_value": 0.0, "open": True})
            e["market_value"] += h["value"] or 0.0
    ranked = sorted(pos.values(), key=lambda p: -p["market_value"])
    wl = {w["ticker"]: w for w in load_watchlist(path, only_tracked=False)} if __import__("pathlib").Path(path).exists() else {}
    out, top = [], []
    for p in ranked:                                         # ETFs / track=no ueberspringen
        w = wl.get(p["ticker"]) or {"ticker": p["ticker"], "name": p.get("name") or p["ticker"],
                                     "query": _clean_name(p.get("name") or p["ticker"]),
                                     "track": "no" if _is_fund(p.get("name") or "", p["ticker"]) else "yes"}
        if str(w.get("track", "yes")).lower() == "no":
            continue
        out.append(w)
        top.append(p)
        if len(out) >= n:
            break
    print("Groesste Positionen:", ", ".join(f"{p['ticker']} (EUR {p['market_value']:,.0f})" for p in top))
    return out


def _us_symbol(t):
    return t if re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", t) and not t.endswith("-EUR") else None


# =============================================================== Sammeln
def _id(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def _norm_title(t):
    t = re.sub(r"\s+-\s+[^-]{2,40}$", "", str(t or ""))          # Google: "Titel - Quelle"
    return re.sub(r"[^a-z0-9 ]", "", t.lower()).strip()


def fetch_finnhub(symbol, start, end):
    from .news_tools import _client
    out = []
    for n in _client().company_news(symbol, _from=start, to=end) or []:
        if not n.get("headline"):
            continue
        out.append({"date": datetime.fromtimestamp(n["datetime"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                    "source_type": "finnhub", "publisher": n.get("source", ""), "title": n["headline"],
                    "summary": n.get("summary", "") or "", "url": n.get("url", "")})
    return out


def fetch_yahoo(ticker):
    import yfinance as yf
    out = []
    for n in yf.Ticker(ticker).news or []:
        c = n.get("content", n)
        title = c.get("title")
        if not title:
            continue
        ts = c.get("pubDate") or c.get("displayTime")
        if not ts and n.get("providerPublishTime"):
            ts = datetime.fromtimestamp(n["providerPublishTime"], tz=timezone.utc).isoformat()
        try:
            d = pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%d %H:%M") if pd.Timestamp(ts).tzinfo else \
                pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            continue
        url = ((c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or n.get("link", ""))
        out.append({"date": d, "source_type": "yahoo", "publisher": (c.get("provider") or {}).get("displayName", "")
                    or n.get("publisher", ""), "title": title, "summary": c.get("summary") or c.get("description") or "",
                    "url": url})
    return out


def fetch_edgar_8k(symbol, start):
    import requests
    from finrobot.data_source.fmp_utils import _sec_headers, _ticker_to_cik
    cik = _ticker_to_cik().get(symbol.upper())
    if cik is None:
        return []
    rec = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=_sec_headers(), timeout=30).json()
    r = rec["filings"]["recent"]
    items = r.get("items") or [""] * len(r["form"])
    out = []
    for f, d, acc, it, doc in zip(r["form"], r["filingDate"], r["accessionNumber"], items, r["primaryDocument"]):
        if f not in ("8-K", "8-K/A") or d < start:
            continue
        codes = [c.strip() for c in str(it).split(",") if c.strip() and c.strip() != "9.01"]
        desc = "; ".join(f"Item {c} {ITEMS_8K.get(c, '')}".strip() for c in codes) or "8-K filing"
        out.append({"date": f"{d} 00:00", "source_type": "edgar", "publisher": "SEC EDGAR",
                    "title": f"{f}: {desc}", "summary": f"Form {f} filed with the SEC ({desc}).",
                    "url": f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{doc}"})
    return out


def fetch_google_rss(query, days=7, langs=(("de", "DE"), ("en", "US")), max_per_lang=20):
    import requests
    out = []
    for hl, gl in langs:
        url = (f"https://news.google.com/rss/search?q={quote_plus(chr(34) + query + chr(34) + f' when:{days}d')}"
               f"&hl={hl}&gl={gl}&ceid={gl}:{hl}")
        try:
            root = ET.fromstring(requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}).content)
        except Exception:
            continue
        got = []
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            try:
                d = pd.Timestamp(it.findtext("pubDate")).tz_convert("UTC").strftime("%Y-%m-%d %H:%M")
            except Exception:
                continue
            src = it.find("source")
            got.append({"date": d, "source_type": "google", "publisher": src.text if src is not None else "",
                        "title": title, "summary": "", "url": it.findtext("link") or "", "lang": hl})
        out += sorted(got, key=lambda x: x["date"], reverse=True)[:max_per_lang]
    return out


def _relevant(item, w):
    """Regelbasierter Filter: Ticker oder Firmenname muss vorkommen (8-Ks sind immer relevant)."""
    if item["source_type"] == "edgar":
        return True
    text = f" {item['title']} {item.get('summary', '')} ".lower()
    base = w["ticker"].split(".")[0].split("-")[0].lower()
    words = [x.lower() for x in re.findall(r"[\w&]+", w.get("query") or w["name"]) if x.lower() not in GENERIC and len(x) >= 3]
    if words and re.search(r"\b" + re.escape(words[0]) + r"\b", text):
        return True
    if re.search(r"\$" + re.escape(base) + r"\b", text):                # Cashtag, auch kurze Ticker ($NU)
        return True
    return len(base) >= 3 and re.search(r"\b" + re.escape(base) + r"\b", text) is not None


def _dedupe(items):
    out, seen = [], []
    for it in sorted(items, key=lambda x: (x["date"], {"edgar": 0, "finnhub": 1, "yahoo": 2, "google": 3}[x["source_type"]])):
        toks = set(_norm_title(it["title"]).split())
        if not toks:
            continue
        dup = False
        for s_ticker, s_toks in seen:
            if s_ticker == it["ticker"] and len(toks & s_toks) / max(len(toks | s_toks), 1) >= 0.7:
                dup = True
                break
        if not dup:
            seen.append((it["ticker"], toks))
            out.append(it)
    return out


SOURCE_PRIO = {"edgar": 0, "finnhub": 1, "yahoo": 1, "google": 2}


def select_items(items, per_ticker=30):
    """Hoechstens per_ticker Meldungen je Titel (jeweils die neuesten): alle 8-Ks, dann ca. 2/3 Finnhub/Yahoo und
    1/3 Google-News; freie Plaetze fuellt die jeweils andere Gruppe auf."""
    out = []
    for t in sorted({i["ticker"] for i in items}):
        sub = sorted([i for i in items if i["ticker"] == t], key=lambda x: x["date"], reverse=True)
        edgar = [i for i in sub if i["source_type"] == "edgar"][:per_ticker]
        api = [i for i in sub if i["source_type"] in ("finnhub", "yahoo")]
        goog = [i for i in sub if i["source_type"] == "google"]
        free = per_ticker - len(edgar)
        n_g = min(len(goog), max(free // 3, free - len(api)))
        n_a = min(len(api), free - n_g)
        n_g = min(len(goog), free - n_a)
        out += edgar + api[:n_a] + goog[:n_g]
    return out


def load_store():
    if not STORE.exists():
        return []
    return [json.loads(l) for l in open(STORE, encoding="utf-8") if l.strip()]


def save_store(items):
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    with open(STORE, "w", encoding="utf-8") as f:
        for it in sorted(items, key=lambda x: (x["ticker"], x["date"])):
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def collect(watchlist, days=7, use_google=True, fetchers=None, per_ticker=30, end=None):
    """Neue Meldungen aller Quellen sammeln, filtern, Dubletten entfernen und im Speicher ablegen.
    fetchers: optional eigene Funktionen (fuer Tests). Gibt (alle Meldungen im Zeitraum, Statistik) zurueck."""
    f = {"finnhub": fetch_finnhub, "yahoo": fetch_yahoo, "edgar": fetch_edgar_8k, "google": fetch_google_rss}
    f.update(fetchers or {})
    end = pd.Timestamp(end).date() if end is not None else date.today()
    start = (end - timedelta(days=days)).isoformat()
    recent = (date.today() - end).days <= 3          # Yahoo und Google liefern nur aktuelle Meldungen
    raw, errors, by_source = [], [], {}
    for w in watchlist:
        t, us = w["ticker"], _us_symbol(w["ticker"])
        jobs = [("yahoo", lambda: f["yahoo"](t))] if recent else []
        if us:
            jobs += [("finnhub", lambda: f["finnhub"](us, start, end.isoformat())), ("edgar", lambda: f["edgar"](us, start))]
        if use_google and recent:
            jobs.append(("google", lambda: f["google"](w.get("query") or w["name"], days)))
        for src, job in jobs:
            try:
                got = job()
            except Exception as e:
                errors.append(f"{t} {src}: {str(e)[:120]}")
                continue
            by_source[src] = by_source.get(src, 0) + len(got)
            for it in got:
                if it["date"][:10] < start or it["date"][:10] > end.isoformat():
                    continue
                it.update(ticker=t, name=w["name"])
                raw.append(it)
    relevant = [it for it in raw if _relevant(it, next(w for w in watchlist if w["ticker"] == it["ticker"]))]
    items = _dedupe(relevant)
    store = load_store()
    known = {s["id"] for s in store}
    for it in items:
        it["id"] = _id(it["ticker"], _norm_title(it["title"])[:90])
        it["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    items = select_items(items, per_ticker)
    new = [it for it in items if it["id"] not in known]
    store += new
    save_store(store)
    period = select_items([x for x in store if start <= x["date"][:10] <= end.isoformat()
                           and x["ticker"] in {w["ticker"] for w in watchlist}], per_ticker)
    stats = {"raw": len(raw), "relevant": len(relevant), "deduplicated": len(items), "new": len(new),
             "by_source": by_source, "errors": errors, "start": start, "end": end.isoformat(), "per_ticker": per_ticker}
    return period, stats


# =============================================================== Klassifizieren (guenstiges Modell, gebuendelt)
def _theses(ticker):
    """Thesen aus dem letzten Annual Report des Agenten (falls vorhanden) und letzter Status aus dem Thesen-Protokoll."""
    from .quarterly_data import annual_baseline, load_thesis_log
    sym = ticker.split(".")[0]
    b = annual_baseline(sym)
    if b.get("error"):
        return []
    out = [{"thesis": str(t.get("thesis", ""))[:220], "signpost": str(t.get("signpost", ""))[:160],
            "invalidation": str(t.get("invalidation", ""))[:160]} for t in b.get("theses") or []]
    log = load_thesis_log(sym)
    if log:
        last = log[-1]
        for i, s in enumerate(last.get("theses", [])):
            if i < len(out):
                out[i]["status"] = s.get("current_status") or s.get("status", "")
    return out


CLASSIFY_SYSTEM = dedent(f"""
    You classify news about listed companies for an equity analyst. Be strict: routine noise (price moves without news,
    listicles, generic market commentary, ads) is materiality 1 and usually relevant=false. Return ONLY a JSON array,
    one object per input item, with keys: id, relevant (true/false: is it really about this company?), category (one of
    {', '.join(CATEGORIES)}), direction (positive / negative / neutral for the company's fundamentals or valuation),
    materiality (1 = noise: opinion pieces, stock-price recaps, listicles, repeated or recycled stories, generic
    commentary; 2 = NEW company-specific information such as results, guidance, orders/contracts, product or
    regulatory decisions, management changes, rating changes by named banks; 3 = could change the investment case),
    thesis (index of the affected
    investment thesis from the list, or null), thesis_effect (supports / challenges / none), reason (max. 20 words,
    facts from the item only). Use category "analyst rating" for rating or price-target actions by banks/brokers/research
    firms and then add key analyst = {{firm, action (upgrade / downgrade / initiate / reiterate / target raise /
    target cut), rating (e.g. Buy, Overweight), price_target (number or null), prior_target (number or null),
    currency (or null)}}. Do not use knowledge beyond the item text.
""").strip()


def _parse_json_array(text):
    text = re.sub(r"^```(json)?|```$", "", str(text).strip(), flags=re.M).strip()
    s, e = text.find("["), text.rfind("]")
    if s < 0 or e < 0:
        return []
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return []


def _store_classification(s, r, n_th, model):
    th_i = r.get("thesis") if isinstance(r.get("thesis"), int) and 0 <= r["thesis"] < n_th.get(s["ticker"], 0) else None
    cat = str(r.get("category", "other")).lower()
    d = str(r.get("direction", "neutral")).lower()
    mat = str(r.get("materiality", "1")).strip()
    s.update(relevant=bool(r.get("relevant", True)), category=cat if cat in CATEGORIES else "other",
             direction=d if d in ("positive", "negative", "neutral") else "neutral",
             materiality=min(max(int(mat), 1), 3) if mat.isdigit() else 1, thesis=th_i,
             thesis_effect=str(r.get("thesis_effect", "none")).lower() if th_i is not None else "none",
             reason=str(r.get("reason", ""))[:200], classified_by=model, prompt_version=PROMPT_VERSION)
    an = r.get("analyst")
    if s["category"] == "analyst rating" and isinstance(an, dict):
        def num(v):
            try:
                return float(str(v).replace(",", "."))
            except (TypeError, ValueError):
                return None
        s["analyst"] = {"firm": str(an.get("firm") or "")[:60], "action": str(an.get("action") or "").lower()[:20],
                        "rating": str(an.get("rating") or "")[:30], "price_target": num(an.get("price_target")),
                        "prior_target": num(an.get("prior_target")), "currency": str(an.get("currency") or "")[:5]}
    else:
        s.pop("analyst", None)


def classify(items, llm_config, batch=25, client=None, workers=4):
    """Klassifiziert die ausgewaehlten, noch nicht (oder mit aelterer Prompt-Version) klassifizierten Meldungen: gebuendelt je Titel, mehrere Aufrufe
    parallel, Fortschritt sichtbar, Zwischenstand nach jedem Buendel gespeichert (Abbruch verliert nichts)."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import autogen
    store = load_store()
    by_id = {s["id"]: s for s in store}
    todo = [by_id[i["id"]] for i in items if i["id"] in by_id and
            ("category" not in by_id[i["id"]] or by_id[i["id"]].get("prompt_version") != PROMPT_VERSION)]
    if not todo:
        return 0, 0
    if client is None:
        cfg = {k: v for k, v in llm_config.items() if k not in ("parallel_tool_calls", "tools", "functions")}
        cfg["temperature"] = 0
        client = autogen.OpenAIWrapper(**cfg)
    model = (llm_config.get("config_list") or [{}])[0].get("model", "")
    jobs, n_th = [], {}
    for t in sorted({s["ticker"] for s in todo}):
        group = [s for s in todo if s["ticker"] == t]
        theses = _theses(t)
        n_th[t] = len(theses)
        th_txt = "\n".join(f"[{i}] {x['thesis']} (signpost: {x['signpost']}; invalidation: {x['invalidation']})"
                           for i, x in enumerate(theses)) or "(no investment theses on file)"
        for k in range(0, len(group), batch):
            chunk = group[k:k + batch]
            lines = [f"id={s['id']} | {s['date'][:10]} | {s['source_type']}/{s.get('publisher', '')} | {s['title']}"
                     + (f" | {' '.join(str(s.get('summary', '')).split())[:300]}" if s.get("summary") else "")
                     for s in chunk]
            jobs.append(f"Company: {group[0].get('name')} ({t})\nInvestment theses:\n{th_txt}\n\nNews items:\n" +
                        "\n".join(lines))
    print(f"Klassifiziere {len(todo)} Meldungen in {len(jobs)} Buendeln ({workers} parallel) ...")
    lock, done, failed = threading.Lock(), [0], []

    def run(msg):
        resp = client.create(messages=[{"role": "system", "content": _AS.get("news.classify", CLASSIFY_SYSTEM)},
                                       {"role": "user", "content": msg}], cache=None)
        return _parse_json_array((client.extract_text_or_completion_object(resp) or [""])[0] or "")

    n_ok = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(run, m) for m in jobs]
        for f in as_completed(futs):
            try:
                res = f.result()
            except Exception as e:
                failed.append(str(e)[:120])
                res = []
            with lock:
                for r in res:
                    s = by_id.get(str(r.get("id"))) if isinstance(r, dict) else None
                    if s is not None:
                        _store_classification(s, r, n_th, model)
                        n_ok += 1
                done[0] += 1
                save_store(store)
                print(f"  {done[0]}/{len(jobs)} Buendel fertig", end="\r")
    print(f"\n{n_ok} von {len(todo)} klassifiziert" + (f"; {len(failed)} Buendel fehlgeschlagen: {failed[0]}" if failed else ""))
    return n_ok, len(jobs)


# =============================================================== Analystenaktionen (getrennt von den News)
_UD_ACTION = {"up": "upgrade", "down": "downgrade", "init": "initiate", "main": "reiterate", "reit": "reiterate"}


def fetch_analyst_actions(ticker, since):
    """Rating- und Kurszielaenderungen (Yahoo upgradeDowngradeHistory) seit 'since' plus Konsens-Kursziel."""
    import yfinance as yf
    tk = yf.Ticker(ticker)
    out = []
    try:
        ud = tk.upgrades_downgrades
    except Exception:
        ud = None
    if ud is not None and len(ud):
        for d, r in ud[ud.index >= pd.Timestamp(since)].iterrows():
            cur, pri = r.get("currentPriceTarget"), r.get("priorPriceTarget")
            act = _UD_ACTION.get(str(r.get("Action", "")).lower(), str(r.get("Action", "")).lower())
            pta = str(r.get("priceTargetAction") or "").lower()
            if act == "reiterate" and pta.startswith("raise"):
                act = "target raise"
            elif act == "reiterate" and pta.startswith("lower"):
                act = "target cut"
            out.append({"ticker": ticker, "date": str(pd.Timestamp(d).date()), "firm": str(r.get("Firm", "")),
                        "action": act, "rating": str(r.get("ToGrade", "")), "from_rating": str(r.get("FromGrade", "")),
                        "price_target": float(cur) if cur and cur == cur and float(cur) > 0 else None,
                        "prior_target": float(pri) if pri and pri == pri and float(pri) > 0 else None,
                        "source": "yahoo"})
    cons = {}
    try:
        pt = tk.analyst_price_targets or {}
        cur = pt.get("current")
        cons = {"current_price": cur, "mean": pt.get("mean"), "median": pt.get("median"), "high": pt.get("high"),
                "low": pt.get("low"), "upside": (pt["mean"] / cur - 1) if pt.get("mean") and cur else None}
    except Exception:
        pass
    return out, cons


def analyst_summary(items, watchlist, days=7, momentum_days=90, fetch=None):
    """Analystenaktionen der Periode (Yahoo strukturiert + aus News extrahiert, ohne Doppelte) und 90-Tage-Momentum."""
    fetch = fetch or fetch_analyst_actions
    end = pd.Timestamp(date.today())
    start, mstart = end - pd.Timedelta(days=days), end - pd.Timedelta(days=momentum_days)
    res = {"actions": [], "momentum": {}, "consensus": {}, "errors": []}
    hist = []
    for w in watchlist:
        t = w["ticker"]
        if t.endswith("-EUR"):
            continue
        try:
            acts, cons = fetch(t, mstart.date().isoformat())
        except Exception as e:
            res["errors"].append(f"{t} analyst data: {str(e)[:100]}")
            acts, cons = [], {}
        res["consensus"][t] = cons
        hist += acts
    from_news = []
    for s in items:
        a = s.get("analyst")
        if s.get("category") == "analyst rating" and s.get("relevant", True) and a and a.get("firm"):
            from_news.append({"ticker": s["ticker"], "date": s["date"][:10], "firm": a["firm"], "action": a["action"],
                              "rating": a["rating"], "from_rating": "", "price_target": a.get("price_target"),
                              "prior_target": a.get("prior_target"), "source": f"news/{s.get('publisher', '')}"[:40],
                              "title": s["title"], "url": s.get("url", "")})

    def same(x, y):
        fx, fy = re.sub(r"[^a-z]", "", x["firm"].lower())[:6], re.sub(r"[^a-z]", "", y["firm"].lower())[:6]
        return x["ticker"] == y["ticker"] and fx and fx == fy and \
            abs((pd.Timestamp(x["date"]) - pd.Timestamp(y["date"])).days) <= 3
    period = [h for h in hist if h["date"] >= start.date().isoformat()]
    period += [n for n in from_news if not any(same(n, h) for h in period)]
    for a in period:
        cp = (res["consensus"].get(a["ticker"]) or {}).get("current_price")
        a["pt_change"] = (a["price_target"] / a["prior_target"] - 1) if a.get("price_target") and a.get("prior_target") else None
        a["upside"] = (a["price_target"] / cp - 1) if a.get("price_target") and cp else None
        if a["upside"] is not None and not -0.8 < a["upside"] < 1.5:
            a["upside"] = None                    # vermutlich andere Waehrung/Boerse als der Kurs -> nicht ausweisen
    res["actions"] = sorted(period, key=lambda x: (x["ticker"], x["date"]))
    for w in watchlist:
        sub = [h for h in hist if h["ticker"] == w["ticker"]]
        if not sub:
            continue
        chg = [h["price_target"] / h["prior_target"] - 1 for h in sub if h.get("price_target") and h.get("prior_target")]
        res["momentum"][w["ticker"]] = {
            "n": len(sub), "upgrades": sum(h["action"] == "upgrade" for h in sub),
            "downgrades": sum(h["action"] == "downgrade" for h in sub),
            "pt_raises": sum(1 for c in chg if c > 0.001), "pt_cuts": sum(1 for c in chg if c < -0.001),
            "avg_pt_change": float(np.mean(chg)) if chg else None}
    # Verlauf speichern (fuer spaetere Trend-Auswertung)
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    astore = NEWS_DIR / "analyst_actions.jsonl"
    old = [json.loads(l) for l in open(astore, encoding="utf-8")] if astore.exists() else []
    keys = {(o["ticker"], o["date"], o["firm"], o["action"]) for o in old}
    with open(astore, "a", encoding="utf-8") as f:
        for h in hist + from_news:
            k = (h["ticker"], h["date"], h["firm"], h["action"])
            if k not in keys:
                keys.add(k)
                f.write(json.dumps({k_: v for k_, v in h.items() if k_ not in ("title", "url")}, ensure_ascii=False) + "\n")
    return res


def analyst_text(an):
    P = _pp
    if not an or not (an["actions"] or an["momentum"]):
        return "ANALYST ACTIONS: none found for the period."
    lines = ["ANALYST ACTIONS of the period (rating and price-target changes; Yahoo Finance and news; cite as [1]):"]
    for a in an["actions"]:
        pt = ""
        if a.get("price_target"):
            pt = f", target {a['price_target']:,.2f}" + (f" (from {a['prior_target']:,.2f}, {P(a['pt_change'])})"
                                                           if a.get("prior_target") else "")
            pt += f", implied upside {P(a['upside'])}" if a.get("upside") is not None else ""
        rating = f"{a['from_rating']} -> {a['rating']}" if a.get("from_rating") and a["from_rating"] != a["rating"] else a["rating"]
        lines.append(f"- {a['date']} {a['ticker']}: {a['firm']} {a['action']}" + (f" ({rating})" if rating else "") + pt +
                     f" [{a['source']}]")
    lines.append("ANALYST MOMENTUM last 90 days (Yahoo Finance) and consensus price target:")
    for t, m in an["momentum"].items():
        c = an["consensus"].get(t) or {}
        lines.append(f"- {t}: {m['n']} actions, upgrades {m['upgrades']}, downgrades {m['downgrades']}, target raises "
                     f"{m['pt_raises']}, target cuts {m['pt_cuts']}, average target change {P(m['avg_pt_change'])}"
                     + (f"; consensus mean target {c['mean']:,.2f} vs price {c['current_price']:,.2f} (upside "
                        f"{P(c['upside'])})" if c.get("mean") and c.get("current_price") else ""))
    return "\n".join(lines)


# =============================================================== Marktreaktion (Ereignisstudie)
def market_reaction(items, prices=None, volumes=None):
    """Ueberrendite ggue. MSCI ACWI (EUR): Tag 0 = erster Handelstag ab Meldungsdatum, CAR = Tag 0 und +1;
    Volumen Tag 0 ggue. Median der 20 Handelstage davor. Ergebnis wird im Speicher abgelegt."""
    tickers = sorted({i["ticker"] for i in items})
    if not tickers:
        return prices
    bench = pe.BENCHMARKS["MSCI ACWI"]
    traded = None                                    # echte Handelstage je Titel (ohne fortgeschriebene Kurse)
    if prices is None:
        prices, _ = pe.download_prices(tickers + [bench], years=1)
        import yfinance as yf
        try:
            raw = yf.download(tickers, period="1y", auto_adjust=True, progress=False)
            close, vol = raw["Close"], raw["Volume"]
            if isinstance(close, pd.Series):
                close, vol = close.to_frame(tickers[0]), vol.to_frame(tickers[0])
            traded = close.notna()
            volumes = vol if volumes is None else volumes
        except Exception:
            traded = None
    ret = prices.pct_change()
    store = load_store()
    ids = {i["id"] for i in items}
    for s in store:
        if s["id"] not in ids or s["ticker"] not in ret:
            continue
        d = pd.Timestamp(s["date"][:10])
        idx = ret[s["ticker"]].dropna().index
        if traded is not None and s["ticker"] in traded:
            idx = idx.intersection(traded.index[traded[s["ticker"]]])
        pos = idx.searchsorted(d)
        if pos >= len(idx):
            s.update(ar0=None, car01=None, vol_ratio=None, reaction_note="no trading day yet")
            continue
        d0 = idx[pos]
        ar0 = float(ret.at[d0, s["ticker"]] - ret[bench].get(d0, np.nan))
        car = ar0
        if pos + 1 < len(idx):
            d1 = idx[pos + 1]
            car += float(ret.at[d1, s["ticker"]] - ret[bench].get(d1, np.nan))
            note = ""
        else:
            note = "day +1 not yet available"
        vr = None
        if volumes is not None and s["ticker"] in getattr(volumes, "columns", []):
            v = volumes[s["ticker"]].dropna()
            vpos = v.index.searchsorted(d0)
            if 20 <= vpos < len(v) and v.iloc[vpos - 20:vpos].median() > 0:
                vr = float(v.iloc[vpos] / v.iloc[vpos - 20:vpos].median())
        drift = {}
        for k in (5, 20):                         # Nachlauf: kumulierte Ueberrendite Tag 0..+k (fuer die Evaluation)
            if pos + k < len(idx):
                seg = idx[pos:pos + k + 1]
                v = float((ret.loc[seg, s["ticker"]] - ret.loc[seg, bench]).sum())
                drift[f"car0{k}"] = v if v == v else None
        s.update(ar0=ar0 if ar0 == ar0 else None, car01=car if car == car else None, vol_ratio=vr,
                 reaction_day=str(d0.date()), reaction_note=note, **drift)
    save_store(store)
    return prices


def _agree(s, thr=0.01):
    """Stimmt die Richtung der Klassifizierung mit dem Vorzeichen der Ueberrendite ueberein?"""
    car, d = s.get("car01"), s.get("direction")
    if car is None or d not in ("positive", "negative"):
        return None
    if abs(car) < thr:
        return "no reaction"
    return "agrees" if (car > 0) == (d == "positive") else "disagrees"


# =============================================================== Stories (Meldungen zu Geschichten buendeln)
STORY_SYSTEM = dedent("""
    You maintain a story log for an equity analyst. A story is one developing situation of a company (e.g. a regulatory
    probe, a product delay, a guidance change), not a single article. You get the company's open stories and this
    period's notable news items. Return ONLY a JSON array of objects: {story (id of an open story, or "new"), title
    (only for new stories, max. 8 words, neutral), item_ids (list), update (max. 30 words: what is new this period,
    facts from the items only), status (new / escalating / ongoing / calming / resolved), direction (positive /
    negative / mixed for the company)}. Group items about the same situation together; put unrelated one-off items
    into their own new story only if they are material, otherwise leave them out.
""").strip()


def _stories_path():
    return NEWS_DIR / "stories.json"


def load_stories():
    p = _stories_path()
    return json.load(open(p, encoding="utf-8")) if p.exists() else []


def save_stories(st):
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    json.dump(st, open(_stories_path(), "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def track_stories(items, llm_config, client=None, workers=4, period_end=None, quiet_weeks=4):
    """Ordnet die wesentlichen News der Periode bestehenden Stories zu oder eroeffnet neue (ein Aufruf je Position).
    Stories ohne neue Meldung seit quiet_weeks Wochen werden als 'quiet' markiert."""
    from concurrent.futures import ThreadPoolExecutor
    import autogen
    stories = load_stories()
    period_end = str(period_end or date.today())
    mat = [s for s in items if _is_news(s) and s.get("materiality", 1) >= 2 and not s.get("story")]
    if not mat:
        return stories
    if client is None:
        cfg = {k: v for k, v in llm_config.items() if k not in ("parallel_tool_calls", "tools", "functions")}
        cfg["temperature"] = 0
        client = autogen.OpenAIWrapper(**cfg)
    jobs = []
    for t in sorted({s["ticker"] for s in mat}):
        open_ = [x for x in stories if x["ticker"] == t and x["status"] not in ("resolved", "quiet")]
        sub = [s for s in mat if s["ticker"] == t]
        msg = (f"Company: {sub[0].get('name')} ({t})\nOpen stories:\n" +
               ("\n".join(f"- id={x['id']} | {x['title']} | since {x['first_seen']} | last: {x['timeline'][-1]['update']}"
                          for x in open_) or "(none)") + "\n\nNotable news items this period:\n" +
               "\n".join(f"id={s['id']} | {s['date'][:10]} | {s['title']} | {s.get('category')}, {s.get('direction')}, "
                         f"materiality {s.get('materiality')}" for s in sub))
        jobs.append((t, msg, {x["id"] for x in open_}, {s["id"] for s in sub}))

    def run(job):
        resp = client.create(messages=[{"role": "system", "content": _AS.get("news.story", STORY_SYSTEM)}, {"role": "user", "content": job[1]}],
                             cache=None)
        return job, _parse_json_array((client.extract_text_or_completion_object(resp) or [""])[0] or "")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda j: _safe(run, j), jobs))
    store = load_store()
    by_id = {x["id"]: x for x in store}
    for res in results:
        if not res:
            continue
        (t, _, open_ids, item_ids), out = res
        for r in out:
            if not isinstance(r, dict):
                continue
            ids = [i for i in (r.get("item_ids") or []) if i in item_ids]
            if not ids:
                continue
            dates = sorted(by_id[i]["date"][:10] for i in ids if i in by_id)
            entry = {"date": dates[-1] if dates else period_end, "item_ids": ids, "update": str(r.get("update", ""))[:250],
                     "status": str(r.get("status", "ongoing")).lower(), "direction": str(r.get("direction", "mixed")).lower()}
            sid = str(r.get("story"))
            st = next((x for x in stories if x["id"] == sid), None) if sid in open_ids else None
            if st is None:
                st = {"id": _id(t, r.get("title", ""), period_end), "ticker": t, "title": str(r.get("title") or "Untitled")[:80],
                      "first_seen": dates[0] if dates else period_end, "timeline": []}
                stories.append(st)
                entry["status"] = "new" if entry["status"] in ("ongoing", "escalating", "calming") else entry["status"]
            st["timeline"].append(entry)
            st["status"], st["direction"], st["last_update"] = entry["status"], entry["direction"], entry["date"]
            for i in ids:
                if i in by_id:
                    by_id[i]["story"] = st["id"]
    cutoff = (pd.Timestamp(period_end) - pd.Timedelta(weeks=quiet_weeks)).date().isoformat()
    for st in stories:
        if st["status"] not in ("resolved", "quiet") and st.get("last_update", st["first_seen"]) < cutoff:
            st["status"] = "quiet"
    save_store(store)
    save_stories(stories)
    return stories


def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        print(f"  Aufruf fehlgeschlagen: {str(e)[:120]}")
        return None


THEME_SYSTEM = dedent("""
    You look for themes that affect SEVERAL positions of a portfolio at once (e.g. AI capex, China export controls,
    interest rates, a regulatory push). Input: this period's stories by position. Return ONLY a JSON array of
    {theme (max. 6 words), tickers (list, at least two), story_ids (list), explanation (max. 40 words, facts from the
    stories only), risk (concentration / opportunity / mixed)}. Return [] if there is no genuine common theme.
""").strip()


def portfolio_themes(stories, period_start, llm_config, client=None):
    """Querschnittsthemen ueber mehrere Positionen (ein Aufruf) aus den Stories der Periode."""
    import autogen
    cur = [x for x in stories if x.get("last_update", "") >= period_start]
    if len({x["ticker"] for x in cur}) < 2:
        return []
    if client is None:
        cfg = {k: v for k, v in llm_config.items() if k not in ("parallel_tool_calls", "tools", "functions")}
        cfg["temperature"] = 0
        client = autogen.OpenAIWrapper(**cfg)
    msg = "\n".join(f"- id={x['id']} | {x['ticker']} | {x['title']} | {x['timeline'][-1]['update']}" for x in cur)
    out = _safe(lambda: _parse_json_array((client.extract_text_or_completion_object(client.create(
        messages=[{"role": "system", "content": _AS.get("news.theme", THEME_SYSTEM)}, {"role": "user", "content": msg}], cache=None)) or [""])[0]
        or ""))
    valid = {x["ticker"] for x in cur}
    return [t for t in (out or []) if isinstance(t, dict) and len([k for k in t.get("tickers", []) if k in valid]) >= 2]


# =============================================================== Signale (Python, aus der Historie im Speicher)
def _week(d):
    return pd.Timestamp(d[:10]).to_period("W-SUN")


def signals(watchlist, period_start, period_end, prices=None, analyst=None, stories=None):
    """Je Position: News-Volumen ggue. eigenem Schnitt, Sentiment (Woche / 4 Wochen), Kurs ggue. ACWI in der Periode,
    Divergenz News vs. Kurs, Analysten-Revisionen, aktive Stories. Historie aus dem Speicher (Backfill hilft)."""
    store = [s for s in load_store() if _is_news(s)]
    bench = pe.BENCHMARKS["MSCI ACWI"]
    out = {}
    cur_w = _week(str(period_end))
    for w in watchlist:
        t = w["ticker"]
        sub = [s for s in store if s["ticker"] == t and s.get("materiality", 1) >= 2]
        weeks = {}
        for s in sub:
            k = _week(s["date"])
            sgn = {"positive": 1, "negative": -1}.get(s.get("direction"), 0)
            wgt = 2 if s.get("materiality") == 3 else 1
            e = weeks.setdefault(k, [0, 0.0])
            e[0] += 1
            e[1] += sgn * wgt
        cur = [s for s in sub if period_start <= s["date"][:10] <= str(period_end)]
        n_cur = len(cur)
        sent_cur = sum({"positive": 1, "negative": -1}.get(s.get("direction"), 0) * (2 if s.get("materiality") == 3 else 1)
                       for s in cur)
        hist_weeks = [k for k in weeks if k < cur_w]
        all_t = [_week(x["date"]) for x in store if x["ticker"] == t]      # Historie = ab erster klassifizierter Meldung
        first = min(all_t) if all_t else cur_w
        span = max((cur_w - first).n, 0)                        # Wochen Historie (inkl. Wochen ohne Meldung)
        avg = (sum(weeks[k][0] for k in hist_weeks) / span) if span >= 3 else None
        last4 = [weeks.get(cur_w - i, [0, 0.0])[1] for i in range(4)] if span >= 3 else None
        r = {"n_notable": n_cur, "avg_weekly": avg, "volume_ratio": (n_cur / avg) if avg else None,
             "sentiment": sent_cur, "sentiment_4w": float(np.mean(last4)) if last4 else None, "history_weeks": span}
        r["period_ar"] = None
        if prices is not None and t in prices and bench in prices:
            px = prices[[t, bench]].dropna()
            a = px[px.index >= pd.Timestamp(period_start)]
            b = px[px.index < pd.Timestamp(period_start)]
            if len(a) and len(b):
                r["period_ar"] = float((a[t].iloc[-1] / b[t].iloc[-1]) - (a[bench].iloc[-1] / b[bench].iloc[-1]))
        flags = []
        if r["volume_ratio"] is not None and r["volume_ratio"] >= 2 and n_cur >= 3:
            flags.append(f"news volume x{r['volume_ratio']:.1f} vs. average")
        elif avg == 0 and n_cur >= 2:
            flags.append(f"first notable news after {span} quiet weeks")
        if r["period_ar"] is not None:
            if sent_cur >= 2 and r["period_ar"] <= -0.03:
                flags.append("divergence: positive news, stock underperformed (overhang?)")
            elif sent_cur <= -2 and r["period_ar"] >= 0.03:
                flags.append("divergence: negative news, stock outperformed (priced in?)")
        m = (analyst or {}).get("momentum", {}).get(t)
        r["analyst_net"] = None
        if m:
            r["analyst_net"] = m["upgrades"] - m["downgrades"] + 0.5 * (m["pt_raises"] - m["pt_cuts"])
            if m["n"] >= 3 and (m["upgrades"] - m["downgrades"] >= 2 or (m["avg_pt_change"] or 0) >= 0.05):
                flags.append("positive analyst revisions (90 days)")
            elif m["n"] >= 3 and (m["downgrades"] - m["upgrades"] >= 2 or (m["avg_pt_change"] or 0) <= -0.05):
                flags.append("negative analyst revisions (90 days)")
        act = [x for x in (stories or []) if x["ticker"] == t and x["status"] not in ("resolved", "quiet")]
        r["active_stories"] = len(act)
        esc = [x["title"] for x in act if x["status"] == "escalating"]
        if esc:
            flags.append("escalating story: " + "; ".join(esc[:2]))
        r["flags"] = flags
        out[t] = r
    return out


def signals_text(sig, stories, themes, period_start):
    P = _pp
    lines = ["SIGNALS by position (calculated from the stored news history; cite as [1]). News volume and sentiment use "
             "notable news only (materiality 2-3, sentiment weight 2 for materiality 3); 'n/a' = fewer than 3 weeks of history:"]
    for t, r in sig.items():
        lines.append(f"- {t}: notable news {r['n_notable']}"
                     + (f" (weekly average {r['avg_weekly']:.1f}, ratio x{r['volume_ratio']:.1f})" if r["volume_ratio"] is not None
                        else " (history n/a)")
                     + f"; sentiment {r['sentiment']:+.0f}" + (f", 4-week average {r['sentiment_4w']:+.1f}" if r["sentiment_4w"]
                                                               is not None else "")
                     + f"; stock vs MSCI ACWI in the period {P(r['period_ar'])}; active stories {r['active_stories']}"
                     + (f"; FLAGS: {' | '.join(r['flags'])}" if r["flags"] else ""))
    cur = [x for x in stories if x.get("last_update", "") >= period_start]
    if cur:
        lines.append("STORIES updated this period (status, since, latest update):")
        for x in sorted(cur, key=lambda y: (y["ticker"], y["first_seen"])):
            lines.append(f"- [{x['id']}] {x['ticker']}: {x['title']} | {x['status']}, {x.get('direction', '')} | since "
                         f"{x['first_seen']} ({len(x['timeline'])} updates) | {x['timeline'][-1]['update']}")
    if themes:
        lines.append("PORTFOLIO THEMES (affecting several positions):")
        for th in themes:
            lines.append(f"- {th.get('theme')}: {', '.join(th.get('tickers', []))} ({th.get('risk', '')}) - "
                         f"{th.get('explanation', '')}")
    return "\n".join(lines)


def backfill(watchlist, llm_config, weeks=8, per_week=15, stories=True, fetchers=None, client=None, prices=None):
    """Einmaliger Rueckblick: Finnhub (1 Jahr verfuegbar) und 8-Ks der letzten 'weeks' Wochen, Woche fuer Woche
    gesammelt und klassifiziert (max. per_week je Position und Woche), optional mit Story-Aufbau in zeitlicher
    Reihenfolge. Yahoo und Google liefern nur aktuelle Meldungen und fehlen deshalb im Rueckblick."""
    us = [w for w in watchlist if _us_symbol(w["ticker"])]
    if len(us) < len(watchlist):
        print("Ohne Rueckblick (keine US-Quelle):", ", ".join(w["ticker"] for w in watchlist if not _us_symbol(w["ticker"])))
    total = 0
    for k in range(weeks, 0, -1):
        end = date.today() - timedelta(days=7 * k)
        items, st = collect(us, days=7, use_google=False, fetchers=fetchers, per_ticker=per_week, end=end)
        n, _ = classify(items, llm_config, client=client)
        total += n
        if stories:
            ids = {i["id"] for i in items}
            track_stories([s for s in load_store() if s["id"] in ids], llm_config, client=client, period_end=end)
        print(f"Woche bis {end}: {len(items)} Meldungen, {n} klassifiziert")
    all_ids = {s["id"] for s in load_store() if s["ticker"] in {w["ticker"] for w in us}}
    market_reaction([s for s in load_store() if s["id"] in all_ids], prices=prices)
    return total


# =============================================================== Texte fuer den Agenten
def _is_news(s):
    """Klassifizierte, relevante Meldung, die KEINE Analystenaktion ist (die stehen im eigenen Abschnitt)."""
    return "category" in s and s.get("relevant", True) and s.get("category") != "analyst rating"


def _pp(v):
    return "n/a" if v is None else f"{v * 100:+.1f}%"


def overview_text(items, stats, watchlist):
    P = _pp
    rel = [s for s in items if _is_news(s)]
    mat = sorted([s for s in rel if s.get("materiality", 1) >= 2], key=lambda x: (-x.get("materiality", 1), x["date"]))
    lines = [f"NEWS OVERVIEW {stats['start']} to {stats['end']} (cite as [1]): {len(watchlist)} positions tracked; "
             f"{stats['raw']} items collected, {stats['relevant']} passed the name filter, {stats['deduplicated']} after "
             f"de-duplication and the cap of {stats.get('per_ticker', 30)} per position ({stats['new']} new); {len(rel)} relevant "
             f"news items (analyst actions excluded, see ANALYST ACTIONS), {len(mat)} notable or material "
             f"(materiality 2-3). Sources: " + ", ".join(f"{k} {v}" for k, v in stats["by_source"].items()) + "."]
    ag = [_agree(s) for s in mat]
    n_ag, n_dis = ag.count("agrees"), ag.count("disagrees")
    if n_ag + n_dis:
        lines.append(f"- Market reaction vs. classified direction (notable items with a move above 1%): agrees {n_ag}, "
                     f"disagrees {n_dis}, no reaction {ag.count('no reaction')}.")
    lines.append("BY POSITION (counts of relevant items: positive / negative / neutral; notable items listed; CAR n/a = "
                 "no trading day since the news yet, do not interpret as a missing reaction):")
    for w in watchlist:
        sub = [s for s in rel if s["ticker"] == w["ticker"]]
        pos_, neg_ = sum(s["direction"] == "positive" for s in sub), sum(s["direction"] == "negative" for s in sub)
        cars = [s["car01"] for s in sub if s.get("car01") is not None and s.get("materiality", 1) >= 2]
        lines.append(f"- {w['ticker']} ({w['name']}): {len(sub)} relevant ({pos_} / {neg_} / {len(sub) - pos_ - neg_})"
                     + (f", average CAR[0,+1] of notable items {P(float(np.mean(cars)))}" if cars else ""))
        th = _theses(w["ticker"])
        for s in [x for x in mat if x["ticker"] == w["ticker"]][:8]:
            tline = ""
            if s.get("thesis") is not None and s["thesis"] < len(th):
                tline = f"; thesis [{s['thesis']}] '{th[s['thesis']]['thesis'][:120]}' -> {s.get('thesis_effect')}"
            vr = f", volume x{s['vol_ratio']:.1f}" if s.get("vol_ratio") else ""
            lines.append(f"    * {s['date'][:10]} [{s['source_type']}/{s.get('publisher', '')}] {s['title'][:160]} | "
                         f"{s['category']}, {s['direction']}, materiality {s['materiality']} | AR day 0 {P(s.get('ar0'))}, "
                         f"CAR[0,+1] {P(s.get('car01'))}{vr} | {s.get('reason', '')}{tline}")
    alerts = [s for s in mat if s.get("thesis_effect") == "challenges"]
    if alerts:
        lines.append("THESIS ALERTS (notable items classified as challenging a thesis):")
        for s in alerts:
            lines.append(f"- {s['ticker']} {s['date'][:10]}: {s['title'][:140]} ({s.get('reason', '')})")
    if stats.get("errors"):
        lines.append("DATA NOTES: " + " | ".join(stats["errors"][:6]))
    return "\n".join(lines)


def theses_text(ticker):
    th = _theses(ticker)
    if not th:
        return f"No investment theses on file for {ticker} (run the annual report agent first)."
    return f"Investment theses for {ticker} (from the annual report agent; cite as [2]):\n" + "\n".join(
        f"[{i}] {t['thesis']} | signpost: {t['signpost']} | invalidation: {t['invalidation']}"
        + (f" | last status: {t['status']}" if t.get("status") else "") for i, t in enumerate(th))


# =============================================================== PDF
def _charts(items, watchlist, base, color):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rel = [s for s in items if _is_news(s)]
    paths = {}
    tick = [w["ticker"] for w in watchlist]
    cnt = {d: [sum(1 for s in rel if s["ticker"] == t and s["direction"] == d) for t in tick]
           for d in ("positive", "neutral", "negative")}
    order = np.argsort([-(a + b + c) for a, b, c in zip(*cnt.values())])[:15]
    fig, ax = plt.subplots(figsize=(5.2, 4.2))
    left = np.zeros(len(order))
    for d, col in (("positive", "#2D8A4E"), ("neutral", "#B8C2CC"), ("negative", "#C0392B")):
        vals = np.array(cnt[d])[order]
        ax.barh(range(len(order)), vals, left=left, color=col, label=d)
        left += vals
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([tick[i] for i in order], fontsize=8)
    ax.invert_yaxis()
    ax.legend(fontsize=7, frameon=False, loc="lower right")
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.set_xlabel("Relevant news items", fontsize=8)
    fig.tight_layout()
    paths["counts"] = base + "_counts.png"
    fig.savefig(paths["counts"], dpi=200)
    plt.close(fig)
    pts = [(s, {"positive": 1, "neutral": 0, "negative": -1}[s["direction"]]) for s in rel if s.get("car01") is not None]
    if pts:
        rng = np.random.default_rng(0)
        fig, ax = plt.subplots(figsize=(9, 2.9))
        for s, x in pts:
            ax.scatter(x + rng.uniform(-0.18, 0.18), s["car01"] * 100, s=12 + 18 * (s.get("materiality", 1) - 1),
                       color={"agrees": "#2D8A4E", "disagrees": "#C0392B"}.get(_agree(s), "#9AA5B1"), alpha=0.8,
                       edgecolor="white", lw=0.4)
        ax.axhline(0, color="#888888", lw=0.6)
        ax.set_xticks([-1, 0, 1])
        ax.set_xticklabels(["negative", "neutral", "positive"], fontsize=8)
        ax.set_ylabel("CAR day 0..+1 vs ACWI (%)", fontsize=8)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        ax.grid(axis="y", color="#E5E5E5", lw=0.6)
        fig.tight_layout()
        paths["reaction"] = base + "_reaction.png"
        fig.savefig(paths["reaction"], dpi=200)
        plt.close(fig)
    return paths


def _build_pdf(pdf_path, title, texts, items, stats, watchlist, fc, analyst=None, state=None):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_JUSTIFY
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from finrobot.functional.reportlab import REPORT_BRAND, REPORT_COLOR, _heading_font, _paragraphs, _scaled_image, _tint

    NAVY, PANEL, GREY = colors.HexColor(REPORT_COLOR), colors.HexColor(_tint(REPORT_COLOR, 0.93)), colors.HexColor("#5A6472")
    page_w, page_h = A4
    m = 1.6 * cm
    usable = page_w - 2 * m
    ss = getSampleStyleSheet()
    hf = _heading_font()
    body = ParagraphStyle("BodyN", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13.2,
                          alignment=TA_JUSTIFY, spaceAfter=5)
    small = ParagraphStyle("SmallN", parent=body, fontSize=7, leading=9, textColor=GREY, alignment=0)
    cell = ParagraphStyle("CellN", parent=body, fontSize=7.4, leading=9.2, alignment=0, spaceAfter=0)
    cell_r = ParagraphStyle("CellRN", parent=cell, alignment=2)
    cell_w = ParagraphStyle("CellWN", parent=cell, textColor=colors.white, fontName="Helvetica-Bold")
    h1 = ParagraphStyle("H1N", parent=body, fontName=hf, fontSize=20, leading=24, textColor=NAVY, alignment=0)
    h2 = ParagraphStyle("H2N", parent=body, fontName=hf, fontSize=13, leading=16, textColor=NAVY, alignment=0,
                        spaceBefore=8, spaceAfter=2)
    head = ParagraphStyle("HeadN", parent=body, fontName="Helvetica-Bold", fontSize=11.5, leading=14.5, alignment=0)
    exh = ParagraphStyle("ExhN", parent=cell, fontName="Helvetica-Bold", textColor=NAVY, fontSize=8.5, spaceBefore=6,
                         spaceAfter=3)
    line = TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("LINEBELOW", (0, -1), (-1, -1), 0.8, NAVY),
                       ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor(_tint(REPORT_COLOR, 0.96))]),
                       ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1.8),
                       ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8)])
    exno = [0]

    def heading(t):
        return [Paragraph(t, h2), HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceBefore=1, spaceAfter=5)]

    def exhibit(t):
        exno[0] += 1
        return Paragraph(f"Exhibit {exno[0]}: {t}", exh)

    def source(t):
        return Paragraph(f"Source: {t}", small)

    def table(rows, widths, right=()):
        out = [[Paragraph(str(c), cell_w) for c in rows[0]]]
        for r in rows[1:]:
            out.append([Paragraph(str(c), cell_r if i in right else cell) for i, c in enumerate(r)])
        t = Table(out, colWidths=widths, repeatRows=1)
        t.setStyle(line)
        return t

    paths = _charts(items, watchlist, os.path.splitext(pdf_path)[0], REPORT_COLOR)
    rel = [s for s in items if _is_news(s)]
    mat = sorted([s for s in rel if s.get("materiality", 1) >= 2], key=lambda x: (-x["materiality"], x["ticker"], x["date"]))
    content = [Paragraph(escape(title), h1), Spacer(1, 3), Paragraph(escape(texts["headline"]), head), Spacer(1, 2),
               Paragraph(f"{stats['start']} to {stats['end']} | {len(watchlist)} positions | {len(rel)} relevant items, "
                         f"{len(mat)} notable | Generated by {REPORT_BRAND}", small), Spacer(1, 8)]
    left_w, right_w = usable * 0.54, usable * 0.42
    inner = right_w - 14
    ag = [_agree(s) for s in mat]
    kd = [["Key figures", ""], ["Items collected / after filter", f"{stats['raw']} / {stats['deduplicated']}"],
          ["Relevant / notable (materiality 2-3)", f"{len(rel)} / {len(mat)}"],
          ["Positive / negative (relevant)", f"{sum(s['direction'] == 'positive' for s in rel)} / "
                                             f"{sum(s['direction'] == 'negative' for s in rel)}"],
          ["Thesis alerts", str(len(texts.get("thesis_alerts") or []))],
          ["Analyst actions (period)", str(len((analyst or {}).get("actions") or []))],
          ["Market agrees / disagrees", f"{ag.count('agrees')} / {ag.count('disagrees')}"]]
    kt = Table([[Paragraph(r[0], cell_w if i == 0 else cell), Paragraph(r[1], cell_w if i == 0 else cell_r)]
                for i, r in enumerate(kd)], colWidths=[inner * 0.66, inner * 0.34])
    kt.setStyle(TableStyle(line.getCommands() + [("SPAN", (0, 0), (-1, 0))]))
    right = [exhibit("Key figures"), kt, source("Own collection and classification [1]"), Spacer(1, 6),
             exhibit("Relevant news by position"), _scaled_image(paths["counts"], inner, 6.2 * cm),
             source("Finnhub, Yahoo Finance, SEC EDGAR, Google News [1]")]
    panel = Table([[right]], colWidths=[right_w])
    panel.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PANEL), ("LEFTPADDING", (0, 0), (-1, -1), 7),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    left = [Paragraph("Summary", ParagraphStyle("SH", parent=head, fontSize=10.5, textColor=NAVY))]
    left += _paragraphs(texts["summary"], body)
    top = Table([[left, panel]], colWidths=[left_w, usable - left_w])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (0, 0), 12)]))
    content.append(top)
    if texts.get("thesis_alerts"):
        rows = [["Position", "Thesis", "Evidence this week", "Status"]]
        for a_ in texts["thesis_alerts"]:
            rows.append([f"<b>{escape(str(a_.get('ticker', '')))}</b>", escape(str(a_.get("thesis", ""))),
                         escape(str(a_.get("evidence", ""))), escape(str(a_.get("status", "")))])
        content += heading("Thesis Alerts") + [table(rows, [usable * 0.11, usable * 0.32, usable * 0.43, usable * 0.14]),
                                               source("Classification of the news against the agent's investment theses "
                                                      "[1][2]")]
    state = state or {}
    sig, stories, themes = state.get("signals") or {}, state.get("stories") or [], state.get("themes") or []
    if sig:
        rows = [["Position", "Notable news", "Vol. vs avg", "Sentiment wk / 4w", "Stock vs ACWI", "Analyst net",
                 "Stories", "Flags"]]
        for t, r in sig.items():
            if not (r["n_notable"] or r["flags"] or r["active_stories"]):
                continue
            rows.append([f"<b>{escape(t)}</b>", str(r["n_notable"]),
                         f"x{r['volume_ratio']:.1f}" if r["volume_ratio"] is not None else "n/a",
                         f"{r['sentiment']:+.0f} / " + (f"{r['sentiment_4w']:+.1f}" if r["sentiment_4w"] is not None else "n/a"),
                         _pp(r["period_ar"]), f"{r['analyst_net']:+.1f}" if r["analyst_net"] is not None else "n/a",
                         str(r["active_stories"]), escape("; ".join(r["flags"])) or "-"])
        content += heading("Signals") + _paragraphs(texts.get("signal_commentary") or "", body) + [
            table(rows, [usable * 0.10, usable * 0.08, usable * 0.08, usable * 0.11, usable * 0.10, usable * 0.08,
                         usable * 0.085, usable * 0.365], right=(1, 2, 3, 4, 5, 6)),
            source("Own calculations from the stored news history [1]: notable news only; sentiment = positive minus negative "
                   "(weight 2 for materiality 3); stock vs ACWI = excess return in the period (EUR); analyst net = upgrades "
                   "minus downgrades plus 0.5 x (target raises minus cuts), 90 days; n/a = fewer than 3 weeks of history.")]
    cur = sorted([x for x in stories if x.get("last_update", "") >= stats["start"]], key=lambda y: (y["ticker"], y["first_seen"]))
    if cur:
        rows = [["Position", "Story", "Status", "Since", "Latest update"]]
        col = {"escalating": "#C0392B", "new": "#0F4C5C", "calming": "#2D8A4E", "resolved": "#2D8A4E"}
        for x in cur[:30]:
            stt = x["status"]
            rows.append([f"<b>{escape(x['ticker'])}</b>", escape(x["title"]),
                         f"<font color='{col.get(stt, '#5A6472')}'><b>{escape(stt)}</b></font>",
                         f"{x['first_seen']} ({len(x['timeline'])})", escape(x["timeline"][-1]["update"])])
        content.append(KeepTogether(heading("Developing Stories") + [
            table(rows, [usable * 0.10, usable * 0.24, usable * 0.11, usable * 0.13, usable * 0.42]),
            source("Notable news grouped into stories by the language model; (n) = number of updates; stories without "
                   "news for four weeks are set to quiet [1].")]))
    if themes:
        rows = [["Theme", "Positions", "Type", "Explanation"]]
        for th in themes:
            rows.append([f"<b>{escape(str(th.get('theme', '')))}</b>", escape(", ".join(th.get("tickers", []))),
                         escape(str(th.get("risk", ""))), escape(str(th.get("explanation", "")))])
        content.append(KeepTogether(heading("Portfolio Themes") + [
            table(rows, [usable * 0.20, usable * 0.18, usable * 0.12, usable * 0.50]),
            source("Stories affecting several positions, identified by the language model [1].")]))
    if texts.get("position_notes"):
        rows = [["Position", "Notable", "Avg. CAR", "Note", "Action"]]
        for p in texts["position_notes"]:
            t = str(p.get("ticker", ""))
            cars = [s["car01"] for s in mat if s["ticker"] == t and s.get("car01") is not None]
            rows.append([f"<b>{escape(t)}</b>", str(sum(1 for s in mat if s["ticker"] == t)),
                         _pp(float(np.mean(cars))) if cars else "n/a", escape(str(p.get("note", ""))),
                         escape(str(p.get("action", "")))])
        content += heading("Position Notes") + [table(rows, [usable * 0.11, usable * 0.08, usable * 0.09, usable * 0.58,
                                                             usable * 0.14], right=(1, 2)),
                                                source("Agent assessment based on [1]; 'review' = worth a closer look, not a "
                                                       "trading recommendation. CAR = abnormal return vs MSCI ACWI, day 0..+1.")]
    if mat:
        rows = [["Date", "Position", "Headline (source)", "Category", "Dir", "Mat", "CAR"]]
        per, shown = {}, []
        for s in sorted(mat, key=lambda x: (-x["materiality"], -abs(x.get("car01") or 0), x["date"])):
            if per.get(s["ticker"], 0) < 3:
                per[s["ticker"]] = per.get(s["ticker"], 0) + 1
                shown.append(s)
        shown = sorted(shown, key=lambda x: (x["ticker"], x["date"]))
        for s in shown:
            link = f'<link href="{escape(s.get("url", ""))}" color="#0F4C5C">{escape(s["title"][:150])}</link>' if s.get("url") \
                else escape(s["title"][:150])
            rows.append([s["date"][:10], escape(s["ticker"]), f"{link} <font color='#5A6472'>({escape(s['source_type'])}"
                         f"{'/' + escape(str(s.get('publisher', ''))[:25]) if s.get('publisher') else ''})</font>",
                         escape(s["category"]), {"positive": "+", "negative": "-"}.get(s["direction"], "o"),
                         str(s["materiality"]), _pp(s.get("car01"))])
        content += heading("Notable News") + [table(rows, [usable * 0.10, usable * 0.09, usable * 0.45, usable * 0.14,
                                                           usable * 0.06, usable * 0.06, usable * 0.10], right=(4, 5, 6)),
                                              source("Collected news [1]; up to three notable items per position (highest "
                                                     "materiality first); classification by language model (prompt "
                                                     f"{PROMPT_VERSION}); CAR from Yahoo Finance prices in EUR; n/a = no "
                                                     "trading day yet.")]
    if analyst and (analyst.get("actions") or analyst.get("momentum")):
        content += heading("Analyst Actions") + _paragraphs(texts.get("analyst_commentary") or "", body)
        if analyst.get("actions"):
            rows = [["Date", "Position", "Firm", "Action", "Rating", "Target (change)", "Upside", "Source"]]
            for a_ in analyst["actions"][:30]:
                tgt = f"{a_['price_target']:,.2f}" if a_.get("price_target") else "n/a"
                if a_.get("pt_change") is not None:
                    tgt += f" ({_pp(a_['pt_change'])})"
                rat = f"{a_['from_rating']} &gt; {a_['rating']}" if a_.get("from_rating") and a_["from_rating"] != a_["rating"] \
                    else escape(a_.get("rating") or "")
                rows.append([a_["date"], f"<b>{escape(a_['ticker'])}</b>", escape(a_["firm"][:28]), escape(a_["action"]),
                             rat, tgt, _pp(a_.get("upside")), escape(str(a_.get("source", ""))[:22])])
            content.append(table(rows, [usable * 0.10, usable * 0.09, usable * 0.16, usable * 0.12, usable * 0.15,
                                        usable * 0.14, usable * 0.10, usable * 0.14], right=(5, 6)))
            content.append(source("Yahoo Finance upgrade/downgrade history and analyst actions extracted from the news [1]; "
                                  "targets in the trading currency of the listing; upside vs. current price."))
        if analyst.get("momentum"):
            rows = [["Position", "Actions 90d", "Up / down", "Target raises / cuts", "Avg. target change", "Consensus upside"]]
            for t, m_ in analyst["momentum"].items():
                c = analyst["consensus"].get(t) or {}
                rows.append([f"<b>{escape(t)}</b>", str(m_["n"]), f"{m_['upgrades']} / {m_['downgrades']}",
                             f"{m_['pt_raises']} / {m_['pt_cuts']}", _pp(m_["avg_pt_change"]), _pp(c.get("upside"))])
            content.append(KeepTogether([exhibit("Analyst momentum, last 90 days"),
                                         table(rows, [usable * 0.16, usable * 0.14, usable * 0.14, usable * 0.20,
                                                      usable * 0.18, usable * 0.18], right=(1, 2, 3, 4, 5)),
                                         source("Yahoo Finance [1]; consensus upside = mean analyst target vs. current price.")]))
    if paths.get("reaction"):
        content.append(KeepTogether([exhibit("Does the market agree? Classified direction vs. abnormal return day 0..+1"),
                                     _scaled_image(paths["reaction"], usable, 5.4 * cm),
                                     source("Own calculations [1]; green = same sign, red = opposite sign (move above 1%), "
                                            "grey = smaller move or neutral; size = materiality.")]))
    if texts.get("market_context"):
        content += heading("Market and Sector Context") + _paragraphs(texts["market_context"], body)
    content.append(Paragraph("For academic purposes only; not investment advice.", small))
    refs = [f"News collected {stats['start']} to {stats['end']}: Finnhub company news, Yahoo Finance news, SEC EDGAR 8-K "
            f"filings, Google News RSS (German and English); prices from Yahoo Finance.",
            "Investment theses with signposts from the annual report agent and the thesis log of the earnings reviewer."]
    content += heading("Sources") + [Paragraph(f"[{i}] {escape(r)}", ParagraphStyle(f"RefN{i}", parent=body, fontSize=8.5,
                                                                                    alignment=0, leading=11)) for i, r in
                                     enumerate(refs, 1)]
    rate = f"{fc['match_rate'] * 100:.0f}%" if fc["match_rate"] is not None else "n/a"
    content += heading("Appendix: Automated Fact Check") + [Paragraph(
        f"Every number in the agent's text was compared with the collected data [1]: {fc['matched']} of "
        f"{fc['total_claims']} found ({rate}).", small)]
    gen = date.today().strftime("%d %B %Y")

    def deco(canv, d):
        canv.saveState()
        canv.setFillColor(NAVY)
        if d.page == 1:
            canv.rect(0, page_h - 1.15 * cm, page_w, 1.15 * cm, stroke=0, fill=1)
            canv.setFillColor(colors.white)
            canv.setFont("Helvetica-Bold", 9)
            canv.drawString(m, page_h - 0.72 * cm, "NEWS DIGEST")
            canv.setFont("Helvetica", 9)
            canv.drawRightString(page_w - m, page_h - 0.72 * cm, gen)
        else:
            canv.setFont("Helvetica-Bold", 8)
            canv.drawString(m, page_h - 1.0 * cm, escape(title))
            canv.setFont("Helvetica", 8)
            canv.setFillColor(GREY)
            canv.drawRightString(page_w - m, page_h - 1.0 * cm, f"News Digest  |  {gen}")
            canv.setStrokeColor(NAVY)
            canv.line(m, page_h - 1.15 * cm, page_w - m, page_h - 1.15 * cm)
        canv.setStrokeColor(colors.HexColor(_tint(REPORT_COLOR, 0.75)))
        canv.line(m, 1.25 * cm, page_w - m, 1.25 * cm)
        canv.setFont("Helvetica", 7)
        canv.setFillColor(GREY)
        canv.drawString(m, 0.85 * cm, f"Generated by {REPORT_BRAND} - for academic purposes only, not investment advice")
        canv.drawRightString(page_w - m, 0.85 * cm, f"Page {d.page}")
        canv.restoreState()

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, leftMargin=m, rightMargin=m, topMargin=1.6 * cm, bottomMargin=1.6 * cm)
    doc.build(content, onFirstPage=deco, onLaterPages=deco)


# =============================================================== Agent
def make_tools(state):
    def get_news_overview() -> str:
        """Collected and classified news of the period by position, with market reaction and thesis alerts."""
        return overview_text(state["items"], state["stats"], state["watchlist"])

    def get_signals_and_stories() -> str:
        """Calculated signals by position (news volume vs average, sentiment trend, divergence between news and stock,
        analyst revisions), the developing stories with status and the themes that affect several positions."""
        return signals_text(state.get("signals") or {}, state.get("stories") or [], state.get("themes") or [],
                            state["stats"]["start"])

    def get_analyst_actions() -> str:
        """Analyst rating and price-target changes of the period, 90-day analyst momentum and consensus targets
        (kept separate from the news)."""
        return analyst_text(state.get("analyst"))

    def get_investment_theses(ticker: Annotated[str, "ticker as in the overview, e.g. RBRK or SAP.DE"]) -> str:
        """Investment theses (with signposts and invalidation criteria) of one position from the annual report agent."""
        return theses_text(ticker)

    def build_news_digest(
        headline: Annotated[str, "one-sentence headline of the week (max. 25 words)"],
        summary: Annotated[str, "summary for page 1, 120-220 words: the most important developments, thesis alerts, "
                                "where the market reaction contradicts the news"],
        position_notes: Annotated[List[dict], "one entry per position with notable news: {ticker, note (max. 45 words: "
                                              "what happened and why it matters), action ('review' or 'no action')}"],
        thesis_alerts: Annotated[List[dict], "only where news supports or challenges a thesis: {ticker, thesis (short), "
                                             "evidence (max. 35 words), status ('supported', 'at risk' or 'challenged')}; "
                                             "may be empty"] = None,
        market_context: Annotated[str, "optional, max. 120 words: common themes across positions (sector, macro)"] = "",
        signal_commentary: Annotated[str, "optional, 60-180 words: what the signals show (news volume spikes, sentiment "
                                          "trend, divergences between news and price, escalating stories, portfolio "
                                          "themes); say when the history is too short to judge"] = "",
        analyst_commentary: Annotated[str, "optional, 40-150 words: what the analyst actions and the 90-day momentum say "
                                           "(upgrades vs downgrades, target changes, consensus upside), kept separate "
                                           "from the news"] = "",
    ) -> str:
        """Build the weekly news digest PDF (with automated fact check)."""
        from finrobot.functional.fact_check import SourceIndex, run_fact_check, save_json
        texts = dict(headline=headline, summary=summary, position_notes=position_notes or [],
                     thesis_alerts=thesis_alerts or [], market_context=market_context or "",
                     analyst_commentary=analyst_commentary or "", signal_commentary=signal_commentary or "")
        n = len(summary.split())
        problems = [] if 80 <= n <= 280 else [f"summary: {n} words, expected 120-220"]
        for p in texts["position_notes"]:
            if not isinstance(p, dict) or not p.get("ticker"):
                problems.append("position_notes entries need ticker, note, action")
                break
        if problems:
            return "PDF NOT generated. Problems: " + "; ".join(problems) + ". Fix them and call build_news_digest again."
        os.makedirs(state["save_dir"], exist_ok=True)
        pdf_path = os.path.join(state["save_dir"], f"{state['name']}_news_digest.pdf")
        base = os.path.splitext(pdf_path)[0]
        json.dump(texts, open(base + "_build_args.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
        src = SourceIndex("[1] Collected news data")
        src.add_text(overview_text(state["items"], state["stats"], state["watchlist"]))
        src.add_text(analyst_text(state.get("analyst")))
        src.add_text(signals_text(state.get("signals") or {}, state.get("stories") or [], state.get("themes") or [],
                                  state["stats"]["start"]))
        for w in state["watchlist"]:
            src.add_text(theses_text(w["ticker"]))
        sections = [("Headline", headline), ("Summary", summary), ("Market context", market_context or ""),
                    ("Analyst commentary", analyst_commentary or ""), ("Signals", signal_commentary or "")]
        sections += [(f"Note {p.get('ticker')}", str(p.get("note", ""))) for p in texts["position_notes"]]
        sections += [(f"Alert {a.get('ticker')}", str(a.get("evidence", ""))) for a in texts["thesis_alerts"]]
        fc = run_fact_check(sections, [src], None)
        key = os.path.abspath(pdf_path)
        _ROUNDS[key] = _ROUNDS.get(key, 0) + 1
        if _ROUNDS[key] == 1:
            save_json(fc, base + "_factcheck_round1.json")
        save_json(fc, base + "_factcheck.json")
        try:
            _build_pdf(pdf_path, state["title"], texts, state["items"], state["stats"], state["watchlist"], fc,
                       state.get("analyst"), state)
        except Exception:
            import traceback
            return "PDF NOT generated:\n" + traceback.format_exc()[-1500:]
        msg = f"News digest generated: {pdf_path}. Fact check: {fc['matched']} of {fc['total_claims']} figures found."
        if _ROUNDS[key] == 1 and fc["unmatched"] and os.environ.get("FINROBOT_SELF_CORRECT", "1") != "0":
            items_ = [f"- [{u['section']}] {u['text']}: \"{' '.join(str(u.get('context', '')).split())[:170]}\""
                      for u in fc["unmatched"][:20]]
            msg += ("\n\nSELF-CHECK (one revision round): these figures were not found in the collected data:\n" +
                    "\n".join(items_) + "\n\nCorrect or remove each, then call build_news_digest exactly once more. "
                    "After that, reply TERMINATE.")
        return msg

    return [get_news_overview, get_signals_and_stories, get_analyst_actions, get_investment_theses, build_news_digest]


SYSTEM = dedent("""
    You are an equity analyst writing a weekly news digest for a private portfolio. Use only the collected news and the
    calculated market reactions; never add facts from memory. Separate signal from noise: focus on notable items
    (materiality 2-3), relate them to the investment theses, and say where the market reaction contradicts the news.
    'review' means worth a closer look, not a trading recommendation. Use tools one at a time; reply TERMINATE when done.
""").strip() + "\n" + STYLE_RULES


def _save_transcript(messages, save_dir, name):
    os.makedirs(save_dir, exist_ok=True)
    with open(os.path.join(save_dir, f"{name}_transcript.md"), "w", encoding="utf-8") as f:
        for m in messages:
            f.write(f"## {m.get('role')} {m.get('name') or ''}\n\n")
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                f.write(f"TOOL CALL {fn.get('name')}: {str(fn.get('arguments'))[:20000]}\n\n")
            for r in m.get("tool_responses") or []:
                f.write(f"TOOL RESPONSE: {str(r.get('content'))[:20000]}\n\n")
            if m.get("content"):
                f.write(str(m["content"])[:20000] + "\n\n")


def run_news_tracker(llm_config, classifier_config=None, watchlist=None, days=7, use_google=True,
                     save_dir="reports/news", name=None, title="Weekly News Digest", fetchers=None, prices=None,
                     volumes=None, classifier_client=None, per_ticker=30, workers=4, analyst_fetch=None):
    """Sammeln -> klassifizieren (classifier_config, sonst llm_config) -> Marktreaktion -> Digest-Agent.
    watchlist: Liste von dicts (ticker, name, query) oder None = portfolios/watchlist.csv."""
    import autogen
    from finrobot.toolkits import register_toolkits
    _ROUNDS.clear()
    wl = watchlist or load_watchlist()
    name = name or f"news_{date.today().isoformat()}"
    print(f"Sammle News fuer {len(wl)} Positionen ({days} Tage) ...")
    items, stats = collect(wl, days=days, use_google=use_google, fetchers=fetchers, per_ticker=per_ticker)
    print(f"{stats['raw']} gesammelt, {stats['deduplicated']} nach Filter/Dubletten, {stats['new']} neu; "
          f"{len(items)} im Zeitraum (max. {per_ticker} je Position).")
    classify(items, classifier_config or llm_config, client=classifier_client, workers=workers)
    print("Marktreaktion wird berechnet ...")
    # Marktreaktion fuer die Periode und Nachlauf (5/20 Tage) aelterer wesentlicher Meldungen der letzten 60 Tage
    tick = {w["ticker"] for w in wl}
    cutoff = (date.today() - timedelta(days=60)).isoformat()
    older = [s for s in load_store() if s["ticker"] in tick and s["date"][:10] >= cutoff and s.get("materiality", 1) >= 2
             and s.get("car020") is None]
    px = market_reaction(list({i["id"]: i for i in items + older}.values()), prices=prices, volumes=volumes)
    ids = {i["id"] for i in items}
    items = [s for s in load_store() if s["id"] in ids]
    print("Stories werden aktualisiert ...")
    stories = track_stories(items, classifier_config or llm_config, client=classifier_client, workers=workers)
    themes = portfolio_themes(stories, stats["start"], classifier_config or llm_config, client=classifier_client)
    items = [s for s in load_store() if s["id"] in ids]
    print("Analystenaktionen werden geladen ...")
    analyst = analyst_summary(items, wl, days=days, fetch=analyst_fetch)
    sig = signals(wl, stats["start"], stats["end"], prices=px, analyst=analyst, stories=stories)
    try:                                            # fuer Pipeline und Portfolio Manager
        act = {}
        for x in stories:
            if x["status"] not in ("resolved", "quiet"):
                act.setdefault(x["ticker"], []).append({"title": x["title"], "status": x["status"],
                                                        "since": x["first_seen"], "last_update": x.get("last_update")})
        NEWS_DIR.mkdir(parents=True, exist_ok=True)
        json.dump({"date": stats["end"], "signals": sig, "stories": act, "themes": themes},
                  open(NEWS_DIR / "signals_latest.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"Signale nicht gespeichert: {e}")
    state = {"items": items, "stats": stats, "watchlist": wl, "save_dir": save_dir, "name": name, "title": title,
             "analyst": analyst, "stories": stories, "themes": themes, "signals": sig}
    agent = autogen.AssistantAgent(name="News_Analyst", system_message=_AS.get("news.digest", SYSTEM), llm_config=llm_config)
    proxy = autogen.UserProxyAgent(
        name="User_Proxy", human_input_mode="NEVER", max_consecutive_auto_reply=12, code_execution_config=False,
        is_termination_msg=lambda x: str(x.get("content") or "").rstrip().rstrip("*.").endswith("TERMINATE"))
    register_toolkits(make_tools(state), agent, proxy)
    msg = ("Write this week's news digest. 1) Call get_news_overview, get_signals_and_stories and get_analyst_actions. "
           "2) For positions with thesis alerts or notable news, call get_investment_theses if needed. 3) Call "
           "build_news_digest with headline, summary, position_notes, thesis_alerts, market_context (portfolio themes), "
           "signal_commentary and analyst_commentary. Write about stories, not single headlines. Keep analyst actions out of the "
           "position notes unless they change the picture. Cite figures exactly as given and mark them [1] (theses [2]). If the tool "
           "returns a SELF-CHECK list, revise once and rebuild.")
    try:
        proxy.initiate_chat(agent, message=msg, cache=None)
    finally:
        _save_transcript(proxy.chat_messages.get(agent, []), save_dir, name)
    pdf = os.path.join(save_dir, f"{name}_news_digest.pdf")
    print(f"\nPDF: {pdf}" if os.path.exists(pdf) else
          f"\nKein PDF erzeugt - Verlauf in {os.path.join(save_dir, name + '_transcript.md')} pruefen.")
    return state


# =============================================================== Evaluation
def export_label_sample(n=100, path=None, seed=1):
    """Zufallsstichprobe klassifizierter Meldungen zum Labeln von Hand (Spalten label_* ausfuellen)."""
    rows = [s for s in load_store() if "category" in s]
    rng = np.random.default_rng(seed)
    pick = [rows[i] for i in rng.choice(len(rows), size=min(n, len(rows)), replace=False)] if rows else []
    path = path or (NEWS_DIR / "label_sample.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "ticker", "date", "title", "summary", "llm_relevant", "llm_category", "llm_direction",
                    "llm_materiality", "label_relevant", "label_category", "label_direction", "label_materiality"])
        for s in pick:
            w.writerow([s["id"], s["ticker"], s["date"][:10], s["title"], " ".join(str(s.get("summary", "")).split())[:400],
                        s.get("relevant"), s.get("category"), s.get("direction"), s.get("materiality"), "", "", "", ""])
    return path


def _f1(y, p, labels):
    out = {}
    for l in labels:
        tp = sum(1 for a, b in zip(y, p) if a == l and b == l)
        fp = sum(1 for a, b in zip(y, p) if a != l and b == l)
        fn = sum(1 for a, b in zip(y, p) if a == l and b != l)
        pr, rc = (tp / (tp + fp) if tp + fp else 0.0), (tp / (tp + fn) if tp + fn else 0.0)
        out[l] = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
    return out


def evaluate_labels(path=None):
    """Trefferquote und Macro-F1 der Klassifizierung gegen die Hand-Labels; dazu Marktuebereinstimmung im Speicher."""
    path = path or (NEWS_DIR / "label_sample.csv")
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r.get("label_direction")]
    res = {"n_labeled": len(rows)}
    for fld, labels in (("direction", ["positive", "negative", "neutral"]), ("category", CATEGORIES)):
        y = [r[f"label_{fld}"].strip().lower() for r in rows if r.get(f"label_{fld}")]
        p = [r[f"llm_{fld}"].strip().lower() for r in rows if r.get(f"label_{fld}")]
        if y:
            f1 = _f1(y, p, [l for l in labels if l in y or l in p])
            res[fld] = {"accuracy": sum(a == b for a, b in zip(y, p)) / len(y), "macro_f1": float(np.mean(list(f1.values()))),
                        "f1_by_class": f1}
    ag = [_agree(s) for s in load_store() if s.get("materiality", 1) >= 2]
    a_, d_ = ag.count("agrees"), ag.count("disagrees")
    res["market_agreement"] = {"agrees": a_, "disagrees": d_, "no_reaction": ag.count("no reaction"),
                               "hit_rate": a_ / (a_ + d_) if a_ + d_ else None}
    return res
