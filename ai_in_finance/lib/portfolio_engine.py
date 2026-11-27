"""
Portfolio-Engine (eigene Erweiterung): Daten, Analyse, Optimierung und Backtest - alles deterministisch.

Bewusst nur mit numpy/pandas (auf dem Laptop ist kein scipy installiert):
- Kovarianz: Ledoit-Wolf-Schaetzer (Schrumpfung zur skalierten Einheitsmatrix), stabiler als die Stichprobe.
- Optimierung: projizierter Gradientenabstieg auf dem "gekappten Simplex" (long-only, Summe 100 %, max. Gewicht
  je Titel); Sektor-Obergrenzen ueber Straffunktion.
- HRP (Hierarchical Risk Parity, Lopez de Prado 2016): eigene Clusterung (Single Linkage) + rekursive Halbierung.
- Backtest: Walk-forward - optimiert wird nur mit Daten bis zum jeweiligen Stichtag.

Basiswaehrung EUR: Kurse in Fremdwaehrung werden mit Yahoo-Wechselkursen (EURxxx=X) umgerechnet.
Benchmarks: MSCI ACWI (iShares ETF ACWI, in EUR umgerechnet) und FTSE All-World (Vanguard VWCE.DE, EUR).
"""
import csv
import math
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

TRADING_DAYS = 252
BENCHMARKS = {"MSCI ACWI": "ACWI", "FTSE All-World": "VWCE.DE"}
STRESS = [("COVID crash", "2020-02-19", "2020-03-23"), ("2022 rate shock", "2022-01-03", "2022-10-12"),
          ("2025 tariff shock", "2025-02-19", "2025-04-08")]


# =============================================================== Eingabe
# Spaltennamen (kleingeschrieben, ohne Leer- und Sonderzeichen) -> Feld
PORTFOLIO_COLS = {
    "ticker": ["ticker", "symbol", "tickersymbol", "kuerzel", "yahooticker"],
    "isin": ["isin"],
    "weight": ["weight", "weights", "gewicht", "gewichtung", "anteil", "allocation", "portfolioweight", "weightpct",
               "weight_pct", "pct", "percent", "prozent", "anteilinprozent", "gewichtinprozent"],
    "shares": ["shares", "stueck", "stuecke", "stuck", "stueckzahl", "anzahl", "menge", "quantity", "qty", "units",
               "bestand", "position"],
    "cost": ["cost", "einstandskurs", "einstandspreis", "einstand", "kaufkurs", "avgprice", "averageprice",
             "durchschnittskurs", "costbasis", "buyprice"],
}


def portfolio_columns(header):
    """Feld -> Spaltenindex fuer eine einfache Portfolio-Datei (Gewichte oder Stueckzahlen)."""
    from .transactions import _norm
    h = [_norm(c) for c in header]
    out = {}
    for field, names in PORTFOLIO_COLS.items():
        for i, c in enumerate(h):
            if c in names and i not in out.values():
                out[field] = i
                break
    return out


def _clean_ticker(t):
    t = str(t or "").strip().strip('"').strip("'").upper().replace(" ", "")
    m = re.fullmatch(r"([A-Z]{1,5})[./]([AB])", t)        # BRK.B / BRK/B -> BRK-B (Yahoo-Schreibweise)
    return f"{m.group(1)}-{m.group(2)}" if m else t


