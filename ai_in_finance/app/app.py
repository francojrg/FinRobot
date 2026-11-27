"""
BLUMBÖRG - App von Franci's FINRobot (Streamlit). Start: start.bat (Windows) oder `streamlit run ai_in_finance/app/app.py`.
Portfolio-Datei hochladen -> Plan und Kosten ansehen -> kompletter Lauf aller Agenten -> Dashboard mit Reitern.
"""
import json
import os
import sys
import time
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

AIF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AIF))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import app_backend as ab  # noqa: E402


def _reload_changed_libs():
    """Geaenderte Dateien aus lib/ und die Ansichten (app/*_view.py) neu laden (Streamlit behaelt importierte Module sonst
    bis zum Neustart im Speicher; sonst passen z. B. neue Ausloeser einer Komponente nicht zur alten Ansicht)."""
    import importlib
    import os
    import lib
    seen = getattr(lib, "_loaded_mtimes", {})
    views = ["home_view", "company_view", "portfolio_view", "news_view", "brief_view"]   # home_view zuerst (CSS)
    mods = sorted(sys.modules.items(), key=lambda kv: (kv[0] not in views, views.index(kv[0]) if kv[0] in views else 0))
    for name, mod in mods:
        f = getattr(mod, "__file__", None)
        if not (name.startswith("lib.") or name in views) or not f:
            continue
        try:
            m = os.path.getmtime(f)
        except OSError:
            continue
        if name in seen and m > seen[name]:
            try:
                importlib.reload(mod)
            except Exception as ex:  # neue Datei fehlerhaft: alte Version behalten, Hinweis zeigen
                st.toast(f"{name} could not be reloaded: {ex}")
        seen[name] = m
    lib._loaded_mtimes = seen


_reload_changed_libs()
ab.register_keys()                                   # SEC User-Agent usw. auch fuer Abrufe direkt in der App

