"""
Musterdepot aus 13F-Meldungen nachbauen (z. B. Valley Forge Capital Management, CIK 1697868).

Ablauf:
1. Alle 13F-HR des Managers von SEC EDGAR laden (je Quartal die neueste Meldung, Berichtigungen ersetzen das Original).
2. Je Quartal die Stueckzahlen je Wertpapier (CUSIP) aus der Infotabelle; nur Aktien (SH), keine Optionen.
3. CUSIP -> Ticker ueber den Emittentennamen und die SEC-Tickerliste (plus feste Zuordnungen fuer ADRs).
4. Splits (Yahoo) herausrechnen, damit z. B. der 10:1-Split von Nvidia nicht als Kauf erscheint.
5. Selbstfinanziertes Musterdepot: Start mit --start-value; an jedem Stichtag werden die Gewichte des Fonds
   nachgebildet, aber nur mit dem eigenen Depotwert (Kaeufe aus Verkaeufen bezahlt, keine Zufluesse wie beim
   Fonds). Kurse leer: die App setzt den Schlusskurs am Buchungstag ein.
Zwei Dateien:
   <name>_quarter.csv  gebucht zum Quartalsende   (ungefaehr das Depot des Managers)
   <name>_filed.csv    gebucht am Tag der Meldung (so haette ein Privatanleger es kopieren koennen, ~45 Tage spaeter)

Grenzen: Handel innerhalb eines Quartals ist unsichtbar; nur US-gelistete Long-Positionen; keine Kasse.

    python ai_in_finance/scripts/build_13f_portfolio.py --cik 1697868 --name sample_transactions_vfc
"""
import argparse
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AIF = ROOT / "ai_in_finance"
sys.path.insert(0, str(ROOT / "finrobot_autogen"))

# Feste Zuordnungen: ADRs/Auslaender, umbenannte Firmen (Facebook -> META) und Namen, die in der heutigen
# SEC-Liste falsch treffen wuerden (INTUIT -> Intuitive Surgical, ASPEN TECHNOLOGY -> Aspen Aerogels)
FIXED = {"N07059210": "ASML", "874039100": "TSM", "30303M102": "META", "461202103": "INTU", "294429105": "EFX",
         "045327103": "AZPN", "29109X106": "AZPN"}
DROP_WORDS = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COM", "LTD", "LIMITED", "PLC", "NV", "N.V.", "SA",
              "HLDG", "HLDGS", "HOLDING", "HOLDINGS", "GROUP", "THE", "CL", "A", "B", "C", "NEW", "DEL", "&", "AND"}


def _headers():
    import os
    from finrobot.utils import register_keys_from_json
    register_keys_from_json(str(ROOT / "finrobot_autogen" / "config_api_keys"))
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise SystemExit("SEC_USER_AGENT fehlt (Einstellungen der App).")
    return {"User-Agent": ua}


def _get(url, h, tries=3):
    import requests
    for i in range(tries):
        r = requests.get(url, headers=h, timeout=60)
        if r.status_code == 200:
            return r
        time.sleep(1 + i)
    r.raise_for_status()


def filings(cik, h):
    rec = _get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", h).json()
    blocks = [rec["filings"]["recent"]]
    for f in rec["filings"].get("files", []):              # aeltere Einreichungen in Zusatzdateien
        blocks.append(_get(f"https://data.sec.gov/submissions/{f['name']}", h).json())
    out = []
    for r in blocks:
        for form, fd, rd, acc in zip(r["form"], r["filingDate"], r["reportDate"], r["accessionNumber"]):
            if form in ("13F-HR", "13F-HR/A") and rd:
                out.append({"form": form, "filed": fd, "period": rd, "acc": acc})
    best = {}
    for f in sorted(out, key=lambda x: x["filed"]):        # je Quartal die letzte Meldung
        best[f["period"]] = f
    return [best[k] for k in sorted(best)]


def infotable(cik, acc, h):
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
    idx = _get(f"{base}/index.json", h).json()
    names = [i["name"] for i in idx["directory"]["item"]]
    xmls = [n for n in names if n.lower().endswith(".xml") and "primary_doc" not in n.lower()]
    if not xmls:
        raise RuntimeError(f"keine Infotabelle in {acc}")
    root = ET.fromstring(_get(f"{base}/{xmls[0]}", h).content)
    rows = []
    for it in root.iter():
        if not it.tag.endswith("infoTable"):
            continue
        g = lambda tag: next((c.text for c in it.iter() if c.tag.endswith(tag)), None)
        if (g("putCall") or "").strip() or (g("sshPrnamtType") or "SH").strip() != "SH":
            continue
        rows.append({"name": (g("nameOfIssuer") or "").strip(), "cusip": (g("cusip") or "").strip().upper(),
                     "value": float(g("value") or 0), "shares": float(g("sshPrnamt") or 0)})
    return rows