def read_portfolio(path):
    """
    Einfache Portfolio-Datei lesen: Spalten Ticker (oder ISIN) und Gewicht (in % oder als Anteil) oder Stueckzahl,
    optional Einstandskurs. Erkennt Komma/Semikolon/Tab, deutsche Zahlen (1.234,5), Prozentzeichen, Excel-Kodierung
    und deutsche Spaltennamen. Rueckgabe: (positionen, hinweise); Fehler als ValueError mit verstaendlichem Text.
    """
    from .transactions import _read_table, _num
    try:
        header, rows = _read_table(path)
    except Exception:
        raise ValueError("The file is empty or not a readable CSV file.")
    cols = portfolio_columns(header)
    if "ticker" not in cols and "isin" not in cols:
        raise ValueError("No ticker column found (detected: " + ", ".join(h.strip() for h in header[:8])
                         + "). Expected e.g. ticker,weight or ticker,shares.")
    if "weight" not in cols and "shares" not in cols:
        raise ValueError("No weight or share-count column found. Expected e.g. ticker,weight "
                         "or ticker,shares.")
    issues = []
    num_idx = [cols[f] for f in ("weight", "shares", "cost") if f in cols]
    de = any(re.match(r"^-?[\d.]*\d,\d+\s*%?$", r[i].strip()) for r in rows for i in num_idx if i < len(r))
    cell = lambda r, f: r[cols[f]].strip() if f in cols and cols[f] < len(r) else ""
    raw = []
    for n, r in enumerate(rows, start=2):
        t = _clean_ticker(cell(r, "ticker")) if "ticker" in cols else ""
        isin = cell(r, "isin").upper()
        if not t and not isin:
            continue
        item = {"ticker": t, "isin": isin, "row": n}
        for f in ("weight", "shares", "cost"):
            v = cell(r, f)
            if v:
                x = _num(v, de=de)
                if x is None:
                    issues.append(f"Row {n}: '{v}' is not a number ({f}) – ignored")
                else:
                    item[f] = x
        raw.append(item)
    if not raw:
        raise ValueError("The file contains no positions.")
    need = sorted({x["isin"] for x in raw if not x["ticker"] and x["isin"]})
    if need:
        from .transactions import resolve_isins
        try:
            m, unresolved = resolve_isins(need)
        except Exception as e:
            m, unresolved = {}, need
            issues.append(f"ISIN lookup failed: {e}")
        for x in raw:
            if not x["ticker"] and x["isin"]:
                x["ticker"] = m.get(x["isin"], "")
        if unresolved:
            issues.append("No ticker found for ISIN " + ", ".join(unresolved[:8]) + " – please add the ticker")
        raw = [x for x in raw if x["ticker"]]
        if not raw:
            raise ValueError("; ".join(issues))
    has_w = [x for x in raw if x.get("weight") is not None]
    has_s = [x for x in raw if x.get("shares") is not None]
    if len(has_s) == len(raw):
        key = "shares"
    elif len(has_w) == len(raw) or len(has_w) >= len(has_s):
        key = "weight"
    else:
        key = "shares"
    skipped = [x["ticker"] for x in raw if x.get(key) is None]
    if skipped:
        issues.append(f"Skipped without {'weight' if key == 'weight' else 'share count'}: " + ", ".join(skipped[:10]))
    out = {}
    for x in raw:
        v = x.get(key)
        if v is None:
            continue
        if v <= 0:
            issues.append(f"Row {x['row']}: {x['ticker']} with {v:g} – skipped")
            continue
        if x["ticker"] in out:
            issues.append(f"{x['ticker']} appears more than once – combined")
            out[x["ticker"]][key] += v
            continue
        out[x["ticker"]] = {"ticker": x["ticker"], key: v}
        if x.get("cost") is not None:
            out[x["ticker"]]["cost"] = x["cost"]
    pos = list(out.values())
    if not pos:
        raise ValueError("No valid position found (all values empty or not positive).")
    if key == "weight":
        tot = sum(p["weight"] for p in pos)
        if not (0.98 <= tot <= 1.02 or 98 <= tot <= 102):
            issues.append(f"Gewichte summieren sich auf {tot:g} – sie werden auf 100 % skaliert")
    return pos, issues


def load_portfolio(path):
    """CSV mit Spalten ticker und shares ODER weight (in % oder als Anteil); optional cost (Einstandskurs)."""
    return read_portfolio(path)[0]


# =============================================================== Daten
def _yf():
    import yfinance as yf
    return yf


def _currency(t):
    try:
        info = _yf().Ticker(t).fast_info
        return info.get("currency") or info["currency"]
    except Exception:
        try:
            return _yf().Ticker(t).info.get("currency", "USD")
        except Exception:
            return "USD"


