"""
Backend der App (ohne Streamlit): Upload erkennen, Plan mit Zeit- und Kostenschaetzung, Lauf im Hintergrund starten
und verfolgen, Ergebnisse fuer die Reiter lesen. Die App selbst (app/app.py) ist nur die Oberflaeche darueber.
"""
import csv
import glob
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
ROOT = AIF.parent
FR = ROOT / "finrobot_autogen"
RUNS = AIF / "research" / "app_runs"
UPLOADS = AIF / "portfolios" / "uploads"
DEFAULT_STEPS = ["annual_report", "earnings_review", "forecast", "news", "portfolio", "brief"]   # ohne Committee
# Erfahrungswerte aus den Pipeline-Protokollen (Claude Haiku 5.5): Minuten, USD je Lauf
EST = {"annual_report": (6.0, 0.09), "earnings_review": (2.5, 0.035), "committee": (55.0, 1.30),
       "forecast": (0.4, 0.006), "portfolio": (2.0, 0.01), "brief": (0.7, 0.015)}
NEWS_PER_TICKER = (0.8, 0.02)
STEP_LABEL = {"annual_report": "Annual report", "earnings_review": "Earnings review", "committee": "Investment committee",
              "forecast": "Weekly forecast", "news": "News digest", "portfolio": "Portfolio review",
              "brief": "Weekly brief", "skip": "no 10-K agents"}


# =============================================================== Upload
def save_upload(name, data):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(name).name) or "portfolio.csv"
    p = UPLOADS / safe
    p.write_bytes(data)
    return p


def sample_files():
    """Dateien, die die App zur Auswahl anbietet: Musterdateien und eigene Uploads (keine Broker-Exporte)."""
    out = [AIF / "portfolios" / f for f in ("sample_portfolio.csv", "sample_transactions.csv")
           if (AIF / "portfolios" / f).exists()]
    out += sorted(UPLOADS.glob("*.csv")) if UPLOADS.exists() else []
    return out


def _header(path):
    with open(path, encoding="utf-8-sig", errors="ignore") as f:
        first = f.readline()
    sep = ";" if first.count(";") > first.count(",") else ","
    return [h.strip().lower() for h in first.split(sep)]


def inspect_portfolio(path):
    """Erkennt Gewichte/Stueckzahlen oder Transaktions-Exporte. Rueckgabe: kind, positions, issues, Dateirollen."""
    path = Path(path)
    head = _header(path)
    is_simple = "ticker" in head and ("weight" in head or "shares" in head) and not ({"type", "date"} & set(head))
    if is_simple:
        from . import portfolio_engine as pe
        pos = pe.load_portfolio(str(path))
        kind = "weights" if all("weight" in p for p in pos) else "shares"
        return {"kind": kind, "positions": pos, "issues": [], "portfolio_file": str(path), "transaction_files": None,
                "tickers": [p["ticker"] for p in pos]}
    from . import transactions as tr
    tx, issues = tr.read_all([str(path)])
    try:
        tx, unresolved = tr.attach_tickers(tx)
        if unresolved:
            issues = list(issues) + [f"ISIN without ticker: {', '.join(unresolved[:8])}"]
    except Exception as e:
        issues = list(issues) + [f"ticker lookup failed: {e}"]
    sg = {"buy": 1, "sell": -1, "deliver_in": 1, "deliver_out": -1, "transfer_in": 1, "transfer_out": -1}
    t = tx[tx["type"].isin(sg)].copy()
    t["q"] = t["type"].map(sg) * t["shares"].astype(float)
    key = t["ticker"].where(t["ticker"].astype(str) != "", t["isin"]) if "isin" in t else t["ticker"]
    q = t.groupby(key)["q"].sum()
    pos = [{"ticker": k, "shares": round(float(v), 4)} for k, v in q.items() if v > 1e-6 and str(k)]
    return {"kind": "transactions", "positions": pos, "issues": [str(i) for i in issues], "portfolio_file": None,
            "transaction_files": [str(path)], "tickers": [p["ticker"] for p in pos], "n_bookings": int(len(tx))}


