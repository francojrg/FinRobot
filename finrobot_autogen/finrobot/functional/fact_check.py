"""
Automatischer Faktencheck fuer generierte Reports (eigene Ergaenzung, nicht Teil von FinRobot).

Idee: Jede Zahl im Report-Text wird gegen die Quellen geprueft, die der Agent tatsaechlich
bekommen hat: [1] 10-K-Abschnitte (Item 1, 1A, 7), [2] Yahoo-Finance-Daten des Unternehmens,
[4] Kennzahlen der Peers. Zusaetzlich wird geprueft, ob Firmennamen vor einem Ticker in
Klammern zum Ticker passen (z. B. "Luna Innovations (LUNR)" -> falsch, LUNR = Intuitive Machines).

Wichtig fuer die Interpretation: "nicht gefunden" heisst nicht automatisch "falsch". Es kann
sich auch um eine abgeleitete Zahl handeln (z. B. selbst berechnete Quote). Solche Zahlen
muessen manuell geprueft werden.
"""

import re
import json

MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
STOP = {"inc", "inc.", "corp", "corp.", "corporation", "company", "co", "co.", "ltd", "plc", "holdings",
        "group", "the", "and", "&", "technologies", "technology", "labs", "lab", "s.a.", "ag", "se", "nv"}


def _to_float(s):
    return float(s.replace(",", ""))


def _decimals(s):
    s = s.replace(",", "")
    return len(s.split(".")[1]) if "." in s else 0


# ------------------------------------------------------------------ Quellen
class SourceIndex:
    """Sammelt Zahlen aus einer Quelle in normalisierten Mengen."""

    def __init__(self, label):
        self.label = label
        self.money_mn = []   # Geldbetraege in Mio.
        self.pct = []        # Prozentwerte (Betrag)
        self.plain = []      # sonstige Zahlen (Betrag), inkl. skalierter Varianten

    def add_text(self, text):
        text = str(text)
        for m in re.finditer(rf"(\(?)(\$?)\s?({NUM})\s?(\)?)\s?(%|million|billion|thousand)?", text, re.I):
            raw = _to_float(m.group(3))
            unit = (m.group(5) or "").lower()
            if unit == "%":
                self.pct.append(abs(raw))
            elif unit == "million":
                self.money_mn.append(abs(raw)); self.plain.append(abs(raw))
            elif unit == "billion":
                self.money_mn.append(abs(raw) * 1000); self.plain.append(abs(raw))
            elif unit == "thousand":
                self.money_mn.append(abs(raw) / 1000); self.plain.append(abs(raw))
            else:
                self.plain.append(abs(raw))
                if raw >= 1000:  # Tabellen im 10-K sind meist in Tausend USD
                    self.money_mn.append(abs(raw) / 1000)
                self.money_mn.append(abs(raw))  # bereits in Mio. (z. B. Kennzahlentabelle)

    def add_raw_usd(self, value):
        """Rohwerte in USD (z. B. Yahoo-Abschluesse) -> Mio."""
        try:
            v = abs(float(value))
        except (TypeError, ValueError):
            return
        if v != v:  # NaN
            return
        self.money_mn.append(v / 1e6)
        self.plain.append(v)

    def add_value(self, value):
        """Einzelwert aus Tabellen ("34.4%", "-155", 23.88)."""
        if value is None:
            return
        s = str(value).strip()
        if s.endswith("%"):
            try:
                self.pct.append(abs(float(s[:-1])))
            except ValueError:
                pass
            return
        try:
            v = abs(float(s.replace(",", "")))
        except ValueError:
            return
        self.money_mn.append(v)
        self.plain.append(v)


def _close(claim, candidates, tol_abs, tol_rel=0.0):
    tol = max(tol_abs, tol_rel * abs(claim))
    return any(abs(abs(claim) - c) <= tol + 1e-9 for c in candidates)