def download_prices(tickers, years=8):
    """Schlusskurse (dividendenbereinigt) in EUR, taeglich; dazu Waehrungen je Ticker."""
    yf = _yf()
    start = (pd.Timestamp.today() - pd.DateOffset(years=years)).date().isoformat()
    raw = yf.download(list(tickers), start=start, auto_adjust=True, progress=False)["Close"]
    if isinstance(raw, pd.Series):
        raw = raw.to_frame(tickers[0])
    curr = {t: _currency(t) for t in tickers}
    fx_needed = sorted({c for c in curr.values() if c and c.upper() not in ("EUR",)})
    fx = {}
    for c in fx_needed:
        base = "GBP" if c in ("GBp", "GBX") else c.upper()
        s = yf.download(f"EUR{base}=X", start=start, auto_adjust=True, progress=False)["Close"]
        fx[c] = s.squeeze()
    out = pd.DataFrame(index=raw.index)
    for t in tickers:
        p = raw[t].astype(float)
        c = curr.get(t, "EUR")
        if c in fx:
            rate = fx[c].reindex(p.index).ffill()
            p = p / rate / (100.0 if c in ("GBp", "GBX") else 1.0)
        out[t] = p
    return out.ffill().dropna(how="all"), curr


def fundamentals(tickers):
    """Sektor, Land, Bewertung und Konsens je Titel (Yahoo)."""
    yf = _yf()
    rows = {}
    for t in tickers:
        try:
            i = yf.Ticker(t).info or {}
        except Exception:
            i = {}
        price, target = i.get("currentPrice") or i.get("regularMarketPrice"), i.get("targetMeanPrice")
        rows[t] = {"name": i.get("shortName") or t, "sector": i.get("sector") or {"ETF": "ETF/Fund", "CRYPTOCURRENCY": "Crypto"}.get(i.get("quoteType"), "n/a"),
                   "country": i.get("country") or "n/a", "currency": i.get("currency") or "n/a",
                   "market_cap": i.get("marketCap"), "forward_pe": i.get("forwardPE"),
                   "peg": i.get("trailingPegRatio") or i.get("pegRatio"), "revenue_growth": i.get("revenueGrowth"),
                   "upside": (target / price - 1) if price and target else None, "beta_yahoo": i.get("beta"),
                   "rating": i.get("recommendationKey")}
    return rows


# =============================================================== Kennzahlen
def _returns(prices):
    return prices.pct_change().dropna(how="all")


def ann_vol(r):
    return float(r.std() * math.sqrt(TRADING_DAYS))


def cagr(series):
    s = series.dropna()
    if len(s) < 2:
        return None
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    return float((s.iloc[-1] / s.iloc[0]) ** (1 / yrs) - 1) if yrs > 0 else None


def max_drawdown(series):
    s = series.dropna()
    return float((s / s.cummax() - 1).min()) if len(s) else None


def perf_stats(r, bench_r=None, rf=0.02):
    """Kennzahlen einer Tagesrendite-Reihe."""
    r = r.dropna()
    if len(r) < 20:
        return {}
    curve = (1 + r).cumprod()
    vol = ann_vol(r)
    cg = cagr(curve)
    downside = r[r < 0].std() * math.sqrt(TRADING_DAYS)
    var95 = float(np.percentile(r, 5))
    out = {"cagr": cg, "vol": vol, "sharpe": (cg - rf) / vol if vol and cg is not None else None,
           "sortino": (cg - rf) / downside if downside and cg is not None else None,
           "max_dd": max_drawdown(curve), "var95_1d": var95, "cvar95_1d": float(r[r <= var95].mean())}
    if bench_r is not None:
        b = bench_r.reindex(r.index).dropna()
        rr = r.reindex(b.index)
        if len(b) > 20:
            cov = np.cov(rr, b)
            out["beta"] = float(cov[0, 1] / cov[1, 1])
            te = (rr - b).std() * math.sqrt(TRADING_DAYS)
            bc = cagr((1 + b).cumprod())
            out["tracking_error"] = float(te)
            out["info_ratio"] = (cg - bc) / te if te and bc is not None else None
            out["bench_cagr"] = bc
    return out


def ledoit_wolf(r):
    """Ledoit-Wolf-Kovarianz (Ziel: skalierte Einheitsmatrix), annualisiert."""
    X = np.asarray(r.dropna(), dtype=float)
    X = X - X.mean(axis=0)
    n, p = X.shape
    S = X.T @ X / n
    mu = np.trace(S) / p
    F = mu * np.eye(p)
    d2 = np.sum((S - F) ** 2) / p
    # sum_k ||x_k x_k' - S||^2 = sum_k ||x_k||^4 - n ||S||^2 (vektorisiert)
    b2 = min((np.sum(np.sum(X ** 2, axis=1) ** 2) - n * np.sum(S ** 2)) / (n ** 2 * p), d2)
    shrink = b2 / d2 if d2 > 0 else 1.0
    return pd.DataFrame((shrink * F + (1 - shrink) * S) * TRADING_DAYS, index=r.columns, columns=r.columns), float(shrink)


