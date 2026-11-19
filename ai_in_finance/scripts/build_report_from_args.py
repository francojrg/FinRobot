"""Baut den PDF-Report aus gespeicherten Argumenten eines Agenten-Laufs (ohne neuen LLM-Aufruf).
Nuetzlich, wenn ein Lauf erst beim letzten Schritt (build_annual_report) gescheitert ist.

Ausfuehren (aus dem FinRobot-Ordner):
    python ai_in_finance/scripts/build_report_from_args.py ai_in_finance/reports/RKLB_2025_claude-haiku-5.5/RKLB_2025_build_args.json
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
from finrobot.utils import register_keys_from_json
register_keys_from_json(str(ROOT / "finrobot_autogen" / "config_api_keys"))
from finrobot.functional.reportlab import ReportLabUtils
import inspect

args_file = Path(sys.argv[1]).resolve()
args = json.load(open(args_file, encoding="utf-8"))
allowed = set(inspect.signature(ReportLabUtils.build_annual_report).parameters)
dropped = [k for k in args if k not in allowed]
args = {k: v for k, v in args.items() if k in allowed}
if dropped:
    print("Ignoriert (kein Parameter):", dropped)
os.chdir(ROOT / "ai_in_finance" / "notebooks")  # Pfade im Agenten-Lauf sind relativ zu notebooks/
print(ReportLabUtils.build_annual_report(**args))
