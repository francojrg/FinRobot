"""
Transaktionen einlesen (eigene Erweiterung): Broker-CSV-Exporte -> einheitliches Format.

Unterstuetzt:
- Scalable Capital (Broker -> Transaktionen -> Export; Kopfzeile date;time;status;reference;description;assetType;
  type;isin;shares;price;amount;fee;tax;currency)
- Trade Republic (Transaktionsexport seit April 2026; Spalten u. a. datetime, date, account_type, category, type,
  asset_class, name, symbol, shares, price, amount, fee, tax, currency, ...)
- Smartbroker+ und andere: Erkennung ueber deutsche/englische Spaltennamen (Datum, Typ/Art, ISIN, Stueck, Kurs,
  Betrag, Gebuehr, Steuer, Waehrung ...)
- Eigene Vorlage: date,type,ticker,shares,price,currency,fees (siehe portfolios/sample_transactions.csv)

Die Broker-Formate aendern sich gelegentlich. Unbekannte Spalten oder Buchungstypen werden nicht geraten,
sondern in "issues" gemeldet, damit man die Zuordnung pruefen kann.

ISIN -> Yahoo-Ticker: Suche ueber yfinance (bevorzugt Xetra/Frankfurt in EUR), Ergebnis in portfolios/isin_map.csv
gespeichert; diese Datei kann man von Hand korrigieren (Spalten isin,ticker).
"""
import csv
import io
import re
from pathlib import Path

import pandas as pd

AIF = Path(__file__).resolve().parents[1]
ISIN_MAP = AIF / "portfolios" / "isin_map.csv"

# Spaltennamen (kleingeschrieben, ohne Sonderzeichen) -> Feld
SYNONYMS = {
    "date": ["date", "handelsdatum", "handelstag", "tradedate", "transactiondate", "schlusstag", "buchungstag",
             "buchungsdatum", "ausfuehrungsdatum", "valutadatum", "valuta", "datum", "datetime"],
    "date2": ["valutadatum", "valuta", "buchungsdatum"],
    "type": ["type", "typ", "art", "transaktionsart", "transaktionstyp", "buchungsart", "umsatzart", "transactiontype",
             "category"],
    "isin": ["isin", "symbol", "wertpapierkennnummer"],
    "ticker": ["ticker", "tickersymbol"],
    "name": ["name", "name1", "description", "bezeichnung", "wertpapier", "wertpapiername", "titel", "securityname"],
    "shares": ["shares", "stueck", "stuecke", "stuck", "stucke", "anzahl", "menge", "nominale", "quantity", "units",
               "stueckzahl"],
    "price": ["price", "kurs", "preis", "ausfuehrungskurs", "quote", "kursproeinheit"],
    "amount": ["amount", "gesamtbetraginkontowaehrung", "betrag", "wert", "gesamtbetrag", "kurswert", "endbetrag",
               "nettobetrag", "total", "anlagebetraginkontowaehrung"],
    "fee": ["fee", "fees", "gebuehr", "gebuehren", "gebuehreninkontowaehrung", "provision", "entgelt", "kosten",
            "ordergebuehr"],
    "tax": ["tax", "taxes", "steuer", "steuern", "steuerninkontowaehrung", "kapitalertragsteuer", "quellensteuer"],
    "currency": ["currency", "kontowaehrung", "waehrung", "wahrung", "devise"],
    "status": ["status", "statusdertransaktion", "orderstatus"],
    "asset": ["assettype", "assetclass", "asset_class", "assetklasse", "gattung"],
}

