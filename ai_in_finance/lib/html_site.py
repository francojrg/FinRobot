"""
Research-Dashboard als statische HTML-Seiten (ohne Server, im Browser oeffnen: reports/site/index.html).

- index.html: Weekly Brief (Action Board), Positionen mit Links zu ihren Reports, Liste aller Reports mit Faktencheck.
- je Report eine Seite mit den Texten des Agenten, jede Zahl markiert: gruen = im Faktencheck in den Quellen gefunden
  (Quelle als Tooltip), rot = nicht gefunden. Grundlage sind die *_build_args.json und *_factcheck.json, die jeder
  Agent neben seinem PDF ablegt; es wird nichts neu berechnet und kein Sprachmodell aufgerufen.
"""
import glob
import json
import os
import re
from collections import Counter
from datetime import date, datetime
from html import escape
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
REPORTS = AIF / "reports"
RESEARCH = AIF / "research"
SKIP_KEYS = {"ticker_symbol", "save_path", "save_dir", "filing_date", "fyear", "peer_tickers", "segment_data",
             "company_kpis", "statuses", "share_performance_image_path", "pe_eps_performance_image_path", "ticker"}
LEVEL_LABEL = {"decide": "Decision needed", "read": "Read up", "none": "No action"}

CSS = """
:root{--c:#0F4C5C;--g:#5A6472;--ok:#E3F3E8;--okb:#2D8A4E;--no:#FBE5E2;--nob:#B03A2E;--un:#EEF0F2;--cx:#FDF1D8;--cxb:#B9770E}
*{box-sizing:border-box}body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#1d2329;margin:0;
background:#f6f7f8;line-height:1.55}header{background:var(--c);color:#fff;padding:14px 28px;display:flex;
justify-content:space-between;align-items:center}header a{color:#fff}header .brand{font-weight:700;letter-spacing:.3px}
main{max-width:1060px;margin:0 auto;padding:22px 28px 60px}h1{color:var(--c);font-family:Georgia,serif;
margin:4px 0 6px;font-size:28px}h2{color:var(--c);font-family:Georgia,serif;font-size:19px;border-bottom:2px solid var(--c);
padding-bottom:3px;margin-top:30px}h3{font-size:15px;margin:16px 0 4px}.sub{color:var(--g);font-size:13px}
.card{background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:14px 18px;margin:12px 0}
table{border-collapse:collapse;width:100%;font-size:13.5px;background:#fff}th{background:var(--c);color:#fff;text-align:left;
padding:6px 8px;font-weight:600}td{padding:6px 8px;border-bottom:1px solid #e6e8eb;vertical-align:top}
tr:nth-child(even) td{background:#fafbfc}a{color:var(--c)}.lvl{font-weight:700;white-space:nowrap}
.decide{color:var(--nob)}.read{color:#B9770E}.none{color:var(--okb)}.num{border-radius:3px;padding:0 2px;cursor:help}
.num.ok{background:var(--ok);border-bottom:2px solid var(--okb)}.num.no{background:var(--no);border-bottom:2px solid var(--nob)}
.num.un{background:var(--un)}.num{position:relative}.num.ctx{background:var(--cx);border-bottom:2px dashed var(--cxb)}
.jt .num[data-tip]:hover::after,.jt .num[data-tip]:focus::after{display:none}
.rtip{position:fixed;z-index:9999;max-width:460px;background:#1d2329;color:#fff;font:12.5px/1.5 -apple-system,Segoe UI,Helvetica,
Arial,sans-serif;padding:9px 11px;border-radius:9px;box-shadow:0 8px 24px rgba(0,0,0,.22);pointer-events:none;display:none}
.rtip .h{font-weight:600;margin-bottom:4px}.rtip .q{color:#d9dee3}.rtip mark{background:#F5C451;color:#1d2329;border-radius:3px;
padding:0 2px}.rtip u{text-decoration-color:#7FC8A9;text-underline-offset:2px}.rtip .f{color:#9aa4ad;font-size:11.5px;margin-top:5px}
.num[data-tip]:hover::after,.num[data-tip]:focus::after{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 6px);
z-index:20;width:max-content;max-width:420px;white-space:pre-line;background:#1d2329;color:#fff;font:12.5px/1.45 -apple-system,
Segoe UI,Helvetica,Arial,sans-serif;padding:8px 10px;border-radius:8px;box-shadow:0 6px 20px rgba(0,0,0,.18);pointer-events:none}
.num.tr[data-tip]:hover::after,.num.tr[data-tip]:focus::after{left:auto;right:0}.legend span{margin-right:14px}.pill{display:inline-block;padding:1px 8px;border-radius:10px;
font-size:12px;background:#e8eef0;color:var(--c);margin-right:6px}.bar{height:8px;background:#e6e8eb;border-radius:4px;
overflow:hidden;width:120px;display:inline-block;vertical-align:middle;margin-right:6px}.bar i{display:block;height:100%;
background:var(--okb)}ul{margin:4px 0 8px 20px;padding:0}footer{color:var(--g);font-size:12px;margin-top:40px}
details summary{cursor:pointer;color:var(--c);font-weight:600}
"""


# =============================================================== Faktencheck-Markierung
def _claims_index(fc):
    by_key, by_text = {}, {}
    for c in fc.get("claims", []):
        ev = dict(c.get("evidence") or {})
        if c.get("context_ok") is False:          # Zahl steht in den Quellen, aber nicht im passenden Zusammenhang
            ev["ctx_mismatch"] = True
        v = (c.get("source"), ev or None)
        by_key[(c["text"], c.get("context", ""))] = v
        by_text.setdefault(c["text"], []).append(v)
    return by_key, by_text


