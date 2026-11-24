"""
Franci's FINRobot - App (Streamlit). Start: start.bat (Windows) oder `streamlit run ai_in_finance/app/app.py`.
Portfolio-Datei hochladen -> Plan und Kosten ansehen -> kompletter Lauf aller Agenten -> Dashboard mit Reitern.
"""
import json
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
from lib import app_backend as ab  # noqa: E402

st.set_page_config(page_title="Franci's FINRobot", page_icon="📈", layout="wide")
st.markdown("""<style>
.lvl-decide{color:#B03A2E;font-weight:700}.lvl-read{color:#B9770E;font-weight:700}.lvl-none{color:#2D8A4E;font-weight:700}
table.fr{border-collapse:collapse;width:100%;font-size:14px}table.fr th{background:#0F4C5C;color:#fff;text-align:left;padding:6px 8px}
table.fr td{padding:6px 8px;border-bottom:1px solid #e6e8eb;vertical-align:top}.small{color:#5A6472;font-size:13px}
</style>""", unsafe_allow_html=True)

LEVEL = {"decide": "Entscheidung nötig", "read": "Einlesen", "none": "Kein Handlungsbedarf"}
PAGES = ["▶ Analyse starten", "🏠 Home", "📊 Portfolio", "🔎 Research", "📰 News", "🧾 Protokoll", "⚙ Einstellungen"]


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


# =============================================================== Seitenleiste
with st.sidebar:
    st.markdown("### Franci's FINRobot")
    page = st.radio("Bereich", PAGES, label_visibility="collapsed")
    lr = ab.latest_run()
    if lr:
        stt = ab.run_status(lr)
        if stt["alive"]:
            st.info(f"Lauf aktiv seit {stt['cfg']['started'][11:16]} Uhr")
    s = ab.load_settings()
    if not s["openrouter"]:
        st.warning("Kein OpenRouter-Schlüssel – unter ⚙ Einstellungen eintragen.")
    st.caption("Nur für akademische Zwecke, keine Anlageberatung.")


# =============================================================== Analyse starten
def page_run():
    st.title("Analyse starten")
    st.write("Portfolio-Datei wählen, Plan prüfen, starten. Die Agenten laufen im Hintergrund weiter, auch wenn du "
             "die Seite wechselst.")
    lr = ab.latest_run()
    if lr and ab.run_status(lr)["alive"]:
        progress(lr)
        return
    c1, c2 = st.columns([1, 1])
    with c1:
        src = st.radio("Portfolio", ["Datei hochladen", "Vorhandene Datei"], horizontal=True)
        path = None
        if src == "Datei hochladen":
            up = st.file_uploader("CSV: ticker,weight · ticker,shares · Export von Trade Republic, Scalable oder "
                                  "Smartbroker", type=["csv"])
            if up:
                path = ab.save_upload(up.name, up.getvalue())
        else:
            files = ab.sample_files()
            if files:
                f = st.selectbox("Datei", files, format_func=lambda p: p.name)
                path = f
    with c2:
        st.markdown("**Formate**")
        st.markdown("<div class='small'>Gewichte: <code>ticker,weight</code> (z. B. <code>GOOG,14</code>) · Stückzahlen: "
                    "<code>ticker,shares</code> · Broker-Exporte mit Käufen und Verkäufen ergeben zusätzlich die echte "
                    "Performance (Rendite gegen MSCI ACWI, Attribution, Ausstiege, Fehler und Lehren).</div>",
                    unsafe_allow_html=True)
    if not path:
        return
    try:
        info = inspect_cached(str(path), Path(path).stat().st_mtime)
    except Exception as e:
        st.error(f"Datei nicht lesbar: {e}")
        return
    kind = {"weights": "Gewichte", "shares": "Stückzahlen", "transactions": "Transaktionen (Broker-Export)"}[info["kind"]]
    st.success(f"Erkannt: {kind}, {len(info['positions'])} Positionen")
    for i in info["issues"][:5]:
        st.caption(f"Hinweis: {i}")
    st.dataframe(pd.DataFrame(info["positions"]), hide_index=True, use_container_width=True, height=min(38 * (len(info['positions']) + 1), 320))
    tickers = st.multiselect("Positionen für die Research-Agenten", info["tickers"], default=info["tickers"][:15])
    o1, o2 = st.columns(2)
    with o1:
        models = ab.load_settings()["models"] or ["anthropic/claude-haiku-5.5"]
        model = st.selectbox("Modell", models)
    with o2:
        comm = st.checkbox("Investment Committee einschließen (langsam und teuer: bis zu 90 Min. und ca. 1–2 USD je "
                           "Titel, liefert oft kein Kursziel)", value=False)
    if st.button("Plan erstellen", type="secondary"):
        with st.spinner("Prüfe SEC-Einreichungen und vorhandene Reports …"):
            st.session_state["plan"] = ab.make_plan(tickers, include_committee=comm)
            st.session_state["plan_for"] = (str(path), tuple(tickers), comm)
    plan = st.session_state.get("plan")
    if plan and st.session_state.get("plan_for") == (str(path), tuple(tickers), comm):
        st.subheader("Plan")
        rows = [[ab.STEP_LABEL.get(s["step"], s["step"]), escape(s["ticker"]), escape(s["reason"])] for s in plan["steps"]]
        html_table(["Schritt", "Titel", "Grund"], rows)
        if plan["skipped"]:
            st.caption("Ohne 10-K (nur News, Prognose entfällt, Portfolio): " +
                       ", ".join(s["ticker"] for s in plan["skipped"]))
        if plan["committee_held"]:
            st.caption(f"Committee fällig für {len(plan['committee_held'])} Titel, aber ausgeschaltet.")
        st.info(f"Geschätzt: ca. {plan['minutes']} Minuten, ca. {plan['usd']:.2f} USD (Erfahrungswerte; bereits "
                f"vorhandene Reports werden nicht neu erstellt).")
        if not ab.load_settings()["openrouter"]:
            st.error("Zuerst unter ⚙ Einstellungen den OpenRouter-Schlüssel eintragen.")
        elif st.button("Analyse starten", type="primary"):
            stamp = ab.start_run(info, tickers, include_committee=comm, model=model)
            st.session_state.pop("plan", None)
            st.success(f"Gestartet ({stamp}).")
            time.sleep(1)
            st.rerun()
    if lr:
        stt = ab.run_status(lr)
        if stt["done"]:
            with st.expander(f"Letzter Lauf {lr}: " + ("abgeschlossen" if stt["done"].get("ok") else "mit Fehler")):
                show_steps(stt)