# =============================================================== Plan
def make_plan(tickers, include_committee=False):
    """Faellige Schritte (fragt EDGAR ab) und Schaetzung. Ohne Committee, ausser include_committee."""
    from . import pipeline as pl
    steps, states = pl.plan(list(tickers))
    allowed = set(DEFAULT_STEPS) | ({"committee"} if include_committee else set())
    todo = [s for s in steps if s["step"] in allowed]
    skipped = [s for s in steps if s["step"] == "skip"]
    held = [s for s in steps if s["step"] == "committee" and not include_committee]
    minutes = usd = 0.0
    for s in todo:
        if s["step"] == "news":
            minutes += NEWS_PER_TICKER[0] * len(tickers)
            usd += NEWS_PER_TICKER[1] * len(tickers)
        else:
            m, u = EST.get(s["step"], (1, 0.01))
            minutes += m
            usd += u
    return {"steps": todo, "skipped": skipped, "committee_held": held, "minutes": round(minutes),
            "usd": round(usd, 2), "tickers": list(tickers)}


# =============================================================== Lauf
def start_run(info, tickers, include_committee=False, model="anthropic/claude-haiku-5.5", max_steps=None):
    """Startet scripts/run_app_pipeline.py als eigenen Prozess (laeuft weiter, auch wenn die Seite neu laedt)."""
    RUNS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    cfg = {"stamp": stamp, "tickers": list(tickers), "portfolio_file": info.get("portfolio_file"),
           "transaction_files": info.get("transaction_files"), "include_committee": include_committee,
           "model": model, "max_steps": max_steps, "started": datetime.now().isoformat(timespec="seconds")}
    cfg_p = RUNS / f"{stamp}.json"
    json.dump(cfg, open(cfg_p, "w", encoding="utf-8"), indent=2)
    log = open(RUNS / f"{stamp}.log", "w", encoding="utf-8")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    p = subprocess.Popen([sys.executable, str(AIF / "scripts" / "run_app_pipeline.py"), "--config", str(cfg_p)],
                         cwd=str(AIF / "scripts"), stdout=log, stderr=subprocess.STDOUT, creationflags=flags, env=env)
    cfg["pid"] = p.pid
    json.dump(cfg, open(cfg_p, "w", encoding="utf-8"), indent=2)
    return stamp


def latest_run():
    files = sorted(RUNS.glob("*.json")) if RUNS.exists() else []
    files = [f for f in files if not f.name.endswith("_done.json")]
    return files[-1].stem if files else None


def run_status(stamp):
    """Stand eines Laufs: fertig?, Schritte mit Ergebnis, letzte Logzeilen."""
    cfg = json.load(open(RUNS / f"{stamp}.json", encoding="utf-8"))
    done_p = RUNS / f"{stamp}_done.json"
    done = json.load(open(done_p, encoding="utf-8")) if done_p.exists() else None
    log_p = RUNS / f"{stamp}.log"
    lines = open(log_p, encoding="utf-8", errors="replace").read().splitlines() if log_p.exists() else []
    run_log = None
    pr = cfg.get("pipeline_log") or (done or {}).get("pipeline_log")
    if not pr:
        cands = sorted(glob.glob(str(AIF / "research" / "pipeline_runs" / "*.json")))
        cands = [c for c in cands if Path(c).stem >= stamp[:15].replace("_", "_")]
        pr = cands[-1] if cands else None
    if pr and Path(pr).exists():
        try:
            run_log = json.load(open(pr, encoding="utf-8"))
        except Exception:
            run_log = None
    total = None
    for ln in lines:
        if ln.startswith("PLAN_STEPS="):
            total = int(ln.split("=", 1)[1])
    alive = done is None and _alive(cfg.get("pid"))
    return {"cfg": cfg, "done": done, "alive": alive, "steps": (run_log or {}).get("steps", []), "total": total,
            "tail": lines[-25:], "cost": (run_log or {}).get("cost_usd")}


def _alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
            return str(pid) in out
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


# =============================================================== Ergebnisse
def site_dir():
    return AIF / "reports" / "site"


def site_page(name, embed=True):
    """HTML einer Dashboard-Seite; embed=True entfernt die Kopfzeile (Links funktionieren in der App nicht)."""
    import re
    p = site_dir() / name
    if not p.exists():
        return None
    html = p.read_text(encoding="utf-8")
    if embed:
        html = re.sub(r"<header>.*?</header>", "", html, count=1, flags=re.S)
        html = html.replace("<a href='index.html'>", "<a>")
    return html


def latest_brief():
    from .html_site import _newest
    bj = _newest(AIF / "research" / "briefs" / "brief_*.json")
    if not bj:
        return None, None
    data = json.load(open(bj, encoding="utf-8"))
    ba = _newest(AIF / "reports" / "brief_*" / "brief_*_build_args.json")
    texts = json.load(open(ba, encoding="utf-8")) if ba else {}
    return data, texts


