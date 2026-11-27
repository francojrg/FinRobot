"""
Mehrere Portfolios in der App: speichern, wechseln, zusammenfassen (eigene Erweiterung).

Was je Portfolio getrennt ist und was geteilt wird
- Geteilt (gehoert zur Firma, nicht zum Portfolio): Annual Reports, Earnings Reviews, Quarter Records, Thesis Books,
  Bewertungsdaten, Prognosen, der News-Speicher je Titel. Ein Wechsel loest deshalb keinen neuen Lauf aus.
- Je Portfolio (Arbeitsbereich): Portfolio-Dashboard und -Snapshot, Weekly Brief, Portfolio Review, News-Digest und
  Signale, Termine, Dividenden, ETF-Durchschau. Beim Wechsel wird der Arbeitsbereich des alten Portfolios unter
  research/portfolios/<id>/ws/ gesichert und der des neuen an die gewohnten Stellen zurueckgelegt (die uebrige App
  bleibt unveraendert). Fuer ein Portfolio ohne Arbeitsbereich rechnet Python Dashboard und Snapshot neu (ohne
  Sprachmodell); Brief und Review entstehen beim naechsten Lauf, der nur das Fehlende nachholt.
- Das DEMO-Depot (Valley Forge, aus 13F-Meldungen nachgebaut) ist fest eingetragen und unabhaengig von den eigenen
  Portfolios; es kann nicht geloescht oder zusammengefasst werden.
Verzeichnis: research/portfolios/index.json (Liste, aktives Portfolio), research/portfolios/<id>/ws/ (Arbeitsbereich).
"""
import glob
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("BLUMBOERG_PORTFOLIO_ROOT") or AIF / "research" / "portfolios")   # Tests: eigener Ordner
INDEX = ROOT / "index.json"
DEMO_ID = "demo"
DEMO = {"id": DEMO_ID, "name": "DEMO · Valley Forge (13F)", "kind": "demo", "portfolio_file": None,
        "transaction_files": [str(AIF / "portfolios" / "sample_transactions_vfc_filed.csv")], "holdings_files": None,
        "note": "Model portfolio rebuilt from Valley Forge Capital's 13F filings since 2016 (synthetic transactions)"}
SCOPED_FILES = ["research/portfolio_dashboard.json", "research/portfolio_snapshot.json", "research/dividends.json",
                "research/etf_lookthrough.json", "research/events.json", "news/signals_latest.json"]
SCOPED_DIRS = ["research/briefs", "reports/brief_*", "reports/news_*", "reports/portfolio_app_*"]


# =============================================================== Verzeichnis
def _now():
    return datetime.now().isoformat(timespec="minutes")


def _norm_files(x):
    if not x:
        return []
    return sorted(str(f) for f in ([x] if isinstance(x, str) else x))


def _base(f):
    return re.split(r"[\\/]", str(f))[-1]


def _stem(f):
    return _base(f).rsplit(".", 1)[0]


def _key(p):
    """Gleiche Dateien = gleiches Portfolio (Reihenfolge, Trennzeichen und Gross-/Kleinschreibung egal).
    Die Musterdatei des DEMO-Depots wird am Dateinamen erkannt (gleich, wo das Projekt liegt)."""
    fs = _norm_files(p.get("transaction_files")) + _norm_files(p.get("holdings_files")) + _norm_files(p.get("portfolio_file"))
    if fs and all(_base(f).lower() == _base(DEMO["transaction_files"][0]).lower() for f in fs):
        return ("demo",)
    return tuple(sorted(f.replace("\\", "/").lower() for f in fs))


def _full_runs():
    """Alle frueheren Laeufe mit dem ganzen Portfolio (keine Einzelfirma, keine Automatik), aelteste zuerst."""
    out = []
    for f in sorted((AIF / "research" / "app_runs").glob("*.json")):
        if f.name.endswith("_done.json"):
            continue
        try:
            c = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if not c.get("label") and not c.get("steps") and (c.get("transaction_files") or c.get("portfolio_file")):
            out.append(c)
    return out


