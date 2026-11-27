"""
Chat mit dem eigenen Research (App-Reiter "Fragen"). Grundsatz wie im ganzen Projekt: Python sucht die passenden
Stellen in den eigenen Ergebnissen (Reports, Brief, News, Portfolio, Termine), das Sprachmodell formuliert nur aus
diesen nummerierten Quellen, der Faktencheck prueft danach jede Zahl der Antwort gegen genau diese Quellen.
Aktionen (z. B. Earnings Review fuer einen Titel neu laufen lassen) schlaegt das Modell nur vor; ausgefuehrt wird
erst nach Bestaetigung in der App. Jede Frage wird in research/chat_log.jsonl protokolliert (fuer die Evaluation).
"""
import glob
import json
import math
import re
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
ROOT = AIF.parent
FR = ROOT / "finrobot_autogen"
REPORTS = AIF / "reports"
RESEARCH = AIF / "research"
LOG = RESEARCH / "chat_log.jsonl"

SKIP = {"ticker_symbol", "save_path", "save_dir", "filing_date", "fyear", "peer_tickers", "segment_data",
        "share_performance_image_path", "pe_eps_performance_image_path", "statuses"}
LABEL = {"investment_summary": "Investment summary", "key_takeaways": "Key takeaways", "business_overview": "Business",
         "market_position": "Market position", "operating_results": "Operating results", "risk_assessment": "Risks",
         "competitors_analysis": "Competitors", "investment_theses": "Theses", "headline": "Headline",
         "summary": "Summary", "results_commentary": "Results", "thesis_check": "Thesis check",
         "risk_update": "Risk update", "outlook": "Outlook", "company_kpis": "KPIs per quarter"}
# Deutsche Fragen, englische Reports: einfache Uebersetzung wichtiger Begriffe fuer die Suche
SYN = {"umsatz": "revenue sales", "erlöse": "revenue sales", "gewinn": "income profit earnings", "marge": "margin",
       "margen": "margin", "freier": "free", "cashflow": "cash flow", "schulden": "debt", "verschuldung": "debt",
       "these": "thesis", "thesen": "thesis theses", "risiko": "risk", "risiken": "risks", "dividende": "dividend",
       "prognose": "forecast guidance", "ausblick": "outlook guidance", "bewertung": "valuation", "kgv": "pe valuation",
       "wachstum": "growth", "quartal": "quarter", "quartale": "quarters", "aktie": "stock share", "kurs": "price stock",
       "investitionen": "capex capital expenditures", "gebrochen": "broken", "geschwächt": "weakened",
       "gestärkt": "strengthened", "intakt": "intact", "gewicht": "weight", "depot": "portfolio", "portfolio": "portfolio",
       "termine": "termine dates earnings dividend calendar", "termin": "termine date calendar", "handlungsbedarf": "decide read trigger", "zahlen": "results quarter", "nachrichten": "news",
       "konkurrenz": "competitors", "wettbewerb": "competitors competition", "entscheiden": "decide decision",
       "einlesen": "read", "betriebsergebnis": "operating income", "nettogewinn": "net income", "ergebnis": "income results",
       "jahresbericht": "annual report", "rendite": "return", "verlust": "loss", "kosten": "costs fees"}
STOP = set("""der die das und oder ist sind war wie was warum wieso welche welcher welches wer wo wann ich du er sie es
wir ihr mein dein unser euer ein eine einen einem einer zu im in am an auf aus bei mit von vom zur zum für über unter
nicht auch noch schon nur sehr mehr hat haben wird werden kann können soll sollte gibt the a an and or of to in on
for is are was were be by with as at from that this it its which what why how who""".split())


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _clean(s):
    return re.sub(r"\s*\[\d+(?:\]\[\d+)*(?:,\s*\d+)*\]", "", str(s or "")).strip()


def _tok(s):
    out = []
    for w in re.findall(r"[a-zäöüß0-9][a-zäöüß0-9.\-]*", str(s).lower()):
        w = w.strip(".-")
        parts = [w] + ([p for p in re.split(r"[-]", w) if p] if "-" in w else [])
        out += [p for p in parts if p not in STOP and len(p) > 1]
    return out


