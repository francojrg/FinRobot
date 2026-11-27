"""
Automatik: die Agenten laufen ohne Klick, sobald etwas faellig ist.

- Takt je Agent in research/automation.json (News taeglich, Prognose/Portfolio/Brief woechentlich, Annual Report und
  Earnings Review ereignisgesteuert ueber pipeline.plan: neue 10-K bzw. neue Quartalsmeldung bei der SEC).
- Eine Windows-Aufgabe ("FINRobot Automatik", ohne Adminrechte) startet scripts/run_scheduled.py taeglich zur
  gewaehlten Uhrzeit und nach der Anmeldung; verpasste Laeufe holt Windows nach (StartWhenAvailable).
- Monatsbudget: geplante Schritte werden vorab geschaetzt und abgeschnitten; waehrend des Laufs stoppt die Pipeline,
  sobald das Budget erreicht ist (siehe scripts/run_app_pipeline.py).
Protokoll jeder Pruefung: research/automation_log.jsonl.
"""
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
RES = AIF / "research"
CFG = RES / "automation.json"
STATE = RES / "automation_state.json"
LOG = RES / "automation_log.jsonl"
TASK = "FINRobot Automatik"

AGENTS = [  # key, Anzeige, Art, Standard an, Standardtakt in Tagen
    ("news", "News Tracker", "takt", True, 1),
    ("earnings_review", "Earnings Review", "ereignis", True, None),
    ("annual_report", "Annual Report", "ereignis", True, None),
    ("forecast", "Forecast", "takt", True, 7),
    ("preview", "Earnings Preview", "ereignis", True, None),
    ("portfolio", "Portfolio Manager", "takt", True, 7),
    ("brief", "Weekly Brief", "takt", True, 7),
    ("committee", "Investment Committee", "takt", False, 30),
]
EVENT_TEXT = {"earnings_review": "after new quarterly results (8-K at the SEC)",
              "annual_report": "on a new 10-K or new position",
              "preview": "up to 14 days before quarterly results"}
PRIORITY = ["news", "quarter_review", "earnings_review", "annual_report", "preview", "forecast", "portfolio", "brief", "committee"]


# =============================================================== Konfiguration
def default_config():
    return {"enabled": False, "time": "07:00", "budget_usd": 5.0, "model": None, "source": None,
            "brief_on_new_numbers": True, "watchlist": True, "watchlist_research": False,
            "agents": {k: {"on": on, "days": d} for k, _, _, on, d in AGENTS}}


def load_config():
    cfg = default_config()
    if CFG.exists():
        try:
            cur = json.load(open(CFG, encoding="utf-8"))
            agents = {**cfg["agents"], **{k: {**cfg["agents"].get(k, {}), **v} for k, v in cur.get("agents", {}).items()}}
            cfg.update(cur)
            cfg["agents"] = agents
        except Exception:
            pass
    return cfg