# Buchungstyp-Erkennung ueber Stichworte (Reihenfolge wichtig: spezifisch vor allgemein)
TYPE_RULES = [
    ("sell", ["sell", "verkauf", "sale", "veraeusserung"]),
    ("buy", ["buy", "kauf", "purchase", "savings plan", "savingsplan", "sparplan", "saveback", "roundup",
             "round up", "investment"]),
    ("dividend", ["dividend", "dividende", "ausschuettung", "distribution", "ertrag", "coupon"]),
    ("interest", ["interest", "zinsen", "zins"]),
    ("deposit", ["deposit", "einzahlung", "einlage", "transfer in", "transferin", "gutschrift", "sepa credit",
                 "incoming", "inbound", "eingang"]),
    ("withdrawal", ["withdrawal", "auszahlung", "entnahme", "transfer out", "transferout", "outgoing", "outbound",
                    "ausgang", "card", "karte", "lastschrift", "direct debit"]),
    ("fee", ["fee", "gebuehr", "entgelt", "kosten"]),
    ("tax", ["tax", "steuer"]),
]
SKIP_WORDS = ["cancel", "storn", "rejected", "abgelehnt", "pending", "split"]

# Exakte Buchungstypen (Trade Republic u. a.), haben Vorrang vor den Stichworten.
# transfer_in/out = Stueck ohne Zahlung (Spin-off, Gratisaktien, Fusion); income = Ertrag ohne Wertpapierbewegung
EXACT_TYPES = {
    "CUSTOMER_INPAYMENT": "deposit", "REDEMPTION": "sell", "UNBUNDLING": "transfer_in",
    "UNBUNDLING_CANCELLED": "transfer_out", "CAPITAL_INCR_CASH": "transfer_in", "STOCK_DIVIDEND": "transfer_in",
    "STOCK_DIVIDEND_CANCELLED": "transfer_out", "MERGER": "transfer_out", "EXCHANGE": "income",
    "COMPENSATION": "income", "STOCKPERK": "income", "REFERRAL": "income", "SEC_ACCOUNT": None, "SPLIT": None,
    "REVERSE_SPLIT": None,
    # Scalable Capital
    "SECURITY TRANSFER": "deliver", "CORPORATE ACTION": "corporate",
    # Smartbroker+ (Aktivitaeten-Export)
    "ENTERINTOSECACCOUNT": "deliver_in", "LEAVESECACCOUNT": "deliver_out", "EXITSECACCOUNT": "deliver_out",
    "REMOVEFROMSECACCOUNT": "deliver_out",
}
CRYPTO_NAMES = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "cardano": "ADA", "xrp": "XRP", "ripple": "XRP",
                "litecoin": "LTC", "polkadot": "DOT", "dogecoin": "DOGE", "chainlink": "LINK", "avalanche": "AVAX",
                "polygon": "MATIC", "tron": "TRX", "bitcoin cash": "BCH", "stellar": "XLM"}


def _norm(s):
    s = str(s or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9_]", "", s)


def _num(x, de=None):
    """Zahl aus deutschem oder englischem Format ('1.234,56', '1,234.56', '-12.5 EUR').
    de=True: deutsches Format erzwingen ('3.012' = 3012), sonst wird geraten."""
    if x is None:
        return None
    s = str(x).strip().replace("\xa0", "").replace(" ", "")
    s = re.sub(r"[A-Za-z€$%]", "", s)
    if not s or s in ("-", "--"):
        return None
    if de:
        try:
            return float(s.replace(".", "").replace(",", "."))
        except ValueError:
            return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _read_table(path):
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = text.splitlines()[0] if text else ""
    delim = max([";", ",", "\t", "|"], key=first.count)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    return rows[0], rows[1:]


def _german_numbers(rows, cols):
    """Deutsches Zahlenformat, wenn Werte mit Dezimalkomma vorkommen (z. B. '12,5' oder '1.053,49')."""
    idx = [cols[f] for f in ("shares", "price", "amount", "fee", "tax") if f in cols]
    pat = re.compile(r"^-?[\d.]*\d,\d+$")
    return any(pat.match(r[i].strip()) for r in rows[:500] for i in idx if i < len(r))


def _detect(header):
    h = [_norm(c) for c in header]
    if {"date", "time", "status", "reference", "assettype", "type", "isin", "shares", "price", "amount"} <= set(h):
        return "scalable"
    if {"datetime", "account_type", "category", "type", "symbol", "shares", "amount"} <= set(h) or \
       {"datetime", "accounttype", "category", "type", "symbol", "shares", "amount"} <= set(h):
        return "traderepublic"
    if {"date", "type", "ticker", "shares", "price"} <= set(h):
        return "template"
    return "generic"


