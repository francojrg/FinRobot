"""
Automatischer Faktencheck fuer generierte Reports (eigene Ergaenzung, nicht Teil von FinRobot).

Idee: Jede Zahl im Report-Text wird gegen die Quellen geprueft, die der Agent tatsaechlich
bekommen hat: [1] 10-K-Abschnitte (Item 1, 1A, 7), [2] Yahoo-Finance-Daten des Unternehmens,
[4] Kennzahlen der Peers. Zusaetzlich wird geprueft, ob Firmennamen vor einem Ticker in
Klammern zum Ticker passen (z. B. "Luna Innovations (LUNR)" -> falsch, LUNR = Intuitive Machines).

Wichtig fuer die Interpretation: "nicht gefunden" heisst nicht automatisch "falsch". Es kann
sich auch um eine abgeleitete Zahl handeln (z. B. selbst berechnete Quote). Solche Zahlen
muessen manuell geprueft werden.

Herkunft: Jede gefundene Zahl bekommt "evidence" = {source, origin, snippet}: die Quelle, optional die genauere
Herkunft (z. B. "GOOG - Earnings review 2026-11-24") und die Textstelle, an der die Zahl in der Quelle steht.
Abkuerzungen in den Quellen ("$45.8bn", "$120mn") werden wie im Report-Text erkannt.

Kontextabgleich (25.11.2026): Eine Zahl allein ist schwacher Beleg, weil kleine Zahlen wie "12 %" in langen Quellen fast
immer irgendwo vorkommen. Fuer Prozentwerte und sonstige Zahlen (CONTEXT_KINDS) prueft der Check deshalb zusaetzlich den
Kontext: Ein seltenes Wort aus dem Satz im Report (z. B. "cloud", "value-added") oder mindestens zwei gemeinsame Woerter
stehen auch in der Naehe der Zahl in der Quelle. "Selten" wird je Quelle gemessen (Woerter neben fast jeder Zahl wie der
Firmenname oder "year" zaehlen nicht), Synonyme (sales/revenue, profit/income ...) werden zusammengefasst.
Ergebnis je Zahl: source (Zahl gefunden, wie bisher) und context_ok (True = Zahl und Kontext passen, False = nur die Zahl
steht irgendwo in den Quellen, None = Art ohne Kontextpruefung, z. B. Geldbetraege). Die Trefferquote match_rate bleibt
der reine Zahlenabgleich (Selbstkorrektur der Agenten unveraendert); context_match_rate ist die strengere Quote.
"""

import math
import re
import json

MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
UNIT_SRC = r"(?:(%|trillion|million|billion|thousand|tn|mn|bn|m|b|k)(?![a-z]))"
UNIT_NORM = {"mn": "million", "m": "million", "bn": "billion", "b": "billion", "k": "thousand", "tn": "trillion"}
SCALE_MN = {"million": 1, "billion": 1000, "thousand": 0.001, "trillion": 1_000_000}
CURRENCY = r"(?:US\$|NT\$|\$|€|EUR\s?|USD\s?|TWD\s?|NT\s?)"   # Geldbetraege auch in EUR/TWD (20-F-Emittenten)
STOP = {"inc", "inc.", "corp", "corp.", "corporation", "company", "co", "co.", "ltd", "plc", "holdings",
        "group", "the", "and", "&", "technologies", "technology", "labs", "lab", "s.a.", "ag", "se", "nv"}