def load():
    """Verzeichnis laden; beim ersten Aufruf anlegen (DEMO + das Portfolio des letzten Laufs als aktiv)."""
    try:
        d = json.load(open(INDEX, encoding="utf-8"))
    except Exception:
        d = None
    if not d:
        d = {"active": None, "items": [dict(DEMO, created=_now())]}
        for run in _full_runs():                     # fruehere Portfolios uebernehmen; das zuletzt gelaufene ist aktiv
            entry = {"portfolio_file": run.get("portfolio_file"), "transaction_files": run.get("transaction_files"),
                     "holdings_files": run.get("holdings_files")}
            hit = next((x for x in d["items"] if _key(x) == _key(entry)), None)
            if hit is None:
                name = _stem((_norm_files(entry["transaction_files"]) or _norm_files(entry["portfolio_file"]))[0])
                hit = {"id": _new_id(d, name), "name": _pretty(name), "kind": "user", **entry, "created": _now()}
                d["items"].append(hit)
            hit["last_run"] = run.get("started")
            d["active"] = hit["id"]
        d["active"] = d["active"] or DEMO_ID
        save(d)
    demo = next((x for x in d["items"] if x["id"] == DEMO_ID), None)
    if demo is None:                                               # DEMO immer vorhanden
        d["items"].insert(0, dict(DEMO, created=_now()))
        save(d)
    else:                                                          # Pfad immer aus diesem Rechner (nicht gespeichert)
        demo.update({k: DEMO[k] for k in ("name", "transaction_files", "portfolio_file", "holdings_files", "note")})
    return d


def save(d):
    ROOT.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix(".tmp")
    json.dump(d, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, INDEX)


def _pretty(stem):
    s = re.sub(r"[_\-]+", " ", stem).strip()
    known = {"traderepublic": "Trade Republic", "scalablecapital": "Scalable Capital",
             "sampleportfolio": "Sample · Big Tech and Europe (weights)", "sampleportfoliovfc": "Sample · Valley Forge weights (13F Q3)",
             "sampletransactions": "Sample · transactions", "sampletransactionsvfcquarter": "Sample · Valley Forge quarter-end",
             "sampleportfoliov1bigtech": "Sample · Big Tech", "sampletransactionsv1bigtech": "Sample · Big Tech transactions"}
    return known.get(s.lower().replace(" ", ""), s[:1].upper() + s[1:])


def _new_id(d, name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:30] or "portfolio"
    ids, i, pid = {x["id"] for x in d["items"]}, 1, base
    while pid in ids or pid == DEMO_ID:
        i += 1
        pid = f"{base}-{i}"
    return pid


def items():
    return load()["items"]


def get(pid):
    return next((x for x in load()["items"] if x["id"] == pid), None)


def active():
    d = load()
    return next((x for x in d["items"] if x["id"] == d.get("active")), None)


def has_workspace(pid):
    return (ROOT / pid / "ws").exists()


# =============================================================== Arbeitsbereich sichern / zuruecklegen
def _scoped_paths():
    out = [AIF / f for f in SCOPED_FILES]
    for pat in SCOPED_DIRS:
        out += [Path(p) for p in glob.glob(str(AIF / pat))]
    return out


def _save_ws(pid):
    """Aktuellen Zustand als Arbeitsbereich von pid sichern (erst in einen neuen Ordner, dann umbenennen)."""
    dest, tmp = ROOT / pid / "ws", ROOT / pid / "ws_new"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    for p in _scoped_paths():
        if not p.exists():
            continue
        rel = p.relative_to(AIF)
        tgt = tmp / rel
        tgt.parent.mkdir(parents=True, exist_ok=True)
        (shutil.copytree if p.is_dir() else shutil.copy2)(p, tgt)
    if dest.exists():
        shutil.rmtree(dest)
    os.replace(tmp, dest)


def _clear_scoped():
    for p in _scoped_paths():
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()


def _restore_ws(pid):
    src = ROOT / pid / "ws"
    _clear_scoped()
    if not src.exists():
        return False
    for p in src.rglob("*"):
        if p.is_file():
            tgt = AIF / p.relative_to(src)
            tgt.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, tgt)
    return True


def run_active():
    """Laeuft gerade eine Analyse? Dann darf nicht gewechselt werden (sie schreibt in den Arbeitsbereich)."""
    try:
        from .app_backend import latest_run, run_status
        lr = latest_run()
        return bool(lr and run_status(lr)["alive"])
    except Exception:
        return False


def switch(pid):
    """Zu Portfolio pid wechseln. Rueckgabe: True, wenn ein gesicherter Arbeitsbereich zurueckgelegt wurde
    (sonst muss prepare() Dashboard und Snapshot neu rechnen)."""
    d = load()
    if d.get("active") == pid:
        return True
    if not any(x["id"] == pid for x in d["items"]):
        raise ValueError(f"unknown portfolio {pid}")
    if run_active():
        raise RuntimeError("an analysis is running – switch portfolios after it has finished")
    if d.get("active"):
        _save_ws(d["active"])
    restored = _restore_ws(pid)
    d["active"] = pid
    save(d)
    return restored