def save_config(cfg):
    RES.mkdir(parents=True, exist_ok=True)
    json.dump(cfg, open(CFG, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def load_state():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def save_state(s):
    json.dump(s, open(STATE, "w", encoding="utf-8"), indent=2)


def source_from_run(stamp):
    """Portfolio der Automatik = Portfolio eines App-Laufs (Datei und Titel, keine Kontodaten)."""
    from .app_backend import RUNS
    c = json.load(open(RUNS / f"{stamp}.json", encoding="utf-8"))
    return {"tickers": c.get("tickers") or [], "portfolio_file": c.get("portfolio_file"),
            "transaction_files": c.get("transaction_files"), "from_run": stamp}


# =============================================================== Budget
def month_spend(month=None):
    """Kosten der App- und Pipeline-Laeufe plus Chat im laufenden Monat (USD, aus den lokalen Protokollen)."""
    month = month or date.today().strftime("%Y-%m")
    tot = 0.0
    for f in (RES / "pipeline_runs").glob(f"{month}-*.json"):
        try:
            d = json.load(open(f, encoding="utf-8"))
            tot += d.get("cost_usd") or sum(x.get("cost_usd") or 0 for x in d.get("steps") or [])
        except Exception:
            pass
    for lp in (RES / "chat_log.jsonl", RES / "app_costs.jsonl"):   # Chat und kleine Modellaufrufe der App
        if not lp.exists():
            continue
        for line in lp.read_text(encoding="utf-8").splitlines():
            try:
                c = json.loads(line)
                if str(c.get("ts", "")).startswith(month):
                    tot += c.get("cost") or 0
            except Exception:
                pass
    return round(tot, 3)


def est_usd(step, n_tickers=1):
    from .app_backend import EST, NEWS_PER_TICKER
    if step == "news":
        return NEWS_PER_TICKER[1] * max(n_tickers, 1)
    return EST.get(step, (1, 0.02))[1]


# =============================================================== Was ist faellig?
def _days_since(iso):
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except Exception:
        return 10 ** 4


def due(cfg=None, plan_fn=None):
    """Faellige Schritte mit Begruendung und Schaetzung; Budget schneidet von hinten ab (Prioritaet siehe PRIORITY)."""
    cfg = cfg or load_config()
    src = cfg.get("source") or {}
    tickers = [t.upper() for t in src.get("tickers") or []]
    if not tickers:
        return {"steps": [], "dropped": [], "usd": 0.0, "reason": "no portfolio chosen for automation"}
    watch = watch_tickers(cfg, tickers)
    ag = cfg["agents"]
    if plan_fn is None:
        from .pipeline import plan as plan_fn
    days = lambda k, d: max(int(ag.get(k, {}).get("days") or d), 1)
    steps, _ = plan_fn(tickers + watch, news_days=days("news", 1) - 1, forecast_days=days("forecast", 7) - 1,
                       committee_days=days("committee", 30))
    wset = set(watch)                                 # Watchlist: News immer, Reports nur auf Wunsch, kein Committee
    steps = [s for s in steps if s["ticker"] not in wset or
             (cfg.get("watchlist_research") and s["step"] in ("annual_report", "quarter_review", "earnings_review"))]
    st_ = load_state()
    chosen = []
    for s in steps:
        k = s["step"]
        if k == "skip" or not ag.get("earnings_review" if k == "quarter_review" else k, {}).get("on"):
            continue
        if k in ("portfolio", "brief"):
            continue                                  # unten nach eigenem Takt
        chosen.append(dict(s))
    new_numbers = any(s["step"] in ("annual_report", "quarter_review", "earnings_review") for s in chosen)
    for k in ("portfolio", "brief"):
        if not ag.get(k, {}).get("on"):
            continue
        last = st_.get(k)
        if _days_since(last or "") >= days(k, 7):
            chosen.append({"step": k, "ticker": "portfolio", "reason": f"weekly (last {last[:10] if last else 'never'})"})
        elif k == "brief" and new_numbers and cfg.get("brief_on_new_numbers", True):
            chosen.append({"step": k, "ticker": "portfolio", "reason": "new quarterly results or annual report in the run"})
        elif k == "portfolio" and new_numbers:
            chosen.append({"step": k, "ticker": "portfolio", "reason": "new research view for the brief"})
    budget = float(cfg.get("budget_usd") or 0)
    left = budget - month_spend() if budget > 0 else float("inf")
    rank = {k: i for i, k in enumerate(PRIORITY)}
    keep, dropped, usd = [], [], 0.0
    for s in sorted(chosen, key=lambda s: rank.get(s["step"], 99)):
        u = est_usd(s["step"], len(tickers) + len(watch))
        if usd + u <= left:
            keep.append(s)
            usd += u
        else:
            dropped.append(s)
    order = {k: i for i, k in enumerate(["annual_report", "quarter_review", "earnings_review", "committee", "forecast", "preview", "news", "portfolio", "brief"])}
    keep.sort(key=lambda s: order.get(s["step"], 99))
    return {"steps": keep, "dropped": dropped, "usd": round(usd, 2), "left": None if left == float("inf") else round(left, 2),
            "tickers": tickers, "watch": watch}


def watch_tickers(cfg, tickers=()):
    """Watchlist-Titel fuer die Automatik (ohne Titel, die schon im Depot sind)."""
    if not cfg.get("watchlist", True):
        return []
    try:
        from .watchlist import tickers as _wl
        return [t for t in _wl() if t not in set(tickers)]
    except Exception:
        return []


def _log(entry):
    RES.mkdir(parents=True, exist_ok=True)
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), **entry}
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def history(n=30):
    if not LOG.exists():
        return []
    out = []
    for line in LOG.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(out))


