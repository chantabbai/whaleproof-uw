"""Quick-start: fill an empty cache with the last few sessions so a fresh UW key sees live pages.

Per session, newest first: the day's flow alerts (past days cache forever), then context only for tickers that could
reach a tier (earnings, sector, IV rank + realized vol, daily bars), then the signals' option histories
(signal tracker). History and evidence come from the committed derived JSON, so nothing older is fetched.
Everything goes through cached_get, so a rerun resumes where a stop left off at almost no cost."""
from __future__ import annotations

from datetime import date, datetime

from whaleproof import market_calendar as mc
from whaleproof.core.backtest.simple import day_trades
from whaleproof.core.data_layer.client import UWAuthError, UWBlocked, UWBudgetExceeded, UWError
from whaleproof.core.data_layer.ingest import ingest_bars, ingest_contract_oi, ingest_flow_day
from whaleproof.core.data_layer.models import FlowAlert
from whaleproof.core.data_layer.store import Store

from . import live
from .config import DEFAULT_FILTER, TTL, FilterConfig
from .service import AS_OF_DELAY, INDEXES, compute_signals


class CallCap:
    """UW client wrapper with an optional hard per-run cap (None = no cap, the default since owner 10-16: UW lifted its
    call limits). Usage is measured by UW's own daily counter (it sees retries and anything else on the same
    key); this run's own call count is the floor when no header is available."""

    def __init__(self, client, max_calls: int | None):
        self.c, self.max, self.own, self.base = client, max_calls, 0, None

    def _count(self) -> int | None:
        return getattr(getattr(self.c, "usage", None), "daily_count", None)

    def used(self) -> int:
        n = self._count()
        return max(n - self.base, self.own) if n is not None and self.base is not None else self.own

    def get(self, path: str, params: dict | None = None):
        if self.max is not None and self.used() >= self.max:
            raise UWBudgetExceeded(f"quick-start cap of {self.max} calls reached")
        out = self.c.get(path, params)
        self.own += 1
        if self.base is None and (n := self._count()) is not None:
            self.base = n - 1                      # the counter already includes this first call
        return out

    @property
    def usage(self):
        return getattr(self.c, "usage", None)


def tier_possible(a: FlowAlert, cfg: FilterConfig = DEFAULT_FILTER) -> bool:
    """Could this alert become a signal (or bearish watch)? Size and distance only — context decides the rest."""
    if a.underlying_price < cfg.min_stock_price:
        return False
    return (a.total_premium >= cfg.whale_premium and a.otm_pct > cfg.whale_min_otm) or a.otm_pct > cfg.far_otm


def last_sessions(now: datetime, n: int) -> list[date]:
    """The n most recent completed sessions, newest first."""
    d, out = mc.last_completed_session(now), []
    for _ in range(n):
        out.append(d)
        d = mc.previous_session(d)
    return out


def _context(cap, store: Store, ticker: str, today: date) -> None:
    live.refresh_earnings(cap, store, ticker)
    live.sector_of(cap, store, ticker)
    live.refresh_vol(cap, store, ticker, today)      # IV rank decides far-OTM; whale cards show it as the option value
    ingest_bars(cap, store, ticker, TTL["context"])


def run(client, store: Store, days: list[date], max_calls: int | None, today: date | None = None, log=lambda s: None) -> dict:
    """Backfill `days` (newest first). Stops cleanly at the cap or the daily quota; a day UW refuses (e.g. outside the
    key's history window) is reported and skipped. A refused key or blocked network aborts."""
    today = today or datetime.now(mc.NY).date()     # UW 422s dates past today in New York (users abroad)
    cap = CallCap(client, max_calls)
    res: dict = {"days": [], "stopped": None, "calls": 0}
    try:
        for t in INDEXES:
            ingest_bars(cap, store, t, TTL["context"])
        for d in days:
            try:
                alerts = ingest_flow_day(cap, store, d)
                cands = sorted({a.ticker for a, fails, _ in day_trades(store, d) if not fails and tier_possible(a)})
                for t in cands:
                    _context(cap, store, t, today)
                ds = compute_signals(store, d, mc.session_close(d) + AS_OF_DELAY)
                for s in [*ds.signals, *ds.bearish]:
                    ingest_contract_oi(cap, store, s["contract"], TTL["context"])
                row = {"day": d.isoformat(), "alerts": ds.funnel["raw"], "new_alerts": alerts,
                       "candidates": len(cands), "signals": len(ds.signals), "bearish_watch": len(ds.bearish),
                       "tickers": sorted({s["ticker"] for s in ds.signals})}
            except (UWAuthError, UWBlocked, UWBudgetExceeded):
                raise
            except UWError as e:
                row = {"day": d.isoformat(), "error": str(e)[:200]}
            res["days"].append(row)
            log(f"{row['day']}: " + (f"skipped — {row['error']}" if "error" in row else
                                     f"{row['alerts']} alert{'' if row['alerts'] == 1 else 's'} → {row['signals']} signal{'' if row['signals'] == 1 else 's'} {', '.join(row['tickers'])}"
                                     f" · calls so far {cap.used()}"))
    except UWBudgetExceeded as e:
        res["stopped"] = str(e)
    res["calls"] = cap.used()
    return res