def _map_columns(header):
    h = [_norm(c) for c in header]
    cols = {}
    for field, names in SYNONYMS.items():
        for n in names:
            if n in h and field not in cols:
                cols[field] = h.index(n)
    return cols


def _classify(*texts):
    raw = str(texts[0] or "").strip().upper() if texts else ""
    if raw in EXACT_TYPES:
        return EXACT_TYPES[raw]
    t = " ".join(str(x or "").lower() for x in texts).replace("_", " ").replace("-", " ")
    t_n = _norm(t)
    if any(w in t for w in SKIP_WORDS):
        return None
    for typ, words in TYPE_RULES:
        if any(w in t or _norm(w) in t_n for w in words):
            return typ
    return "unknown"


def _parse_date(s):
    s = str(s or "").strip()
    for fmt in (None, "%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            d = pd.to_datetime(s, format=fmt, dayfirst=fmt is None and "." in s, utc=True if fmt is None else False)
            return pd.Timestamp(d).tz_localize(None).normalize() if getattr(d, "tzinfo", None) else pd.Timestamp(d).normalize()
        except Exception:
            continue
    return None


def read_transactions(path, broker="auto"):
    """Liest eine CSV und liefert (DataFrame im Einheitsformat, issues)."""
    header, rows = _read_table(path)
    kind = _detect(header) if broker == "auto" else broker
    cols = _map_columns(header)
    issues = []
    hn = {_norm(c) for c in header}
    if "type" not in cols and ({"marktwert", "einstandswert", "einstandskursprostueck"} & hn
                               or {"marketvalue", "costbasis"} & hn):
        return pd.DataFrame(), [f"{Path(path).name}: this is a holdings snapshot (positions with market value), not a "
                                f"transaction history - export the activities/transactions instead "
                                f"(Smartbroker+: Depot > Exportieren > Aktivitaeten > Als CSV exportieren, Gesamter Zeitraum)"]
    if "date" not in cols:
        return pd.DataFrame(), [f"{Path(path).name}: no date column found (header: {header})"]
    out = []
    de = _german_numbers(rows, cols)
    num = lambda v: _num(v, de=de)
    for i, r in enumerate(rows, start=2):
        g = lambda f: r[cols[f]].strip() if f in cols and cols[f] < len(r) else ""
        if kind == "scalable" and g("status").lower() not in ("", "executed", "ausgefuehrt", "ausgeführt", "settled"):
            continue
        if any(w in g("status").lower() for w in ("cancel", "storn", "reject", "abgelehnt", "fail")):
            continue
        typ = _classify(g("type"), g("name") if kind == "generic" else "")
        if typ is None:
            continue
        shares, price = num(g("shares")), num(g("price"))
        amount, fee, tax = num(g("amount")), num(g("fee")), num(g("tax"))
        sym = g("isin").upper()
        isin = sym if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", sym) else ""
        crypto = ""
        if "crypto" in g("asset").lower() or "krypto" in g("asset").lower():
            base = sym if re.fullmatch(r"[A-Z0-9]{2,6}", sym) and not isin else CRYPTO_NAMES.get(g("name").lower().strip())
            crypto, isin = (f"{base}-EUR", "") if base else ("", isin)
        rec = {"date": _parse_date(g("date") or g("date2")), "type": typ, "isin": isin, "ticker": g("ticker").upper() or crypto,
               "name": g("name"), "shares": abs(shares) if shares else None, "price": abs(price) if price else None,
               "amount": abs(amount) if amount is not None else None, "fee": abs(fee) if fee else 0.0,
               "tax": tax or 0.0, "currency": (g("currency") or "EUR").upper(), "source": Path(path).name,
               "broker": kind, "row": i, "raw_type": g("type")}
        if rec["date"] is None:
            issues.append(f"{rec['source']} row {i}: date not readable ({g('date')})")
            continue
        if typ == "unknown":
            issues.append(f"{rec['source']} row {i}: unknown type '{g('type')}' - skipped")
            continue
        if typ in ("deposit", "withdrawal") and amount:   # Vorzeichen des Exports hat Vorrang
            typ = rec["type"] = "deposit" if amount > 0 else "withdrawal"
        if typ in ("deliver", "corporate"):             # Richtung aus dem Vorzeichen der Stueckzahl
            if not shares:
                continue
            typ = rec["type"] = ("deliver_in" if shares > 0 else "deliver_out") if typ == "deliver" else \
                ("transfer_in" if shares > 0 else "transfer_out")
        if typ == "tax" and amount and amount > 0:     # Steuererstattung
            typ = rec["type"] = "income"
        if typ in ("transfer_in", "transfer_out", "deliver_in", "deliver_out") and \
                not (rec["shares"] and (rec["isin"] or rec["ticker"])):
            continue
        if typ in ("buy", "sell") and not (rec["isin"] or rec["ticker"]):
            issues.append(f"{rec['source']} row {i}: {typ} without ISIN/ticker - skipped")
            continue
        if typ in ("buy", "sell") and not rec["shares"]:
            issues.append(f"{rec['source']} row {i}: {typ} without number of shares - skipped")
            continue
        if typ in ("buy", "sell") and rec["price"] is None and rec["amount"]:
            rec["price"] = rec["amount"] / rec["shares"]
        if typ in ("buy", "sell") and rec["amount"] is None and rec["price"]:
            rec["amount"] = rec["price"] * rec["shares"]
        out.append(rec)
    df = pd.DataFrame(out)
    if not df.empty:
        df = df.sort_values(["date", "row"]).reset_index(drop=True)
    return df, issues


def compact(tx):
    """Buchungsliste fuer die App (Transaktionen-Tab): eine Zeile je Buchung, ohne Quelldatei und Zeilennummer."""
    if tx is None or tx.empty:
        return []
    out = []
    for _, r in tx.sort_values(["date"], ascending=False).iterrows():
        f = lambda k: (None if pd.isna(r.get(k)) else float(r.get(k))) if r.get(k) is not None else None
        out.append({"date": str(pd.Timestamp(r["date"]).date()), "type": r["type"], "ticker": (r.get("ticker") or "") or "",
                    "name": r.get("name") or "", "shares": f("shares"), "price": f("price"), "amount": f("amount"),
                    "fee": f("fee") or 0.0, "tax": f("tax") or 0.0, "currency": r.get("currency") or "EUR"})
    return out


def read_all(paths):
    frames, issues = [], []
    for p in paths:
        df, iss = read_transactions(p)
        frames.append(df)
        issues += iss
    frames = [f for f in frames if not f.empty]
    df = pd.concat(frames, ignore_index=True).sort_values("date").reset_index(drop=True) if frames else pd.DataFrame()
    return df, issues


# --------------------------------------------------------------- ISIN -> Ticker
def _load_map():
    if not ISIN_MAP.exists():
        return {}
    return {r["isin"].strip().upper(): r["ticker"].strip().upper()
            for r in csv.DictReader(open(ISIN_MAP, encoding="utf-8")) if r.get("isin") and r.get("ticker")
            and not _ISIN_SYM.match(r["ticker"].strip().upper())}


def _save_map(m):
    ISIN_MAP.parent.mkdir(parents=True, exist_ok=True)
    with open(ISIN_MAP, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["isin", "ticker"])
        for k in sorted(m):
            w.writerow([k, m[k]])


_ISIN_SYM = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}\d(\.|$)")
_PREF = (".DE", ".F", ".MI", ".AS", ".PA", ".VI", ".SW", ".L")     # EUR-Boersen zuerst, dann Schweiz/London