def research_reports():
    """{ticker: {"annual": (page, pdf), "earnings": (page, pdf)}} aus dem Dashboard-Ordner."""
    out = {}
    for p in site_dir().glob("*_annual.html"):
        out.setdefault(p.stem[:-7], {})["annual"] = p.name
    for p in site_dir().glob("*_earnings.html"):
        out.setdefault(p.stem[:-9], {})["earnings"] = p.name
    return dict(sorted(out.items()))


def report_pdf(ticker, kind):
    t = ticker.upper()
    if kind == "annual":
        from . import pipeline as pl
        r = pl.agent_report(t)
        if not r:
            return None
        pdfs = sorted(Path(r["path"]).glob("*.pdf"), key=os.path.getmtime)
    else:
        pdfs = sorted(glob.glob(str(AIF / "reports" / f"{t}_earnings_multi_*" / "*.pdf")), key=os.path.getmtime)
        pdfs = [Path(p) for p in pdfs]
    return pdfs[-1] if pdfs else None


def notable_news(tickers, days=10, limit=12):
    """Wesentliche Meldungen der letzten Tage (aus dem News-Speicher), neueste zuerst."""
    try:
        from . import news_tracker as nt
        start = (date.today().toordinal() - days)
        tick = {t.upper() for t in tickers}
        items = [s for s in nt.load_store() if s.get("ticker", "").upper() in tick and s.get("materiality", 1) >= 2
                 and date.fromisoformat(s["date"][:10]).toordinal() >= start and s.get("relevant", True)]
        items.sort(key=lambda s: (s["date"], s.get("materiality", 1)), reverse=True)
        return items[:limit]
    except Exception:
        return []


def pipeline_runs(n=15):
    files = sorted(glob.glob(str(AIF / "research" / "pipeline_runs" / "*.md")), reverse=True)[:n]
    return [Path(f) for f in files]


# =============================================================== Einstellungen (Schluessel bleiben lokal)
KEY_FIELDS = ["SEC_USER_AGENT", "FINNHUB_API_KEY", "SEC_API_KEY", "FMP_API_KEY"]


def load_settings():
    keys = json.load(open(FR / "config_api_keys", encoding="utf-8")) if (FR / "config_api_keys").exists() else {}
    oai = json.load(open(FR / "OAI_CONFIG_LIST", encoding="utf-8")) if (FR / "OAI_CONFIG_LIST").exists() else []
    orr = next((e for e in oai if "openrouter" in str(e.get("base_url", ""))), {})
    ok = lambda v: bool(v) and "YOUR" not in str(v).upper()
    return {"openrouter": ok(orr.get("api_key")), "models": [e.get("model") for e in oai],
            **{k: ok(keys.get(k)) for k in KEY_FIELDS}}


def save_settings(openrouter_key=None, models=None, **keys):
    """Schreibt nur Felder, die ausgefuellt wurden; vorhandene Werte bleiben sonst erhalten."""
    kp = FR / "config_api_keys"
    cur = json.load(open(kp, encoding="utf-8")) if kp.exists() else {}
    for k, v in keys.items():
        if v:
            cur[k] = v.strip()
    json.dump(cur, open(kp, "w", encoding="utf-8"), indent=4)
    op = FR / "OAI_CONFIG_LIST"
    oai = json.load(open(op, encoding="utf-8")) if op.exists() else []
    key = openrouter_key.strip() if openrouter_key else next((e.get("api_key") for e in oai
                                                              if "openrouter" in str(e.get("base_url", ""))), None)
    if key:
        ms = models or [e.get("model") for e in oai] or ["anthropic/claude-haiku-5.5"]
        oai = [{"model": m, "api_key": key, "base_url": "https://openrouter.ai/api/v1"} for m in ms]
        json.dump(oai, open(op, "w", encoding="utf-8"), indent=4)


def test_openrouter():
    """Prueft den OpenRouter-Schluessel (kein Modellaufruf): Rueckgabe Text."""
    import requests
    oai = json.load(open(FR / "OAI_CONFIG_LIST", encoding="utf-8"))
    key = next((e.get("api_key") for e in oai if "openrouter" in str(e.get("base_url", ""))), None)
    if not key:
        return False, "no OpenRouter key saved"
    try:
        r = requests.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=20)
        if r.status_code != 200:
            return False, f"OpenRouter answered {r.status_code}"
        d = r.json().get("data", {})
        lim = d.get("limit")
        return True, f"key valid; used USD {d.get('usage', 0):.2f}" + (f" of limit USD {lim:.2f}" if lim else " (no limit set)")
    except Exception as e:
        return False, f"not reachable: {e}"
