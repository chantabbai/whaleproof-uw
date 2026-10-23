"""Ticker page company header: name and short description from UW's stock info (`/api/stock/{t}/info`).

The API reads the cache only; the refresher fetches the info once for a viewed ticker that has none (cached forever).
UW sends most names in capitals and many descriptions in lower case, so both are tidied for display.
"""
from __future__ import annotations

import re

from whaleproof.core.data_layer.fetch import cache_key, rows
from whaleproof.core.data_layer.store import Store

INFO = "/api/stock/{t}/info"
# capitalised words kept as UW spells them (word without a vowel, a digit or '&' is kept too: KKR, 3M, S&P)
KEEP = {"ETF", "ETN", "SPDR", "US", "USA", "UK", "NVIDIA", "MSCI", "GXO", "FTI", "CSI", "AMD", "MSTR", "GOOGL", "SA",
        "NV", "AG", "SE", "ADR", "ADS", "REIT", "AI", "IBM", "UPS", "AMC", "ASML", "TSMC", "NYSE", "II", "III", "IV",
        "QQQ", "ARK", "UBS", "BP", "EOG", "AES", "AIG"}
SPECIAL = {"ISHARES": "iShares"}


def _word(w: str) -> str:
    if w in SPECIAL:
        return SPECIAL[w]
    if w in KEEP or not re.search(r"[AEIOU]", w) or re.search(r"[0-9&]", w):
        return w
    return w[:1] + w[1:].lower()


def tidy_name(name: str | None) -> str | None:
    n = (name or "").strip()
    if not re.search(r"[A-Za-z]", n):
        return None
    if n != n.upper():
        return n                                   # UW already gave mixed case: trust it
    n = re.sub(r"\((R|SM|TM)\)", "", n)
    return " ".join("-".join(_word(p) for p in w.split("-")) for w in n.split())


def tidy_description(text: str | None) -> str | None:
    d = (text or "").strip()
    if not d:
        return None
    d = re.sub(r"\s*\.\.\.$", "…", d)
    d = d[:1].upper() + d[1:]
    # new sentence after a lower-case word ("change. we" → "We"); not after an abbreviation like "Inc." or "U.S."
    return re.sub(r"(\b[a-z][\w-]*[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), d)


def company_info(store: Store, ticker: str) -> dict | None:
    hit = store.cache_get(cache_key(INFO.format(t=ticker), {}), None)
    rs = rows(hit) if hit is not None else []
    if not rs or not isinstance(rs[0], dict):
        return None
    r = rs[0]
    return {"name": tidy_name(r.get("full_name") or r.get("short_name")),
            "description": tidy_description(r.get("short_description"))}
