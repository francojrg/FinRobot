"""
Testsatz fuer den Portfolio-Upload: erzeugt typische CSV-Varianten in eval/upload_tests/ und prueft, was die App
daraus erkennt (lib.app_backend.inspect_portfolio). Kein LLM, keine Kosten; nur Test 16 (ISIN) braucht Internet.

    python ai_in_finance/scripts/test_upload.py
"""
import sys
from pathlib import Path

AIF = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AIF))
OUT = AIF / "eval" / "upload_tests"

# Name -> (Inhalt, Kodierung, erwartet). erwartet: {"kind", "pos": {ticker: wert}, "issue": Textteil} oder {"error": Textteil}
CASES = {
    "01_komma_prozent.csv": ("ticker,weight\nAAPL,40\nMSFT,35\nSAP.DE,25\n", "utf-8",
                             {"kind": "weights", "pos": {"AAPL": 40, "MSFT": 35, "SAP.DE": 25}}),
    "02_semikolon_deutsch.csv": ("Ticker;Gewicht\nAAPL;40,5\nMSFT;35,25\nSAP.DE;24,25\n", "utf-8",
                                 {"kind": "weights", "pos": {"AAPL": 40.5, "MSFT": 35.25, "SAP.DE": 24.25}}),
    "03_anteile.csv": ("ticker,weight\nAAPL,0.5\nMSFT,0.3\nNVDA,0.2\n", "utf-8",
                       {"kind": "weights", "pos": {"AAPL": 0.5, "MSFT": 0.3, "NVDA": 0.2}}),
    "04_summe_ungleich_100.csv": ("ticker,weight\nAAPL,30\nMSFT,30\nNVDA,30\n", "utf-8",
                                  {"kind": "weights", "issue": "summieren sich auf 90"}),
    "05_stueck_deutsche_spalten.csv": ("Symbol;Stück;Einstandskurs\nAAPL;10;150,20\nNVDA;1.200;45,10\n", "utf-8",
                                       {"kind": "shares", "pos": {"AAPL": 10, "NVDA": 1200}}),
    "06_kleinschreibung.csv": (" ticker , weight \n aapl , 50\nbrk.b,50\n", "utf-8",
                               {"kind": "weights", "pos": {"AAPL": 50, "BRK-B": 50}}),
    "07_doppelt.csv": ("ticker,shares\nAAPL,5\nMSFT,3\nAAPL,5\n", "utf-8",
                       {"kind": "shares", "pos": {"AAPL": 10, "MSFT": 3}, "issue": "mehrfach"}),
    "08_excel_bom_prozentzeichen.csv": ("Ticker;Name;Anteil\nAAPL;Apple;40 %\nSIE.DE;Siemens Müller;60 %\n", "utf-8-sig",
                                        {"kind": "weights", "pos": {"AAPL": 40, "SIE.DE": 60}}),
    "09_excel_ansi.csv": ("Ticker;Name;Anteil\nAAPL;Apple;40\nSIE.DE;Börse Düsseldorf;60\n", "cp1252",
                          {"kind": "weights", "pos": {"AAPL": 40, "SIE.DE": 60}}),
    "10_leere_zeilen.csv": ("ticker,weight,\n\nAAPL,50,\n,,\nMSFT,50,\n\n", "utf-8",
                            {"kind": "weights", "pos": {"AAPL": 50, "MSFT": 50}}),
    "11_gemischt.csv": ("ticker,shares,weight\nAAPL,10,\nMSFT,,30\nNVDA,,20\n", "utf-8",
                        {"kind": "weights", "pos": {"MSFT": 30, "NVDA": 20}, "issue": "übersprungen"}),
    "12_negativ_null.csv": ("ticker,weight\nAAPL,60\nMSFT,0\nNVDA,-5\nAMZN,40\n", "utf-8",
                            {"kind": "weights", "pos": {"AAPL": 60, "AMZN": 40}, "issue": "übersprungen"}),
    "13_tabulator.csv": ("ticker\tweight\nAAPL\t50\nMSFT\t50\n", "utf-8",
                         {"kind": "weights", "pos": {"AAPL": 50, "MSFT": 50}}),
    "14_keine_zahl.csv": ("ticker,weight\nAAPL,50\nMSFT,viel\nNVDA,50\n", "utf-8",
                          {"kind": "weights", "pos": {"AAPL": 50, "NVDA": 50}, "issue": "keine Zahl"}),
    "15_falsche_spalten.csv": ("Name,Wert\nApple,100\n", "utf-8", {"error": "Format nicht erkannt"}),
    "16_isin.csv": ("isin,weight\nUS0378331005,50\nUS5949181045,50\n", "utf-8",
                    {"kind": "weights", "pos": {"AAPL": 50, "MSFT": 50}, "network": True}),
    "17_leer.csv": ("", "utf-8", {"error": "leer"}),
    "18_nur_kopfzeile.csv": ("ticker,weight\n", "utf-8", {"error": "keine Positionen"}),
    "19_transaktionen.csv": ("date,type,ticker,shares,price,currency,fees,amount\n"
                             "2024-01-15,buy,AAPL,10,180,USD,1,\n2024-06-03,buy,MSFT,5,410,USD,1,\n"
                             "2025-02-10,sell,AAPL,4,230,USD,1,\n", "utf-8",
                             {"kind": "transactions", "pos": {"AAPL": 6, "MSFT": 5}}),
}


def check(info, exp):
    probs = []
    if "error" in exp:
        return ["kein Fehler gemeldet"]
    if info["kind"] != exp["kind"]:
        probs.append(f"erkannt als {info['kind']}, erwartet {exp['kind']}")
    got = {p["ticker"]: p.get("weight", p.get("shares")) for p in info["positions"]}
    for t, v in exp.get("pos", {}).items():
        if t not in got:
            probs.append(f"{t} fehlt")
        elif abs(float(got[t]) - v) > 1e-6:
            probs.append(f"{t}: {got[t]} statt {v}")
    if exp.get("pos") and set(got) - set(exp["pos"]):
        probs.append("zusaetzlich: " + ", ".join(sorted(set(got) - set(exp["pos"]))))
    if exp.get("issue") and not any(exp["issue"] in i for i in info["issues"]):
        probs.append(f"Hinweis '{exp['issue']}' fehlt")
    return probs


def main():
    from lib.app_backend import inspect_portfolio
    OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name, (text, enc, exp) in CASES.items():
        p = OUT / name
        p.write_bytes(text.encode(enc))
        try:
            info = inspect_portfolio(p)
            probs = check(info, exp)
            detail = (f"{info['kind']}: " + ", ".join(f"{x['ticker']}={x.get('weight', x.get('shares')):g}"
                                                     for x in info["positions"]))
            if info["issues"]:
                detail += " | Hinweise: " + "; ".join(info["issues"])
        except Exception as e:
            probs = [] if "error" in exp and exp["error"].lower() in str(e).lower() else [f"Fehler: {e}"]
            detail = f"Fehlermeldung: {e}"
        tag = "OK  " if not probs else ("NETZ" if exp.get("network") else "FAIL")
        ok += not probs
        print(f"{tag} {name:34s} {detail}" + ("" if not probs else "\n     -> " + "; ".join(probs)))
    print(f"\n{ok} von {len(CASES)} Faellen wie erwartet.")


if __name__ == "__main__":
    main()