# ------------------------------------------------------------------ Kontext
CONTEXT_KINDS = ("pct", "plain", "multiple")   # Arten, bei denen der Kontext passen muss
CTX_WORDS = 8                                 # Woerter links/rechts der Zahl in der Quelle
CTX_MIN_IDF = 1.4                              # Wort darf hoechstens neben ~20 % aller Zahlen einer Quelle stehen
CTX_RARE_IDF = 2.2                             # Einzelwort reicht, wenn es neben hoechstens ~10 % der Zahlen steht
CTX_PAIR_IDF = 1.8                             # Kennzahlwort plus Veraenderungswort ("revenue ... up 15%")
CTX_STOP = set("""a an the of in on at to for from by with and or but as is are was were be been being this that these
those it its their our we they he she you which who whom whose than then there here into over under about after before
during while also not no nor so such per vs versus via up down out off more most less least very can could would should
may might will shall has have had do does did each other some any all both either neither only own same just year years
yoy fy fiscal quarter quarters quarterly month months period periods ended ending end compared compare comparison
approximately approx roughly around nearly about billion billions million millions thousand thousands percent percentage
pct usd dollar dollars eur basis points bps table start total totals note notes see item items page including include
includes included primarily mainly mostly respectively prior previous current last next first second third fourth
q1 q2 q3 q4 h1 h2 company companies business name dtype object float int nan""".split())
CTX_SYN = {"us": "united", "u.s": "united", "domestic": "united", "sales": "revenue", "revenues": "revenue", "turnover": "revenue", "topline": "revenue",
           "profit": "income", "profits": "income", "earnings": "income", "earning": "income",
           "eps": "pershare", "share": "pershare", "shares": "pershare", "diluted": "pershare",
           "fcf": "cashflow", "cash": "cashflow", "flow": "cashflow", "flows": "cashflow",
           "capex": "capital", "expenditures": "capital", "expenditure": "capital",
           "margins": "margin", "opex": "operating", "operating": "operating", "ebit": "operating",
           "employees": "headcount", "employee": "headcount", "headcount": "headcount",
           "grew": "change", "growth": "change", "grow": "change", "increase": "change", "increased": "change",
           "increases": "change", "rose": "change", "rise": "change", "up": "change", "decline": "change",
           "declined": "change", "decrease": "change", "decreased": "change", "fell": "change", "down": "change",
           "change": "change", "changes": "change", "higher": "change", "lower": "change"}
WEAK = {"change"}                              # zaehlt nie allein als Kontext


def _stem(w):
    for suf in ("ies", "es", "s"):
        if len(w) > 4 and w.endswith(suf) and not w.endswith("ss"):
            return w[: -len(suf)] + ("y" if suf == "ies" else "")
    return w


def ctx_terms(text):
    """Normalisierte Inhaltswoerter eines Textstuecks (ohne Zahlen, Stoppwoerter, Einheiten)."""
    out = set()
    for w in re.findall(r"[A-Za-z][A-Za-z&\-]{1,}", str(text)):
        w = w.lower().strip("-")
        if w in CTX_SYN:
            out.add(CTX_SYN[w])
            continue
        if len(w) < 3 or w in CTX_STOP:
            continue
        w = _stem(w)
        out.add(CTX_SYN.get(w, w))
    return out


