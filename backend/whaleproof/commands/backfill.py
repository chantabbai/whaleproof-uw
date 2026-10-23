from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta
from typing import Callable

from whaleproof import market_calendar as mc
from whaleproof.config import load_settings
from whaleproof.core.budget import intraday_enabled, live_reserve
from whaleproof.core.data_layer.client import UWBudgetExceeded, UWClient, UWError
from whaleproof.core.data_layer.ingest import (
    ingest_contract_oi, ingest_dp_blocks, ingest_eod, ingest_flow_day, ingest_insider, ingest_market,
    ingest_net_prem, ingest_prices, ingest_realized_vol, ingest_sector, ingest_sector_tide, ingest_series,
    ingest_uw_unusual_paged)
from whaleproof.core.data_layer.context import oi_ratio
from whaleproof.core.data_layer.models import row_to_alert
from whaleproof.core.data_layer.store import Store
from whaleproof.core.verdict.candidates import MAX_CANDIDATES, prefilter
from whaleproof.core.backtest.option_prices import has_history
from whaleproof.core.backtest.simple import day_trades, option_view


DONE = "done-v3"  # v3: Plan 1.5 inputs (dp blocks, ticker/sector flow, insider, contract OI)


def ingest_candidate(client, store: Store, a, d: date, today: date, live: bool) -> None:
    """Everything the checks need for one candidate on session d (shared by backfill and live scan)."""
    ingest_series(client, store, a.ticker, today)
    ingest_eod(client, store, a.ticker, d, live=live)
    ingest_dp_blocks(client, store, a.ticker, d, live=live)
    ingest_net_prem(client, store, a.ticker, d, live=live)
    ingest_insider(client, store, a.ticker, today)
    sector = ingest_sector(client, store, a.ticker)
    if sector:
        ingest_sector_tide(client, store, sector, d, live=live)
    # expired contracts never change → cache forever; live ones refresh twice a day
    ingest_contract_oi(client, store, a.option_chain, ttl=None if a.expiry < today else 12 * 3600)


_UNUSED = "done-v2"  # v2: candidates use the as_of cut; v1 days are redone (cached calls make it cheap)


def backfill(client, store: Store, start: date, end: date, today: date,
             max_candidates_per_day: int = MAX_CANDIDATES,
             stop_at: Callable[[], bool] = lambda: False) -> dict:
    res = {"days_done": 0, "days_skipped": 0, "candidates": 0, "stopped_reason": ""}
    for d in reversed(mc.sessions(start, end)):
        if stop_at():
            res["stopped_reason"] = "time"
            break
        mark = f"day:{d.isoformat()}"
        if store.get_checkpoint(mark) == DONE:
            res["days_skipped"] += 1
            continue
        try:
            ingest_series(client, store, "SPY", today)  # market baseline for excess returns
            ingest_flow_day(client, store, d)
            ingest_market(client, store, d)
            as_of = mc.session_close(d) + timedelta(minutes=15)  # same cut as run_backtest / live scan
            cands = prefilter([a for a in (row_to_alert(r) for r in store.alerts_between(d, d))
                               if a.created_at <= as_of])[:max_candidates_per_day]
            for a in cands:
                ingest_candidate(client, store, a, d, today, live=False)
            res["candidates"] += len(cands)
        except UWBudgetExceeded:
            res["stopped_reason"] = "budget"
            break
        except (UWError, ValueError, KeyError, TypeError) as e:
            print(f"{d}: {type(e).__name__}: {e} — will retry next run", flush=True)
            continue
        store.set_checkpoint(mark, DONE)
        res["days_done"] += 1
        usage = getattr(client, "usage", None)
        print(f"{d}: done ({len(cands)} candidates) — requests today "
              f"{getattr(usage, 'daily_count', None)}", flush=True)
    return res


def fill_prices(client, store: Store, start: date, end: date, today: date,
                stop_at: Callable[[], bool] = lambda: False) -> dict:
    """Daily bars + earnings for gate-passing tickers that have none (simple-rules backtest; 2 calls/ticker)."""
    from whaleproof.core.backtest import simple
    if store.get_checkpoint("prices_done") == end.isoformat():
        return {"tickers": 0, "done": 0, "stopped_reason": "already done"}
    need = simple.missing_price_tickers(store, start, end)
    res = {"tickers": len(need), "done": 0, "stopped_reason": ""}
    for t in need:
        if stop_at():
            res["stopped_reason"] = "budget"
            break
        try:
            ingest_prices(client, store, t, today)
        except UWBudgetExceeded:
            res["stopped_reason"] = "budget"
            break
        except (UWError, ValueError, KeyError, TypeError) as e:
            print(f"{t}: {type(e).__name__}: {e}", flush=True)
            continue
        res["done"] += 1
    if not res["stopped_reason"]:
        store.set_checkpoint("prices_done", end.isoformat())
    return res