def risk_contributions(w, cov):
    w = np.asarray(w, float)
    port_var = float(w @ cov @ w)
    mrc = cov @ w
    return w * mrc / port_var if port_var > 0 else np.zeros_like(w)


# =============================================================== Optimierung
def _project_capped_simplex(v, cap):
    """Projektion auf {w: 0 <= w <= cap, sum w = 1} (Bisektion ueber den Verschiebungsparameter)."""
    lo, hi = v.min() - cap - 1, v.max() + 1
    for _ in range(45):
        tau = (lo + hi) / 2
        s = np.clip(v - tau, 0, cap).sum()
        lo, hi = (tau, hi) if s > 1 else (lo, tau)
    return np.clip(v - (lo + hi) / 2, 0, cap)


def _pgd(grad_fn, n, cap, sectors=None, sector_cap=None, iters=400, L=1.0, w0=None, tol=1e-8):
    """Beschleunigter projizierter Gradient (FISTA) mit Schrittweite 1/L; Sektorgrenzen als Straffunktion."""
    groups = [np.array([k for k, x in enumerate(sectors) if x == sec]) for sec in set(sectors)] if sectors and sector_cap else []
    pen = 100.0

    def grad(w):
        g = grad_fn(w)
        for idx in groups:
            excess = w[idx].sum() - sector_cap
            if excess > 0:
                g[idx] += 2 * pen * excess
        return g
    Ltot = L + (2 * pen * n if groups else 0)
    w = np.full(n, 1.0 / n) if w0 is None else np.asarray(w0, float)
    y, t = w.copy(), 1.0
    for _ in range(iters):
        w_new = _project_capped_simplex(y - grad(y) / Ltot, cap)
        t_new = (1 + math.sqrt(1 + 4 * t * t)) / 2
        y = w_new + (t - 1) / t_new * (w_new - w)
        if np.abs(w_new - w).max() < tol:
            w = w_new
            break
        w, t = w_new, t_new
    return w


def min_variance(cov, cap=0.10, sectors=None, sector_cap=None):
    C = np.asarray(cov, float)
    scale = 1 / max(np.abs(C).max(), 1e-12)
    L = 2 * scale * float(np.linalg.eigvalsh(C).max())
    return _pgd(lambda w: 2 * scale * C @ w, len(C), cap, sectors, sector_cap, iters=800, L=L)


def max_sharpe(mu, cov, rf=0.02, cap=0.10, sectors=None, sector_cap=None, n_points=25):
    """Effizienzlinie ueber min w'Cw - lam * mu'w fuer viele lam; Auswahl des Punkts mit hoechstem Sharpe."""
    C, m = np.asarray(cov, float), np.asarray(mu, float)
    scale = 1 / max(np.abs(C).max(), 1e-12)
    L = 2 * scale * float(np.linalg.eigvalsh(C).max())
    best, frontier = None, []
    w0 = None
    for lam in np.concatenate([[0], np.geomspace(0.02, 50, n_points)]):
        w = _pgd(lambda w: scale * (2 * C @ w - lam * m), len(C), cap, sectors, sector_cap, iters=400, L=L, w0=w0)
        w0 = w
        ret, vol = float(w @ m), math.sqrt(float(w @ C @ w))
        sr = (ret - rf) / vol if vol > 0 else -9
        frontier.append((vol, ret))
        if best is None or sr > best[0]:
            best = (sr, w)
    return best[1], frontier


def _single_linkage_order(corr):
    """Reihenfolge der Titel nach hierarchischer Clusterung (Distanz = sqrt((1 - Korrelation) / 2))."""
    D = np.sqrt(np.clip((1 - np.asarray(corr, float)) / 2, 0, None))
    clusters = {i: [i] for i in range(len(D))}
    dist = {(i, j): D[i, j] for i in clusters for j in clusters if i < j}
    nxt = len(D)
    while len(clusters) > 1:
        (a, b) = min(dist, key=dist.get)
        new = clusters.pop(a) + clusters.pop(b)
        dist = {k: v for k, v in dist.items() if a not in k and b not in k}
        for c, members in clusters.items():
            dist[(min(c, nxt), max(c, nxt))] = min(D[i, j] for i in new for j in members)
        clusters[nxt] = new
        nxt += 1
    return list(clusters.values())[0]


