"""
Abschnitte aus 10-K und 10-Q direkt von SEC EDGAR (ohne sec-api.io).

Hintergrund: Das kostenlose Kontingent von sec-api.io (ExtractorApi) ist auf 100 Abrufe begrenzt; danach liefern
alle Analyse-Tools nur noch HTTP 429. EDGAR selbst ist frei (nur ein User-Agent ist Pflicht). Hier wird das
Hauptdokument einmal geladen, in Text umgewandelt (wie bei den 20-F, annual_20f.html_to_text) und ueber die
Item-Ueberschriften am Zeilenanfang zerlegt:
  10-K: Item 1, 1A, 1B, 1C, 2, ..., 7, 7A, 8 ...      10-Q: Part I Item 2 (MD&A), Part II Item 1A (Risikofaktoren)
Je Item wird der laengste Abschnitt genommen, der nicht im Inhaltsverzeichnis steht (Querverweise im Fliesstext
stehen nicht am Zeilenanfang). sec-api bleibt nur Rueckfall, wenn die eigene Zerlegung nichts findet.
"""
import os
import re

from .annual_20f import _is_toc, html_to_text

MAX_CHARS = 100_000
MIN_CHARS = {"7A": 300, "1B": 100, "1C": 300, "9B": 50}
_HEAD = re.compile(r"(?im)^[ \t]*item[ \t]+(\d{1,2})[ \t]*([A-C])?\b[ \t]*[\.:\-–—]?")


def fetch_text(url, cache_file):
    """Hauptdokument als Text (einmal laden, dann Cache-Datei)."""
    if cache_file and os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return f.read()
    import requests
    from .fmp_utils import _sec_headers
    r = requests.get(url, headers=_sec_headers(), timeout=120)
    r.raise_for_status()
    text = html_to_text(r.text)
    if cache_file:
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(text)
    return text


def headings(text):
    """[(pos, item_id)] fuer alle Item-Ueberschriften am Zeilenanfang, z. B. (12345, '1A')."""
    return [(m.start(), (m.group(1).lstrip("0") or "0") + (m.group(2) or "").upper()) for m in _HEAD.finditer(text)]


def section(text, item, min_chars=None):
    """Laengster Abschnitt mit dieser Item-Nummer ausserhalb des Inhaltsverzeichnisses, sonst None."""
    item = str(item).upper()
    heads = headings(text)
    best = ""
    for i, (pos, nr) in enumerate(heads):
        if nr != item or _is_toc(text, pos):
            continue
        end = next((p for p, n in heads[i + 1:] if n != nr), len(text))
        seg = text[pos:end]
        if len(seg) > len(best):
            best = seg
    lim = MIN_CHARS.get(item, 1500) if min_chars is None else min_chars
    return best[:MAX_CHARS] if len(best) >= lim else None


def tenq_item(text, key):
    """10-Q: 'part1item2' (MD&A) oder 'part2item1a' (Risikofaktoren). MD&A ist das laengste Item 2 (Part II Item 2
    ist kurz), Risikofaktoren stehen im 10-Q nur in Part II."""
    item = {"part1item2": "2", "part2item1a": "1A", "part1item3": "3", "part1item1": "1"}.get(key)
    # Risikofaktoren im 10-Q sind oft nur ein Satz ("no material changes ... since the 10-K") - auch das ist die Antwort
    return section(text, item, min_chars=60 if key == "part2item1a" else 1500) if item else None