def _split(text, size=650):
    """Text in Stuecke von etwa size Zeichen an Satzgrenzen."""
    sents = re.split(r"(?<=[.!?])\s+", str(text))
    out, cur = [], ""
    for s in sents:
        if len(cur) + len(s) > size and cur:
            out.append(cur.strip())
            cur = ""
        cur += s + " "
    if cur.strip():
        out.append(cur.strip())
    return out


# =============================================================== Quellen sammeln
def _report_chunks(e):
    a = _load(AIF / e["args"]) or {}
    kind = "Annual Report FY" + str(e.get("fy") or "") if e["kind"] == "annual" else "Earnings Review"
    head = f"{e['ticker']} {kind} ({e['date']})"
    out = []
    for k, v in a.items():
        if k in SKIP or k.endswith("_path") or not v:
            continue
        lab = f"{head} · {LABEL.get(k, k.replace('_', ' ').capitalize())}"
        if k == "company_kpis" and isinstance(v, list):
            lines = []
            for x in v:
                if not isinstance(x, dict):
                    continue
                vals = "; ".join(f"{q} {val}" + (f" (prior year {x.get('prior_values', {}).get(q)})"
                                                 if (x.get("prior_values") or {}).get(q) is not None else "")
                                 for q, val in (x.get("values") or {}).items())
                lines.append(f"{x.get('name')} ({x.get('unit')}): {vals}")
            out.append((lab, "\n".join(lines)))
        elif k in ("thesis_check", "investment_theses") and isinstance(v, list):
            for x in v:
                if not isinstance(x, dict):
                    continue
                st = ", ".join(f"{q}: {s}" for q, s in (x.get("statuses") or {}).items())
                txt = f"{_clean(x.get('thesis'))}. " + (f"Status by quarter: {st}. " if st else "") + \
                      (f"Current status: {x.get('current_status')}. " if x.get("current_status") else "") + \
                      (f"Signpost: {_clean(x.get('signpost'))}. " if x.get("signpost") else "") + \
                      f"Evidence: {_clean(x.get('evidence'))}"
                out.append((lab, txt))
        elif isinstance(v, list):
            out.append((lab, "\n".join("- " + _clean(x) for x in v if isinstance(x, str))))
        elif isinstance(v, str):
            for part in _split(_clean(v)):
                out.append((lab, part))
    return [(lab, txt, e["ticker"]) for lab, txt in out if txt.strip()]