@st.cache_data(show_spinner="Lese Portfolio …")
def inspect_cached(path, mtime):
    return ab.inspect_portfolio(path)


def show_steps(stt):
    rows = []
    for s in stt["steps"]:
        ok = "✅" if s.get("ok") else "❌"
        rows.append([ok, ab.STEP_LABEL.get(s["step"], s["step"]), escape(s["ticker"]), f"{s.get('seconds', '')} s",
                     f"{s['cost_usd']:.3f}" if isinstance(s.get("cost_usd"), (int, float)) else "–",
                     escape(str(s.get("error") or s.get("result") or ""))[:120]])
    if rows:
        html_table(["", "Schritt", "Titel", "Dauer", "USD", "Hinweis"], rows)
    if stt["done"] and stt["done"].get("error"):
        st.error(stt["done"]["error"])


def progress(stamp):
    @st.fragment(run_every=5)
    def _box():
        stt = ab.run_status(stamp)
        n, tot = len(stt["steps"]), stt["total"] or max(len(stt["steps"]), 1)
        if stt["done"]:
            st.success("Lauf abgeschlossen. Ergebnisse unter 🏠 Home, 📊 Portfolio und 🔎 Research."
                       if stt["done"].get("ok") else "Lauf beendet mit Fehler.")
        elif not stt["alive"]:
            st.warning("Der Lauf wurde unterbrochen (Prozess nicht mehr aktiv).")
        else:
            st.info(f"Läuft … {n} von {tot} Schritten erledigt.")
        st.progress(min(n / tot, 1.0))
        show_steps(stt)
        with st.expander("Live-Protokoll"):
            st.code("\n".join(stt["tail"]) or "…", language=None)
        if stt["done"] or not stt["alive"]:
            if st.button("Neue Analyse"):
                st.rerun()
    _box()


