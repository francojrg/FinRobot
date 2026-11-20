"""
Faktencheck fuer einen beliebigen Text, z. B. den Output eines einfachen Prompts
("Erstelle einen Equity Research Report zu ...") als Vergleich (Baseline) zum Agenten.

Der Text wird gegen dieselben Quellen geprueft wie die Agenten-Reports:
[1] 10-K (Items 1, 1A, 7), [2] Yahoo-Finanzdaten, [2][3] Konsens/Liquiditaet/Reverse DCF, [4] Peer-Daten.

Ausfuehren (aus dem FinRobot-Ordner):
    python ai_in_finance/scripts/factcheck_text.py RBRK 2026 ai_in_finance/reports/baseline/RBRK_chatgpt.md --peers SNOW CRWD
Unterstuetzt .txt, .md und .pdf. Ergebnis: <Datei>_factcheck.json daneben und eine Zusammenfassung.

Achtung: Fehlt das 10-K im Cache, werden 3 sec-api-Calls verbraucht.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
from finrobot.utils import register_keys_from_json  # noqa: E402

register_keys_from_json(str(ROOT / "finrobot_autogen" / "config_api_keys"))

from finrobot.data_source import FMPUtils  # noqa: E402
from finrobot.data_source.fmp_utils import _find_10k  # noqa: E402
from finrobot.data_source.sec_utils import SECUtils  # noqa: E402
from finrobot.functional.analyzer import ReportAnalysisUtils  # noqa: E402
from finrobot.functional.fact_check import SourceIndex, run_fact_check, save_json  # noqa: E402
from finrobot.functional.outlook import outlook_text  # noqa: E402
from finrobot.functional.reportlab import _collect_sources, _company_name, _peer_tickers_from_text  # noqa: E402


def read_text(path):
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(p)).pages)
    return p.read_text(encoding="utf-8", errors="ignore")


def split_sections(text):
    """Teilt Markdown an Ueberschriften; ohne Ueberschriften ein einziger Abschnitt."""
    parts = re.split(r"(?m)^#{1,4}\s+(.+)$", text)
    if len(parts) < 3:
        return [("Text", text)]
    out = [("Intro", parts[0])] if parts[0].strip() else []
    out += [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker")
    ap.add_argument("fyear", help="Geschaeftsjahr des 10-K (Periodenende), z. B. 2025")
    ap.add_argument("file")
    ap.add_argument("--peers", nargs="*", default=None, help="Peer-Ticker; sonst aus dem Text erkannt")
    a = ap.parse_args()
    t = a.ticker.upper()

    tenk = _find_10k(t, a.fyear)
    filing_date = tenk["filing_date"]
    fy = tenk["report_date"][:4]
    for item in ("1", "1A", "7"):  # fuellt den Cache, falls noetig
        SECUtils.get_10k_section(t, fy, item)

    text = read_text(a.file)
    sections = split_sections(text)
    metrics = FMPUtils.get_financial_metrics(t, years=5)
    key_data = ReportAnalysisUtils.get_key_data(t, filing_date)
    peers = a.peers if a.peers is not None else _peer_tickers_from_text(text, t)
    peer_metrics = {}
    for p in peers:
        try:
            peer_metrics[p] = FMPUtils.get_financial_metrics(p, years=4)
        except Exception as e:
            print(f"Peer {p} uebersprungen: {e}")
    srcs, n_tenk = _collect_sources(t, filing_date, metrics, key_data, peer_metrics)
    s3 = SourceIndex("[2][3] Liquidity and consensus")
    s3.add_text(outlook_text(t, fy))
    srcs.insert(2, s3)
    names = {x: _company_name(x) for x in [t] + list(peer_metrics)}
    fc = run_fact_check(sections, srcs, names)
    fc.update({"ticker": t, "fyear": fy, "filing_date": filing_date, "source_file": str(a.file),
               "peer_tickers": list(peer_metrics), "n_tenk_files": n_tenk, "kind": "baseline"})
    out = Path(a.file).with_suffix("")
    out = out.parent / (out.name + "_factcheck.json")
    save_json(fc, str(out))
    rate = f"{fc['match_rate'] * 100:.0f}%" if fc["match_rate"] is not None else "n/a"
    print(f"Faktencheck {t}: {fc['matched']} von {fc['total_claims']} Zahlen in den Quellen gefunden ({rate}); "
          f"Namensfehler: {len(fc['name_issues'])}; 10-K-Dateien: {n_tenk}")
    print(f"Gespeichert: {out}")


if __name__ == "__main__":
    main()