def _status(c, by_key, by_text):
    """('ok'|'no'|'un', Quelle, Herkunft) fuer eine Zahl im Text."""
    k = (c["text"], c.get("context", ""))
    if k in by_key:
        src, ev = by_key[k]
        if src and ev and ev.get("ctx_mismatch"):
            return ("ctx", src, ev)
        return ("ok", src, ev) if src else ("no", None, None)
    vals = by_text.get(c["text"])
    if not vals:
        return ("un", None, None)
    found = [v for v in vals if v[0]]
    if len(found) == len(vals):
        src = Counter(v[0] for v in found).most_common(1)[0][0]
        ev = next((v[1] for v in found if v[0] == src and v[1]), None)
        if all((v[1] or {}).get("ctx_mismatch") for v in found):
            return ("ctx", src, ev)
        return ("ok", src, ev)
    if not found:
        return ("no", None, None)
    return ("un", None, None)


TIP_HEAD = {"ok": "Found in {src}", "ctx": "Figure appears in {src}, but in a different context - check",
            "no": "Not found in the sources the agent received - check manually (it may be a derived figure)",
            "un": "Not part of the fact check"}


def _tip_attrs(st, src, ev):
    """data-Attribute fuer den ausfuehrlichen Tooltip (TIP_JS): Kopfzeile, Textstelle, markierte Zahl, gemeinsame Woerter."""
    ev = ev or {}
    where = ev.get("origin") or src or ""
    head = TIP_HEAD[st].format(src=where + (f" ({src})" if ev.get("origin") and src else ""))
    a = [f'data-head="{escape(head)}"']
    if st in ("ok", "ctx") and ev.get("snippet"):
        a.append(f'data-snip="{escape(ev["snippet"][:320])}"')
        if ev.get("hl"):
            a.append(f'data-hl="{escape(ev["hl"])}"')
        if ev.get("context_words"):
            a.append(f'data-words="{escape("|".join(ev["context_words"][:4]))}"')
    return " ".join(a)


def _tip(st, src, ev):
    if st == "ctx":
        ev = ev or {}
        snip = ev.get("snippet")
        return TIP_HEAD["ctx"].format(src=ev.get("origin") or src) + (f"\n\u201c{snip[:260]}\u201d" if snip else "")
    if st == "ok":
        ev = ev or {}
        where = ev.get("origin") or src
        snip = ev.get("snippet")
        return f"Source: {where}" + (f" ({src})" if ev.get("origin") and src else "") + \
            (f"\n\u201c{snip[:260]}\u201d" if snip else "")
    if st == "no":
        return "Not found in the sources the agent received - check manually (it may be a derived figure)"
    return "Not part of the fact check"


def highlight(text, by_key, by_text):
    """Text als HTML; jede Zahl, die der Faktencheck erkennt, wird markiert (Tooltip: Quelle und Textstelle)."""
    from finrobot.functional.fact_check import extract_claims
    text = str(text or "")
    spans, used = [], []
    for c in extract_claims(text):
        st, src, ev = _status(c, by_key, by_text)
        pat = r"(?<![\d.])" + re.escape(c["text"]) + r"(?!\d)"
        for m in re.finditer(pat, text):
            if any(not (m.end() <= a or m.start() >= b) for a, b in used):
                continue
            used.append((m.start(), m.end()))
            spans.append((m.start(), m.end(), st, src, ev))
            break
    spans.sort()
    out, pos = [], 0
    for a, b, st, src, ev in spans:
        out.append(escape(text[pos:a]))
        tip = escape(_tip(st, src, ev)).replace("\n", "&#10;")
        out.append(f'<span class="num {st}" tabindex="0" data-tip="{tip}" {_tip_attrs(st, src, ev)}>{escape(text[a:b])}</span>')
        pos = b
    out.append(escape(text[pos:]))
    html = "".join(out)
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", html) if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paras)


def _label(k):
    return str(k).replace("_", " ").strip().capitalize()


def _render_value(v, by_key, by_text, depth=0):
    if isinstance(v, str):
        return highlight(v, by_key, by_text) if v.strip() else ""
    if isinstance(v, list):
        if all(isinstance(x, str) for x in v):
            return "<ul>" + "".join(f"<li>{highlight(x, by_key, by_text)}</li>" for x in v) + "</ul>"
        parts = []
        for i, x in enumerate(v, 1):
            if isinstance(x, dict):
                head = x.get("ticker") or x.get("thesis") or x.get("name") or f"Item {i}"
                body = "".join(f"<div><b>{escape(_label(k))}:</b> {_render_value(val, by_key, by_text, depth + 1)}</div>"
                               for k, val in x.items() if k not in SKIP_KEYS and k not in ("thesis",) and val)
                title = escape(str(head)[:160])
                parts.append(f'<div class="card"><h3>{title}</h3>{body}</div>' if x.get("thesis") or x.get("ticker")
                             else f'<div class="card">{body}</div>')
            else:
                parts.append(_render_value(x, by_key, by_text, depth + 1))
        return "".join(parts)
    if isinstance(v, dict):
        return "".join(f"<div><b>{escape(_label(k))}:</b> {_render_value(val, by_key, by_text, depth + 1)}</div>"
                       for k, val in v.items() if k not in SKIP_KEYS)
    return escape(str(v))


