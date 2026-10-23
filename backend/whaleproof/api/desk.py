"""Signal Desk JSON API (/api/desk/*). Reads the SQLite cache, the service snapshot and the user DB only — never UW
directly. Every payload carries `as_of` so the UI can show freshness."""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.models import row_to_alert
from whaleproof.core.verdict.setups import BUY_SHARE
from whaleproof.desk.company import company_info
from whaleproof.desk.config import DEFAULT_FILTER, HOLDOUT, TRAIN, UI_REFRESH_S
from whaleproof.desk.config import FORWARD_START, RAW_MIN_PREMIUM
from whaleproof.core.data_layer.fetch import cache_key, rows
from whaleproof.desk.history import classify_rows, earnings_map, load_raw
from whaleproof.desk import lessons as lessons_mod, live_evidence, surfacing
from whaleproof.desk.postmortem import explain as explain_loss, explain_review, note_rates, review_rates
from whaleproof.desk.plain import plainly, reason as plain_reason
from whaleproof.desk.signals import decide
from whaleproof.core.verdict.setups import DTE_RANGE, GATE_TYPES, MONEYNESS
from whaleproof.core.options.pricing import value_view
from whaleproof.desk.tracker import BENCHMARKS, saved_day, unfinished_day, LIVE_PERIOD, PERIODS, hold_day, still_holding, live_mark, mark_price, option_now, today_move, build_rows, close_items, settle_items, csv_text as tracker_csv_text, frozen_day, rounded as _rounded
from whaleproof.desk.service import (
    AS_OF_DELAY,
    DeskService,
    compute_signals,
    data_day,
    earnings_for,
    reporting_window,
)
from whaleproof.desk import earnings as earn
from whaleproof.desk.lookup import KINDS, Bet, LookupIndex, bet_from_raw
from whaleproof.desk.oi import oi_by_session, oi_record, oi_view
from whaleproof.desk.userdb import UserDB

SHORT_DTE = 7
STALE_DAYS = 7            # cached levels older than this are labelled stale, not shown as current
CITATIONS = [
    {"key": "pan_poteshman_2006", "cite": "Pan, J. & Poteshman, A. (2006). The Information in Option Volume for Future "
     "Stock Prices. Review of Financial Studies 19(3), 871–908.", "supports": "Opening-buy flow predicts next-week "
     "returns; deep OTM most informative → gate (opening buys only) and the far-OTM tier. Caveat: their data identified "
     "opening buys from non-public records; UW flow is public and the opening flag is inferred."},
    {"key": "cremers_weinbaum_2010", "cite": "Cremers, M. & Weinbaum, D. (2010). Deviations from Put-Call Parity and "
     "Stock Return Predictability. JFQA 45(2), 335–367.", "supports": "Related, not the same test: expensive calls "
     "vs puts (put-call parity deviations) predict returns → motivates reading option prices at all; our cheap/fair/rich "
     "view compares IV with realized vol instead."},
    {"key": "xing_zhang_zhao_2010", "cite": "Xing, Y., Zhang, X. & Zhao, R. (2010). What Does the Individual Option "
     "Volatility Smirk Tell Us About Future Equity Returns? JFQA 45(3), 641–662.", "supports": "Steep put skew "
     "precedes weak returns; informed bad-news traders buy OTM puts → background for excluding put buys from the long "
     "signals (they are not traded as short signals either). Skew itself is not shown yet."},
    {"key": "ni_pearson_poteshman_2005", "cite": "Ni, S., Pearson, N. & Poteshman, A. (2005). Stock Price Clustering "
     "on Option Expiration Dates. JFE 78(1), 49–87.", "supports": "Hedging pins prices near big strikes at expiry "
     "→ GEX walls / gamma regime as day-trader levels (context, not a signal)."},
    {"key": "ni_pan_poteshman_2008", "cite": "Ni, S., Pan, J. & Poteshman, A. (2008). Volatility Information Trading "
     "in the Option Market. Journal of Finance 63(3), 1059–1091.", "supports": "Pre-earnings option demand is about "
     "volatility, not direction → earnings-in-hold block."},
]


class TradeIn(BaseModel):
    ticker: str
    direction: int = 1
    entry_price: float
    instrument: str = "stock"
    entry_date: str | None = None
    stop: float | None = None
    size: float | None = None
    setup: str | None = None
    notes: str | None = None
    signal: dict | None = None


class CloseIn(BaseModel):
    exit_price: float
    exit_date: str | None = None


log = logging.getLogger(__name__)

STARTUP_WAIT_S = 90.0     # startup jobs wait at most this long for today's signals, then run anyway


