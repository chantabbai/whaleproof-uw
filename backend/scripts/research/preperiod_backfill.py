"""Pre-period backfill for docs/PREPERIOD-TEST.md: UW flow alerts 2023-10-31..2024-09-27 (oldest first — the token's
history window is a rolling 730 trading days) plus the minimum context the frozen filter needs, only where missing:
daily bars (outcomes), earnings (earnings-in-hold block), realized-vol history (far-OTM option-value check).
Usage: uv run python scripts/research/preperiod_backfill.py [stop_at_daily_count]   (resumable; checkpoints per day)"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from whaleproof import market_calendar as mc
from whaleproof.config import load_settings
from whaleproof.core.backtest.simple import day_trades
from whaleproof.core.data_layer.client import UWBudgetExceeded, UWClient, UWError
from whaleproof.core.data_layer.ingest import ingest_bars, ingest_earnings, ingest_flow_day, ingest_realized_vol
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import DEFAULT_FILTER

START, END = date(2023, 10, 31), date(2024, 9, 27)


def main(stop_at: int) -> None:
    s = load_settings()
    store = Store(s.db_path)
    client = UWClient(s.uw_api_key, daily_cap=stop_at)
    days = mc.sessions(START, END)
    try:
        for d in days:                                           # 1) flow, oldest first
            if store.get_checkpoint(f"pre:{d}") == "flow":
                continue
            n = ingest_flow_day(client, store, d)
            store.set_checkpoint(f"pre:{d}", "flow")
            print(f"{d} flow +{n} (count {client.usage.daily_count})", flush=True)
        need_bars, need_ctx, need_vol = set(), set(), set()      # 2) context, only where missing
        for d in days:
            for a, fails, _ in day_trades(store, d):
                if not store.get_ohlc(a.ticker, d, d + timedelta(days=12)):
                    need_bars.add(a.ticker)
                if not fails and a.direction > 0:
                    if store.get_metric(a.ticker, "all", "earnings") is None:
                        need_ctx.add(a.ticker)
                    if a.otm_pct > DEFAULT_FILTER.far_otm and not store.get_metric(a.ticker, "all", "vol_hist"):
                        need_vol.add(a.ticker)
        print(f"context: bars {len(need_bars)}, earnings {len(need_ctx)}, vol {len(need_vol)}", flush=True)
        for fn, tickers in ((lambda t: ingest_bars(client, store, t, None), need_bars),
                            (lambda t: ingest_earnings(client, store, t, None), need_ctx),
                            (lambda t: ingest_realized_vol(client, store, t, date.today()), need_vol)):
            for t in sorted(tickers):
                try:
                    fn(t)
                except UWBudgetExceeded:
                    raise
                except UWError as e:
                    print("skip", t, str(e)[:100], flush=True)
        print(f"DONE (count {client.usage.daily_count})", flush=True)
    except UWBudgetExceeded as e:
        print(f"STOPPED on budget: {e} — rerun after the 20:00 ET reset (resumes)", flush=True)


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 37_500)