RICH_TIP_JS = r"""(function(root, host){
  var box=null, cur=null;
  function esc(s){return String(s).replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
  function words(seg, ws){ws.forEach(function(w){if(!w)return;var re=new RegExp('\\b('+w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'[a-z]*)','i');
    seg=seg.replace(re,'<u>$1</u>')});return seg}
  function show(n){
    if(!box){box=document.createElement('div');box.className='rtip';(host||document.body).appendChild(box)}
    var d=n.dataset, s=esc(d.snip||''), hl=d.hl?esc(d.hl):'', ws=(d.words||'').split('|');
    var i=hl?s.indexOf(hl):-1;
    if(!hl&&s){var t=esc(n.textContent.replace(/[$%x]/g,'').trim());i=t?s.indexOf(t):-1;hl=t}
    var body=i>=0?words(s.slice(0,i),ws)+'<mark>'+hl+'</mark>'+words(s.slice(i+hl.length),ws):words(s,ws);
    box.innerHTML='<div class="h">'+esc(d.head||d.tip||'')+'</div>'+(s?'<div class="q">\u201c'+body+'\u201d</div>':'')+
      (d.words?'<div class="f">matching context: '+esc(d.words.split('|').join(', '))+'</div>':'');
    box.style.display='block';
    var r=n.getBoundingClientRect(), bw=box.offsetWidth, bh=box.offsetHeight, vw=window.innerWidth, vh=window.innerHeight;
    var x=Math.min(Math.max(8,r.left),vw-bw-8), y=r.bottom+8; if(y+bh>vh-8)y=Math.max(8,r.top-bh-8);
    box.style.left=x+'px';box.style.top=y+'px';cur=n}
  function hide(){if(box)box.style.display='none';cur=null}
  (document.documentElement||root).classList.add('jt'); if(root.classList)root.classList.add('jt');
  root.addEventListener('mouseover',function(e){var n=e.target.closest&&e.target.closest('.num[data-head]');if(n&&n!==cur)show(n);else if(!n&&cur)hide()});
  root.addEventListener('focusin',function(e){var n=e.target.closest&&e.target.closest('.num[data-head]');if(n)show(n)});
  root.addEventListener('focusout',hide);window.addEventListener('scroll',hide,true);
})"""
TIP_JS = "<script>" + RICH_TIP_JS + "(document, document.body);</script>"


def _page(title, body, sub=""):
    return (f"<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{escape(title)}</title><style>{CSS}</style></head><body>"
            f"<header><span class='brand'>Franci's FINRobot</span><span><a href='index.html'>Dashboard</a> &nbsp; "
            f"<a href='portfolio.html'>Portfolio</a></span></header>"
            f"<main><h1>{escape(title)}</h1><div class='sub'>{sub}</div>{body}<footer>Generated by Franci's FINRobot on "
            f"{datetime.now():%Y-%m-%d %H:%M} - for academic purposes only, not investment advice.</footer></main>{TIP_JS}</body></html>")


def _rate(fc):
    if not fc or not fc.get("total_claims"):
        return "n/a", None
    r = fc["matched"] / fc["total_claims"]
    return f"{fc['matched']} of {fc['total_claims']} ({r * 100:.0f}%)", r


def _bar(r):
    return f"<span class='bar'><i style='width:{(r or 0) * 100:.0f}%'></i></span>" if r is not None else ""


def report_page(rep, out_dir):
    """Eine Report-Seite mit markierten Zahlen; gibt den Dateinamen zurueck."""
    args = json.load(open(rep["args"], encoding="utf-8"))
    fc = json.load(open(rep["factcheck"], encoding="utf-8")) if rep.get("factcheck") and Path(rep["factcheck"]).exists() else {}
    by_key, by_text = _claims_index(fc)
    rate, r = _rate(fc)
    n_ctx = sum(1 for c in fc.get("claims", []) if c.get("source") and c.get("context_ok") is False)
    body = [f"<div class='card legend'><span class='num ok'>green</span> figure found in the sources (hover: source and the exact "
            f"passage, figure highlighted) &nbsp; <span class='num ctx'>amber</span> figure appears in the sources, but in a "
            f"different context &nbsp; <span class='num no'>red</span> not found &nbsp; <span class='num un'>grey</span> not part of "
            f"the check<br><span class='sub'>Fact check: {_bar(r)}{rate} figures found"
            + (f", {n_ctx} of them only as a number without matching context" if n_ctx else "") + "."
            + (f" Self-correction rounds: {fc.get('build_round')}." if fc.get("build_round") else "")
            + (f" Recomputed offline with source origins (at build time: {fc['original']['matched']} of "
               f"{fc['original']['total_claims']})." if fc.get("original") else "") + "</span>"
            + (f" &nbsp; <a href='{escape(rep['pdf_rel'])}'>Open the PDF</a>" if rep.get("pdf_rel") else "") + "</div>"]
    for k, v in args.items():
        if k in SKIP_KEYS or k.endswith("_path") or v in (None, "", [], {}):
            continue
        html = _render_value(v, by_key, by_text)
        if html:
            body.append(f"<h2>{escape(_label(k))}</h2>{html}")
    un = fc.get("unmatched") or []
    if un:
        rows = "".join(f"<tr><td>{escape(str(u.get('section', '')))}</td><td><span class='num no'>{escape(u['text'])}</span>"
                       f"</td><td>{escape(str(u.get('context', '')))}</td></tr>" for u in un)
        body.append(f"<h2>Figures not found in the sources</h2><details open><summary>{len(un)} figures</summary>"
                    f"<table><tr><th>Section</th><th>Figure</th><th>Context</th></tr>{rows}</table></details>")
    name = rep["slug"] + ".html"
    sub = f"{escape(rep['agent'])} | {escape(rep['date'])}"
    (out_dir / name).write_text(_page(rep["title"], "".join(body), sub), encoding="utf-8")
    return name


# =============================================================== Reports finden
def _newest(pattern):
    files = glob.glob(str(pattern))
    return max(files, key=os.path.getmtime) if files else None


def _rep(args, agent, title, slug, pdf_suffix, out_dir, ticker=None):
    base = args[: -len("_build_args.json")]
    pdf = base + pdf_suffix if Path(base + pdf_suffix).exists() else None
    if pdf is None:
        pdfs = glob.glob(str(Path(args).parent / "*.pdf"))
        pdf = max(pdfs, key=os.path.getmtime) if pdfs else None
    return {"args": args, "factcheck": base + "_factcheck.json", "agent": agent, "title": title, "slug": slug,
            "ticker": ticker, "date": date.fromtimestamp(os.path.getmtime(args)).isoformat(),
            "pdf_rel": os.path.relpath(pdf, out_dir).replace("\\", "/") if pdf else None}


