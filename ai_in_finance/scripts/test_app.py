"""
Seitentest fuer die App (Streamlit AppTest): oeffnet jede Seite, jede Firmenansicht und die Einrichtung mit jeder
Musterdatei und meldet Abstuerze. Startet keine Analyse und ruft kein LLM auf.

    python ai_in_finance/scripts/test_app.py            (alle Seiten und Firmen)
    python ai_in_finance/scripts/test_app.py --quick    (nur die Seiten)
"""
import argparse
import os
import sys
import time
import traceback
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
APP = AIF / "app" / "app.py"
sys.path.insert(0, str(AIF))
PAGES = ["home", "news", "portfolio", "research", "chat", "run", "log", "settings"]


def run_page(page, state=None, actions=None, timeout=180):
    from streamlit.testing.v1 import AppTest
    os.environ["BLUMBOERG_TEST_PAGE"] = page
    at = AppTest.from_file(str(APP), default_timeout=timeout)
    for k, v in (state or {}).items():
        at.session_state[k] = v
    t0 = time.time()
    at.run()
    for act in actions or []:
        act(at)
    exc = [e.message for e in at.exception]
    errs = [e.value for e in at.error]
    return exc, errs, time.time() - t0


def report(name, res):
    exc, errs, sec = res
    tag = "FAIL" if exc else ("WARN" if errs else "OK  ")
    print(f"{tag} {name:48s} {sec:5.1f} s" + "".join(f"\n     Absturz: {str(m)[:300]}" for m in exc)
          + "".join(f"\n     Fehlermeldung auf der Seite: {str(m)[:200]}" for m in errs))
    return not exc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    ok = total = 0

    def do(name, *args, **kw):
        nonlocal ok, total
        total += 1
        try:
            ok += report(name, run_page(*args, **kw))
        except Exception as e:
            print(f"FAIL {name:48s} Test selbst abgebrochen: {e}\n{traceback.format_exc(limit=3)}")

    print("Seiten")
    for p in PAGES:
        do(p, p)
    if not a.quick:
        print("\nEinrichtung mit jeder Musterdatei")
        from lib import app_backend as ab
        for f in ab.sample_files():
            def pick(at, f=f):
                box = [s for s in at.selectbox if s.label == "Datei"]
                if box:
                    box[0].set_value(f)
                    at.run()
            do(f"run: {f.name}", "run", actions=[pick])
        print("\nFirmenansichten")
        try:
            from lib import company_data as cd
            tickers = [c.get("t") or c.get("ticker") for c in cd.companies()]
        except Exception as e:
            tickers = []
            print(f"FAIL Firmenliste nicht lesbar: {e}")
        for t in [x for x in tickers if x]:
            do(f"research: {t}", "research", state={"company": t})
    print(f"\n{ok} von {total} Seiten ohne Absturz.")


if __name__ == "__main__":
    main()