# =============================================================== Home
def page_home():
    st.title("Home")
    data, texts = ab.latest_brief()
    tickers = current_tickers()
    if not data:
        st.info("Noch kein Weekly Brief vorhanden – zuerst unter ▶ Analyse starten einen Lauf machen.")
        return
    n = {k: sum(p["level"] == k for p in data["positions"]) for k in LEVEL}
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Entscheidung nötig", n["decide"])
    m2.metric("Einlesen", n["read"])
    m3.metric("Kein Handlungsbedarf", n["none"])
    m4.metric("Stand", data["date"])
    if texts.get("headline"):
        st.markdown(f"#### {escape(texts['headline'])}")
    if texts.get("summary"):
        st.write(texts["summary"])
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Nächste Schritte")
        items = {str(x.get("ticker", "")).upper(): x for x in texts.get("items") or []}
        any_ = False
        for p in data["positions"]:
            if p["level"] == "none":
                continue
            any_ = True
            it = items.get(p["ticker"].upper(), {})
            w = f" · Gewicht {p['weight'] * 100:.1f}%" if isinstance(p.get("weight"), (int, float)) else ""
            st.markdown(f"<span class='lvl-{p['level']}'>{LEVEL[p['level']]}</span> **{escape(p['ticker'])}**{w}",
                        unsafe_allow_html=True)
            if it.get("what"):
                st.markdown(f"<div class='small'>{escape(it['what'])}</div>", unsafe_allow_html=True)
            if it.get("next_step"):
                st.markdown(f"➜ {escape(it['next_step'])}")
            else:
                st.markdown("<div class='small'>" + "<br>".join(escape(t["text"]) for t in p["triggers"][:3]) + "</div>",
                            unsafe_allow_html=True)
        if not any_:
            st.write("Keine Position mit Handlungsbedarf.")
        st.subheader("Action Board")
        rows = [[f"<b>{escape(p['ticker'])}</b>",
                 f"{p['weight'] * 100:.1f}%" if isinstance(p.get("weight"), (int, float)) else "–",
                 f"<span class='lvl-{p['level']}'>{LEVEL[p['level']]}</span>",
                 "<br>".join(escape(t["text"]) for t in p["triggers"][:3]) or "<span class='small'>kein Auslöser</span>"]
                for p in data["positions"]]
        html_table(["Position", "Gewicht", "Stufe", "Warum (regelbasiert)"], rows)
        if data.get("gaps"):
            with st.expander(f"Datenlücken ({len(data['gaps'])})"):
                for g in data["gaps"]:
                    st.write("– " + g)
    with right:
        st.subheader("Termine")
        try:
            from lib import events as ev
            if st.button("Termine aktualisieren"):
                st.session_state["ev_refresh"] = True
            e = ev.events(tickers, refresh=st.session_state.pop("ev_refresh", False))
            up = [x for x in e["upcoming"] if x["date"] <= (date.fromordinal(date.today().toordinal() + 75)).isoformat()]
            if up:
                html_table(["Datum", "Titel", "Termin"], [[x["date"], escape(x["ticker"]), escape(x["type"]) +
                                                          (f" <span class='small'>({escape(x['detail'])})</span>" if x.get("detail") else "")]
                                                         for x in up])
            else:
                st.caption("Keine Termine im Yahoo-Kalender für die nächsten 75 Tage.")
            if e["announced"]:
                st.markdown("**In den News angekündigt**")
                for x in e["announced"][:6]:
                    link = f"[{escape(x['detail'])}]({x['url']})" if x.get("url") else escape(x["detail"])
                    st.markdown(f"<div class='small'>{x['date']} · {escape(x['ticker'])}</div>", unsafe_allow_html=True)
                    st.markdown(link)
            st.caption(f"Quellen: Yahoo-Kalender und gesammelte News · Stand {e['updated']}")
        except Exception as ex:
            st.caption(f"Termine nicht verfügbar: {ex}")
        st.subheader("Aktuelle News")
        news = ab.notable_news(tickers)
        if not news:
            st.caption("Keine wesentlichen Meldungen der letzten 10 Tage im News-Speicher.")
        for s_ in news:
            arrow = {"positive": "🟢", "negative": "🔴"}.get(s_.get("direction"), "⚪")
            car = f" · Kursreaktion {s_['car01'] * 100:+.1f}%" if isinstance(s_.get("car01"), (int, float)) else ""
            st.markdown(f"{arrow} <span class='small'>{s_['date'][:10]} · {escape(s_['ticker'])}{car}</span>",
                        unsafe_allow_html=True)
            st.markdown(f"[{escape(s_.get('title', '')[:140])}]({s_.get('url', '')})" if s_.get("url") else
                        escape(s_.get("title", "")[:140]))


# =============================================================== Portfolio / Research / News
def embed(name, height):
    html = ab.site_page(name)
    if not html:
        st.info("Noch nicht vorhanden – zuerst einen Lauf machen oder unter 🧾 Protokoll das Dashboard neu erzeugen.")
        return
    components.html(html, height=height, scrolling=True)