def build_corpus():
    """[(label, text, ticker or None)] aus allen eigenen Ergebnissen; je Firma und Report-Art der neueste Stand."""
    chunks = []
    try:
        from .company_data import load_index
        latest = {}
        for e in sorted(load_index(), key=lambda e: e["date"]):
            latest[(e["ticker"], e["kind"], e.get("fy") if e["kind"] == "annual" else None)] = e
        for e in latest.values():
            chunks += _report_chunks(e)
    except Exception:
        pass
    # Weekly Brief: Eingaben (mit Herkunft) und Texte
    try:
        from .brief_agent import brief_lines
        bj = sorted(glob.glob(str(RESEARCH / "briefs" / "brief_*.json")))
        if bj:
            data = _load(bj[-1])
            cur_t, block = None, []
            for text, origin in brief_lines(data):
                t = origin.split(" · ")[0] if origin and " · " in origin else None
                if t != cur_t and block:
                    chunks.append((f"Weekly brief inputs {data['date']} · {cur_t or 'portfolio'}", "\n".join(block), cur_t))
                    block = []
                cur_t = t
                block.append(text.strip())
            if block:
                chunks.append((f"Weekly brief inputs {data['date']} · {cur_t or 'portfolio'}", "\n".join(block), cur_t))
        ba = sorted(glob.glob(str(REPORTS / "brief_*" / "brief_*_build_args.json")))
        if ba:
            b = _load(ba[-1]) or {}
            d = Path(ba[-1]).name[6:16]
            chunks.append((f"Weekly brief {d} · Summary", _clean(f"{b.get('headline', '')} {b.get('summary', '')}"), None))
            for x in b.get("items") or []:
                chunks.append((f"Weekly brief {d} · {x.get('ticker')}",
                               _clean(f"{x.get('what', '')} Why: {x.get('why', '')} Next step: {x.get('next_step', '')}"),
                               str(x.get("ticker", "")).upper() or None))
    except Exception:
        pass
    # News Digest und einzelne Meldungen
    nd = sorted(glob.glob(str(REPORTS / "news_*" / "*_news_digest_build_args.json")))
    if nd:
        a = _load(nd[-1]) or {}
        d = time.strftime("%Y-%m-%d", time.localtime(Path(nd[-1]).stat().st_mtime))
        for k, v in a.items():
            if k in SKIP or not v:
                continue
            if isinstance(v, str):
                for part in _split(_clean(v)):
                    chunks.append((f"News digest {d} · {k.replace('_', ' ')}", part, None))
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        t = str(x.get("ticker", "")).upper() or None
                        chunks.append((f"News digest {d} · {k.replace('_', ' ')}" + (f" · {t}" if t else ""),
                                       _clean(" ".join(f"{kk}: {vv}" for kk, vv in x.items() if isinstance(vv, (str, int, float)))), t))
                    elif isinstance(x, str):
                        chunks.append((f"News digest {d} · {k.replace('_', ' ')}", _clean(x), None))
    try:
        from .news_tracker import load_store
        since = (date.today() - timedelta(days=30)).isoformat()
        for s in load_store():
            if s.get("date", "")[:10] >= since and s.get("materiality", 1) >= 2 and s.get("relevant", True):
                txt = f"{s.get('title', '')}. {s.get('summary', '') or ''}"
                if s.get("car01") is not None:
                    txt += f" Stock reaction day 0-1: {s['car01'] * 100:+.1f}%."
                chunks.append((f"News {s['date'][:10]} · {s.get('ticker')} · {s.get('source_type', 'news')}", txt.strip(),
                               str(s.get("ticker", "")).upper()))
    except Exception:
        pass
    # Portfolio-Kennzahlen und Termine
    try:
        from .home_data import portfolio_payload
        p = portfolio_payload()
        if p:
            pos = "; ".join(f"{x['t']} weight {x['w'] * 100:.1f}%" + (f", 1-year return {x['ret1y'] * 100:+.0f}%" if x['ret1y'] is not None else "")
                            + (f", share of risk {x['rc'] * 100:.1f}%" if x['rc'] is not None else "") for x in p["positions"])
            chunks.append((f"Portfolio manager {p['date']} · Positions", pos, None))
            s = p["stats"]
            chunks.append((f"Portfolio manager {p['date']} · Risk and return",
                           f"Return p.a. {s.get('cagr', 0) * 100:.1f}% vs benchmark {s.get('bench_cagr', 0) * 100:.1f}%, volatility "
                           f"{s.get('vol', 0) * 100:.1f}%, Sharpe {s.get('sharpe', 0):.2f}, max drawdown {s.get('max_dd', 0) * 100:.1f}%, "
                           f"beta {s.get('beta', 0):.2f}. Periods: " + "; ".join(
                               f"{x['p']} {x['r'] * 100:+.1f}% vs {x['b'] * 100:+.1f}%" for x in p["periods"] if x["r"] is not None and x["b"] is not None)
                           + ". Stress tests: " + "; ".join(f"{x.get('scenario')} {x.get('portfolio', 0) * 100:+.1f}%" for x in p["stress"]), None))
            st = p["struct"] or {}
            if st.get("sector"):
                chunks.append((f"Portfolio manager {p['date']} · Structure", "Sectors: " + ", ".join(
                    f"{k} {v * 100:.1f}%" for k, v in st["sector"].items()) + f"; effective number of positions {st.get('effective_n', 0):.1f}", None))
    except Exception:
        pass
    ev = _load(RESEARCH / "events.json") or {}
    today = date.today().isoformat()
    cal = [f"{x['date']}: {x['ticker']} {x['type']} {x.get('detail', '')}".strip()
           for x in ev.get("upcoming", []) if x["date"] >= today]
    if cal:
        chunks.append((f"Calendar (Yahoo Finance, as of {ev.get('updated', '')[:10]}) · upcoming dates and events "
                       "Termine earnings dividend", "\n".join(cal), None))
    for x in ev.get("announced", [])[:8]:
        chunks.append((f"News announcement {x['date']} · {x['ticker']} · event", x.get("detail", ""), x["ticker"].upper()))
    return [(l, t, k) for l, t, k in chunks if t and t.strip()]