def build_router(svc: DeskService, store, udb: UserDB, jdir: Path, rows_dir: Path) -> APIRouter:
    r = APIRouter(prefix="/api/desk")
    cache: dict[str, object] = {}

    live_ev_lock = threading.Lock()

    def live_window() -> dict | None:
        """Live row of 'Does the filter help?', scored like the four history periods (cache only). Scoring live days
        takes ~25 s, so it runs on a background thread when new exit-day prices land or a session completes; requests
        get the last finished result meanwhile (None until the first one)."""
        end = mc.last_completed_session(datetime.now(UTC))
        key = (svc.live_ev_version, end.isoformat())
        if cache.get("live_ev_key") != key and end >= FORWARD_START and live_ev_lock.acquire(blocking=False):
            cache["live_ev_key"] = key

            def run() -> None:
                try:
                    from whaleproof.commands.evidence import raw_counts, window_report
                    cache["live_ev"] = _finite(live_evidence.report(store, end, raw_counts(store), window_report))
                except Exception:                      # noqa: BLE001 — keep the last good row, retry on the next key
                    cache.pop("live_ev_key", None)
                    log.exception("live evidence failed")
                finally:
                    live_ev_lock.release()
            threading.Thread(target=run, daemon=True, name="live-evidence").start()
        return cache.get("live_ev")  # type: ignore[return-value]

    def evidence() -> dict:
        out = {"live": live_window()}
        for k, name in (("train_post", "desk-evidence.json"), ("holdout", "desk-holdout.json"),
                        ("preperiod", "desk-preperiod.json"), ("preperiod_farotm", "desk-preperiod-farotm.json")):
            p = jdir / name
            out[k] = json.loads(p.read_text()) if p.exists() else None
        return out

    def hist_by_ticker() -> dict[str, list]:
        if "hist" not in cache:
            holdout_run = (jdir / "desk-holdout.json").exists()     # holdout rows only after the one-time test
            rows = classify_rows(load_raw(rows_dir, include_holdout=holdout_run), earnings_map(store))
            by = defaultdict(list)
            for h in rows:
                if h.tier:
                    by[h.ticker].append(h)
            cache["hist"] = by
        return cache["hist"]  # type: ignore[return-value]


    def freshness(at: str | None, max_age_s: float) -> dict:
        """stale only matters while the market is open; otherwise the last session's close data is current."""
        if not at:
            return {"at": None, "age_s": None, "stale": True}
        age = (datetime.now(UTC) - datetime.fromisoformat(at)).total_seconds()
        is_open = mc.market_state(datetime.now(UTC))["state"] == "open"
        return {"at": at, "age_s": age, "stale": is_open and age > max_age_s}

    def day_signals() -> tuple[str, dict | None, list[dict]]:
        snap = svc.snapshot()
        now = datetime.now(UTC)
        day = data_day(now)
        cur = snap.signals
        if cur is None or cur.day != day.isoformat():         # refresher not run yet → compute from cache now
            cur = compute_signals(store, day, min(now, mc.session_close(day) + AS_OF_DELAY))
        recent = svc.recent or svc.recent_days(store, day)
        signals_ready.set()
        return day.isoformat(), cur.__dict__, [x.__dict__ for x in recent]

    signals_ready = threading.Event()

    def after_signals(job):
        """Cold start 10-16: the Track record warm-up and the bet-history index used to start with the server and share
        the CPU with the first Sightings load (restart → home 40–75 s). They wait until today's signals exist (the
        refresher's first pass or a first page), at most STARTUP_WAIT_S."""
        def run() -> None:
            end = time.monotonic() + STARTUP_WAIT_S
            while not signals_ready.is_set() and svc.snapshot().signals is None and time.monotonic() < end:
                signals_ready.wait(0.25)
            job()
        return run

    def now_forming(day: str) -> bool:
        """True while `day`'s flow can still change: the filter's decision time is the close + 15 min."""
        return datetime.now(UTC) < mc.session_close(date.fromisoformat(day)) + AS_OF_DELAY

    def mark_now(ticker: str, entry_on: date, direction: int) -> dict:
        """An open hold priced now (live while the market is open, else the last close) — Sightings, ticker page and
        Track record all read this, so the same hold shows the same number everywhere."""
        snap = svc.snapshot()
        bars = store.get_ohlc(ticker, entry_on, datetime.now(mc.NY).date())
        return live_mark(bars, entry_on, direction, (snap.spot.get(ticker) or {}).get("last"), snap.spot_at,
                         datetime.now(UTC))

    def move_today(ticker: str, entry_on: date, direction: int) -> dict:
        """The hold's move today for the Sightings tape (same price as mark_now, against yesterday's close) and that price
        itself, which the signal card shows next to the price at the bet even before the entry open."""
        snap = svc.snapshot()
        today = datetime.now(mc.NY).date()
        bars = store.get_ohlc(ticker, today - timedelta(days=20), today)   # holds are at most 5 sessions old
        m = today_move(bars, entry_on, direction, (snap.spot.get(ticker) or {}).get("last"), snap.spot_at, datetime.now(UTC))
        return {"today_move": m["move"], "today_day": m["day"].isoformat() if m["day"] else None, "price_now": m["price"],
                "today_since": m["since"]}

    def with_marks(sigs: list[dict]) -> list[dict]:
        snap = svc.snapshot()
        out = []
        for s in sigs:
            mk = mark_now(s["ticker"], date.fromisoformat(s["entry"]), s["direction"])
            entry, now_px, src, m = mk["entry"], mk["price"], mk["source"], mk
            q = snap.quotes.get(s["contract"])
            oi = oi_view(store, s["contract"], s["session_date"], s.get("size"))
            if oi["confirmed"] is False:     # how such signals did in the record (exploratory, research/oi-confirm.json)
                oi["record"] = oi_record(jdir / "research" / "oi-confirm.json")
            out.append(s | {"quote": q | {"at": snap.quotes_at} if q else None, "spot_at": snap.spot_at, "oi": oi, "entry_price": entry, "last_price": now_px, "since_entry": m["move"],
                            "since_entry_net": m["net"], "hold_day": hold_day(date.fromisoformat(s["entry"]), datetime.now(UTC)), "price_source": "live" if src == "live" else "last close"}
                       | move_today(s["ticker"], date.fromisoformat(s["entry"]), s["direction"]))
        return out

    def full_cards(sigs: list[dict], d: date) -> list[dict]:
        """The full signal card (marks + open interest + IV rank, gamma, dark pool, accumulation, earnings) — one
        builder for Sightings and the ticker page, so a signal reads the same on both (bug 10-07: no OI on ticker)."""
        out = []
        for s in with_marks(sigs):
            t = s["ticker"]
            ivr = store.latest_metric(t, d, "iv_rank")
            live_g = svc.snapshot().gex.get(t)
            cached_g = store.latest_metric(t, d, "gex")
            gex = (date.fromisoformat(live_g["date"]), live_g) if live_g else cached_g
            dp = store.latest_metric(t, d, "dp_levels")
            out.append(s | {"iv_rank": ivr[1] if ivr else None, "gex": gex[1] if gex else None,
                            "gex_date": gex[0].isoformat() if gex else None,
                            "gex_stale": bool(gex) and (d - gex[0]).days > STALE_DAYS,
                            "dp_stale": bool(dp) and (d - dp[0]).days > STALE_DAYS,
                            "dp_levels": sorted(dp[1], key=lambda x: -x[1])[:3] if dp else [],
                            "accumulation": _accumulation(store, t, s["direction"], d),
                            "earnings_warning": _earn_warn(store, t, d)})
        return out

    @r.get("/status")
    def status() -> dict:
        snap, st = svc.snapshot(), svc.state
        now = datetime.now(UTC)
        failing = {k: v["error"] for k, v in st.sources.items() if not v["ok"]}
        u = st.usage or {}
        return {"clock": mc.market_state(now), "data_day": data_day(now).isoformat(), "refreshed_at": snap.refreshed_at,
                "usage": u, "quota_exhausted": st.quota_exhausted, "blocked": st.blocked, "auth_failed": st.auth_failed,
                "live_enabled": svc.client is not None, "failing": failing,
                "sources_ok": sum(1 for v in st.sources.values() if v["ok"]), "sources_total": len(st.sources),
                "refresh_s": UI_REFRESH_S}

    @r.get("/today")
    @plainly
    def today() -> dict:
        snap = svc.snapshot()
        day, cur, recent = day_signals()
        ev = evidence()
        gex_all = {t: snap.gex.get(t) or _cached_gex(store, t, date.fromisoformat(day)) for t in ("SPY", "QQQ", "IWM")}
        spy_g, spy_px = gex_all.get("SPY"), (snap.spot.get("SPY") or {}).get("last")
        gamma = None
        if spy_g and spy_g.get("gamma_flip") and spy_px:
            pos = spy_px >= spy_g["gamma_flip"]
            gamma = {"positive": pos, "spot": spy_px, "flip": spy_g["gamma_flip"], "date": spy_g.get("date"),
                     "text": ("Positive gamma: SPY above its gamma flip, so dealer hedging tends to sell rallies and buy dips (damped moves)"
                              if pos else "Negative gamma: SPY below its gamma flip, so dealer hedging tends to sell drops and buy rallies (moves run)")}
        tide_last = snap.tide[-1] if snap.tide else None
        today_iso = datetime.now(mc.NY).date().isoformat()
        active = [s for d in recent for s in d["signals"] if still_holding(date.fromisoformat(s["exit_by"]), datetime.now(UTC))]
        bearish = [*((cur or {}).get("bearish") or []), *[s for d in recent for s in d.get("bearish", []) if still_holding(date.fromisoformat(s["exit_by"]), datetime.now(UTC))]]
        forming = now_forming(day)
        entering = [s for d in recent for s in d["signals"] if s["entry"] == today_iso]
        # quiet-day fallback: the most recent earlier day with signals (last 5 sessions, else the history rows)
        last = next((d for d in sorted(recent, key=lambda d: d["day"], reverse=True) if d["signals"]), None)
        if last:
            latest = {"day": last["day"], "tickers": list(dict.fromkeys(x["ticker"] for x in last["signals"]))}
        else:
            hist = [h for rows in hist_by_ticker().values() for h in rows if h.session_date.isoformat() < day]
            top = max((h.session_date for h in hist), default=None)
            latest = {"day": top.isoformat(), "tickers": sorted({h.ticker for h in hist if h.session_date == top})} if top else None
        rep_day, rep = reporting_window(snap.earnings_upcoming, datetime.now(UTC))
        if not snap.earnings_upcoming:                     # calendar not pulled yet: keep the cache-built list
            rep_day, rep = datetime.now(mc.NY).date().isoformat(), snap.earnings_today
        surf = svc.surfacing_log(day)                      # signals that surfaced today and the ones that went back under
        first = {k: v["first_seen"] for k, v in surf["seen"].items()}
        return {"day": day, "forming": forming, "entering": with_marks(entering), "latest": latest,
                "surfacing": {"first_seen": first, "went_under": surfacing.went_under(surf)}, "funnel": cur["funnel"] if cur else None, "by_stage": cur["by_stage"] if cur else {},
                "signals": with_marks(cur["signals"]) if cur else [], "clusters": cur["clusters"] if cur else [],
                "active": with_marks(active), "bearish": with_marks(bearish), "rejected_top": (cur or {}).get("rejected_top", [])[:12],
                "regime": {"tide_last": tide_last, "tide_day": snap.tide_day, "gamma": gamma,
                           "tide": snap.tide[::3], "gex": gex_all, "spot": {k: snap.spot.get(k) for k in ("SPY", "QQQ", "IWM")},
                "spy_today": move_today("SPY", date(2000, 1, 1), 1)},
                "events": {"calendar": _calendar_window(snap.calendar), "earnings": rep, "earnings_day": rep_day},
                "evidence": _headline(ev), "freshness": {"signals": freshness(cur["as_of"] if cur else None, 900),
                                                         "tide": freshness(svc.state.sources.get("tide", {}).get("at"), 900)}}

    @r.get("/swing")
    @plainly
    def swing() -> dict:
        day, cur, recent = day_signals()
        sigs = [*((cur or {}).get("signals") or []), *[s for d in recent for s in d["signals"]
                                                        if still_holding(date.fromisoformat(s["exit_by"]), datetime.now(UTC))]]
        d = date.fromisoformat(day)
        enriched = full_cards(sigs, d)
        bearish = [*((cur or {}).get("bearish") or []), *[s for d in recent for s in d.get("bearish", [])
                                                          if still_holding(date.fromisoformat(s["exit_by"]), datetime.now(UTC))]]
        return {"day": day, "forming": now_forming(day), "signals": enriched, "bearish": with_marks(bearish), "rotation": _rotation(store, d),
                "earnings_watch": _earnings_watch(store, [*udb.watchlist(), *{s["ticker"] for s in sigs}], d),
                "earnings_next": _earnings_next(store, [*udb.watchlist(), *{s["ticker"] for s in sigs}], d)}

    @r.get("/day")
    def day_traders() -> dict:
        snap = svc.snapshot()
        day = data_day(datetime.now(UTC))
        wl = udb.watchlist()
        rows = [row_to_alert(x) for x in store.alerts_between(day, day)]
        short = [a for a in rows if a.dte <= SHORT_DTE and not a.has_multileg and a.ask_share >= BUY_SHARE]
        by_t: dict[str, dict] = {}
        for a in short:
            b = by_t.setdefault(a.ticker, {"ticker": a.ticker, "calls": 0.0, "puts": 0.0, "n": 0, "top": None})
            b["calls" if a.kind == "call" else "puts"] += a.total_premium
            b["n"] += 1
            if b["top"] is None or a.total_premium > b["top"]["premium"]:
                b["top"] = {"premium": a.total_premium, "kind": a.kind, "strike": a.strike, "expiry": a.expiry.isoformat(),
                            "dte": a.dte, "at": a.created_at.isoformat(), "sweep": a.has_sweep}
        board = sorted(by_t.values(), key=lambda b: -(b["calls"] + b["puts"]))[:25]
        for b in board:
            b["net"] = b["calls"] - b["puts"]
            b["watch"] = b["ticker"] in wl
        levels = {}
        for t in dict.fromkeys(["SPY", "QQQ", "IWM", *wl]):
            g = snap.gex.get(t) or _cached_gex(store, t, day)
            dp = store.latest_metric(t, day, "dp_levels")     # shown with its day: often weeks old (KTOS: Feb 24)
            levels[t] = {"spot": snap.spot.get(t), "gex": g or None,
                         "dp_top": sorted(dp[1], key=lambda x: -x[1])[:3] if dp else [],
                         "dp_date": dp[0].isoformat() if dp else None}
        return {"day": day.isoformat(), "short_dte_board": board, "short_dte_total": len(short),
                "tide": snap.tide, "tide_day": snap.tide_day, "sectors": snap.sectors, "levels": levels,
                "freshness": {"flow": freshness(svc.state.sources.get("flow", {}).get("at"), 180),
                              "tide": freshness(svc.state.sources.get("tide", {}).get("at"), 600)},
                "note": "Short-dated flow is context only: the conviction filter (and its backtest) covers 7–90 DTE."}

    @r.get("/ticker/{ticker}")
    @plainly
    def ticker(ticker: str) -> dict:
        t = ticker.strip().upper()
        if not t.replace(".", "").replace("-", "").isalnum() or len(t) > 10:
            raise HTTPException(400, "bad ticker")
        svc.view(t)                                  # refresher fetches fresh bars/GEX/dark pool for this ticker
        day = data_day(datetime.now(UTC))
        start = day - timedelta(days=30)
        alerts = [row_to_alert(x) for x in store.alerts_between(start, day, t)]
        daily: dict[str, dict] = {}
        for a in alerts:
            b = daily.setdefault(a.session_date.isoformat(), {"date": a.session_date.isoformat(), "bull": 0.0, "bear": 0.0,
                                                             "other": 0.0, "n": 0})
            b["bull" if a.direction > 0 else "bear" if a.direction < 0 else "other"] += a.total_premium
            b["n"] += 1
        bars = [{"date": b.date.isoformat(), "open": b.open, "high": b.high, "low": b.low, "close": b.close}
                for b in store.get_ohlc(t, day - timedelta(days=180), day)]
        ivr = [{"date": d, "v": json.loads(p)} for d, p in store.conn.execute(
            "SELECT date, payload FROM daily_metric WHERE ticker=? AND kind='iv_rank' AND date>=? ORDER BY date",
            (t, (day - timedelta(days=365)).isoformat()))]
        vol = [v for v in (store.get_metric(t, "all", "vol_hist") or []) if v[0] >= (day - timedelta(days=120)).isoformat()]
        snap = svc.snapshot()
        fresh = svc.view_ctx.get(t) or (svc.cached_view(store, t, day) if svc.client is None else {})
        gex_live = fresh.get("gex") or snap.gex.get(t)
        gex = store.latest_metric(t, day, "gex")
        if gex_live and (not gex or gex_live["date"] >= gex[0].isoformat()):
            gex = (date.fromisoformat(gex_live["date"]), {k: v for k, v in gex_live.items() if k != "date"})
        dp = _fresh_dp(store, t, day)
        if fresh.get("dp"):
            dp = (day, [[x["price"], x["volume"]] for x in fresh["dp"]])
        earn = earnings_for(store, t)
        # newest session first (its 10 biggest always shown), then the 12 biggest earlier ones; newest day on top
        last = max((a.session_date for a in alerts), default=None)
        top = (sorted((a for a in alerts if a.session_date == last), key=lambda a: -a.total_premium)[:10]
               + sorted((a for a in alerts if a.session_date != last), key=lambda a: -a.total_premium)[:12])
        top.sort(key=lambda a: (a.session_date, a.total_premium), reverse=True)
        _, cur, recent = day_signals()                              # the refresher's snapshot, not a recompute
        holding = [s for d in recent for s in d["signals"] if s["ticker"] == t and still_holding(date.fromisoformat(s["exit_by"]), datetime.now(UTC))]
        return {"ticker": t, "day": day.isoformat(), "sector": store.get_metric(t, "all", "sector") or None,
                "company": company_info(store, t),             # name, logo, description (UW stock info, cache only)
                "history_loaded": bool(hist_by_ticker()),        # False on a quick-start install (no history rows)
                "watch": t in udb.watchlist(), "flow_daily": sorted(daily.values(), key=lambda x: x["date"]),
                "top_alerts": [{"premium": a.total_premium, "kind": a.kind, "strike": a.strike, "expiry": a.expiry.isoformat(),
                                "dte": a.dte, "ask_share": a.ask_share, "direction": a.direction, "sweep": a.has_sweep,
                                "opening": a.all_opening, "date": a.session_date.isoformat(), "otm_pct": a.otm_pct}
                               for a in top],
                "spot": fresh.get("spot") or snap.spot.get(t), "spot_at": fresh.get("spot_at") or (snap.spot_at if snap.spot.get(t) else None),
                "bars": bars, "iv_rank": ivr, "vol": vol, "gex": gex[1] | {"date": gex[0].isoformat()} if gex else None,
                "dp_levels": sorted(dp[1], key=lambda x: -x[1])[:6] if dp else [],
                "earnings": [{"date": e.isoformat(), "time": w} for e, w in earn if e >= day - timedelta(days=400)][-6:],
                "signal_today": full_cards([s for s in cur["signals"] if s["ticker"] == t], day),
                "holding": full_cards(holding, day),   # an earlier signal still inside its five-day hold
                "rejected_today": [{"premium": b["premium"], "strike": b["strike"], "kind": b["opt_type"], "reason": b["reason"]}
                                   for b in sorted(cur.get("bets") or [], key=lambda b: -b["premium"])
                                   if b["ticker"] == t and b["verdict"] != "signal"][:5],
                "updating": (svc.client is not None and t not in svc.view_ctx
                             and not (svc.state.quota_exhausted or svc.state.auth_failed)),
                "fresh_at": fresh.get("at"),
                "earnings_view": earnings_card(t),
                # same rows as Track record (history + live), so a signal's result reads the same on both pages
                "past_signals": [{"date": x["session_date"], "tier": x["tier"], "direction": x["direction"],
                                  "premium": x["premium"], "otm_pct": x["otm_pct"],
                                  "x5": x["stock"]["vs_spy"] if done else None, "ret": x["stock"]["ret"] if done else None,
                                  "period": x["period"]}
                                 for x in tracker_rows() if x["ticker"] == t
                                 for done in [x["stock"]["status"] == "closed"]],
                "benchmark": t in BENCHMARKS}

    # ----- earnings (W2, exploratory): implied move vs the ticker's own past report moves -----
    def earnings_upcoming() -> list[dict]:
        snap = svc.snapshot()
        key = ("earn", snap.earnings_at, len(snap.earnings_upcoming))
        if cache.get("earn_key") != key:
            tick = {c["ticker"] for c in snap.earnings_upcoming}
            reps = {t: r for t in tick if (r := earn.load_reports(store, t))}
            cache["earn_rows"], cache["earn_key"] = earn.upcoming(snap.earnings_upcoming, reps), key
        return cache["earn_rows"]  # type: ignore[return-value]

    @r.get("/earnings")
    def earnings() -> dict:
        bp = jdir / "research" / "earnings-moves.json"
        first, _ = reporting_window([], datetime.now(UTC))          # after the close, today's reports are done
        now = datetime.now(UTC)
        rows = [x | {"reported": earn.reported(x, now)} for x in earnings_upcoming() if x["date"] >= first]
        return {"at": svc.snapshot().earnings_at, "upcoming": rows,
                "sessions": sorted({x["date"] for x in rows}),
                "backtest": json.loads(bp.read_text()) if bp.exists() else None,
                "thresholds": {"cheap_below": earn.CHEAP, "rich_above": earn.RICH, "min_past": earn.MIN_PAST,
                               "max_past": earn.MAX_PAST}}

    def earnings_card(t: str) -> dict:
        now = datetime.now(UTC)
        v = earn.ticker_view(t, earn.load_reports(store, t), svc.snapshot().earnings_upcoming, now.astimezone(mc.NY).date())
        if v["next"]:                       # reported before today's open: say it's out, like the Earnings page
            v["next"]["reported"] = earn.reported(v["next"], now)
        return v

    @r.get("/earnings/{ticker}")
    def earnings_ticker(ticker: str) -> dict:
        t = ticker.strip().upper()
        if not t.replace(".", "").replace("-", "").isalnum() or len(t) > 10:
            raise HTTPException(400, "bad ticker")
        return earnings_card(t)

    # ----- watchlist -----
    @r.get("/watchlist")
    @plainly
    def watchlist() -> dict:
        snap = svc.snapshot()
        day, cur, recent = day_signals()
        sig_by = {s["ticker"]: s for d in [cur or {}, *recent] for s in d.get("signals", [])}
        d = date.fromisoformat(day)
        out = []
        for t in udb.watchlist():
            bars = store.get_ohlc(t, d - timedelta(days=10), d)
            flow = [row_to_alert(x) for x in store.alerts_between(d, d, t)]
            out.append({"ticker": t, "spot": snap.spot.get(t), "last_close": bars[-1].close if bars else None,
                        "prev_close": bars[-2].close if len(bars) > 1 else None,
                        "flow_today": {"n": len(flow), "bull": sum(a.total_premium for a in flow if a.direction > 0),
                                       "bear": sum(a.total_premium for a in flow if a.direction < 0)},
                        "signal": sig_by.get(t), "earnings_warning": _earn_warn(store, t, d)})
        return {"day": day, "tickers": out}

    @r.post("/watchlist/{ticker}")
    def watch_add(ticker: str) -> dict:
        try:
            udb.watch_add(ticker)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"watchlist": udb.watchlist()}

    @r.delete("/watchlist/{ticker}")
    def watch_remove(ticker: str) -> dict:
        try:
            udb.watch_remove(ticker)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"watchlist": udb.watchlist()}

    # ----- journal -----
    @r.get("/journal")
    @plainly
    def journal() -> dict:
        return {"trades": [{**t, "now": trade_now(t)} for t in udb.trades()], "stats": udb.stats()}

    def trade_now(t: dict) -> dict | None:
        """An open stock trade priced now (owner 10-08): the same price Sightings shows (live while the market is open,
        the last close after), against the price the owner logged. Options and closed trades: None."""
        if t.get("status") == "closed" or (t.get("instrument") or "stock") != "stock" or not t.get("entry_price"):
            return None
        snap = svc.snapshot()
        today = datetime.now(mc.NY).date()
        bars = store.get_ohlc(t["ticker"], today - timedelta(days=10), today)
        price, src = mark_price((snap.spot.get(t["ticker"]) or {}).get("last"), snap.spot_at, bars, datetime.now(UTC))
        if price is None:
            return None
        move = (price / t["entry_price"] - 1) * t["direction"]
        return {"price": price, "source": src, "at": snap.spot_at if src == "live" else None,
                "date": bars[-1].date.isoformat() if src == "close" else today.isoformat(), "move": move,
                "pnl": (price - t["entry_price"]) * t["direction"] * t["size"] if t.get("size") else None}

    @r.post("/journal")
    def journal_add(t: TradeIn) -> dict:
        body = t.model_dump()
        if not body.get("signal"):
            body["signal"] = _find_signal(svc, store, body["ticker"])       # auto-snapshot the signal at entry
        try:
            return {"id": udb.trade_add(body)}
        except ValueError as e:
            raise HTTPException(400, str(e))

    @r.post("/journal/{trade_id}/close")
    def journal_close(trade_id: int, c: CloseIn) -> dict:
        try:
            udb.trade_close(trade_id, c.exit_price, c.exit_date)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"ok": True}

    @r.delete("/journal/{trade_id}")
    def journal_delete(trade_id: int) -> dict:
        udb.trade_delete(trade_id)
        return {"ok": True}

    @r.get("/journal.csv", response_class=PlainTextResponse)
    def journal_csv() -> str:
        return udb.export_csv()

    @r.get("/methodology")
    def methodology() -> dict:
        ev = evidence()
        sp = jdir / "desk-structures.json"
        cp = jdir / "research" / "compound-stock-signals.json"     # exploratory portfolio simulation (stock)
        bp = jdir / "research" / "beta-adjusted.json"              # exploratory beta-adjusted returns
        hp = jdir / "research" / "holding-period.json"             # exploratory 5/10/20/30-session holds
        op = jdir / "research" / "oi-confirm.json"                 # exploratory next-morning open interest check
        return {"structures": json.loads(sp.read_text()) if sp.exists() else None,
                "compound": json.loads(cp.read_text()) if cp.exists() else None,
                "beta": json.loads(bp.read_text()) if bp.exists() else None,
                "holding": json.loads(hp.read_text()) if hp.exists() else None,
                "oi_confirm": json.loads(op.read_text()) if op.exists() else None,
                "filter": DEFAULT_FILTER.as_dict(), "windows": {"train": [str(TRAIN[0]), str(TRAIN[1])],
                "holdout": [str(HOLDOUT[0]), str(HOLDOUT[1])]}, "evidence": ev, "citations": CITATIONS}


    # ----- signal tracker: every signal, history + live, priced at the daily close -----
    def forward_start() -> date:
        hist = [h for v in hist_by_ticker().values() for h in v]
        last = max((h.session_date for h in hist), default=FORWARD_START - timedelta(days=1))
        return max(mc.next_session(last), FORWARD_START)

    def unsaved_past_days() -> list[str]:
        """Past live days with no saved file: the refresher catches up on their alerts before they're saved."""
        today, out, d = data_day(datetime.now(UTC)), [], forward_start()
        while d < today:
            if not (rows_dir / "live" / f"{d.isoformat()}.json").exists():
                out.append(d.isoformat())
            d = mc.next_session(d)
        return out

    svc.catchup_days_fn = unsaved_past_days

    def live_signal_days() -> list[dict]:
        """Signals of sessions after the last history row (the forward record), decided ones only."""
        day_s, cur, _ = day_signals()
        out, d = [], forward_start()
        while d <= date.fromisoformat(day_s):
            k = d.isoformat()
            if k == day_s:
                if cur and not now_forming(day_s):
                    snap = svc.snapshot()     # saved only once the refresher caught up on the day's alerts (bug 10-16)
                    final = snap.signals_final and snap.signals is not None and snap.signals.day == day_s
                    sigs = snap.signals.signals if final else cur["signals"]
                    out += saved_day(rows_dir / "live", k, lambda: sigs, final)
            else:
                def past(d=d, k=k) -> list[dict]:
                    return svc.past_day(k, lambda: compute_signals(store, d, mc.session_close(d) + AS_OF_DELAY)).signals
                out += saved_day(rows_dir / "live", k, past, svc.caught_up(k))
            d = mc.next_session(d)
        return out

    tracker_lock = threading.Lock()

    def tracker_rows() -> list[dict]:
        with tracker_lock:                           # one build at a time (startup warm-up vs first page load)
            live_rows = live_signal_days()
            key = (svc.tracker_version, data_day(datetime.now(UTC)).isoformat(), tuple(s["id"] for s in live_rows),
                   unfinished_day(datetime.now(UTC)))       # the close turns today's candle into a real close
            if cache.get("tracker_key") != key:
                hist = [h for v in hist_by_ticker().values() for h in v]
                cache["tracker"] = _rounded(build_rows(store, hist, live_rows))
                cache["tracker_key"] = key
            return cache["tracker"]  # type: ignore[return-value]

    svc.tracker_open_fn = lambda: close_items(tracker_rows(), mc.last_completed_session(datetime.now(UTC)))
    svc.tracker_settle_fn = lambda d: settle_items(tracker_rows(), d)

    @r.get("/tracker")
    @plainly
    def tracker() -> dict:
        rows = tracker_rows()
        through = max((x["stock"]["priced_through"] or "" for x in rows), default="") or None
        now = datetime.now(UTC)
        def held(x: dict) -> dict:      # still in its hold: day N of 5 + the live price Sightings shows (display only)
            if x["stock"]["status"] == "closed":
                return x
            e = date.fromisoformat(x["entry_on"])
            snap = svc.snapshot()
            opt = x["option"] and x["option"] | {"now": option_now(x["option"]["buy"], snap.quotes.get(x["option"]["contract"]),
                                                                   snap.quotes_at, now)}
            return x | {"hold_day": hold_day(e, now), "option": opt,
                        "stock": x["stock"] | {"now": mark_now(x["ticker"], e, x["direction"])}}
        h = _headline(evidence()) or {}
        names = dict(zip(("post", "holdout", "train", "pre"), PERIODS)) | {"live": LIVE_PERIOD}
        # all one-way UW alerts in the same period (the 'Does the filter help?' comparison), per tracker period name
        baseline = {names[k]: {"mean": w["all"].get("mean"), "n": w["all"].get("n"), "unpriced": w.get("unpriced"),
                                 "open": w.get("open")}
                    for k, w in h.items() if k in names and w}
        return {"as_of": now.isoformat(), "rows": [held(_without_paths(x)) for x in rows], "baseline": baseline,
                "priced_through": through, "history_loaded": bool(hist_by_ticker()),
                "last_close_update": svc.tracker_last, "periods": [LIVE_PERIOD, *PERIODS],
                "note": "The stock is bought at the next open and sold at the close of the fifth session, minus 0.10% in "
                        "costs, the same as the backtest. The option is the whale's own contract, bought at the entry "
                        "day's open plus half the bid-ask gap and sold at the closing bid. Finished results use daily "
                        "closes; signals still in their hold show the live price while the market is open. This is a "
                        "record of what happened, not proof."}

    @r.get("/tracker/{sid}/path")
    def tracker_path(sid: str) -> dict:
        """Daily closes for one signal (stock vs entry, option closing bid vs paid) and, for a finished signal that
        lagged the S&P 500, descriptive 'why it lost' notes — loaded when a row is expanded."""
        rows = tracker_rows()
        row = next((x for x in rows if x["id"] == sid), None)
        if row is None:
            raise HTTPException(404, "unknown signal")
        closed = row["stock"]["status"] == "closed"
        t = lessons_mod.trade(store, row) if closed else None
        return {"id": sid, "stock": row["stock"]["path"], "option": (row["option"] or {}).get("path", []),
                "oi": oi_by_session(store, row.get("contract"), row["session_date"], row["exit_by"]),
                "why_lost": (w := explain_loss(store, row)) and w | {"how_common": loss_note_rates(rows)},
                "review": (v := explain_review(store, row)) and v | {"how_common": cached_review_rates(rows)},
                # what each locked lesson rule would have done to this trade (exploratory, fixed rules)
                "lessons": t and [{"key": k, "text": c["text"], **(t["rules"][k] or {"taken": None})}
                                  | {"base": t["base"]["net"]} for k, c in lessons_mod.CANDIDATES.items()]}

    def cached_review_rates(rows: list[dict]) -> dict:
        if cache.get("review_rates_key") != cache.get("tracker_key"):
            cache["review_rates"] = review_rates(store, rows)
            cache["review_rates_key"] = cache.get("tracker_key")
        return cache["review_rates"]  # type: ignore[return-value]

    @r.get("/tracker/lessons")
    def tracker_lessons() -> dict:
        """Lessons from the record: the locked candidate rules, their history (research JSON, hindsight) and the forward
        tally on finished signals decided after the lock (the fair test). Exploratory; never part of the filter."""
        fp, hp = jdir / "lessons-frozen.json", jdir / "research" / "lessons.json"
        frozen = json.loads(fp.read_text()) if fp.exists() else None
        hist = (json.loads(hp.read_text()) if hp.exists() else {}).get("rules", {})
        fwd = lessons_mod.forward(store, tracker_rows(), frozen) if frozen else {}
        return {"frozen": frozen and {k: frozen[k] for k in ("hash", "frozen_at", "git_sha")},
                "changed_since_freeze": bool(frozen) and frozen["hash"] != lessons_mod.candidates_hash(),
                "rules": [{"key": k, "text": c["text"], "history": hist.get(k), "forward": fwd.get(k, {"trades": 0})}
                          for k, c in lessons_mod.CANDIDATES.items()],
                "min_trades": 30, "label": "Exploratory: fixed rules locked before testing; history is hindsight."}

    def loss_note_rates(rows: list[dict]) -> dict:
        """Share of finished losers vs winners showing each note (computed once per tracker refresh)."""
        if cache.get("why_rates_key") != cache.get("tracker_key"):
            cache["why_rates"] = note_rates(store, rows)
            cache["why_rates_key"] = cache.get("tracker_key")
        return cache["why_rates"]  # type: ignore[return-value]

    @r.get("/tracker.csv", response_class=PlainTextResponse)
    def tracker_csv() -> str:
        return tracker_csv_text(tracker_rows())

    # ----- Flow check: "how did bets like this do?" (descriptive history lookup, never a filter) -----
    lookup_lock = threading.Lock()

    def lookup_index() -> LookupIndex:
        with lookup_lock:                       # warm-up thread and an early request must not both build it
            return _lookup_index()

    def _lookup_index() -> LookupIndex:
        if "lookup" not in cache:
            holdout_run = (jdir / "desk-holdout.json").exists()
            cache["lookup"] = LookupIndex([bet_from_raw(x, e) for x, e in load_raw(rows_dir, include_holdout=holdout_run)])
        return cache["lookup"]  # type: ignore[return-value]

    threading.Thread(target=after_signals(lookup_index), name="signaldesk-lookup", daemon=True).start()

    def today_bets() -> tuple[str, str | None, list[dict]]:
        day, cur, _ = day_signals()
        return day, (cur or {}).get("as_of"), (cur or {}).get("bets") or []

    def bet_of(b: dict) -> Bet:
        return Bet(date.fromisoformat(b["session_date"]), b["ticker"], b["direction"], b["opt_type"], b["bet_kind"],
                   b["premium"], b["dte"], b["otm_pct"], b["sweep"], b["sector"])

    @r.get("/alerts")
    @plainly
    def alerts() -> dict:
        day, as_of, bets = today_bets()
        idx, before = lookup_index(), date.fromisoformat(day)
        rows = []
        for b in bets:
            h = idx.lookup(bet_of(b), before)
            rows.append(b | {"history": {k: h[k] for k in ("matches", "win_share", "avg", "thin", "periods_agree",
                                                           "traits_dropped")}})
        return {"day": day, "as_of": as_of, "forming": now_forming(day), "bets": rows,
                "history_size": idx.size, "label": LOOKUP_LABEL}

    @r.get("/alerts/{bet_id}")
    @plainly
    def alert_detail(bet_id: str) -> dict:
        day, _, bets = today_bets()
        b = next((x for x in bets if x["id"] == bet_id), None)
        if b is None:
            raise HTTPException(404, "unknown bet")
        return {"bet": b, "history": lookup_index().lookup(bet_of(b), date.fromisoformat(day)), "label": LOOKUP_LABEL}

    @r.get("/lookup")
    def manual_lookup(direction: int, opt_type: str, premium: float, dte: int | None = None, otm_pct: float | None = None,
                      sweep: bool = False, bet_kind: str = "clean buy", sector: str | None = None,
                      ticker: str | None = None, strike: float | None = None, expiry: str | None = None) -> dict:
        """Either % out of the money + days, or what UW shows (ticker, strike, expiry): then both come from the stock's
        last close, worked out like the engine (calls: strike above the price, puts: below), and the sector is matched."""
        day = data_day(datetime.now(UTC))
        inputs = None
        if ticker and strike and expiry:
            t = ticker.strip().upper()
            if not t.replace(".", "").replace("-", "").isalnum() or len(t) > 10 or strike <= 0:
                raise HTTPException(400, "bad lookup")
            try:
                exp = date.fromisoformat(expiry[:10])
            except ValueError:
                raise HTTPException(400, "bad expiry date")
            bars = store.get_ohlc(t, day - timedelta(days=14), day)
            # the stock price on its latest UW alert: used when no daily bar is saved, or the bar is older than it
            al = [row_to_alert(x) for x in store.alerts_between(day - timedelta(days=7), day, t)]
            al = [x for x in al if x.underlying_price]
            last = max(al, key=lambda x: x.created_at) if al else None
            if bars and (last is None or bars[-1].date >= last.session_date):
                spot, spot_day, source = bars[-1].close, bars[-1].date, "close"
            elif last is not None:
                spot, spot_day, source = last.underlying_price, last.session_date, "alert"
            else:
                raise HTTPException(400, f"No recent price saved for {t}. Enter % out of the money and days instead.")
            otm_pct = (strike - spot) / spot if opt_type == "call" else (spot - strike) / spot
            dte = (exp - day).days
            if dte < 0:
                raise HTTPException(400, "That expiry date has already passed.")
            sector = store.get_metric(t, "all", "sector") or None
            inputs = {"ticker": t, "spot": spot, "spot_date": spot_day.isoformat(), "spot_source": source,
                      "otm_pct": otm_pct, "dte": dte, "sector": sector}
        if premium < RAW_MIN_PREMIUM:
            raise HTTPException(400, "Unusual Whales only flags bets of $100K or more. Enter what was paid in dollars.")
        if dte is None or otm_pct is None or direction not in (1, -1) or opt_type not in ("call", "put") \
                or bet_kind not in KINDS.values() or premium < 0 or not 0 <= dte <= 3650 or not -1 <= otm_pct <= 10 \
                or len(sector or "") > 64:
            raise HTTPException(400, "bad lookup")
        b = Bet(day, "", direction, opt_type, bet_kind, premium, dte, otm_pct, sweep, sector)
        return lookup_index().lookup(b, day) | {"label": LOOKUP_LABEL, "inputs": inputs,
                                               "filter": _filter_check(inputs, direction, opt_type, bet_kind, premium, day)}

    def _filter_check(inputs: dict | None, direction: int, opt_type: str, bet_kind: str, premium: float, day: date) -> dict | None:
        """Would our frozen filter take this bet? Its own rules (signals.decide) on what was typed: the last close as the
        price, IV rank for cheap/fair/rich, cached earnings dates. Needs the ticker; it can't see whether the trade
        really opened a position on one leg, so that part is assumed."""
        if not inputs:
            return None
        if bet_kind != "clean buy":
            return {"signal": False, "stage": "gate", "tier": None,
                    "reason": "Sold, not bought: we only count options bought at the asking price."}
        # the first screen's checks that the form can see (core/verdict/setups.gate_failures, same constants)
        info = rows(store.cache_get(cache_key(f"/api/stock/{inputs['ticker']}/info", {}), None))
        issue = (info[0].get("issue_type") if info and isinstance(info[0], dict) else None) or None
        fails = []
        if not MONEYNESS[0] <= inputs["otm_pct"] <= MONEYNESS[1]:
            fails.append(f"moneyness {inputs['otm_pct'] * 100:+.0f}% outside −5%…+30%")
        if not DTE_RANGE[0] <= inputs["dte"] <= DTE_RANGE[1]:
            fails.append(f"DTE {inputs['dte']} outside 7–90")
        if issue and issue not in GATE_TYPES:
            fails.append(f"issue type {issue}")
        elif issue == "ETF" and opt_type == "put":
            fails.append("ETF put (likely hedge)")
        if fails:
            return {"signal": False, "stage": "gate", "tier": None, "reason": plain_reason(fails[0])}
        ivr = store.latest_metric(inputs["ticker"], day, "iv_rank")
        value = value_view(None, None, ivr[1] if ivr else None)["verdict"]
        stage, why, tier = decide(direction, inputs["spot"], premium, inputs["otm_pct"], value, day,
                                  earnings_for(store, inputs["ticker"]))
        out = {"signal": tier is not None, "stage": stage, "tier": tier, "value": value, "reason": plain_reason(why)}
        hp = jdir / "desk-holdout.json"
        if tier and hp.exists():                     # that signal type's sealed-test record (run once, frozen)
            t = (json.loads(hp.read_text()).get("tiers") or {}).get(tier)
            if t:
                out["record"] = {"tier": tier, "trades": t["n"], "beat": t["win_rate"], "avg": t["mean"]}
        return out

    def warm() -> None:
        """Load history and build the tracker once at startup, so the first ticker or Track record page is fast."""
        try:
            tracker_rows()
        except Exception:                            # a cold or partial cache must not kill the server
            hist_by_ticker()

    threading.Thread(target=after_signals(warm), name="signaldesk-warm", daemon=True).start()
    return r


