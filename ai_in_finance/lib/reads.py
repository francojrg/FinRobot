"""
Interesting Reads: eine kuratierte Lese-, Hoer- und Seh-Auswahl fuer den Nutzer.

Ablauf (einmal pro Woche oder auf Knopfdruck):
  1. Python sammelt Kandidaten: neue Beitraege der Insights-Quellen (Banken, Blogs, Podcasts, YouTube) und eine
     Google-News-Suche nach laengeren Formaten (Interviews, Podcasts, Analysen, Fondsbriefe) zu den groessten
     Depotpositionen, zur Watchlist und zu den Interessen aus den Einstellungen.
  2. Ein Modell waehlt daraus 5-7 Empfehlungen und begruendet jede in einem Satz. Es darf nur Kandidaten aus der
     Liste waehlen (Pruefung ueber die Kandidaten-ID), erfindet also keine Links.
Speicher: research/reads.json (lokal). Kosten: ein Modellaufruf, typischerweise 1-3 Cent.
"""
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from . import agent_settings as _AS  # Prompts/Parameter aus der App (research/agent_settings.json)
from urllib.parse import quote_plus

AIF = Path(__file__).resolve().parents[1]
STORE = AIF / "research" / "reads.json"
MAX_AGE_DAYS = 7
LONGFORM = '(interview OR podcast OR "deep dive" OR analysis OR "investor letter" OR "shareholder letter" OR essay)'
ROUTINE = re.compile(r"(?i)\b(stock (rises|falls|jumps|drops|slips|gains)|shares? (rise|fall|jump|drop|slip)|price target|"
                     r"top (gainers|losers)|stocks to (buy|watch)|trading volume|52-week|premarket|options activity)\b")

PROMPT = """You curate a short weekly reading, listening and watching list for one private investor.

INVESTOR PROFILE
- Interests (in their own words): {interests}
- Portfolio (largest positions first): {holdings}
- Watchlist: {watchlist}

CANDIDATES (id | type | source | date | title):
{cands}

Pick the {n} candidates this investor would most likely want to spend 10-60 minutes on. Prefer long-form and
original thinking (bank research, investor letters, interviews with management or investors, podcasts, deep dives)
over routine news, price-move stories and listicles. Cover several of their positions and interests rather than one
topic, and include at least one podcast or video if a fitting one exists. Use only ids from the list.

Answer with JSON only:
{{"picks": [{{"id": <id>, "why": "<one sentence in English: why this is worth their time, tied to a position or
interest>", "topic": "<ticker or interest it relates to>"}}]}}"""


def _load():
    try:
        return json.load(open(STORE, encoding="utf-8"))
    except Exception:
        return {}


def latest():
    return _load()


def is_due(max_age_days=MAX_AGE_DAYS):
    d = _load()
    return not d.get("created") or d["created"][:10] < (datetime.now() - timedelta(days=max_age_days)).date().isoformat()


def _google(q, days=30, n=12):
    import requests
    url = f"https://news.google.com/rss/search?q={quote_plus(q + f' when:{days}d')}&hl=en-US&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).content)
    except Exception:
        return []
    out = []
    for it in root.iter("item"):
        t = (it.findtext("title") or "").strip()
        src = it.find("source")
        pub = src.text if src is not None else ""
        if pub and t.endswith(" - " + pub):
            t = t[: -len(pub) - 3]
        try:
            d = datetime.strptime(it.findtext("pubDate")[:25], "%a, %d %b %Y %H:%M:%S").date().isoformat()
        except Exception:
            d = None
        if t and not ROUTINE.search(t):
            out.append({"title": t, "url": it.findtext("link") or "", "source": pub or "Google News", "date": d,
                        "type": "listen" if re.search(r"(?i)podcast|episode", t) else
                        "watch" if re.search(r"(?i)video|watch", t) else "read"})
    return out[:n]


def _profile():
    from .app_backend import load_ui
    from .pipeline import portfolio_positions
    from . import watchlist as wl
    pos = sorted(portfolio_positions(), key=lambda p: -(p.get("weight") or 0))
    hold = [(p["ticker"], p.get("name") or p["ticker"], p.get("weight")) for p in pos if (p.get("weight") or 0) > 0]
    watch = [(w["ticker"], w.get("name") or w["ticker"]) for w in wl.load()]
    return load_ui().get("interests") or "", hold, watch


def candidates(max_queries=12):
    """Kandidaten aus Insights-Quellen (letzte 30 Tage) und Google-News-Suchen; ohne Doppelte."""
    from . import insights as ins
    interests, hold, watch = _profile()
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    out = []
    for x in ins.payload(limit=400)["items"]:
        d = x.get("date") or x.get("first_seen") or ""
        if d >= since[:10]:
            out.append({"title": x["title"], "url": x["url"], "source": x["source"], "date": (x.get("date") or "")[:10] or None,
                        "type": "listen" if x.get("cat") == "media" and "youtube" not in x["url"] else
                        "watch" if "youtube" in x["url"] else "read", "origin": "source"})
    clean = lambda n: re.sub(r"(?i),?\s+(inc|corp|corporation|holdings|ltd|plc|ag|se|n\.?v\.?|s\.?a\.?|class [a-c])\.?$", "", n or "").strip()
    queries = [f'"{clean(n)}" {LONGFORM}' for _, n, _ in hold[:6]] + [f'"{clean(n)}" {LONGFORM}' for _, n in watch[:3]]
    queries += [f'{t.strip()} {LONGFORM}' for t in re.split(r"[,;\n]", interests) if t.strip()][:4]
    for q in queries[:max_queries]:
        for x in _google(q):
            out.append({**x, "origin": "search"})
    seen, uniq = set(), []
    for x in out:
        key = re.sub(r"\W+", "", x["title"].lower())[:80]
        if key and key not in seen:
            seen.add(key)
            uniq.append(x)
    return uniq[:160], (interests, hold, watch)


def run(model=None, llm=None, n=6):
    """Auswahl erstellen und speichern. Rueckgabe: das gespeicherte Dict."""
    from .chat import call_llm
    cands, (interests, hold, watch) = candidates()
    if not cands:
        raise RuntimeError("no candidates found (insight sources and search returned nothing)")
    lines = "\n".join(f"{i} | {c['type']} | {c['source'][:40]} | {c['date'] or '-'} | {c['title'][:160]}"
                      for i, c in enumerate(cands))
    model = model or _AS.model("reads")
    prompt = _AS.get("reads.prompt", PROMPT).format(interests=interests or "(not given)", n=n,
                           holdings=", ".join(f"{t} ({nm}, {w:.0%})" for t, nm, w in hold[:15]) or "(none)",
                           watchlist=", ".join(f"{t} ({nm})" for t, nm in watch[:15]) or "(none)", cands=lines)
    raw, cost = (llm or call_llm)([{"role": "user", "content": prompt}], model=model, max_tokens=1200)
    m = re.search(r"\{.*\}", raw, re.S)
    picks = []
    for p in (json.loads(m.group(0)).get("picks") if m else []) or []:
        try:
            c = cands[int(p.get("id"))]
        except (TypeError, ValueError, IndexError):
            continue                                  # nur echte Kandidaten, keine erfundenen Eintraege
        if c["url"] in {x["url"] for x in picks}:
            continue
        picks.append({**c, "why": str(p.get("why") or "")[:300], "topic": str(p.get("topic") or "")[:40]})
    out = {"created": datetime.now().isoformat(timespec="minutes"), "picks": picks[:n + 1], "n_candidates": len(cands),
           "cost": cost, "model": model}
    STORE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(STORE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out
