"""
Testet die Insights-Watchlist an echten Quellen (in einem Testordner, deine eigene Quellenliste bleibt unberuehrt).
Kein LLM, keine Kosten.   python ai_in_finance/scripts/test_insights.py
"""
import sys
import tempfile
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AIF))
TESTS = ["https://www.jpmorgan.com/insights/research", "https://www.goldmansachs.com/insights",
         "https://www.morganstanley.com/ideas", "https://www.blackrock.com/corporate/insights/blackrock-investment-institute",
         "https://www.youtube.com/@GoldmanSachs", "https://www.federalreserve.gov/feeds/press_all.xml",
         "https://www.rbccm.com/en/insights/", "https://www.citigroup.com/global/insights", "https://www.dbresearch.com/"]


class _Tee:
    def __init__(self, path):
        self.f, self.out = open(path, "w", encoding="utf-8"), sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.out.flush()


def main():
    from lib import insights as ins
    d = Path(tempfile.mkdtemp())
    ins.SOURCES, ins.ITEMS = d / "sources.json", d / "items.json"
    ins._save(ins.SOURCES, [])
    for u in TESTS:
        ins.add_source(u)
    ins.refresh(force=True)
    p = ins.payload(limit=400)
    for s in p["sources"]:
        print(f"\n{s['name']} ({s['url']}): {s['kind']} · " + (f"FEHLER {s['error']}" if s["ok"] is False else
                                                              f"{s['n']} Beiträge {s.get('note') or ''}"))
        for x in [i for i in p["items"] if i["src"] == s["id"]][:5]:
            print(f"   {(x.get('date') or '')[:10]:10s} {x['title'][:100]}  ->  {x['url'][:90]}")


if __name__ == "__main__":
    sys.stdout = _Tee(AIF / "eval" / "test_insights.txt")
    main()