LOOKUP_LABEL = ("History lookup: how earlier bets like this one did, measured on the stock over five days against the "
                "S&P 500. It describes the past. It isn't a tested signal; only our filter's signals were tested.")


def _without_paths(row: dict) -> dict:
    """Tracker list row minus the daily paths (≈ half the payload); /tracker/{id}/path serves them on demand."""
    return {**row, "stock": {k: v for k, v in row["stock"].items() if k != "path"},
            "option": {k: v for k, v in row["option"].items() if k != "path"} if row["option"] else None}


def _finite(x):
    """NaN/inf (e.g. a range over too few days) → None, so the JSON stays valid."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {k: _finite(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_finite(v) for v in x]
    return x


def _headline(ev: dict) -> dict | None:
    tp, ho, pre = ev.get("train_post"), ev.get("holdout"), ev.get("preperiod_farotm") or ev.get("preperiod")
    if not tp:
        return None

    def pick(w: dict | None) -> dict | None:
        if not w:
            return None
        return {"label": w.get("label") or (w.get("meta") or {}).get("label"), "funnel": w["funnel"],
                "signals": w["signals"], "all": w["all_directional"], "clean": w["clean"], "unpriced": w.get("unpriced"),
                                 "open": w.get("open")}
    return {"pre": pick(pre), "train": pick(tp["train"]), "holdout": pick(ho), "post": pick(tp["post"]),
            "live": pick(ev.get("live")),
            "filter_hash": tp["meta"]["filter_hash"]}


def _fresh_dp(store, ticker: str, d: date) -> tuple[date, list] | None:
    """Cached dark-pool levels, only if at most STALE_DAYS old: an old day's busiest price isn't shown as today's
    (Market listed KTOS's from Feb 24 next to today's price)."""
    dp = store.latest_metric(ticker, d, "dp_levels")
    return dp if dp and (d - dp[0]).days <= STALE_DAYS else None


def _cached_gex(store, ticker: str, d: date) -> dict | None:
    """Latest cached GEX levels on or before d (labelled with their date) — fallback while today's are not out."""
    m = store.latest_metric(ticker, d, "gex")
    return m[1] | {"date": m[0].isoformat()} if m and any(v is not None for v in m[1].values()) else None