def cap_weights(w, cap):
    """Obergrenze je Titel: Ueberschuss anteilig auf die Titel unter der Grenze verteilen (iterativ)."""
    w = np.asarray(w, float).copy()
    for _ in range(50):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = w < cap - 1e-12
        if not under.any():
            break
        w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


def hrp(cov, corr):
    """Hierarchical Risk Parity: Gewichte nach inverser Cluster-Varianz, rekursiv halbiert."""
    C = np.asarray(cov, float)
    order = _single_linkage_order(corr)
    w = np.ones(len(C))

    def cvar(idx):
        sub = C[np.ix_(idx, idx)]
        iv = 1 / np.diag(sub)
        iv /= iv.sum()
        return float(iv @ sub @ iv)

    stack = [order]
    while stack:
        items = stack.pop()
        if len(items) < 2:
            continue
        half = len(items) // 2
        left, right = items[:half], items[half:]
        vl, vr = cvar(left), cvar(right)
        alpha = 1 - vl / (vl + vr)
        w[left] *= alpha
        w[right] *= 1 - alpha
        stack += [left, right]
    return w / w.sum()


def expected_returns(r, bench_r, rf=0.02, erp=0.05, shrink=0.5):
    """Erwartete Renditen: Mischung aus historischer Rendite (verrauscht) und CAPM (rf + Beta x Risikopraemie)."""
    hist = (1 + r.mean()) ** TRADING_DAYS - 1
    capm = {}
    b = bench_r.reindex(r.index)
    for c in r.columns:
        x = pd.concat([r[c], b], axis=1).dropna()
        beta = np.cov(x.iloc[:, 0], x.iloc[:, 1])[0, 1] / np.var(x.iloc[:, 1], ddof=1) if len(x) > 60 else 1.0
        capm[c] = rf + beta * erp
    capm = pd.Series(capm)
    return shrink * hist + (1 - shrink) * capm