def find_reports(tickers, out_dir, portfolio_name=None):
    reps = []
    for t in tickers:
        sym = t.split(".")[0] if "." in t and not t.endswith((".US",)) else t
        sym = sym.upper()
        ann = [p for p in glob.glob(str(REPORTS / f"{sym}_*" / "*build_args.json"))
               if re.match(rf"{re.escape(sym)}_\d{{4}}_", Path(p).parent.name)]
        if ann:
            a = max(ann, key=os.path.getmtime)
            fy = re.match(rf"{re.escape(sym)}_(\d{{4}})_", Path(a).parent.name).group(1)
            reps.append(_rep(a, "Annual report agent", f"{sym} Annual Report FY{fy}", f"{sym}_annual", ".pdf", out_dir, t))
        er = _newest(REPORTS / f"{sym}_earnings_multi_*" / "*_build_args.json") or \
            _newest(REPORTS / f"{sym}_earnings_*" / "*_build_args.json")
        if er:
            reps.append(_rep(er, "Earnings reviewer", f"{sym} Earnings & Thesis Update", f"{sym}_earnings", ".pdf",
                             out_dir, t))
    nd = _newest(REPORTS / "news_*" / "*_news_digest_build_args.json")
    if nd:
        reps.append(_rep(nd, "News tracker", "Weekly News Digest", "news_digest", ".pdf", out_dir))
    if portfolio_name:
        pr = _newest(REPORTS / f"portfolio_{portfolio_name}_*" / f"{portfolio_name}_portfolio_review_build_args.json")
        if pr:
            reps.append(_rep(pr, "Portfolio manager", "Portfolio Review", "portfolio_review", ".pdf", out_dir))
    br = _newest(REPORTS / "brief_*" / "brief_*_build_args.json")
    if br:
        reps.append(_rep(br, "Briefing agent", "Weekly Brief", "weekly_brief", ".pdf", out_dir))
    return reps


def _brief_recheck(rep):
    """Aeltere Briefs ohne Herkunftsangaben: Faktencheck offline neu rechnen (eigene Datei, Original bleibt)."""
    try:
        fc = json.load(open(rep["factcheck"], encoding="utf-8")) if Path(rep["factcheck"]).exists() else {}
        if any(c.get("evidence") for c in fc.get("claims", [])):
            return
        stem = Path(rep["args"]).name[: -len("_build_args.json")]
        bj = RESEARCH / "briefs" / f"{stem}.json"
        if not bj.exists():
            return
        from .brief_agent import recheck_brief
        out = rep["args"][: -len("_build_args.json")] + "_factcheck_recheck.json"
        new = recheck_brief(bj, rep["args"])
        new["original"] = {"matched": fc.get("matched"), "total_claims": fc.get("total_claims")}
        json.dump(new, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        rep["factcheck"] = out
    except Exception as e:
        print(f"Faktencheck des Briefs nicht neu berechnet: {e}")


# =============================================================== Startseite
def build_site(tickers=None, out_dir=None, portfolio_name=None):
    """Erzeugt reports/site/index.html und je Report eine Seite; gibt den Pfad der Startseite zurueck."""
    out_dir = Path(out_dir or REPORTS / "site")
    out_dir.mkdir(parents=True, exist_ok=True)
    snap = RESEARCH / "portfolio_snapshot.json"
    snap = json.load(open(snap, encoding="utf-8")) if snap.exists() else {}
    portfolio_name = portfolio_name or snap.get("name")
    br_json = _newest(RESEARCH / "briefs" / "brief_*.json")
    brief = json.load(open(br_json, encoding="utf-8")) if br_json else None
    positions = (brief or {}).get("positions") or []
    tickers = list(dict.fromkeys(list(tickers or []) + [p["ticker"] for p in positions]))
    reps = find_reports(tickers, out_dir, portfolio_name)
    for r in reps:
        if r["slug"] == "weekly_brief":
            _brief_recheck(r)
    pages = {}
    for r in reps:
        try:
            pages[r["slug"]] = report_page(r, out_dir)
        except Exception as e:
            print(f"Seite fuer {r['title']} nicht erzeugt: {e}")
    try:  # Report-Archiv: jeder Annual Report / jedes Earnings Review bleibt mit Datum erhalten
        from .company_data import archive_reports
        added = archive_reports()
        if added:
            print(f"Archiv: {len(added)} Report(s) neu abgelegt")
    except Exception as e:
        print(f"Archiv nicht aktualisiert: {e}")
    body = []
    port = None
    try:
        port = build_portfolio_page(out_dir)
    except Exception as e:
        print(f"Portfolio-Dashboard nicht erzeugt: {e}")
    if port:
        body.append(f"<div class='card'><b><a href='{port}'>Portfolio dashboard</a></b> <span class='sub'>performance vs "
                    f"MSCI ACWI, attribution, positions with the research view of all agents, structure, risk, "
                    f"optimisation, decisions</span></div>")
    btexts = {}
    if brief:
        bp = _newest(REPORTS / "brief_*" / "brief_*_build_args.json")
        btexts = json.load(open(bp, encoding="utf-8")) if bp else {}
        n = Counter(p["level"] for p in positions)
        head = escape(btexts.get("headline") or "Weekly brief")
        body.append(f"<div class='card'><b>{head}</b><br><span class='sub'>As of {escape(brief['date'])}: "
                    f"{n.get('decide', 0)} decision needed, {n.get('read', 0)} read up, {n.get('none', 0)} no action"
                    + (f" | <a href='{pages['weekly_brief']}'>Brief with sources</a>" if "weekly_brief" in pages else "")
                    + "</span>" + (f"<p>{escape(btexts['summary'])}</p>" if btexts.get("summary") else "") + "</div>")
        items = {str(x.get("ticker", "")).upper(): x for x in btexts.get("items") or []}
        rows = []
        for p in positions:
            t = p["ticker"]
            sym = (t.split(".")[0] if "." in t else t).upper()
            links = " ".join(f"<a href='{pages[s]}'>{lab}</a>" for s, lab in ((f"{sym}_annual", "Annual report"),
                                                                              (f"{sym}_earnings", "Earnings review"))
                             if s in pages) or "<span class='sub'>no agent research</span>"
            why = "<br>".join(escape(x["text"]) for x in p.get("triggers", [])[:4]) or "<span class='sub'>no trigger</span>"
            it = items.get(t.upper())
            nxt = f"<div class='sub'><b>Next step:</b> {escape(it['next_step'])}</div>" if it and it.get("next_step") else ""
            w = f"{p['weight'] * 100:.1f}%" if isinstance(p.get("weight"), (int, float)) else "n/a"
            rows.append(f"<tr><td><b>{escape(t)}</b></td><td>{w}</td><td class='lvl {p['level']}'>"
                        f"{LEVEL_LABEL.get(p['level'], p['level'])}</td><td>{why}{nxt}</td><td>{links}</td></tr>")
        body.append("<h2>Action board</h2><table><tr><th>Position</th><th>Weight</th><th>Level</th><th>Why (rule-based "
                    "triggers)</th><th>Research</th></tr>" + "".join(rows) + "</table><div class='sub'>Levels are set "
                    "by fixed rules from the outputs of the other agents, not by the language model.</div>")
        if brief.get("gaps"):
            body.append("<h2>Data gaps</h2><ul>" + "".join(f"<li>{escape(g)}</li>" for g in brief["gaps"]) + "</ul>")
    rows = []
    for r in reps:
        fc = json.load(open(r["factcheck"], encoding="utf-8")) if Path(r["factcheck"]).exists() else {}
        rate, rr = _rate(fc)
        view = f"<a href='{pages[r['slug']]}'>View with sources</a>" if r["slug"] in pages else ""
        pdf = f" | <a href='{escape(r['pdf_rel'])}'>PDF</a>" if r.get("pdf_rel") else ""
        rows.append(f"<tr><td><b>{escape(r['title'])}</b></td><td>{escape(r['agent'])}</td><td>{escape(r['date'])}</td>"
                    f"<td>{_bar(rr)}{rate}</td><td>{view}{pdf}</td></tr>")
    body.append("<h2>Reports</h2><table><tr><th>Report</th><th>Agent</th><th>Date</th><th>Fact check (figures found)</th>"
                "<th>Open</th></tr>" + "".join(rows) + "</table>")
    body.append("<h2>How to read this</h2><div class='card sub'>Each report page shows the agent's text with every figure "
                "marked: green = found in the sources the agent was given (hover to see which), red = not found, grey = "
                "not part of the fact check. The fact check catches about 60-68% of deliberately falsified figures in a "
                "test, so green is evidence, not proof. The PDFs are the formatted versions of the same reports.</div>")
    sub = f"As of {date.today().isoformat()}" + (f" | portfolio: {escape(snap.get('title') or portfolio_name)}"
                                                if portfolio_name else "")
    idx = out_dir / "index.html"
    idx.write_text(_page("Research Dashboard", "".join(body), sub), encoding="utf-8")
    print(f"Dashboard: {idx} ({len(pages)} Report-Seiten)")
    return str(idx)


# =============================================================== Portfolio-Dashboard: Daten (schreibt der Portfolio Manager)
PORTFOLIO_DATA = RESEARCH / "portfolio_dashboard.json"


def _clean(x):
    """JSON-taugliche Kopie (numpy, pandas, NaN)."""
    import math
    import numpy as np
    import pandas as pd
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, pd.Series):
        return {str(k.date() if hasattr(k, "date") else k): _clean(v) for k, v in x.items()}
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return None if (math.isnan(x) or math.isinf(x)) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (pd.Timestamp, date, datetime)):
        return str(x.date() if hasattr(x, "date") and not isinstance(x, date) else x)[:10]
    if isinstance(x, np.ndarray):
        return [_clean(v) for v in x.tolist()]
    return x


