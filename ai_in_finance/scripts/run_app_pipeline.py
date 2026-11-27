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
        from lib.tool_repair import install as _install_tool_repair
        _install_tool_repair()                  # abgeschnittene/zerlegte Tool-Aufrufe reparieren
        os.chdir(AIF / "scripts")
        register_keys_from_json(str(FR / "config_api_keys"))
        tickers = [t.upper() for t in cfg["tickers"]]
        watch = [t.upper() for t in cfg.get("watch") or [] if t.upper() not in tickers]   # Watchlist (nur News/Reports)
        watchlist = nt.watchlist_from_tickers(tickers + watch)
        steps, _ = pl.plan(tickers + watch, **(cfg.get("plan_args") or {}))
        only = set(cfg["steps"]) if cfg.get("steps") else \
            set(DEFAULT_STEPS) | ({"committee"} if cfg.get("include_committee") else set())
        if cfg.get("select"):                        # Automatik: genau die vorab geprueften Schritte (Schritt, Titel)
            sel = {tuple(x) for x in cfg["select"]}
            have = {(s["step"], s["ticker"]) for s in steps}
            steps = [s for s in steps if (s["step"], s["ticker"]) in sel]
            steps += [{"step": k, "ticker": t, "reason": "Automatik: woechentlich"} for k, t in sorted(sel - have)
                      if k in ("portfolio", "brief")]
        todo = [s for s in steps if s["step"] in only]
        if cfg.get("max_steps"):
            todo = todo[: int(cfg["max_steps"])]
        print(pl.plan_table(steps).to_string(index=False), flush=True)
        print(f"PLAN_STEPS={len(todo)}", flush=True)
        m = cfg.get("model") or "anthropic/claude-haiku-5.5"
        cfgs = {"writer": pl.llm_config_for(m), "committee": pl.llm_config_for(m),
                "forecast": pl.llm_config_for(m, temperature=0.3),
                "classifier": pl.llm_config_for(m, temperature=0, max_tokens=8000)}
        runner = None
        if cfg.get("budget_usd"):                    # Monatsbudget: vor jedem Schritt pruefen
            from lib import automation as au
            spent0, use0 = au.month_spend(), pl.openrouter_usage(cfgs["writer"])

            def runner(step, cfgs_, ctx):
                now = pl.openrouter_usage(cfgs_["writer"])
                spent = spent0 + ((now - use0) if now is not None and use0 is not None else 0)
                need = au.est_usd(step["step"], len(tickers))
                if spent + need > float(cfg["budget_usd"]):
                    print(f"BUDGET: {step['step']} {step['ticker']} uebersprungen ({spent:.2f} von {cfg['budget_usd']} USD verbraucht)")
                    return {"ok": False, "error": f"Monatsbudget erreicht ({spent:.2f} von {cfg['budget_usd']} USD)"}
                return pl._run_step(step, cfgs_, ctx)
        log = pl.run_pipeline(steps, cfgs, tickers, transaction_files=cfg.get("transaction_files"),
                              portfolio_file=None if cfg.get("transaction_files") else cfg.get("portfolio_file"),
                              watchlist=watchlist, only=only, max_steps=cfg.get("max_steps"), name="app",
                              title="Portfolio Review", runner=runner)
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
