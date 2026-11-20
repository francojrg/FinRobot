"""
Stichwortsuche im 10-K (Items 1, 1A, 7) - Ersatz fuer die RAG-Funktion aus FinRobots Experimenten.

Das Original nutzt eine Vektor-Datenbank (chromadb) ueber eine fest eingetragene SEC-URL (PDD 20-F 2022).
Hier werden die bereits gecachten 10-K-Abschnitte (sec-api, siehe sec_utils) in Absaetze zerlegt und per
einfacher Stichwort-Bewertung durchsucht: keine Embeddings, keine Zusatzkosten, nachvollziehbar.
"""
import math
import re
from collections import Counter
from typing import Annotated

from finrobot.data_source.sec_utils import SECUtils

_STOP = set("the a an of and or to in on for with by is are was were be as at from that this which its it their "
            "our we us has have had not but than more less into over under about".split())
_CACHE = {}


def _tokens(text):
    return [w for w in re.findall(r"[a-z0-9][a-z0-9\-\.%]*", text.lower()) if w not in _STOP and len(w) > 1]


def _paragraphs(ticker, fyear):
    key = (ticker.upper(), str(fyear))
    if key not in _CACHE:
        paras = []
        for item, label in (("1", "Item 1 Business"), ("1A", "Item 1A Risk Factors"), ("7", "Item 7 MD&A")):
            try:
                text = SECUtils.get_10k_section(ticker.upper(), str(fyear), item)
            except Exception as e:
                text = ""
                print(f"10-K Item {item} nicht verfuegbar: {e}")
            for p in re.split(r"\n\s*\n|(?<=\.)\s{2,}", str(text)):
                p = " ".join(p.split())
                if len(p) > 120:
                    paras.append((label, p))
        _CACHE[key] = paras
    return _CACHE[key]


def make_tenk_search(ticker, fyear):
    """Liefert eine Tool-Funktion fuer genau dieses 10-K."""

    def search_10k(
        query: Annotated[str, "what to look for, e.g. 'customer concentration government revenue' or 'liquidity convertible notes'"],
        n_results: Annotated[int, "number of passages to return (default 4)"] = 4,
    ) -> str:
        paras = _paragraphs(ticker, fyear)
        if not paras:
            return "The 10-K text is not available."
        q = _tokens(query)
        if not q:
            return "Please provide keywords."
        df = Counter(w for _, p in paras for w in set(_tokens(p)))
        n = len(paras)
        scored = []
        for label, p in paras:
            tf = Counter(_tokens(p))
            score = sum((tf[w] / (1 + tf[w])) * math.log(1 + n / (1 + df[w])) for w in q if w in tf)
            if score > 0:
                scored.append((score, label, p))
        scored.sort(reverse=True)
        if not scored:
            return f"No passages found for '{query}'."
        out = [f"[{label}] {p[:1200]}" for _, label, p in scored[:max(1, min(int(n_results), 8))]]
        return f"Passages from {ticker.upper()}'s 10-K for fiscal year {fyear} (cite as 10-K):\n\n" + "\n\n".join(out)

    search_10k.__doc__ = (f"Search {ticker.upper()}'s 10-K for fiscal year {fyear} (Business, Risk Factors, MD&A) by keywords "
                          "and return the most relevant passages.")
    return search_10k