# =============================================================== Gesamtanalyse
def analyze(portfolio, years_hist=3, rf=0.02, cap=0.10, sector_cap=0.35, prices=None, curr=None, fund=None):
    """Analyse des aktuellen Portfolios plus Optimierungsvorschlaege. Alle Betraege in EUR."""
    tickers = [p["ticker"] for p in portfolio]
    bench_t = list(BENCHMARKS.values())
    if prices is None:
        prices, curr = download_prices(tickers + bench_t)
    fund = fund if fund is not None else fundamentals(tickers)
    last = prices.iloc[-1]
    if all("shares" in p for p in portfolio):
        values = pd.Series({p["ticker"]: p["shares"] * last[p["ticker"]] for p in portfolio})
    else:
        wv = pd.Series({p["ticker"]: p.get("weight", 0.0) for p in portfolio})
        values = wv / wv.sum() * 100000.0  # fiktiver Wert 100.000 EUR
    w = values / values.sum()
    window = prices.loc[prices.index >= prices.index[-1] - pd.DateOffset(years=years_hist)]
    rets = _returns(window[tickers]).dropna()
    bench_r = _returns(window[BENCHMARKS["MSCI ACWI"]]).reindex(rets.index)
    port_r = (rets * w[tickers].values).sum(axis=1)
    cov, shrink = ledoit_wolf(rets)
    corr = rets.corr()
    rc = pd.Series(risk_contributions(w[tickers].values, cov.values), index=tickers)
    sectors = [fund[t]["sector"] for t in tickers]

    # Struktur
    def group(key):
        g = {}
        for t in tickers:
            g[fund[t][key]] = g.get(fund[t][key], 0) + float(w[t])
        return dict(sorted(g.items(), key=lambda x: -x[1]))
    structure = {"sector": group("sector"), "country": group("country"),
                 "currency": {c: float(sum(w[t] for t in tickers if (curr or {}).get(t) == c)) for c in set((curr or {}).values()) if c},
                 "hhi": float((w ** 2).sum()), "top5": float(w.sort_values(ascending=False).head(5).sum()),
                 "effective_n": float(1 / (w ** 2).sum())}

    # Positionen
    pos = []
    for t in tickers:
        r_t = rets[t]
        pos.append({"ticker": t, "name": fund[t]["name"], "sector": fund[t]["sector"], "weight": float(w[t]),
                    "value_eur": float(values[t]), "ret_1y": float(prices[t].iloc[-1] / prices[t].loc[prices.index >= prices.index[-1] - pd.DateOffset(years=1)].iloc[0] - 1),
                    "vol": ann_vol(r_t), "risk_contrib": float(rc[t]), "forward_pe": fund[t]["forward_pe"],
                    "peg": fund[t]["peg"], "revenue_growth": fund[t]["revenue_growth"], "upside": fund[t]["upside"]})

    # Performance und Risiko (3 Jahre, statische heutige Gewichte)
    stats = perf_stats(port_r, bench_r, rf)
    bench_stats = {name: perf_stats(_returns(window[t]).reindex(rets.index), None, rf) for name, t in BENCHMARKS.items()
                   if t in window and window[t].notna().sum() > 100}

    # Stresstests: heutiges Portfolio in historischen Krisen
    stress = []
    for name, a, b in STRESS:
        seg = prices.loc[a:b]
        if len(seg) < 5 or seg[tickers].iloc[0].isna().any():
            continue
        pr = float((seg[tickers].iloc[-1] / seg[tickers].iloc[0] - 1) @ w[tickers].values)
        br = float(seg[BENCHMARKS["MSCI ACWI"]].iloc[-1] / seg[BENCHMARKS["MSCI ACWI"]].iloc[0] - 1)
        stress.append({"scenario": name, "from": a, "to": b, "portfolio": pr, "benchmark": br})

    # Optimierung
    mu = expected_returns(rets, bench_r, rf)
    opt = {"current": w[tickers].values}
    opt["min_variance"] = min_variance(cov.values, cap, sectors, sector_cap)
    opt["max_sharpe"], frontier = max_sharpe(mu.values, cov.values, rf, cap, sectors, sector_cap)
    opt["hrp"] = cap_weights(hrp(cov.values, corr.values), cap)
    opt["equal_weight"] = np.full(len(tickers), 1 / len(tickers))
    opt_stats = {}
    for k, ww in opt.items():
        vol = math.sqrt(float(ww @ cov.values @ ww))
        er = float(ww @ mu.values)
        opt_stats[k] = {"exp_return": er, "vol": vol, "sharpe": (er - rf) / vol if vol else None,
                        "max_weight": float(ww.max()), "turnover": float(np.abs(ww - w[tickers].values).sum() / 2)}
    return {"date": date.today().isoformat(), "tickers": tickers, "weights": w, "values": values, "positions": pos,
            "structure": structure, "stats": stats, "bench_stats": bench_stats, "stress": stress, "cov_shrink": shrink,
            "corr": corr, "mu": mu, "opt": opt, "opt_stats": opt_stats, "frontier": frontier, "rf": rf, "cap": cap,
            "sector_cap": sector_cap, "port_curve": (1 + port_r).cumprod(),
            "bench_curve": (1 + bench_r.fillna(0)).cumprod(), "prices": prices, "fund": fund, "years_hist": years_hist}