def tick(force=False, plan_fn=None, start_fn=None):
    """Eine Pruefung: faellige Schritte ermitteln und als App-Lauf starten. force=True ignoriert 'ausgeschaltet'."""
    from . import app_backend as ab
    cfg = load_config()
    if not cfg.get("enabled") and not force:
        _log({"result": "aus"})
        return {"result": "aus"}
    lr = ab.latest_run()
    if lr and ab.run_status(lr)["alive"]:
        _log({"result": "uebersprungen", "why": f"run {lr} still running"})
        return {"result": "uebersprungen"}
    if not ab.load_settings()["openrouter"]:
        _log({"result": "fehler", "why": "no OpenRouter key"})
        return {"result": "fehler"}
    d = due(cfg, plan_fn=plan_fn)
    if not d["steps"]:
        why = "budget reached" if d.get("dropped") else d.get("reason", "nothing due")
        _log({"result": "nichts", "why": why, "dropped": [f"{s['step']} {s['ticker']}" for s in d.get("dropped", [])]})
        return {"result": "nichts", "why": why}
    src = cfg["source"]
    info = {"portfolio_file": src.get("portfolio_file"), "transaction_files": src.get("transaction_files")}
    try:                                     # Ergebnisse gehoeren in den Arbeitsbereich des Automatik-Portfolios
        from . import portfolios as pf
        pid = pf.ensure(info)
        if plan_fn is None and pf.load().get("active") != pid:
            pf.switch(pid)
    except Exception as e:
        _log({"result": "fehler", "why": f"portfolio switch failed: {e}"})
        return {"result": "fehler"}
    start_fn = start_fn or ab.start_run
    sel = [[s["step"], s["ticker"]] for s in d["steps"]]
    stamp = start_fn(info, d["tickers"], model=cfg.get("model") or "anthropic/claude-haiku-5.5",
                     steps=sorted({s["step"] for s in d["steps"]}), label="Automatik",
                     extra={"select": sel, "plan_args": _plan_args(cfg), "budget_usd": cfg.get("budget_usd"),
                            "automation": True, "watch": d.get("watch") or []})
    st_ = load_state()
    for s in d["steps"]:
        if s["step"] in ("portfolio", "brief"):
            st_[s["step"]] = datetime.now().isoformat(timespec="seconds")
    st_["last_tick"] = datetime.now().isoformat(timespec="seconds")
    save_state(st_)
    _log({"result": "gestartet", "run": stamp, "usd": d["usd"], "steps": [f"{s['step']} {s['ticker']}" for s in d["steps"]],
          "dropped": [f"{s['step']} {s['ticker']}" for s in d["dropped"]]})
    return {"result": "gestartet", "run": stamp, "steps": d["steps"]}


def _plan_args(cfg):
    ag = cfg["agents"]
    days = lambda k, d: max(int(ag.get(k, {}).get("days") or d), 1)
    return {"news_days": days("news", 1) - 1, "forecast_days": days("forecast", 7) - 1,
            "committee_days": days("committee", 30)}


# =============================================================== Windows-Aufgabe
def _pythonw():
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w if w.exists() else exe)


def task_xml(hhmm="07:00"):
    script = AIF / "scripts" / "run_scheduled.py"
    start = f"{date.today().isoformat()}T{hhmm}:00"
    esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    user = esc(f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\"))  # Anmeldung nur dieses Nutzers (ohne Adminrechte)
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Franci's FINRobot: prueft taeglich, welche Agenten faellig sind (lokal, eigenes Budget).</Description></RegistrationInfo>
  <Triggers>
    <CalendarTrigger><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled>
      <ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>
    <LogonTrigger><Enabled>true</Enabled><UserId>{user}</UserId><Delay>PT15M</Delay></LogonTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <ExecutionTimeLimit>PT8H</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>{esc(_pythonw())}</Command><Arguments>"{esc(script)}"</Arguments><WorkingDirectory>{esc(script.parent)}</WorkingDirectory></Exec>
  </Actions>
</Task>
"""


def _schtasks(*args):
    if os.name != "nt":
        return 1, "Scheduled automation is only available on Windows"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    p = subprocess.run(["schtasks", *args], capture_output=True, text=True, creationflags=flags)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def install_task(hhmm="07:00"):
    """Legt die Aufgabe fuer den angemeldeten Nutzer an (ueberschreibt eine vorhandene)."""
    xp = RES / "automation_task.xml"
    RES.mkdir(parents=True, exist_ok=True)
    xp.write_text(task_xml(hhmm), encoding="utf-16")
    code, out = _schtasks("/Create", "/TN", TASK, "/XML", str(xp), "/F")
    return code == 0, out.strip()


def remove_task():
    code, out = _schtasks("/Delete", "/TN", TASK, "/F")
    return code == 0, out.strip()


def task_installed():
    code, _ = _schtasks("/Query", "/TN", TASK)
    return code == 0


def next_check(hhmm="07:00", now=None):
    now = now or datetime.now()
    h, m = (int(x) for x in hhmm.split(":"))
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return t if t > now else t + timedelta(days=1)


def status():
    """Fuer Cockpit und Einrichtungsseite."""
    cfg = load_config()
    inst = task_installed() if cfg.get("enabled") else False
    hist = history(1)
    return {"enabled": bool(cfg.get("enabled")), "installed": inst, "time": cfg.get("time", "07:00"),
            "next": next_check(cfg.get("time", "07:00")) if cfg.get("enabled") else None,
            "budget": float(cfg.get("budget_usd") or 0), "spent": month_spend(), "last": hist[0] if hist else None,
            "source": cfg.get("source"), "cfg": cfg}
