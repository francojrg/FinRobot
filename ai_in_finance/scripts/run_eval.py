"""
Evaluation: laesst den Annual-Report-Agenten fuer mehrere Firmen und Modelle nacheinander laufen
und protokolliert je Lauf Laufzeit, Tool-Aufrufe, Fehler, Tokens, Kosten und das Faktencheck-Ergebnis.

Ausfuehren (aus dem FinRobot-Ordner), Beispiele:
    python ai_in_finance/scripts/run_eval.py --runs RKLB:2025 UBER:2025 --models anthropic/claude-haiku-5.5
    python ai_in_finance/scripts/run_eval.py --runs RKLB:2025 --models anthropic/claude-haiku-5.5 google/gemini-4-neon

Ergebnis je Lauf: reports/<FIRMA>_<JAHR>_<MODELL>_eval/  (PDF, Faktencheck-JSON, run_meta.json, run_log.txt)
Danach: python ai_in_finance/scripts/eval_summary.py

Hinweise:
- Ohne Cache, damit jeder Lauf echt ist (kostet also jedes Mal Guthaben).
- Neue Firmen kosten 3 sec-api-Calls (10-K-Abschnitte), danach liegt das 10-K im Cache.
- Kosten = Differenz des OpenRouter-Verbrauchs vor/nach dem Lauf (nur korrekt, wenn der Key
  waehrenddessen nicht anderweitig genutzt wird).
"""
import argparse
import contextlib
import glob
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIF = ROOT / "ai_in_finance"
FR = ROOT / "finrobot_autogen"
sys.path.insert(0, str(AIF))

import autogen  # noqa: E402
from finrobot.utils import register_keys_from_json  # noqa: E402
from lib import report_agent  # noqa: E402