# =============================================================== Backtest (walk-forward)
def backtest(prices, tickers, current_w, lookback_years=3, rebalance="QE", rf=0.02, cap=0.10, cost_bps=10,
             sectors=None, sector_cap=None):
    """Walk-forward: zu jedem Stichtag nur mit Daten bis dahin optimieren, dann bis zum naechsten Stichtag halten.
    Titel mit zu kurzer Kurshistorie (z. B. junge Boersengaenge) werden ausgelassen, die Gewichte neu normiert."""
    need = prices.index[-1] - pd.DateOffset(years=lookback_years + 2)
    keep = [i for i, t in enumerate(tickers) if prices[t].first_valid_index() is not None
            and prices[t].first_valid_index() <= need]
    excluded = [t for i, t in enumerate(tickers) if i not in keep]
    tickers = [tickers[i] for i in keep]
    current_w = np.asarray(current_w, float)[keep]
    current_w = current_w / current_w.sum()
    if sectors is not None:
        sectors = [sectors[i] for i in keep]
    if len(tickers) < 3:
        return {"curves": {}, "stats": {}, "start": None, "end": None, "rebalances": 0, "lookback_years": lookback_years,
                "cost_bps": cost_bps, "excluded": excluded}
    px = prices[tickers].dropna()
    r = px.pct_change().dropna()
    bench = prices[BENCHMARKS["MSCI ACWI"]].reindex(r.index).pct_change().fillna(0)
    start = r.index[0] + pd.DateOffset(years=lookback_years)
    freq = "Q" if rebalance.startswith("Q") else "M"
    # letzter tatsaechlicher Handelstag je Quartal (nicht das Kalenderende, das in der Zukunft liegen kann)
    dates = [g.index[-1] for _, g in r.groupby(r.index.to_period(freq)) if g.index[-1] >= start]
    if r.index[-1] not in dates:
        dates.append(r.index[-1])
    strategies = {"Current weights (rebalanced)": None, "Equal weight": None, "Min variance": None, "Max Sharpe": None, "HRP": None}
    daily = {k: [] for k in strategies}
    turnover = {k: 0.0 for k in strategies}
    prev = {k: None for k in strategies}
    for i, d in enumerate(dates[:-1]):
        hist = r.loc[(r.index > d - pd.DateOffset(years=lookback_years)) & (r.index <= d)]
        cov, _ = ledoit_wolf(hist)
        mu = expected_returns(hist, bench.reindex(hist.index), rf)
        ws = {"Current weights (rebalanced)": np.asarray(current_w, float), "Equal weight": np.full(len(tickers), 1 / len(tickers)),
              "Min variance": min_variance(cov.values, cap, sectors, sector_cap),
              "Max Sharpe": max_sharpe(mu.values, cov.values, rf, cap, sectors, sector_cap, n_points=12)[0],
              "HRP": cap_weights(hrp(cov.values, hist.corr().values), cap)}
        period = r.loc[(r.index > d) & (r.index <= dates[i + 1])]
        for k, ww in ws.items():
            tc = 0.0 if prev[k] is None else np.abs(ww - prev[k]).sum() * cost_bps / 1e4
            turnover[k] += 0.0 if prev[k] is None else np.abs(ww - prev[k]).sum() / 2
            prev[k] = ww
            pr = (period * ww).sum(axis=1)
            if len(pr):
                pr.iloc[0] -= tc
            daily[k].append(pr)
    curves, stats = {}, {}
    bench_r = bench.loc[(bench.index > dates[0]) & (bench.index <= dates[-1])]
    for k in strategies:
        if not daily[k]:
            continue
        s = pd.concat(daily[k])
        curves[k] = (1 + s).cumprod()
        stats[k] = perf_stats(s, bench_r, rf)
        stats[k]["turnover_pa"] = turnover[k] / max(len(dates) - 1, 1) * {"QE": 4, "ME": 12}.get(rebalance, 4)
    curves["MSCI ACWI (EUR)"] = (1 + bench_r).cumprod()
    stats["MSCI ACWI (EUR)"] = perf_stats(bench_r, None, rf)
    return {"curves": curves, "stats": stats, "start": str(dates[0].date()) if dates else None,
            "end": str(dates[-1].date()) if dates else None, "rebalances": max(len(dates) - 1, 0),
            "lookback_years": lookback_years, "cost_bps": cost_bps, "excluded": excluded}


# =============================================================== Text fuer den Agenten
def _p(v, d=1):
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:.{d}f}%"


def _x(v, d=2):
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.{d}f}"


OPT_NAMES = {"current": "Current", "min_variance": "Min variance", "max_sharpe": "Max Sharpe", "hrp": "HRP",
             "equal_weight": "Equal weight"}