def _norm(name):
    w = re.sub(r"[^A-Z0-9& ]", " ", name.upper()).split()
    return [x for x in w if x not in DROP_WORDS]


def ticker_map(cusip_names, h):
    """CUSIP -> Ticker: feste Zuordnung, sonst bester Treffer der ersten Namenswoerter in der SEC-Tickerliste."""
    sec = _get("https://www.sec.gov/files/company_tickers.json", h).json().values()
    cands = [(v["ticker"].upper(), _norm(v["title"])) for v in sec]
    out, unmatched = {}, []
    for cusip, name in cusip_names.items():
        if cusip in FIXED:
            out[cusip] = FIXED[cusip]
            continue
        words = _norm(name)
        best, score = None, 0
        for tic, tw in cands:
            if not tw or not words:
                continue
            k, m = 0, 0.0
            while k < min(len(tw), len(words)) and (tw[k] == words[k] or tw[k].startswith(words[k]) or words[k].startswith(tw[k])):
                m += 1.0 if tw[k] == words[k] else 0.5             # exakte Woerter zaehlen mehr als Wortanfaenge
                k += 1
            s = (m / max(len(words), 1) - 0.02 * max(0, len(tw) - len(words))
                 + (0.01 if "-" not in tic and "." not in tic else 0))
            if k and s > score:
                best, score = tic, s
        if best and score >= 0.5:
            out[cusip] = best
        else:
            unmatched.append(f"{cusip} {name}")
    return out, unmatched


def has_prices(ticker):
    """True, wenn Yahoo eine Kurshistorie liefert (die App braucht sie fuer Buchungskurse und Depotwert)."""
    try:
        import yfinance as yf
        return not yf.Ticker(ticker).history(period="max")["Close"].dropna().empty
    except Exception:
        return False