_ICON = Path(__file__).parent / "assets" / "blumboerg.png"
st.set_page_config(page_title="BLUMBÖRG", page_icon=str(_ICON) if _ICON.exists() else "📈", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600&family=IBM+Plex+Sans:wght@400;500&display=swap');
.lvl-decide{color:#B03A2E;font-weight:700}.lvl-read{color:#B9770E;font-weight:700}.lvl-none{color:#2D8A4E;font-weight:700}
table.fr{border-collapse:collapse;width:100%;font-size:calc(16.5px*var(--bfs,1))}table.fr th{color:rgba(128,128,128,1);font-weight:500;text-align:left;
padding:7px 8px;border-bottom:1px solid rgba(128,128,128,.3)}table.fr td{padding:7px 8px;border-bottom:1px solid rgba(128,128,128,.15);vertical-align:top}
.small{color:rgba(128,128,128,1);font-size:calc(16px*var(--bfs,1))}
.block-container{padding-top:2.6rem;max-width:none;padding-left:2.2rem;padding-right:2.2rem}
@keyframes rvIn{0%{max-height:0;opacity:0;clip-path:inset(0 0 100% 0 round 14px);transform:perspective(1400px) rotateX(-14deg) translateY(-10px)}
 30%{opacity:1}100%{max-height:1300px;opacity:1;clip-path:inset(0 0 0 0 round 14px);transform:none}}
@keyframes rvOut{0%{max-height:1300px;opacity:1;clip-path:inset(0 0 0 0 round 14px);transform:none}
 60%{opacity:.9}100%{max-height:0;opacity:0;clip-path:inset(0 0 100% 0 round 14px);transform:perspective(1400px) rotateX(-14deg) translateY(-10px)}}
[class*="st-key-rv_"]{animation:rvIn .85s cubic-bezier(.45,0,.2,1) backwards;transform-origin:top center;overflow:hidden;will-change:max-height,clip-path,transform}
[class*="st-key-rvx_"]{animation:rvOut .55s cubic-bezier(.55,0,.75,.3) forwards;transform-origin:top center;overflow:hidden;will-change:max-height,clip-path,transform}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:14px}
.ui-h{margin:0 0 4px}.ui-h h1{font-size:calc(25px*var(--bfs,1));font-weight:600;margin:0;padding:0;letter-spacing:-.01em}
.ui-sub{color:rgba(128,128,128,1);font-size:calc(16px*var(--bfs,1));margin:2px 0 14px}
.ui-step{display:flex;gap:10px;align-items:center;margin:0 0 6px}.ui-step b{font-size:calc(18px*var(--bfs,1));font-weight:600}
.ui-num{width:24px;height:24px;border-radius:50%;background:rgba(55,138,221,.14);color:#378ADD;font-weight:600;display:flex;
align-items:center;justify-content:center;font-size:calc(15.5px*var(--bfs,1));flex:none}
.ui-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:6px 0 10px}
.ui-kpi{background:rgba(128,128,128,.08);border-radius:12px;padding:11px 14px}.ui-kpi .l{font-size:calc(15.5px*var(--bfs,1));color:rgba(128,128,128,1)}
.ui-kpi .v{font-size:calc(24px*var(--bfs,1));font-weight:600;margin-top:2px}.ui-kpi .s{font-size:calc(15px*var(--bfs,1));color:rgba(128,128,128,1)}
.ui-pill{display:inline-block;font-size:calc(14.5px*var(--bfs,1));padding:2px 9px;border-radius:999px;background:rgba(128,128,128,.12);margin:0 4px 4px 0}
.ui-pill.ok{background:rgba(29,158,117,.14);color:#1D9E75}.ui-pill.no{background:rgba(226,75,74,.14);color:#E24B4A}
.ui-pill.run{background:rgba(55,138,221,.14);color:#378ADD}.ui-pill.wait{background:rgba(239,159,39,.16);color:#BA7517}
.ui-plan{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;margin:6px 0 10px}
.ui-pcard{border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:11px 13px}
.ui-pcard .t{font-weight:600}.ui-pcard .m{font-size:calc(15.5px*var(--bfs,1));color:rgba(128,128,128,1);margin-top:3px}
.ui-tl{border-left:2px solid rgba(128,128,128,.25);margin:6px 0 6px 8px;padding-left:16px}
.ui-tli{position:relative;padding:6px 0}.ui-tli:before{content:"";position:absolute;left:-23px;top:11px;width:12px;height:12px;
border-radius:50%;background:rgba(128,128,128,.35);border:2px solid var(--background-color,#fff)}
.ui-tli.ok:before{background:#1D9E75}.ui-tli.no:before{background:#E24B4A}.ui-tli.run:before{background:#378ADD}
.ui-tli .m{font-size:calc(15.5px*var(--bfs,1));color:rgba(128,128,128,1)}
.ui-bar{display:flex;flex-direction:column;gap:8px;font-size:calc(15.5px*var(--bfs,1));color:rgba(128,128,128,1);padding:4px 2px}
[data-testid="stSidebarNav"]::before{content:"";display:block;width:112px;height:112px;margin:0 auto 1.4rem;background:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='9' fill='%230e2238'/><rect x='6.5' y='6.5' width='51' height='51' fill='none' stroke='%23b89a5a' stroke-width='1.8'/><rect x='11' y='11' width='42' height='42' fill='none' stroke='%23b89a5a' stroke-width='.8'/><text x='32' y='44' text-anchor='middle' font-family='Cormorant Garamond,Georgia,serif' font-weight='600' font-size='37' fill='%23d8c08a'>B</text></svg>") center/contain no-repeat}
[data-testid="stMainBlockContainer"]{padding-top:0 !important}
[data-testid="stElementContainer"]:has([data-testid="stMarkdownContainer"] > style:only-child){display:none}
[data-testid="stHeader"]{background:transparent !important;height:62px;z-index:5}
[data-testid="stAppDeployButton"]{display:none !important}
[data-testid="stToolbar"] button,[data-testid="stToolbar"] [data-testid="stMainMenu"] *{color:#e9e1cf !important}
[data-testid="stStatusWidget"]{color:#e9e1cf}
.bh{margin:0 -2.2rem 1.4rem;background:light-dark(#0e2238,#262420);color:#f3ecdc;font-family:"IBM Plex Sans",system-ui,sans-serif}
.bh-top{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;min-height:62px;box-sizing:border-box;padding:8px calc(2.2rem + 48px) 8px 2.2rem;border-bottom:1px solid light-dark(#b89a5a,#8f7a4c)}
.bh-wm{font-family:"Cormorant Garamond",Georgia,serif;font-weight:600;font-size:calc(34px*var(--bfs,1));letter-spacing:.34em;line-height:1;padding-left:.34em;color:#f3ecdc;text-align:center;white-space:nowrap}
.bh-l,.bh-r{font-size:calc(12px*var(--bfs,1));letter-spacing:.16em;text-transform:uppercase;color:#b89a5a}.bh-r{text-align:right}
.bt{display:flex;flex-wrap:wrap;gap:4px 22px;align-items:center;padding:7px 2.2rem;background:light-dark(#0a1a2c,#1f1d1a);font-size:calc(13.5px*var(--bfs,1));color:#d5dbe3;font-variant-numeric:tabular-nums}
.bh-demo{border:1px solid #b89a5a;color:#e2c98f;padding:2px 8px;border-radius:4px;letter-spacing:.18em}
.bt-l{color:#b89a5a;letter-spacing:.06em;margin-right:3px}.bt .up{color:#4cc38a}.bt .dn{color:#f07a7a}
.bt-a{margin-left:auto;color:light-dark(#7d8a9b,#8d877c);font-size:calc(12px*var(--bfs,1))}
@media (max-width:900px){.bh-l{display:none}.bh-wm{font-size:calc(24px*var(--bfs,1))}}
.st-key-ag_sel [role="radiogroup"]{gap:6px;display:flex;flex-direction:column;align-items:stretch}
.st-key-ag_sel [role="radiogroup"] label{border:1px solid rgba(128,128,128,.28);border-radius:10px;padding:10px 12px;margin:0;width:100% !important;max-width:none;box-sizing:border-box}
.st-key-ag_sel [role="radiogroup"] label:has(input:checked){border-color:#b89a5a;background:rgba(184,154,90,.10)}
.st-key-ag_sel [role="radiogroup"] label p{font-size:calc(17px*var(--bfs,1)) !important;font-weight:500}
.ag-info{border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:6px 16px;margin:4px 0 14px}
.ag-info .r{display:grid;grid-template-columns:130px minmax(0,1fr);gap:14px;padding:9px 0;border-top:1px solid rgba(128,128,128,.18);font-size:calc(16px*var(--bfs,1));line-height:1.5}
.ag-info .r:first-child{border-top:0}.ag-info .r b{font-weight:600}
.ii{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;border:1px solid rgba(128,128,128,.45);
color:rgba(128,128,128,1);font:italic 600 11px/1 Georgia,serif;margin-left:7px;cursor:help;position:relative;vertical-align:2px}
.ii:hover::after{content:attr(data-tip);position:absolute;left:50%;top:calc(100% + 7px);transform:translateX(-50%);width:max-content;max-width:320px;
white-space:normal;background:#1d2329;color:#fff;font:400 calc(14px*var(--bfs,1))/1.45 system-ui,sans-serif;padding:8px 11px;border-radius:8px;z-index:999;
box-shadow:0 6px 20px rgba(0,0,0,.2);text-align:left}
.beta-b{display:inline-block;font-size:calc(14px*var(--bfs,1));font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#B9770E;
background:rgba(239,159,39,.15);border:1px solid rgba(239,159,39,.35);border-radius:6px;padding:0 6px;margin-left:10px;
vertical-align:5px;line-height:18px;cursor:help}
[data-testid="stStatusWidgetRunningManIcon"]{display:none !important}
[data-testid="stStatusWidgetRunningIcon"]::before{content:"💶";font-size:calc(25px*var(--bfs,1));line-height:1;display:inline-block;
animation:blumb-run 3s steps(1,end) infinite}
@keyframes blumb-run{0%{content:"💶"}16.6%{content:"📈"}33.3%{content:"💰"}50%{content:"🏦"}66.6%{content:"💹"}83.3%{content:"🚀"}}
[data-testid="stSidebarNavItems"]{padding-top:0;max-height:none}
[data-testid="stSidebarNavLink"]{padding:.62rem .95rem !important;border-radius:10px !important;margin:3px 0 !important;min-height:46px;gap:.75rem}
[data-testid="stSidebarNavLink"] span[label],[data-testid="stSidebarNavLink"] p,[data-testid="stSidebarNavLink"] div{font-size:calc(19.5px*var(--bfs,1)) !important;line-height:1.3}
[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"]{font-size:calc(27px*var(--bfs,1)) !important}
[data-testid="stSidebarNavLink"]:hover{background:rgba(128,128,128,.12) !important}
[data-testid="stSidebar"]{min-width:305px}
[data-testid="stNavSectionHeader"]{font-size:calc(15.5px*var(--bfs,1)) !important;font-weight:500 !important;color:rgba(128,128,128,1) !important;
text-transform:none !important;letter-spacing:0 !important;padding:.9rem .95rem .2rem !important}
.ui-ckh{display:flex;justify-content:space-between;align-items:center;margin:0 0 4px}.ui-ckh b{font-size:calc(18px*var(--bfs,1));font-weight:600}
.ui-ck{display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-top:1px solid rgba(128,128,128,.15)}
.ui-ck .ico{width:20px;height:20px;border-radius:50%;border:1.5px solid rgba(128,128,128,.5);flex:none;margin-top:1px;
display:flex;align-items:center;justify-content:center;font-size:calc(15px*var(--bfs,1))}
.ui-ck.ok .ico{background:#1D9E75;border-color:#1D9E75;color:#fff}.ui-ck .m{font-size:calc(15.5px*var(--bfs,1));color:rgba(128,128,128,1)}
.ui-ck.ok b{font-weight:500}
</style>""", unsafe_allow_html=True)
_UI = ab.load_ui()
_FS = ab.FONT_SCALES.get(_UI["font"], 1.0)          # Schriftgroesse aus den Einstellungen (Normal = 18 px Grundschrift)
st.markdown(f"<style>:root{{--bfs:{_FS}}} html{{font-size:{18 * _FS:.2f}px !important}}</style>", unsafe_allow_html=True)

LEVEL = {"decide": "Decision needed", "read": "Read up", "none": "No action needed"}
STEP_ICON = {"annual_report": "Annual Report", "quarter_review": "Quarter Records", "earnings_review": "Earnings Review", "committee": "Investment Committee",
             "forecast": "Forecast (Beta)", "preview": "Earnings Preview (Beta)", "news": "News Tracker", "portfolio": "Portfolio Manager", "brief": "Weekly Brief"}


def html_table(head, rows):
    h = "".join(f"<th>{c}</th>" for c in head)
    b = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    st.markdown(f"<table class='fr'><tr>{h}</tr>{b}</table>", unsafe_allow_html=True)


def current_tickers():
    data, _ = ab.latest_brief()
    if data:
        return [p["ticker"] for p in data.get("positions", [])]
    lr = ab.latest_run()
    if lr:
        return json.load(open(ab.RUNS / f"{lr}.json", encoding="utf-8")).get("tickers", [])
    return []


def go(key):
    """Seite wechseln (Navigation oben)."""
    st.switch_page(PAGE_OBJ[key])


BETA_BADGE = ("<span class='beta-b' title='Beta: results not yet systematically validated'>Beta</span>")


def ui_header(title, sub="", beta=False):
    st.markdown(f"<div class='ui-h'><h1>{escape(title)}{BETA_BADGE if beta else ''}</h1></div>"
                + (f"<div class='ui-sub'>{sub}</div>" if sub else ""), unsafe_allow_html=True)


def ui_kpis(items):
    st.markdown("<div class='ui-kpis'>" + "".join(
        f"<div class='ui-kpi'><div class='l'>{escape(l)}</div><div class='v'>{v}</div><div class='s'>{s_}</div></div>"
        for l, v, s_ in items) + "</div>", unsafe_allow_html=True)


def brand_header():
    """Kopfzeile auf jeder Seite: Wortmarke mittig, Datum, darunter die Index-Leiste (Yahoo, 15 Min. Cache)."""
    from lib import market_strip as ms
    try:
        items, asof = ms.quotes()
    except Exception:
        items, asof = [], None
    today = date.today().strftime("%a %d %b %Y")
    left = "Research · Portfolio"
    try:
        from lib import portfolios as pf
        a = pf.active()
        if a and a["kind"] == "demo":
            left = "<span class='bh-demo'>DEMO PORTFOLIO</span>"
        elif a:
            left = escape(a["name"])
    except Exception:
        pass
    st.markdown(f"<div class='bh'><div class='bh-top'><span class='bh-l'>{left}</span>"
                f"<span class='bh-wm'>BLUMBÖRG</span><span class='bh-r'>{today}</span></div>"
                f"{ms.html(items, asof) if items else ''}</div>", unsafe_allow_html=True)


def portfolio_switcher():
    """Aktives Portfolio in der Seitenleiste waehlen. Wechsel ohne neuen Lauf: Firmen-Reports werden geteilt,
    Brief/Review/Dashboard je Portfolio gesichert; fehlt ein Dashboard, rechnet Python es neu (kein Modellaufruf)."""
    from lib import portfolios as pf
    try:
        d = pf.load()
    except Exception as ex:
        st.sidebar.caption(f"Portfolios not available: {ex}")
        return
    ids = [x["id"] for x in d["items"]]
    names = {x["id"]: x["name"] for x in d["items"]}
    cur = d.get("active") if d.get("active") in ids else None
    with st.sidebar:
        if st.session_state.get("pf_err"):
            st.error(st.session_state.pop("pf_err"))
        sel = st.selectbox("Portfolio", ids, index=ids.index(cur) if cur else 0, format_func=lambda i: names[i],
                           key=f"pf_switch_{cur}_{st.session_state.get('pf_v', 0)}",
                           help="Switch between your portfolios and the DEMO portfolio. Company reports are shared; "
                                "brief, review and dashboard are kept per portfolio.")
    if sel == cur:
        return
    try:
        with st.spinner(f"Switching to {names[sel]} …"):
            restored = pf.switch(sel)
        if not restored:
            with st.spinner("Calculating value, risk and structure for this portfolio (about a minute, no model call) …"):
                pf.prepare(sel)
    except Exception as ex:
        st.session_state["pf_err"] = f"Switch failed: {ex}"
        st.session_state["pf_v"] = st.session_state.get("pf_v", 0) + 1
    st.cache_data.clear()
    st.rerun()


def portfolios_section():
    """Gespeicherte Portfolios verwalten: umbenennen, entfernen, zusammenfassen."""
    from lib import portfolios as pf
    d = pf.load()
    ui_header("Portfolios", "Your saved portfolios and the DEMO portfolio. Company reports are shared between portfolios, "
                            "so switching or combining never re-runs them – only brief, portfolio review and news digest "
                            "are per portfolio.")
    for x in d["items"]:
        files = [Path(f).name for f in (x.get("transaction_files") or []) + (x.get("holdings_files") or [])] + \
            ([Path(x["portfolio_file"]).name] if x.get("portfolio_file") else [])
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1.2, 1])
            tag = {"demo": "<span class='ui-pill run'>DEMO</span>", "combined": "<span class='ui-pill'>combined</span>"}.get(x["kind"], "")
            act = " <span class='ui-pill ok'>active</span>" if x["id"] == d.get("active") else ""
            c1.markdown(f"**{escape(x['name'])}** {tag}{act}<br><span class='small'>{escape(', '.join(files) or '–')}"
                        f"{' · last run ' + escape(str(x.get('last_run'))[:16].replace('T', ' ')) if x.get('last_run') else ''}"
                        f"{' · ' + escape(x['note']) if x.get('note') else ''}</span>", unsafe_allow_html=True)
            if x["kind"] != "demo":
                nn = c2.text_input("Name", x["name"], key=f"pf_name_{x['id']}", label_visibility="collapsed")
                if nn != x["name"] and c2.button("Rename", key=f"pf_ren_{x['id']}"):
                    pf.rename(x["id"], nn)
                    st.rerun()
                if x["id"] != d.get("active") and c3.button("Remove", key=f"pf_del_{x['id']}", icon=":material/delete:",
                                                             help="Removes it from the list; files and company reports stay."):
                    pf.delete(x["id"])
                    st.rerun()
    own = [x for x in d["items"] if x["kind"] != "demo" and (x.get("transaction_files") or x.get("holdings_files"))]
    with st.container(border=True):
        st.markdown("**Combine portfolios** <span class='small'>· e.g. Trade Republic + Scalable as one portfolio; "
                    "transactions are merged, the same holding is added up, deposits and withdrawals are counted together</span>",
                    unsafe_allow_html=True)
        if len(own) < 2:
            st.caption("You need at least two of your own portfolios with transactions or share counts. Upload them under "
                       "Analysis first (each run saves its portfolio here).")
            return
        pick = st.multiselect("Portfolios", [x["id"] for x in own], format_func=lambda i: next(x["name"] for x in own if x["id"] == i),
                              label_visibility="collapsed", placeholder="Choose two or more portfolios")
        name = st.text_input("Name of the combined portfolio", " + ".join(next(x["name"] for x in own if x["id"] == i) for i in pick))
        if st.button("Create combined portfolio", type="primary", disabled=len(pick) < 2):
            try:
                pid = pf.combine(pick, name)
                st.success(f"Created “{pf.get(pid)['name']}”. Choose it in the sidebar to see it, or start an analysis for it "
                           "(only brief, review and missing companies run).")
            except Exception as ex:
                st.error(str(ex))


def status_bar():
    """Kleine Statuszeile oben rechts: laufende Analyse, fehlender Schluessel, Hinweis."""
    parts = []
    lr = ab.latest_run()
    if lr:
        stt = ab.run_status(lr)
        if stt["alive"]:
            parts.append(f"<span class='ui-pill run'>Analysis running since {stt['cfg']['started'][11:16]}</span>")
    if not ab.load_settings()["openrouter"]:
        parts.append("<span class='ui-pill wait'>No OpenRouter key – see Settings</span>")
    parts.append("<span>For academic purposes only, not investment advice</span>")
    with st.sidebar:
        st.markdown("<div class='ui-bar'>" + "".join(parts) + "</div>", unsafe_allow_html=True)


# =============================================================== Einrichtung und Automatik
def page_run():
    if "setup_tab_next" in st.session_state:          # von anderen Seiten gewuenschter Bereich
        st.session_state["setup_tab"] = st.session_state.pop("setup_tab_next")
    if not st.session_state.get("setup_tab"):
        st.session_state["setup_tab"] = "Analysis"
    tab = st.segmented_control("Section", ["Analysis", "Portfolios", "Automation"], key="setup_tab",
                               label_visibility="collapsed")
    if tab == "Automation":
        page_automation()
    elif tab == "Portfolios":
        portfolios_section()
    else:
        _page_analysis()


AUTO_DAYS = {1: "daily", 2: "every 2 days", 7: "weekly", 14: "every 2 weeks", 30: "monthly"}
RESULT_DE = {"gestartet": "run started", "nichts": "nothing due", "aus": "off",
             "uebersprungen": "skipped", "fehler": "error"}


def _last_portfolio_run():
    """Letzter App-Lauf mit dem ganzen Portfolio (keine Einzelfirma, keine Automatik)."""
    files = sorted(ab.RUNS.glob("*.json"), reverse=True) if ab.RUNS.exists() else []
    for f in files:
        if f.name.endswith("_done.json"):
            continue
        try:
            c = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not c.get("label") and not c.get("automation") and c.get("tickers"):
            return f.stem
    return None


def page_automation():
    from datetime import time as dtime
    from lib import automation as au
    ui_header("Automation", "The agents run by themselves as soon as something is due: news and forecasts on a schedule, annual report "
              "and earnings review as soon as new results are filed with the SEC. A Windows task checks daily and after "
              "login; Windows catches up on missed checks. The monthly budget caps the costs.")
    cfg = au.load_config()
    on = bool(cfg.get("enabled"))
    inst = au.task_installed() if on else False
    spent, hist = au.month_spend(), au.history(20)
    last = hist[0] if hist else None
    nxt = au.next_check(cfg["time"]) if on else None
    ui_kpis([("Status", "on" if inst else ("on, task missing" if on else "off"), "Windows Task Scheduler"),
             ("Next check", nxt.strftime("%d %b %H:%M") if nxt else "–", "and after every login"),
             (f"Budget {date.today().strftime('%b %Y')}", f"${spent:.2f} / ${float(cfg['budget_usd'] or 0):.0f}",
              "app runs and chat"),
             ("Last check", RESULT_DE.get(last["result"], last["result"]) if last else "–",
              last["ts"][:16].replace("T", " ") if last else "none yet")])
    with st.container(border=True):
        st.markdown("<div class='ui-step'><span class='ui-num'>1</span><b>Portfolio</b></div>", unsafe_allow_html=True)
        src = cfg.get("source") or {}
        lr = _last_portfolio_run()
        if src.get("tickers"):
            st.markdown("".join(f"<span class='ui-pill'>{escape(t)}</span>" for t in src["tickers"]) +
                        f"<div class='small'>{len(src['tickers'])} holdings · taken from the run of "
                        f"{escape('.'.join(reversed(str(src.get('from_run', ''))[:10].split('-'))))}</div>", unsafe_allow_html=True)
        else:
            st.caption("No portfolio yet – start a run under Analysis once, then take it over here.")
        wt = au.watch_tickers(cfg, src.get("tickers") or [])
        if wt:
            st.markdown("<div class='small'>Watchlist: " + "".join(f"<span class='ui-pill'>{escape(t)}</span>" for t in wt)
                        + "</div>", unsafe_allow_html=True)
        if lr and lr != src.get("from_run") and st.button("Take over portfolio from last run", icon=":material/sync:"):
            cfg["source"] = au.source_from_run(lr)
            au.save_config(cfg)
            st.rerun()
    with st.form("auto_form"):
        st.markdown("<div class='ui-step'><span class='ui-num'>2</span><b>Agents and schedule</b></div>", unsafe_allow_html=True)
        n_t = len(src.get("tickers") or []) or 1
        agents = {}
        for k, name, kind, _, d in au.AGENTS:
            a = cfg["agents"].get(k, {})
            c1, c2, c3 = st.columns([1.3, 1.2, 2])
            a_on = c1.toggle(name, value=bool(a.get("on")), key=f"au_on_{k}")
            days = None
            if kind == "takt":
                cur = int(a.get("days") or d)
                opts = sorted(set(AUTO_DAYS) | {cur})
                days = c2.selectbox("Schedule", opts, index=opts.index(cur), key=f"au_d_{k}", label_visibility="collapsed",
                                    format_func=lambda x: AUTO_DAYS.get(x, f"every {x} days"))
            else:
                c2.markdown(f"<div class='small' style='padding-top:9px'>{escape(au.EVENT_TEXT[k])}</div>",
                            unsafe_allow_html=True)
            per = au.est_usd(k, n_t) * (n_t if k in ("forecast", "annual_report", "earnings_review", "committee") else 1)
            note = (f"approx. ${au.est_usd(k, n_t):.2f} per holding" if k in ("annual_report", "earnings_review", "committee")
                    else f"approx. ${per:.2f} per run")
            if k == "committee":
                note += " · up to 60 min per holding; runs after new results or when the last vote is older than the schedule"
            c3.markdown(f"<div class='small' style='padding-top:9px'>{note}</div>", unsafe_allow_html=True)
            agents[k] = {"on": a_on, "days": days}
        bon = st.checkbox("Also run Weekly Brief and Portfolio Review after new quarterly results or an annual report",
                          value=bool(cfg.get("brief_on_new_numbers", True)))
        w1, w2 = st.columns(2)
        wl_on = w1.checkbox("Include watchlist (news and calendar)", value=bool(cfg.get("watchlist", True)),
                            help="Stocks from the watchlist on the Portfolio page")
        wl_res = w2.checkbox("Also annual report and earnings review for the watchlist", value=bool(cfg.get("watchlist_research")),
                             help="About $0.13 per stock and new 10-K or quarterly filing")
        st.markdown("<div class='ui-step' style='margin-top:10px'><span class='ui-num'>3</span><b>Time, budget, model</b></div>",
                    unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        hh, mm = (int(x) for x in cfg["time"].split(":"))
        tm = c1.time_input("Daily check at", value=dtime(hh, mm), step=900)
        bud = c2.number_input("Monthly budget (USD)", min_value=0.0, value=float(cfg["budget_usd"] or 0), step=1.0,
                              help="0 = no limit. Counts all app runs and chat questions of the current month.")
        models = ab.load_settings()["models"] or ["anthropic/claude-haiku-5.5"]
        mdl = c3.selectbox("Model", models, index=models.index(cfg["model"]) if cfg.get("model") in models else 0)
        b1, b2, _ = st.columns([1.3, 1, 3])
        save = b1.form_submit_button("Save" if on else "Save and switch on", type="primary")
        off = b2.form_submit_button("Switch off") if on else False
    if save or off:
        cfg.update(agents=agents, brief_on_new_numbers=bon, time=tm.strftime("%H:%M"), budget_usd=bud, model=mdl,
                   watchlist=wl_on, watchlist_research=wl_res)
        if off:
            ok, msg = au.remove_task()
            cfg["enabled"] = False
            au.save_config(cfg)
            st.toast("Automation switched off")
            st.rerun()
        if not (cfg.get("source") or {}).get("tickers"):
            au.save_config(cfg)
            st.error("First take over a portfolio under 1.")
        else:
            ok, msg = au.install_task(cfg["time"])
            cfg["enabled"] = ok
            au.save_config(cfg)
            if ok:
                st.toast("Automation switched on")
                st.rerun()
            st.error(f"Windows task not created: {msg}")
    with st.container(border=True):
        st.markdown("<div class='ui-step'><span class='ui-num'>4</span><b>Preview and test</b></div>", unsafe_allow_html=True)
        c1, c2, _ = st.columns([1.2, 1.2, 3])
        if c1.button("What would be due now?", icon=":material/visibility:"):
            with st.spinner("Checking SEC filings and last runs …"):
                try:
                    st.session_state["auto_due"] = au.due()
                except Exception as ex:
                    st.error(f"Preview failed: {ex}")
        if c2.button("Check and start now", icon=":material/play_arrow:"):
            with st.spinner("Checking what is due …"):
                r = au.tick(force=True)
            if r.get("result") == "gestartet":
                st.session_state["setup_tab_next"] = "Analysis"
                st.session_state.pop("auto_due", None)
                st.rerun()
            st.info(f"No run started: {RESULT_DE.get(r.get('result'), r.get('result'))}"
                    + (f" ({r['why']})" if r.get("why") else "")
                    + ". Automation only starts what is due on its schedule. For an immediate analysis choose "
                      "“Analysis” above; single companies under Company research → “Rebuild reports”.")
        d = st.session_state.get("auto_due")
        if d:
            if not d["steps"]:
                st.caption("Nothing is due right now." + (f" Reason: {d['reason']}" if d.get("reason") else ""))
            else:
                ui_kpis([("Due", str(len(d["steps"])), "Steps"), ("Cost", f"approx. ${d['usd']:.2f}", "estimate"),
                         ("Budget left", f"{d['left']:.2f} USD" if d.get("left") is not None else "no limit", "this month")])
                st.markdown("<div class='ui-plan'>" + "".join(
                    f"<div class='ui-pcard'><div class='t'>{escape(STEP_ICON.get(x['step'], x['step']))}</div>"
                    f"<div class='m'>{escape(x['ticker'])}</div><div class='m'>{escape(str(x['reason']))[:140]}</div></div>"
                    for x in d["steps"]) + "</div>", unsafe_allow_html=True)
            if d.get("dropped"):
                st.caption("Deferred because of the budget: " + ", ".join(f"{STEP_ICON.get(x['step'], x['step'])} {x['ticker']}"
                                                                         for x in d["dropped"]))
    if hist:
        with st.expander(f"Last checks ({len(hist)})"):
            html_table(["Time", "Result", "Steps", "Note"], [
                [escape(h["ts"][:16].replace("T", " ")), escape(RESULT_DE.get(h["result"], h["result"])),
                 escape(", ".join(h.get("steps") or [])[:160]),
                 escape((h.get("why") or "") + (f" · deferred: {', '.join(h['dropped'])}" if h.get("dropped") else ""))[:160]]
                for h in hist])


def _page_analysis():
    lr = ab.latest_run()
    if lr and ab.run_status(lr)["alive"]:
        ui_header("Analysis running", "The agents keep working in the background, even if you switch or close the page.")
        progress(lr)
        return
    ui_header("Start analysis", "Choose a portfolio, check the plan, start – annual reports, earnings reviews, forecasts, "
                                 "news, portfolio review and weekly brief run one after another in the background.")
    with st.container(border=True):
        st.markdown("<div class='ui-step'><span class='ui-num'>1</span><b>Choose portfolio</b></div>", unsafe_allow_html=True)
        c1, c2 = st.columns([1.2, 1])
        with c1:
            from lib import portfolios as pf
            src = st.segmented_control("Source", ["Saved portfolio", "Existing file", "Upload file"],
                                       default="Saved portfolio", label_visibility="collapsed")
            path, saved = None, None
            if src == "Saved portfolio":
                its = pf.items()
                act = pf.active()
                ids = [x["id"] for x in its]
                sid = st.selectbox("Portfolio", ids, index=ids.index(act["id"]) if act and act["id"] in ids else 0,
                                   format_func=lambda i: next(x["name"] for x in its if x["id"] == i),
                                   label_visibility="collapsed")
                saved = pf.get(sid)
            elif src == "Upload file":
                up = st.file_uploader("Upload CSV", type=["csv"], label_visibility="collapsed")
                if up:
                    path = ab.save_upload(up.name, up.getvalue())
            else:
                files = ab.sample_files()
                if files:
                    nice = {"sample_transactions_vfc_filed.csv": "Model portfolio Valley Forge, rebuilt from 13F filings (transactions)",
                            "sample_transactions_vfc_quarter.csv": "Model portfolio Valley Forge, quarter-end (transactions)",
                            "sample_portfolio_vfc.csv": "Model portfolio Valley Forge (13F Q3 2026, weights only)",
                            "sample_portfolio.csv": "Model portfolio Big Tech and Europe (14 stocks)",
                            "sample_transactions.csv": "Model transactions (with portfolio history)"}
                    path = st.selectbox("File", files, label_visibility="collapsed",
                                        format_func=lambda p: nice.get(p.name, p.name))
        with c2:
            st.markdown("<div class='small'><b>Formats</b><br>Weights <code>ticker,weight</code> · share counts "
                        "<code>ticker,shares</code> (also with semicolons, German number format, columns such as Gewicht or "
                        "Stück, ISIN instead of ticker) · broker exports (Trade Republic, Scalable, Smartbroker). With "
                        "transactions the app also shows portfolio value, return vs. the MSCI ACWI, contributions and "
                        "your decisions.</div>", unsafe_allow_html=True)
        if not path and not saved:
            return
        try:
            if saved:
                info = saved_info_cached(saved["id"], json.dumps(saved, sort_keys=True))
                path = saved["id"]
            else:
                info = inspect_cached(str(path), Path(path).stat().st_mtime)
        except Exception as e:
            st.error(f"File not readable: {e}")
            return
        kind = {"weights": "Weights", "shares": "Share counts", "transactions": "Transactions"}[info["kind"]]
        ui_kpis([("Detected as", kind, saved["name"] if saved else Path(path).name), ("Positions", str(len(info["positions"])), "in the file")]
                + ([("Bookings", str(info.get("n_bookings")), "buys, sells, dividends")] if info.get("n_bookings") else []))
        for x in info["issues"][:5]:
            st.caption(f"Note: {x}")
        pos = info["positions"]
        if pos:
            with st.expander("View positions"):
                cols = list(pos[0].keys())
                fmt = lambda v: "" if v is None else (f"{v:,.4g}" if isinstance(v, float) else escape(str(v)))
                html_table([escape(str(c)) for c in cols], [[fmt(r.get(c)) for c in cols] for r in pos])
    with st.container(border=True):
        st.markdown("<div class='ui-step'><span class='ui-num'>2</span><b>Scope</b></div>", unsafe_allow_html=True)
        tickers = st.multiselect("Stocks for the research agents", info["tickers"], default=info["tickers"][:15])
        o1, o2 = st.columns([1, 1.4])
        with o1:
            models = ab.load_settings()["models"] or ["anthropic/claude-haiku-5.5"]
            model = st.selectbox("Model", models)
        with o2:
            st.write("")
            comm = st.toggle("Include Investment Committee", value=False,
                             help="Slow and expensive: up to 90 minutes and about $1–2 per stock, often no price target.")
    with st.container(border=True):
        st.markdown("<div class='ui-step'><span class='ui-num'>3</span><b>Check plan and start</b></div>",
                    unsafe_allow_html=True)
        if st.button("Create plan", icon=":material/checklist:"):
            with st.spinner("Checking SEC filings and existing reports …"):
                st.session_state["plan"] = ab.make_plan(tickers, include_committee=comm)
                st.session_state["plan_for"] = (str(path), tuple(tickers), comm)
        plan = st.session_state.get("plan")
        if plan and st.session_state.get("plan_for") == (str(path), tuple(tickers), comm):
            groups = {}
            for x in plan["steps"]:
                groups.setdefault(x["step"], []).append(x)
            cards = []
            for step, xs in groups.items():
                m, u = ab.EST.get(step, (ab.NEWS_PER_TICKER[0] * len(tickers), ab.NEWS_PER_TICKER[1] * len(tickers))) \
                    if step != "news" else (ab.NEWS_PER_TICKER[0] * len(tickers), ab.NEWS_PER_TICKER[1] * len(tickers))
                n = len(xs)
                who = ", ".join(sorted({x["ticker"] for x in xs}))
                why = escape(xs[0]["reason"])[:140]
                cards.append(f"<div class='ui-pcard' title='{why}'><div class='t'>{escape(STEP_ICON.get(step, step))}</div>"
                             f"<div class='m'>{escape(who)}</div><div class='m'>approx. {m * (n if step not in ('news', 'portfolio', 'brief') else 1):.0f} min · "
                             f"{u * (n if step not in ('news', 'portfolio', 'brief') else 1):.2f} USD</div><div class='m'>{why}</div></div>")
            ui_kpis([("Steps", str(len(plan["steps"])), "will run"), ("Duration", f"approx. {plan['minutes']} min", "from past runs"),
                     ("Cost", f"approx. ${plan['usd']:.2f}", "OpenRouter"),
                     ("Without SEC report", str(len(plan["skipped"])), "news and portfolio only")])
            st.markdown("<div class='ui-plan'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
            if plan.get("no_prices"):
                st.warning("For " + ", ".join(plan["no_prices"]) + " Yahoo finds no current quotes. Usually the "
                           "ticker is wrong (Yahoo format: SAP.DE, BRK-B, 7203.T) or the stock is delisted. These "
                           "stocks are missing from value and metrics – please correct them in the CSV.",
                           icon=":material/warning:")
            if plan["skipped"]:
                why = {"no SEC filings - covered by news tracker and portfolio view":
                       "not an SEC filer (e.g. listed only in Europe)",
                       "no CIK (not an SEC filer)": "not found at the SEC"}
                st.markdown("<div class='small'>Without SEC report (no research reports, but news, portfolio review "
                            "and brief): " + "".join(
                                f"<span class='ui-pill' title='{escape(why.get(x['reason'], x['reason']))}'>"
                                f"{escape(x['ticker'])}</span>" for x in plan["skipped"]) + "</div>",
                            unsafe_allow_html=True)
            if plan["committee_held"]:
                st.caption(f"Committee would be due for {len(plan['committee_held'])} stocks but is switched off.")
            if not ab.load_settings()["openrouter"]:
                st.error("First enter the OpenRouter key under Settings.")
            elif st.button("Start analysis", type="primary", icon=":material/play_arrow:"):
                from lib import portfolios as pf
                pid = saved["id"] if saved else pf.ensure(info)
                try:
                    if pf.load().get("active") != pid:      # Ergebnisse landen im Arbeitsbereich dieses Portfolios
                        pf.switch(pid)
                except Exception as ex:
                    st.error(f"Could not switch to this portfolio: {ex}")
                    return
                stamp = ab.start_run(info, tickers, include_committee=comm, model=model, extra={"portfolio_id": pid})
                pf.mark_run(pid, stamp)
                st.session_state.pop("plan", None)
                st.toast(f"Analysis started ({stamp})")
                time.sleep(1)
                st.rerun()
    if lr:
        stt = ab.run_status(lr)
        if stt["done"]:
            with st.expander(f"Last run {lr.replace('_', ' ')}: " + ("completed" if stt["done"].get("ok") else "with errors")):
                show_steps(stt)


@st.cache_data(show_spinner="Reading portfolio …")
def inspect_cached(path, mtime):
    return ab.inspect_portfolio(path)


@st.cache_data(show_spinner="Reading portfolio …")
def saved_info_cached(pid, signature):
    from lib import portfolios as pf
    return pf.info(json.loads(signature))


def show_steps(stt, running=False):
    """Schritte als Zeitleiste: erledigt (gruen/rot), laufend (blau)."""
    items = []
    for x in stt["steps"]:
        ok = x.get("ok")
        cost = f" · {x['cost_usd']:.3f} USD" if isinstance(x.get("cost_usd"), (int, float)) else ""
        note = escape(str(x.get("error") or ""))[:160]
        items.append(f"<div class='ui-tli {'ok' if ok else 'no'}'><b>{escape(STEP_ICON.get(x['step'], x['step']))}</b> "
                     f"<span class='ui-pill'>{escape(x['ticker'])}</span><div class='m'>{x.get('seconds', '–')} s{cost}"
                     f"{' · ' + note if note else ''}</div></div>")
    if running:
        items.append("<div class='ui-tli run'><b>Next step running …</b><div class='m'>Details in the live log</div></div>")
    if items:
        st.markdown("<div class='ui-tl'>" + "".join(items) + "</div>", unsafe_allow_html=True)
    if stt["done"] and stt["done"].get("error"):
        st.error(stt["done"]["error"])


def progress(stamp):
    @st.fragment(run_every=5)
    def _box():
        stt = ab.run_status(stamp)
        n, tot = len(stt["steps"]), stt["total"] or max(len(stt["steps"]), 1)
        cost = sum(x.get("cost_usd") or 0 for x in stt["steps"])
        mins = sum(x.get("seconds") or 0 for x in stt["steps"]) / 60
        state = ("completed" if stt["done"].get("ok") else "finished with errors") if stt["done"] else \
            ("running" if stt["alive"] else "interrupted")
        ui_kpis([("Status", state, f"started {stt['cfg']['started'][11:16]}"), ("Steps", f"{n} of {tot}", "done"),
                 ("Runtime", f"{mins:.0f} min", "so far"), ("Cost", f"{cost:.2f} USD", "so far")])
        st.progress(min(n / tot, 1.0))
        show_steps(stt, running=stt["alive"] and not stt["done"])
        with st.expander("Live log"):
            st.code("\n".join(stt["tail"]) or "…", language=None)
        if stt["alive"] and not stt["done"]:
            if st.session_state.get("confirm_stop") == stamp:
                st.warning("Really stop the run? Finished steps are kept, the running step is lost.")
                b1, b2, _ = st.columns([1, 1, 4])
                if b1.button("Yes, stop", type="primary", key="stop_yes"):
                    ab.stop_run(stamp)
                    st.session_state.pop("confirm_stop", None)
                    st.rerun(scope="app")
                if b2.button("Keep running", key="stop_no"):
                    st.session_state.pop("confirm_stop", None)
                    st.rerun(scope="fragment")
            elif st.button("Stop run", icon=":material/stop_circle:", key="stop_ask"):
                st.session_state["confirm_stop"] = stamp
                st.rerun(scope="fragment")
        if stt["done"] or not stt["alive"]:
            c1, c2 = st.columns([1, 4])
            c1.page_link(PAGE_OBJ["home"], label="To overview", icon=":material/space_dashboard:")
            if c2.button("New analysis"):
                st.rerun(scope="app")
    _box()


# =============================================================== Home
def setup_items():
    """Einrichtungs-Checkliste fuer das Cockpit: (erledigt, Titel, Hinweis, Ziel)."""
    from lib import automation as au
    s = ab.load_settings()
    acfg = au.load_config()
    keys = s["openrouter"] and s["SEC_USER_AGENT"]
    tick = current_tickers()
    brief = ab.latest_brief()[0] is not None
    n = len((acfg.get("source") or {}).get("tickers") or tick)
    return [(keys, "API keys and monthly budget",
             f"OpenRouter and SEC set · budget ${float(acfg.get('budget_usd') or 0):.0f} per month" if keys
             else "Enter OpenRouter key and SEC user agent", "settings"),
            (bool(tick), "Portfolio and watchlist", f"{n} holdings" if tick else "Choose or upload a file", "Analysis"),
            (brief, "First run of all agents", "Weekly brief available" if brief else "run all agents once",
             "Analysis"),
            (bool(acfg.get("enabled")), "Switch on automation",
             f"checks daily at {acfg.get('time')}" if acfg.get("enabled") else "then the agents run by themselves",
             "Automation")]


def setup_card():
    items = setup_items()
    done = sum(1 for x in items if x[0])
    if done == len(items):
        return
    rows = "".join(f"<div class='ui-ck {'ok' if ok else ''}'><span class='ico'>{'✓' if ok else ''}</span><div>"
                   f"<b>{escape(t)}</b><div class='m'>{escape(m)}</div></div></div>" for ok, t, m, _ in items)
    with st.container(border=True):
        st.markdown(f"<div class='ui-ckh'><b>Setup · {done} of {len(items)} done</b>"
                    f"<span class='ui-pill run'>{round(done / len(items) * 100)} %</span></div>{rows}", unsafe_allow_html=True)
        nxt = next(x for x in items if not x[0])
        if st.button(f"Next: {nxt[1]}", icon=":material/arrow_forward:", key="setup_next"):
            if nxt[3] == "settings":
                go("settings")
            st.session_state["setup_tab_next"] = nxt[3]
            go("run")


def automation_strip():
    """Kleine Zeile im Cockpit, wenn die Automatik an ist: naechste Pruefung, Budget, letzte Pruefung."""
    from lib import automation as au
    cfg = au.load_config()
    if not cfg.get("enabled"):
        return
    last = (au.history(1) or [None])[0]
    nxt = au.next_check(cfg.get("time", "07:00"))
    bud = float(cfg.get("budget_usd") or 0)
    tip = (", ".join(last.get("steps") or []) or last.get("why") or "") if last else ""
    st.markdown("<div class='ui-bar' style='flex-direction:row;flex-wrap:wrap;gap:8px;padding:0 0 8px'>"
                f"<span class='ui-pill run'>Automation on · next check {nxt.strftime('%d %b %H:%M')}</span>"
                f"<span class='ui-pill'>Budget ${au.month_spend():.2f} / ${bud:.0f}</span>"
                + (f"<span class='ui-pill' title='{escape(tip)}'>Last check {escape(last['ts'][5:10] + ' ' + last['ts'][11:16])}: "
                   f"{escape(RESULT_DE.get(last['result'], last['result']))}</span>" if last else "")
                + "</div>", unsafe_allow_html=True)


def page_home():
    """Ueberblick: Kennzahlen und Brief oben, Handlungsbedarf mit Buttons links, Termine und Meldungen rechts."""
    from lib import home_data as hd
    from brief_view import render_brief
    from home_view import render_home
    setup_card()
    automation_strip()
    refresh = st.session_state.pop("home_refresh", False)
    payload = hd.home_payload(current_tickers() or None, refresh=refresh)
    if not payload["positions"]:
        ui_header("Overview")
        st.info("No results yet – first start a run under Setup and automation.")
        return
    res = render_home({**payload, "part": "top"}, key="home_top")
    if res.refresh:
        st.session_state["home_refresh"] = True
        st.rerun()
    if res.pdf:
        st.session_state["home_pdf"] = not st.session_state.get("home_pdf", False)
        st.session_state["home_doc"] = False
    if res.doc:
        st.session_state["home_doc"] = not st.session_state.get("home_doc", False)
        st.session_state["home_pdf"] = False
    _home_open(res.open)
    if st.session_state.get("home_pdf"):
        pdfs = sorted((ab.AIF / "reports").glob("brief_*/brief_*.pdf"), key=lambda p: p.stat().st_mtime)
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 1.4, 1])
            c1.markdown("**Weekly brief (PDF)**")
            if pdfs:
                c2.download_button("Download", pdfs[-1].read_bytes(), file_name=pdfs[-1].name, mime="application/pdf",
                                   icon=":material/download:")
            if c3.button("Close", key="home_pdf_close"):
                st.session_state["home_pdf"] = False
                st.rerun()
            if pdfs:
                for img in pdf_pages(str(pdfs[-1]), pdfs[-1].stat().st_mtime):
                    st.image(img, width="stretch")
            else:
                st.info("No brief PDF yet.")
    if st.session_state.get("home_doc"):
        with st.container(border=True):
            c1, c3 = st.columns([6, 1])
            c1.markdown("**Weekly brief with fact check** – hover over a number to see source and passage.")
            if c3.button("Close", key="home_doc_close"):
                st.session_state["home_doc"] = False
                st.rerun()
            embed("weekly_brief.html", 2400)
    bp = hd.brief_payload()
    left, right = st.columns([1.7, 1])
    with left:
        if bp:
            rb = render_brief({**bp, "mode": "overview"}, key="ov_brief")
            if rb.act:
                _set_action(rb.act)
            if rb.open:
                _home_open({"page": "research", "t": rb.open.get("t")})
            if rb.news:
                go("news")
        else:
            st.info("No brief yet – actions appear after the next run.")
    with right:
        rs = render_home({**payload, "part": "side"}, key="home_side")
        _home_open(rs.open)
        insights_section(compact=True)


def _home_open(o):
    if not o:
        return
    target = o.get("page")
    if target == "research" and o.get("t"):
        st.session_state["company"] = o["t"]
        st.session_state.pop("report_id", None)
    go(target if target in PAGE_OBJ else "home")


def _set_action(a):
    """Button im Handlungsbedarf: Status mit dem aktuellen Ausloeser-Fingerabdruck speichern."""
    from lib import action_state as acs
    t = str(a.get("t") or "").upper()
    data, _ = ab.latest_brief()
    trig = next((p.get("triggers") for p in (data or {}).get("positions", []) if p["ticker"].upper() == t), [])
    acs.set_state(t, trig, a.get("state"), a.get("note", ""))
    st.rerun()


def page_brief():
    from lib import home_data as hd
    from brief_view import render_brief
    payload = hd.brief_payload()
    if not payload:
        ui_header("Weekly Brief")
        st.info("No brief yet – first start a run under Setup and automation.")
        return
    res = render_brief(payload)
    if res.open:
        st.session_state["company"] = res.open["t"]
        st.session_state.pop("report_id", None)
        go("research")
    if res.news:
        go("news")
    if res.doc:
        st.session_state["brief_doc"] = not st.session_state.get("brief_doc", False)
    pdfs = sorted((ab.AIF / "reports").glob("brief_*/brief_*.pdf"))
    if pdfs:
        st.download_button("Download brief as PDF", pdfs[-1].read_bytes(), file_name=pdfs[-1].name,
                           mime="application/pdf", icon=":material/download:")
    if st.session_state.get("brief_doc"):
        st.divider()
        st.caption("The brief as a document, as written by the Brief agent – every number with its fact-check marking.")
        embed("weekly_brief.html", 2400)


def embed(name, height):
    html = ab.site_page(name)
    if not html:
        st.info("Not available yet – start a run first or rebuild the dashboard under Log.")
        return
    components.html(html, height=height, scrolling=True)


def _eur(v, d=0):
    return "–" if v is None else ("−€" if v < 0 else "€") + f"{abs(v):,.{d}f}"


def _pct(v, d=1):
    return "–" if v is None else f"{v * 100:.{d}f}%"


def _ddmm(s_):
    return f"{int(s_[8:10])} {MON_DE[int(s_[5:7]) - 1]} {s_[2:4]}" if s_ and len(s_) >= 10 else "–"


CH_PAL = ["#185FA5", "#1D9E75", "#7F77DD", "#D85A30", "#BA7517", "#D4537E", "#378ADD", "#5DCAA5", "#888780"]
CH_CSS = """<style>
.hbx{display:flex;flex-direction:column;gap:7px}.hbr{display:flex;align-items:center;gap:10px;font-size:calc(15.5px*var(--bfs,1))}
.hbl{width:9.5em;flex:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.hbt{flex:1;display:flex;flex-direction:column;gap:2px}
.hbb{height:8px;border-radius:3px;min-width:1px}.hbv{width:8.5em;flex:none;text-align:right;white-space:nowrap}
.mcx{display:flex;align-items:flex-end;gap:6px;height:190px;padding-top:18px}.mcc{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;min-width:0}
.mcs{width:100%;max-width:46px;display:flex;flex-direction:column-reverse;border-radius:4px;overflow:hidden}.mcs i{display:block}
.mcl{font-size:calc(13.5px*var(--bfs,1));color:rgba(128,128,128,1)}.mct{font-size:calc(13px*var(--bfs,1));color:rgba(128,128,128,1);white-space:nowrap}
.chl{display:flex;flex-wrap:wrap;gap:4px 14px;margin-top:8px;font-size:calc(14.5px*var(--bfs,1));color:rgba(128,128,128,1)}
.chl i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
</style>"""
MON_DE = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _hbars(rows, labels, colors=("#378ADD", "#B4B2A9"), fmt=None):
    """Horizontale Balkenpaare als HTML (ohne pyarrow): rows = [(Beschriftung, Wert A, Wert B)]."""
    fmt = fmt or (lambda v: _pct(v, 1))
    mx = max([max(a or 0, b or 0) for _, a, b in rows] + [1e-9])
    out = [CH_CSS, "<div class='hbx'>"]
    for lab, a, b in rows:
        bars = "".join(f"<div class='hbb' style='width:{(v or 0) / mx * 100:.1f}%;background:{c}' "
                       f"title='{escape(l)}: {fmt(v)}'></div>" for v, c, l in ((a, colors[0], labels[0]), (b, colors[1], labels[1])))
        out.append(f"<div class='hbr'><span class='hbl' title='{escape(lab)}'>{escape(lab)}</span><div class='hbt'>{bars}</div>"
                   f"<span class='hbv'>{fmt(a)} <span class='small'>/ {fmt(b)}</span></span></div>")
    out.append("</div><div class='chl'>" + "".join(f"<span><i style='background:{c}'></i>{escape(l)}</span>"
                                                   for c, l in zip(colors, labels)) + "</div>")
    return "".join(out)


def _month_bars(months):
    """Gestapelte Monatssaeulen (EUR je Titel) als HTML."""
    tot = {}
    for m in months:
        for t, v in m["items"].items():
            tot[t] = tot.get(t, 0) + v
    ticks = sorted(tot, key=lambda t: -tot[t])
    col = {t: CH_PAL[i % len(CH_PAL)] for i, t in enumerate(ticks)}
    mx = max([sum(m["items"].values()) for m in months] + [1e-9])
    cols = []
    for m in months:
        s = sum(m["items"].values())
        segs = "".join(f"<i style='height:{v / mx * 150:.1f}px;background:{col[t]}' title='{escape(t)}: {_eur(v, 2)}'></i>"
                       for t, v in sorted(m["items"].items(), key=lambda x: -tot[x[0]]) if v > 0)
        mm = int(m["m"][5:7])
        cols.append(f"<div class='mcc'><span class='mct'>{_eur(s) if s else ''}</span><div class='mcs'>{segs}</div>"
                    f"<span class='mcl'>{MON_DE[mm - 1]}</span></div>")
    legend = "".join(f"<span><i style='background:{col[t]}'></i>{escape(t)}</span>" for t in ticks)
    return CH_CSS + f"<div class='mcx'>{''.join(cols)}</div><div class='chl'>{legend}</div>"


def _received_dividends(days=365):
    """Tatsaechlich erhaltene Dividenden (brutto laut Export) der letzten 12 Monate aus der Buchungsliste."""
    from datetime import date as _d, timedelta as _td
    from lib import home_data as hd
    try:
        dash = json.load(open(ab.AIF / "research" / "portfolio_dashboard.json", encoding="utf-8"))
        tx = ((dash.get("performance") or {}).get("transactions")) or hd._transactions_fallback()
    except Exception:
        return None
    if not tx:
        return None
    since = (_d.today() - _td(days=days)).isoformat()
    return sum(x.get("amount") or 0 for x in tx if x.get("type") == "dividend" and x.get("date", "") >= since)


def dividends_section():
    """Dividendenkalender: erwartete Zahlungen der naechsten 12 Monate, Rendite je Position, naechste Ex-Tage."""
    from lib import dividends as dv
    from lib.pipeline import portfolio_positions
    pos = portfolio_positions()
    if not pos:
        return
    with st.container(border=True):
        h1, h2 = st.columns([5, 1])
        h1.markdown("**Dividends** <span class='ii' data-tip='Expected payments for the next 12 months, projected from each holding’s last 12 months of dividends (announced ex-dates from Yahoo first), gross before tax, converted to EUR via your position value. Received = dividend bookings in your exports.'>i</span> <span class='small'>· expected for the next 12 months (gross, from the pattern of the "
                    "last 12 months; announced ex-dates from Yahoo first) and actually received</span>",
                    unsafe_allow_html=True)
        refresh = h2.button("", key="div_rf", icon=":material/refresh:", help="Reload dividend data")
        try:
            with st.spinner("Loading dividend data …"):
                d = dv.payload(pos, refresh=refresh)
        except Exception as ex:
            st.caption(f"Dividend data not available: {ex}")
            return
        nxt = d["upcoming"][0] if d["upcoming"] else None
        got = _received_dividends()
        ui_kpis([("Expected, next 12 months", _eur(d["total_eur"]), f"for your portfolio · {d['payers']} of {len(d['rows'])} holdings pay"),
                 ("Received, last 12 months", _eur(got) if got is not None else "–", "from your bookings"),
                 ("Dividend yield", _pct(d["yield"], 2), "expected, on portfolio value"),
                 ("Next ex-date", escape(nxt["t"]) if nxt else "–",
                  (_ddmm(nxt["next_ex"]) + (" announced" if nxt["announced"] else " estimated")) if nxt else "no date")])
        if d["total_eur"]:
            st.markdown("<div class='small' style='margin-top:6px'>Expected payments per month (ex-date), in €</div>"
                        + _month_bars(d["months"]), unsafe_allow_html=True)
        rows = [r for r in d["rows"] if r["income"]]
        if rows:
            html_table(["Holding", "Yield", "Dividend per share (12 m)", "Expected for you p.a.", "Frequency", "Next ex-date"],
                       [[escape(r["t"]), _pct(r["yield"], 2),
                         f"{r['dps']:.2f} {escape(r['currency'] or '')}" if r["dps"] else "–", _eur(r["income"]),
                         escape(r["freq"] or "–"),
                         _ddmm(r["next_ex"]) + ("" if r["announced"] else " (estimated)") if r["next_ex"] else "–"] for r in rows])
        nopay = [r["t"] for r in d["rows"] if not r["income"]]
        if nopay:
            st.caption("No dividend in the last 12 months: " + ", ".join(nopay))


def etf_section():
    """ETF-Durchschau und Vergleich mit einem Welt-ETF (FTSE All-World, MSCI ACWI, MSCI World)."""
    from lib import etf_lookthrough as el
    from lib.pipeline import portfolio_positions
    pos = portfolio_positions()
    if not pos:
        return
    with st.container(border=True):
        h1, h2 = st.columns([3.2, 2])
        h1.markdown("**Comparison with a world ETF** <span class='ii' data-tip='Compares your weights with a global index ETF: its top 10 holdings with index weight vs. your weight, the largest over- and underweights, and sector weights. Data from Yahoo via US-listed proxies with the same index (VT, ACWI, URTH).'>i</span> <span class='small'>· where your portfolio deviates from the world market (Yahoo: "
                    "top 10 and sectors of the ETF)</span>", unsafe_allow_html=True)
        ui = ab.load_ui()
        idx = h2.segmented_control("World ETF", list(el.WORLD), default=ui.get("world_etf") or "FTSE All-World",
                                   key="world_etf", label_visibility="collapsed") or "FTSE All-World"
        if idx != (ui.get("world_etf") or "FTSE All-World"):
            ab.save_ui(world_etf=idx)
        try:
            with st.spinner("Loading ETF data …"):
                w = el.world_compare(pos, idx)
        except Exception as ex:
            st.caption(f"ETF data not available: {ex}")
            w = None
        if w and w["has_data"]:
            over = max(w["rows"] + w["extra"], key=lambda r: r.get("diff", r.get("mine", 0)), default=None)
            under = min(w["rows"], key=lambda r: r["diff"], default=None)
            ui_kpis([("Overlap", _pct(w["overlap"], 1), f"with the top 10 of the {escape(idx)}"),
                     ("Your share in the top 10", _pct(w["mine_in_top"], 0), f"Index: {_pct(w['top10_share'], 0)}"),
                     ("Largest overweight", escape(over["t"]) if over else "–",
                      ("+" + _pct(over.get("diff", over.get("mine")), 1).lstrip("+")) if over else ""),
                     ("Largest underweight", escape(under["t"]) if under else "–", _pct(under["diff"], 1) if under else "")])
            c1, c2 = st.columns([1.3, 1])
            with c1:
                html_table(["Top 10 in the index", "Index", "Your portfolio", "Difference"],
                           [[f"<b>{escape(r['t'])}</b> <span class='small'>{escape(str(r['name'])[:28])}</span>",
                             _pct(r["index"], 1), _pct(r["mine"], 1) if r["mine"] else "–",
                             f"<span style='color:{'#1a7f4b' if r['diff'] > 0 else '#b42318'}'>{'+' if r['diff'] > 0 else ''}"
                             f"{_pct(r['diff'], 1).lstrip('+')}</span>"] for r in w["rows"]])
                if w["extra"]:
                    st.caption("Your largest positions outside the index top 10: "
                               + ", ".join(f"{escape(r['t'])} {_pct(r['mine'], 1)}" for r in w["extra"][:6]))
            with c2:
                st.markdown("<div class='small' style='margin-bottom:6px'>Sectors: your portfolio vs. the index</div>"
                            + _hbars([(x["s"], x["mine"], x["index"]) for x in w["sectors"][:11]], ("Your portfolio", idx)),
                            unsafe_allow_html=True)
            st.caption(f"Data source: {escape(w['proxy'])} ({escape(w['name'] or '')}) as US proxy with the "
                       f"same index, because Yahoo has no holdings data for the European UCITS versions"
                       + (" (VT tracks the FTSE Global All Cap, i.e. FTSE All-World plus small caps)." if w["proxy"] == "VT" else "."))
        elif w is not None:
            st.caption("Yahoo currently has no holdings data for this ETF.")
    try:
        d = el.payload(pos)
    except Exception:
        return
    if not d["etfs"]:
        return
    with st.container(border=True):
        st.markdown("**ETF look-through** <span class='ii' data-tip='What your ETFs hold (top 10 and sectors from Yahoo) and where they overlap with stocks you hold directly; total weight = direct weight plus ETF weight times the share in the ETF.'>i</span> <span class='small'>· what your ETFs hold and where it doubles up with single "
                    "stocks (Yahoo: top 10 positions and sectors per ETF)</span>", unsafe_allow_html=True)
        top = d["rows"][0] if d["rows"] else None
        ui_kpis([("ETF share", _pct(d["etf_weight"]), f"{len(d['etfs'])} ETFs/Fonds"),
                 ("Looked through", _pct(d["covered_share"], 0), "of the ETF share (top 10)"),
                 ("Overlaps", str(len(d["overlaps"])), "held directly and in an ETF"),
                 ("Largest total position", escape(top["t"]) if top else "–", _pct(top["total"]) if top else "")])
        nodata = [e["t"] for e in d["etfs"] if not e["has_data"]]
        if nodata:
            st.caption("No holdings data at Yahoo (common for European UCITS ETFs): " + ", ".join(nodata))
        c1, c2 = st.columns([1.4, 1])
        with c1:
            html_table(["Holding", "Direct", "Via ETFs", "Total", "Held in"],
                       [[("<b>" if r["overlap"] else "") + escape(r["t"]) + ("</b>" if r["overlap"] else ""),
                         _pct(r["direct"]), _pct(r["etf"], 2), _pct(r["total"]), escape(", ".join(r["via"]) or "–")]
                        for r in d["rows"][:15]])
            st.caption("Bold = stock you hold directly that is also inside an ETF.")
        with c2:
            if d["sectors"]:
                st.markdown(_hbars([(x["s"], x["direct"], x["etf"]) for x in d["sectors"]], ("Direct", "Via ETFs")),
                            unsafe_allow_html=True)


def _portfolio_page(view, title):
    from lib import home_data as hd
    from portfolio_view import render_portfolio
    payload = hd.portfolio_payload()
    if not payload:
        ui_header(title)
        st.info("No portfolio data yet – first start a run under Setup and automation.")
        return False
    res = render_portfolio({**payload, "view": view, "title": title}, key=f"portfolio_{view}")
    if res.open:
        st.session_state["company"] = res.open["t"]
        st.session_state.pop("report_id", None)
        go("research")
    return True


def page_portfolio():
    """Depot: Wert, Wertentwicklung, Positionen, Dividenden, Transaktionen, Watchlist."""
    if _portfolio_page("depot", "Portfolio"):
        dividends_section()
    watchlist_widget()


def page_analysis():
    """Portfolio-Analyse: Performance gegen Benchmark, Risiko, Struktur, ETF-Durchschau, Optimierung, Entscheidungen."""
    if _portfolio_page("analysis", "Portfolio analysis"):
        etf_section()
        review_section()


def review_section():
    """Kurzfassung des letzten Portfolio Reviews (Portfolio-Manager-Agent) mit PDF."""
    import glob
    pdfs = sorted(glob.glob(str(ab.AIF / "reports" / "portfolio_*" / "*_portfolio_review.pdf")), key=os.path.getmtime)
    if not pdfs:
        return
    pdf = Path(pdfs[-1])
    args = {}
    try:
        args = json.load(open(str(pdf).replace(".pdf", "_build_args.json"), encoding="utf-8"))
    except Exception:
        pass
    with st.container(border=True):
        c1, c2 = st.columns([5, 1.3])
        c1.markdown(f"**Portfolio review by the agent** <span class='ii' data-tip='Written by the Portfolio Manager agent from the calculated performance, risk, optimisation and backtest; every number is fact-checked.'>i</span> <span class='small'>· "
                    f"{time.strftime('%d %b %Y', time.localtime(pdf.stat().st_mtime))}</span>", unsafe_allow_html=True)
        c2.download_button("Download PDF", pdf.read_bytes(), file_name=pdf.name, mime="application/pdf",
                           key="pr_dl")
        if args.get("headline"):
            st.markdown(f"<div style='font-weight:600;margin:2px 0 4px'>{escape(str(args['headline']))}</div>"
                        f"<div class='small'>{escape(str(args.get('summary') or ''))[:900]}</div>", unsafe_allow_html=True)
        with st.expander("Read review"):
            for img in pdf_pages(str(pdf), pdf.stat().st_mtime):
                st.image(img, width="stretch")


def _de(x, d=2):
    return f"{x:,.{d}f}"


def watchlist_widget():
    """Bearbeitbare Watchlist: Titel beobachten, ohne sie zu halten (News, Termine, Research, Automatik)."""
    from lib import watchlist as wl
    with st.container(border=True):
        st.markdown("<div class='ui-ckh'><b>Watchlist</b><span class='small'>follow stocks without holding them · "
                    "feeds into news and automation</span></div>", unsafe_allow_html=True)
        with st.form("wl_add", clear_on_submit=True, border=False):
            c1, c2, c3 = st.columns([1, 2.6, 0.9])
            t = c1.text_input("Ticker", placeholder="Ticker, e.g. NVDA", label_visibility="collapsed")
            n = c2.text_input("Note", placeholder="Why follow? e.g. entry below $120, wait for Q4 results",
                              label_visibility="collapsed")
            add = c3.form_submit_button("Add", icon=":material/add:", use_container_width=True)
        if add:
            ok, msg = wl.add(t, n)
            if ok:
                st.toast(msg)
                st.rerun()
            st.warning(msg)
        rows = wl.payload(current_tickers())
        if not rows:
            st.caption("Empty. Enter tickers in Yahoo format (NVDA, ASML.AS, SAP.DE). Automation then collects "
                       "news for them and creates reports on request.")
            return
        widths = [0.9, 2.4, 0.9, 0.8, 1.0, 0.7, 2.0]
        for col, lab in zip(st.columns(widths), ["Holding", "Note", "Price", "Today", "Next results", "News 7 d", ""]):
            col.markdown(f"<span class='small'>{lab}</span>", unsafe_allow_html=True)
        for r in rows:
            c = st.columns(widths, vertical_alignment="center")
            c[0].markdown(f"**{escape(r['t'])}**" + (" <span class='ui-pill ok'>in portfolio</span>" if r["in_portfolio"] else ""),
                          unsafe_allow_html=True)
            lab = (r["note"][:38] + "…") if len(r["note"]) > 40 else (r["note"] or "Add note")
            with c[1].popover(lab, use_container_width=True):
                nn = st.text_area("Note", value=r["note"], key=f"wl_note_{r['t']}", label_visibility="collapsed")
                if st.button("Save", key=f"wl_ns_{r['t']}"):
                    wl.set_note(r["t"], nn)
                    st.rerun()
            c[2].markdown(_de(r["price"]) if r["price"] is not None else "–")
            chg = r["chg"]
            c[3].markdown("–" if chg is None else (f":green[+{_de(chg * 100, 1)} %]" if chg >= 0 else f":red[{_de(chg * 100, 1)} %]"))
            c[4].markdown(".".join(reversed(r["earn"].split("-"))) if r["earn"] else "–")
            c[5].markdown(str(r["news7"]) if r["news7"] else "–")
            a1, a2 = c[6].columns([1.6, 0.5])
            if r["report"]:
                if a1.button("Dashboard", key=f"wl_o_{r['t']}", icon=":material/domain:", use_container_width=True):
                    st.session_state["company"] = r["t"]
                    st.session_state.pop("report_id", None)
                    go("research")
            elif a1.button("Create reports", key=f"wl_m_{r['t']}", use_container_width=True,
                           help="Annual report and earnings review in the background (approx. $0.13, 5–10 min; SEC filers only)"):
                _start_company_run(r["t"])
            if a2.button("", key=f"wl_x_{r['t']}", icon=":material/close:", help=f"Remove {r['t']} from the watchlist"):
                wl.remove(r["t"])
                st.rerun()


def _start_company_run(t, steps=("annual_report", "quarter_review", "earnings_review"), label=None, extra=None):
    """Annual Report und Earnings Review (oder Committee) fuer eine einzelne Firma starten (laeuft im Hintergrund)."""
    lr = ab.latest_run()
    if lr and ab.run_status(lr)["alive"]:
        st.warning("An analysis is already running – please wait until it has finished.")
        return
    if not ab.load_settings()["openrouter"]:
        st.error("No OpenRouter key – enter it under Settings first.")
        return
    ab.start_run({}, [t], steps=list(steps), label=label or f"{t}: check for new results", extra=extra)
    st.session_state["setup_tab_next"] = "Analysis"
    go("run")


def kpi_history_section(t):
    """KPI-Verlauf: firmenspezifische Kennzahlen aus allen Earnings Reviews als Zeitreihe."""
    from lib import kpi_history as kh
    try:
        hist = kh.history(t)
    except Exception:
        hist = []
    if not hist:
        return
    import pandas as pd
    with st.container(border=True):
        st.markdown(f"**KPI history** <span class='ii' data-tip='Company-specific KPIs extracted from every earnings review, as a time series; it grows with each review.'>i</span> <span class='small'>· {len(hist)} company-specific KPIs from the earnings "
                    "reviews (quarters since the annual report and prior-year quarters; grows with every review)</span>",
                    unsafe_allow_html=True)
        for i in range(0, min(len(hist), 6), 3):
            cols = st.columns(3)
            for c, k in zip(cols, hist[i:i + 3]):
                yoy = k["latest_yoy"]
                good = yoy is not None and ((yoy > 0) == (k["good"] != "down"))
                col = "#1a7f4b" if good else "#b42318"
                c.markdown(f"<div style='font-size:calc(16.5px*var(--bfs,1));font-weight:600'>{escape(k['name'])}</div><div class='small'>"
                           f"{escape(k['unit'])}" + (f" · latest <span style='color:{col}'>{yoy * 100:+.1f}%</span> vs. prior year"
                                                    if yoy is not None else "") + "</div>", unsafe_allow_html=True)
                df = pd.DataFrame({"Value": [v for _, v in k["points"]]},
                                  index=[f"{lab[-4:]} {lab[:2]}" for lab, _ in k["points"]])   # '2026 Q3' sortiert richtig
                c.line_chart(df, height=150)
        if len(hist) > 6:
            st.caption("More KPIs: " + ", ".join(escape(k["name"]) for k in hist[6:]))


def preview_section(t):
    """Earnings Preview (Beta) vor anstehenden Quartalszahlen, sofern vorhanden und der Termin nicht vorbei ist."""
    from datetime import date as _date, timedelta as _td
    from lib import earnings_preview as ep
    pv = ep.latest(t)
    if not pv or (pv.get("earnings_date") or "") < (_date.today() - _td(days=1)).isoformat():
        return
    with st.container(border=True):
        fc = pv.get("fc") or {}
        st.markdown(f"**Earnings preview** {BETA_BADGE} <span class='ii' data-tip='Written 14 days before results from consensus, revisions, your theses and the KPI history: what to watch and bull/base/bear scenarios. Numbers are checked against these inputs.'>i</span> <span class='small'>· results on {_ddmm(pv['earnings_date'])} · "
                    f"created {escape(str(pv.get('created', ''))[:10])} · fact check {fc.get('matched', '–')}/{fc.get('total', '–')} "
                    "numbers found in the inputs</span>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:calc(18px*var(--bfs,1));font-weight:600;margin:4px 0'>{escape(pv.get('headline') or '')}</div>"
                    f"<div class='small'>{escape(pv.get('consensus_note') or '')}</div>", unsafe_allow_html=True)
        c1, c2 = st.columns([1, 1.2])
        with c1:
            st.markdown("**What to watch**")
            html_table(["Item", "Why", "Threshold"], [[escape(str(w.get("item", ""))), escape(str(w.get("why", ""))),
                                                        escape(str(w.get("threshold", "")))] for w in pv.get("watch") or []])
        with c2:
            st.markdown("**Scenarios**")
            lab = {"bull": "Bull", "base": "Base", "bear": "Bear"}
            html_table(["Case", "What would have to be reported", "Effect on the theses", "Signal"],
                       [[lab.get(str(x.get("case")), escape(str(x.get("case")))), escape(str(x.get("what", ""))),
                         escape(str(x.get("thesis_impact", ""))), escape(str(x.get("signal", "")))] for x in pv.get("scenarios") or []])
        if fc.get("unmatched"):
            st.caption("Not found in the inputs: " + ", ".join(escape(str(x)) for x in fc["unmatched"]))
        if pv.get("kpis"):
            st.caption("Check first: " + ", ".join(escape(str(k)) for k in pv["kpis"]))


def page_research():
    from lib import company_data as cd
    from company_view import render_companies, render_company
    try:
        cd.archive_reports()  # neue Reports mit Datum ablegen (schnell, erkennt bereits archivierte)
    except Exception as ex:
        st.caption(f"Archive not updated: {ex}")
    t = st.session_state.get("company")
    if not t:
        res = render_companies(cd.companies())
        if res.open:
            st.session_state["company"] = res.open["t"]
            st.session_state.pop("report_id", None)
            st.rerun()
        if res.make:
            _start_company_run(res.make["t"])
        return
    if st.session_state.get("confirm_committee") == t:
        from lib import automation as au
        acfg = au.load_config()
        with st.container(border=True):
            st.markdown(f"**Start investment committee for {escape(t)}?** {BETA_BADGE} A CIO and three analyst groups debate on the "
                        "basis of the annual report, earnings reviews and news, then vote. Takes up to 60 minutes, costs "
                        f"about $1–2. This month so far ${au.month_spend():.2f} of "
                        f"${float(acfg.get('budget_usd') or 0):.0f} budget.", unsafe_allow_html=True)
            c1, c2, _ = st.columns([1, 1, 5])
            if c1.button("Start", type="primary", key="com_go"):
                st.session_state.pop("confirm_committee", None)
                _start_company_run(t, steps=["committee"], label=f"{t}: Investment Committee",
                                   extra={"plan_args": {"committee_days": 0}})
            if c2.button("Cancel", key="com_no"):
                st.session_state.pop("confirm_committee", None)
                st.rerun()
    payload = cd.company_payload(t)
    res = render_company({**payload, "part": "top"}, key=f"company_{t}")
    if res.committee:
        st.session_state["confirm_committee"] = t
        st.rerun()
    if res.back:
        st.session_state.pop("company", None)
        st.session_state.pop("report_id", None)
        st.rerun()
    if res.check:
        _start_company_run(t)
    trk = getattr(res, "tracker", None)          # aeltere Sitzungen kennen den Ausloeser noch nicht
    if trk:
        if not ab.load_settings()["openrouter"]:
            st.warning("No OpenRouter key – enter it under Settings first.")
        elif trk["v"] == "book":
            from lib import thesis_tracker as tt
            with st.spinner("Turning the annual report theses into measurable milestones (about 10 seconds) …"):
                try:
                    b = tt.build_book(t)
                    tt._log_cost(f"thesis book {t}", b.get("cost"), b.get("model"))
                except Exception as ex:
                    b = None
                    st.error(f"Thesis book not created: {ex}")
            if b:
                st.rerun()
        else:
            _start_company_run(t, steps=["quarter_review"], label=f"{t}: quarter records")
    if res.report:
        st.session_state["report_id"] = res.report["v"]
        st.session_state.pop("report_closing", None)
        st.rerun()
    rid = st.session_state.get("report_id")
    if rid:
        report_viewer(t, rid)
    preview_section(t)
    render_company({**payload, "part": "main"}, key=f"company_main_{t}")
    valuation_section(t)
    with st.expander("Rebuild reports"):
        st.caption("Rewrite the annual report and earnings review with the current agents, even if no "
                   "new filing exists (e.g. after a fix). Takes about 12 minutes, costs about $0.15.")
        what = st.segmented_control("Scope", ["Both", "Annual Report", "Earnings Review"], default="Both",
                                    key=f"rebuild_{t}", label_visibility="collapsed")
        if st.button("Rebuild", key=f"rebuild_go_{t}", icon=":material/refresh:"):
            steps = {"Annual Report": ["annual_report"], "Earnings Review": ["earnings_review"]}.get(
                what or "Both", ["annual_report", "earnings_review"])
            _start_company_run(t, steps=steps, label=f"{t}: rebuild reports",
                               extra={"plan_args": {"force": steps}})


def valuation_section(t):
    """Reverse DCF mit Reglern, Financial Quality und Peer-Vergleich (Yahoo, 24 h zwischengespeichert)."""
    from lib import valuation_data as vd
    from company_view import render_valuation
    d = vd.payload(t)
    if d is None and not st.session_state.get(f"val_failed_{t}"):
        with st.spinner(f"Loading valuation data for {t} (Yahoo Finance, about 15 seconds) …"):
            try:
                d = vd.payload(t, refresh=True)
            except Exception as ex:
                st.session_state[f"val_failed_{t}"] = str(ex)[:200]
    res = render_valuation(d or {"t": t, "missing": True, "error": st.session_state.get(f"val_failed_{t}")},
                           key=f"valuation_{t}")
    if getattr(res, "refresh", None):
        st.session_state.pop(f"val_failed_{t}", None)
        with st.spinner("Refreshing valuation data …"):
            try:
                vd.payload(t, refresh=True)
            except Exception as ex:
                st.error(f"Refresh failed: {ex}")
                return
        st.rerun()
    if getattr(res, "suggest", None):
        if not ab.load_settings()["openrouter"]:
            st.warning("No OpenRouter key – enter it under Settings first.")
            return
        with st.spinner("The model proposes a base case from the annual report (about 10 seconds) …"):
            try:
                vd.suggest_case(t)
            except Exception as ex:
                st.error(f"No AI case: {ex}")
                return
        st.rerun()


def report_viewer(t, rid):
    """Geoeffneter Report direkt unter der Report-Liste; klappt animiert auf und beim Schliessen wieder zu."""
    from lib import company_data as cd
    closing = st.session_state.get("report_closing") == rid
    e = next((x for x in cd.load_index() if x["id"] == rid), None)
    box = st.container(border=True, key=f"rv{'x' if closing else ''}_{rid}")
    with box:
        c1, c2, c3 = st.columns([6, 1.4, 1])
        c1.markdown(f"**{escape(t)} {escape(e['title'] if e else '')}** <span class='small'>· "
                    f"{escape(e['date'] if e else '')}</span>", unsafe_allow_html=True)
        has_pdf = bool(e and e.get("pdf") and (ab.AIF / e["pdf"]).exists())
        if has_pdf:
            c2.download_button("Download PDF", (ab.AIF / e["pdf"]).read_bytes(), file_name=Path(e["pdf"]).name,
                               mime="application/pdf")
        if c3.button("Close", key=f"rv_close_{rid}", icon=":material/close:"):
            st.session_state["report_closing"] = rid
            st.rerun()
        view = st.segmented_control("View", ["PDF", "With fact check"] if has_pdf else ["With fact check"],
                                    default="PDF" if has_pdf else "With fact check", key=f"rview_{rid}",
                                    label_visibility="collapsed")
        if view == "PDF" and has_pdf:
            pdf_path = ab.AIF / e["pdf"]
            for img in pdf_pages(str(pdf_path), pdf_path.stat().st_mtime):
                st.image(img, width="stretch")
        else:
            st.caption("Report text with fact check: green = number and context found in the sources (hover "
                       "to see source and passage, the number is highlighted), yellow = number is in the sources but in a "
                       "different context, red = not found.")
            if not (ab.site_dir() / f"archive_{rid}.html").exists():
                cd.archive_pages()
            embed(f"archive_{rid}.html", 3200)
    if closing:                                       # Zuklapp-Animation abspielen lassen, dann entfernen
        time.sleep(0.6)
        st.session_state.pop("report_id", None)
        st.session_state.pop("report_closing", None)
        st.rerun()


@st.cache_data(show_spinner="Loading PDF …", max_entries=20)
def pdf_pages(path, mtime, zoom=1.7):
    """PDF-Seiten als PNG-Bilder (PyMuPDF), damit der Report direkt in der App angezeigt wird."""
    import fitz
    with fitz.open(path) as doc:
        return [pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png") for pg in doc]


CHAT_CSS = """<style>
.ans p{margin:0 0 .55rem}.ans ul{margin:.1rem 0 .6rem 1.1rem;padding:0}.ans li{margin:.15rem 0}
.ans .num{border-radius:3px;padding:0 2px;position:relative;cursor:help}
.ans .num.ok{background:rgba(29,158,117,.13);border-bottom:2px solid #1D9E75}
.ans .num.no{background:rgba(226,75,74,.13);border-bottom:2px solid #E24B4A}
.ans .num.un{background:rgba(127,127,127,.12)}
.ans .num.ctx{background:rgba(239,159,39,.16);border-bottom:2px dashed #BA7517}
.ans .num[data-tip]:hover::after{content:attr(data-tip);position:absolute;left:0;top:calc(100% + 6px);z-index:50;width:max-content;
max-width:420px;white-space:pre-line;background:#1d2329;color:#fff;font-size:calc(15.5px*var(--bfs,1));line-height:1.45;padding:8px 10px;border-radius:8px;
box-shadow:0 6px 20px rgba(0,0,0,.18);pointer-events:none}
.ans .cite{display:inline-block;font-size:calc(14px*var(--bfs,1));line-height:16px;min-width:17px;text-align:center;border-radius:8px;
background:rgba(55,138,221,.15);color:#378ADD;margin:0 1px;padding:0 4px;cursor:help;vertical-align:1px}
.srcs{font-size:calc(16px*var(--bfs,1))}.srcs .cited{font-weight:600}
</style>"""


def _chat_actions(res, i):
    for j, a in enumerate(res.get("actions") or []):
        label = {"check": f"Re-run annual report and earnings review for {a['ticker']}",
                 "add": f"Create reports for {a['ticker']}",
                 "open": f"Open company dashboard {a['ticker']}"}[a["type"]]
        if st.button(("✓ Confirm: " if a["type"] != "open" else "") + label, key=f"act_{i}_{j}"):
            if a["type"] == "open":
                st.session_state["company"] = a["ticker"]
                st.session_state.pop("report_id", None)
                go("research")
            else:
                _start_company_run(a["ticker"])


def _chat_message(m, i):
    from lib import chat
    if m["role"] == "user":
        with st.chat_message("user"):
            st.markdown(escape(m["content"]))
        return
    res = m["res"]
    with st.chat_message("assistant"):
        st.markdown(f"<div class='ans'>{chat.render_html(res)}</div>", unsafe_allow_html=True)
        fc = res["fc"]
        parts = [f"Fact check: {fc['matched']} of {fc['total']} numbers found in the sources" if fc["total"] else "no numbers",
                 f"{len(res['cited'])} sources cited"]
        if res.get("cost") is not None:
            parts.append(f"{res['cost']:.4f} $")
        parts.append(f"{res.get('seconds', 0)} s")
        st.caption(" · ".join(parts))
        with st.expander(f"Sources ({len(res['sources'])})"):
            rows = []
            for n, h in enumerate(res["sources"], 1):
                cls_ = "cited" if n in res["cited"] else ""
                rows.append(f"<div class='srcs'><span class='{cls_}'>[{n}] {escape(h['label'])}</span><br>"
                            f"<span class='small'>{escape(h['text'][:320])}{'…' if len(h['text']) > 320 else ''}</span></div>")
            st.markdown("<br>".join(rows), unsafe_allow_html=True)
        _chat_actions(res, i)


def page_chat():
    from lib import chat
    ui_header("Ask your research", beta=True, sub="Answers only from your own reports, the weekly brief, the news and the "
              "portfolio data, with sources. Every number is checked against the sources: green found, red not "
              "found (hover to see the source). Actions only run after you confirm.")
    st.markdown(CHAT_CSS, unsafe_allow_html=True)
    hist = st.session_state.setdefault("chat", [])
    s = ab.load_settings()
    if not s["openrouter"]:
        st.warning("No OpenRouter key – enter it under Settings.")
    for i, m in enumerate(hist):
        _chat_message(m, i)
    q = st.chat_input("Ask a question, e.g. “Why is GOOG on Decide?”")
    if not hist and not q:
        st.markdown("**For example:**")
        cols = st.columns(2)
        for j, sug in enumerate(chat.suggestions()):
            if cols[j % 2].button(sug, key=f"sug_{j}", use_container_width=True):
                q = sug
    if q:
        hist.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(escape(q))
        with st.chat_message("assistant"):
            with st.spinner("Searching your reports and writing the answer …"):
                past = [{"q": hist[k]["content"], "a": hist[k + 1]["res"]["answer"]}
                        for k in range(len(hist) - 1) if hist[k]["role"] == "user" and k + 1 < len(hist)
                        and hist[k + 1]["role"] == "assistant"]
                try:
                    res = chat.answer(q, history=past[-2:], model=(s["models"] or [None])[0])
                    hist.append({"role": "assistant", "res": res})
                except Exception as ex:
                    hist.pop()
                    st.error(f"No answer: {ex}")
                    return
        st.rerun()
    if hist and st.button("Clear history"):
        st.session_state["chat"] = []
        st.rerun()


def _insight_rows(items):
    rows = []
    for x in items:
        d = (x.get("date") or "")[:10]          # nur das Datum des Beitrags, nicht das des Abrufs
        month = x.get("date_prec") == "month" or (not x.get("date_prec") and d.endswith("-01") and "/20" in x.get("url", ""))
        dd = (f"{d[5:7]}/{d[2:4]}" if month else f"{d[8:10]}.{d[5:7]}.{d[2:4]}") if len(d) == 10 else ""
        url = x.get("url", "")
        safe = url if url.startswith(("http://", "https://")) else "#"
        rows.append(f"<div class='ins-r'><span class='ins-d'>{dd}</span><span class='ui-pill' title='{escape(x.get('source', ''))}'>{escape(x.get('source', ''))}</span>"
                    f"<a href='{escape(safe)}' target='_blank' rel='noopener'>{escape(x.get('title', ''))}</a>"
                    + ("<span class='ins-new'>new</span>" if x.get("new") else "") + "</div>")
    return "".join(rows) or "<div class='small'>No posts yet – sources are read on the first fetch.</div>"


INS_CSS = """<style>.ins-r .ui-pill{flex:none;width:9.5em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:center;
box-sizing:border-box;padding-left:6px;padding-right:6px}
.ins-r{display:flex;gap:10px;align-items:baseline;padding:6px 0;border-top:1px solid rgba(128,128,128,.18);font-size:calc(17px*var(--bfs,1))}
.ins-r:first-child{border-top:0}.ins-d{color:rgba(128,128,128,1);font-size:calc(15.5px*var(--bfs,1));min-width:70px}.ins-r a{text-decoration:none}
.ins-r a:hover{text-decoration:underline}.ins-new{font-size:calc(14px*var(--bfs,1));font-weight:700;color:#185FA5;background:rgba(55,138,221,.13);
border-radius:6px;padding:0 6px}</style>"""


def reads_section():
    """Interesting Reads: von der KI ausgewaehlte Beitraege, Podcasts und Videos zu Interessen, Depot und Watchlist."""
    from lib import reads as rd
    d = rd.latest()
    with st.container(border=True):
        c1, c2 = st.columns([3.2, 1.4])
        when = f" · picked on {d['created'][:10]}" if d.get("created") else ""
        c1.markdown(f"**Interesting reads** {BETA_BADGE} <span class='ii' data-tip='Once a week (or on request) the app collects candidates from your sources and a Google News search for interviews, podcasts and deep dives on your holdings, watchlist and interests; the model picks 5–7 and says why in one sentence. It can only pick real candidates. About 1–3 cents per pick.'>i</span><br><span class='small'>picked by AI for your "
                    f"interests, portfolio and watchlist{when}</span>", unsafe_allow_html=True)
        if c2.button("Pick again" if d.get("picks") else "Create picks", key="reads_go",
                     help="Collects candidates from your sources and the search; one model call, about 1–3 cents"):
            with st.spinner("Collecting candidates and picking (about 20–40 seconds) …"):
                try:
                    d = rd.run()
                except Exception as ex:
                    st.error(f"Picking not possible: {ex}")
        if not d.get("picks"):
            st.markdown("<div class='small'>No picks yet. They are created automatically with the next run (once a "
                        "week) or right away with the button.</div>", unsafe_allow_html=True)
        ico = {"read": "📄", "listen": "🎧", "watch": "▶️"}
        rows = []
        for x in d.get("picks") or []:
            url = x.get("url", "")
            safe = url if url.startswith(("http://", "https://")) else "#"
            dd = x.get("date") or ""
            meta = " · ".join(v for v in (x.get("source"), f"{dd[8:10]}.{dd[5:7]}." if len(dd) >= 10 else "", x.get("topic")) if v)
            rows.append(f"<div class='rd-r'><span class='rd-i'>{ico.get(x.get('type'), '📄')}</span><div>"
                        f"<a href='{escape(safe)}' target='_blank' rel='noopener'>{escape(x.get('title', ''))}</a>"
                        f"<div class='small'>{escape(meta)}</div><div class='rd-w'>{escape(x.get('why', ''))}</div></div></div>")
        if rows:
            st.markdown(RD_CSS + "".join(rows), unsafe_allow_html=True)
        if not ab.load_ui().get("interests"):
            st.caption("Tip: enter your interests under Settings to make the picks more targeted.")


RD_CSS = """<style>.rd-r{display:flex;gap:10px;padding:8px 0;border-top:1px solid rgba(128,128,128,.18)}
.rd-r:first-of-type{border-top:0}.rd-i{font-size:calc(17px*var(--bfs,1));line-height:1.4}.rd-r a{text-decoration:none;font-weight:600}
.rd-r a:hover{text-decoration:underline}.rd-w{font-size:calc(15.5px*var(--bfs,1));margin-top:2px;font-style:italic;opacity:.85}</style>"""


def insights_section(compact=False):
    """Insights-Watchlist in zwei Boxen: Research der Banken (neuester Beitrag je Quelle) und Podcasts/Videos
    (neueste Folgen der abonnierten Kanaele)."""
    from lib import insights as ins
    try:
        if compact:
            ins.refresh(max_age_h=6)
        else:
            with st.spinner("Checking insight sources …"):
                ins.refresh(max_age_h=6)
    except Exception:
        pass
    p = ins.payload(limit=200)
    st.markdown(INS_CSS, unsafe_allow_html=True)
    res = [x for x in p.get("latest") or [] if x.get("cat") == "research"]
    media = [x for x in p["items"] if x.get("cat") == "media"]
    media.sort(key=lambda x: x.get("date") or "", reverse=True)
    newc = lambda L: sum(1 for x in L if x.get("new"))
    head = lambda title, L: f"**{title}**" + (f" <span class='ins-new'>{newc(L)} new</span>" if newc(L) else "")
    if compact:                                   # Overview: nur Podcasts und Videos (Bank-Research steht auf der News-Seite)
        if media:
            with st.container(border=True):
                st.markdown(head("Podcasts and videos", media[:4]) + _insight_rows(media[:4]), unsafe_allow_html=True)
                if st.button("All insights", key="ins_all", type="tertiary", icon=":material/arrow_forward:"):
                    go("news")
        return
    all_res = [x for x in p["items"] if x.get("cat") == "research"]
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        c1.markdown(head("Bank research", res) + "<span class='ii' data-tip='Research pages of the banks you follow (and blogs): the app reads each page every few hours and shows the newest post per source with its publication date, looked up on the article page or in the PDF.'>i</span><br><span class='small'>newest post per source</span>",
                    unsafe_allow_html=True)
        if c2.button("", key="ins_refresh", icon=":material/refresh:", help="Check all sources now"):
            with st.spinner("Fetching all sources …"):
                ins.refresh(force=True)
            st.rerun()
        st.markdown(_insight_rows(res), unsafe_allow_html=True)
        with st.expander(f"All posts ({len(all_res)})"):
            st.markdown(_insight_rows(all_res), unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown(head("Podcasts and videos", media[:8]) + "<span class='ii' data-tip='New episodes and videos of the YouTube channels and podcast feeds you follow, newest first (official RSS feeds).'>i</span><br><span class='small'>new episodes of your channels</span>",
                    unsafe_allow_html=True)
        st.markdown(_insight_rows(media[:8]) if media else "<div class='small'>No channels yet – add a YouTube channel or podcast feed under "
                    "“Manage sources” below.</div>", unsafe_allow_html=True)
        if len(media) > 8:
            with st.expander(f"Older episodes ({len(media) - 8})"):
                st.markdown(_insight_rows(media[8:]), unsafe_allow_html=True)
    with st.expander(f"Manage sources ({len(p['sources'])})"):
        with st.form("ins_add", clear_on_submit=True, border=False):
            url = st.text_input("Address", placeholder="Research page, blog, youtube.com/@channel or podcast feed",
                                label_visibility="collapsed")
            f1, f2, f3 = st.columns([1.4, 1.2, 1])
            name = f1.text_input("Name", placeholder="Name (optional)", label_visibility="collapsed")
            catl = f2.selectbox("Type", ["Detect automatically", "Research", "Podcast or video"], label_visibility="collapsed")
            if f3.form_submit_button("Add", icon=":material/add:", use_container_width=True) and url:
                try:
                    sid = ins.add_source(url, name, cat={"Research": "research", "Podcast or video": "media"}.get(catl))
                    with st.spinner("Reading the new source …"):
                        ins.refresh(force=True, only=[sid])
                    st.rerun()
                except Exception as ex:
                    st.error(str(ex))
        kind_de = {"youtube": "YouTube-Feed", "rss": "RSS/Atom-Feed", "page": "Page"}
        for s_ in p["sources"]:
            a1, a2, a3 = st.columns([5, 1.6, 0.7])
            state = ("not fetched yet" if s_["ok"] is None else
                     f"Error: {s_['error']}" if s_["ok"] is False else
                     f"{s_['n']} posts found" + (f" · {s_['note']}" if s_.get("note") else ""))
            a1.markdown(f"**{escape(s_['name'])}** <span class='small'>· {escape(kind_de.get(s_['kind'], 'unknown'))} · "
                        f"{escape(state)}{' · checked ' + escape(s_['checked']) if s_['checked'] else ''}</span><br>"
                        f"<span class='small'>{escape(s_['url'])}</span>", unsafe_allow_html=True)
            opts = ["research", "media"]
            cur = a2.selectbox("Type", opts, index=opts.index(s_["cat"]), key=f"ins_cat_{s_['id']}",
                               format_func=lambda c: {"research": "Research", "media": "Podcast/Video"}[c],
                               label_visibility="collapsed")
            if cur != s_["cat"]:
                ins.set_category(s_["id"], cur)
                st.rerun()
            if a3.button("", key=f"ins_rm_{s_['id']}", icon=":material/delete:", help="Remove source"):
                ins.remove_source(s_["id"])
                st.rerun()
    ins.mark_seen()


def page_news():
    from lib import home_data as hd
    from lib import watchlist as wl
    from news_view import render_news
    tickers = current_tickers()
    tickers += [t for t in wl.tickers() if t not in tickers]
    if not tickers:
        ui_header("News")
        st.info("No portfolio loaded yet – first start a run under Setup and automation.")
        return
    try:
        payload = hd.news_payload(tickers)
    except Exception as ex:  # Fehler sichtbar machen statt leerer Seite
        ui_header("News")
        st.error(f"News data could not be loaded: {ex}")
        st.exception(ex)
        return
    rt = render_news({**payload, "part": "top"}, key="news_top")
    left, right = st.columns([1.9, 1])
    with left:
        rm = render_news({**payload, "part": "main"}, key="news_main")
    with right:
        reads_section()
        insights_section()
        rs = render_news({**payload, "part": "side"}, key="news_side")
    for res in (rt, rm, rs):
        if res.open:
            st.session_state["company"] = res.open["t"]
            st.session_state.pop("report_id", None)
            go("research")
    if rt.digest:
        st.session_state["show_digest"] = True
    if st.session_state.get("show_digest"):
        st.divider()
        c1, c2 = st.columns([6, 1])
        c1.subheader("News Digest")
        if c2.button("Close", key="close_digest"):
            st.session_state.pop("show_digest", None)
            st.rerun()
        st.caption("Green = number found in the collected news data (hover to see source and passage), red = not found.")
        embed("news_digest.html", 2600)


# =============================================================== Protokoll / Einstellungen
def page_log():
    import glob as _glob
    ui_header("Log", "All agent runs with duration and cost, the chat questions, the evaluation and maintenance tools.")
    runs = []
    for f in sorted(_glob.glob(str(AIF / "research" / "pipeline_runs" / "*.json")), reverse=True):
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        steps = d.get("steps") or []
        runs.append({"stamp": d.get("started", Path(f).stem), "tickers": d.get("tickers") or [], "steps": steps,
                     "ok": sum(1 for x in steps if x.get("ok")), "cost": d.get("cost_usd"),
                     "sec": sum(x.get("seconds") or 0 for x in steps), "md": Path(f).with_suffix(".md")})
    chats = []
    lp = AIF / "research" / "chat_log.jsonl"
    if lp.exists():
        for line in lp.read_text(encoding="utf-8").splitlines():
            try:
                chats.append(json.loads(line))
            except Exception:
                pass
    tot_cost = sum(r["cost"] or 0 for r in runs) + sum(c.get("cost") or 0 for c in chats)
    fc_t = sum(c.get("fc_total") or 0 for c in chats)
    ui_kpis([("Runs", str(len(runs)), "pipeline and app"), ("Agent steps", str(sum(len(r["steps"]) for r in runs)),
              f"{sum(r['ok'] for r in runs)} successful"), ("Total cost", f"{tot_cost:.2f} USD", "runs and chat"),
             ("Chat questions", str(len(chats)), (f"{sum(c.get('fc_matched') or 0 for c in chats)}/{fc_t} numbers verified" if fc_t else "–"))])
    tab1, tab2, tab3, tab4 = st.tabs(["Runs", "Chat", "Evaluation", "Tools"])
    with tab4:
        tools_section()
    with tab1:
        if not runs:
            st.caption("No runs yet.")
        rows = [[escape(r["stamp"].replace("_", " ")), escape(", ".join(r["tickers"][:6]) + (" …" if len(r["tickers"]) > 6 else "")),
                 f"{r['ok']}/{len(r['steps'])}", f"{r['sec'] / 60:.0f} min", f"{r['cost']:.2f} USD" if r["cost"] is not None else "–"]
                for r in runs[:40]]
        if rows:
            html_table(["Start", "Holding", "Steps ok", "Duration", "Cost"], rows)
            pick = st.selectbox("Run details", [r["stamp"] for r in runs[:40]], index=None,
                                placeholder="Choose run …")
            if pick:
                r = next(x for x in runs if x["stamp"] == pick)
                show_steps({"steps": r["steps"], "done": None})
                if r["md"].exists():
                    with st.expander("Log as text"):
                        st.markdown(r["md"].read_text(encoding="utf-8"))
        st.divider()
        if st.button("Rebuild dashboard (without agent run)", icon=":material/refresh:"):
            from lib.html_site import build_site
            with st.spinner("Building dashboard pages and archive …"):
                build_site(current_tickers())
            st.toast("Dashboard updated")
    with tab2:
        if not chats:
            st.caption("No questions asked yet.")
        rows = [[escape(c.get("ts", "")[:16]), escape(c.get("question", "")[:110]),
                 f"{c.get('fc_matched')}/{c.get('fc_total')}" if c.get("fc_total") else "–", str(len(c.get("cited") or [])),
                 f"{c['cost']:.4f} USD" if isinstance(c.get("cost"), (int, float)) else "–"] for c in reversed(chats[-60:])]
        if rows:
            html_table(["Time", "Question", "Numbers verified", "Sources", "Cost"], rows)
    with tab3:
        mode = st.segmented_control("View", ["Evaluation", "Label sample"], default="Evaluation",
                                    key="eval_mode", label_visibility="collapsed")
        if mode == "Label sample":
            eval_labeling()
            return
        summ = AIF / "eval" / "summary.md"
        if summ.exists():
            ch = AIF / "eval" / "summary_chart.png"
            if ch.exists():
                st.image(str(ch))
            st.markdown(summ.read_text(encoding="utf-8"))
        else:
            st.caption("No evaluation yet – run evaluation.ipynb (creates eval/summary.md).")


LABEL_CSS = """<style>
.lb-card{border:1px solid rgba(128,128,128,.25);border-radius:14px;padding:16px 18px;margin:4px 0 10px}
.lb-card .meta{font-size:calc(15.5px*var(--bfs,1));color:rgba(128,128,128,1);margin-bottom:8px}
.lb-card .sent{font-size:calc(19px*var(--bfs,1));line-height:1.6}.lb-card mark{background:#F5C451;color:#1d2329;border-radius:3px;padding:0 3px}
.lb-src{margin-top:12px;padding:10px 12px;border-radius:10px;background:rgba(128,128,128,.08);font-size:calc(16.5px*var(--bfs,1));line-height:1.55}
.lb-src .h{font-weight:600;font-size:calc(15.5px*var(--bfs,1));margin-bottom:3px}.lb-src u{text-decoration-color:#1D9E75;text-underline-offset:2px}
</style>"""


def _mark(text, needle, words=()):
    """Text escapen, erste Fundstelle von needle markieren, Kontextwoerter unterstreichen."""
    import re as _re
    t = escape(str(text or ""))
    n = escape(str(needle or "")).strip()
    i = t.find(n) if n else -1
    if i < 0 and n:                                # "15 %" in der Quelle gegen "15%" im Report
        m = _re.search(_re.escape(n.replace(" ", "")).replace("%", r"\s?%"), t)
        i, n = (m.start(), m.group(0)) if m else (-1, n)

    def und(seg):
        for w in words:
            seg = _re.sub(r"\b(" + _re.escape(w) + r"[a-z]*)", r"<u>\1</u>", seg, count=1, flags=_re.I)
        return seg
    return und(t[:i]) + f"<mark>{n}</mark>" + und(t[i + len(n):]) if i >= 0 else und(t)


def eval_labeling():
    from lib import labeling as lb
    its = lb.items()
    if not its:
        st.caption("No sample – run scripts/eval_summary.py first (creates eval/manual_review_sample.csv).")
        return
    st.markdown(LABEL_CSS, unsafe_allow_html=True)
    s = lb.stats(its)
    pc = lambda v: "–" if v is None else f"{v * 100:.0f} %"
    ui_kpis([("Labelled", f"{s['labelled']} / {s['total']}", f"{s['unsure']} unklar"),
             ("Found and correct", pc(s["found_correct"]), f"n = {s['found_n']} · fact check says found"),
             ("Not found but correct", pc(s["notfound_correct"]), f"n = {s['notfound_n']} · e.g. computed numbers"),
             ("Context matches: correct", pc(s["ctx_ok_correct"]), f"n = {s['ctx_ok_n']} · green"),
             ("Number only: correct", pc(s["ctx_no_correct"]), f"n = {s['ctx_no_n']} · yellow")])
    st.caption("Per number: is it correct in the context of the sentence? The source passage is shown below with the number "
               "highlighted. The order is random; 100–150 numbers already give a usable estimate.")
    c1, c2, c3 = st.columns([1.2, 1.4, 1])
    grp = c1.selectbox("Group", ["all", "found", "not found"], key="lb_grp")
    reps = sorted({x["report"] for x in its})
    rsel = c2.selectbox("Report", ["all"] + reps, key="lb_rep")
    only_open = c3.toggle("open only", value=True, key="lb_open")
    pool = [x for x in its if (grp == "all" or (x["group"] == "found") == (grp == "found"))
            and (rsel == "all" or x["report"] == rsel) and (not only_open or not x["label"])]
    if not pool:
        st.success("Everything in this selection is labelled.")
    else:
        x = pool[0]
        ev = x.get("evidence") or {}
        status = ("<span class='ui-pill wait'>number found, different context</span>" if x.get("context_ok") is False
                  else "<span class='ui-pill ok'>found by fact check</span>" if x["group"] == "found"
                  else "<span class='ui-pill no'>not found</span>")
        src_html = ""
        if x["group"] == "found":
            where = ev.get("origin") or x["source"] or "Source"
            snip = ev.get("snippet")
            src_html = (f"<div class='lb-src'><div class='h'>Source: {escape(where)}</div>"
                        + (f"„{_mark(snip, ev.get('hl') or x['figure'].lstrip('$'), ev.get('context_words') or ())}“" if snip
                           else "<span class='small'>No passage stored (older report).</span>") + "</div>")
        st.markdown(f"<div class='lb-card'><div class='meta'><span class='ui-pill'>{escape(x['report'])}</span> "
                    f"{escape(x['section'])} &nbsp; {status} &nbsp; {len(pool)} left</div>"
                    f"<div class='sent'>{_mark(x['context'], x['figure'])}</div>{src_html}</div>", unsafe_allow_html=True)
        b1, b2, b3, b4, _ = st.columns([1, 1, 1, 1.4, 2])
        for col, lab, val, typ in ((b1, "Correct", "1", "primary"), (b2, "Wrong", "0", "secondary"),
                                   (b3, "Unclear", "u", "secondary")):
            if col.button(lab, key=f"lb_{val}_{x['i']}", type=typ, use_container_width=True):
                lb.set_label(x["i"], val)
                st.session_state["lb_last"] = x["i"]
                st.rerun()
        if st.session_state.get("lb_last") is not None and b4.button("Undo last", key="lb_undo"):
            lb.set_label(st.session_state.pop("lb_last"), "")
            st.rerun()


def page_settings():
    s = ab.load_settings()
    done = [s["openrouter"], s["SEC_USER_AGENT"], s["FINNHUB_API_KEY"]]
    ui_header("Settings", "Setup guide, keys and display. Everything stays local on this computer – keys are stored in "
                          "finrobot_autogen/config_api_keys and OAI_CONFIG_LIST and never go to Git.")
    if not all(done):
        st.info(f"**Welcome to BLUMBÖRG.** Three keys and you can start – about 5 minutes. {sum(done)} of 3 done.",
                icon=":material/waving_hand:")
    ok = lambda b: "<span class='ui-pill ok'>done</span>" if b else "<span class='ui-pill wait'>missing</span>"

    def step(n, title, status, text, links):
        st.markdown(f"<div class='ui-step'><span class='ui-num'>{n}</span><b>{title}</b> &nbsp;{status}</div>"
                    f"<div class='small' style='margin:2px 0 8px'>{text}</div>", unsafe_allow_html=True)
        if links:
            cs = st.columns(len(links) + 1)
            for c, (lab, url) in zip(cs, links):
                c.link_button(lab, url, icon=":material/open_in_new:")

    with st.container(border=True):
        step(1, "OpenRouter – the language model (required)", ok(s["openrouter"]),
             "OpenRouter gives one key for many models (default: Claude Haiku). Create an account, add credits (prepaid, "
             "from $5), then create a key. Set a credit limit on the key – a full first run with the DEMO portfolio costs "
             "roughly $1–3.", [("Add credits", "https://openrouter.ai/credits"), ("Create key", "https://openrouter.ai/keys")])
        c1, c2, c3 = st.columns([3, 1, 1])
        orr = c1.text_input("OpenRouter API key", type="password", placeholder="sk-or-v1-…", label_visibility="collapsed",
                            key="set_orr")
        if c2.button("Save", key="set_orr_save", type="primary", disabled=not orr):
            ab.save_settings(openrouter_key=orr.strip())
            st.session_state["set_msg"] = ("ok", "OpenRouter key saved.")
            st.rerun()
        if c3.button("Test", key="set_orr_test", disabled=not s["openrouter"]):
            good, msg = ab.test_openrouter()
            (st.success if good else st.error)(f"OpenRouter: {msg}")
    with st.container(border=True):
        step(2, "SEC user agent – no account needed (required)", ok(s["SEC_USER_AGENT"]),
             "SEC EDGAR is free, but the SEC asks every program to identify itself with a name and an e-mail address. "
             "Just type yours, e.g. <code>Jane Doe jane@uni.edu</code>. It is only sent to the SEC.",
             [("SEC fair-access rules", "https://www.sec.gov/os/accessing-edgar-data")])
        c1, c2, c3 = st.columns([3, 1, 1])
        ua = c1.text_input("SEC user agent", placeholder="First Last name@example.com", label_visibility="collapsed",
                           key="set_ua")
        if c2.button("Save", key="set_ua_save", type="primary", disabled=not ua):
            ab.save_settings(SEC_USER_AGENT=ua.strip())
            ab.register_keys()
            st.session_state["set_msg"] = ("ok", "SEC user agent saved.")
            st.rerun()
        if c3.button("Test", key="set_ua_test", disabled=not s["SEC_USER_AGENT"]):
            good, msg = ab.test_sec()
            (st.success if good else st.error)(f"SEC: {msg}")
    with st.container(border=True):
        step(3, "Finnhub – company news and peers (free)", ok(s["FINNHUB_API_KEY"]),
             "Register for the free plan; the key is shown on your dashboard right after sign-up.",
             [("Register", "https://finnhub.io/register"), ("Dashboard (key)", "https://finnhub.io/dashboard")])
        c1, c2, c3 = st.columns([3, 1, 1])
        fh = c1.text_input("Finnhub API key", type="password", label_visibility="collapsed", key="set_fh")
        if c2.button("Save", key="set_fh_save", type="primary", disabled=not fh):
            ab.save_settings(FINNHUB_API_KEY=fh.strip())
            ab.register_keys()
            st.session_state["set_msg"] = ("ok", "Finnhub key saved.")
            st.rerun()
        if c3.button("Test", key="set_fh_test", disabled=not s["FINNHUB_API_KEY"]):
            good, msg = ab.test_finnhub()
            (st.success if good else st.error)(f"Finnhub: {msg}")
    if st.session_state.get("set_msg"):
        kind, msg = st.session_state.pop("set_msg")
        st.toast(msg)
    with st.container(border=True):
        st.markdown("<div class='ui-step'><span class='ui-num'>✓</span><b>No key needed</b></div><div class='small'>"
                    "<b>Yahoo Finance</b> (prices, financial statements, consensus, ETF holdings) through the open-source "
                    "<code>yfinance</code> library – free, unofficial, quotes delayed; Yahoo occasionally slows down "
                    "requests, then simply try again later. <b>Google News</b> (RSS), <b>SEC EDGAR</b> (10-K, 10-Q, 8-K), "
                    "<b>Deutsche Bundesbank</b> (5-year Bund yield).</div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("<div class='ui-step'><span class='ui-num'>4</span><b>Try it with the DEMO portfolio</b></div>"
                    "<div class='small' style='margin:2px 0 8px'>The DEMO portfolio rebuilds Valley Forge Capital's "
                    "positions since 2016 from its public 13F filings. Under Setup and automation → Analysis choose "
                    "<b>DEMO · Valley Forge (13F)</b>, click <b>Create plan</b> and <b>Start analysis</b>. The first full "
                    "run takes about 1–1.5 hours and runs in the background.</div>", unsafe_allow_html=True)
        if st.button("Go to Analysis", icon=":material/arrow_forward:", disabled=not all(done), key="set_go"):
            go("run")
    with st.expander("Advanced: models and optional keys"):
        with st.form("keys_adv"):
            models = st.text_input("Models offered in the app (comma-separated OpenRouter model IDs)",
                                   value=", ".join(s["models"] or ["anthropic/claude-haiku-5.5"]),
                                   help="e.g. anthropic/claude-haiku-5.5, google/gemini-4-neon – the model list on "
                                        "openrouter.ai/models shows the IDs.")
            sa = st.text_input("sec-api.io key (optional, only a fallback for 10-K sections)", type="password")
            if st.form_submit_button("Save"):
                ab.save_settings(models=[m.strip() for m in models.split(",") if m.strip()], SEC_API_KEY=sa)
                st.success("Saved.")
                st.rerun()
    ui = ab.load_ui()
    with st.container(border=True):
        st.markdown("**Display and interests**")
        fs = st.segmented_control("Font size", list(ab.FONT_SCALES), default=ui["font"], key="ui_font",
                                  format_func=lambda k: {"Klein": "Small", "Normal": "Normal", "Groß": "Large", "Sehr groß": "Extra large"}.get(k, k))
        if fs and fs != ui["font"]:
            ab.save_ui(font=fs)
            st.rerun()
        with st.form("ui_int", border=False):
            interests = st.text_area("Your interests (for the reading picks on the News page)", value=ui["interests"],
                                     placeholder="e.g. value and quality investing, AI infrastructure, semiconductors, "
                                                 "capital allocation, fund letters, CEO interviews", height=90)
            if st.form_submit_button("Save interests"):
                ab.save_ui(interests=interests.strip())
                st.success("Saved. The next reading picks will take this into account.")


def page_agents():
    """Agenten bearbeiten: Prompts, Zusatzanweisungen, Parameter, Modell (lokal, versioniert, Reset auf Standard)."""
    from lib import agent_settings as AS
    ui_header("Agents", "How each agent works: prompts, extra instructions, parameters and model. Changes stay on this "
                        "computer and apply from the next run; every saved version is kept and the defaults in the code "
                        "are never overwritten. The fact check is not part of the prompts and cannot be switched off.")
    left, right = st.columns([1.25, 3])
    with left:
        sel = st.radio("Agent", [a["key"] for a in AS.AGENTS], key="ag_sel", label_visibility="collapsed",
                       format_func=lambda k: next(a["name"] for a in AS.AGENTS if a["key"] == k) + ("  ●" if AS.changed(k) else ""))
        st.caption("● = changed by you")
    a = next(x for x in AS.AGENTS if x["key"] == sel)
    with right:
        st.markdown(f"#### {escape(a['name'])}", unsafe_allow_html=True)
        st.markdown("<div class='ag-info'>" + "".join(
            f"<div class='r'><b>{lab}</b><span>{escape(a.get(k) or '–')}</span></div>"
            for lab, k in (("What it does", "what"), ("Sources", "sources"), ("Result", "output"), ("When it runs", "when")))
            + "</div>", unsafe_allow_html=True)
        if sel != "style":
            models = ab.load_settings()["models"] or ["anthropic/claude-haiku-5.5"]
            cur = AS.model(sel)
            opts = ["(default model)"] + [m for m in models if m]
            if cur and cur not in opts:
                opts.append(cur)
            m = st.selectbox("Model", opts, index=opts.index(cur) if cur in opts else 0, key=f"ag_model_{sel}",
                             help="Model for this agent only; '(default model)' uses the model chosen for the run.")
            newm = None if m == "(default model)" else m
            if newm != cur:
                AS.set_model(sel, newm)
                st.toast("Model saved")
        for x in a["params"]:
            v = AS.param(x["key"], x["default"])
            if x["kind"] == "pct":
                nv = st.slider(x["label"], int(round(x["lo"] * 100)), int(round(x["hi"] * 100)), int(round(v * 100)),
                               step=1, format="%d%%", help=x["help"] or None, key=f"ag_p_{x['key']}") / 100
            else:
                nv = st.slider(x["label"], int(x["lo"]), int(x["hi"]), int(v), step=int(x["step"]),
                               help=x["help"] or None, key=f"ag_p_{x['key']}")
            if abs(nv - v) > 1e-9:
                AS.set_param(x["key"], nv)
                st.toast("Parameter saved")
        if a["params"] and any(x["key"] in AS.load()["params"] for x in a["params"]):
            if st.button("Reset parameters", key=f"ag_pr_{sel}"):
                for x in a["params"]:
                    AS.set_param(x["key"], None)
                    st.session_state.pop(f"ag_p_{x['key']}", None)
                st.rerun()
        for p in a["prompts"]:
            d = AS.load()
            try:
                dflt = AS.default(p["key"])
            except Exception as ex:
                st.error(f"Default prompt could not be loaded: {ex}")
                continue
            edited = p["key"] in d["prompts"]
            st.markdown(f"**{escape(p['label'])}** " + ("<span class='ui-pill run'>edited</span>" if edited else
                                                       "<span class='ui-pill'>default</span>")
                        + (f"<br><span class='small'>{escape(p['help'])}</span>" if p["help"] else ""), unsafe_allow_html=True)
            if p["template"]:
                st.caption("Words in {braces} are filled in by the app and must stay in the text; write literal braces "
                           "as {{ and }}.")
            k = f"ag_txt_{p['key']}"
            txt = st.text_area(p["label"], d["prompts"].get(p["key"]) or dflt, height=300, key=k, label_visibility="collapsed")
            c1, c2, _ = st.columns([1, 1.4, 3])
            if c1.button("Save", key=f"ag_save_{p['key']}", type="primary"):
                try:
                    AS.set_prompt(p["key"], txt)
                    st.toast("Saved – used from the next run")
                    st.rerun()
                except ValueError as ex:
                    st.error(str(ex))
            if edited and c2.button("Reset to default", key=f"ag_rst_{p['key']}"):
                AS.reset_prompt(p["key"])
                st.session_state.pop(k, None)
                st.rerun()
            hist = AS.history(p["key"])
            if hist:
                with st.expander(f"Versions ({len(hist)})"):
                    for i, h in enumerate(hist[:10]):
                        h1, h2 = st.columns([4, 1])
                        h1.markdown(f"<span class='small'>{escape(h['ts'].replace('T', ' '))}</span>", unsafe_allow_html=True)
                        if h["text"] != "(reset to default)" and h2.button("Restore", key=f"ag_res_{p['key']}_{i}"):
                            try:
                                AS.set_prompt(p["key"], h["text"])
                                st.session_state.pop(k, None)
                                st.rerun()
                            except ValueError as ex:
                                st.error(str(ex))
                        st.code(h["text"][:2500] + ("…" if len(h["text"]) > 2500 else ""), language=None)
        if a["extra"]:
            ek = f"ag_ex_{a['extra']}"
            st.markdown("**Extra instructions** <span class='small'>· appended to the agent's task, e.g. what to focus on; "
                        "leave empty for none</span>", unsafe_allow_html=True)
            ex_txt = st.text_area("Extra instructions", AS.load()["extras"].get(a["extra"], ""), height=110, key=ek,
                                  label_visibility="collapsed",
                                  placeholder="e.g. Always compare margins with the two closest peers and name the main "
                                              "risk to the dividend.")
            if st.button("Save extra instructions", key=f"ag_exs_{sel}"):
                AS.set_extra(a["extra"], ex_txt)
                st.toast("Saved – used from the next run")
        if sel in ("annual_report", "earnings_review"):
            with st.container(border=True):
                st.markdown("**Test the change on one company** <span class='small'>· rebuilds this report in the "
                            "background (annual report ≈ $0.10, earnings review ≈ $0.04)</span>", unsafe_allow_html=True)
                from lib import company_data as cd
                tick = sorted({c["t"] for c in cd.companies()})
                if tick:
                    t1, t2 = st.columns([2, 1])
                    tt = t1.selectbox("Company", tick, key=f"ag_tt_{sel}", label_visibility="collapsed")
                    if t2.button("Run test", key=f"ag_tb_{sel}", icon=":material/play_arrow:"):
                        _start_company_run(tt, steps=[sel], label=f"{tt}: test {a['name']}",
                                           extra={"plan_args": {"force": [sel]}})


TOOLS = [("Score forecasts", "score_forecasts.py", [], "Checks last week's forecasts against the actual price moves (forecasts/forecast_log.csv)."),
         ("Evaluation summary", "eval_summary.py", [], "Collects all fact checks and runs into eval/summary.md and draws the manual review sample."),
         ("Evaluation report", "eval_report.py", [], "Writes the evaluation for the course report (Markdown and chart in eval/)."),
         ("Fact-check error rate", "factcheck_fpr.py", [], "How often the fact check accepts a wrong number (eval/fpr_results.csv)."),
         ("Rebuild DEMO portfolio from 13F", "build_13f_portfolio.py", ["--cik", "1697868", "--name", "sample_transactions_vfc"],
          "Downloads Valley Forge's 13F filings again and rebuilds the DEMO transactions."),
         ("Compare SEC sections with sec-api", "compare_sec_api.py", [], "Own 10-K/10-Q splitting vs. sec-api.io on the same filings."),
         ("Check foreign filers", "check_foreign_filer.py", ["ASML", "TSM", "MA"], "Data check for 20-F issuers before a run (no model, no cost)."),
         ("App test (all pages)", "test_app.py", [], "Opens every page of the app and reports crashes (takes a few minutes).")]


def tools_section():
    """Wartungs-Skripte per Knopf (statt VS Code). Laufen als eigener Prozess; Ausgabe in research/tool_runs/."""
    import subprocess
    out_dir = AIF / "research" / "tool_runs"
    st.caption("Maintenance scripts that used to be run from VS Code. Each runs in the background; the output appears "
               "below and is saved in research/tool_runs/.")
    procs = st.session_state.setdefault("tool_procs", {})
    for i, (label, script, args, desc) in enumerate(TOOLS):
        log = out_dir / f"{Path(script).stem}.log"
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{escape(label)}**<br><span class='small'>{escape(desc)}</span>", unsafe_allow_html=True)
            p = procs.get(script)
            running = p is not None and p.poll() is None
            if c2.button("Running …" if running else "Run", key=f"tool_{i}", disabled=running, icon=None if running else ":material/play_arrow:"):
                out_dir.mkdir(parents=True, exist_ok=True)
                env = dict(os.environ, PYTHONIOENCODING="utf-8")
                fh = open(log, "w", encoding="utf-8")
                procs[script] = subprocess.Popen([sys.executable, str(AIF / "scripts" / script), *args], cwd=str(AIF.parent),
                                                 stdout=fh, stderr=subprocess.STDOUT, env=env)
                st.rerun()
            if log.exists():
                txt = log.read_text(encoding="utf-8", errors="replace")
                state = "running" if running else ("finished" if p is None or p.returncode == 0 else f"exit code {p.returncode}")
                with st.expander(f"Output ({state}, {time.strftime('%d %b %H:%M', time.localtime(log.stat().st_mtime))})", expanded=running):
                    st.code(txt[-6000:] or "(no output yet)", language=None)
    if any(p.poll() is None for p in procs.values()):
        if st.button("Refresh output", icon=":material/refresh:"):
            st.rerun()


PAGE_DEFS = [("home", "Overview", ":material/space_dashboard:", page_home, "Today"),
             ("news", "News", ":material/newspaper:", page_news, "Today"),
             ("portfolio", "Portfolio", ":material/donut_large:", page_portfolio, "Analysis"),
             ("analysis", "Portfolio analysis", ":material/query_stats:", page_analysis, "Analysis"),
             ("research", "Company research", ":material/domain:", page_research, "Analysis"),
             ("chat", "Ask", ":material/forum:", page_chat, "Analysis"),
             ("run", "Setup and automation", ":material/tune:", page_run, "System"),
             ("agents", "Agents", ":material/smart_toy:", page_agents, "System"),
             ("log", "Log", ":material/receipt_long:", page_log, "System"),
             ("settings", "Settings", ":material/settings:", page_settings, "System")]
_default = os.environ.get("BLUMBOERG_TEST_PAGE") or (
    "settings" if not (ab.load_settings()["openrouter"] and ab.load_settings()["SEC_USER_AGENT"])   # neue Nutzer: Setup-Guide
    else "home" if ab.latest_brief()[0] else "run")   # Seitentest: scripts/test_app.py
PAGE_OBJ = {k: st.Page(fn, title=t, icon=ic, url_path=k, default=(k == _default)) for k, t, ic, fn, _ in PAGE_DEFS}
_sections = {}
for _k, _t, _ic, _fn, _sec in PAGE_DEFS:
    _sections.setdefault(_sec, []).append(PAGE_OBJ[_k])
_nav = st.navigation(_sections, position="sidebar")
brand_header()
portfolio_switcher()
status_bar()
_nav.run()