def page_portfolio():
    st.title("Portfolio")
    embed("portfolio.html", 5200)


def page_research():
    st.title("Research")
    reps = ab.research_reports()
    if not reps:
        st.info("Noch keine Research-Reports.")
        return
    t = st.selectbox("Titel", list(reps))
    kinds = [k for k in ("annual", "earnings") if k in reps[t]]
    k = st.radio("Report", kinds, horizontal=True,
                 format_func=lambda x: {"annual": "Annual Report (10-K)", "earnings": "Earnings & Thesis Update"}[x])
    pdf = ab.report_pdf(t, k)
    if pdf and pdf.exists():
        st.download_button("PDF herunterladen", pdf.read_bytes(), file_name=pdf.name, mime="application/pdf")
    st.caption("Grün = Zahl in den Quellen gefunden (Maus darüber zeigt die Quelle), rot = nicht gefunden.")
    embed(reps[t][k], 3200)


def page_news():
    st.title("News")
    try:
        from lib import pipeline as pl
        n = pl.last_news()
        stories = n.get("stories") or {}
        if stories:
            st.subheader("Laufende Storylines")
            rows = [[escape(t), escape(x["title"]), escape(x["status"]), x.get("since", "")]
                    for t, xs in stories.items() for x in xs]
            html_table(["Titel", "Story", "Status", "seit"], rows)
    except Exception:
        pass
    st.subheader("News Digest")
    embed("news_digest.html", 2600)


# =============================================================== Protokoll / Einstellungen
def page_log():
    st.title("Protokoll")
    if st.button("Dashboard neu erzeugen (ohne Agentenlauf)"):
        from lib.html_site import build_site
        with st.spinner("Erzeuge Dashboard …"):
            build_site(current_tickers())
        st.success("Dashboard aktualisiert.")
    runs = ab.pipeline_runs()
    if runs:
        f = st.selectbox("Pipeline-Lauf", runs, format_func=lambda p: p.stem)
        st.markdown(f.read_text(encoding="utf-8"))
    summ = AIF / "eval" / "summary.md"
    if summ.exists():
        with st.expander("Evaluation (eval/summary.md)"):
            st.markdown(summ.read_text(encoding="utf-8"))
            ch = AIF / "eval" / "summary_chart.png"
            if ch.exists():
                st.image(str(ch))


def page_settings():
    st.title("Einstellungen")
    s = ab.load_settings()
    ok = lambda b: "✅ gesetzt" if b else "— fehlt"
    st.write(f"OpenRouter: {ok(s['openrouter'])} · SEC User-Agent: {ok(s['SEC_USER_AGENT'])} · Finnhub: "
             f"{ok(s['FINNHUB_API_KEY'])} · sec-api: {ok(s['SEC_API_KEY'])}")
    st.caption("Die Schlüssel werden nur lokal in finrobot_autogen/config_api_keys und OAI_CONFIG_LIST gespeichert. "
               "Leere Felder lassen vorhandene Werte unverändert.")
    with st.form("keys"):
        orr = st.text_input("OpenRouter API-Schlüssel (Pflicht, openrouter.ai)", type="password")
        models = st.text_input("Modelle (kommagetrennt)", value=", ".join(s["models"] or ["anthropic/claude-haiku-5.5"]))
        ua = st.text_input("SEC User-Agent: Name und E-Mail (Pflicht für SEC EDGAR, z. B. 'Max Muster max@uni.de')")
        fh = st.text_input("Finnhub API-Schlüssel (für News, kostenlos bei finnhub.io)", type="password")
        sa = st.text_input("sec-api.io Schlüssel (für 10-K-Abschnitte, kostenloses Kontingent)", type="password")
        if st.form_submit_button("Speichern", type="primary"):
            ab.save_settings(openrouter_key=orr or None, models=[m.strip() for m in models.split(",") if m.strip()],
                             SEC_USER_AGENT=ua, FINNHUB_API_KEY=fh, SEC_API_KEY=sa)
            st.success("Gespeichert.")
            st.rerun()
    if st.button("OpenRouter-Schlüssel testen"):
        good, msg = ab.test_openrouter()
        (st.success if good else st.error)(msg)
    st.caption("Tipp: Auf openrouter.ai ein Ausgabelimit für den Schlüssel setzen.")


{PAGES[0]: page_run, PAGES[1]: page_home, PAGES[2]: page_portfolio, PAGES[3]: page_research, PAGES[4]: page_news,
 PAGES[5]: page_log, PAGES[6]: page_settings}[page]()
