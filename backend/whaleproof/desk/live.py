"""Live UW pulls for Signal Desk. Every call goes through cached_get (UWClient); every source records its own
freshness and error so one failing endpoint or ticker never breaks the page."""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple
from urllib.parse import quote

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.client import (
    UWAuthError,
    UWBlocked,
    UWBudgetExceeded,
    UWError,
    UWQuotaExhausted,
)
from whaleproof.core.data_layer.fetch import cached_get, rows
from whaleproof.core.data_layer.ingest import (
    UW_SECTORS,
    ingest_realized_vol,
    ingest_sector,
)
from whaleproof.core.data_layer.models import alert_to_row, num, parse_alert
from whaleproof.core.data_layer.store import Store
from whaleproof.core.options.live import chain as _chain
from whaleproof.core.options.live import stock_state as _stock_state

from .config import RAW_MIN_PREMIUM, TTL

log = logging.getLogger("signaldesk.live")
FLOW_PATH = "/api/option-trades/flow-alerts"
PAGE = 200
MAX_PAGES = 40


@dataclass
class LiveState:
    """Freshness/error per source + budget, shared by the refresher thread and the API."""
    sources: dict[str, dict] = field(default_factory=dict)
    quota_exhausted: bool = False
    blocked: bool = False
    auth_failed: bool = False
    usage: dict = field(default_factory=dict)
    calls_by_us: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def mark(self, name: str, ok: bool, error: str | None = None) -> None:
        with self.lock:
            prev = self.sources.get(name, {})
            self.sources[name] = {"ok": ok, "error": error,
                                  "at": datetime.now(UTC).isoformat() if ok else prev.get("at"),
                                  "tried": datetime.now(UTC).isoformat()}


def safe(state: LiveState, name: str, fn: Callable[[], Any], default: Any = None) -> Any:
    """Run one live pull; on any UW/network error record it for the UI and return `default`."""
    try:
        out = fn()
    except UWQuotaExhausted as e:
        state.quota_exhausted = True
        state.mark(name, False, f"quota reached — resets 20:00 ET ({e})")
        return default
    except UWBudgetExceeded as e:
        state.quota_exhausted = True
        state.mark(name, False, f"live budget reserve reached — resets 20:00 ET ({e})")
        return default
    except UWBlocked as e:
        state.blocked = True
        state.mark(name, False, f"network blocked (Cloudflare/proxy), not the key: {e}")
        return default
    except UWAuthError as e:
        state.auth_failed = True
        state.mark(name, False, f"UW refused the key/plan: {str(e)[:120]}")
        return default
    except (UWError, OSError, ValueError, KeyError, TypeError) as e:
        log.warning("live source %s failed: %s", name, e)
        state.mark(name, False, str(e)[:200])
        return default
    state.mark(name, True)
    return out


class CacheOnlyClient:
    """Stand-in UW client while live pulls are paused: any cache miss is an error, never a network call."""
    usage = None

    def get(self, path: str, params=None):
        raise UWError(f"cache only (live pulls paused): {path}")


class StaleOkStore:
    """Store view that accepts cached payloads of any age and never writes — for rebuilding panels from the cache."""
    def __init__(self, store: Store):
        self._s = store

    def cache_get(self, key: str, max_age_s: float | None):
        return self._s.cache_get(key, None)

    def cache_put(self, *args) -> None:
        return None

    def __getattr__(self, name):
        return getattr(self._s, name)


class FlowPull(NamedTuple):
    stored: int
    caught_up: bool     # reached an alert already stored or the start of the day (not out of pages / stuck cursor)


