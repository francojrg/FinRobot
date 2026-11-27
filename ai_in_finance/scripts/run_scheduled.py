"""
Wird von der Windows-Aufgabe "FINRobot Automatik" gestartet (taeglich und nach der Anmeldung; siehe lib/automation.py).
Prueft, welche Agenten faellig sind, startet sie als normalen App-Lauf (sichtbar unter "Einrichtung und Automatik" und
im Protokoll) und wartet, bis der Lauf fertig ist. Von Hand: python ai_in_finance/scripts/run_scheduled.py [--force]
"""
import argparse
import sys
import time
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AIF))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="auch pruefen, wenn die Automatik ausgeschaltet ist")
    a = ap.parse_args()
    if sys.stdout is None or sys.stderr is None:     # pythonw (ohne Konsole): Ausgaben in eine Logdatei
        (AIF / "research").mkdir(exist_ok=True)
        sys.stdout = sys.stderr = open(AIF / "research" / "automation_run.log", "a", encoding="utf-8", buffering=1)
    from lib import app_backend as ab, automation as au
    try:
        res = au.tick(force=a.force)
    except Exception as e:  # Fehler protokollieren statt still abbrechen
        au._log({"result": "fehler", "why": f"{type(e).__name__}: {e}"})
        raise
    print(res.get("result"), res.get("why") or res.get("run") or "", flush=True)
    if res.get("result") == "gestartet":
        while ab.run_status(res["run"])["alive"]:     # Aufgabe bleibt aktiv, bis der Lauf fertig ist
            time.sleep(30)


if __name__ == "__main__":
    main()
