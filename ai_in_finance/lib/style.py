"""
Gemeinsame Stilregeln fuer alle Agenten (abgeleitet aus Investor-Letters von Fundsmith, Giverny, Pershing Square und
Greenlight; siehe Projekt-Dokument 'letter-leitfaden'). Werden an System-Prompts bzw. Aufgaben angehaengt.
"""
STYLE_RULES = (
    "WRITING STYLE (like the best investor letters): lead with the result and the numbers, then the explanation. "
    "Discuss problems before successes. Explain shortfalls with named, specific causes - an explanation, not an excuse. "
    "Give every number its context (period, comparison, source). Name what would prove a view wrong. Write plainly: no "
    "promotional words (e.g. 'compelling', 'highly attractive', 'exceptional'), no filler, no generic disclaimers in the "
    "body. Mark any rough or back-of-the-envelope calculation as illustrative. Never invent motives, facts or figures "
    "that are not in the provided data."
)