def _calendar_window(cal: list[dict]) -> list[dict]:
    now = datetime.now(UTC)
    out, seen = [], set()
    for e in cal:
        if (e["time"], e["event"]) in seen:
            continue
        seen.add((e["time"], e["event"]))
        try:
            t = datetime.fromisoformat(e["time"].replace("Z", "+00:00"))
        except ValueError:
            continue
        if now - timedelta(hours=12) <= t <= now + timedelta(days=3):
            out.append(e | {"et": t.astimezone(mc.NY).isoformat()})
    return sorted(out, key=lambda e: e["et"])


def _accumulation(store, ticker: str, direction: int, d: date, sessions: int = 5) -> dict:
    """Clean same-direction buys over the last `sessions` sessions (cache): is someone building a position?"""
    from whaleproof.core.verdict.setups import pure_only
    start = d
    for _ in range(sessions - 1):
        start = mc.previous_session(start)
    alerts = [row_to_alert(x) for x in store.alerts_between(start, d, ticker)]
    clean = [a for a in pure_only(alerts, mc.session_close(d) + AS_OF_DELAY) if a.direction == direction]
    days = sorted({a.session_date.isoformat() for a in clean})
    return {"buys": len(clean), "days": len(days), "premium": sum(a.total_premium for a in clean), "sessions": sessions}