def claim_terms(c):
    """Kontextwoerter einer Behauptung: Satz um die Zahl (aus c['context']), ohne die Zahl selbst."""
    ctx = str(c.get("context") or "")
    t = str(c.get("text") or "")
    i = ctx.find(t) if t else -1
    if i >= 0:                                 # nur der Satz, in dem die Zahl steht
        lo = max(ctx.rfind(". ", 0, i), ctx.rfind("; ", 0, i))
        hi_c = [x for x in (ctx.find(". ", i + len(t)), ctx.find("; ", i + len(t))) if x >= 0]
        ctx = ctx[lo + 1 if lo >= 0 else 0: min(hi_c) if hi_c else len(ctx)]
    return ctx_terms(ctx)


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
        self._ev = []        # (Art, Wert, Text-Nr., Start, Ende, Herkunft, Notiz) fuer die Herkunftsangabe
        self._texts = []
        self._terms = {}     # Index in _ev -> Kontextwoerter (lazy)
        self._idf = None

    def _note(self, kind, v, tid=None, a=0, b=0, origin=None, note=None):
        self._ev.append((kind, v, tid, a, b, origin, note))
        self._idf = None

    def window_terms(self, i):
        """Kontextwoerter um Fundstelle i: CTX_WORDS Woerter links/rechts in derselben Zeile (Tabellenzeile inkl.)."""
        if i in self._terms:
            return self._terms[i]
        kind, v, tid, a, b, origin, note = self._ev[i]
        if tid is None:
            terms = ctx_terms(note or "")
        else:
            t = self._texts[tid]
            wre = r"[A-Za-z][A-Za-z&\-]+"
            # Absatz/Tabellenblock um die Zahl (Grenze: Leerzeile); Tabellen ohne Beschriftung in derselben Zeile
            # (z. B. "Gross Margin:" mehrere Zeilen darueber) werden so mit ihrer Ueberschrift verbunden.
            blocks_l = re.split(r"\n\s*\n", t[max(0, a - 600):a])
            left = re.findall(wre, blocks_l[-1])
            if len(left) < 2 and len(blocks_l) > 1:     # Beschriftung steht im Block davor (Zeile "Other Americas")
                left = re.findall(wre, blocks_l[-2]) + left
            right = re.findall(wre, re.split(r"\n\s*\n", t[b:b + 300])[0])
            terms = ctx_terms(" ".join(left[-CTX_WORDS:] + right[:CTX_WORDS // 2]))
        self._terms[i] = terms
        return terms

    def idf(self):
        """Seltenheit je Wort ueber alle Zahlen-Fundstellen dieser Quelle (log N/df)."""
        if self._idf is None:
            df, n = {}, 0
            for i, e in enumerate(self._ev):
                if e[0] == "mn" and e[2] is not None:
                    continue                    # doppelte Eintraege derselben Stelle nicht zaehlen
                n += 1
                for w in self.window_terms(i):
                    df[w] = df.get(w, 0) + 1
            n_eff = max(n, 200)                 # kleine Quellen (Chat, Brief): gemeinsame Woerter zaehlen trotzdem
            self._idf = {w: math.log((n_eff + 1) / (d + 0.5)) for w, d in df.items()}
            self._idf_n = n
        return self._idf

    def context_match(self, c, terms=None):
        """Beste Fundstelle mit passendem Zahlenwert UND passendem Kontext: (Index, gemeinsame Woerter) oder None."""
        terms = claim_terms(c) if terms is None else terms
        if not terms:
            return None
        kinds, target, tol = _targets(c)
        idf = self.idf()
        best = None
        for i, (kind, v, tid, a, b, origin, note) in enumerate(self._ev):
            if kind not in kinds or abs(abs(target) - v) > tol + 1e-9:
                continue
            both = self.window_terms(i) & terms
            common = both - WEAK
            strong = [w for w in common if idf.get(w, 0) >= CTX_MIN_IDF]
            # ein haeufiges Kennzahlwort allein ("revenue", "net") reicht nicht: entweder ein seltenes Wort
            # (z. B. "cloud", "value-added") oder zwei gemeinsame Woerter (auch "revenue" + Veraenderung: "up 15%")
            top = max((idf.get(w, 0) for w in strong), default=0)
            if strong and (len(strong) >= 2 or top >= CTX_RARE_IDF or (both & WEAK and top >= CTX_PAIR_IDF)):
                score = sum(idf.get(w, 0) for w in strong)
                if best is None or score > best[0]:
                    best = (score, i, sorted(strong, key=lambda w: -idf.get(w, 0)))
        return (best[1], best[2]) if best else None

    def add_text(self, text, origin=None):
        text = str(text)
        self._texts.append(text)
        tid = len(self._texts) - 1
        for m in re.finditer(rf"(\(?)(\$?)\s?({NUM})\s?(\)?)\s?{UNIT_SRC}?", text, re.I):
            raw = abs(_to_float(m.group(3)))
            unit = UNIT_NORM.get((m.group(5) or "").lower(), (m.group(5) or "").lower())
            a, b = m.start(3), m.end()
            if unit == "%":
                self.pct.append(raw); self._note("pct", raw, tid, a, b, origin)
                continue
            if unit in ("million", "billion", "thousand", "trillion"):
                mn = raw * SCALE_MN[unit]
                self.money_mn.append(mn); self.plain.append(raw)
                self._note("mn", mn, tid, a, b, origin); self._note("plain", raw, tid, a, b, origin)
                continue
            self.plain.append(raw); self._note("plain", raw, tid, a, b, origin)
            if raw >= 1000:  # Tabellen im 10-K sind meist in Tausend USD
                self.money_mn.append(raw / 1000); self._note("mn", raw / 1000, tid, a, b, origin)
            self.money_mn.append(raw); self._note("mn", raw, tid, a, b, origin)  # bereits in Mio. (Kennzahlentabelle)

    def add_raw_usd(self, value, note=None):
        """Rohwerte in USD (z. B. Yahoo-Abschluesse) -> Mio."""
        try:
            v = abs(float(value))
        except (TypeError, ValueError):
            return
        if v != v:  # NaN
            return
        self.money_mn.append(v / 1e6)
        self.plain.append(v)
        self._note("mn", v / 1e6, note=note or f"{v:,.0f} USD"); self._note("plain", v, note=note or f"{v:,.0f} USD")

    def add_value(self, value, note=None):
        """Einzelwert aus Tabellen ("34.4%", "-155", 23.88)."""
        if value is None:
            return
        s = str(value).strip()
        if s.endswith("%"):
            try:
                self.pct.append(abs(float(s[:-1]))); self._note("pct", abs(float(s[:-1])), note=note or s)
            except ValueError:
                pass
            return
        try:
            v = abs(float(s.replace(",", "")))
        except ValueError:
            return
        self.money_mn.append(v)
        self.plain.append(v)
        self._note("mn", v, note=note or s); self._note("plain", v, note=note or s)

    def _snippet(self, tid, a, b, width=110):
        t = self._texts[tid]
        lo, hi = max(0, a - width), min(len(t), b + width)
        lo = t.rfind("\n", lo, a) + 1 if t.rfind("\n", lo, a) >= 0 else lo  # nicht ueber Zeilengrenzen
        nl = t.find("\n", b, hi)
        hi = nl if nl >= 0 else hi
        s = t[lo:hi]
        if lo > 0 and t[lo - 1] not in "\n" and " " in s[:25]:
            s = s.split(" ", 1)[1]
        if hi < len(t) and t[hi] not in "\n" and " " in s[-25:]:
            s = s.rsplit(" ", 1)[0]
        s = " ".join(s.replace("##TABLE_START", " ").replace("##TABLE_END", " ").split())
        return ("..." if lo > 0 and t[lo - 1] != "\n" else "") + s + ("..." if hi < len(t) and t[hi] != "\n" else "")

    def evidence(self, c):
        """Textstelle der besten Uebereinstimmung fuer eine gefundene Behauptung (oder None).
        Mit passendem Kontext (siehe context_match) wird diese Stelle bevorzugt und die gemeinsamen Woerter angegeben."""
        cm = self.context_match(c) if c.get("context_ok") else None
        if cm:
            i, words = cm
            kind, v, tid, a, b, origin, note = self._ev[i]
            return {"source": self.label, "origin": origin, "context_words": words,
                    "hl": self._texts[tid][a:b].strip() if tid is not None else None,
                    "snippet": self._snippet(tid, a, b) if tid is not None else (note or "")}
        kinds, target, tol = _targets(c)
        best = None
        for kind, v, tid, a, b, origin, note in self._ev:
            if kind not in kinds:
                continue
            d = abs(abs(target) - v)
            if d <= tol + 1e-9 and (best is None or d < best[0]):
                best = (d, tid, a, b, origin, note)
        if best is None:
            return None
        _, tid, a, b, origin, note = best
        return {"source": self.label, "origin": origin,
                "hl": self._texts[tid][a:b].strip() if tid is not None else None,
                "snippet": self._snippet(tid, a, b) if tid is not None else (note or "")}


def _close(claim, candidates, tol_abs, tol_rel=0.0):
    tol = max(tol_abs, tol_rel * abs(claim))
    return any(abs(abs(claim) - c) <= tol + 1e-9 for c in candidates)


# ------------------------------------------------------------------ Behauptungen
def extract_claims(text):
    """Findet Zahlenangaben im Report-Text und klassifiziert sie."""
    claims = []
    text = re.sub(r"\[\d+\](\[\d+\])*", " ", str(text))  # Zitierungen entfernen
    # Keine Zahlenangaben: ISO-Datum (2026-11-24) und Formularnamen (10-K, 10-Q, 8-K, 20-F)
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", lambda m: " " * len(m.group()), text)
    text = re.sub(r"\b(?:10-K|10-Q|8-K|20-F|6-K|S-1)\b", lambda m: " " * len(m.group()), text, flags=re.I)
    text = re.sub(r"\b(?:Items?|Exhibits?|Ex\.)\s+\d+(?:\.\d+)?[A-Z]?\b", lambda m: " " * len(m.group()), text, flags=re.I)
    taken = []

    def overlaps(a, b):
        return any(not (b <= s or a >= e) for s, e in taken)

    patterns = [
        ("money", rf"-?{CURRENCY}\s?\(?({NUM})\)?\s?(trillion|million|billion|thousand|tn|mn|bn|m|b|k)?(?![a-z])"),
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
            unit = UNIT_NORM.get(unit, unit)
            mn = None
            if kind == "money":
                mn = val * SCALE_MN.get(unit, 0) if unit else None
            claims.append({"kind": kind, "text": m.group(0).strip(), "value": val, "unit": unit,
                           "money_mn": mn, "decimals": _decimals(num), "context": ctx})
            taken.append((m.start(), m.end()))
    return claims


def _targets(c):
    """Welche Quellenwerte fuer eine Behauptung in Frage kommen: (Arten, Zielwert, Toleranz)."""
    rnd = 0.5 * 10 ** (-c["decimals"])
    if c["kind"] == "money" and c["money_mn"] is not None:
        tol = max(rnd * SCALE_MN.get(c["unit"], 1), 0.002 * abs(c["money_mn"]))
        return ("mn",), c["money_mn"], tol
    if c["kind"] == "money":
        return ("plain",), c["value"], max(rnd, 0.002 * abs(c["value"]))
    if c["kind"] == "pct":
        return ("pct",), c["value"], rnd + 0.05
    return ("plain", "mn"), c["value"], max(rnd, 0.002 * abs(c["value"]))


def check_claim(c, sources, context_kinds=None):
    """Quelle, in der die Zahl steht (oder None). context_kinds: Arten, bei denen auch der Kontext passen muss
    (None = nur Zahlenabgleich wie bisher). Ohne Kontextwoerter im Report-Satz gilt der reine Zahlenabgleich."""
    hit = _check_number(c, sources)
    if hit is None or not context_kinds or c["kind"] not in context_kinds:
        return hit
    terms = claim_terms(c)
    if not terms - WEAK:
        return hit
    for src in sources:
        if hasattr(src, "context_match") and src.context_match(c, terms):
            return src.label
    return None


def _check_number(c, sources):
    dec = c["decimals"]
    rnd = 0.5 * 10 ** (-dec)  # Rundungstoleranz gemaess angegebener Stellen
    for src in sources:
        if c["kind"] == "money":
            if c["money_mn"] is not None:
                if _close(c["money_mn"], src.money_mn, rnd * SCALE_MN.get(c["unit"], 1), 0.002):
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
def run_fact_check(sections, sources, ticker_names=None, context_kinds=CONTEXT_KINDS):
    """sections: Liste (Titel, Text); sources: Liste SourceIndex; ticker_names: {Ticker: Name}.
    context_kinds: Arten mit Kontextpruefung (Standard CONTEXT_KINDS; None = keine Kontextpruefung)."""
    results, by_kind = [], {}
    for title, text in sections:
        for c in extract_claims(text):
            c["section"] = title
            c["source"] = _check_number(c, sources)
            c["context_ok"] = None
            if c["source"] is not None and context_kinds and c["kind"] in context_kinds:
                terms = claim_terms(c)
                if terms - WEAK:
                    c["context_ok"] = any(hasattr(s, "context_match") and s.context_match(c, terms) for s in sources)
            if c["source"] is not None:
                src = next((s for s in sources if s.label == c["source"]), None)
                if c["context_ok"]:                   # Beleg aus der Quelle mit passendem Kontext
                    src = next((s for s in sources if hasattr(s, "context_match") and s.context_match(c)), src)
                ev = src.evidence(c) if src is not None and hasattr(src, "evidence") else None
                if ev:
                    c["evidence"] = ev
            results.append(c)
            k = by_kind.setdefault(c["kind"], [0, 0, 0])
            k[0] += 1
            k[1] += c["source"] is not None
            k[2] += c["source"] is not None and c.get("context_ok") is not False
    names = []
    if ticker_names:
        for title, text in sections:
            for i in check_names(text, ticker_names):
                i["section"] = title
                names.append(i)
    total = len(results)
    matched = sum(r["source"] is not None for r in results)
    ctx_matched = sum(r["source"] is not None and r.get("context_ok") is not False for r in results)
    return {
        "context_kinds": list(context_kinds or []),
        "context_matched": ctx_matched,
        "context_match_rate": round(ctx_matched / total, 3) if total else None,
        "number_only": [r for r in results if r["source"] is not None and r.get("context_ok") is False],
        "total_claims": total,
        "matched": matched,
        "match_rate": round(matched / total, 3) if total else None,
        "by_kind": {k: {"total": v[0], "matched": v[1], "context_matched": v[2]} for k, v in by_kind.items()},
        "by_source": {s.label: sum(r["source"] == s.label for r in results) for s in sources},
        "unmatched": [r for r in results if r["source"] is None],
        "name_issues": names,
        "claims": results,
    }


def save_json(result, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
