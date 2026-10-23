"""Basic local dashboard: read-only JSON API over the engine + one static page. Binds to 127.0.0.1 only."""
from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

from whaleproof.api.guard import add_local_guard
from whaleproof.core.data_layer.models import row_to_alert
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import read_picks, verify_chain
from whaleproof.core.journal.flow_health import oi_trail
from whaleproof.core.journal.tracker import after_open_fills, scorecard, tradable
from whaleproof.core.options.contract import choose_contract
from whaleproof.core.options.pnl import estimate, mark
from whaleproof.core.options.pricing import value_view
from whaleproof import market_calendar as mc
from whaleproof.core.verdict.verdict import hold_em
from whaleproof.core.verdict.setups import SETUPS

PURE_HOLD = 5          # pure buys: next open → close of the 5th session

REQ_RE = re.compile(r"requests today (\d+)")


def _health(store: Store) -> dict[str, dict]:
    return {pid: json.loads(p) for pid, p in store.conn.execute("SELECT pick_id, payload FROM pick_health")}


def _outcomes(store: Store) -> dict[str, dict]:
    return {pid: json.loads(p) for pid, p in store.conn.execute("SELECT pick_id, payload FROM pick_outcome")}


def _alert_for(store: Store, rec: dict):
    try:
        sd = date.fromisoformat(rec["session_date"])
        rows = store.alerts_between(sd, sd, rec["ticker"])
    except (KeyError, ValueError, TypeError):
        return None
    match = [r for r in rows if r["id"] == rec.get("source_alert_id")] or \
        sorted((r for r in rows if r.get("option_chain") == rec.get("contract")),
               key=lambda r: -(float(r.get("total_premium") or 0)))
    return row_to_alert(match[0]) if match else None


def _our_contract(rec: dict, a) -> tuple[str, float, int]:
    """(contract we'd buy, entry spot, holding sessions). Ours, not the whale's: the whale's may be a hedge or a
    2-day lottery; ours is a near-the-money monthly with room after the hold (core/options/contract.py)."""
    d, plan = rec.get("direction") or a.direction, rec.get("plan")
    spot = (plan or {}).get("entry_ref") or a.underlying_price
    n = (plan or {}).get("time_stop_sessions") or PURE_HOLD
    return choose_contract(a.ticker, d, spot, date.fromisoformat(rec["entry_session"]), n), spot, n


def option_pnl(store: Store, rec: dict) -> dict | None:
    """Black-Scholes estimate at the plan's target/stop (official) or ±EM levels over the 5-day hold (pure)."""
    a = _alert_for(store, rec)
    if a is None or not a.iv:
        return None
    d, plan = rec.get("direction") or a.direction, rec.get("plan")
    try:
        contract, spot, n = _our_contract(rec, a)
        entry = date.fromisoformat(rec["entry_session"])
        whale = {"whale_contract": rec.get("contract") or a.option_chain}
        if plan:
            em = hold_em(spot, a.iv, n)
            width = round(em, 2) if "debit spread" in (plan.get("structure") or "") else None
            e = estimate(contract, spot, plan["target"], plan["invalidation"], a.iv, entry, n, width)
            return e and e | {"contract": contract} | whale
        em = hold_em(spot, a.iv, PURE_HOLD)
        e = estimate(contract, spot, spot + d * 1.25 * em, spot - d * 0.75 * em, a.iv, entry, PURE_HOLD)
        return e and e | {"contract": contract} | whale
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return None


def option_mark(store: Store, rec: dict, outcome: dict | None) -> float | None:
    """Estimated option result so far (or at exit) for our contract, from the tracked stock move; IV flat, net of spread."""
    if not outcome or outcome.get("return") is None or not outcome.get("entry"):
        return None
    a = _alert_for(store, rec)
    if a is None or not a.iv:
        return None
    try:
        contract, _, _ = _our_contract(rec, a)
        d = rec.get("direction") or a.direction
        start = date.fromisoformat(outcome.get("entry_date") or rec["entry_session"])
        on = date.fromisoformat(outcome["exit_date"]) if outcome.get("exit_date") else start
        if not outcome.get("exit_date"):
            for _ in range(max((outcome.get("sessions_held") or 1) - 1, 0)):
                on = mc.next_session(on)
        s0 = outcome["entry"]
        return mark(contract, a.iv, start, s0, s0 * (1 + outcome["return"] * d), on)
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return None


