"""
Status des Handlungsbedarfs je Titel: erledigt, gesehen oder ausgeblendet, mit optionaler Notiz
(research/action_state.json, lokal, nicht in Git).

Gespeichert wird der "Fingerabdruck" der Ausloeser (Regel-Code und Quelle, z. B. 'thesis_weakened|earnings review
2026-11-25'). Kommt spaeter ein Ausloeser dazu, der nicht im gespeicherten Fingerabdruck steht, gilt der Titel wieder
als offen; so warnt ein ausgeblendeter Titel bei neuen Ereignissen erneut. Die Notizen bekommt der Brief-Agent mit.
"""
import json
from datetime import date
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
STATE = AIF / "research" / "action_state.json"
STATES = ("done", "seen", "hidden")


def _load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {}


def _save(d):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(d, open(STATE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def fingerprint(triggers):
    return sorted({f"{x.get('code') or x.get('text', '')[:40]}|{x.get('source', '')}" for x in triggers or []
                   if x.get("level") in ("decide", "read")})


def status(ticker, triggers):
    """Gespeicherter Status, solange keine neuen Ausloeser dazugekommen sind; sonst None (= offen)."""
    s = _load().get(ticker.upper())
    if not s or s.get("state") not in STATES:
        return None
    if set(fingerprint(triggers)) - set(s.get("fp") or []):
        return None
    return s


def set_state(ticker, triggers, state, note=""):
    d = _load()
    t = ticker.upper()
    if state in (None, "", "open"):
        d.pop(t, None)
    else:
        prev = d.get(t) or {}
        d[t] = {"state": state, "fp": fingerprint(triggers), "date": date.today().isoformat(),
                "note": (note or "").strip()[:300] or prev.get("note", "")}
    _save(d)


def notes_for_agents(tickers=None):
    """Notizen und Status fuer den Brief-Agenten (nur Titel mit Status), z. B. 'MCO: done on 2026-11-26 - halte bewusst'."""
    out = {}
    for t, s in _load().items():
        if tickers and t not in {x.upper() for x in tickers}:
            continue
        label = {"done": "marked as handled", "seen": "acknowledged, no action yet", "hidden": "dismissed"}.get(s.get("state"))
        if label:
            out[t] = f"{label} by the user on {s.get('date')}" + (f"; user note: {s['note']}" if s.get("note") else "")
    return out