# =============================================================== Suche (BM25)
def _names():
    """Firmennamen -> Ticker (fuer Fragen wie 'Wie laeuft Amazon?')."""
    out = {}
    try:
        from .company_data import companies
        for c in companies():
            out[c["t"].lower()] = c["t"]
            out[c["t"].split(".")[0].lower()] = c["t"]
            w = re.findall(r"[A-Za-zäöü]{3,}", str(c.get("name") or ""))
            if w and w[0].lower() not in ("the", "inc"):
                out[w[0].lower()] = c["t"]
    except Exception:
        pass
    if "alphabet" in out:
        out["google"] = out["alphabet"]
    return out


def tickers_in(question, names=None):
    names = names or _names()
    words = re.findall(r"[A-Za-zäöüÄÖÜ.\-]+", question)
    hits = []
    for w in words:
        t = names.get(w.lower()) or names.get(w.lower().rstrip("s"))
        if t and t not in hits:
            hits.append(t)
    return hits


def retrieve(question, corpus=None, k=10, focus=None, max_chars=9000):
    corpus = corpus if corpus is not None else build_corpus()
    q = _tok(question)
    q += [x for w in list(q) for x in SYN.get(w, "").split()]
    focus = focus if focus is not None else tickers_in(question)
    docs = [_tok(l + " " + t) for l, t, _ in corpus]
    N = len(docs) or 1
    avg = sum(len(d) for d in docs) / N
    df = Counter(w for d in docs for w in set(d))
    portfolio_q = any(w in q for w in ("portfolio", "depot", "weight", "risk", "positions", "position"))
    news_q = any(w in q for w in ("news", "nachrichten", "meldung", "meldungen", "story", "stories", "schlagzeilen"))
    decide_q = any(w in q for w in ("decide", "decision", "read", "warum", "trigger", "handlungsbedarf"))
    scored = []
    for i, d in enumerate(docs):
        tf = Counter(d)
        s = 0.0
        for w in q:
            if w not in tf:
                continue
            idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(d) / avg))
        t = corpus[i][2]
        if focus:
            s *= 2.5 if t in focus else (1.0 if t is None else 0.4)
        if portfolio_q and corpus[i][0].startswith(("Portfolio manager", "Weekly brief")):
            s *= 1.6
        if corpus[i][0].startswith("News ") and not news_q:
            s *= 0.6  # viele kurze Meldungen sollen die Reports nicht verdraengen
        if decide_q and corpus[i][0].startswith("Weekly brief"):
            s *= 1.5
        if s > 0:
            scored.append((s, i))
    scored.sort(reverse=True)
    out, used = [], 0
    for s, i in scored:
        lab, txt, t = corpus[i]
        if used + len(txt) > max_chars and out:
            continue
        out.append({"label": lab, "text": txt, "ticker": t, "score": round(s, 2)})
        used += len(txt)
        if len(out) >= k:
            break
    return out


# =============================================================== Antwort
SYSTEM = """You are the research assistant inside "Franci's FINRobot", a private investor's research app.
Answer ONLY from the numbered sources below (the investor's own agent reports, weekly brief, news and portfolio data).
Rules:
- Cite every statement with the source number in square brackets, e.g. [2]. Never cite a number that is not listed.
- Copy figures exactly as they appear in the sources; do not recalculate or round differently. If you derive a figure,
  say so and show the inputs.
- If the sources do not answer the question, say that plainly and name which agent run would provide it
  (annual report agent, earnings reviewer, news tracker, portfolio manager).
- Answer in the language of the question (German question -> German answer). Be concise: at most about 170 words,
  short paragraphs or bullet points starting with "- ".
- No buy or sell recommendations; you may describe options to consider.
- Write the answer text first. Optional LAST line, only if an action would clearly help: ACTIONS: followed by a JSON list, e.g.
  ACTIONS: [{"type": "check", "ticker": "MA"}]
  Types: "check" (rerun annual report and earnings review for a ticker), "open" (open the company dashboard),
  "add" (create reports for a ticker that has none yet)."""


