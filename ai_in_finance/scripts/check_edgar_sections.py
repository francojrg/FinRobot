"""
Prueft die eigene Zerlegung von 10-K und 10-Q (edgar_sections.py, Ersatz fuer sec-api.io) an echten Filings.
Laedt die Dokumente in einen Testordner (eval/edgar_test/), schreibt nichts in den Cache der Agenten. Kein LLM.

    python ai_in_finance/scripts/check_edgar_sections.py MNST KO CSCO
"""
import os
import sys
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
ROOT = AIF.parent
sys.path.insert(0, str(AIF))
sys.path.insert(0, str(ROOT / "finrobot_autogen"))
OUT = AIF / "eval" / "edgar_test"


def main(tickers):
    from finrobot.utils import register_keys_from_json
    register_keys_from_json(str(ROOT / "finrobot_autogen" / "config_api_keys"))
    from finrobot.data_source.edgar_sections import fetch_text, section, tenq_item
    from finrobot.data_source.fmp_utils import FMPUtils
    from lib.pipeline import edgar_status
    from lib.quarterly_data import latest_10q
    ok = bad = 0
    for t in tickers:
        e = edgar_status(t)
        if e.get("error") or not e.get("fyear"):
            print(f"{t}: kein Jahresbericht ({e.get('error')})")
            continue
        link = FMPUtils.get_sec_report(t, str(e["fyear"]))
        url = link.lstrip("Link: ").split()[0] if link.startswith("Link: ") else None
        print(f"\n{t} {e.get('annual_form')} FY{e['fyear']}: {url}")
        if url and e.get("annual_form") == "10-K":
            full = fetch_text(url, str(OUT / f"{t}_{e['fyear']}_10k.txt"))
            for it in ("1", "1A", "7", "7A"):
                seg = section(full, it)
                good = bool(seg) and (it == "7A" or len(seg) > 5000)
                ok += good
                bad += not good
                print(f"  {'OK  ' if good else 'FEHLT'} Item {it:3s} {len(seg) if seg else 0:7,d} Zeichen | "
                      + ((seg or "")[:90].replace("\n", " ")))
        q = latest_10q(t)
        if q:
            full = fetch_text(q["url"], str(OUT / f"{t}_{q['report_date']}_10q.txt"))
            for key in ("part1item2", "part2item1a"):
                seg = tenq_item(full, key)
                good = bool(seg)
                ok += good
                bad += not good
                print(f"  {'OK  ' if good else 'FEHLT'} 10-Q {q['report_date']} {key:11s} {len(seg) if seg else 0:7,d} Zeichen | "
                      + ((seg or "")[:80].replace("\n", " ")))
    print(f"\n{ok} Abschnitte gefunden, {bad} fehlen.")


class _Tee:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.f, self.out = open(path, "w", encoding="utf-8"), sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.out.flush()


if __name__ == "__main__":
    sys.stdout = _Tee(AIF / "eval" / "check_edgar_sections.txt")
    main([a.upper() for a in sys.argv[1:]] or ["MNST", "KO", "CSCO", "SPGI", "AMZN"])
