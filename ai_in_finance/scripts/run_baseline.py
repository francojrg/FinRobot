"""
Baseline fuer die Evaluation: dasselbe Sprachmodell schreibt einen Equity-Research-Report mit einem einfachen Prompt,
ohne Werkzeuge und ohne Daten (so, wie man ein Chat-Modell direkt fragen wuerde). Der Text wird danach mit
factcheck_text.py gegen dieselben Quellen geprueft wie die Agenten-Reports.

Ausfuehren (aus dem FinRobot-Ordner):
    python ai_in_finance/scripts/run_baseline.py --runs GOOG:2025 AMZN:2025 MA:2025 [--model anthropic/claude-haiku-5.5]

Ergebnis: ai_in_finance/reports/baseline/<FIRMA>_<FY>_<modell>_plain.md und daneben *_factcheck.json.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIF = ROOT / "ai_in_finance"
sys.path.insert(0, str(AIF))

PROMPT = """You are an equity research analyst. Write an equity research report on {name} ({ticker}) based on its annual
report (Form 10-K) for fiscal year {fy}. Use these sections as Markdown headings: Investment Summary, Business Overview,
Operating Results, Market Position, Risk Assessment, Competitors Analysis, Key Takeaways, Investment Theses. Include the
key financial figures (revenue, growth, margins, earnings per share, cash flow, segment figures) and compare the company
with two or three peers. Write about 1,200 words in English."""


def company_name(t):
    try:
        import yfinance as yf
        i = yf.Ticker(t).info
        return i.get("longName") or i.get("shortName") or t
    except Exception:
        return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="FIRMA:JAHR, z. B. GOOG:2025")
    ap.add_argument("--model", default="anthropic/claude-haiku-5.5")
    ap.add_argument("--no-check", action="store_true", help="nur Texte erzeugen, keinen Faktencheck")
    a = ap.parse_args()
    import autogen
    from finrobot.utils import register_keys_from_json
    from lib import pipeline as pl
    register_keys_from_json(str(ROOT / "finrobot_autogen" / "config_api_keys"))
    cfg = pl.llm_config_for(a.model)
    cfg = {k: v for k, v in cfg.items() if k not in ("parallel_tool_calls", "tools", "functions")}
    client = autogen.OpenAIWrapper(**cfg)
    out_dir = AIF / "reports" / "baseline"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = a.model.split("/")[-1]
    for run in a.runs:
        t, fy = run.split(":")
        t = t.upper()
        name = company_name(t)
        msg = PROMPT.format(name=name, ticker=t, fy=fy)
        print(f"\n=== {t} FY{fy}: Baseline-Text ({a.model}) ...")
        resp = client.create(messages=[{"role": "user", "content": msg}], cache=None)
        text = (client.extract_text_or_completion_object(resp) or [""])[0] or ""
        path = out_dir / f"{t}_{fy}_{tag}_plain.md"
        path.write_text(f"<!-- prompt: {msg.replace(chr(10), ' ')} -->\n\n{text}", encoding="utf-8")
        print(f"Gespeichert: {path} ({len(text.split())} Woerter)")
        if not a.no_check:
            subprocess.run([sys.executable, str(AIF / "scripts" / "factcheck_text.py"), t, fy, str(path)], cwd=str(ROOT),
                           check=False)


if __name__ == "__main__":
    main()
