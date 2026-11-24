"""
Kompletter Lauf fuer die App (wird von lib/app_backend.start_run als eigener Prozess gestartet):
Plan -> Annual Reports -> Earnings Reviews -> (Committee, optional) -> Prognosen -> News -> Portfolio Review ->
Weekly Brief -> Dashboard. Konfiguration aus research/app_runs/<stamp>.json; Ende: <stamp>_done.json.
"""
import argparse
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
ROOT = AIF.parent
FR = ROOT / "finrobot_autogen"
sys.path.insert(0, str(AIF))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))
    done = {"ok": False, "finished": None, "error": None, "pipeline_log": None}
    try:
        from finrobot.utils import register_keys_from_json
        from lib import news_tracker as nt, pipeline as pl
        from lib.app_backend import DEFAULT_STEPS
        os.chdir(AIF / "scripts")
        register_keys_from_json(str(FR / "config_api_keys"))
        tickers = [t.upper() for t in cfg["tickers"]]
        watchlist = nt.watchlist_from_tickers(tickers)
        steps, _ = pl.plan(tickers)
        only = set(DEFAULT_STEPS) | ({"committee"} if cfg.get("include_committee") else set())
        todo = [s for s in steps if s["step"] in only]
        if cfg.get("max_steps"):
            todo = todo[: int(cfg["max_steps"])]
        print(pl.plan_table(steps).to_string(index=False), flush=True)
        print(f"PLAN_STEPS={len(todo)}", flush=True)
        m = cfg.get("model") or "anthropic/claude-haiku-5.5"
        cfgs = {"writer": pl.llm_config_for(m), "committee": pl.llm_config_for(m),
                "forecast": pl.llm_config_for(m, temperature=0.3),
                "classifier": pl.llm_config_for(m, temperature=0, max_tokens=8000)}
        log = pl.run_pipeline(steps, cfgs, tickers, transaction_files=cfg.get("transaction_files"),
                              portfolio_file=None if cfg.get("transaction_files") else cfg.get("portfolio_file"),
                              watchlist=watchlist, only=only, max_steps=cfg.get("max_steps"), name="app",
                              title="Portfolio Review")
        done.update(ok=True, pipeline_log=str(AIF / "research" / "pipeline_runs" / f"{log['started']}.json"),
                    dashboard=log.get("dashboard"), cost_usd=log.get("cost_usd"))
    except Exception as e:
        done["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()
    done["finished"] = datetime.now().isoformat(timespec="seconds")
    json.dump(done, open(str(a.config).replace(".json", "_done.json"), "w", encoding="utf-8"), indent=2)
    print("RUN_DONE", json.dumps(done), flush=True)


if __name__ == "__main__":
    main()
