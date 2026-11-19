"""Diagnose: welche FMP-Endpunkte (alt /api/v3 vs. neu /stable) und SEC EDGAR funktionieren?
Ausfuehren (beliebiger Ordner): python ai_in_finance/scripts/check_data_sources.py
Gibt nur Statuscodes und Feldnamen aus, niemals API-Keys."""
import os, json, requests
from finrobot.utils import register_keys_from_json

from pathlib import Path
register_keys_from_json(str(Path(__file__).resolve().parents[2] / "finrobot_autogen" / "config_api_keys"))
KEY = os.environ.get("FMP_API_KEY", "")
T = "RKLB"
print("FMP-Key gesetzt:", bool(KEY) and not KEY.startswith("YOUR_"))

tests = {
    "v3  sec_filings":        f"https://financialmodelingprep.com/api/v3/sec_filings/{T}?type=10-k&page=0",
    "v3  income-statement":   f"https://financialmodelingprep.com/api/v3/income-statement/{T}?limit=2",
    "st  income-statement":   f"https://financialmodelingprep.com/stable/income-statement?symbol={T}&limit=5",
    "st  key-metrics":        f"https://financialmodelingprep.com/stable/key-metrics?symbol={T}&limit=5",
    "st  ratios":             f"https://financialmodelingprep.com/stable/ratios?symbol={T}&limit=5",
    "st  hist-market-cap":    f"https://financialmodelingprep.com/stable/historical-market-capitalization?symbol={T}&from=2025-03-03&to=2025-03-07",
    "st  price-target-cons.": f"https://financialmodelingprep.com/stable/price-target-consensus?symbol={T}",
    "st  income-stmt AAPL":   "https://financialmodelingprep.com/stable/income-statement?symbol=AAPL&limit=2",
    "st  profile RKLB":       f"https://financialmodelingprep.com/stable/profile?symbol={T}",
    "st  sec-filings-search": f"https://financialmodelingprep.com/stable/sec-filings-search/symbol?symbol={T}&from=2025-01-01&to=2025-12-31&limit=50",
}
for name, url in tests.items():
    try:
        r = requests.get(url + ("&" if "?" in url else "?") + "apikey=" + KEY, timeout=20)
        try:
            body = r.json()
        except ValueError:
            body = f"(kein JSON, content-type={r.headers.get('content-type')}) " + r.text[:200].replace(KEY, "***")
        if isinstance(body, list) and body:
            info = f"{len(body)} Eintraege, Felder: {sorted(body[0].keys())}"
            if "formType" in body[0]:
                info += f" | Formulare: {sorted({b.get('formType') for b in body})}"
        elif isinstance(body, dict):
            info = str({k: str(v)[:120] for k, v in list(body.items())[:2]})
        else:
            info = str(body)[:150]
        print(f"[{r.status_code}] {name}: {info.replace(KEY, '***') if KEY else info}")
    except Exception as e:
        print(f"[ERR] {name}: {type(e).__name__}: {e}")

# SEC EDGAR (kostenlos, ohne Key). Die SEC verlangt einen User-Agent mit Kontakt.
ua = os.environ.get("SEC_USER_AGENT")
print("\nSEC_USER_AGENT gesetzt:", bool(ua))
if ua:
    h = {"User-Agent": ua}
    try:
        m = requests.get("https://www.sec.gov/files/company_tickers.json", headers=h, timeout=20)
        cik = next(v["cik_str"] for v in m.json().values() if v["ticker"] == T)
        s = requests.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=h, timeout=20).json()
        rec = s["filings"]["recent"]
        tenk = [(d, a, p) for f, d, a, p in zip(rec["form"], rec["filingDate"], rec["accessionNumber"], rec["primaryDocument"]) if f == "10-K"]
        print(f"[OK] EDGAR: CIK {cik}, 10-Ks: {[t[0] for t in tenk[:3]]}")
        if tenk:
            d, a, p = tenk[0]
            print("     Link:", f"https://www.sec.gov/Archives/edgar/data/{cik}/{a.replace('-', '')}/{p}")
    except Exception as e:
        print(f"[ERR] EDGAR: {type(e).__name__}: {e}")