def enrich(client, store: Store, start: date, end: date, today: date,
           stop_at: Callable[[], bool] = lambda: False) -> dict:
    """Inputs added after most history was backfilled (H3 uw_flagged, H9 iv_rv): UW's unusual list per day via
    paging (~2 calls) and 3y IV/RV history once per candidate ticker (1 call). Own checkpoint, resumable."""
    res = {"days_done": 0, "tickers": 0, "stopped_reason": ""}
    for d in reversed(mc.sessions(start, end)):
        mark = f"enrich:{d.isoformat()}"
        if store.get_checkpoint(mark) == "done":
            continue
        if stop_at():
            res["stopped_reason"] = "time"
            break
        try:
            ingest_uw_unusual_paged(client, store, d)
            as_of = mc.session_close(d) + timedelta(minutes=15)
            cands = prefilter([a for a in (row_to_alert(r) for r in store.alerts_between(d, d))
                               if a.created_at <= as_of])[:MAX_CANDIDATES]
            for t in sorted({a.ticker for a in cands}):
                if store.get_metric(t, "all", "vol_hist") is None:
                    ingest_realized_vol(client, store, t, today)
                    res["tickers"] += 1
        except UWBudgetExceeded:
            res["stopped_reason"] = "budget"
            break
        except (UWError, ValueError, KeyError, TypeError) as e:
            print(f"enrich {d}: {type(e).__name__}: {e} — will retry next run", flush=True)
            continue
        store.set_checkpoint(mark, "done")
        res["days_done"] += 1
    return res


def fill_contract_history(client, store: Store, start: date, end: date, today: date,
                          stop_at: Callable[[], bool] = lambda: False) -> dict:
    """Real option prices for the F2/F3 finalist candidates (long + cheap option, or long + ≥15% OTM): one
    `/option-contract/{id}/historic` call per contract not cached yet (F1's are cached by the morning OI check).
    Descriptive backtest data only — never changes a pass/fail rule."""
    if store.get_checkpoint("contracts_done") == end.isoformat():
        return {"fetched": 0, "stopped_reason": "already done"}
    res = {"fetched": 0, "stopped_reason": ""}
    for d in reversed(mc.sessions(start, end)):
        for a, fails, _ in day_trades(store, d):
            if fails or a.direction <= 0 or has_history(store, a.option_chain):
                continue
            if a.otm_pct < 0.15 and option_view(store, a) != "cheap":
                continue
            if stop_at():
                res["stopped_reason"] = "budget"
                return res
            try:
                ingest_contract_oi(client, store, a.option_chain, ttl=None)
            except UWBudgetExceeded:
                res["stopped_reason"] = "budget"
                return res
            except (UWError, ValueError, KeyError, TypeError) as e:
                print(f"{a.option_chain}: {type(e).__name__}: {e}", flush=True)
                continue
            res["fetched"] += 1
    store.set_checkpoint("contracts_done", end.isoformat())
    return res


def fill_f1_oi(client, store: Store, start: date, end: date, today: date,
               stop_at: Callable[[], bool] = lambda: False) -> dict:
    """Amendment 15: open interest (D and D+1) for every F1-shaped gate passer — 31–90 DTE, > 5% OTM, not a put
    sale, either direction — so F1's 'OI confirmed' block sees the whole population, not only fetched candidates.
    One `/option-contract/{id}/historic` call per contract (cached forever for expired contracts)."""
    if store.get_checkpoint("f1_oi_done") == end.isoformat():
        return {"fetched": 0, "stopped_reason": "already done"}
    res, tried = {"fetched": 0, "stopped_reason": ""}, set()
    for d in reversed(mc.sessions(start, end)):
        for a, fails, put_sale in day_trades(store, d):
            if fails or put_sale or not (30 < (a.dte or 0) <= 90) or not ((a.otm_pct or 0) > 0.05):
                continue
            if a.option_chain in tried or oi_ratio(store, a) is not None:
                continue
            if stop_at():
                res["stopped_reason"] = "budget"
                return res
            tried.add(a.option_chain)
            try:
                ingest_contract_oi(client, store, a.option_chain, ttl=None)
            except UWBudgetExceeded:
                res["stopped_reason"] = "budget"
                return res
            except (UWError, ValueError, KeyError, TypeError) as e:
                print(f"{a.option_chain}: {type(e).__name__}: {e}", flush=True)
                continue
            res["fetched"] += 1
    store.set_checkpoint("f1_oi_done", end.isoformat())
    return res