def pull_flow_incremental(client, store: Store, d: date) -> FlowPull:
    """Newest-first pages of today's flow alerts until a page reaches an alert we already stored (or a short page).
    Typical steady-state cost: 1 call per refresh.

    A pull cut short (UW error, page cap, stuck cursor) leaves where it stopped in checkpoint `flow_gaps:<day>`; the
    next pulls resume those holes after the top, and the day only counts as caught up once none is left (10-22: before,
    the next pull's own newest alerts made it "caught up" and the hole stayed for good)."""
    key = f"flow_gaps:{d.isoformat()}"
    # UW reads `older_than=<date>` as "through the end of that date": the next date's string started a past day's
    # pull with the whole next day (10-23: Oct 15 never caught up behind Oct 16's 38 pages). Its midnight in New York
    top = str(int(datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=mc.NY).timestamp() * 1000))
    todo: list[str] = [top, *json.loads(store.get_checkpoint(key) or "[]")]
    stored, pages = 0, 0
    try:
        while todo:
            cursor, prev_oldest = todo[0], None
            while True:
                if pages >= MAX_PAGES:
                    return FlowPull(stored, False)
                params = {"limit": PAGE, "min_premium": RAW_MIN_PREMIUM, "newer_than": d.isoformat(), "older_than": cursor}
                batch = rows(cached_get(client, store, FLOW_PATH, params, 0))
                pages += 1
                parsed = [(parse_alert(r), r) for r in batch]
                good = [(a, alert_to_row(a, r)) for a, r in parsed if a and a.session_date == d]
                # `older_than` is inclusive: alerts at the cursor's ms come back from the page before. Only alerts
                # strictly older than the cursor that were already stored mean "caught up" (bug 10-22: the repeats
                # stopped a mid-day start at 11:01, losing 9:30–11:01).
                cut = int(cursor) if cursor.isdigit() else None
                known = _known_ids(store, [g["id"] for a, g in good
                                           if cut is None or a.created_at.timestamp() * 1000 < cut])
                stored += store.upsert_alerts([g for _, g in good])
                alerts = [a for a, _ in parsed if a]
                if len(batch) < PAGE or known:
                    todo.pop(0)
                    break
                oldest = int(min(a.created_at for a in alerts).timestamp() * 1000) if alerts else None
                if oldest is None or (prev_oldest is not None and oldest >= prev_oldest):
                    todo.pop(0)                 # can't page further back: give this hole up, as before
                    return FlowPull(stored, False)
                prev_oldest, cursor = oldest, str(oldest)
                todo[0] = cursor
        return FlowPull(stored, True)
    finally:
        holes = list(dict.fromkeys(c for c in todo if c.isdigit() and c != top))
        if holes or store.get_checkpoint(key) not in (None, "[]"):
            store.set_checkpoint(key, json.dumps(holes))


def _known_ids(store: Store, ids: list[str]) -> bool:
    if not ids:
        return False
    q = ",".join("?" * len(ids))
    return store.conn.execute(f"SELECT 1 FROM flow_alerts WHERE id IN ({q}) LIMIT 1", ids).fetchone() is not None


# ---------- market context ----------
def market_tide(client, store: Store, d: date, live: bool) -> list[dict]:
    rs = rows(cached_get(client, store, "/api/market/market-tide", {"date": d.isoformat(), "interval_5m": True},
                         TTL["tide"] if live else None))
    out = []
    for r in rs:
        c, p = num(r.get("net_call_premium")), num(r.get("net_put_premium"))
        if r.get("timestamp") and c is not None and p is not None:
            out.append({"t": str(r["timestamp"]), "call": c, "put": p, "net": c - p, "volume": num(r.get("net_volume"))})
    return out


def sector_tides(client, store: Store, d: date, live: bool) -> list[dict]:
    out = []
    for s in UW_SECTORS:
        rs = rows(cached_get(client, store, f"/api/market/{quote(s)}/sector-tide", {"date": d.isoformat()},
                             TTL["tide"] if live else None))
        if rs:
            c, p = num(rs[-1].get("net_call_premium")), num(rs[-1].get("net_put_premium"))
            if c is not None and p is not None:
                out.append({"sector": s, "net": c - p, "call": c, "put": p, "t": rs[-1].get("timestamp")})
                # day total for the Market page's recent-sessions rotation (same row the backfill writes)
                store.put_metric(f"SECTOR:{s}", d, "tide", {"net": c - p, "gross": abs(c) + abs(p)})
    return sorted(out, key=lambda x: -x["net"])


def sector_tides_one(client, store: Store, sector: str, d: date) -> list[dict]:
    """One sector's latest tide (cache-friendly single-sector variant of sector_tides)."""
    rs = rows(cached_get(client, store, f"/api/market/{quote(sector)}/sector-tide", {"date": d.isoformat()}, None))
    if not rs:
        return []
    c, p = num(rs[-1].get("net_call_premium")), num(rs[-1].get("net_put_premium"))
    return [{"sector": sector, "net": c - p, "call": c, "put": p, "t": rs[-1].get("timestamp")}] if c is not None and p is not None else []


