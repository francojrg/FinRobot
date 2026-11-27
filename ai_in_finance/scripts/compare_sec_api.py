"""
Vergleich: eigene Zerlegung (edgar_sections.py) gegen sec-api.io an denselben Filings.

Grundlage sind die Abschnitte, die sec-api frueher geliefert hat und die im Cache der Agenten liegen
(finrobot_autogen/finrobot/data_source/.cache/sec_utils/<TICKER>_<FY>_<ITEM>.txt bzw. _10q_<item>.txt). Fuer jedes
dieser Filings wird das Originaldokument von EDGAR geladen (Testordner eval/edgar_test/, der Cache bleibt
unveraendert), selbst zerlegt und verglichen:
  Abdeckung  = Anteil der 8-Wort-Folgen aus dem sec-api-Text, die auch im eigenen Abschnitt stehen
  Genauigkeit = Anteil der 8-Wort-Folgen aus dem eigenen Abschnitt, die auch bei sec-api stehen
  Laenge     = eigene Zeichen / sec-api-Zeichen
Ergebnis: eval/compare_sec_api.txt und eval/compare_sec_api.csv. Kein LLM, keine Kosten.

    python ai_in_finance/scripts/compare_sec_api.py
"""
import csv
import re
import sys
import time
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
ROOT = AIF.parent
sys.path.insert(0, str(AIF))
sys.path.insert(0, str(ROOT / "finrobot_autogen"))
TEST = AIF / "eval" / "edgar_test"


def shingles(text, n=8):
    w = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def compare(ours, ref):
    a, b = shingles(ours or ""), shingles(ref)
    if not b:
        return None
    return {"coverage": len(a & b) / len(b), "precision": (len(a & b) / len(a)) if a else 0.0,
            "length": len(ours or "") / max(len(ref), 1)}


def main():
    from finrobot.utils import register_keys_from_json
    register_keys_from_json(str(ROOT / "finrobot_autogen" / "config_api_keys"))
    from finrobot.data_source.edgar_sections import fetch_text, section, tenq_item
    from finrobot.data_source.fmp_utils import FMPUtils, _submissions, _ticker_to_cik
    from finrobot.data_source.sec_utils import CACHE_PATH
    cache = Path(CACHE_PATH) / "sec_utils"
    rows = []
    tenk = {}
    for p in cache.glob("*.txt"):
        m = re.fullmatch(r"([A-Z.\-]+)_(\d{4})_(1|1A|7|7A)\.txt", p.name)
        if m:
            tenk.setdefault((m.group(1), m.group(2)), []).append((m.group(3), p))
    print(f"{len(tenk)} Jahresberichte mit sec-api-Abschnitten im Cache, lade die Originale ...", flush=True)
    for (t, fy), items in sorted(tenk.items()):
        try:
            link = FMPUtils.get_sec_report(t, fy)
        except Exception as e:
            print(f"{t} FY{fy}: Filing nicht gefunden ({str(e)[:100]})", flush=True)
            continue
        print(f"  {t} FY{fy}: {str(link)[:110]}", flush=True)
        if not link.startswith("Link: ") or "Form: 10-K" not in link:
            continue                                          # 20-F: ohnehin eigene Zerlegung, kein sec-api-Vergleich
        url = link[len("Link: "):].split()[0]
        try:
            full = fetch_text(url, str(TEST / f"{t}_{fy}_10k.txt"))
        except Exception as e:
            print(f"{t} FY{fy}: Download fehlgeschlagen ({e})")
            continue
        for it, p in sorted(items):
            ref = p.read_text(encoding="utf-8")
            if ref.startswith("["):                           # schon aus eigener Zerlegung, kein sec-api-Text
                continue
            r = compare(section(full, it), ref)
            if r:
                rows.append({"filing": f"{t} 10-K FY{fy}", "section": f"Item {it}", **r, "ref_chars": len(ref)})
        time.sleep(0.2)
    cik = _ticker_to_cik()
    for p in sorted(cache.glob("*_10q_*.txt")):
        m = re.fullmatch(r"([A-Z.\-]+)_(\d{4}-\d{2}-\d{2})_10q_(part1item2|part2item1a)\.txt", p.name)
        if not m:
            continue
        t, rd, key = m.groups()
        ref = p.read_text(encoding="utf-8")
        if ref.startswith("[") or ref.startswith("(not available"):
            continue
        c = cik.get(t)
        if c is None:
            continue
        try:
            r_ = _submissions(c)["filings"]["recent"]
        except Exception as e:
            print(f"{t}: EDGAR-Abruf fehlgeschlagen ({str(e)[:100]})", flush=True)
            continue
        url = next((f"https://www.sec.gov/Archives/edgar/data/{int(c)}/{a.replace('-', '')}/{doc}"
                    for f, a, d, doc in zip(r_["form"], r_["accessionNumber"], r_["reportDate"], r_["primaryDocument"])
                    if f == "10-Q" and d == rd), None)
        if not url:
            continue
        try:
            full = fetch_text(url, str(TEST / f"{t}_{rd}_10q.txt"))
        except Exception as e:
            print(f"{t} 10-Q {rd}: Download fehlgeschlagen ({e})")
            continue
        r = compare(tenq_item(full, key), ref)
        if r:
            rows.append({"filing": f"{t} 10-Q {rd}", "section": key, **r, "ref_chars": len(ref)})
        time.sleep(0.2)
    print(f"{'Filing':26s} {'Abschnitt':12s} {'Abdeckung':>9s} {'Genauigk.':>9s} {'Länge':>6s}")
    for r in rows:
        flag = "" if r["coverage"] >= 0.9 else "  <- prüfen"
        print(f"{r['filing']:26s} {r['section']:12s} {r['coverage']:9.1%} {r['precision']:9.1%} {r['length']:6.2f}{flag}")
    if rows:
        import statistics as s_
        for grp, sel in (("10-K", [r for r in rows if "10-K" in r["filing"]]), ("10-Q", [r for r in rows if "10-Q" in r["filing"]])):
            if sel:
                print(f"\n{grp}: {len(sel)} Abschnitte · Abdeckung Median {s_.median(x['coverage'] for x in sel):.1%}, "
                      f"mindestens 90 %: {sum(x['coverage'] >= 0.9 for x in sel)}/{len(sel)} · Genauigkeit Median "
                      f"{s_.median(x['precision'] for x in sel):.1%} · Länge Median {s_.median(x['length'] for x in sel):.2f}")
        with open(AIF / "eval" / "compare_sec_api.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


class _Tee:
    def __init__(self, path):
        self.f, self.out = open(path, "w", encoding="utf-8"), sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.out.flush()


if __name__ == "__main__":
    sys.stdout = _Tee(AIF / "eval" / "compare_sec_api.txt")
    try:
        main()
    except Exception:
        import traceback
        print("ABBRUCH:\n" + traceback.format_exc())