class Tee:
    """Schreibt die Konsolenausgabe zusaetzlich in eine Logdatei."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def llm_config_for(model, reasoning="low"):
    base = json.load(open(FR / "OAI_CONFIG_LIST", encoding="utf-8"))
    entry = next((e for e in base if e.get("model") == model), None)
    if entry is None:  # gleicher OpenRouter-Key, anderes Modell
        tpl = next(e for e in base if "openrouter" in str(e.get("base_url", "")))
        entry = dict(tpl, model=model)
    cfg = {"config_list": [entry], "timeout": 300, "temperature": 0.5,
           "parallel_tool_calls": False, "max_tokens": 16000}
    if model.startswith("google/") and reasoning:
        cfg["extra_body"] = {"reasoning": {"effort": reasoning}}
    return cfg, entry


def openrouter_usage(entry):
    """Bisheriger Gesamtverbrauch des Keys in USD (None, falls nicht abrufbar)."""
    if "openrouter" not in str(entry.get("base_url", "")):
        return None
    try:
        import requests
        r = requests.get("https://openrouter.ai/api/v1/key",
                         headers={"Authorization": f"Bearer {entry['api_key']}"}, timeout=20)
        return float(r.json()["data"]["usage"])
    except Exception:
        return None


def token_usage(clients):
    p = c = 0
    for cl in clients:
        summ = getattr(cl, "total_usage_summary", None) or {}
        for k, v in summ.items():
            if isinstance(v, dict):
                p += v.get("prompt_tokens", 0)
                c += v.get("completion_tokens", 0)
    return p, c


def analyse_history(messages):
    tools, errors, builds = {}, [], 0
    for m in messages:
        for tc in m.get("tool_calls") or []:
            name = tc.get("function", {}).get("name", "?")
            tools[name] = tools.get(name, 0) + 1
            builds += name == "build_annual_report"
        if m.get("role") == "tool" or m.get("tool_responses"):
            for tr in m.get("tool_responses") or [m]:
                txt = str(tr.get("content", ""))
                if any(x in txt for x in ("Traceback", "Error:", "PDF NOT generated", "Ignored unknown parameters")):
                    errors.append(txt[:300])
    return tools, errors, builds


def run_one(company, fyear, model, reasoning, max_rounds, peers=None):
    tag = model.split("/")[-1]
    suffix = "_eval" if os.environ.get("FINROBOT_SELF_CORRECT", "1") != "0" else "_eval_nosc"
    work_dir_abs = AIF / "reports" / f"{company}_{fyear}_{tag}{suffix}"
    work_dir_abs.mkdir(parents=True, exist_ok=True)
    os.chdir(AIF / "notebooks")  # gleiche relativen Pfade wie im Notebook
    work_dir = f"../reports/{work_dir_abs.name}"
    cfg, entry = llm_config_for(model, reasoning)
    meta = {"company": company, "fyear": fyear, "model": model, "reasoning": cfg.get("extra_body"),
            "started": datetime.now().isoformat(timespec="seconds"), "max_rounds": max_rounds,
            "self_correct": os.environ.get("FINROBOT_SELF_CORRECT", "1") != "0"}
    usage_before = openrouter_usage(entry)
    t0 = time.time()
    log = open(work_dir_abs / "run_log.txt", "w", encoding="utf-8")
    agent = None
    try:
        with contextlib.redirect_stdout(Tee(sys.__stdout__, log)):
            agent = report_agent.build_agent(cfg, max_rounds=max_rounds)
            msg = report_agent.default_message(company, fyear, work_dir, peers)
            agent.user_proxy.initiate_chat(agent.assistant, message=msg, cache=None, max_turns=60)
        meta["exception"] = None
    except Exception as e:  # Lauf abgebrochen (z. B. API-Fehler) - trotzdem protokollieren
        meta["exception"] = f"{type(e).__name__}: {e}"[:500]
    finally:
        log.close()
    meta["seconds"] = round(time.time() - t0, 1)
    usage_after = openrouter_usage(entry)
    meta["cost_usd"] = round(usage_after - usage_before, 4) if None not in (usage_before, usage_after) else None
    if agent is not None:
        msgs = agent.user_proxy.chat_messages.get(agent.assistant, [])
        tools, errors, builds = analyse_history(msgs)
        p, c = token_usage([agent.assistant.client] + list(report_agent.ANALYSIS_CLIENTS))
        meta.update({"n_messages": len(msgs), "tool_calls": tools, "n_tool_calls": sum(tools.values()),
                     "tool_errors": errors, "n_tool_errors": len(errors), "build_attempts": builds,
                     "prompt_tokens": p, "completion_tokens": c})
    pdfs = [f for f in glob.glob(str(work_dir_abs / "*.pdf")) if os.path.getmtime(f) >= t0]
    fcs = [f for f in glob.glob(str(work_dir_abs / "*_factcheck.json")) if os.path.getmtime(f) >= t0
           and not f.endswith("_round1_factcheck.json")]
    meta["success"] = bool(pdfs)
    if fcs:
        fc = json.load(open(fcs[-1], encoding="utf-8"))
        meta.update({"claims": fc["total_claims"], "matched": fc["matched"], "match_rate": fc["match_rate"],
                     "name_issues": len(fc["name_issues"]), "peers": fc.get("peer_tickers"),
                     "build_round": fc.get("build_round"), "round1": fc.get("round1")})
    json.dump(meta, open(work_dir_abs / "run_meta.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="+", required=True, help="FIRMA:JAHR, z. B. RKLB:2025 UBER:2025")
    ap.add_argument("--models", nargs="+", default=["anthropic/claude-haiku-5.5"])
    ap.add_argument("--reasoning", default="low", help="Denkaufwand fuer Gemini-Modelle (low/medium/high)")
    ap.add_argument("--max-rounds", type=int, default=30)
    ap.add_argument("--no-self-correct", action="store_true",
                    help="Selbstkorrektur abschalten (Vergleichslauf); Ordner bekommt den Zusatz _nosc")
    a = ap.parse_args()
    register_keys_from_json(str(FR / "config_api_keys"))
    os.environ["FINROBOT_SELF_CORRECT"] = "0" if a.no_self_correct else "1"
    for model in a.models:
        for run in a.runs:
            company, fyear = run.split(":")
            print(f"\n===== {company} {fyear} | {model} =====")
            m = run_one(company.upper(), fyear, model, a.reasoning, a.max_rounds)
            print(f"-> Erfolg: {m['success']}, {m['seconds']} s, Kosten: {m.get('cost_usd')} USD, "
                  f"Faktencheck: {m.get('matched')}/{m.get('claims')}, Tool-Fehler: {m.get('n_tool_errors')}")


if __name__ == "__main__":
    main()
