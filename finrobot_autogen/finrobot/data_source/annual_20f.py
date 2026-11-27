"""
Abschnitte aus 20-F-Jahresberichten (auslaendische Emittenten wie ASML oder TSMC), ohne sec-api.

Hintergrund: sec-api.io (ExtractorApi) zerlegt nur 10-K, 10-Q und 8-K. Ein 20-F ist anders gegliedert:
  10-K Item 1  (Business)      ~ 20-F Item 4  (Information on the Company)
  10-K Item 1A (Risk Factors)  ~ 20-F Item 3D (Risk Factors)
  10-K Item 7  (MD&A)          ~ 20-F Item 5  (Operating and Financial Review and Prospects)
  10-K Item 7A (Market risk)   ~ 20-F Item 11 (Quantitative and Qualitative Disclosures About Market Risk)
Viele Emittenten (z. B. ASML) legen den 20-F als integrierten Geschaeftsbericht an; die Items stehen dann nur in
einer Querverweistabelle. Deshalb drei Stufen: (1) Item-Ueberschriften, (2) Abschnittsueberschriften wie
"Risk factors", (3) Stichwort-Auswahl von Absaetzen. Jede Stufe meldet, wie der Abschnitt gefunden wurde
(Kopfzeile im Text), damit falsche Treffer auffallen.

Das Dokument wird einmal von EDGAR geladen und als Text zwischengespeichert (CACHE_PATH/sec_utils/<T>_<FY>_20f.txt).
"""
import os
import re
from html import unescape

MAX_CHARS = 100_000

SECTIONS = {
    "1": {"item": "4", "label": "Item 4 Information on the Company (20-F)",
          "head": [r"information on the company", r"business overview", r"our business", r"our company",
                   r"business description", r"about (us|asml|the company)"],
          "words": ["customers", "products", "segment", "competition", "market", "technology", "strategy",
                    "manufacturing", "supply", "employees"]},
    "1A": {"item": "3", "sub": r"risk\s+factors", "label": "Item 3D Risk Factors (20-F)",
           "head": [r"risk factors", r"principal risks", r"risk management and risk factors"],
           "words": ["risk", "could", "adversely", "may", "uncertain", "depend", "failure", "regulation"]},
    "7": {"item": "5", "label": "Item 5 Operating and Financial Review and Prospects (20-F)",
          "head": [r"operating and financial review", r"management'?s discussion", r"results of operations",
                   r"financial performance", r"financial review"],
          "words": ["net sales", "revenue", "gross margin", "operating income", "compared", "increase", "decrease",
                    "cash flow", "liquidity", "expenses"]},
    "7A": {"item": "11", "label": "Item 11 Market Risk (20-F)",
           "head": [r"quantitative and qualitative disclosures? about market risk", r"market risk"],
           "words": ["currency", "interest rate", "hedg", "exposure", "derivative"]},
}


