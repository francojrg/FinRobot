"""Test der neuen Datenabrufe (EDGAR + Yahoo statt FMP). Ausfuehren in finrobot_autogen:
    python scripts/test_new_data.py RKLB 2025
Jeder Schritt wird einzeln geprueft; Fehler werden angezeigt, nicht verschluckt."""
import sys, traceback
from finrobot.utils import register_keys_from_json
register_keys_from_json("config_api_keys")
from finrobot.data_source import FMPUtils, SECUtils
from finrobot.functional.analyzer import ReportAnalysisUtils

T = sys.argv[1] if len(sys.argv) > 1 else "RKLB"
FY = sys.argv[2] if len(sys.argv) > 2 else "2025"

def step(name, fn):
    print(f"\n=== {name}")
    try:
        out = fn()
        print(out if not isinstance(out, str) or len(out) < 800 else out[:800] + " [...]")
        return out
    except Exception:
        traceback.print_exc(limit=2)

rep = step("10-K aus EDGAR", lambda: FMPUtils.get_sec_report(T, FY))
filing_date = rep.split("Filing Date: ")[1].split()[0] if rep else None
step("Kennzahlen (Yahoo)", lambda: FMPUtils.get_financial_metrics(T, years=5))
if filing_date:
    step("Marktkapitalisierung am Einreichungstag", lambda: f"{FMPUtils.get_historical_market_cap(T, filing_date)/1e6:,.0f} Mio.")
    step("BVPS", lambda: FMPUtils.get_historical_bvps(T, filing_date))
    step("Key Data fuer den Report", lambda: ReportAnalysisUtils.get_key_data(T, filing_date))
step("Kursziel", lambda: FMPUtils.get_target_price(T, filing_date or "latest"))
step("10-K Abschnitt 1A (Risiken) ueber sec-api", lambda: SECUtils.get_10k_section(T, FY, "1A"))