def _has_data(sym):
    import yfinance as yf
    try:
        h = yf.Ticker(sym).history(period="1mo", auto_adjust=False)
        return h is not None and not h["Close"].dropna().empty
    except Exception:
        return False


def _search(q):
    """Bester Yahoo-Ticker fuer eine ISIN oder einen Namen: nur Symbole mit Kursdaten, EUR-Boersen bevorzugt."""
    import yfinance as yf
    try:
        quotes = yf.Search(q, max_results=10).quotes
    except Exception:
        return None
    syms = [x.get("symbol", "") for x in quotes if x.get("symbol") and x.get("quoteType") in (None, "EQUITY", "ETF",
                                                                                              "MUTUALFUND", "CRYPTOCURRENCY")]
    syms = [x for x in syms if not _ISIN_SYM.match(x)]            # z. B. 'GB00BLD4ZM24.SG' hat keine Kurse
    if re.fullmatch(r"US[A-Z0-9]{9}\d", q.strip().upper()):
        # US-Wertpapier: das US-Symbol zuerst (die Research-Agenten brauchen es fuer SEC-Filings; die App rechnet
        # Kurse ohnehin in EUR um), danach die EUR-Boersen
        ranked = sorted(syms, key=lambda x: 0 if "." not in x else 1 + next(
            (i for i, sfx in enumerate(_PREF) if x.endswith(sfx)), len(_PREF)))
    else:
        ranked = sorted(syms, key=lambda x: next((i for i, sfx in enumerate(_PREF) if x.endswith(sfx)), len(_PREF)))
    for sym in ranked[:5]:
        if _has_data(sym):
            return sym
    return None


