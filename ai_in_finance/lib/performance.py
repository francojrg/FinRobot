"""
Tatsaechliche Performance aus Transaktionen (eigene Erweiterung) - deterministisch, in EUR.

- Rekonstruktion: Bestand je Titel und Tag, Cash (falls Ein-/Auszahlungen im Export), Depotwert.
- TTWROR (True Time-Weighted Rate of Return): taeglich verkettet, externe Zahlungen herausgerechnet
  -> Qualitaet der Anlageentscheidungen, direkt mit einem Index vergleichbar.
- MWR / IRR (geldgewichtet, XIRR): was das eingesetzte Geld tatsaechlich verdient hat (inkl. Timing).
- Benchmark mit denselben Zahlungsstroemen: jede Einzahlung am selben Tag in den MSCI ACWI (EUR).
- Positionen: investiert, Verkaufserloese, Dividenden, Gebuehren, realisierter/unrealisierter Gewinn
  (Durchschnittskostenmethode), IRR je Position.
- Entscheidungen: jeder Kauf/Verkauf vs. MSCI ACWI seit dem Trade; Gegenszenario "keine Trades" (Startdepot halten).

Zwei Modi: Enthaelt der Export Ein-/Auszahlungen, wird ein Cash-Konto gefuehrt (externe Zahlungen = Ein-/Auszahlungen).
Sonst gilt jeder Kauf als Zufluss und jeder Verkauf/jede Dividende als Abfluss (nur Wertpapiere).
"""
import math

import numpy as np
import pandas as pd

from . import portfolio_engine as pe

BENCH = pe.BENCHMARKS["MSCI ACWI"]


def _eur(amount, currency, date, fx):
    if amount is None:
        return 0.0
    if currency in ("EUR", "", None):
        return float(amount)
    s = fx.get(currency)
    if s is None:
        return float(amount)
    rate = s.asof(date) if hasattr(s, "asof") else None
    return float(amount) / float(rate) if rate and rate == rate else float(amount)