# ------------------------------------------------------------------ Behauptungen
def extract_claims(text):
    """Findet Zahlenangaben im Report-Text und klassifiziert sie."""
    claims = []
    text = re.sub(r"\[\d+\](\[\d+\])*", " ", str(text))  # Zitierungen entfernen
    taken = []

    def overlaps(a, b):
        return any(not (b <= s or a >= e) for s, e in taken)

    patterns = [
        ("money", rf"-?\$\s?\(?({NUM})\)?\s?(million|billion|thousand|mn|bn|m|b|k)?(?![a-z])"),
        ("pct", rf"(-?(?:{NUM}))\s?%"),
        ("multiple", rf"\b({NUM})\s?x\b"),
        ("plain", rf"(?<![\w.])(-?(?:{NUM}))(?![\w.%])"),
    ]
    for kind, pat in patterns:
        for m in re.finditer(pat, text, re.I):
            if overlaps(m.start(), m.end()):
                continue
            num = m.group(1)
            val = _to_float(num.lstrip("-"))
            a0, b0 = max(0, m.start() - 70), min(len(text), m.end() + 50)
            while a0 > 0 and text[a0 - 1] not in " \n":
                a0 += 1 if a0 < m.start() else 0
                break
            ctx = text[a0:b0]
            ctx = (ctx.split(" ", 1)[1] if a0 > 0 and " " in ctx[:20] else ctx)
            ctx = (ctx.rsplit(" ", 1)[0] if b0 < len(text) and " " in ctx[-20:] else ctx)
            ctx = ("..." if a0 > 0 else "") + ctx.replace("\n", " ").strip() + ("..." if b0 < len(text) else "")
            if kind == "plain":
                if num.isdigit() and 1990 <= int(num) <= 2040:
                    continue  # Jahreszahl
                around = text[max(0, m.start() - 12): m.end() + 12]
                if re.search(MONTHS, around) and val <= 31:
                    continue  # Tagesdatum
                if val < 2 and "." not in num:
                    continue  # "1", "0" usw. (Aufzaehlungen)
                if re.match(r"\s?-?(week|day|month|year|quarter)\b", text[m.end():m.end() + 9], re.I):
                    continue  # Zeitraum ("52-week range", "12-month target")
            unit = (m.group(2) or "").lower() if kind == "money" and m.lastindex and m.lastindex >= 2 else ""
            unit = {"mn": "million", "m": "million", "bn": "billion", "b": "billion", "k": "thousand"}.get(unit, unit)
            mn = None
            if kind == "money":
                mn = val * {"million": 1, "billion": 1000, "thousand": 0.001}.get(unit, 0) if unit else None
            claims.append({"kind": kind, "text": m.group(0).strip(), "value": val, "unit": unit,
                           "money_mn": mn, "decimals": _decimals(num), "context": ctx})
            taken.append((m.start(), m.end()))
    return claims


def check_claim(c, sources):
    dec = c["decimals"]
    rnd = 0.5 * 10 ** (-dec)  # Rundungstoleranz gemaess angegebener Stellen
    for src in sources:
        if c["kind"] == "money":
            if c["money_mn"] is not None:
                if _close(c["money_mn"], src.money_mn, rnd * {"million": 1, "billion": 1000, "thousand": 0.001}.get(c["unit"], 1), 0.002):
                    return src.label
            elif _close(c["value"], src.plain, rnd, 0.002):  # z. B. Kurs "$93.15"
                return src.label
        elif c["kind"] == "pct":
            if _close(c["value"], src.pct, rnd + 0.05):
                return src.label
        else:
            if _close(c["value"], src.plain, rnd, 0.002) or _close(c["value"], src.money_mn, rnd, 0.002):
                return src.label
    return None


# ------------------------------------------------------------------ Namen
def check_names(text, ticker_names):
    """Prueft 'Name (TICKER)'-Muster gegen die bekannten Firmennamen."""
    issues = []
    for m in re.finditer(r"((?:[A-Z][\w&.\-']*\s){1,4})\(([A-Z]{1,5})\)", str(text)):
        name, tic = m.group(1).strip(), m.group(2)
        if tic not in ticker_names:
            continue
        official = ticker_names[tic] or ""
        a = {w.lower().strip(",.") for w in name.split()} - STOP
        b = {w.lower().strip(",.") for w in official.split()} - STOP
        if a and b and not (a & b):
            issues.append({"ticker": tic, "written": name, "official": official,
                           "context": text[max(0, m.start() - 40): m.end() + 40]})
    return issues


# ------------------------------------------------------------------ Hauptfunktion
def run_fact_check(sections, sources, ticker_names=None):
    """sections: Liste (Titel, Text); sources: Liste SourceIndex; ticker_names: {Ticker: Name}."""
    results, by_kind = [], {}
    for title, text in sections:
        for c in extract_claims(text):
            c["section"] = title
            c["source"] = check_claim(c, sources)
            results.append(c)
            k = by_kind.setdefault(c["kind"], [0, 0])
            k[0] += 1
            k[1] += c["source"] is not None
    names = []
    if ticker_names:
        for title, text in sections:
            for i in check_names(text, ticker_names):
                i["section"] = title
                names.append(i)
    total = len(results)
    matched = sum(r["source"] is not None for r in results)
    return {
        "total_claims": total,
        "matched": matched,
        "match_rate": round(matched / total, 3) if total else None,
        "by_kind": {k: {"total": v[0], "matched": v[1]} for k, v in by_kind.items()},
        "by_source": {s.label: sum(r["source"] == s.label for r in results) for s in sources},
        "unmatched": [r for r in results if r["source"] is None],
        "name_issues": names,
        "claims": results,
    }


def save_json(result, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
