"""Fetch REAL daily price history for the option legs of the structures test (short put, put spread, call spread) so
desk_structures.py can replace model prices with real ones. Runs through UWClient/cached_get; hard cap on calls.
Usage: uv run python scripts/desk_fetch_legs.py [max_calls]   (run after the 20:00 ET reset)"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.backtest.option_prices import has_history
from whaleproof.core.data_layer.client import UWBudgetExceeded, UWClient, UWError
from whaleproof.core.data_layer.fetch import cached_get
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import HOLDOUT, TRAIN
from whaleproof.desk.history import classify_rows, earnings_map, load_raw
from whaleproof.desk.structures import own_calls, own_expiry, structures_for

PRIORITY = ("call_itm10_60d", "call_atm_60d", "short_put", "put_spread", "call_spread")


def occ(ticker: str, expiry: date, kind: str, strike: float) -> str:
    return f"{ticker}{expiry:%y%m%d}{kind}{round(strike * 1000):08d}"


def plan(store: Store) -> list[str]:
    raw = load_raw(REPO_ROOT / "data" / "desk", include_holdout=True)
    rows = classify_rows(raw, earnings_map(store))
    order = {"holdout": 0, "post": 1, "train": 2}
    todo: list[tuple[int, int, str]] = []
    for h, (_, x) in zip(rows, raw):
        if not h.tier or not x.get("expiry") or not x.get("strike"):
            continue
        w = "train" if h.session_date <= TRAIN[1] else "holdout" if h.session_date <= HOLDOUT[1] else "post"
        entry = mc.next_session(h.session_date)
        bars = store.get_ohlc(h.ticker, entry, entry + timedelta(days=1))
        if not bars:
            continue
        expiry = date.fromisoformat(str(x["expiry"])[:10])
        spot = bars[0].open
        legs = {n: (lg, expiry) for n, lg in structures_for(spot, float(x["strike"])).items()}
        legs |= {n: (lg, own_expiry(entry)) for n, lg in own_calls(spot).items()}
        for p, name in enumerate(PRIORITY):
            lg, ex = legs[name]
            for g in lg:
                todo.append((p, order[w], occ(h.ticker, ex, g.kind, g.strike)))
    seen, out = set(), []
    for _, _, sym in sorted(todo):
        if sym not in seen and not has_history(store, sym):
            seen.add(sym)
            out.append(sym)
    return out


def main(cap: int) -> None:
    s = load_settings()
    store = Store(s.db_path)
    todo = plan(store)
    print(f"{len(todo)} leg contracts without history; fetching up to {cap}", flush=True)
    client = UWClient(s.uw_api_key, daily_cap=s.daily_limit - 3_000)      # never touch the last 3K of the day
    done = 0
    for sym in todo[:cap]:
        try:
            cached_get(client, store, f"/api/option-contract/{sym}/historic", {"limit": 500}, None)
            done += 1
        except UWBudgetExceeded as e:
            print("stopped on budget:", e, flush=True)
            break
        except UWError as e:                       # unlisted strike guess → skip, keep going
            print("skip", sym, str(e)[:80], flush=True)
    print(f"fetched {done}; UW count {client.usage.daily_count}", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2500)