def _xirr(flows):
    """flows: Liste (datum, betrag) aus Anlegersicht (Einzahlung negativ, Endwert positiv)."""
    flows = [(pd.Timestamp(d), float(a)) for d, a in flows if a]
    if len(flows) < 2 or all(a >= 0 for _, a in flows) or all(a <= 0 for _, a in flows):
        return None
    t0 = min(d for d, _ in flows)

    def npv(r):
        return sum(a / (1 + r) ** ((d - t0).days / 365.25) for d, a in flows)
    lo, hi = -0.99, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if npv(lo) * npv(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def _ttw_curve(value, flows, first):
    """TTWROR-Kurve, Zahlungen zum Tagesende: r_t = (V_t - CF_t) / V_{t-1} - 1."""
    prev = value.shift(1).fillna(0.0)
    r = pd.Series(np.where(prev > 1e-6, (value - flows) / prev.where(prev > 1e-6, 1.0) - 1, 0.0), index=value.index)
    return (1 + r.loc[first:].clip(-0.9, 3)).cumprod()


def _period_row(label, s, value, ext, curve, bcurve, end, annualize):
    """Kennzahlen fuer einen Zeitraum ab Handelstag s (Bewertung am Vortag als Start)."""
    idx = curve.index
    if s <= idx[0]:
        c0, b0, v0, start = 1.0, 1.0, 0.0, idx[0]
        flows_in = ext.loc[idx[0]:end]
    else:
        pos = idx.searchsorted(s)
        if pos >= len(idx):
            return None
        d_prev = idx[pos - 1]
        c0, b0, v0, start = float(curve.loc[d_prev]), float(bcurve.loc[d_prev]), float(value.loc[d_prev]), idx[pos]
        flows_in = ext.loc[idx[pos]:end]
    tw = float(curve.loc[end] / c0 - 1)
    bw = float(bcurve.loc[end] / b0 - 1)
    yrs = max((end - (start if v0 == 0 else idx[max(idx.searchsorted(start) - 1, 0)])).days / 365.25, 1 / 365)
    if annualize and yrs > 1.0:
        tw, bw = (1 + tw) ** (1 / yrs) - 1, (1 + bw) ** (1 / yrs) - 1
    flows = ([(start - pd.Timedelta(days=1), -v0)] if v0 > 0 else []) + \
        [(d, -a) for d, a in flows_in.items() if abs(a) > 1e-9] + [(end, float(value.loc[end]))]
    mwr = _xirr(flows)
    if mwr is not None and not (annualize and yrs > 1.0):
        mwr = (1 + mwr) ** min(yrs, 1.0) - 1            # bis 1 Jahr: nicht annualisiert (vergleichbar mit TTWROR)
    pl = float(value.loc[end] - v0 - flows_in.sum())
    return {"period": label, "start": str(start.date()), "ttwror": tw, "bench": bw, "diff": tw - bw, "mwr": mwr,
            "pl_eur": pl, "annualized": bool(annualize and yrs > 1.0)}


def _fx_series(currencies, start):
    import yfinance as yf
    fx = {}
    for c in sorted({c for c in currencies if c and c != "EUR"}):
        base = "GBP" if c in ("GBP", "GBX", "GBp") else c
        s = yf.download(f"EUR{base}=X", start=start, auto_adjust=True, progress=False)["Close"].squeeze()
        fx[c] = s.dropna()
    return fx


def load_market_data(tickers, start):
    """Kurse in EUR ab start: 'close' (nur splitbereinigt, fuer Depotwerte - Dividenden kommen als Buchung),
    'total' (dividendenbereinigt, fuer Entscheidungsvergleich und Benchmark), dazu Splits und FX."""
    import yfinance as yf
    tickers = list(dict.fromkeys(list(tickers) + [BENCH]))
    raw = yf.download(tickers, start=start, auto_adjust=False, actions=True, progress=False)
    curr = {t: pe._currency(t) for t in tickers}
    fx = _fx_series([c for c in curr.values()] + ["USD"], start)
    close, total = pd.DataFrame(index=raw.index), pd.DataFrame(index=raw.index)
    splits = {}
    for t in tickers:
        c = curr.get(t, "EUR")
        conv = 1.0
        if c in fx:
            conv = fx[c].reindex(raw.index).ffill() * (100.0 if c in ("GBp", "GBX") else 1.0)
        close[t] = raw["Close"][t].astype(float) / conv
        total[t] = raw["Adj Close"][t].astype(float) / conv
        if "Stock Splits" in raw:
            sp = raw["Stock Splits"][t]
            sp = sp[sp > 0]
            if len(sp):
                splits[t] = sp
    return {"close": close.ffill(), "total": total.ffill(), "splits": splits, "fx": fx, "currency": curr}


def _apply_splits(tx, splits):
    """Kauf/Verkauf vor einem Split auf heutige Stueckzahl umrechnen (Yahoo-Kurse sind splitbereinigt)."""
    tx = tx.copy()
    for t, sp in (splits or {}).items():
        for d, ratio in sp.items():
            m = (tx["ticker"] == t) & (tx["date"] < pd.Timestamp(d).tz_localize(None)) & \
                tx["type"].isin(["buy", "sell", "deliver_in", "deliver_out", "transfer_in", "transfer_out"])
            tx.loc[m, "shares"] = tx.loc[m, "shares"] * float(ratio)
            tx.loc[m, "price"] = tx.loc[m, "price"] / float(ratio)
    return tx


def analyze_transactions(tx, market=None):
    """tx: Einheitsformat aus transactions.read_all (mit Spalte ticker).
    market: Ergebnis von load_market_data (fuer Offline-Tests direkt uebergeben)."""
    tx = tx.copy()
    tx = tx[tx["type"].isin(["buy", "sell", "dividend", "deposit", "withdrawal", "fee", "tax", "interest", "income",
                             "transfer_in", "transfer_out", "deliver_in", "deliver_out"])].copy()
    tx["ticker"] = tx["ticker"].fillna("")
    pre_warn = []
    # Ohne Yahoo-Ticker (z. B. Derivate des Brokers): Zahlungen bleiben drin, die Position wird aber nicht bewertet
    no_t = tx["type"].isin(["buy", "sell", "dividend", "income", "transfer_in", "transfer_out", "deliver_in",
                            "deliver_out"]) & (tx["ticker"] == "") & \
        (tx["isin"].fillna("") != "")
    unpriced = sorted(set(tx.loc[no_t, "isin"]))
    if unpriced:
        pre_warn.append(f"{int(no_t.sum())} bookings in {len(unpriced)} instruments without Yahoo price "
                        f"({', '.join(unpriced)}): cash flows counted, holdings not valued - add tickers to "
                        f"portfolios/isin_map.csv if they are listed")
        tx.loc[no_t, "ticker"] = "NOPRICE:" + tx.loc[no_t, "isin"]
    tickers = sorted(t for t in tx.loc[tx["type"].isin(["buy", "sell", "transfer_in", "deliver_in"]), "ticker"].unique()
                     if t and not t.startswith("NOPRICE:"))
    start = tx["date"].min()
    if market is None:
        market = load_market_data(tickers, (start - pd.Timedelta(days=7)).date().isoformat())
    prices, total, fx = market["close"], market["total"], market.get("fx", {})
    for t in tickers:
        if t not in prices or prices[t].dropna().empty:
            prices[t], total[t] = np.nan, np.nan
    tx = _apply_splits(tx, market.get("splits"))
    splits = market.get("splits") or {}
    drop = []
    for i, r in tx[tx["type"].isin(["transfer_in", "transfer_out"])].iterrows():
        sp = splits.get(r["ticker"])
        if sp is not None and len(sp) and min(abs((pd.Timestamp(d).tz_localize(None) - r["date"]).days)
                                              for d in sp.index) <= 14:
            drop.append(i)                                  # Split-Buchung des Brokers: Yahoo-Kurse sind schon bereinigt
    for (d, t), g in tx[tx["type"].isin(["transfer_in", "transfer_out"])].drop(drop).groupby(["date", "ticker"]):
        net = g.loc[g["type"] == "transfer_in", "shares"].sum() - g.loc[g["type"] == "transfer_out", "shares"].sum()
        if len(g) > 1 and abs(net) < 1e-6:
            drop += list(g.index)                           # Umtausch 1:1 (z. B. neue ISIN, gleicher Ticker)
    if drop:
        tx = tx.drop(drop)
    warnings = pre_warn
    nodata = [t for t in tickers if prices[t].dropna().empty]
    if nodata:
        warnings.append(f"no Yahoo prices for {', '.join(nodata)} (delisted or wrong ticker) - valued at 0")
    idx = prices.loc[prices.index >= start].index
    if len(idx) == 0:
        raise ValueError("no price data after the first transaction")
    # Cash-Konto je Exportdatei, sofern diese Ein-/Auszahlungen enthaelt (mehrere Broker getrennt)
    if "source" not in tx:
        tx["source"] = "transactions"
    cash_src = set(tx.loc[tx["type"].isin(["deposit", "withdrawal"]), "source"])
    cash_mode = bool(cash_src)
    # Buchungen an Nicht-Handelstagen -> naechster Handelstag
    tx["day"] = tx["date"].apply(lambda d: idx[min(idx.searchsorted(d), len(idx) - 1)])
    # Vorlage ohne Kurs: Schlusskurs des Tages (EUR) verwenden
    miss = tx["type"].isin(["buy", "sell"]) & tx["price"].isna() & tx["amount"].isna() & tx["ticker"].isin(tickers)
    for i in tx.index[miss]:
        tx.at[i, "price"] = float(prices.loc[tx.at[i, "day"], tx.at[i, "ticker"]])
        tx.at[i, "currency"] = "EUR"

    # Zahlungsbetrag je Buchung in EUR. Hat der Export eine Betragsspalte, ist das die tatsaechliche Kontobewegung
    # (Kauf inkl. Gebuehr, Verkauf/Dividende nach Gebuehr und Steuer). Sonst: Stueck x Kurs +/- Gebuehr/Steuer.
    def _ok(v):
        return v is not None and v == v

    def cash_eur(r):
        if _ok(r.get("amount")) and r.get("broker") != "template":
            return _eur(abs(r["amount"]), r["currency"], r["date"], fx)
        gross = (r["shares"] or 0) * (r["price"] or 0) if r["type"] in ("buy", "sell") else abs(r["amount"] or 0)
        fee, tax = abs(r.get("fee") or 0), abs(r.get("tax") or 0)
        net = gross + fee if r["type"] == "buy" else gross - fee - (tax if r["type"] != "deposit" else 0)
        return _eur(net, r["currency"], r["date"], fx)
    tx["cash"] = tx.apply(cash_eur, axis=1)
    # Plausibilitaet: Ausfuehrungskurs (EUR) vs. Yahoo-Schlusskurs - grosse Abweichung = falscher Ticker/Waehrung
    for _, r in tx[tx["type"].isin(["buy", "sell"]) & tx["ticker"].isin(tickers)].iterrows():
        mkt = prices[r["ticker"]].get(r["day"])
        px_eur = r["cash"] / r["shares"] if r["shares"] else None
        if mkt and px_eur and mkt == mkt and abs(px_eur / mkt - 1) > 0.25:
            warnings.append(f"{r['date'].date()} {r['type']} {r['ticker']}: trade price EUR {px_eur:,.2f} vs market close "
                            f"EUR {mkt:,.2f} - check ticker mapping (isin_map.csv) or split")
    tx["fee_eur"] = tx.apply(lambda r: _eur(abs(r["fee"] or 0), r["currency"], r["date"], fx), axis=1)

    tx["mv"] = np.nan
    # Depotuebertrag: Wert = Stueck x Schlusskurs am Tag (Fluss fuer TTWROR/MWR); Einstand = Betrag laut Export
    for i in tx.index[tx["type"].isin(["deliver_in", "deliver_out"])]:
        t, d = tx.at[i, "ticker"], tx.at[i, "day"]
        mkt = prices[t].get(d) if t in tickers else None
        tx.at[i, "mv"] = float(mkt) * tx.at[i, "shares"] if mkt is not None and mkt == mkt else tx.at[i, "cash"]
    # Taegliche Bestaende und Zahlungen
    shares = pd.DataFrame(0.0, index=idx, columns=tickers)
    cash_df = pd.DataFrame(0.0, index=idx, columns=sorted(cash_src) or ["_"])
    ext = pd.Series(0.0, index=idx)          # externe Zufluesse (+) / Abfluesse (-)
    sec_ext = pd.Series(0.0, index=idx)      # nur Wertpapiere: Kauf = Zufluss, Verkauf/Ertrag = Abfluss
    ns_shares = pd.DataFrame(0.0, index=idx, columns=tickers)   # Gegenszenario "nie verkauft"
    ns_ext = pd.Series(0.0, index=idx)
    for _, r in tx.iterrows():
        d, t, c, src = r["day"], r["ticker"], r["cash"], r["source"]
        has_cash = src in cash_src
        sign = {"buy": -1, "sell": 1, "dividend": 1, "interest": 1, "income": 1, "deposit": 1, "withdrawal": -1,
                "fee": -1, "tax": -1, "transfer_in": 0, "transfer_out": 0, "deliver_in": 0, "deliver_out": 0}[r["type"]]
        priced = t in shares.columns
        if r["type"] in ("buy", "transfer_in") and priced:
            shares.loc[d:, t] += r["shares"]
        elif r["type"] == "transfer_out" and priced:
            shares.loc[d:, t] -= min(r["shares"], max(shares.loc[d, t], 0))
        elif r["type"] == "sell" and priced:
            if shares.loc[d, t] + 1e-9 < r["shares"]:
                warnings.append(f"{r['date'].date()} sell {t}: {r['shares']:g} shares but only {shares.loc[d, t]:g} held "
                                f"(history incomplete?) - capped")
            shares.loc[d:, t] -= min(r["shares"], max(shares.loc[d, t], 0))
        if r["type"] in ("deliver_in", "deliver_out"):
            mv = r["mv"]
            if priced:
                if r["type"] == "deliver_in":
                    shares.loc[d:, t] += r["shares"]
                    ns_shares.loc[d:, t] += r["shares"]
                    ns_ext.loc[d] += mv
                else:
                    shares.loc[d:, t] -= min(r["shares"], max(shares.loc[d, t], 0))
                sec_ext.loc[d] += mv if r["type"] == "deliver_in" else -mv
                ext.loc[d] += mv if r["type"] == "deliver_in" else -mv
            continue
        if priced and r["type"] in ("buy", "transfer_in"):
            ns_shares.loc[d:, t] += r["shares"]
        if priced and r["type"] in ("buy", "sell", "dividend", "income"):
            sec_ext.loc[d] -= sign * c
            if r["type"] == "buy":
                ns_ext.loc[d] += c
        if sign == 0:
            continue
        if has_cash:
            cash_df.loc[d:, src] += sign * c
            if r["type"] in ("deposit", "withdrawal"):
                ext.loc[d] += sign * c
        elif r["type"] not in ("deposit", "withdrawal"):
            ext.loc[d] -= sign * c           # ohne Cash-Konto: Kauf = Zufluss, Verkauf/Dividende = Abfluss
    # Fehlende Einzahlungen (Export beginnt spaeter, Cash wuerde negativ): als implizite Einzahlung werten
    implicit = 0.0
    for col in cash_df.columns:
        need = (-cash_df[col].cummin()).clip(lower=0)
        add = need.diff().fillna(need.iloc[0]).clip(lower=0)
        if add.sum() > 0.005:
            cash_df[col] += need
            ext += add
            implicit += float(add.sum())
    if implicit > 0:
        warnings.append(f"cash balance would turn negative (deposits missing in export) - treated EUR {implicit:,.0f} "
                        f"as implicit deposits")
    cash = cash_df.sum(axis=1)
    shares = shares.clip(lower=0)
    px = prices.reindex(idx)[tickers].ffill()
    sec_value = (shares * px.fillna(0.0)).sum(axis=1)
    value = sec_value + (cash if cash_mode else 0.0)

    # TTWROR: Zahlungen zum Tagesende (Trades zum Schlusskurs), r_t = (V_t - CF_t) / V_{t-1} - 1
    prev = value.shift(1).fillna(0.0)
    r = pd.Series(np.where(prev > 1e-6, (value - ext) / prev.where(prev > 1e-6, 1.0) - 1, 0.0), index=idx)
    first = ext[ext.abs() > 1e-9].index.min() if (ext.abs() > 1e-9).any() else idx[0]
    r = r.loc[first:]
    bad = (r < -0.9) | (r > 3)
    if bad.any():                                  # unplausible Tagesrendite: meist falscher Ticker oder Kurs
        warnings.append(f"{int(bad.sum())} day(s) with implausible portfolio returns (e.g. {bad[bad].index[0].date()}) "
                        f"were capped at -90%/+300% - check the ticker mapping and the price warnings")
        r = r.clip(-0.9, 3)
    ttwror_curve = (1 + r).cumprod()
    years = max((idx[-1] - first).days / 365.25, 1 / 365)
    ttwror = float(ttwror_curve.iloc[-1] - 1)
    ttwror_pa = float((1 + ttwror) ** (1 / years) - 1) if ttwror > -1 else -1.0

    # MWR (Anlegersicht: Zufluss ins Depot = negativ, Endwert = positiv)
    flows = [(d, -a) for d, a in ext.items() if abs(a) > 1e-9] + [(idx[-1], float(value.iloc[-1]))]
    mwr = _xirr(flows)

    # Benchmark mit denselben Zahlungen
    b = total[BENCH].reindex(idx).ffill()
    units = (ext / b).cumsum()
    bench_value = units * b
    b_flows = [(d, -a) for d, a in ext.items() if abs(a) > 1e-9] + [(idx[-1], float(bench_value.iloc[-1]))]
    bench_mwr = _xirr(b_flows)
    b_r = b.loc[first:].pct_change().fillna(0)
    bench_curve = (1 + b_r).cumprod()
    bench_tw = float(bench_curve.iloc[-1] - 1)

    # Nur investiertes Kapital (ohne Cash) und Gegenszenario "nie verkauft" (gleiche Kaeufe, keine Verkaeufe)
    sec_curve = _ttw_curve(sec_value, sec_ext, first)
    ns_value = (ns_shares * px.fillna(0.0)).sum(axis=1)
    ns_curve = _ttw_curve(ns_value, ns_ext, first)
    sec_mwr = _xirr([(d, -a) for d, a in sec_ext.items() if abs(a) > 1e-9] + [(idx[-1], float(sec_value.iloc[-1]))])
    ns_mwr = _xirr([(d, -a) for d, a in ns_ext.items() if abs(a) > 1e-9] + [(idx[-1], float(ns_value.iloc[-1]))])
    proceeds = float(-(sec_ext.clip(upper=0)).sum())
    never_sold = {"value": float(ns_value.iloc[-1]), "actual_sec_value": float(sec_value.iloc[-1]),
                  "proceeds_and_income": proceeds, "mwr": ns_mwr, "actual_mwr": sec_mwr,
                  "ttwror": float(ns_curve.iloc[-1] - 1), "actual_ttwror": float(sec_curve.iloc[-1] - 1)}

    # Zeitraeume (YTD, 1/3/5 Jahre, seit Beginn) und Kalenderjahre
    end = idx[-1]
    periods = []
    for lab, s0, ann in (("YTD", pd.Timestamp(end.year, 1, 1), False), ("1 year", end - pd.DateOffset(years=1), False),
                         ("3 years", end - pd.DateOffset(years=3), True), ("5 years", end - pd.DateOffset(years=5), True),
                         ("Since start", first, True)):
        if s0 >= first or lab == "Since start":
            row = _period_row(lab, max(s0, first), value, ext, ttwror_curve, bench_curve, end, ann)
            if row:
                periods.append(row)
    years_tab = []
    for y in range(first.year, end.year + 1):
        ye = idx[idx <= pd.Timestamp(y, 12, 31)][-1]
        row = _period_row(str(y) + (" YTD" if y == end.year else ""), max(pd.Timestamp(y, 1, 1), first), value, ext,
                          ttwror_curve, bench_curve, ye, False)
        if row:
            years_tab.append(row)

    # Datenqualitaet: unplausible Kurssprunge (Yahoo-Fehler oder falscher Ticker)
    for t in tickers:
        ch = px[t].dropna().pct_change().abs()
        if len(ch) and ch.max() > 0.8:
            warnings.append(f"{t}: daily price move of {ch.max() * 100:.0f}% on {ch.idxmax().date()} - check Yahoo data "
                            f"or the ticker mapping")

    # Positionen (Durchschnittskosten)
    positions = []
    last_px = px.iloc[-1]
    for t in tickers:
        sub = tx[tx["ticker"] == t]
        q, cost, realized, divs, fees, pflows = 0.0, 0.0, 0.0, 0.0, 0.0, []
        for _, rr in sub.iterrows():
            if rr["type"] == "buy":
                q += rr["shares"]
                cost += rr["cash"]
                fees += rr["fee_eur"]
                pflows.append((rr["day"], -rr["cash"]))
            elif rr["type"] == "sell" and q > 0:
                n = min(rr["shares"], q)
                avg = cost / q
                pro = rr["cash"] * n / rr["shares"]
                realized += pro - avg * n
                cost -= avg * n
                q -= n
                fees += rr["fee_eur"]
                pflows.append((rr["day"], pro))
            elif rr["type"] == "deliver_in":                # Depotuebertrag: Einstand laut Export
                q += rr["shares"]
                cost += rr["cash"] if rr["cash"] else rr["mv"]
                pflows.append((rr["day"], -rr["mv"]))
            elif rr["type"] == "deliver_out" and q > 0:     # Abgang zum Marktwert
                n = min(rr["shares"], q)
                realized += rr["mv"] * n / rr["shares"] - cost / q * n
                cost -= cost / q * n
                q -= n
                pflows.append((rr["day"], rr["mv"] * n / rr["shares"]))
            elif rr["type"] == "transfer_in":
                q += rr["shares"]                       # ohne Einstand (Spin-off, Gratisaktien)
            elif rr["type"] == "transfer_out" and q > 0:
                n = min(rr["shares"], q)
                removed = cost / q * n
                cost -= removed
                realized -= removed                      # z. B. Fusion gegen Barabfindung (Erloes als income)
                q -= n
            elif rr["type"] == "dividend":
                divs += rr["cash"]
                pflows.append((rr["day"], rr["cash"]))
            elif rr["type"] == "income":                 # Barabfindung, Entschaedigung, Praemie
                realized += rr["cash"]
                pflows.append((rr["day"], rr["cash"]))
        q = q if q > 1e-6 and not (last_px[t] == last_px[t] and q * float(last_px[t]) < 0.5) else 0.0   # Rundungsrest < 0,50 EUR = geschlossen
        mv = q * float(last_px[t]) if q > 0 and last_px[t] == last_px[t] else 0.0
        positions.append({"ticker": t, "name": str(sub["name"].iloc[-1] or t), "shares": q, "market_value": mv,
                          "cost_open": cost, "unrealized": mv - cost if q > 0 else 0.0, "realized": realized,
                          "dividends": divs, "fees": fees, "total_pl": mv - cost + realized + divs if q > 0 else realized + divs,
                          "irr": _xirr(pflows + ([(idx[-1], mv)] if mv > 0 else [])), "open": q > 1e-9})
    if unpriced:
        sub = tx[tx["ticker"].str.startswith("NOPRICE:")]
        sgn = sub["type"].map({"buy": -1, "sell": 1, "dividend": 1, "income": 1}).fillna(0)
        net = float((sgn * sub["cash"]).sum())
        positions.append({"ticker": "Unpriced instruments", "name": f"{len(unpriced)} instruments without Yahoo price",
                          "shares": 0.0, "market_value": 0.0, "cost_open": 0.0, "unrealized": 0.0, "realized": net,
                          "dividends": 0.0, "fees": float(sub["fee_eur"].sum()), "total_pl": net, "irr": None,
                          "open": False})
    total_pl = sum(p["total_pl"] for p in positions)
    for p in positions:
        p["contribution"] = p["total_pl"] / total_pl if total_pl else None

    # Entscheidungen vs. MSCI ACWI (Total Return):
    # - Kauf: ueber die tatsaechliche Haltedauer (FIFO bis zum Verkauf, sonst bis heute)
    # - Verkauf: Entwicklung in den 12 Monaten danach (Opportunitaetskosten), bei juengeren Verkaeufen bis heute
    decisions = []
    tp_all = total.reindex(idx).ffill()

    def _ret(t, d0, d1):
        p0, p1, b0_, b1_ = tp_all[t].loc[d0], tp_all[t].loc[d1], b.loc[d0], b.loc[d1]
        if not (p0 == p0 and p1 == p1 and p0 > 0 and b0_ > 0):
            return None, None
        return float(p1 / p0 - 1), float(b1_ / b0_ - 1)
    for t in tickers:
        lots, segs = [], {}
        for i, rr in tx[(tx["ticker"] == t) & tx["type"].isin(["buy", "sell", "transfer_in", "transfer_out", "deliver_in",
                                                                "deliver_out"])].iterrows():
            if rr["type"] in ("buy", "transfer_in", "deliver_in"):
                lots.append([i, rr["shares"], rr["type"] == "buy"])
                segs[i] = []
            else:
                left = rr["shares"]
                while left > 1e-12 and lots:
                    n = min(left, lots[0][1])
                    segs[lots[0][0]].append((n, rr["day"]))
                    lots[0][1] -= n
                    left -= n
                    if lots[0][1] <= 1e-12:
                        lots.pop(0)
                if rr["type"] == "sell":
                    d1 = idx[min(idx.searchsorted(rr["day"] + pd.DateOffset(years=1)), len(idx) - 1)]
                    rs, rb = _ret(t, rr["day"], d1)
                    if rs is not None:
                        decisions.append({"date": str(pd.Timestamp(rr["date"]).date()), "type": "sell", "ticker": t,
                                          "eur": rr["cash"], "ret_stock": rs, "ret_bench": rb, "excess": rb - rs,
                                          "impact_eur": rr["cash"] * (rb - rs), "days": int((d1 - rr["day"]).days)})
        for lot in lots:
            segs[lot[0]].append((lot[1], idx[-1]))
        for i, sg in segs.items():
            rr = tx.loc[i]
            if rr["type"] != "buy" or not sg:
                continue
            tot = sum(n for n, _ in sg)
            rs_w = rb_w = days_w = 0.0
            ok = True
            for n, d1 in sg:
                rs, rb = _ret(t, rr["day"], d1)
                if rs is None:
                    ok = False
                    break
                w = n / tot
                rs_w, rb_w, days_w = rs_w + w * rs, rb_w + w * rb, days_w + w * (d1 - rr["day"]).days
            if ok:
                decisions.append({"date": str(pd.Timestamp(rr["date"]).date()), "type": "buy", "ticker": t,
                                  "eur": rr["cash"], "ret_stock": rs_w, "ret_bench": rb_w, "excess": rs_w - rb_w,
                                  "impact_eur": rr["cash"] * (rs_w - rb_w), "days": int(days_w),
                                  "held": ("open" if all(d1 == idx[-1] for _, d1 in sg) else
                                           "partly sold" if any(d1 == idx[-1] for _, d1 in sg) else "sold")})
    trades = [(pd.Timestamp(rr["day"]), rr["type"], rr["ticker"], rr["cash"]) for _, rr in
              tx[tx["type"].isin(["buy", "sell"]) & tx["ticker"].isin(tickers)].iterrows()]

    # --- Letzte 12 Monate: Attribution je Position, Umschlag und Kosten (Vorbild: Fundsmith, Pershing Square)
    end = idx[-1]
    p_start = max(first, end - pd.DateOffset(years=1))
    prev = idx[idx < p_start]
    d0 = prev[-1] if len(prev) else None
    in_p = (tx["day"] > d0) if d0 is not None else (tx["day"] >= p_start)
    txp = tx[in_p & (tx["day"] <= end)]
    avg_value = float(value.loc[p_start:].mean()) if len(value.loc[p_start:]) else float(value.iloc[-1])
    flow_sign = {"buy": 1, "sell": -1, "dividend": -1, "income": -1}
    attribution = []
    for t in tickers:
        v0 = float(shares.loc[d0, t] * px.loc[d0, t]) if d0 is not None and px.loc[d0, t] == px.loc[d0, t] else 0.0
        v1 = float(shares.iloc[-1][t] * px.iloc[-1][t]) if px.iloc[-1][t] == px.iloc[-1][t] else 0.0
        sub = txp[txp["ticker"] == t]
        net_in = float(sum(flow_sign.get(r["type"], 0) * r["cash"] for _, r in sub.iterrows())
                       + sum(r["mv"] if r["type"] == "deliver_in" else -r["mv"] for _, r in sub.iterrows()
                             if r["type"] in ("deliver_in", "deliver_out") and r["mv"] == r["mv"]))
        pl = v1 - v0 - net_in
        if abs(pl) > 0.5 or v0 or v1:
            attribution.append({"ticker": t, "pl_eur": pl, "contribution": pl / avg_value if avg_value else None,
                                "start_value": v0, "end_value": v1})
    if unpriced:
        sub = txp[txp["ticker"].str.startswith("NOPRICE:")]
        pl = float(sum(-flow_sign.get(r["type"], 0) * r["cash"] for _, r in sub.iterrows()))
        if abs(pl) > 0.5:
            attribution.append({"ticker": "Unpriced instruments", "pl_eur": pl,
                                "contribution": pl / avg_value if avg_value else None, "start_value": 0.0, "end_value": 0.0})
    v_start = float(value.loc[d0]) if d0 is not None else 0.0
    total_pl = float(value.iloc[-1] - v_start - ext[ext.index > d0].sum()) if d0 is not None \
        else float(value.iloc[-1] - ext.sum())
    rest = total_pl - sum(x["pl_eur"] for x in attribution)
    if abs(rest) > 0.5:
        attribution.append({"ticker": "Cash, interest, fees, other", "pl_eur": rest,
                            "contribution": rest / avg_value if avg_value else None, "start_value": 0.0, "end_value": 0.0})
    attribution.sort(key=lambda x: x["pl_eur"])
    buys_p = float(txp.loc[txp["type"] == "buy", "cash"].sum())
    sells_p = float(txp.loc[txp["type"] == "sell", "cash"].sum())
    tax_eur = txp.apply(lambda r: _eur(abs(r["tax"] or 0) if r["tax"] == r["tax"] else 0, r["currency"], r["date"], fx), axis=1) \
        if len(txp) else pd.Series(dtype=float)
    costs = {"start": str(p_start.date()), "end": str(end.date()), "avg_value": avg_value, "purchases": buys_p,
             "sales": sells_p, "turnover": min(buys_p, sells_p) / avg_value if avg_value else None,
             "n_trades": int(txp["type"].isin(["buy", "sell"]).sum()), "fees": float(txp["fee_eur"].sum()),
             "fees_pct": float(txp["fee_eur"].sum()) / avg_value if avg_value else None,
             "taxes": float(tax_eur.sum()) if len(tax_eur) else 0.0, "total_pl": total_pl,
             "total_contribution": total_pl / avg_value if avg_value else None}

    # --- Ausstiege: vollstaendig verkaufte Positionen mit Nachschau (Vorbild: Pershing Square, Greenlight)
    exits = []
    for p_ in [x for x in positions if not x["open"] and x["ticker"] in tickers]:
        sub = tx[tx["ticker"] == p_["ticker"]]
        bu, se = sub[sub["type"].isin(["buy", "deliver_in"])], sub[sub["type"].isin(["sell", "deliver_out"])]
        if bu.empty or se.empty:
            continue
        d_in, d_out = bu["day"].min(), se["day"].max()
        rs, rb = _ret(p_["ticker"], d_in, d_out)
        after_s, after_b = _ret(p_["ticker"], d_out, idx[-1]) if d_out < idx[-1] else (None, None)
        exits.append({"ticker": p_["ticker"], "first_buy": str(d_in.date()), "last_sell": str(d_out.date()),
                      "days": int((d_out - d_in).days), "invested": float(bu["cash"].sum()),
                      "proceeds": float(se["cash"].sum()), "realized": p_["realized"], "dividends": p_["dividends"],
                      "total_pl": p_["total_pl"], "irr": p_["irr"], "stock_held": rs, "acwi_held": rb,
                      "excess_held": (rs - rb) if rs is not None else None, "stock_after": after_s, "acwi_after": after_b,
                      "excess_after": (after_s - after_b) if after_s is not None else None,
                      "recent": d_out >= p_start})
    exits.sort(key=lambda x: x["last_sell"], reverse=True)

    # --- Kandidaten fuer "Fehler und Lehren" (Vorbild: Giverny "Podium of Errors"): schwaechste Entscheidungen
    floor = -max(100.0, 0.002 * float(value.iloc[-1]))      # Kleinstbetraege sind keine Lehren wert
    worst_buys = sorted([d for d in decisions if d["type"] == "buy" and d["impact_eur"] < floor], key=lambda x: x["impact_eur"])[:3]
    worst_sells = sorted([d for d in decisions if d["type"] == "sell" and d["impact_eur"] < floor], key=lambda x: x["impact_eur"])[:2]
    mistakes = [dict(d, kind="buy that lagged the index over its holding period") for d in worst_buys] + \
        [dict(d, kind="sale followed by outperformance of the stock (sold too early)") for d in worst_sells]
    return {"mode": "cash account" if cash_mode else "securities only", "start": str(first.date()),
            "end": str(idx[-1].date()), "years": years, "value": value, "sec_value": sec_value,
            "cash": cash if cash_mode else None, "ext": ext, "invested": ext.cumsum(), "ttwror": ttwror,
            "ttwror_pa": ttwror_pa, "ttwror_curve": ttwror_curve, "mwr": mwr, "bench_tw": bench_tw,
            "bench_tw_pa": float((1 + bench_tw) ** (1 / years) - 1), "bench_curve": bench_curve,
            "bench_value": bench_value, "bench_mwr": bench_mwr, "final_value": float(value.iloc[-1]),
            "bench_final_value": float(bench_value.iloc[-1]), "net_invested": float(ext.sum()),
            "sec_curve": sec_curve, "ns_curve": ns_curve, "never_sold": never_sold, "periods": periods,
            "calendar_years": years_tab,
            "positions": positions, "decisions": decisions, "trades": trades, "current_shares": shares.iloc[-1],
            "max_dd": pe.max_drawdown(ttwror_curve), "n_trades": len(trades), "warnings": warnings,
            "fees_total": float(tx["fee_eur"].sum()), "dividends_total": float(tx.loc[tx["type"] == "dividend", "cash"].sum()),
            "attribution": attribution, "costs": costs, "exits": exits, "mistakes": mistakes}


def attach_notes(perf, path):
    """Optionale Entscheidungsnotizen (CSV: date,ticker,action,reason) den Kaeufen/Verkaeufen und Ausstiegen zuordnen
    (gleicher Ticker und Typ, Datum +/- 7 Tage). Ohne Datei bleibt alles unveraendert."""
    import csv as _csv
    from pathlib import Path as _P
    if not path or not _P(path).exists():
        return 0
    notes = []
    for r in _csv.DictReader(open(path, encoding="utf-8-sig")):
        try:
            notes.append((pd.Timestamp(r["date"]), r["ticker"].strip().upper(), r.get("action", "").strip().lower(),
                          r.get("reason", "").strip()))
        except Exception:
            continue

    def find(t, kind, d):
        best = [n for n in notes if n[1] == t.upper() and (not n[2] or n[2] == kind) and abs((n[0] - pd.Timestamp(d)).days) <= 7]
        return best[0][3] if best else None
    n = 0
    for d in perf.get("decisions", []) + perf.get("mistakes", []):
        d["note"] = find(d["ticker"], d["type"], d["date"])
        n += d["note"] is not None
    for e in perf.get("exits", []):
        e["entry_note"], e["exit_note"] = find(e["ticker"], "buy", e["first_buy"]), find(e["ticker"], "sell", e["last_sell"])
    perf["notes_file"] = str(path)
    return n


def holdings_portfolio(perf, min_value=1.0):
    """Aktuelle Bestaende als Portfolio-Liste fuer portfolio_engine.analyze (ticker + shares); nur bewertbare Titel."""
    mv = {p["ticker"]: p["market_value"] for p in perf["positions"]}
    return [{"ticker": t, "shares": float(q)} for t, q in perf["current_shares"].items()
            if q > 1e-6 and mv.get(t, 0) >= min_value]


def condensed_positions(perf, n_closed=5):
    """Offene Positionen + beste/schlechteste geschlossene; Rest zusammengefasst (fuer Tabelle und Agententext)."""
    pos = perf["positions"]
    open_ = sorted([p for p in pos if p["open"]], key=lambda x: -x["total_pl"])
    closed = sorted([p for p in pos if not p["open"]], key=lambda x: -x["total_pl"])
    if len(closed) <= 2 * n_closed + 1:
        return open_, closed, None
    keep = closed[:n_closed] + closed[-n_closed:]
    rest = closed[n_closed:-n_closed]
    other = {"ticker": f"Other closed ({len(rest)})", "name": "", "open": False, "market_value": 0.0, "unrealized": 0.0,
             "realized": sum(p["realized"] for p in rest), "dividends": sum(p["dividends"] for p in rest),
             "total_pl": sum(p["total_pl"] for p in rest), "irr": None}
    tot = sum(p["total_pl"] for p in pos)
    other["contribution"] = other["total_pl"] / tot if tot else None
    return open_, keep, other


def performance_text(perf):
    P = pe._p
    lines = [f"ACTUAL PERFORMANCE FROM TRANSACTIONS ({perf['start']} to {perf['end']}, {perf['n_trades']} trades, mode: "
             f"{perf['mode']}; prices in EUR from Yahoo Finance; cite as [1]):",
             f"- Value today EUR {perf['final_value']:,.0f}; net external inflows EUR {perf['net_invested']:,.0f}; same cash "
             f"flows in the MSCI ACWI would be worth EUR {perf['bench_final_value']:,.0f} (difference EUR "
             f"{perf['final_value'] - perf['bench_final_value']:,.0f}).",
             f"- MWR / IRR since start (money-weighted): {P(perf['mwr'])} p.a.; same cash flows in the MSCI ACWI: "
             f"{P(perf['bench_mwr'])} p.a. Max drawdown (TTWROR): {P(perf['max_dd'])}.",
             "RETURNS BY PERIOD (TTWROR = time-weighted; periods over one year annualized, p.a.; MWR = money-weighted; "
             "P/L = change in value minus net inflows):"]
    for r in perf["periods"] + perf["calendar_years"]:
        u = " p.a." if r["annualized"] else ""
        lines.append(f"- {r['period']} (from {r['start']}): portfolio TTWROR {P(r['ttwror'])}{u}, MSCI ACWI {P(r['bench'])}{u}, "
                     f"difference {P(r['diff'])}{u}; MWR {P(r['mwr'])}{u}; P/L EUR {r['pl_eur']:,.0f}")
    ns = perf["never_sold"]
    lines.append(f"- Securities only (excluding cash): TTWROR {P(ns['actual_ttwror'])} cumulative, MWR {P(ns['actual_mwr'])} "
                 f"p.a. Counterfactual 'never sold' (same buys, no sales): TTWROR {P(ns['ttwror'])} cumulative, MWR "
                 f"{P(ns['mwr'])} p.a.; holdings would be worth EUR {ns['value']:,.0f} today vs actual holdings EUR "
                 f"{ns['actual_sec_value']:,.0f} plus EUR {ns['proceeds_and_income']:,.0f} received from sales and income.")
    open_, closed, other = condensed_positions(perf)
    lines.append("POSITIONS (average-cost method; total P/L = unrealized + realized + dividends; IRR per position). Open:")
    for p in open_:
        lines.append(f"- {p['ticker']}: value EUR {p['market_value']:,.0f}, unrealized EUR {p['unrealized']:,.0f}, realized "
                     f"EUR {p['realized']:,.0f}, dividends EUR {p['dividends']:,.0f}, total EUR {p['total_pl']:,.0f} "
                     f"({P(p['contribution'])} of total P/L), IRR {P(p['irr'])}")
    if closed:
        lines.append("Closed (best and worst" + (", rest aggregated):" if other else "):"))
        for p in closed + ([other] if other else []):
            lines.append(f"- {p['ticker']}: realized EUR {p['realized']:,.0f}, dividends EUR {p['dividends']:,.0f}, total EUR "
                         f"{p['total_pl']:,.0f} ({P(p['contribution'])} of total P/L), IRR {P(p['irr'])}")
    dec = sorted(perf["decisions"], key=lambda x: -x["impact_eur"])
    if dec:
        lines.append("DECISIONS vs MSCI ACWI (total return). Buy: stock minus index over the actual holding period (FIFO until "
                     "sold, else until today). Sell: index minus stock over the 12 months after the sale. Value added = "
                     "amount x excess:")
        for x in dec[:5] + (dec[-5:] if len(dec) > 5 else []):
            held = f", {x['held']}" if x.get("held") else ""
            lines.append(f"- {x['date']} {x['type']} {x['ticker']} EUR {x['eur']:,.0f}: stock {P(x['ret_stock'])}, index "
                         f"{P(x['ret_bench'])}, excess {P(x['excess'])}, value added EUR {x['impact_eur']:,.0f} "
                         f"({x['days']} days{held})")
        buys = [x for x in dec if x["type"] == "buy"]
        sells = [x for x in dec if x["type"] == "sell"]
        if buys:
            lines.append(f"- Buys beating the index over their holding period: {sum(x['excess'] > 0 for x in buys)} of "
                         f"{len(buys)}; total value added EUR {sum(x['impact_eur'] for x in buys):,.0f}.")
        if sells:
            lines.append(f"- Sells followed by underperformance of the stock within 12 months (good sells): "
                         f"{sum(x['excess'] > 0 for x in sells)} of {len(sells)}; total value added EUR "
                         f"{sum(x['impact_eur'] for x in sells):,.0f}.")
    c = perf.get("costs")
    if c:
        big = [x for x in perf["attribution"] if x["contribution"] is not None and abs(x["contribution"]) >= 0.005]
        small = [x for x in perf["attribution"] if x not in big]
        lines.append(f"ATTRIBUTION last 12 months ({c['start']} to {c['end']}; P/L in EUR = change in value minus net purchases, "
                     f"contribution in % of the average portfolio value EUR {c['avg_value']:,.0f}; detractors first):")
        for x in big:
            lines.append(f"- {x['ticker']}: EUR {x['pl_eur']:,.0f} ({P(x['contribution'])})")
        if small:
            lines.append(f"- {len(small)} other positions below 0.5% each: EUR {sum(x['pl_eur'] for x in small):,.0f}")
        lines.append(f"- Total: EUR {c['total_pl']:,.0f} ({P(c['total_contribution'])} of average value)")
        lines.append(f"TURNOVER AND COSTS last 12 months: purchases EUR {c['purchases']:,.0f}, sales EUR {c['sales']:,.0f}, "
                     f"{c['n_trades']} trades, turnover {P(c['turnover'])} (lower of purchases and sales / average value), "
                     f"fees EUR {c['fees']:,.0f} ({P(c['fees_pct'])} of average value), taxes EUR {c['taxes']:,.0f}.")
    ex = perf.get("exits") or []
    if ex:
        lines.append("EXITS (fully sold positions, most recent first; held = first buy to last sale; after = since the last "
                     "sale until today, both vs MSCI ACWI):")
        for e in ex[:8]:
            note = "".join(f"; {k} note: {e[k]}" for k in ("entry_note", "exit_note") if e.get(k))
            lines.append(f"- {e['ticker']}: {e['first_buy']} to {e['last_sell']} ({e['days']} days), invested EUR "
                         f"{e['invested']:,.0f}, total P/L EUR {e['total_pl']:,.0f}, IRR {P(e['irr'])}; while held stock "
                         f"{P(e['stock_held'])} vs ACWI {P(e['acwi_held'])}; after the sale stock {P(e['stock_after'])} vs "
                         f"ACWI {P(e['acwi_after'])}{note}")
    mk = perf.get("mistakes") or []
    if mk:
        lines.append("MISTAKE CANDIDATES (weakest decisions by value lost vs MSCI ACWI). Reasons at the time are only known "
                     "where a note exists; otherwise do NOT invent motives, state that no rationale was recorded:")
        for d in mk:
            lines.append(f"- {d['date']} {d['type']} {d['ticker']} EUR {d['eur']:,.0f}: {d['kind']}; stock {P(d['ret_stock'])} "
                         f"vs ACWI {P(d['ret_bench'])}, value lost EUR {-d['impact_eur']:,.0f} ({d['days']} days)"
                         + (f"; note at the time: {d['note']}" if d.get("note") else "; no rationale recorded"))
    if perf["warnings"]:
        lines.append("DATA NOTES (mention material ones as caveats): " + " | ".join(perf["warnings"][:8]))
    return "\n".join(l for l in lines if l)