def close_prices(tickers, start):
    """Splitbereinigte Schlusskurse (Yahoo, ohne Dividendenbereinigung) ab kurz vor dem ersten Stichtag."""
    import yfinance as yf
    s0 = (pd.Timestamp(start) - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    df = yf.download(tickers, start=s0, progress=False, auto_adjust=False, threads=True)["Close"]
    if not hasattr(df, "columns"):
        df = df.to_frame(tickers[0])
    df.index = df.index.tz_localize(None) if getattr(df.index, "tz", None) is not None else df.index
    return df


def split_factor(ticker, cache):
    """Funktion datum -> Produkt aller Splits NACH diesem Datum (Yahoo)."""
    if ticker not in cache:
        try:
            import yfinance as yf
            sp = yf.Ticker(ticker).splits
            sp.index = sp.index.tz_localize(None) if getattr(sp.index, "tz", None) is not None else sp.index
            cache[ticker] = sp[sp > 0]
        except Exception:
            cache[ticker] = pd.Series(dtype=float)
    sp = cache[ticker]
    return lambda d: float(sp[sp.index > pd.Timestamp(d)].prod()) if len(sp) else 1.0


def build(cik, name, start_value, min_change=0.001, out_dir=None):
    h = _headers()
    fs = filings(cik, h)
    if not fs:
        raise SystemExit("keine 13F-HR gefunden")
    print(f"{len(fs)} Quartale: {fs[0]['period']} bis {fs[-1]['period']}")
    periods, names = [], {}
    for i, f in enumerate(fs, 1):
        print(f"  Meldung {i}/{len(fs)}: Quartal {f['period']}", flush=True)
        rows = infotable(cik, f["acc"], h)
        agg = {}
        for r in rows:
            a = agg.setdefault(r["cusip"], {"shares": 0.0, "value": 0.0})
            a["shares"] += r["shares"]
            a["value"] += r["value"]
            names.setdefault(r["cusip"], r["name"])
        # Werte bis Ende 2022 in Tausend USD, danach in USD
        unit = 1000.0 if f["period"] < "2023-01-01" else 1.0
        periods.append({**f, "pos": agg, "total": sum(a["value"] for a in agg.values()) * unit})
        time.sleep(0.15)                                   # SEC: hoechstens 10 Abrufe je Sekunde
    tmap, unmatched = ticker_map(names, h)
    if unmatched:
        print("Ohne Ticker (uebersprungen): " + "; ".join(unmatched))
    print(f"Pruefe Yahoo-Kurse fuer {len(set(tmap.values()))} Ticker ...", flush=True)
    no_prices = sorted(t for t in set(tmap.values()) if not has_prices(t))
    if no_prices:                                          # z. B. nach Uebernahme delistet: die App bewertet sie sonst mit 0
        print("Ohne Yahoo-Kurse (uebersprungen): " + ", ".join(no_prices))
        tmap = {c: t for c, t in tmap.items() if t not in no_prices}
    sp_cache = {}
    # Fonds-Stueckzahlen je Quartal in heutigen (splitbereinigten) Einheiten
    fund = []
    for p in periods:
        cur = {}
        for cusip, a in p["pos"].items():
            t = tmap.get(cusip)
            if t:
                cur[t] = cur.get(t, 0.0) + a["shares"] * split_factor(t, sp_cache)(p["period"])
        fund.append({t: v for t, v in cur.items() if v > 0})
    tickers = sorted({t for f in fund for t in f})
    print(f"Lade Kurse fuer {len(tickers)} Ticker ...", flush=True)
    px = close_prices(tickers, periods[0]["period"])

    def price(t, d):
        s_ = px[t].loc[:pd.Timestamp(d)].dropna() if t in px else None
        return float(s_.iloc[-1]) if s_ is not None and len(s_) else None

    def simulate(date_key):
        """Selbstfinanziertes Depot: an jedem Stichtag dieselben Gewichte wie der Fonds, aber nur mit dem eigenen
        Depotwert (keine Zufluesse wie beim Fonds). Kaeufe werden aus Verkaeufen bezahlt."""
        rows, hold, values = [], {}, []
        for p, f in zip(periods, fund):
            d = p[date_key]
            fv = sum(sh * (price(t, d) or 0) for t, sh in f.items())
            if fv <= 0:
                continue
            v = start_value if not hold else sum(sh * (price(t, d) or 0) for t, sh in hold.items())
            target = {t: sh * v / fv for t, sh in f.items() if price(t, d)}
            for t in sorted(set(hold) | set(target)):
                delta = target.get(t, 0.0) - hold.get(t, 0.0)
                base = max(hold.get(t, 0.0), target.get(t, 0.0))
                if base <= 0 or abs(delta) < min_change * base:
                    target[t] = hold.get(t, 0.0) if t in hold else target.get(t, 0.0)
                    continue
                sh = abs(delta) / split_factor(t, sp_cache)(d)        # Einheiten am Buchungstag
                rows.append({"date": d, "type": "buy" if delta > 0 else "sell", "ticker": t,
                             "shares": round(sh, 4), "price": "", "currency": "EUR", "fees": 0, "amount": ""})
            hold = {t: x for t, x in target.items() if x > 1e-9}
            values.append((d, v))
        return rows, hold, values

    rows_q, adj, values_q = simulate("period")
    rows_f, _, values_f = simulate("filed")
    last_v = sum(sh * (price(t, pd.Timestamp.today()) or 0) for t, sh in adj.items())
    print(f"Depotwert (Variante Quartalsende, in USD-Kursen): Start {start_value:,.0f}, heute ca. {last_v:,.0f}", flush=True)
    out_dir = Path(out_dir or AIF / "portfolios")
    for suffix, rows in (("quarter", rows_q), ("filed", rows_f)):
        p = out_dir / f"{name}_{suffix}.csv"
        pd.DataFrame(rows, columns=["date", "type", "ticker", "shares", "price", "currency", "fees", "amount"]).to_csv(
            p, index=False)
        print(f"{p.name}: {len(rows)} Buchungen")
    last = periods[-1]
    summary = {"cik": cik, "quarters": len(periods), "first": periods[0]["period"], "last": last["period"],
               "last_filed": last["filed"], "start_value": start_value, "value_today_usd": round(last_v), "unmatched": unmatched, "no_prices": no_prices,
               "mapping": {c: [names[c], tmap.get(c)] for c in names}, "final_positions": {t: round(v, 2) for t, v in sorted(adj.items())},
               "created": time.strftime("%Y-%m-%d %H:%M")}
    json.dump(summary, open(out_dir / f"{name}_summary.json", "w", encoding="utf-8"), indent=2)
    print(json.dumps({k_: v for k_, v in summary.items() if k_ not in ("final_positions", "mapping")}, indent=1))
    print("Zuordnung CUSIP -> Ticker:", {v[0]: v[1] for v in summary["mapping"].values()})
    print("Endbestand (heutige Stueckzahlen):", summary["final_positions"])
    return summary


class _Tee:
    """Ausgabe gleichzeitig ins Fenster und in eine Datei (die .bat zeigt so den Fortschritt)."""
    def __init__(self, path):
        self.f, self.out = open(path, "w", encoding="utf-8"), sys.stdout

    def write(self, s):
        self.out.write(s)
        self.f.write(s)
        self.f.flush()

    def flush(self):
        self.out.flush()


if __name__ == "__main__":
    sys.stdout = _Tee(AIF / "eval" / "build_13f_portfolio.txt")
    ap = argparse.ArgumentParser()
    ap.add_argument("--cik", default="1697868")
    ap.add_argument("--name", default="sample_transactions_vfc")
    ap.add_argument("--start-value", type=float, default=100_000)
    a = ap.parse_args()
    build(a.cik, a.name, a.start_value)