def _earn_warn(store, ticker: str, d: date) -> dict | None:
    for e, when in earnings_for(store, ticker):
        if d < e <= d + timedelta(days=10) or (e == d and when == "postmarket"):
            last = e if when in ("postmarket", "afterhours") else mc.previous_session(e)   # no time set: assume the open
            return {"date": e.isoformat(), "time": when, "last_session_before": last.isoformat(),
                    "text": f"Earnings {e.isoformat()} ({when}); last full session before the report: {last.isoformat()}"}
    return None


def _earnings_watch(store, tickers: list[str], d: date) -> list[dict]:
    out = []
    for t in dict.fromkeys(tickers):
        w = _earn_warn(store, t, d)
        if w:
            out.append({"ticker": t} | w)
    return sorted(out, key=lambda x: x["date"])


def _earnings_next(store, tickers: list[str], d: date) -> dict | None:
    """Soonest report after `d` among `tickers` (cache), so an empty 10-day window can still say what's next."""
    ahead = [(e, t, when) for t in dict.fromkeys(tickers) for e, when in earnings_for(store, t) if e > d]
    if not ahead:
        return None
    e, t, when = min(ahead)
    return {"ticker": t, "date": e.isoformat(), "time": when}


def _rotation(store, d: date, sessions: int = 5) -> list[dict]:
    """Net sector-tide premium for each of the last `sessions` sessions (cache)."""
    days = [d]
    for _ in range(sessions - 1):
        days.append(mc.previous_session(days[-1]))
    from whaleproof.core.data_layer.ingest import UW_SECTORS
    by: dict[str, dict] = {}
    for sector in UW_SECTORS:                     # primary-key lookups; a LIKE scan over daily_metric takes seconds
        for day, p in store.conn.execute(
                "SELECT date, payload FROM daily_metric WHERE ticker=? AND kind='tide' AND date BETWEEN ? AND ?",
                (f"SECTOR:{sector}", days[-1].isoformat(), d.isoformat())):
            v = json.loads(p)
            s = by.setdefault(sector, {"sector": sector, "days": {}, "total": 0.0})
            s["days"][day] = v.get("net") if isinstance(v, dict) else v
            s["total"] += s["days"][day] or 0
    return sorted(by.values(), key=lambda s: -s["total"])


def _find_signal(svc: DeskService, store, ticker: str) -> dict | None:
    t = ticker.strip().upper()
    snap = svc.snapshot()
    for ds in [snap.signals, *svc.recent]:
        for s in (ds.signals if ds else []):
            if s["ticker"] == t:
                return {k: s[k] for k in ("tier", "label", "why", "premium", "contract", "session_date", "exit_by",
                                          "otm_pct", "dte", "direction")} | {"snapshot_at": datetime.now(UTC).isoformat()}
    return None