def analysis_text(a):
    s, st = a["structure"], a["stats"]
    lines = [f"PORTFOLIO ANALYSIS (Yahoo Finance prices in EUR, {a['years_hist']} years of daily data, retrieved {a['date']}; cite as [1]):",
             f"- {len(a['tickers'])} positions, total value EUR {a['values'].sum():,.0f}; top 5 = {_p(s['top5'])}; "
             f"effective number of positions {s['effective_n']:.1f} (HHI {s['hhi']:.3f}).",
             "- Sectors: " + ", ".join(f"{k} {_p(v)}" for k, v in s["sector"].items()),
             "- Countries: " + ", ".join(f"{k} {_p(v)}" for k, v in s["country"].items()),
             "- Currencies: " + ", ".join(f"{k} {_p(v)}" for k, v in s["currency"].items()),
             f"- Performance with today's weights over {a['years_hist']} years: CAGR {_p(st.get('cagr'))} vs MSCI ACWI "
             f"{_p(st.get('bench_cagr'))}; volatility {_p(st.get('vol'))}; Sharpe {_x(st.get('sharpe'))}; Sortino "
             f"{_x(st.get('sortino'))}; max drawdown {_p(st.get('max_dd'))}; beta {_x(st.get('beta'))}; tracking error "
             f"{_p(st.get('tracking_error'))}; information ratio {_x(st.get('info_ratio'))}; 1-day VaR 95% "
             f"{_p(st.get('var95_1d'), 2)}, CVaR {_p(st.get('cvar95_1d'), 2)} (risk-free rate assumed {_p(a['rf'])})."]
    for name, b in a["bench_stats"].items():
        lines.append(f"- Benchmark {name}: CAGR {_p(b.get('cagr'))}, volatility {_p(b.get('vol'))}, max drawdown {_p(b.get('max_dd'))}.")
    lines.append("POSITIONS (weight, 1-year return, volatility, share of portfolio risk, forward P/E, PEG, revenue growth, "
                 "upside to consensus target):")
    for p in sorted(a["positions"], key=lambda x: -x["weight"]):
        lines.append(f"- {p['ticker']} ({p['name']}, {p['sector']}): {_p(p['weight'])}, {_p(p['ret_1y'])}, {_p(p['vol'])}, "
                     f"risk {_p(p['risk_contrib'])}, P/E {_x(p['forward_pe'], 1)}, PEG {_x(p['peg'])}, growth "
                     f"{_p(p['revenue_growth'])}, upside {_p(p['upside'])}")
    if a["stress"]:
        lines.append("STRESS TESTS (today's weights in past crises): " + "; ".join(
            f"{x['scenario']} ({x['from']} to {x['to']}): portfolio {_p(x['portfolio'])} vs MSCI ACWI {_p(x['benchmark'])}"
            for x in a["stress"]))
    lines.append(f"OPTIMIZATION (long-only, max {_p(a['cap'], 0)} per position, max {_p(a['sector_cap'], 0)} per sector; "
                 f"Ledoit-Wolf covariance, shrinkage {a['cov_shrink']:.2f}; expected returns = 50% historical + 50% CAPM; "
                 "these are model outputs, sensitive to estimation error):")
    for k, v in a["opt_stats"].items():
        top = sorted(zip(a["tickers"], a["opt"][k]), key=lambda x: -x[1])[:5]
        lines.append(f"- {OPT_NAMES[k]}: expected return {_p(v['exp_return'])}, volatility {_p(v['vol'])}, Sharpe "
                     f"{_x(v['sharpe'])}, largest weight {_p(v['max_weight'])}, turnover vs current {_p(v['turnover'])}; "
                     "top weights " + ", ".join(f"{t} {_p(x)}" for t, x in top))
    return "\n".join(lines)


def backtest_text(bt):
    if not bt.get("stats"):
        return "Backtest not available (too little common price history)."
    lines = [f"WALK-FORWARD BACKTEST ({bt['start']} to {bt['end']}, {bt['rebalances']} quarterly rebalancings, "
             f"{bt['lookback_years']}-year lookback, {bt['cost_bps']} bp trading costs; EUR; cite as [1]). Each strategy is "
             "optimized only with data available at each rebalancing date:"]
    for k, s in bt["stats"].items():
        lines.append(f"- {k}: CAGR {_p(s.get('cagr'))}, volatility {_p(s.get('vol'))}, Sharpe {_x(s.get('sharpe'))}, "
                     f"max drawdown {_p(s.get('max_dd'))}" + (f", turnover {_p(s.get('turnover_pa'), 0)} p.a." if "turnover_pa" in s else ""))
    if bt.get("excluded"):
        lines.append(f"Excluded for lack of price history: {', '.join(bt['excluded'])} (weights of the rest rescaled).")
    lines.append("Note: the backtest uses today's holdings, so it suffers from hindsight in the stock selection; it compares "
                 "weighting methods, not stock picking.")
    return "\n".join(lines)
