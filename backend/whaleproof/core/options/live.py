"""Live option tracking (owner request 2026-09-29): real quotes for every open pick from entry to its cut-off date.

- `/api/stock/{t}/option-contracts?expiry=D` = the full listed chain for one expiry (one call; unfiltered caps at 500)
- `/api/stock/{t}/stock-state` = live last price, today's open, previous close
After the open, `after_open_check` says whether a pick is still worth buying after the overnight move. It is ADVISORY:
the tested strategies enter at the open; skipping on a gap is an untested rule until the learning year says otherwise."""
from __future__ import annotations

from whaleproof.core.data_layer.fetch import cached_get, rows

from .pnl import parse_contract

MOVED = 0.5          # ≥ half the way to the target before we could buy → "already moved"
PRICE_RAN = 0.25     # option costs ≥ 25% more than last night's estimate → "price ran"
WIDE_SPREAD = 0.10   # (ask − bid) / mid over 10% → "wide spread" (Amendment 14)
MIN_OI = 100         # our strike must have open interest ≥ 100 (Amendment 17)
MAX_AWAY = 0.10      # ... and lie within 10% of the stock price


def _f(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f >= 0 else None


def parse_chain(payload) -> dict[str, dict]:
    out = {}
    for r in rows(payload):
        s = r.get("option_symbol")
        if not s:
            continue
        out[s] = {"bid": _f(r.get("nbbo_bid")), "ask": _f(r.get("nbbo_ask")), "last": _f(r.get("last_price")),
                  "iv": _f(r.get("implied_volatility")), "delta": r.get("delta"), "volume": r.get("volume"),
                  "open_interest": r.get("open_interest")}
    return out


def parse_state(payload) -> dict:
    d = payload.get("data", payload) if isinstance(payload, dict) else {}
    d = d if isinstance(d, dict) else {}          # {"data": null}: a ticker UW doesn't know
    return {"last": _f(d.get("close")), "open": _f(d.get("open")), "prev_close": _f(d.get("prev_close")),
            "market_time": d.get("market_time")}


def chain(client, store, ticker: str, expiry: str, ttl: float = 120) -> dict[str, dict]:
    return parse_chain(cached_get(client, store, f"/api/stock/{ticker}/option-contracts", {"expiry": expiry}, ttl))


def stock_state(client, store, ticker: str, ttl: float = 60) -> dict:
    return parse_state(cached_get(client, store, f"/api/stock/{ticker}/stock-state", {}, ttl))


def _oi(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def snap_listed(symbol: str, listed: dict, spot: float | None = None) -> str | None:
    """Nearest listed strike (same expiry and type) that really trades: open interest ≥ 100 and, given the stock price,
    within 10% of it (Amendment 17). Ties → slightly in the money. None if no strike qualifies."""
    c = parse_contract(symbol)
    if c is None:
        return None
    same = [(s, parse_contract(s)) for s in listed]
    same = [(s, p) for s, p in same if p and p["expiry"] == c["expiry"] and p["kind"] == c["kind"]
            and _oi(listed[s].get("open_interest")) >= MIN_OI
            and (not spot or abs(p["strike"] - spot) <= MAX_AWAY * spot)]
    if not same:
        return None
    itm = 1 if c["kind"] == "C" else -1          # ties: calls take the lower strike, puts the higher (in the money)
    return min(same, key=lambda sp: (abs(sp[1]["strike"] - c["strike"]), itm * sp[1]["strike"]))[0]


def after_open_check(direction: int, plan: dict, stock_now: float | None, est_premium: float | None,
                     ask_now: float | None, bid_now: float | None = None, quote_given: bool | None = None,
                     contract_found: bool = True) -> dict:
    """Is the pick still worth buying after the overnight move? Advisory only (see module doc).
    With our contract's quote (bid given, or quote_given=True) a bid/ask gap over 10% of mid skips it (Amendment 14);
    a missing quote does not (14a). No traded strike near the money (contract_found=False) skips it (Amendment 17)."""
    if stock_now is None:
        return {"decision": "no live price", "reason": "no live stock price available"}
    ref, tgt, stop = plan["entry_ref"], plan["target"], plan["invalidation"]
    progress = (stock_now - ref) * direction / ((tgt - ref) * direction) if tgt != ref else 0.0
    change = (ask_now / est_premium - 1) if ask_now and est_premium else None
    out = {"progress": progress, "price_change": change, "stock_now": stock_now}
    if (stock_now - stop) * direction <= 0:
        return out | {"decision": "skip: past the stop", "reason": f"stock at {stock_now:.2f} is already past the stop {stop:.2f}"}
    if progress >= MOVED:
        return out | {"decision": "already moved",
                      "reason": f"stock already went {progress:.0%} of the way to the target before we could buy"}
    if change is not None and change >= PRICE_RAN:
        return out | {"decision": "skip: price ran", "reason": f"option costs {change:.0%} more than last night's estimate"}
    if not contract_found:
        return out | {"decision": "skip: no liquid strike",
                      "reason": "no strike near the stock price has enough open contracts (100+) to trade easily"}
    if quote_given or (quote_given is None and bid_now is not None):
        if not (bid_now and ask_now):       # UW omits quotes of contracts not traded yet today (Amendment 14a)
            return out | {"decision": "still a buy",
                          "reason": "little overnight move; the plan still has room (no quote at 9:45 to check the spread)"}
        spread = (ask_now - bid_now) / ((ask_now + bid_now) / 2)
        out["spread"] = spread
        if spread > WIDE_SPREAD:
            return out | {"decision": "skip: wide spread",
                          "reason": f"buy and sell prices are {spread:.0%} apart: buying and selling would lose that much"}
    return out | {"decision": "still a buy", "reason": "little overnight move; the plan still has room"}