# Hebelprodukte (Turbos, Optionsscheine, Zertifikate) haben bei Yahoo keine Kurse; eine Suche ueber den Namen fuehrt
# sonst auf ein falsches Papier (z. B. 'Turbo Long Gold' -> dreifach gehebelter Gold-ETC). In der isin_map steht fuer
# solche ISINs NONE: bewusst ohne Kurs (Zahlungen zaehlen, der Bestand wird nicht bewertet).
_DERIV_NAME = re.compile(r"(?i)\b(turbo|mini[ -]?(long|short|future)|knock|optionsschein|warrant|call|put|zertifikat|"
                         r"certificate|faktor|factor|hebel|leverage|bull|bear|open[ -]?end|endlos|discount|bonus|express|"
                         r"capped|unlimited|sprinter|inline)\b")
NO_PRICE = "NONE"


def resolve_isins(isins, names=None):
    """ISIN -> Yahoo-Ticker; bevorzugt Xetra (.DE), dann Frankfurt (.F), dann andere Boersen; notfalls Suche per Name
    (Treffer per Name immer pruefen - die Kurs-Plausibilitaetspruefung meldet falsche Zuordnungen)."""
    m = _load_map()
    missing = [i for i in sorted(set(isins)) if i and i not in m]
    unresolved = []
    for isin in missing:
        if names and _DERIV_NAME.search(names.get(isin) or ""):
            m[isin] = NO_PRICE                       # Hebelprodukt: nicht per Namen raten
            unresolved.append(isin)
            continue
        pick = _search(isin)
        if not pick and names and names.get(isin):
            pick = _search(re.sub(r"\b(inc|corp|plc|ag|se|sa|nv|ltd|registered|shares?|adr|class [a-c])\b\.?", "",
                                  names[isin], flags=re.I).strip())
        if pick:
            m[isin] = pick.upper()
        else:
            unresolved.append(isin)
    if missing:
        _save_map(m)
    return m, unresolved


def attach_tickers(df):
    """Ergaenzt fehlende Ticker ueber die ISIN; gibt (df, nicht aufloesbare ISINs) zurueck."""
    if df.empty:
        return df, []
    need = df.loc[(df["ticker"] == "") & (df["isin"] != ""), "isin"].unique().tolist()
    names = df.loc[df["isin"].isin(need)].groupby("isin")["name"].last().to_dict() if need else {}
    m, unresolved = resolve_isins(need, names) if need else (_load_map(), [])
    df = df.copy()
    df.loc[df["ticker"] == "", "ticker"] = df.loc[df["ticker"] == "", "isin"].map(m).fillna("")
    df.loc[df["ticker"] == NO_PRICE, "ticker"] = ""
    unresolved = sorted(set(unresolved) | {i for i in need if m.get(i) == NO_PRICE})
    return df, unresolved