def html_to_text(html):
    html = re.sub(r"(?is)<(script|style|ix:header).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>|</li>|</table>", "\n", html)
    html = re.sub(r"(?i)</t[dh]>", " \t ", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"[ \xa0​]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _is_toc(text, pos):
    """Inhaltsverzeichnis: viele kurze Zeilen mit Seitenzahl am Ende direkt nach der Fundstelle."""
    window = text[pos:pos + 1500].split("\n")[1:16]
    short_num = sum(1 for ln in window if len(ln) < 90 and re.search(r"\b\d{1,3}\s*$", ln))
    return short_num >= 5


def _item_sections(text):
    """Item-Ueberschriften am Zeilenanfang: [(pos, item_nr)]."""
    out = []
    for m in re.finditer(r"(?im)^\s*item\s+(\d{1,2})([a-d])?\s*[\.:\-–—]?\s+[A-Z]", text):
        out.append((m.start(), m.group(1)))
    return out


def _by_item(text, spec):
    heads = _item_sections(text)
    if len(heads) < 6:
        return None
    best = ""
    for i, (pos, nr) in enumerate(heads):
        if nr != spec["item"] or _is_toc(text, pos):
            continue
        end = next((p for p, n in heads[i + 1:] if n != nr), len(text))
        seg = text[pos:end]
        if len(seg) > len(best):
            best = seg
    if spec.get("sub") and best:                       # Item 3: erst ab "Risk Factors" (3A-3C sind Kennzahlen)
        m = re.search(rf"(?i)\b{spec['sub']}\b", best[100:])
        if m and m.start() + 100 < len(best) - 6000:
            best = best[m.start() + 100:]
    return best if len(best) >= 6000 else None


XREF_SUB = {"1": ["B. Business Overview"], "1A": ["D. Risk Factors"],
            "7": ["A. Operating Results", "B. Liquidity and Capital Resources", "D. Trend Information"],
            "7A": []}


def _pages(text):
    """Seitenanfaenge [(pos, seite)] ueber die wiederkehrende Kopfzeile mit Seitenzahl (integrierte Geschaeftsberichte)."""
    lines = [(m.start(), m.group(0).strip()) for m in re.finditer(r"[^\n]+", text)]
    from collections import Counter
    cnt = Counter(l for _, l in lines if 8 <= len(l) <= 70 and re.search(r"[A-Za-z]{3}", l))
    for head, n in cnt.most_common(5):
        if n < 20:
            break
        marks = []
        for i, (pos, l) in enumerate(lines):
            if l == head and i + 1 < len(lines) and re.fullmatch(r"\d{1,3}", lines[i + 1][1]):
                marks.append((pos, int(lines[i + 1][1])))
        if len(marks) >= 0.8 * n and len(marks) >= 20:
            return marks
    return []


def _xref_pages(text, sec):
    """Seiten laut 'Form 20-F cross reference table' (Item -> Fundstelle und Seite), z. B. ASML."""
    subs = XREF_SUB.get(sec) or []
    starts = [m.start() for m in re.finditer(r"(?i)Form 20-F caption", text)]
    if not subs or not starts:
        return [], []
    table = text[starts[0]:starts[-1] + 12000]
    lines = [l.strip() for l in table.split("\n") if l.strip()]
    all_pages, want, cur, prev_num = set(), [], None, True
    for l in lines:
        if re.fullmatch(r"\d{1,3}", l):
            if not prev_num:
                all_pages.add(int(l))
                if cur in subs:
                    want.append(int(l))
            prev_num = True
            continue
        prev_num = False
        if re.match(r"^[A-K]\.\s", l):
            cur = next((s_ for s_ in subs if l.lower().startswith(s_.lower()[:18])), l)
    return want, sorted(all_pages)


def _by_xref(text, spec, sec=None):
    sec = sec or next((k for k, v in SECTIONS.items() if v is spec), None)
    want, all_pages = _xref_pages(text, sec)
    if sec != "1A":                                  # Risikoseiten nur im Risikoabschnitt (nicht doppelt)
        risk = set(_xref_pages(text, "1A")[0])
        want = [p for p in want if p not in risk]
    marks = _pages(text)
    if not want or not marks:
        return None
    pos_of = {}
    for pos, pg in marks:
        pos_of.setdefault(pg, pos)
    parts = []
    for p in sorted(set(want)):
        nxt = next((q for q in all_pages if q > p), p + 8)
        end_pg = min(nxt, p + 15)
        a = pos_of.get(p)
        b = next((pos_of[q] for q in range(end_pg, end_pg + 5) if q in pos_of), None)
        if a is not None:
            parts.append(text[a:b if b and b > a else a + 40000])
    seg = "\n\n".join(parts)
    return seg if len(seg) >= 6000 else None


def _by_heading(text, spec):
    best = ""
    for pat in spec["head"]:
        for m in re.finditer(rf"(?im)^[ \t]*(?:[^\n]{{0,30}}\s[\u2013\-]\s)?{pat}[ \t:]*$", text):   # ganze Zeile = Ueberschrift
            if _is_toc(text, m.start()) or re.search(r"\d+\s*$", m.group(0)):   # Verzeichniszeile mit Seitenzahl
                continue
            seg = text[m.start():m.start() + MAX_CHARS]
            # Ende: naechste Ueberschrift eines anderen Abschnitts (ausser der eigenen)
            others = [p for k, s in SECTIONS.items() if s is not spec for p in s["head"]]
            stop = re.search(rf"(?im)^[ \t]*(?:[^\n]{{0,30}}\s[\u2013\-]\s)?({'|'.join(others)})[ \t:]*$", seg[300:])
            if stop:
                seg = seg[:300 + stop.start()]
            if len(seg) > len(best):
                best = seg
        if len(best) >= 15000:
            break
    return best if len(best) >= 6000 else None


def _by_keywords(text, spec, limit=60000):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 200]
    scored = []
    for i, p in enumerate(paras):
        low = p.lower()
        score = sum(low.count(w) for w in spec["words"]) / (1 + len(p) / 2000)
        scored.append((score, i, p))
    keep, total = [], 0
    for score, i, p in sorted(scored, reverse=True):
        if score <= 0 or total > limit:
            break
        keep.append((i, p))
        total += len(p)
    return "\n\n".join(p for _, p in sorted(keep)) if keep else None


def extract(text, section):
    """Abschnitt eines 20-F als Text; erste Zeile nennt Quelle und Methode."""
    spec = SECTIONS.get(str(section).upper())
    if spec is None:
        return f"(Section {section} is not mapped for 20-F filings.)"
    for method, fn in (("item heading", _by_item), ("20-F cross reference table", _by_xref),
                       ("section heading", _by_heading), ("keyword selection", _by_keywords)):
        seg = fn(text, spec)
        if seg:
            return f"[{spec['label']}; located by {method}]\n" + seg[:MAX_CHARS]
    return f"(Section {spec['label']} not found in the 20-F text.)"


def filing_text(url, ticker, fyear, cache_dir):
    """20-F-Hauptdokument als Text (einmal laden, dann Cache)."""
    path = os.path.join(cache_dir, "full", f"{ticker}_{fyear}_20f.txt")   # eigener Ordner: nicht doppelt als Quelle
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    import requests
    from .fmp_utils import _sec_headers
    r = requests.get(url, headers=_sec_headers(), timeout=120)
    r.raise_for_status()
    text = html_to_text(r.text)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text