def row_extras(store: Store, rec: dict) -> dict:
    """Fund vs stock (for the portfolio view) and the next earnings date after the flow day."""
    a = _alert_for(store, rec)
    earn = sorted(e for e in (store.get_metric(rec.get("ticker", ""), "all", "earnings") or [])
                  if e > (rec.get("session_date") or ""))
    return {"issue_type": a.issue_type if a else None, "next_earnings": earn[0] if earn else None}


class _PerThreadStore:
    """FastAPI runs sync endpoints on a thread pool; a sqlite connection must not be used by two threads at once
    (shared, parallel dashboard requests returned mixed-up rows → 500s). Each worker thread gets its own Store."""
    def __init__(self, path: Path):
        self._path, self._local = path, threading.local()

    def __getattr__(self, name):
        st = getattr(self._local, "store", None)
        if st is None:
            st = self._local.store = Store(self._path)
        return getattr(st, name)


def exit_by(rec: dict) -> str | None:
    """Last session of the plan's time stop (entry session counts as day 1); pure buys hold 5 sessions."""
    try:
        d = date.fromisoformat(rec["entry_session"])
        n = (rec.get("plan") or {}).get("time_stop_sessions") or PURE_HOLD
    except (KeyError, ValueError, TypeError):
        return None
    for _ in range(n - 1):
        d = mc.next_session(d)
    return d.isoformat()


def option_value(store, rec: dict) -> dict | None:
    """Cheap / fair / rich for the contract we'd buy: its IV vs the stock's trailing realized vol known on the flow day."""
    a = _alert_for(store, rec)
    if a is None:
        return None
    d = a.session_date.isoformat()
    hist = store.get_metric(a.ticker, "all", "vol_hist") or []
    trailing = [(end, rv) for _, _, rv, end in hist if rv and end and end[:10] <= d]
    rv = max(trailing)[1] if trailing else None
    return value_view(a.iv, rv, _iv_rank(store, a))


def live_view(store, rec: dict, fill: dict | None) -> dict | None:
    """Real option prices for our contract, entry day → cut-off (an overnight hold, not a day trade). Conservative:
    'paid' = ask at the first quoted mark from the entry day's 9:45 decision on (the 9:35 capture is before we may buy),
    'now' = bid at the latest quoted mark (what you'd really get selling)."""
    allm = store.marks(rec["pick_id"])
    if not allm and not fill:
        return None
    pre = [m for m in allm if m["tag"] == "scan"]                       # before entry: today's close (owner 09-29)
    marks = [m for m in allm if m["tag"] != "scan"]
    lc = next((m for m in reversed(pre) if (m.get("ours") or {}).get("symbol")), None)
    q = (lc or {}).get("ours") or {}
    last_close = {"day": lc["day"], "bid": q.get("bid"), "ask": q.get("ask"),
                  "mid": round((q["bid"] + q["ask"]) / 2, 4) if q.get("bid") and q.get("ask") else None,
                  "contract": q.get("symbol")} if lc else None
    rows = [{"day": m["day"], "tag": m["tag"], "at": m["at"], "stock": (m.get("stock") or {}).get("last"),
             "bid": (m.get("ours") or {}).get("bid"), "ask": (m.get("ours") or {}).get("ask")} for m in marks]
    held = [m for m in rows if not (m["tag"] == "early" and m["day"] == rec.get("entry_session"))]
    paid = next(({"day": m["day"], "tag": m["tag"], "price": m["ask"]} for m in held if m["ask"]), None)
    last = next((m for m in reversed(held) if m["bid"]), None)          # never the pre-buy 9:35 quote
    now = {"day": last["day"], "tag": last["tag"], "price": last["bid"], "stock": last["stock"]} if last else None
    contract = next(((m.get("ours") or {}).get("symbol") for m in reversed(marks) if (m.get("ours") or {}).get("symbol")),
                    (fill or {}).get("our_contract") or (last_close or {}).get("contract"))
    mid = lambda m: (m["bid"] + m["ask"]) / 2 if m["bid"] and m["ask"] else None  # noqa: E731
    mids = [(m, mid(m)) for m in held if mid(m)]
    spread = (mids[-1][0]["ask"] - mids[-1][0]["bid"]) / mids[-1][1] if mids else None
    return {"decision": {k: fill.get(k) for k in ("decision", "reason", "created_at")} if fill else None,
            "bought": (fill or {}).get("decision", "still a buy") == "still a buy",   # skipped at 9:45 → not bought
            "mid_change": mids[-1][1] / mids[0][1] - 1 if len(mids) > 1 else None, "spread": spread,
            "mid_first": mids[0][1] if mids else None, "mid_now": mids[-1][1] if mids else None,
            "contract": contract, "paid": paid, "now": now, "marks": rows, "last_close": last_close,
            "paid_on_entry": bool(paid) and paid["day"] == rec.get("entry_session"),   # False: tracking began later
            "change": now["price"] / paid["price"] - 1 if paid and now else None,
            "hold_day": _hold_day(rec, rows[-1]["day"]) if rows else None,
            "hold_days": (rec.get("plan") or {}).get("time_stop_sessions") or PURE_HOLD}