def _weekly(s):
    import pandas as pd
    if s is None or not isinstance(s, pd.Series) or s.empty:
        return None
    w = s.dropna()
    cut = w.index[-1] - pd.DateOffset(days=120)          # letzte ~4 Monate taeglich (fuer 1M/YTD im Chart), davor woechentlich
    w = pd.concat([w[w.index < cut].resample("W-FRI").last().dropna(), w[w.index >= cut]])
    w = w[~w.index.duplicated(keep="last")].sort_index()
    return {"dates": [str(d.date()) for d in w.index], "values": [round(float(v), 6) for v in w.values]}


def save_portfolio_data(a, bt=None, perf=None, research=None, name="portfolio", title="Portfolio", path=None):
    """Alles fuer das Portfolio-Dashboard: Analyse (Bestand, Risiko, Optimierung), Backtest, echte Performance und
    die Research-Sicht der anderen Agenten."""
    path = Path(path or PORTFOLIO_DATA)
    tick = list(a.get("tickers") or [])
    d = {"date": a.get("date"), "name": name, "title": title, "cap": a.get("cap"), "sector_cap": a.get("sector_cap"),
         "rf": a.get("rf"), "years_hist": a.get("years_hist"),
         "positions": a.get("positions"), "structure": a.get("structure"), "stats": a.get("stats"),
         "bench_stats": a.get("bench_stats"), "stress": a.get("stress"), "opt_stats": a.get("opt_stats"),
         "opt_weights": {k: dict(zip(tick, [float(x) for x in v])) for k, v in (a.get("opt") or {}).items()},
         "curve_port": _weekly(a.get("port_curve")), "curve_bench": _weekly(a.get("bench_curve")),
         "research": research or {}}
    if bt:
        d["backtest"] = {"start": bt.get("start"), "end": bt.get("end"), "stats": bt.get("stats"),
                         "curves": {k: _weekly(v) for k, v in (bt.get("curves") or {}).items()}}
    if perf:
        d["performance"] = {
            k: perf.get(k) for k in ("mode", "start", "end", "years", "ttwror", "ttwror_pa", "mwr", "bench_tw",
                                     "bench_tw_pa", "bench_mwr", "final_value", "bench_final_value", "net_invested",
                                     "never_sold", "periods", "calendar_years", "positions", "decisions", "max_dd",
                                     "n_trades", "fees_total", "dividends_total", "attribution", "costs", "exits",
                                     "mistakes", "warnings", "transactions")}
        d["performance"]["curves"] = {"value": _weekly(perf.get("value")), "invested": _weekly(perf.get("invested")),
                                      "ttwror": _weekly(perf.get("ttwror_curve")), "bench": _weekly(perf.get("bench_curve")),
                                      "never_sold": _weekly(perf.get("ns_curve")),
                                      "bench_value": _weekly(perf.get("bench_value"))}
    path.parent.mkdir(parents=True, exist_ok=True)
    json.dump(_clean(d), open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return str(path)


# =============================================================== Portfolio-Dashboard: Seite
PORTFOLIO_JS = r"""
const C={c:'#0F4C5C',g:'#9AA5B1',ok:'#2D8A4E',no:'#B03A2E',a:'#B9770E',pal:['#0F4C5C','#2D8A4E','#B9770E','#5B7DB1','#8E5572','#7A9E3B','#C46A3A','#4FA3A5','#A3A3A3','#6C5B7B','#D4A017','#3B6E8F']};
const pct=(x,d=1)=>x==null?'n/a':(x*100).toFixed(d)+'%';
const pp=(x,d=1)=>x==null?'n/a':((x>=0?'+':'')+(x*100).toFixed(d)+'%');
const eur=x=>x==null?'n/a':'EUR '+Math.round(x).toLocaleString('en-US');
const num=(x,d=2)=>x==null?'n/a':Number(x).toFixed(d);
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
Chart.defaults.font.family='-apple-system,Segoe UI,Helvetica,Arial,sans-serif';Chart.defaults.font.size=11;
Chart.defaults.plugins.legend.labels.boxWidth=12;
function line(id,series,opt={}){const el=document.getElementById(id);if(!el)return;
 new Chart(el,{type:'line',data:{labels:series[0].d.dates,datasets:series.map((s,i)=>({label:s.l,data:s.d.values.map(v=>s.f?s.f(v):v),
 borderColor:s.c||C.pal[i],backgroundColor:s.c||C.pal[i],borderWidth:s.w||1.8,pointRadius:0,borderDash:s.dash||[],tension:.15}))},
 options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
 scales:{x:{ticks:{maxTicksLimit:8}},y:{ticks:{callback:opt.y||(v=>v)}}},plugins:{tooltip:{callbacks:{label:c=>c.dataset.label+': '+(opt.t?opt.t(c.raw):c.raw)}}}}});}
function bars(id,labels,sets,opt={}){const el=document.getElementById(id);if(!el)return;
 new Chart(el,{type:'bar',data:{labels,datasets:sets.map((s,i)=>({label:s.l,data:s.v,backgroundColor:s.c||C.pal[i]}))},
 options:{indexAxis:opt.h?'y':'x',responsive:true,maintainAspectRatio:false,plugins:{legend:{display:sets.length>1},
 tooltip:{callbacks:{label:c=>(sets.length>1?c.dataset.label+': ':'')+(opt.t?opt.t(c.raw):c.raw)}}},
 scales:{[opt.h?'x':'y']:{ticks:{callback:opt.y||(v=>v)}}}}});}
function donut(id,obj){const el=document.getElementById(id);if(!el||!obj)return;const k=Object.keys(obj);
 new Chart(el,{type:'doughnut',data:{labels:k,datasets:[{data:k.map(x=>obj[x]),backgroundColor:C.pal}]},
 options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'right'},tooltip:{callbacks:{label:c=>c.label+': '+pct(c.raw)}}}}});}
function table(id,head,rows){const el=document.getElementById(id);if(!el)return;
 el.innerHTML='<table><tr>'+head.map(h=>'<th>'+h+'</th>').join('')+'</tr>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</table>';}
const P=D.performance, S=D.stats||{}, ST=D.structure||{};
// KPI-Kacheln
const k=[];
if(P){k.push(['Portfolio value',eur(P.final_value)],['Net invested',eur(P.net_invested)],
 ['TTWROR p.a. vs MSCI ACWI',pct(P.ttwror_pa)+' <span class=s>vs '+pct(P.bench_tw_pa)+'</span>'],
 ['Money-weighted (MWR) vs ACWI',pct(P.mwr)+' <span class=s>vs '+pct(P.bench_mwr)+'</span>'],['Max drawdown (realised)',pct(P.max_dd)]);
 if(P.costs)k.push(['Turnover / fees (12m)',pct(P.costs.turnover)+' / '+eur(P.costs.fees)]);}
k.push(['Sharpe / beta (3y, today\'s weights)',num(S.sharpe)+' / '+num(S.beta)],['Positions / effective number',(D.positions||[]).length+' / '+num(ST.effective_n,1)],
 ['Top five positions',pct(ST.top5)]);
document.getElementById('kpi').innerHTML=k.map(x=>'<div class=kpi><div class=kl>'+x[0]+'</div><div class=kv>'+x[1]+'</div></div>').join('');
// Performance
if(P&&P.curves&&P.curves.value){
 line('c_value',[{l:'Portfolio value',d:P.curves.value,c:C.c},{l:'Same cash flows in MSCI ACWI',d:P.curves.bench_value,c:C.g},
  {l:'Net invested',d:P.curves.invested,c:C.a,dash:[4,3],w:1.4}],{y:v=>Math.round(v/1000)+'k',t:v=>eur(v)});
 line('c_tw',[{l:'Portfolio (TTWROR)',d:P.curves.ttwror,c:C.c,f:v=>v*100-100},{l:'MSCI ACWI',d:P.curves.bench,c:C.g,f:v=>v*100-100}],
  {y:v=>v.toFixed(0)+'%',t:v=>v.toFixed(1)+'%'});
 table('t_periods',['Period','Portfolio (TTWROR)','MSCI ACWI','Difference','MWR'],(P.periods||[]).map(r=>[r.period+(r.annualized?' p.a.':''),pct(r.ttwror),pct(r.bench),
  '<b style="color:'+(r.diff>=0?C.ok:C.no)+'">'+pp(r.diff)+'</b>',pct(r.mwr)]));
 const cy=P.calendar_years||[];bars('c_years',cy.map(r=>r.period),[{l:'Portfolio',v:cy.map(r=>r.ttwror),c:C.c},{l:'MSCI ACWI',v:cy.map(r=>r.bench),c:C.g}],{y:v=>pct(v,0),t:v=>pct(v)});
 const at=(P.attribution||[]).filter(r=>r.contribution!=null);
 bars('c_attr',at.map(r=>r.ticker),[{l:'Contribution',v:at.map(r=>r.contribution),c:at.map(r=>r.contribution<0?C.no:C.ok)}],{h:1,y:v=>pct(v,1),t:v=>pct(v,2)});
 const ns=P.never_sold;if(ns)document.getElementById('ns').innerHTML='Counterfactual "never sold": TTWROR '+pct(ns.ttwror)+' vs actual '+pct(ns.actual_ttwror)+
  '; MWR '+pct(ns.mwr)+' vs actual '+pct(ns.actual_mwr)+'.';
 const ex=P.exits||[];table('t_exits',['Position','Held','Invested','Total P/L','IRR','Stock vs ACWI (held)','After sale vs ACWI'],ex.map(e=>['<b>'+esc(e.ticker)+'</b>',e.first_buy+' to '+e.last_sell,eur(e.invested),
  eur(e.total_pl),pct(e.irr),pct(e.stock_held)+' vs '+pct(e.acwi_held),e.stock_after==null?'n/a':pct(e.stock_after)+' vs '+pct(e.acwi_after)]));
 const mk=P.mistakes||[];table('t_mist',['Decision','Amount','Stock vs ACWI','Value lost','Type','Rationale at the time'],mk.map(d=>[d.date+' <b>'+d.type+'</b> '+esc(d.ticker),eur(d.eur),
  pct(d.ret_stock)+' vs '+pct(d.ret_bench),eur(-d.impact_eur),esc(d.kind),esc(d.note||'not recorded')]));
 const dec=(P.decisions||[]).slice().sort((a,b)=>b.impact_eur-a.impact_eur);const top=dec.slice(0,5);
 table('t_best',['Decision','Amount','Stock vs ACWI','Value added'],top.map(d=>[d.date+' <b>'+d.type+'</b> '+esc(d.ticker),eur(d.eur),pct(d.ret_stock)+' vs '+pct(d.ret_bench),eur(d.impact_eur)]));
}else{document.querySelectorAll('.needperf').forEach(e=>e.style.display='none');}
// Positionen mit Research-Sicht
const R=D.research||{};const pos=(D.positions||[]).slice().sort((a,b)=>b.weight-a.weight);
const rs=t=>{const v=R[t];if(!v)return['<span class=s>-</span>','<span class=s>-</span>','<span class=s>-</span>'];
 const th=v.thesis_status?Object.entries(v.thesis_status).map(([s,n])=>'<span class="st '+s+'">'+n+' '+s+'</span>').join(' '):'-';
 const f=v.forecast?v.forecast.direction+' '+v.forecast.low+'-'+v.forecast.high+'%':'-';
 const nw=(v.news_flags||[]).slice(0,2).map(esc).join('<br>')||'-';
 const cm=v.committee&&v.committee.recommendation?' | committee: '+v.committee.recommendation:'';return[th,nw,f+cm];};
table('t_pos',['Position','Sector','Weight','Risk share','1y return','Volatility','Fwd P/E','Analyst upside','Thesis status','News signals','Forecast'],
 pos.map(p=>{const r=rs(p.ticker);return['<b>'+esc(p.ticker)+'</b><br><span class=s>'+esc(p.name)+'</span>',esc(p.sector),pct(p.weight),
 '<span style="color:'+(p.risk_contrib>1.3*p.weight?C.no:'inherit')+'">'+pct(p.risk_contrib)+'</span>',pct(p.ret_1y),pct(p.vol),num(p.forward_pe,1),pct(p.upside),r[0],r[1],r[2]];}));
bars('c_risk',pos.map(p=>p.ticker),[{l:'Weight',v:pos.map(p=>p.weight),c:C.c},{l:'Share of risk',v:pos.map(p=>p.risk_contrib),c:C.a}],{y:v=>pct(v,0),t:v=>pct(v)});
if(D.cap)document.getElementById('capnote').innerHTML='Position limit '+pct(D.cap,0)+', sector limit '+pct(D.sector_cap,0)+'. Risk share in red: more than 1.3x the weight.';
// Struktur
donut('c_sector',ST.sector);donut('c_ccy',ST.currency);
// Risiko
const sx=D.stress||[];bars('c_stress',sx.map(s=>s.scenario),[{l:'Portfolio (today\'s weights)',v:sx.map(s=>s.portfolio),c:C.c},{l:'MSCI ACWI',v:sx.map(s=>s.benchmark),c:C.g}],{y:v=>pct(v,0),t:v=>pct(v)});
const B=(D.bench_stats||{})['MSCI ACWI']||{};
table('t_stats',['3 years, today\'s weights','Portfolio','MSCI ACWI'],[['CAGR',pct(S.cagr),pct(B.cagr)],['Volatility',pct(S.vol),pct(B.vol)],['Sharpe',num(S.sharpe),num(B.sharpe)],
 ['Sortino',num(S.sortino),num(B.sortino)],['Max drawdown',pct(S.max_dd),pct(B.max_dd)],['Beta / tracking error',num(S.beta)+' / '+pct(S.tracking_error),'1.00 / -'],['1-day VaR 95%',pct(S.var95_1d,2),pct(B.var95_1d,2)]]);
if(D.curve_port)line('c_hist',[{l:'Portfolio (today\'s weights)',d:D.curve_port,c:C.c,f:v=>v*100-100},{l:'MSCI ACWI',d:D.curve_bench,c:C.g,f:v=>v*100-100}],{y:v=>v.toFixed(0)+'%',t:v=>v.toFixed(1)+'%'});
// Optimierung und Backtest
const BT=D.backtest;if(BT&&BT.curves){const ks=Object.keys(BT.curves).filter(k=>BT.curves[k]);
 line('c_bt',ks.map((k,i)=>({l:k,d:BT.curves[k],c:k.startsWith('MSCI')?C.g:C.pal[i],f:v=>v*100-100,dash:k.startsWith('MSCI')?[4,3]:[]})),{y:v=>v.toFixed(0)+'%',t:v=>v.toFixed(1)+'%'});
 table('t_bt',['Strategy','CAGR','Volatility','Sharpe','Max drawdown','Turnover p.a.'],ks.map(k=>{const s=BT.stats[k]||{};return[esc(k),pct(s.cagr),pct(s.vol),num(s.sharpe),pct(s.max_dd),s.turnover_pa==null?'-':pct(s.turnover_pa,0)];}));}
const OW=D.opt_weights||{};const om=['current','min_variance','max_sharpe','hrp','equal_weight'].filter(m=>OW[m]);
const on={current:'Current',min_variance:'Min variance',max_sharpe:'Max Sharpe',hrp:'HRP',equal_weight:'Equal weight'};
table('t_opt',['Position'].concat(om.map(m=>on[m])),pos.map(p=>['<b>'+esc(p.ticker)+'</b>'].concat(om.map(m=>pct(OW[m][p.ticker])))).concat(
 [['<b>Expected return / volatility</b>'].concat(om.map(m=>{const s=(D.opt_stats||{})[m]||{};return pct(s.exp_return)+' / '+pct(s.vol);}))]));
"""

PORTFOLIO_CSS = """.kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px;margin:14px 0}
.kpi{background:#fff;border:1px solid #e1e4e8;border-radius:8px;padding:10px 12px}.kl{font-size:11.5px;color:var(--g)}
.kv{font-size:18px;font-weight:700;color:var(--c);margin-top:2px}.kv .s,.s{font-size:12px;color:var(--g);font-weight:400}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.chart{position:relative;height:290px;background:#fff;
border:1px solid #e1e4e8;border-radius:8px;padding:10px}.chart.tall{height:340px}.cap{font-size:12.5px;color:var(--g);margin:4px 0 0}
.st{display:inline-block;padding:0 6px;border-radius:8px;font-size:11.5px;margin:1px;background:#eef0f2}.st.broken{background:#FBE5E2;color:#B03A2E}
.st.weakened{background:#FDF0DC;color:#9A6408}.st.intact{background:#E3F3E8;color:#2D8A4E}.st.strengthened{background:#DDEFE4;color:#1F6B3A}
@media(max-width:800px){.grid{grid-template-columns:1fr}}"""


def build_portfolio_page(out_dir, data_path=None):
    """reports/site/portfolio.html aus research/portfolio_dashboard.json (Charts mit Chart.js)."""
    data_path = Path(data_path or PORTFOLIO_DATA)
    if not data_path.exists():
        return None
    d = json.load(open(data_path, encoding="utf-8"))
    has_perf = bool(d.get("performance"))
    perf = d.get("performance") or {}
    sub = (f"As of {escape(str(d.get('date')))} | {escape(str(d.get('title') or d.get('name')))} | base currency EUR | "
           f"benchmark MSCI ACWI" + (f" | history since {escape(str(perf.get('start')))}" if has_perf else
                                     " | no transaction history: performance uses today's weights"))
    body = f"""
<div class='kpis' id='kpi'></div>
<h2 class='needperf'>Performance of the actual portfolio</h2>
<div class='grid needperf'><div class='chart'><canvas id='c_value'></canvas></div><div class='chart'><canvas id='c_tw'></canvas></div></div>
<p class='cap needperf'>Left: portfolio value against the money paid in and against the same cash flows invested in the MSCI ACWI.
Right: time-weighted return (TTWROR), which removes the effect of deposits and withdrawals.</p>
<div class='grid needperf'><div id='t_periods'></div><div class='chart'><canvas id='c_years'></canvas></div></div>
<p class='cap needperf' id='ns'></p>
<h2 class='needperf'>Attribution, last 12 months</h2>
<div class='chart tall needperf'><canvas id='c_attr'></canvas></div>
<p class='cap needperf'>Contribution of each position to the portfolio result in % of the average portfolio value (detractors red).</p>
<h2>Positions and research view</h2>
<div id='t_pos'></div><p class='cap' id='capnote'></p>
<div class='chart'><canvas id='c_risk'></canvas></div>
<p class='cap'>Weight vs share of portfolio risk (contribution to volatility). Thesis status from the earnings reviewer, news
signals from the news tracker, forecast from the weekly forecaster (low reliability).</p>
<h2>Structure</h2>
<div class='grid'><div class='chart'><canvas id='c_sector'></canvas></div><div class='chart'><canvas id='c_ccy'></canvas></div></div>
<h2>Risk</h2>
<div class='grid'><div id='t_stats'></div><div class='chart'><canvas id='c_hist'></canvas></div></div>
<div class='chart' style='margin-top:14px'><canvas id='c_stress'></canvas></div>
<p class='cap'>Stress tests: today's portfolio in past market shocks, against the MSCI ACWI.</p>
<h2>Optimisation and backtest (model view)</h2>
<div class='chart tall'><canvas id='c_bt'></canvas></div><div id='t_bt'></div>
<h3>Target weights by method</h3><div id='t_opt'></div>
<p class='cap'>Long-only, with position and sector limits. Model outputs are sensitive to estimation error; the walk-forward
backtest shows how each method would have done out of sample.</p>
<h2 class='needperf'>Decisions</h2>
<h3 class='needperf'>Exits</h3><div class='needperf' id='t_exits'></div>
<h3 class='needperf'>Mistakes and lessons (weakest decisions vs MSCI ACWI)</h3><div class='needperf' id='t_mist'></div>
<h3 class='needperf'>Best decisions</h3><div class='needperf' id='t_best'></div>
<script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'></script>
<script>const D={json.dumps(d, ensure_ascii=False)};{PORTFOLIO_JS}</script>"""
    html = _page("Portfolio Dashboard", body, sub).replace("</style>", PORTFOLIO_CSS + "</style>", 1)
    out = Path(out_dir) / "portfolio.html"
    out.write_text(html, encoding="utf-8")
    return out.name