def history_then_prices(client, store: Store, start: date, end: date, today: date, stop) -> dict:
    """Hourly job: history first; once complete, enrich (uw_unusual + iv/rv), then fill bars for the simple backtest."""
    res = backfill(client, store, start, end, today, stop_at=stop)
    if backfill_complete(store, start, end) and res.get("stopped_reason") != "budget":
        res["enrich"] = enrich(client, store, start, end, today, stop_at=stop)
        if res["enrich"]["stopped_reason"] != "budget":
            res["prices"] = fill_prices(client, store, start, end, today, stop_at=stop)
            if res["prices"].get("stopped_reason") != "budget":
                res["f1_oi"] = fill_f1_oi(client, store, start, end, today, stop_at=stop)    # Amendment 15 first
                if res["f1_oi"]["stopped_reason"] != "budget":
                    res["contracts"] = fill_contract_history(client, store, start, end, today, stop_at=stop)
    return res


RESET = time(20, 0)  # UW daily counter resets 8 PM ET
DAY_COST = 400       # upper estimate of requests one backfilled session can take


BACKFILL_START = date(2024, 10, 1)


def backfill_complete(store: Store, start: date = BACKFILL_START, end: date | None = None) -> bool:
    end = end or mc.previous_session(datetime.now(mc.NY).date())
    return all(store.get_checkpoint(f"day:{d.isoformat()}") == DONE for d in mc.sessions(start, end))


def adaptive_stop(client, limit: int, now=lambda: datetime.now(mc.NY), day_cost: int = DAY_COST,
                  intraday: bool = True, ceiling: int | None = None):
    """Stop before the next day would eat into what live jobs still need before the 8 PM reset,
    or would pass the owner's hard ceiling (WHALEPROOF_BACKFILL_MAX)."""
    def stop() -> bool:
        used = getattr(client.usage, "daily_count", None) or 0
        cap = limit - live_reserve(now(), intraday)
        if ceiling is not None:
            cap = min(cap, ceiling)
        return used + day_cost > cap
    return stop


def in_quiet_hours(now: datetime, stop: str) -> bool:
    """True between `stop` (e.g. 07:00) and the 20:00 ET budget reset — daytime belongs to live jobs."""
    t = now.astimezone(mc.NY).time()
    return time.fromisoformat(stop) <= t < RESET


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="whaleproof backfill")
    p.add_argument("--start", required=True, type=date.fromisoformat)
    p.add_argument("--end", required=True, type=date.fromisoformat)
    p.add_argument("--max-candidates", type=int, default=MAX_CANDIDATES)
    p.add_argument("--prices", action="store_true",
                   help="only fill daily bars + earnings for gate-passing tickers missing them (simple backtest)")
    args = p.parse_args(argv)
    s = load_settings()
    if s.backfill_mode == "night":
        client = UWClient(s.uw_api_key, s.backfill_request_cap)
        stop = lambda: in_quiet_hours(datetime.now(mc.NY), s.backfill_stop)  # noqa: E731
        print(f"backfill (night mode) cap {s.backfill_request_cap}, quiet {s.backfill_stop}–20:00 ET", flush=True)
    else:
        client = UWClient(s.uw_api_key, s.live_request_cap)       # hard ceiling; adaptive stop decides earlier
        store = Store(s.db_path)
        intraday = intraday_enabled(backfill_complete(store))
        stop = adaptive_stop(client, s.daily_limit, intraday=intraday, ceiling=s.backfill_max)
        print(f"backfill (adaptive) live reserve now {live_reserve(datetime.now(mc.NY), intraday)} "
              f"(intraday {'on' if intraday else 'off until history complete'}), ceiling {s.backfill_max}", flush=True)
    if args.prices:
        res = fill_prices(client, Store(s.db_path), args.start, args.end, datetime.now(mc.NY).date(), stop_at=stop)
    else:
        res = history_then_prices(client, Store(s.db_path), args.start, args.end, datetime.now(mc.NY).date(), stop)
    print(res, flush=True)
    return 0