def _hold_day(rec: dict, day: str) -> int | None:
    """Trading day number of `day` in the hold (entry day = 1)."""
    try:
        d, end = date.fromisoformat(rec["entry_session"]), date.fromisoformat(day)
    except (KeyError, ValueError, TypeError):
        return None
    n = 1
    while d < end:
        d, n = mc.next_session(d), n + 1
    return n


def finalist_ids(store, r: dict, conf: dict | None, trend: int | None) -> list[str]:
    """Finalists (F1–F3, Amendment 12 blocks) a pure buy matches, in F1, F2, F3 order."""
    from types import SimpleNamespace

    from whaleproof.core.backtest import combos as cb
    v = option_value(store, r)
    row = SimpleNamespace(setup=r.get("setup"), oi_ratio=(conf or {}).get("ratio"), dte=r.get("dte"),
                          value=(v or {}).get("verdict"), premium=r.get("premium"), otm_pct=r.get("otm_pct"),
                          direction=r["direction"], spy_trend=trend)
    return [f for f, blocks in cb.FINALISTS.items() if all(cb.BLOCKS[b][1](row) is True for b in blocks)]


def take_view(store, precs: list[dict]) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Finalist ids per pure pick and the Take list status (Amendment 16) over the whole pure journal."""
    from whaleproof.core.backtest.runner import _spy_trend
    from whaleproof.core.journal.take import take_plan
    confs = {x["pick_id"]: x for x in precs if x.get("kind") == "confirmation"}
    trends: dict[str, int | None] = {}
    fids: dict[str, list[str]] = {}
    cands = []
    for r in (x for x in precs if x.get("kind") == "pure"):
        if r["session_date"] not in trends:
            trends[r["session_date"]] = _spy_trend(store, date.fromisoformat(r["session_date"]))
        fids[r["pick_id"]] = f = finalist_ids(store, r, confs.get(r["pick_id"]), trends[r["session_date"]])
        if f:
            cands.append({"pick_id": r["pick_id"], "ticker": r["ticker"], "entry_session": r["entry_session"],
                          "exit_by": exit_by(r), "finalists": f, "premium": r.get("premium")})
    return fids, take_plan(cands, after_open_fills(precs))


def _iv_rank(store, a) -> float | None:
    from whaleproof.core.data_layer.context import build_context
    try:
        return build_context(store, a, mc.session_close(a.session_date)).iv_rank
    except Exception:  # noqa: BLE001 — descriptive extra; never break the page
        return None


def create_app(journal_path: Path, db_path: Path, log_path: Path, backtest_path: Path | None = None,
               desk=None) -> FastAPI:
    """`desk` = (DeskService, UserDB, rows_dir) → mounts the Signal Desk API under /api/desk."""
    app = FastAPI(title="WhaleProof · Signal Desk (local)")
    add_local_guard(app)
    store = _PerThreadStore(db_path)
    if desk is not None:
        from whaleproof.api.desk import build_router
        svc, udb, rows_dir = desk
        app.state.desk_svc = svc
        app.include_router(build_router(svc, store, udb, journal_path.parent, rows_dir))

    @app.get("/api/picks")
    def picks(kind: str = "official") -> dict:
        recs = read_picks(journal_path)
        confirms = {r["pick_id"]: r for r in recs if r.get("kind") == "confirmation"}
        fills = after_open_fills(recs)
        mine = [r for r in tradable(recs) if r.get("kind") == kind]
        if not mine:
            return {"session_date": None, "entry_session": None, "picks": []}
        session = max(r["session_date"] for r in mine)
        outs, health = _outcomes(store), _health(store)
        today = sorted((r for r in mine if r["session_date"] == session),
                       key=lambda r: (-(r.get("score_parity") or 0), r["ticker"]))
        latest = [{**r, "confirmation": confirms.get(r["pick_id"]), "outcome": outs.get(r["pick_id"]),
                   "health": health.get(r["pick_id"]), "pnl": option_pnl(store, r),
                   "value": option_value(store, r), "exit_by": exit_by(r), "rank": i + 1,
                   "option_result": option_mark(store, r, outs.get(r["pick_id"])),
                   "oi_trail": oi_trail(store, r), "live": live_view(store, r, fills.get(r["pick_id"]))}
                  | row_extras(store, r) for i, r in enumerate(today)]
        return {"session_date": session, "entry_session": latest[0]["entry_session"], "picks": latest}

    @app.get("/api/history")
    def history() -> list[dict]:
        recs = read_picks(journal_path)
        outs, health = _outcomes(store), _health(store)
        confirms = {r["pick_id"]: r for r in recs if r.get("kind") == "confirmation"}
        fills = after_open_fills(recs)
        return [{k: r.get(k) for k in ("pick_id", "kind", "session_date", "entry_session", "ticker", "direction",
                                       "score_parity", "weights_version", "contract", "plan")}
                | {"outcome": outs.get(r["pick_id"]), "health": health.get(r["pick_id"]),
                   "confirmation": confirms.get(r["pick_id"]), "exit_by": exit_by(r),
                   "option_result": option_mark(store, r, outs.get(r["pick_id"])),
                   "our_contract": (option_pnl(store, r) or {}).get("contract"), "oi_trail": oi_trail(store, r),
                   "live": live_view(store, r, fills.get(r["pick_id"]))}
                for r in tradable(recs)]

    @app.get("/api/money-moved")
    def money_moved() -> list[dict]:
        health, outs = _health(store), _outcomes(store)
        picks = {r["pick_id"]: r for r in tradable(read_picks(journal_path))}
        moved = [h for h in health.values() if h.get("state") in {"REDUCING", "EXITED", "ROLLED", "FLOW_REVERSED"}]
        return [h | {"ticker": picks[h["pick_id"]]["ticker"], "direction": picks[h["pick_id"]]["direction"],
                     "kind": picks[h["pick_id"]]["kind"], "contract": picks[h["pick_id"]].get("contract"),
                     "outcome": outs.get(h["pick_id"])}
                for h in sorted(moved, key=lambda h: h["as_of"], reverse=True) if h["pick_id"] in picks]

    @app.get("/api/scorecard")
    def card() -> dict:
        allrecs = read_picks(journal_path)
        recs = tradable(allrecs)
        return {"chain_valid": verify_chain(journal_path), "picks_total": len(recs),
                **scorecard(list(_outcomes(store).values()), after_open_fills(allrecs)), "taken": _taken_card()}

    def _taken_card() -> dict:
        """Amendment 16: closed 5-session results of the Take list vs all finalist trades (pure-scorecard outcomes)."""
        pj, sc_path = jdir / "pure.jsonl", jdir / "pure-scorecard.json"
        if not pj.exists():
            return {}
        fids, takes = take_view(store, read_picks(pj))
        outs = json.loads(sc_path.read_text()).get("outcomes", {}) if sc_path.exists() else {}

        def stats(ids: list[str]) -> dict:
            rs = [outs[i]["return"] for i in ids if outs.get(i, {}).get("status") == "closed"
                  and outs[i].get("return") is not None]
            opened = sum(1 for i in ids if outs.get(i, {}).get("status") == "open")
            return {"closed": len(rs), "open": opened, "win_rate": sum(x > 0 for x in rs) / len(rs) if rs else None,
                    "mean": sum(rs) / len(rs) if rs else None}
        return {"taken": stats([i for i, t in takes.items() if t == "take"]),
                "all_finalist": stats([i for i, f in fids.items() if f])}

    @app.get("/api/status")
    def status() -> dict:
        last = ""
        if log_path.exists():
            lines = [l for l in log_path.read_text(errors="ignore").splitlines() if l.strip()]
            last = lines[-1] if lines else ""
        m = None
        # the scheduler and one-off backfills log to different files — the newest one has today's count
        logs = sorted((p for p in (log_path, log_path.parent / "scheduler.log") if p.exists()),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        for lp in logs:
            for l in reversed(lp.read_text(errors="ignore").splitlines()):
                if (m := REQ_RE.search(l)):
                    break
            if m:
                break
        done = store.conn.execute("SELECT COUNT(*) FROM checkpoint WHERE name LIKE 'day:%' AND value='done-v3'"
                                  ).fetchone()[0]
        oldest = store.conn.execute("SELECT MIN(substr(name,5)) FROM checkpoint WHERE name LIKE 'day:%' "
                                    "AND value='done-v3'").fetchone()[0]
        from whaleproof.commands.backfill import BACKFILL_START
        end = mc.previous_session(datetime.now(mc.NY).date())
        return {"now": datetime.now(timezone.utc).isoformat(), "backfill_days_done": done,
                "backfill_start": BACKFILL_START.isoformat(),
                "backfill_sessions_total": len(mc.sessions(BACKFILL_START, end)),
                "backfill_oldest_day": oldest, "backfill_last_line": last,
                "requests_today": int(m.group(1)) if m else None}

    @app.get("/api/tomorrow")
    def tomorrow() -> dict:
        s = store.latest_scan("official")
        if not s:
            return {"session_date": None, "scanned_at": None, "go": [], "watch": []}
        rows = sorted(s["rows"], key=lambda r: -(r.get("score_parity") or 0))
        picked = {r["pick_id"] for r in tradable(read_picks(journal_path))
                  if r.get("kind") == "official" and r.get("session_date") == s["session_date"]}
        picked_tickers = {r["ticker"] for r in rows if r.get("pick_id") in picked}

        def why(r: dict) -> dict:
            if r.get("pick_id") in picked:
                return {"picked": True, "why_not": None}
            return {"picked": False, "why_not": "another pick on this ticker ranked higher"
                    if r["ticker"] in picked_tickers else "outside the top 5"}
        return {"session_date": s["session_date"], "scanned_at": s["created_at"],
                "weights_version": s["weights_version"], "entry_session": mc.next_session(
                    date.fromisoformat(s["session_date"])).isoformat(),
                "go": [r | why(r) for r in rows if r.get("label") == "GO"],
                "watch": [r for r in rows if r.get("label") == "WATCH"][:10]}

    @app.get("/api/intraday")
    def intraday() -> dict:
        s = store.latest_scan("intraday")
        if not s:
            return {"session_date": None, "scanned_at": None, "go": [], "watch": []}
        rows = sorted(s["rows"], key=lambda r: -(r.get("score_parity") or 0))
        return {"session_date": s["session_date"], "scanned_at": s["created_at"],
                "go": [r for r in rows if r.get("label") == "GO"],
                "watch": [r for r in rows if r.get("label") == "WATCH"][:10]}

    @app.get("/api/backtest")
    def backtest() -> dict:
        if backtest_path is None or not backtest_path.exists():
            return {"meta": None, "summary": None}
        return json.loads(backtest_path.read_text())

    @app.get("/api/pure")
    def pure() -> dict:
        """Pure-directional buys (forward research track, separate journal): latest session by setup + open holds."""
        allrecs = read_picks(journal_path.parent / "pure.jsonl")
        confirms = {r["pick_id"]: r for r in allrecs if r.get("kind") == "confirmation"}
        fills = after_open_fills(allrecs)
        recs = [r for r in allrecs if r.get("kind") == "pure"]
        if not recs:
            return {"session_date": None, "entry_session": None, "by_setup": {}, "tracking": [], "scorecard": None,
                    "count": 0}
        sc_path = journal_path.parent / "pure-scorecard.json"
        sc = json.loads(sc_path.read_text()) if sc_path.exists() else {}
        outs = sc.get("outcomes", {})
        session = max(r["session_date"] for r in recs)
        health = _health(store)
        latest = [r | {"outcome": outs.get(r["pick_id"]), "confirmation": confirms.get(r["pick_id"]),
                       "pnl": option_pnl(store, r), "value": option_value(store, r), "exit_by": exit_by(r),
                       "option_result": option_mark(store, r, outs.get(r["pick_id"])),
                       "oi_trail": oi_trail(store, r), "health": health.get(r["pick_id"]),
                       "live": live_view(store, r, fills.get(r["pick_id"]))} | row_extras(store, r)
                  for r in recs if r["session_date"] == session]
        by_setup: dict[str, list] = {}
        for r in sorted(latest, key=lambda r: -(r.get("premium") or 0)):
            by_setup.setdefault(r["setup"], []).append(r)
        tracking = [r | {"outcome": outs[r["pick_id"]], "confirmation": confirms.get(r["pick_id"]),
                         "live": live_view(store, r, fills.get(r["pick_id"]))} for r in recs
                    if r["session_date"] < session and outs.get(r["pick_id"], {}).get("status") == "open"]
        return {"session_date": session, "entry_session": latest[0]["entry_session"], "by_setup": by_setup,
                "tracking": tracking, "scorecard": sc.get("card"), "count": len(latest)}

    jdir = journal_path.parent

    @app.get("/api/analysis/{phase}")
    def analysis(phase: str) -> dict:
        p = jdir / f"analysis-{phase}.json"
        if phase not in ("train", "holdout") or not p.exists():
            raise HTTPException(404, f"no {phase} analysis yet")
        return json.loads(p.read_text())

    @app.get("/api/holding")
    def holding(today: str | None = None) -> dict:
        """Every trade still held (entry ≤ today ≤ planned exit, not closed): official/intraday and pure buys, the
        finalists each pure buy belongs to, the Take list status (Amendment 16), day X of N and the live option block."""
        day = today or datetime.now(mc.NY).date().isoformat()
        closed = {"target", "invalidated", "time_stop", "closed"}
        rows = []
        orecs = read_picks(journal_path)
        ofills, outs = after_open_fills(orecs), _outcomes(store)
        for r in tradable(orecs):
            o = outs.get(r["pick_id"])
            if r["entry_session"] <= day <= (exit_by(r) or "") and (o or {}).get("status") not in closed:
                rows.append(r | {"group": r.get("kind", "official"), "finalists": [], "outcome": o, "take": None})
        precs = read_picks(jdir / "pure.jsonl") if (jdir / "pure.jsonl").exists() else []
        pfills = after_open_fills(precs)
        fids, takes = take_view(store, precs)
        sc_path = jdir / "pure-scorecard.json"
        pouts = json.loads(sc_path.read_text()).get("outcomes", {}) if sc_path.exists() else {}
        for r in (x for x in precs if x.get("kind") == "pure"):
            o = pouts.get(r["pick_id"])
            if not (r["entry_session"] <= day <= (exit_by(r) or "")) or (o or {}).get("status") in closed:
                continue
            rows.append(r | {"group": "pure", "finalists": fids.get(r["pick_id"], []), "outcome": o,
                             "take": takes.get(r["pick_id"])})
        fills = {**ofills, **pfills}
        out = [{k: r.get(k) for k in ("pick_id", "ticker", "direction", "contract", "setup", "session_date",
                                      "entry_session", "group", "finalists", "outcome", "weights_version", "take")}
               | {"exit_by": exit_by(r), "hold_day": _hold_day(r, day),
                  "hold_days": (r.get("plan") or {}).get("time_stop_sessions") or PURE_HOLD,
                  "live": live_view(store, r, fills.get(r["pick_id"]))}
               for r in rows]
        out.sort(key=lambda x: (x["exit_by"] or "", x["group"], x["ticker"]))
        return {"today": day, "rows": out, "taken_open": sum(1 for x in out if x["take"] == "take")}

    @app.get("/api/finalists")
    def finalists() -> dict:
        """Today's clean buys run through the finalist rules (Amendment 12), same block definitions as the backtest.
        F1 needs the 08:30 open-interest check: before it, matching buys are listed as 'waiting'."""
        from types import SimpleNamespace

        from whaleproof.core.backtest import combos as cb
        from whaleproof.core.backtest.runner import _spy_trend
        allrecs = read_picks(jdir / "pure.jsonl")
        confirms = {r["pick_id"]: r for r in allrecs if r.get("kind") == "confirmation"}
        fills = after_open_fills(allrecs)
        recs = [r for r in allrecs if r.get("kind") == "pure"]
        session = max((r["session_date"] for r in recs), default=None)
        today = [r for r in recs if r["session_date"] == session]
        trend = _spy_trend(store, date.fromisoformat(session)) if session else None
        health_now = _health(store)
        _, takes = take_view(store, allrecs)
        rows = []
        for r in today:
            v = option_value(store, r)
            conf = confirms.get(r["pick_id"])
            row = SimpleNamespace(setup=r.get("setup"), oi_ratio=(conf or {}).get("ratio"), dte=r.get("dte"),
                                  value=(v or {}).get("verdict"), premium=r.get("premium"), otm_pct=r.get("otm_pct"),
                                  direction=r["direction"], spy_trend=trend)
            rows.append((row, r | {"confirmation": conf, "value": v, "pnl": option_pnl(store, r), "exit_by": exit_by(r),
                                   "oi_trail": oi_trail(store, r), "health": health_now.get(r["pick_id"]),
                                   "live": live_view(store, r, fills.get(r["pick_id"])),
                                   "take": takes.get(r["pick_id"])}))
        combos_p, hold_p = jdir / "analysis-train-combos.json", jdir / "analysis-holdout.json"
        ranked = json.loads(combos_p.read_text())["ranked"] if combos_p.exists() else []
        exam = json.loads(hold_p.read_text())["results"] if hold_p.exists() else {}
        out = []
        for fid, blocks in cb.FINALISTS.items():
            trades, waiting = [], []
            for row, rec in rows:
                res = {b: cb.BLOCKS[b][1](row) for b in blocks}
                if all(v is True for v in res.values()):
                    trades.append(rec)
                elif res.get("OI confirmed") is None and "OI confirmed" in res and \
                        all(v is True for b, v in res.items() if b != "OI confirmed") and not rec.get("confirmation"):
                    waiting.append(rec)
            order = lambda t: -(t.get("premium") or 0)  # noqa: E731 — bigger whale bets first (F1 tie-break)

            def one_per_stock(ts: list[dict]) -> list[dict]:
                """A stock bet both ways the same day is one pick at most: the bigger whale bet wins (as Amendment 10)."""
                seen, keep = set(), []
                for t in sorted(ts, key=order):
                    if t["ticker"] not in seen:
                        seen.add(t["ticker"])
                        keep.append(t)
                return keep
            trades = one_per_stock(trades)
            waiting = [w for w in one_per_stock(waiting + trades) if w in waiting]
            out.append({"id": fid, "name": cb.FINALIST_NAMES[fid], "blocks": blocks,
                        "train": next((c for c in ranked if set(c["blocks"]) == set(blocks)), None),
                        "exam": exam.get(fid), "trades": sorted(trades, key=order), "waiting": sorted(waiting, key=order)})
        # the same stock + direction picked by more than one finalist: a stronger case, flagged on every row
        where: dict[tuple, dict] = {}
        for f in out:
            for kind in ("trades", "waiting"):
                for t in f[kind]:
                    w = where.setdefault((t["ticker"], t["direction"]), {"in": [], "waiting": []})
                    w["in"].append(f["id"])
                    if kind == "waiting":
                        w["waiting"].append(f["id"])
        for f in out:
            for kind in ("trades", "waiting"):
                f[kind] = [t | {"also_in": [x for x in where[(t["ticker"], t["direction"])]["in"] if x != f["id"]]}
                           for t in f[kind]]
        overlap = [{"ticker": k[0], "direction": k[1], "in": v["in"], "waiting": v["waiting"]}
                   for k, v in sorted(where.items(), key=lambda kv: (-len(kv[1]["in"]), kv[0])) if len(v["in"]) > 1]
        return {"session_date": session, "entry_session": today[0]["entry_session"] if today else None,
                "exit_by": exit_by(today[0]) if today else None, "finalists": out, "overlap": overlap}

    @app.get("/api/combos")
    def combos() -> dict:
        """Strategy combinations found on TRAIN (Amendment 11); descriptive until finalists pass the holdout."""
        p = jdir / "analysis-train-combos.json"
        if not p.exists():
            raise HTTPException(404, "no strategy combinations yet")
        return json.loads(p.read_text())

    @app.get("/api/setups")
    def setups() -> dict:
        """Simple-backtest setup stats + the pre-registered verdict (only the holdout can say 'tradeable')."""
        bt = jdir / "backtest-simple.json"
        summ = json.loads(bt.read_text()) if bt.exists() else {}
        hold = jdir / "analysis-holdout.json"
        res = json.loads(hold.read_text())["results"] if hold.exists() else {}
        verdicts = {s: ("tradeable" if res.get(f"S.{s}", {}).get("tradeable") else "not proven") for s in SETUPS}
        return {"meta": summ.get("meta"), "setups": (summ.get("summary") or {}).get("by_setup"),
                "verdicts": verdicts, "holdout_run": hold.exists()}

    @app.get("/api/ticker/{ticker}")
    def ticker_view(ticker: str) -> dict:
        """Check a ticker from the local cache only (no UW calls): recent alerts, bars, pure buys, latest scan rows."""
        t = ticker.upper()
        last = store.conn.execute("SELECT MAX(session_date) FROM flow_alerts").fetchone()[0]
        end = date.fromisoformat(last) if last else date.today()
        alerts = sorted(store.alerts_between(end - timedelta(days=7), end, t),
                        key=lambda r: -(float(r.get("total_premium") or 0)))[:25]
        bars = [{"date": b.date.isoformat(), "open": b.open, "high": b.high, "low": b.low, "close": b.close}
                for b in store.get_ohlc(t, end - timedelta(days=120), end + timedelta(days=10))]
        pure_recs = [r for r in read_picks(jdir / "pure.jsonl") if r.get("kind") == "pure" and r.get("ticker") == t]
        scan = store.latest_scan("official")
        rows = [r for r in (scan or {}).get("rows", []) if r.get("ticker") == t]
        return {"ticker": t, "alerts": alerts, "bars": bars, "pure": pure_recs[-10:], "scan": rows}

    return app