def gex_levels(client, store: Store, ticker: str, d: date, live: bool) -> dict | None:
    rs = rows(cached_get(client, store, f"/api/stock/{ticker}/gex-levels", {"date": d.isoformat(), "source": "oi"},
                         TTL["gex"] if live else None))
    if not rs:
        return None
    r = rs[0]
    lv = {k: num(r.get(k)) for k in ("call_wall", "put_wall", "gamma_flip", "gamma_magnet")}
    if all(v is None for v in lv.values()):
        return None                     # UW answers a not-yet-computed day with an all-null row
    return lv | {"date": str(r.get("date") or d)[:10]}


def darkpool_levels(client, store: Store, ticker: str, d: date, live: bool, top: int = 5) -> list[dict]:
    rs = rows(cached_get(client, store, f"/api/darkpool/{ticker}/price-levels", {"date": d.isoformat()},
                         TTL["gex"] if live else None))
    lv = [{"price": num(r.get("price")), "volume": num(r.get("dark_pool_volume")) or 0} for r in rs if num(r.get("price"))]
    return sorted(lv, key=lambda x: -x["volume"])[:top]


def economic_calendar(client, store: Store) -> list[dict]:
    rs = rows(cached_get(client, store, "/api/market/economic-calendar", {}, TTL["calendar"]))
    return [{"time": str(r.get("time")), "event": r.get("event"), "forecast": r.get("forecast"),
             "prev": r.get("prev"), "reported_period": r.get("reported_period")} for r in rs if r.get("time")]


def earnings_session(client, store: Store, when: str, d: date, max_pages: int = 5) -> list[dict]:
    """Market-wide earnings list for one session side: when = 'premarket' | 'afterhours'. Pages through UW's 100-row
    limit; rows dated ≠ d are a date fallback, not a hit, and are dropped."""
    rs: list[dict] = []
    for page in range(max_pages):
        got = rows(cached_get(client, store, f"/api/earnings/{when}", {"date": d.isoformat(), "limit": 100,
                                                                        "page": page}, TTL["calendar"]))
        rs += got
        if len(got) < 100:
            break
    return [{"ticker": r.get("symbol") or r.get("ticker"), "report_date": str(r.get("report_date") or d)[:10],
             "report_time": r.get("report_time") or when, "expected_move_perc": num(r.get("expected_move_perc")),
             "sector": r.get("sector"), "marketcap": num(r.get("marketcap")), "has_options": r.get("has_options")}
            for r in rs if (r.get("symbol") or r.get("ticker")) and str(r.get("report_date") or d)[:10] == d.isoformat()]


def refresh_earnings(client, store: Store, ticker: str) -> None:
    """Re-pull /api/earnings/{t} (same cache key as the backfill) so history.earnings_map sees fresh report times."""
    cached_get(client, store, f"/api/earnings/{ticker}", {}, TTL["context"])


def refresh_vol(client, store: Store, ticker: str, today: date) -> None:
    """Far-OTM candidate context: IV rank (the option-value verdict, same basis as every tested window) + realized
    vol (shown as information only)."""
    for r in rows(cached_get(client, store, f"/api/stock/{ticker}/iv-rank", {"timespan": "1y"}, TTL["context"])):
        v = num(r.get("iv_rank_1y"))
        if r.get("date") and v is not None:
            store.put_metric(ticker, str(r["date"])[:10], "iv_rank", v)      # UW scale 0–100
    ingest_realized_vol(client, store, ticker, today)


def sector_of(client, store: Store, ticker: str) -> str | None:
    return ingest_sector(client, store, ticker)


def option_chain(client, store: Store, ticker: str, expiry: str) -> dict[str, dict]:
    """Live listed chain for one expiry (1 call): bid/ask/last/volume/OI/IV per option symbol."""
    return _chain(client, store, ticker, expiry, TTL["flow"])


def stock_state(client, store: Store, ticker: str) -> dict:
    return _stock_state(client, store, ticker, TTL["flow"])
