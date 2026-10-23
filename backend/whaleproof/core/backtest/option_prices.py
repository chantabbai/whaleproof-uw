"""Real option results from UW's per-contract daily history (`/api/option-contract/{id}/historic`).

Already cached for the next-morning OI check, so reading it costs no API calls. Conservative fills:
buy  = entry day's opening trade + half the (closing) bid/ask spread,
sell = exit day's closing bid (or last trade less the entry half-spread when no closing quote).
A contract without a trade on the entry day, or without a row on the exit day, is "not measured" — never guessed."""
from __future__ import annotations

from datetime import date

from whaleproof.core.data_layer.fetch import cache_key
from whaleproof.core.data_layer.store import Store


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _key(chain: str) -> str:
    return cache_key(f"/api/option-contract/{chain}/historic", {"limit": 500})


def has_history(store: Store, chain: str) -> bool:
    return store.cache_get(_key(chain), None) is not None


def history(store: Store, chain: str) -> dict[str, dict] | None:
    raw = store.cache_get(_key(chain), None)
    if raw is None:
        return None
    rs = raw.get("chains", []) if isinstance(raw, dict) else []
    return {str(r["date"])[:10]: r for r in rs if r.get("date")}


def real_option_return(store: Store, chain: str, entry: date, exit_: date) -> dict | None:
    h = history(store, chain)
    if not h:
        return None
    a, b = h.get(entry.isoformat()), h.get(exit_.isoformat())
    if not a or not b:
        return None
    open_, bid0, ask0 = _num(a.get("open_price")), _num(a.get("nbbo_bid")), _num(a.get("nbbo_ask"))
    if open_ is None:
        return None
    gap0 = ask0 - bid0 if bid0 and ask0 and ask0 >= bid0 else 0.0
    buy = round(open_ + gap0 / 2, 6)
    spread_pct = (ask0 - bid0) / ((ask0 + bid0) / 2) if bid0 and ask0 else None
    bid1, ask1, last = _num(b.get("nbbo_bid")), _num(b.get("nbbo_ask")), _num(b.get("last_price"))
    sell = bid1
    if sell is None:
        if last is None:
            return None
        sell = last * (1 - (spread_pct or 0) / 2)
    # Amendment 18 (report only): best case = mid prices, bad day = 1.5 × the half gap each way
    if bid1 and ask1 and ask1 >= bid1:
        mid1, wide1 = (bid1 + ask1) / 2, max(0.0, (bid1 + ask1) / 2 - 0.75 * (ask1 - bid1))
    else:
        mid1, wide1 = (last, last * (1 - 0.75 * (spread_pct or 0))) if last is not None else (sell, sell)
    return {"buy": buy, "sell": sell, "ret": sell / buy - 1, "spread_pct": spread_pct,
            "ret_mid": mid1 / open_ - 1, "ret_wide": wide1 / (open_ + 0.75 * gap0) - 1}