# =============================================================== Anlegen, umbenennen, loeschen, zusammenfassen
def ensure(info, name=None):
    """Portfolio zu den Dateien eines Laufs finden oder anlegen (ohne zu wechseln). Rueckgabe: id."""
    d = load()
    entry = {"portfolio_file": info.get("portfolio_file"), "transaction_files": info.get("transaction_files") or None,
             "holdings_files": info.get("holdings_files") or None}
    k = _key(entry)
    for x in d["items"]:
        if _key(x) == k:
            return x["id"]
    stem = _stem((_norm_files(entry["transaction_files"]) or _norm_files(entry["holdings_files"])
                  or _norm_files(entry["portfolio_file"]) or ["portfolio"])[0])
    nm = name or _pretty(stem)
    pid = _new_id(d, nm)
    d["items"].append({"id": pid, "name": nm, "kind": "user", **entry, "created": _now()})
    save(d)
    return pid


def mark_run(pid, stamp):
    d = load()
    for x in d["items"]:
        if x["id"] == pid:
            x["last_run"] = stamp
    save(d)


def rename(pid, name):
    d = load()
    for x in d["items"]:
        if x["id"] == pid and x["kind"] != "demo":
            x["name"] = str(name).strip()[:60] or x["name"]
    save(d)


def delete(pid):
    """Eigenes Portfolio aus der Liste entfernen (Dateien und Firmen-Reports bleiben). Das aktive nicht."""
    d = load()
    if pid == DEMO_ID or pid == d.get("active"):
        raise ValueError("the DEMO portfolio and the active portfolio cannot be removed")
    d["items"] = [x for x in d["items"] if x["id"] != pid]
    save(d)
    shutil.rmtree(ROOT / pid, ignore_errors=True)


def combine(pids, name):
    """Neues Portfolio aus mehreren eigenen Portfolios: Transaktions- und Positionsdateien werden zusammengefuehrt
    (gleiche Titel werden addiert, Ein- und Auszahlungen gemeinsam gerechnet). Rueckgabe: id."""
    d = load()
    src = [x for x in d["items"] if x["id"] in pids]
    if len(src) < 2:
        raise ValueError("choose at least two portfolios")
    if any(x["kind"] == "demo" for x in src):
        raise ValueError("the DEMO portfolio cannot be combined with your own portfolios")
    bad = [x["name"] for x in src if not (x.get("transaction_files") or x.get("holdings_files"))]
    if bad:
        raise ValueError("only portfolios with transactions or share counts can be combined: " + ", ".join(bad))
    tx = sorted({f for x in src for f in _norm_files(x.get("transaction_files"))})
    ho = sorted({f for x in src for f in _norm_files(x.get("holdings_files"))})
    entry = {"portfolio_file": None, "transaction_files": tx or None, "holdings_files": ho or None}
    for x in d["items"]:
        if _key(x) == _key(entry):
            return x["id"]
    nm = str(name or " + ".join(x["name"] for x in src)).strip()[:60]
    pid = _new_id(d, nm)
    d["items"].append({"id": pid, "name": nm, "kind": "combined", **entry, "sources": [x["id"] for x in src],
                       "created": _now()})
    save(d)
    return pid


# =============================================================== Daten ohne Sprachmodell
def info(p):
    """Wie app_backend.inspect_portfolio, fuer ein gespeichertes (auch zusammengefasstes) Portfolio."""
    from .app_backend import inspect_portfolio
    files = _norm_files(p.get("transaction_files")) + _norm_files(p.get("holdings_files"))
    if p.get("portfolio_file") and not files:
        return inspect_portfolio(p["portfolio_file"])
    tickers, positions, issues = [], [], []
    for f in files:
        i = inspect_portfolio(f)
        issues += i.get("issues") or []
        for t in i.get("tickers") or []:
            if t not in tickers:
                tickers.append(t)
        positions += i.get("positions") or []
    return {"kind": "transactions" if p.get("transaction_files") else "shares", "tickers": tickers,
            "positions": positions, "issues": issues, "portfolio_file": p.get("portfolio_file"),
            "transaction_files": p.get("transaction_files"), "holdings_files": p.get("holdings_files")}


def prepare(pid=None, log=print):
    """Dashboard und Snapshot fuer das (aktive) Portfolio neu rechnen – nur Python, kein Sprachmodell.
    Dauert je nach Groesse 20-90 Sekunden (Kurse, Risiko, Backtest)."""
    from . import pipeline as pl
    from .portfolio_manager import prepare_portfolio_data
    from . import agent_settings as _AS
    p = get(pid) if pid else active()
    if not p:
        raise ValueError("no active portfolio")
    tick = info(p)["tickers"]
    views = pl.research_views(tick)
    prepare_portfolio_data(p.get("portfolio_file"), transaction_files=p.get("transaction_files"),
                           holdings_files=p.get("holdings_files"), research=views, name="app", title=p["name"],
                           cap=_AS.param("portfolio.cap", 0.10), sector_cap=_AS.param("portfolio.sector_cap", 0.35))
    try:
        pl.warm_portfolio_extras()
    except Exception as e:
        log(f"Dividends / ETF data not refreshed: {e}")
    return True
