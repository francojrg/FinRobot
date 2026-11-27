"""
Pruefung fuer 20-F-Emittenten (z. B. ASML, TSM) vor einem kompletten Lauf. Ruft nur Datenquellen auf (EDGAR, Yahoo),
kein LLM, keine Kosten. Gibt je Titel aus: Jahresbericht, gefundene Abschnitte, Quartalsmitteilungen, Kennzahlen,
Reverse DCF. Zum Vergleich einen US-Titel mitgeben (z. B. MA).

    python ai_in_finance/scripts/check_foreign_filer.py ASML TSM MA
"""
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AIF = ROOT / "ai_in_finance"
sys.path.insert(0, str(ROOT / "finrobot_autogen"))
sys.path.insert(0, str(AIF))


def step(name, fn):
    try:
        out = fn()
        print(f"  [ok] {name}: {out}")
        return True
    except Exception as e:
        print(f"  [FEHLER] {name}: {type(e).__name__}: {str(e)[:300]}")
        traceback.print_exc(limit=1)
        return False


def main(tickers):
    from finrobot.utils import register_keys_from_json
    register_keys_from_json(str(ROOT / "finrobot_autogen" / "config_api_keys"))
    from finrobot.data_source.fmp_utils import FMPUtils, _find_10k
    from finrobot.data_source.sec_utils import SECUtils
    from finrobot.functional.outlook import get_consensus, reverse_dcf
    from lib import pipeline as pl, quarterly_data as qd

    for t in tickers:
        print(f"\n=== {t} ===")
        hit = {}

        def annual():
            hit.update(_find_10k(t, "latest"))
            return f"{hit['form']} fuer {hit['report_date']}, eingereicht {hit['filing_date']}, {hit['url']}"
        if not step("Jahresbericht", annual):
            continue
        fy = hit["report_date"][:4]
        step("EDGAR-Status (Plan)", lambda: {k: v for k, v in pl.edgar_status(t).items() if k != "releases"}
             | {"releases (letzte 4)": pl.edgar_status(t)["releases"][-4:]})
        for sec in ("1", "1A", "7"):
            def section(sec=sec):
                txt = SECUtils.get_10k_section(t, fy, sec)
                first = txt.splitlines()[0][:120] if txt else ""
                return f"{len(txt):,} Zeichen | {first}"
            step(f"Abschnitt {sec}", section)

        def release():
            r = qd.earnings_release(t)
            if r.get("error"):
                raise RuntimeError(r["error"])
            return f"eingereicht {r['filing_date']}, {len(r['text']):,} Zeichen, {r.get('url', '')} | {r['text'][:150]!r}"
        step("Letzte Quartalsmitteilung", release)

        def releases():
            rs = qd.earnings_releases_since(t, hit["report_date"])
            return "; ".join(f"{r.get('filing_date')}: {'ok ' + format(len(r['text']), ',') + ' Z.' if not r.get('error') else r['error']}"
                             for r in rs)
        step("Mitteilungen seit Jahresbericht", releases)

        def metrics():
            m = FMPUtils.get_financial_metrics(t)
            rows = [r for r in ("Revenue", "EBITDA Margin", "EV/EBITDA", "PE Ratio", "PB Ratio") if r in m.index]
            return "\n" + m.loc[rows].to_string()
        step("Kennzahlen (Yahoo, Berichtswaehrung)", metrics)

        def rdcf():
            r = reverse_dcf(t, fy=int(fy))
            if r.get("error"):
                raise RuntimeError(r["error"])
            return (f"EV {r['ev']:,.0f} Mio. | Umsatz FY{r['fy']} {r['rev0']:,.0f} Mio. | FCF-Marge {r['m0']:.1%} | "
                    f"WACC {r['wacc']:.1%} | implizites Wachstum {r['implied_g']}")
        step("Reverse DCF", rdcf)

        def cons():
            c = get_consensus(t)
            if c.get("error"):
                raise RuntimeError(c["error"])
            return "; ".join(f"FY{y['fy']}: Umsatz {y['rev']}, Fwd P/E {y['pe']}, Fwd EV/Sales {y['ev_sales']}"
                             for y in c["years"]) + (f" | {c['currency_note']}" if c.get("currency_note") else "")
        step("Konsens", cons)


if __name__ == "__main__":
    main([a.upper() for a in sys.argv[1:]] or ["ASML", "TSM", "MA"])