def _oai():
    oai = _load(FR / "OAI_CONFIG_LIST") or []
    e = next((x for x in oai if "openrouter" in str(x.get("base_url", ""))), oai[0] if oai else None)
    return e


def call_llm(messages, model=None, max_tokens=900):
    """OpenRouter (OpenAI-kompatibel). Rueckgabe (Text, Kosten in USD oder None)."""
    import requests
    e = _oai()
    if not e or not e.get("api_key"):
        raise RuntimeError("No OpenRouter key saved (Settings).")
    url = str(e.get("base_url") or "https://openrouter.ai/api/v1").rstrip("/") + "/chat/completions"
    body = {"model": model or e.get("model"), "messages": messages, "temperature": 0.2, "max_tokens": max_tokens,
            "usage": {"include": True}}
    if str(body["model"] or "").startswith("google/"):   # Gemini denkt sonst lange und verbraucht max_tokens
        body["reasoning"] = {"effort": "low"}
    r = requests.post(url, headers={"Authorization": f"Bearer {e['api_key']}", "Content-Type": "application/json",
                                    "X-Title": "Franci's FINRobot"}, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"OpenRouter antwortete {r.status_code}: {r.text[:200]}")
    d = r.json()
    ch = (d.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):  # manche Anbieter liefern Textbausteine
        content = "".join(str(x.get("text", "")) if isinstance(x, dict) else str(x) for x in content)
    content = (content or "").strip()
    cost = (d.get("usage") or {}).get("cost")
    if not content:
        if max_tokens < 2000:  # einmal mit mehr Platz wiederholen (z. B. wenn interne Ueberlegungen das Limit aufbrauchen)
            c2, cost2 = call_llm(messages, model=model, max_tokens=2400)
            return c2, (cost or 0) + (cost2 or 0)
        raise RuntimeError(f"Leere Antwort vom Modell (finish_reason={ch.get('finish_reason')}, "
                           f"Felder={sorted(msg.keys())}, usage={d.get('usage')})")
    return content, cost


def _parse_actions(text):
    """Aktionszeile ("ACTIONS: [...]") herausloesen, egal wo sie steht; der restliche Text bleibt die Antwort."""
    keep, acts = [], []
    for line in str(text or "").splitlines():
        m = re.match(r"^\s*\**ACTIONS:?\**\s*(\[.*\])\s*$", line)
        if m:
            try:
                acts += json.loads(m.group(1))
            except Exception:
                pass
            continue
        keep.append(line)
    ok = [a for a in acts if isinstance(a, dict) and a.get("type") in ("check", "open", "add")
          and re.match(r"^[A-Z][A-Z0-9.\-]{0,9}$", str(a.get("ticker", "")).upper())]
    for a in ok:
        a["ticker"] = str(a["ticker"]).upper()
    return "\n".join(keep).strip(), ok[:3]


def answer(question, history=None, model=None, llm=None):
    """Frage beantworten: Suche -> Sprachmodell -> Faktencheck. history: [{"q", "a"}] (letzte Runden)."""
    from finrobot.functional.fact_check import SourceIndex, run_fact_check
    history = history or []
    corpus = build_corpus()
    focus = tickers_in(question)
    if not focus and history:  # Rueckfrage ("Und bei Google?" / "Warum?") -> Firmen aus der letzten Frage
        focus = tickers_in(history[-1]["q"])
    hits = retrieve(question + (" " + history[-1]["q"] if history and not tickers_in(question) else ""), corpus,
                    focus=focus)
    src_txt = "\n\n".join(f"[{i}] {h['label']}\n{h['text']}" for i, h in enumerate(hits, 1)) or "(no sources found)"
    from . import agent_settings as _AS
    model = model or _AS.model("chat")
    msgs = [{"role": "system", "content": _AS.get("chat.system", SYSTEM)}]
    for h in history[-2:]:
        msgs += [{"role": "user", "content": h["q"]}, {"role": "assistant", "content": h["a"]}]
    msgs.append({"role": "user", "content": f"SOURCES:\n{src_txt}\n\nQUESTION: {question}"})
    t0 = time.time()
    raw, cost = (llm or call_llm)(msgs, model=model)
    text, actions = _parse_actions(raw)
    if not text.strip():
        raise RuntimeError("Das Modell hat nur eine Aktionszeile und keinen Antworttext geliefert. Bitte noch einmal fragen.")
    src = SourceIndex("[sources]")
    for i, h in enumerate(hits, 1):
        try:
            src.add_text(h["label"] + "\n" + h["text"], origin=f"[{i}] {h['label']}")
        except TypeError:
            src.add_text(h["label"] + "\n" + h["text"])
    fc = run_fact_check([("Answer", text)], [src], None)
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text) if 0 < int(n) <= len(hits)})
    res = {"question": question, "answer": text, "sources": hits, "cited": cited, "actions": actions,
           "fc": {"matched": fc["matched"], "total": fc["total_claims"], "claims": fc["claims"]},
           "cost": cost, "seconds": round(time.time() - t0, 1), "model": model, "focus": focus}
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "question": question, "answer": text,
                                "sources": [h["label"] for h in hits], "cited": cited, "actions": actions,
                                "fc_matched": fc["matched"], "fc_total": fc["total_claims"], "cost": cost,
                                "raw_chars": len(raw or ""),
                                "model": model}, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return res


