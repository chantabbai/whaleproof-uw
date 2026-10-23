"""Signal Desk service: which day's data to show, the background refresher, and today's filtered signals.

The refresher is the only place that calls UW (through desk.live → cached_get → UWClient). The API only reads the
snapshot it leaves behind plus the SQLite cache, so pages load fast and a UW outage shows as "stale", never a crash."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from whaleproof import market_calendar as mc
from whaleproof.core.backtest.runner import repeat_count
from whaleproof.core.backtest.simple import day_trades
from whaleproof.core.data_layer.client import UWClient
from whaleproof.core.data_layer.fetch import cache_key, cached_get
from whaleproof.core.data_layer.ingest import ingest_bars, ingest_contract_oi
from whaleproof.desk import live_evidence, surfacing
from whaleproof.core.data_layer.models import FlowAlert, row_to_alert
from whaleproof.core.data_layer.store import Store
from whaleproof.core.options.pricing import value_view

from . import live
from dataclasses import replace

from .budget import BurnMeter, DeskTally, live_allowed, load_usage, pace_factor, save_usage
from .config import FORWARD_START, INDEX_TICKERS, DAILY_LIMIT, DEFAULT_FILTER, EOD_EVERY, EOD_ONLY_THROUGH, LIVE_MODE_DEFAULT, LIVE_RESERVE, OPEN_EVERY, TTL

WATCH_FILTER = replace(DEFAULT_FILTER, longs_only=False)
from .signals import Context, classify, decide, exit_session
from .tracker import close_update, settle_update

log = logging.getLogger("signaldesk.service")
INDEXES = ("SPY", "QQQ", "IWM")
AS_OF_DELAY = timedelta(minutes=15)
VIEW_KEEP_S = 600          # a ticker page opened in the last 10 min keeps its bars/GEX/dark pool fresh
VIEW_EVERY_S = 900         # …refreshed at most every 15 min (≈3 UW calls per ticker per refresh)
VIEW_SPOT_S = 60           # …and its live price at most once a minute on a live day (1 call)
VIEW_MAX = 10              # at most this many viewed tickers per refresh pass
EARN_SESSIONS = 5          # earnings calendar: today (if not yet closed) + the next sessions, labelled cheap/fair/rich
EARN_EVERY_S = 6 * 3600    # ≈ 10 calendar calls per pass
EARN_HIST_MAX = 40         # past-report fetches per pass for tickers with no fresh cached history (biggest first)
EARN_HIST_TTL = 45 * 86400 # a ticker's past reports change once a quarter
REPORTS_DONE_HOUR = 18     # ET: after this, today's earnings reports count as done
PAST_SOFT_S = 300          # keyless reader: an unsaved live day is recomputed at most every 5 min
HOLD_LOOKBACK = 5          # signals from the previous 5 sessions: the oldest sells at today's close


def _cache_time(store: Store, key: str) -> str | None:
    """When a cached payload was fetched (ISO, UTC) — so cache-rebuilt panels show their real age."""
    row = store.conn.execute("SELECT fetched_at FROM raw_cache WHERE key=?", (key,)).fetchone()
    return datetime.fromtimestamp(row[0], UTC).isoformat() if row else None


def data_day(now: datetime) -> date:
    """Session whose flow the desk shows: today once the market has opened, else the last completed session."""
    local = now.astimezone(mc.NY)
    d = local.date()
    if mc.is_session(d) and local >= mc.session_open(d):
        return d
    return mc.last_completed_session(now)


def earnings_for(store: Store, ticker: str) -> list[tuple[date, str]]:
    """(report_date, report_time) from the cached /api/earnings/{t} payload (same key the live refresh updates)."""
    row = store.conn.execute("SELECT payload FROM raw_cache WHERE key=?", (f"/api/earnings/{ticker}?{{}}",)).fetchone()
    if not row:
        return []
    data = json.loads(row[0])
    rs = data.get("data", []) if isinstance(data, dict) else []
    return sorted({(date.fromisoformat(str(r["report_date"])[:10]), str(r.get("report_time") or "unknown"))
                   for r in rs if r.get("report_date")})


def value_for(store: Store, a: FlowAlert) -> dict:
    d = a.session_date.isoformat()
    hist = store.get_metric(a.ticker, "all", "vol_hist") or []
    trailing = [(end, rv) for _, _, rv, end in hist if rv and end and end[:10] <= d]
    ivr = store.latest_metric(a.ticker, a.session_date, "iv_rank")
    # Owner 2026-09-30 (exploratory, post-holdout): the verdict uses IV rank — the basis of every tested window (no
    # cached history alert carries IV). Contract IV vs realized vol is kept as information only.
    v = value_view(None, None, ivr[1] if ivr else None)
    info = value_view(a.iv, max(trailing)[1] if trailing else None, None)
    if info["basis"] == "iv_rv":
        v |= {"iv": a.iv, "rv": info["rv"], "iv_rv": info["iv_rv"],
              "reason": f"{v['reason']}; {info['reason']} — info only" if ivr else f"{info['reason']} — info only"}
    return v


@dataclass
class DaySignals:
    day: str
    as_of: str
    funnel: dict
    signals: list[dict]
    rejected_top: list[dict]
    by_stage: dict
    clusters: list[dict]
    bearish: list[dict] = field(default_factory=list)   # puts passing every step but "bullish only" — untested context
    bets: list[dict] = field(default_factory=list)      # every directional bet of the day + our verdict (Flow check page)


# Cash-settled index options. UW's history replies (backfill, quick-start) omit their stock price, so those days never
# store them; leaving them out here too keeps "alerts came in" the same on live and history days. They can't pass the
# gate (stocks, ADRs and ETFs only), so signals are unaffected.


def compute_signals(store: Store, d: date, as_of: datetime, fetch=None) -> DaySignals:
    """Run every directional ticker-bet of day `d` through the conviction filter. `fetch(ticker, need_vol)` refreshes
    earnings (and realized vol) for candidates that reach those stages — live only; None = cache only."""
    idx = sorted(INDEX_TICKERS)
    raw = store.conn.execute(f"SELECT COUNT(*) FROM flow_alerts WHERE session_date=? AND ticker NOT IN ({','.join('?' * len(idx))})",
                             (d.isoformat(), *idx)).fetchone()[0]
    trades = [t for t in day_trades(store, d) if t[0].ticker not in INDEX_TICKERS]
    by_ticker: dict[str, list[FlowAlert]] = defaultdict(list)
    for r in store.alerts_between(d, d):
        a = row_to_alert(r)
        if a.ticker not in INDEX_TICKERS:
            by_ticker[a.ticker].append(a)
    stages: Counter = Counter()
    signals, rejected, bearish = [], [], []
    sectors: dict[str, str | None] = {}
    for a, fails, _sale in trades:
        if a.ticker not in sectors:
            sectors[a.ticker] = store.get_metric(a.ticker, "all", "sector") or None
        if fails:
            stages["gate"] += 1
            rejected.append(_reject_row(a, "gate", fails[0]))
            continue
        pre, reason, _ = decide(a.direction, a.underlying_price, a.total_premium, a.otm_pct, "unknown", d, [])
        if pre == "direction":
            stages[pre] += 1
            rejected.append(_reject_row(a, pre, reason))
            if (w := _bearish_watch(store, a, d, as_of, by_ticker, fetch)) is not None:
                bearish.append(w)
            continue
        if pre == "liquidity":
            stages[pre] += 1
            rejected.append(_reject_row(a, pre, reason))
            continue
        if fetch:
            fetch(a.ticker, a.otm_pct > DEFAULT_FILTER.far_otm)
        v = value_for(store, a)
        ctx = Context(same_day=by_ticker[a.ticker], earnings=earnings_for(store, a.ticker), value=v["verdict"],
                      value_reason=v["reason"], repeat=repeat_count(store, a, as_of))
        res = classify(a, ctx, as_of)
        if not res.passed:
            stages[res.stage] += 1
            rejected.append(_reject_row(a, res.stage, res.reason))
            continue
        stages["signal"] += 1
        signals.append(_signal_row(store, a, res, v, ctx))
    clusters = _cluster(signals)
    bets = _bets(trades, rejected, signals, sectors)
    rejected.sort(key=lambda r: -r["premium"])
    directional = len(trades)
    clean = directional - stages["gate"]
    return DaySignals(d.isoformat(), as_of.isoformat(),
                      {"raw": raw, "directional": directional, "clean": clean, "signals": len(signals)},
                      sorted(signals, key=lambda s: (s["tier"] != "whale", -s["premium"])), rejected[:40],
                      dict(stages), clusters, sorted(bearish, key=lambda s: -s["premium"]), bets)


def _bets(trades, rejected: list[dict], signals: list[dict], sectors: dict) -> list[dict]:
    """One row per directional bet (same unit as the history rows) with our verdict: 'signal' or the stage that
    stopped it (joined by alert id)."""
    verdict = {s["id"]: ("signal", s["label"]) for s in signals}
    for r in rejected:
        verdict[r["id"]] = (r["stage"], r["reason"])
    out = []
    for a, fails, sale in trades:
        stage, reason = verdict.get(a.id, ("unknown", ""))
        out.append({"id": a.id, "ticker": a.ticker, "direction": a.direction, "opt_type": a.kind,
                    "bet_kind": "clean buy" if not fails else "put sale" if sale else "not a clean buy",
                    "premium": a.total_premium, "strike": a.strike, "expiry": a.expiry.isoformat(), "dte": a.dte,
                    "otm_pct": a.otm_pct, "sweep": bool(a.has_sweep), "sector": sectors.get(a.ticker),
                    "spot_at_alert": a.underlying_price, "created_at": a.created_at.isoformat(),
                    "session_date": a.session_date.isoformat(), "verdict": stage, "reason": reason})
    return out


def _bearish_watch(store: Store, a: FlowAlert, d: date, as_of: datetime, by_ticker, fetch) -> dict | None:
    """Same checks as a signal except direction (WATCH_FILTER). Put buys are NOT validated: shown as context only."""
    pre, _, _ = decide(a.direction, a.underlying_price, a.total_premium, a.otm_pct, "unknown", d, [], WATCH_FILTER)
    if pre == "liquidity":
        return None
    if fetch:
        fetch(a.ticker, a.otm_pct > WATCH_FILTER.far_otm)
    v = value_for(store, a)
    ctx = Context(same_day=by_ticker[a.ticker], earnings=earnings_for(store, a.ticker), value=v["verdict"],
                  value_reason=v["reason"], repeat=repeat_count(store, a, as_of))
    res = classify(a, ctx, as_of, WATCH_FILTER)
    return _signal_row(store, a, res, v, ctx) | {"watch_only": True} if res.passed else None


def _reject_row(a: FlowAlert, stage: str, reason: str) -> dict:
    return {"id": a.id, "ticker": a.ticker, "direction": a.direction, "kind": a.kind, "premium": a.total_premium,
            "strike": a.strike, "expiry": a.expiry.isoformat(), "dte": a.dte, "otm_pct": a.otm_pct,
            "stage": stage, "reason": reason, "created_at": a.created_at.isoformat()}


def _signal_row(store: Store, a: FlowAlert, res, v: dict, ctx: Context) -> dict:
    earn = [e for e in ctx.earnings if e[0] > a.session_date]
    return {"id": a.id, "ticker": a.ticker, "direction": a.direction, "tier": res.tier, "label": res.reason,
            "why": list(res.why), "premium": a.total_premium, "kind": a.kind, "strike": a.strike,
            "expiry": a.expiry.isoformat(), "dte": a.dte, "otm_pct": a.otm_pct, "spot_at_alert": a.underlying_price,
            "contract": a.option_chain, "created_at": a.created_at.isoformat(), "sweep": a.has_sweep, "iv": a.iv,
            "size": a.total_size or a.volume,
            "value": v, "repeat": ctx.repeat, "sector": store.get_metric(a.ticker, "all", "sector") or None,
            "issue_type": a.issue_type, "session_date": a.session_date.isoformat(),
            "entry": mc.next_session(a.session_date).isoformat(), "exit_by": exit_session(a.session_date).isoformat(),
            "next_earnings": {"date": earn[0][0].isoformat(), "time": earn[0][1]} if earn else None}


def _cluster(signals: list[dict]) -> list[dict]:
    """Same-day signals in one sector move together — flag them instead of presenting N independent bets."""
    by: dict[str, list[str]] = defaultdict(list)
    for s in signals:
        by[s["sector"] or "Unknown"].append(s["ticker"])
    out = [{"sector": k, "tickers": sorted(set(v)), "n": len(set(v))} for k, v in by.items()]
    for s in signals:
        n = len(set(by[s["sector"] or "Unknown"]))
        s["cluster"] = {"sector": s["sector"] or "Unknown", "n": n} if n > 1 else None
    return sorted(out, key=lambda c: -c["n"])


@dataclass
class Snapshot:
    """Latest live pulls (in memory). Every block carries its own timestamp."""
    tide: list[dict] = field(default_factory=list)
    tide_day: str | None = None
    sectors: list[dict] = field(default_factory=list)
    gex: dict[str, dict] = field(default_factory=dict)
    spot: dict[str, dict] = field(default_factory=dict)
    calendar: list[dict] = field(default_factory=list)
    earnings_today: dict[str, list[dict]] = field(default_factory=dict)
    earnings_upcoming: list[dict] = field(default_factory=list)
    earnings_at: str | None = None
    signals: DaySignals | None = None
    signals_final: bool = False     # built after a successful flow pull at/after the day's close + 15 min (Track record saves it)
    quotes: dict[str, dict] = field(default_factory=dict)     # live bid/ask/volume of tracked option contracts
    quotes_at: str | None = None
    spot_at: str | None = None
    refreshed_at: str | None = None


def entry_day_tickers(store: Store, tracked: list[dict], now: datetime) -> list[str]:
    """Signals bought at today's open whose bar for today (the entry price) isn't saved yet. Before 10-07 only the
    close job fetched it, so all entry day both pages said 'buying at the open' with no entry price."""
    local = now.astimezone(mc.NY)
    today = local.date()
    if not mc.is_session(today) or local < mc.session_open(today):
        return []
    want = dict.fromkeys(x["ticker"] for x in tracked if x.get("entry") == today.isoformat())
    return [t for t in want if not any(b.date == today for b in store.get_ohlc(t, today, today))]


def earnings_days(now: datetime, n: int = EARN_SESSIONS) -> list[date]:
    """The reporting day (reporting_day) and the sessions after it."""
    out = [reporting_day(now)]
    while len(out) < n:
        out.append(mc.next_session(out[-1]))
    return out


def reporting_day(now: datetime) -> date:
    """The session whose earnings still matter: today until 6 PM ET (after-the-close reports are out by then),
    else the next session. One rule for Sightings, Earnings and the MCP."""
    local = now.astimezone(mc.NY)
    d = local.date()
    if not mc.is_session(d) or local.hour >= REPORTS_DONE_HOUR:
        d = mc.next_session(d)
    return d


def reporting_window(cal: list[dict], now: datetime) -> tuple[str, dict[str, list[dict]]]:
    day = reporting_day(now).isoformat()
    return day, {side: [r for r in cal if r["side"] == side and r["report_date"] == day] for side in ("premarket", "afterhours")}


class DeskService:
    def __init__(self, db_path: Path, api_key: str, watchlist_fn=list, journal_fn=list):
        self.db_path = db_path
        self.api_key = api_key
        self.state = live.LiveState()
        self.snap = Snapshot()
        self.watchlist_fn = watchlist_fn
        self.journal_fn = journal_fn            # tickers of open journal stock trades (priced like the watchlist)
        self._journal_bars: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._last: dict[str, float] = {}
        self.client = UWClient(api_key, daily_cap=DAILY_LIMIT - LIVE_RESERVE) if api_key else None
        self.mode_env = os.environ.get("SIGNALDESK_LIVE", "").strip().lower()
        self.mode = self.mode_env or LIVE_MODE_DEFAULT
        self.live_now = False
        self.burn = BurnMeter()
        self.tally: DeskTally | None = None
        self.pace = 1.0
        self._past: dict[str, DaySignals] = {}          # completed sessions never change → memo forever
        self._past_soft: dict[str, tuple[float, DaySignals]] = {}   # keyless: live days not saved yet (past_day)
        self._flow_ok: dict[str, datetime] = {}         # day → time of the last flow pull that caught up on it
        self._surf: dict | None = None                   # today's surfacing log (signals that came and went)
        self._lev_tried: dict[str, set[str]] = {}        # live evidence: tickers already fetched per close day
        self.live_ev_version = 0                          # bumps when new exit-day prices land
        self.recent: list[DaySignals] = []
        self.catchup_days_fn = list                     # past live days not saved yet (API sets it)
        self._close_now = False                         # a catch-up asked for the close job in this pass
        self.tracker_open_fn = list                     # [(ticker, contract)] of signals still in their hold (API sets it)
        self.tracker_settle_fn = lambda d: []           # tickers whose record uses day d's close (API sets it)
        self.tracker_version = 0                        # bumps after each close update → API recomputes open rows
        self.tracker_last: dict | None = None
        self.viewed: dict[str, float] = {}             # ticker → last time its page was opened
        self.view_ctx: dict[str, dict] = {}            # ticker → {gex, dp, at} fetched for a viewed page

    def caught_up(self, day: str) -> bool:
        """A flow pull reached the day's stored alerts (or its start) after the day's close + 15 min."""
        done = self._flow_ok.get(day)
        return done is not None and done >= mc.session_close(date.fromisoformat(day)) + AS_OF_DELAY

    def recent_days(self, store: Store, day: date, n: int = HOLD_LOOKBACK) -> list[DaySignals]:
        """Signals of the n sessions before `day` (cache only) — still inside their 5-session hold."""
        out, d = [], day
        for _ in range(n):
            d = mc.previous_session(d)
            k = d.isoformat()
            out.append(self.past_day(k, lambda d=d: self._with_frozen_words(
                compute_signals(store, d, mc.session_close(d) + AS_OF_DELAY))))
        return out

    def past_day(self, day: str, compute) -> DaySignals:
        """A completed session's signals, memoized. The live desk keeps them for good (its catch-up drops a stale memo).
        A keyless reader (the MCP) can't see the catch-up: a live day the desk hasn't saved as final yet is reused for
        PAST_SOFT_S only, so it fills in as the desk catches up (10-22: it stayed incomplete until the MCP restarted)."""
        if day in self._past:
            return self._past[day]
        soft = self._past_soft.get(day)
        if soft and time.time() - soft[0] < PAST_SOFT_S:
            return soft[1]
        ds = compute()
        if (self.client is not None or date.fromisoformat(day) < FORWARD_START
                or (self.db_path.parent / "desk" / "live" / f"{day}.json").exists()):
            self._past[day] = ds
        else:
            self._past_soft[day] = (time.time(), ds)
        return ds

    def _with_frozen_words(self, ds: DaySignals) -> DaySignals:
        """A past day Track record already froze keeps the frozen why-lines and value note, so Sightings, the ticker
        page and the MCP say what the record says (10-20: AXTI's realized vol read 104% there, 110% after UW published
        the day's window). Prices, marks and the signal list itself still come from the recompute."""
        p = self.db_path.parent / "desk" / "live" / f"{ds.day}.json"
        try:
            frozen = {s["id"]: s for s in json.loads(p.read_text()) if isinstance(s, dict) and "id" in s} if p.exists() else {}
        except (OSError, ValueError):
            return ds
        for s in ds.signals:
            if f := frozen.get(s["id"]):
                s.update({k: f[k] for k in ("why", "value") if k in f})
        return ds

    def _surf_path(self, day: str) -> Path:
        return self.db_path.parent / "desk" / "live" / f"surfacing-{day}.json"

    def surfacing_log(self, day: str) -> dict:
        """Today's surfacing log, from memory or its file (survives restarts)."""
        if self.client is None:                          # keyless reader (the MCP): the desk keeps writing the file
            return surfacing.load(self._surf_path(day), day)
        if self._surf is None or self._surf["day"] != day:
            self._surf = surfacing.load(self._surf_path(day), day)
        return self._surf

    def view(self, ticker: str) -> None:
        """A ticker page was opened: the refresher fetches its latest bars, GEX and dark-pool levels (the API never
        calls UW itself)."""
        self.viewed[ticker] = time.time()

    def _refresh_viewed(self, store: Store, day: date, live_day: bool, closed: bool = False) -> None:
        """closed = weekend/holiday: prices can't change, so each viewed ticker is fetched once per process."""
        c, st = self.client, self.state
        cutoff = time.time() - VIEW_KEEP_S
        for t in [t for t, at in self.viewed.items() if at < cutoff]:
            del self.viewed[t]
        for t in sorted(self.viewed, key=lambda k: -self.viewed[k])[:VIEW_MAX]:
            key = f"view:{t}"
            if live_day and not closed and self._due(f"vspot:{t}", VIEW_SPOT_S):
                sp = live.safe(st, f"spot:{t}", lambda t=t: live.stock_state(c, store, t))
                if sp:
                    with self._lock:
                        self.view_ctx[t] = self.view_ctx.get(t, {}) | {"spot": sp, "spot_at": datetime.now(UTC).isoformat()}
            if not self._due(key, (float("inf") if key in self._last else 0.0) if closed else VIEW_EVERY_S):
                continue
            live.safe(st, f"bars:{t}", lambda t=t: ingest_bars(c, store, t, VIEW_EVERY_S))
            g = live.safe(st, f"gex:{t}", lambda t=t: live.gex_levels(c, store, t, day, live_day))
            dp = live.safe(st, f"dp:{t}", lambda t=t: live.darkpool_levels(c, store, t, day, live_day, top=6), [])
            # IV rank, realized vol, earnings dates: were only fetched for signal candidates (stale tiles); 12 h cache
            live.safe(st, f"vol:{t}", lambda t=t: live.refresh_vol(c, store, t, datetime.now(mc.NY).date()))
            live.safe(st, f"earnings:{t}", lambda t=t: live.refresh_earnings(c, store, t))
            # sector + company header (UW stock info): 1 call the first time, cached forever
            live.safe(st, f"sector:{t}", lambda t=t: live.sector_of(c, store, t))
            with self._lock:
                self.view_ctx[t] = self.view_ctx.get(t, {}) | {"gex": g, "dp": dp, "at": datetime.now(UTC).isoformat()}

    def cached_view(self, store: Store, ticker: str, day: date) -> dict:
        """Keyless desk (the MCP): the GEX and dark-pool levels the live desk pulled for `ticker` on `day` when its
        page was viewed, read from the shared cache — so both show the same levels. Cache misses leave them out."""
        cc, cs, out = live.CacheOnlyClient(), live.StaleOkStore(store), {}
        for k, fn in (("gex", lambda: live.gex_levels(cc, cs, ticker, day, True)),
                      ("dp", lambda: live.darkpool_levels(cc, cs, ticker, day, True, top=6))):
            try:
                out[k] = fn()
            except Exception:  # noqa: BLE001 — not cached: the older saved levels stay
                pass
        return out

    def _refresh_earnings(self, store: Store, now: datetime) -> None:
        """Earnings calendar (UW premarket/afterhours lists) for the next sessions + past reports for tickers whose
        history isn't cached (the API labels them cheap/fair/rich from the cache)."""
        c, st = self.client, self.state
        cal = []
        for d in earnings_days(now):
            for side in ("premarket", "afterhours"):
                got = live.safe(st, "earnings_cal", lambda d=d, side=side: live.earnings_session(c, store, side, d), [])
                cal += [r | {"side": side} for r in got or []]
        need = sorted({r["ticker"]: r.get("marketcap") or 0 for r in cal}.items(), key=lambda kv: -kv[1])
        missing = [t for t, _ in need if store.cache_get(cache_key(f"/api/earnings/{t}", {}), EARN_HIST_TTL) is None]
        for t in missing[:EARN_HIST_MAX]:
            live.safe(st, f"earnings:{t}", lambda t=t: cached_get(c, store, f"/api/earnings/{t}", {}, EARN_HIST_TTL))
        econ = live.safe(st, "econ_cal", lambda: live.economic_calendar(c, store), [])   # 1 call; was cache-only
        today = now.astimezone(mc.NY).date().isoformat()
        with self._lock:
            if econ:
                self.snap.calendar = econ
            self.snap.earnings_upcoming, self.snap.earnings_at = cal, now.isoformat()
            self.snap.earnings_today = {side: [r for r in cal if r["side"] == side and r["report_date"] == today]
                                        for side in ("premarket", "afterhours")}

    # ----- refresher -----
    def start(self) -> None:
        threading.Thread(target=self._loop, name="signaldesk-refresh", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        store = Store(self.db_path)
        while not self._stop.is_set():
            try:
                self.refresh(store)
            except Exception:
                log.exception("refresh failed")
            self._stop.wait(15)

    def _due(self, key: str, every: float) -> bool:
        now = time.time()
        if now - self._last.get(key, 0) >= every:
            self._last[key] = now
            return True
        return False

    def _every(self, key: str, mstate: str, closed_s: float) -> float:
        """eod mode: EOD_EVERY inside the window. full mode: OPEN_EVERY × budget pace while open, else closed_s.
        Weekend/holiday: the last session's data is final → once per process start (catch-up), then not again."""
        if mstate == "closed":
            return float("inf") if key in self._last else 0.0
        if self.mode == "eod":
            return EOD_EVERY[key] * self.pace
        return OPEN_EVERY[key] * self.pace if mstate == "open" else closed_s

    def refresh(self, store: Store, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        mstate = mc.market_state(now)["state"]
        day = data_day(now)
        live_day = mstate == "open" or (mstate == "after" and day == now.astimezone(mc.NY).date())
        c, st = self.client, self.state
        if c is None:
            st.mark("uw", False, "no UW_API_KEY configured — showing cache only")
        if c is not None and c.usage.daily_count is not None:
            self.burn.add(now, c.usage.daily_count)
            self.pace = pace_factor(c.usage.daily_count, c.usage.daily_limit or DAILY_LIMIT, self.burn.per_min(), now)
        today = now.astimezone(mc.NY).date().isoformat()
        self.mode = self.mode_env or ("eod" if today <= EOD_ONLY_THROUGH else LIVE_MODE_DEFAULT)
        self.live_now = live_allowed(now, self.mode)
        halted = (st.quota_exhausted or st.auth_failed or c is None or self.pace == float("inf")
                  or not self.live_now)
        if not halted and self._due("flow", self._every("flow", mstate, 1800)):
            pulled = live.safe(st, "flow", lambda: live.pull_flow_incremental(c, store, day))
            if getattr(pulled, "caught_up", False):
                self._flow_ok[day.isoformat()] = now
            more = not getattr(pulled, "caught_up", True) and getattr(pulled, "stored", 0) > 0
            price_now = False                           # a past day just caught up: price its signals this pass
            for k in self.catchup_days_fn():            # unsaved past days (desk was off over their close): pull the rest
                if k in self._flow_ok:
                    continue
                past = live.safe(st, "flow", lambda k=k: live.pull_flow_incremental(c, store, date.fromisoformat(k)))
                if getattr(past, "caught_up", False):
                    # score it the way today is scored (candidates' earnings, sector, IV rank) before it counts as
                    # final: long shots need IV rank, which the bare cache lacks (10-22: Sep 30 froze 4 of its 7)
                    pd = date.fromisoformat(k)
                    ds = live.safe(st, f"signals:{k}", lambda pd=pd: compute_signals(
                        store, pd, mc.session_close(pd) + AS_OF_DELAY, lambda t, vol: self._fetch_ctx(store, t, vol)))
                    if ds is None or st.quota_exhausted or st.auth_failed:
                        continue                        # context incomplete: try again next pass
                    self._past[k] = self._with_frozen_words(ds)     # replaces one built before the catch-up
                    self._flow_ok[k] = now
                    price_now = True
                elif getattr(past, "stored", 0) > 0:
                    more = True
            if more:                                    # cut short but still storing (page cap): go on next loop, not
                self._last.pop("flow", None)            # in 30 min or, on a closed day, never (10-22)
            if price_now:                               # else its rows say "waiting" until the close job's next run:
                self._close_now = True                  # 30 min, after 4:15 PM, or never on a weekend (10-23)
        if not halted and self._due("tide", self._every("tide", mstate, 1800)):
            tide = live.safe(st, "tide", lambda: live.market_tide(c, store, day, live_day), [])
            sectors = live.safe(st, "sectors", lambda: live.sector_tides(c, store, day, live_day), [])
            with self._lock:
                self.snap.tide, self.snap.tide_day, self.snap.sectors = tide, day.isoformat(), sectors
        if self._due("signals", self._every("signals", mstate, 1800)):
            as_of = min(now, mc.session_close(day) + AS_OF_DELAY)
            fetch = None if halted else (lambda t, vol: self._fetch_ctx(store, t, vol))
            sig = live.safe(st, "signals", lambda: compute_signals(store, day, as_of, fetch))
            recent = live.safe(st, "recent", lambda: self.recent_days(store, day), [])
            if sig:
                with self._lock:
                    self.snap.signals, self.recent = sig, recent
                    self.snap.signals_final = self.caught_up(day.isoformat())
                # still forming: log what comes and goes. Only the live desk (with a key) writes it; the MCP's keyless
                # service over the same data dir overwrote the desk's entries from a stale copy (10-22)
                if live_day and now < mc.session_close(day) + AS_OF_DELAY and c is not None:
                    log = surfacing.update(self.surfacing_log(day.isoformat()), sig.signals, sig.bets or [], now)
                    surfacing.save(self._surf_path(day.isoformat()), log)
        tracked = self._tracked()
        if not halted and live_day:      # today's buys: fetch today's bar so the entry open is known (≤1 call each, 5 min)
            for t in entry_day_tickers(store, tracked, now):
                if self._due(f"entrybar:{t}", 300):
                    live.safe(st, f"bars:{t}", lambda t=t: ingest_bars(c, store, t, 0))
        if self.client is not None and not (st.quota_exhausted or st.auth_failed):
            self._refresh_journal_bars(store, now)
        if not halted and self._due("oi", self._every("oi", mstate, 3600)):
            for ch in {x["contract"] for x in tracked}:  # next-morning OI publishes ~06:45 ET; 1 call per contract
                live.safe(st, f"oi:{ch}", lambda ch=ch: ingest_contract_oi(c, store, ch, TTL["oi"]))
        if not halted and self._due("gex", self._every("gex", mstate, 900 if mstate == "pre" else 3600)):
            gex_t = list(dict.fromkeys([*INDEXES, *self.watchlist_fn(), *(x["ticker"] for x in tracked)]))
            gex = {t: g for t in gex_t if (g := live.safe(st, f"gex:{t}", lambda t=t: live.gex_levels(
                c, store, t, day, live_day)))}
            with self._lock:
                self.snap.gex = gex
        if not halted and self._due("spot", self._every("spot", mstate, 900 if mstate == "pre" else 3600)):
            tickers = self._spot_tickers(tracked)
            spot = {t: s for t in tickers if (s := live.safe(st, f"spot:{t}", lambda t=t: live.stock_state(c, store, t)))}
            with self._lock:
                self.snap.spot, self.snap.spot_at = spot, now.isoformat()
        if c is not None and not (st.quota_exhausted or st.auth_failed or self.pace == float("inf")):
            every = (float("inf") if "earnings_cal" in self._last else 0.0) if mstate == "closed" else EARN_EVERY_S
            if self._due("earnings_cal", every):
                self._refresh_earnings(store, now)
            self._refresh_viewed(store, day, live_day, mstate == "closed")     # user-asked: also outside the live window
        if not halted and mstate in ("open", "after") and self._due("quotes", self._every("quotes", mstate, 3600)):
            quotes = {}
            for tk, exp in {(x["ticker"], x["expiry"]) for x in tracked}:
                ch = live.safe(st, f"chain:{tk}", lambda tk=tk, exp=exp: live.option_chain(c, store, tk, exp), {})
                quotes |= {x["contract"]: ch[x["contract"]] for x in tracked if x["contract"] in (ch or {})}
            with self._lock:
                self.snap.quotes, self.snap.quotes_at = quotes, now.isoformat()
        close_day = mc.last_completed_session(now)
        if self._close_now and not halted:
            self._close_now = False
            self._last.pop("tracker_close", None)
            close_hours = True
        else:
            close_hours = mstate in ("after", "pre")
        if (not halted and close_hours and now >= mc.session_close(close_day) + AS_OF_DELAY
                and self._due("tracker_close", 1800)):
            res = live.safe(st, "tracker_close", lambda: close_update(c, store, self.tracker_open_fn(), close_day))
            if res:
                self.tracker_last, self.tracker_version = res | {"at": now.isoformat()}, self.tracker_version + 1
        if not halted and self._due("tracker_settle", 1800):
            # next morning: the 16:15 bar can be the last trade before the closing auction, not the official close
            # also the exit-day bars of "Does the filter help?"'s live row (one-way bets whose hold ended that day)
            items = lambda d: [*self.tracker_settle_fn(d), *live_evidence.exit_tickers(store, d)]   # noqa: E731
            got = live.safe(st, "tracker_settle", lambda: settle_update(c, store, items, close_day, now), [])
            if got:
                self.tracker_version += 1
                self.live_ev_version += 1
        if (not halted and mstate in ("after", "pre") and now >= mc.session_close(close_day) + AS_OF_DELAY
                and self._due("live_ev_bars", 1800)):
            # live row of "Does the filter help?": exit-day prices for every one-way bet (1 call per ticker, once a day)
            tried = self._lev_tried.setdefault(close_day.isoformat(), set())
            due = [t for t in live.safe(st, "live_ev_due", lambda: live_evidence.due_tickers(store, close_day), [])
                   if t not in tried]
            for t in due:
                tried.add(t)
                live.safe(st, f"bars:{t}", lambda t=t: ingest_bars(c, store, t, 0))
            if due:
                self.live_ev_version += 1
        if halted and self._due("cache_fill", 600 if c is not None else 60):
            # keyless (the MCP): the live desk keeps writing the cache, so re-read every panel each minute
            self._fill_from_cache(store, day, now, reread=c is None)
        if c is not None:
            u = c.usage
            count, count_at = u.daily_count, None
            if count is not None and self._due("save_usage", 60):
                save_usage(store, count, now)
            if count is None and (last := load_usage(store, now)):
                count, count_at = last["count"], last["at"]          # no call yet this run: last known, with its time
            self.tally = self.tally or DeskTally(store, now)
            own = self.tally.update(now, getattr(u, "sent", 0))
            if u.daily_count is None and own:
                count, count_at = own, None      # UW stopped sending its daily count (~10-07): this desk's own calls
            st.usage = {"count": count, "count_at": count_at, "limit": u.daily_limit or DAILY_LIMIT, "reserve": LIVE_RESERVE,
                        "burn_per_min": self.burn.per_min(),
                        "pace": None if self.pace == float("inf") else round(self.pace, 2),   # JSON has no Infinity
                        "stopped": self.pace == float("inf"), "mode": self.mode, "live_now": self.live_now}
        self.snap.refreshed_at = now.isoformat()

    def _fill_from_cache(self, store: Store, day: date, now: datetime, reread: bool = False) -> None:
        """Live pulls paused (end-of-day mode, quota, no key): rebuild empty panels from the last cached pulls —
        any age, no network. Panels keep their original pull time in the cache, so nothing is presented as fresher.
        reread: rebuild every panel, not only empty ones (a keyless reader of a cache another desk keeps writing)."""
        cc, cs = live.CacheOnlyClient(), live.StaleOkStore(store)

        def get(fn, default):
            try:
                return fn()
            except Exception:  # noqa: BLE001 — a cache miss just leaves the panel empty
                return default
        tracked = self._tracked()
        with self._lock:
            sn = self.snap
            if reread:
                sn.tide, sn.sectors, sn.gex, sn.spot, sn.spot_at = [], [], {}, {}, None
                sn.calendar, sn.earnings_upcoming, sn.earnings_at, sn.earnings_today = [], [], None, {}
                sn.quotes, sn.quotes_at = {}, None
            if not sn.tide:
                sn.tide, sn.tide_day = get(lambda: live.market_tide(cc, cs, day, True), []), day.isoformat()
            if not sn.sectors:
                sn.sectors = [x for sec in live.UW_SECTORS for x in get(
                    lambda sec=sec: live.sector_tides_one(cc, cs, sec, day), [])]
            if not sn.gex:
                sn.gex = {t: g for t in dict.fromkeys([*INDEXES, *(x["ticker"] for x in tracked)])
                          if (g := get(lambda t=t: live.gex_levels(cc, cs, t, day, True), None))}
            if not sn.spot:
                sn.spot = {t: v for t in self._spot_tickers(tracked)
                           if (v := get(lambda t=t: live.stock_state(cc, cs, t), None))}
                sn.spot_at = sn.spot_at or _cache_time(store, "/api/stock/SPY/stock-state?{}")
            if not sn.calendar:
                sn.calendar = get(lambda: live.economic_calendar(cc, cs), [])
            if not sn.earnings_upcoming:
                sn.earnings_upcoming = [r | {"side": side} for d in earnings_days(now)
                                        for side in ("premarket", "afterhours")
                                        for r in get(lambda d=d, side=side: live.earnings_session(cc, cs, side, d), [])]
                sn.earnings_at = sn.earnings_at or _cache_time(store, cache_key(
                    "/api/earnings/premarket", {"date": earnings_days(now)[0].isoformat(), "limit": 100, "page": 0}))
            if not sn.earnings_today:
                today = now.astimezone(mc.NY).date()
                sn.earnings_today = {w: get(lambda w=w: live.earnings_session(cc, cs, w, today), [])
                                     for w in ("premarket", "afterhours")}
            if not sn.quotes:
                for tk, exp in {(x["ticker"], x["expiry"]) for x in tracked}:
                    ch = get(lambda tk=tk, exp=exp: live.option_chain(cc, cs, tk, exp), {})
                    sn.quotes |= {x["contract"]: ch[x["contract"]] for x in tracked if x["contract"] in (ch or {})}
                if tracked:
                    t0 = tracked[0]
                    sn.quotes_at = sn.quotes_at or _cache_time(
                        store, cache_key(f"/api/stock/{t0['ticker']}/option-contracts", {"expiry": t0["expiry"]}))

    def _spot_tickers(self, tracked: list[dict]) -> list[str]:
        """Live price list: indexes, watchlist, open journal trades, tracked signals."""
        return list(dict.fromkeys([*INDEXES, *self.watchlist_fn(), *self.journal_fn(), *(x["ticker"] for x in tracked)]))

    def _refresh_journal_bars(self, store: Store, now: datetime) -> None:
        """One daily-bar pull per open journal ticker per finished session, so the journal's 'last close' is the real
        one (10-20: GWRE showed Oct 14's close on Oct 20). ≈1 call per open trade a day."""
        close_day = mc.last_completed_session(now).isoformat()
        for t in dict.fromkeys(self.journal_fn()):
            if f"{t}:{close_day}" not in self._journal_bars:
                self._journal_bars.add(f"{t}:{close_day}")
                live.safe(self.state, f"bars:{t}", lambda t=t: ingest_bars(self.client, store, t, 0))

    def _tracked(self) -> list[dict]:
        """Signals + bearish-watch rows (today and still inside their hold) whose prices/quotes are tracked live."""
        today = datetime.now(mc.NY).date().isoformat()
        rows = []
        for ds in [self.snap.signals, *self.recent]:
            if ds:
                rows += [x for x in [*ds.signals, *ds.bearish] if x["exit_by"] >= today or ds is self.snap.signals]
        return rows

    def _fetch_ctx(self, store: Store, ticker: str, need_vol: bool) -> None:
        c, st = self.client, self.state
        live.safe(st, f"earnings:{ticker}", lambda: live.refresh_earnings(c, store, ticker))
        live.safe(st, f"sector:{ticker}", lambda: live.sector_of(c, store, ticker))
        if need_vol:
            live.safe(st, f"vol:{ticker}", lambda: live.refresh_vol(c, store, ticker, datetime.now(mc.NY).date()))

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self.snap

