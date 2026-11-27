"""
Pipeline von der Kommandozeile (z. B. woechentlich per Windows-Aufgabenplanung):

  python scripts/run_pipeline.py --top 5 --dry-run          # nur Plan anzeigen
  python scripts/run_pipeline.py --top 5 --max-steps 8      # ausfuehren (hoechstens 8 Agentenlaeufe)
  python scripts/run_pipeline.py --tickers RBRK RKLB --only forecast committee

Transaktions-Exporte: --tx (Standard: portfolios/traderepublic.csv und portfolios/ScalableCapital.csv, falls vorhanden).
Protokoll: research/pipeline_runs/<Zeitstempel>.md
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIF = ROOT / "ai_in_finance"
FR = ROOT / "finrobot_autogen"
sys.path.insert(0, str(AIF))

from finrobot.utils import register_keys_from_json  # noqa: E402
from lib import news_tracker as nt, pipeline as pl  # noqa: E402
from lib.tool_repair import install as _install_tool_repair  # noqa: E402
_install_tool_repair()                  # abgeschnittene/zerlegte Tool-Aufrufe reparieren


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5, help="groesste Positionen aus den Transaktionen")
    ap.add_argument("--tickers", nargs="*", help="statt --top: feste Tickerliste")
    ap.add_argument("--tx", nargs="*", help="Transaktions-Exporte")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-steps", type=int)
    ap.add_argument("--only", nargs="*", choices=pl.STEP_ORDER)
    ap.add_argument("--model", default="anthropic/claude-haiku-5.5")
    ap.add_argument("--no-portfolio", action="store_true")
    a = ap.parse_args()
    os.chdir(AIF / "scripts")
    register_keys_from_json(str(FR / "config_api_keys"))
    tx = a.tx or [str(p) for p in (AIF / "portfolios" / "traderepublic.csv", AIF / "portfolios" / "ScalableCapital.csv")
                  if p.exists()]
    if a.tickers:
        watchlist = [{"ticker": t.upper(), "name": t.upper(), "query": t.upper(), "track": "yes"} for t in a.tickers]
    else:
        watchlist = nt.top_watchlist(tx, n=a.top)
    tickers = [w["ticker"] for w in watchlist]
    steps, _ = pl.plan(tickers, with_portfolio=not a.no_portfolio and bool(tx))
    print(pl.plan_table(steps).to_string(index=False))
    if a.dry_run:
        return
    cfgs = {"writer": pl.llm_config_for(a.model), "committee": pl.llm_config_for(a.model),
            "forecast": pl.llm_config_for(a.model, temperature=0.3),
            "classifier": pl.llm_config_for(a.model, temperature=0, max_tokens=8000)}
    pl.run_pipeline(steps, cfgs, tickers, transaction_files=tx, watchlist=watchlist, max_steps=a.max_steps,
                    only=set(a.only) if a.only else None)


if __name__ == "__main__":
    main()