# --------------------------------------------------------------- Depotpositionen (Momentaufnahme ohne Kaufhistorie)
def read_holdings(path):
    """Positions-Export eines Brokers (z. B. Smartbroker+ 'Depotpositionen'): ISIN/Kuerzel, Stueck, Einstands- und
    Marktwert. Liefert (Liste {ticker, isin, name, shares, cost, value, currency, source}, issues). Kundendaten
    (Kunden-/Depotnummer) werden nicht uebernommen."""
    header, rows = _read_table(path)
    h = [_norm(c) for c in header]
    if "type" in _map_columns(header):
        return [], [f"{Path(path).name}: this is a transaction history, not a holdings snapshot - "
                    f"put it into TRANSACTION_FILES instead of HOLDINGS_FILES"]

    def col(*names):
        return next((h.index(n) for n in names if n in h), None)
    ci, ck, cn = col("isin"), col("kuerzel", "kurzel", "symbol", "ticker"), col("name1", "name", "bezeichnung")
    cs, cc = col("stuecke", "stucke", "stueck", "anzahl", "shares", "quantity"), col("einstandswert", "costbasis")
    cv, ca, cw = col("marktwert", "marketvalue"), col("assetklasse", "assetclass"), col("waehrung", "wahrung", "currency")
    issues, out = [], []
    pat = re.compile(r"^-?[\d.]*\d,\d+$")
    de = any(pat.match(r[c].strip()) for r in rows[:500] for c in (cs, cc, cv) if c is not None and c < len(r))
    _n = lambda v: _num(v, de=de)
    if cs is None or (ci is None and ck is None):
        return [], [f"{Path(path).name}: no shares/ISIN columns found - not a holdings export?"]
    for r in rows:
        g = lambda c: r[c].strip() if c is not None and c < len(r) else ""
        sh = _n(g(cs))
        if not sh:
            continue
        isin, sym, asset = g(ci).upper(), g(ck).upper(), g(ca).lower()
        ticker = ""
        if "krypto" in asset or "crypto" in asset:
            base = sym if re.fullmatch(r"[A-Z0-9]{2,6}", sym) else CRYPTO_NAMES.get(g(cn).lower().strip())
            ticker = f"{base}-EUR" if base else ""
            isin = ""
        out.append({"ticker": ticker, "isin": isin if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", isin) else "",
                    "name": g(cn), "shares": abs(sh), "cost": _n(g(cc)), "value": _n(g(cv)),
                    "currency": (g(cw) or "EUR").upper(), "source": Path(path).name})
    need = [x["isin"] for x in out if not x["ticker"] and x["isin"]]
    if need:
        m, unresolved = resolve_isins(need, {x["isin"]: x["name"] for x in out if x["isin"]})
        for x in out:
            if not x["ticker"] and x["isin"]:
                x["ticker"] = m.get(x["isin"], "")
        if unresolved:
            issues.append(f"{Path(path).name}: ISINs without Yahoo ticker (add to portfolios/isin_map.csv): "
                          f"{', '.join(unresolved)}")
    return [x for x in out if x["ticker"]], issues


def read_all_holdings(paths):
    out, issues = [], []
    for p in paths or []:
        h, iss = read_holdings(p)
        out += h
        issues += iss
    return out, issues


def merge_positions(*lists):
    """Positionen (ticker + shares) zusammenfassen; gleiche Ticker werden addiert."""
    tot = {}
    for lst in lists:
        for x in lst or []:
            tot[x["ticker"]] = tot.get(x["ticker"], 0.0) + float(x["shares"])
    return [{"ticker": t, "shares": q} for t, q in tot.items() if q > 1e-9]