def suggestions():
    """Vorschlaege fuer den Einstieg, aus dem aktuellen Brief."""
    out = []
    bj = sorted(glob.glob(str(RESEARCH / "briefs" / "brief_*.json")))
    b = _load(bj[-1]) if bj else {}
    pos = (b or {}).get("positions") or []
    dec = [p["ticker"] for p in pos if p.get("level") == "decide"]
    if dec:
        out.append(f"Why is {dec[0]} on Decide?")
    th = [p["ticker"] for p in pos if p.get("theses")]
    if th:
        out.append(f"How has free cash flow developed at {th[0]}?")
    out.append("Which position carries the most risk relative to its weight?")
    out.append("Which events are coming up in the next weeks?")
    return out[:4]


# =============================================================== Darstellung
def render_html(res):
    """Antwort als HTML: Zahlen markiert (gruen gefunden / rot nicht gefunden, Tooltip mit Quelle), Quellen als Marken."""
    from html import escape
    from finrobot.functional.fact_check import extract_claims
    from .html_site import _claims_index, _status, _tip
    by_key, by_text = _claims_index({"claims": res["fc"]["claims"]})
    labels = {i: h["label"] for i, h in enumerate(res["sources"], 1)}

    def line_html(line):
        spans, used = [], []
        for c in extract_claims(line):
            st, src, ev = _status(c, by_key, by_text)
            for m in re.finditer(r"(?<![\d.])" + re.escape(c["text"]) + r"(?!\d)", line):
                if any(not (m.end() <= a or m.start() >= b) for a, b in used):
                    continue
                used.append((m.start(), m.end()))
                spans.append((m.start(), m.end(), st, src, ev))
                break
        for m in re.finditer(r"\[(\d+)\]", line):
            if not any(not (m.end() <= a or m.start() >= b) for a, b in used):
                used.append((m.start(), m.end()))
                spans.append((m.start(), m.end(), "cite", m.group(1), None))
        spans.sort()
        out, pos = [], 0
        for a, b, st, src, ev in spans:
            out.append(escape(line[pos:a]))
            if st == "cite":
                lab = labels.get(int(src), "Quelle nicht in der Liste")
                out.append(f'<span class="cite" title="{escape(lab)}">{escape(src)}</span>')
            else:
                tip = escape(_tip(st, src, ev)).replace("\n", "&#10;")
                out.append(f'<span class="num {st}" tabindex="0" data-tip="{tip}">{escape(line[a:b])}</span>')
            pos = b
        out.append(escape(line[pos:]))
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", "".join(out))

    html, in_list = [], False
    for raw in res["answer"].splitlines():
        line = raw.strip()
        if not line:
            if in_list:
                html.append("</ul>")
                in_list = False
            continue
        if re.match(r"^[-*•]\s+", line):
            if not in_list:
                html.append("<ul>")
                in_list = True
            item = re.sub(r"^[-*•]\s+", "", line)
            html.append(f"<li>{line_html(item)}</li>")
        else:
            if in_list:
                html.append("</ul>")
                in_list = False
            html.append(f"<p>{line_html(line)}</p>")
    if in_list:
        html.append("</ul>")
    return "".join(html)
