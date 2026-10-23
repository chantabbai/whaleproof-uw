"""`whaleproof marks --at open|close` — real option prices for every open pick, entry day → cut-off (owner 2026-09-29).

16:35 ET ('scan', after the official scan): tomorrow's new picks at today's close — the real price shown on the
picks page before entry (owner 2026-09-29).
09:35 ET ('early'): mark only — closest to the tested open price (shows the opening spread).
09:45 ET ('open'): marks + on the entry day journals the after-open decision ("still a buy" / "already moved" / skip).
15:55 ET ('close'): daily mark; the cut-off day's closing bid is the real exit. Official picks stop being tracked
once their stop/target closed them. Raw quotes live only in the gitignored DB (UW data is not redistributed); the journal gets the
decision and derived numbers. About 1 stock-state + 1–2 chain calls per tracked stock per capture."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from whaleproof import market_calendar as mc
from whaleproof.config import load_settings
from whaleproof.core.data_layer.client import UWBudgetExceeded, UWClient, UWError
from whaleproof.core.data_layer.store import Store
from whaleproof.core.journal.chain import append_pick, read_picks
from whaleproof.core.options import live
from whaleproof.core.options.contract import choose_contract
from whaleproof.core.options.pnl import parse_contract
from whaleproof.core.verdict.verdict import hold_em

TRACKED = {"official", "intraday", "pure"}
PURE_HOLD = 5


def cutoff(rec: dict) -> date:
    """Last day we hold the contract: plan time stop (official) or 5 sessions (pure); entry day counts as day 1."""
    d = date.fromisoformat(rec["entry_session"])
    for _ in range(((rec.get("plan") or {}).get("time_stop_sessions") or PURE_HOLD) - 1):
        d = mc.next_session(d)
    return d


def _closed_early(store: Store, rec: dict, today: date) -> bool:
    row = store.conn.execute("SELECT payload FROM pick_outcome WHERE pick_id=?", (rec["pick_id"],)).fetchone()
    if not row:
        return False
    import json
    o = json.loads(row[0])
    return o.get("status") in {"target", "invalidated", "time_stop"} and bool(o.get("exit_date")) \
        and o["exit_date"] < today.isoformat()


def _alert(store: Store, rec: dict):
    from whaleproof.api.app import _alert_for
    return _alert_for(store, rec)


def _levels(rec: dict, alert) -> tuple[dict | None, float | None]:
    """(plan levels, spot). Pure buys have no stop/target: use the same ±EM levels as the dashboard's estimate."""
    if rec.get("plan"):
        return rec["plan"], rec["plan"].get("entry_ref")
    if alert is None or not alert.iv:
        return None, alert.underlying_price if alert else None
    spot, d = alert.underlying_price, rec["direction"]
    em = hold_em(spot, alert.iv, PURE_HOLD)
    return {"entry_ref": spot, "target": spot + d * 1.25 * em, "invalidation": spot - d * 0.75 * em}, spot


def _est_premium(rec: dict, alert, ours: str | None, spot: float | None) -> float | None:
    from whaleproof.core.options.pnl import _years, bs_price
    c = parse_contract(ours or "")
    if c is None or alert is None or not alert.iv or not spot:
        return None
    return bs_price(c["kind"], spot, c["strike"], _years(date.fromisoformat(rec["entry_session"]), c["expiry"]), alert.iv)


def _locked_contract(store: Store, rec: dict, locked: dict) -> str | None | bool:
    """Contract fixed for this trade (Amendment 17): the 9:45 decision's, else the first one marks recorded.
    False = not fixed yet → choose it now."""
    if rec["pick_id"] in locked:
        return locked[rec["pick_id"]]
    first = next(((m.get("ours") or {}).get("symbol") for m in store.marks(rec["pick_id"])
                  if (m.get("ours") or {}).get("symbol")), None)
    return first or False


def run_marks(client, store: Store, journals: list[Path], now: datetime, tag: str) -> dict:
    today = now.astimezone(mc.NY).date()
    res = {"tracked": 0, "decisions": 0, "errors": 0, "stopped": ""}
    if not mc.is_session(today):
        return res
    local = now.astimezone(mc.NY)
    if tag == "open" and (local.hour, local.minute) < (9, 45):
        return res | {"stopped": "before 09:45 ET"}      # after-open decisions need real post-open prices
    if tag == "early" and (local.hour, local.minute) < (9, 31):
        return res | {"stopped": "before the 09:30 open"}   # 09:35 mark: closest to the tested open price
    if tag == "scan" and local.hour < 16:
        return res | {"stopped": "before the 16:00 close"}  # after the scan: tomorrow's picks at today's close
    items: list[tuple[Path, dict]] = []
    locked: dict[str, str | None] = {}
    for j in journals:
        if not Path(j).exists():
            continue
        recs = read_picks(j)
        voided = {r["pick_id"] for r in recs if r.get("kind") == "fill_void"}
        for r in recs:                                   # latest fill's contract is locked (Amendment 17)
            if r.get("kind") == "fill" and r["pick_id"] not in voided:
                locked[r["pick_id"]] = r.get("our_contract")
        filled = {r["pick_id"] for r in recs if r.get("kind") == "fill"} - voided
        for r in recs:
            if r.get("kind") not in TRACKED or not r.get("entry_session"):
                continue
            entry = date.fromisoformat(r["entry_session"])
            due = (today < entry and not any(m["tag"] == "scan" for m in store.marks(r["pick_id"]))) if tag == "scan" else entry <= today <= cutoff(r) and not _closed_early(store, r, today)
            if due:
                items.append((Path(j), r | {"_filled": r["pick_id"] in filled}))
    by_ticker: dict[str, list] = defaultdict(list)
    for j, r in items:
        by_ticker[r["ticker"]].append((j, r))
    for ticker, group in sorted(by_ticker.items()):
        try:
            state = live.stock_state(client, store, ticker)
            prepared, expiries = [], set()
            for j, r in group:
                a = _alert(store, r)
                plan, spot = _levels(r, a)
                ours = choose_contract(ticker, r["direction"], spot, date.fromisoformat(r["entry_session"]),
                                       (r.get("plan") or {}).get("time_stop_sessions") or PURE_HOLD) if spot else None
                whale = r.get("contract")
                for sym in (whale, ours):
                    c = parse_contract(sym or "")
                    if c:
                        expiries.add(c["expiry"].isoformat())
                prepared.append((j, r, a, plan, spot, ours, whale))
            chains: dict[str, dict] = {}
            for e in sorted(expiries):
                chains.update(live.chain(client, store, ticker, e))
        except UWBudgetExceeded:
            res["stopped"] = "budget"
            break
        except (UWError, ValueError, KeyError, TypeError):
            res["errors"] += 1
            continue
        for j, r, a, plan, spot, ours, whale in prepared:
            listed = _locked_contract(store, r, locked)
            if listed is False:
                listed = live.snap_listed(ours, chains, spot) if ours else None
            q_ours, q_whale = chains.get(listed or "", {}), chains.get(whale or "", {})
            store.put_mark(r["pick_id"], today.isoformat(), tag, now.astimezone(timezone.utc).isoformat(),
                           {"stock": state, "whale": {"symbol": whale, **q_whale}, "ours": {"symbol": listed, **q_ours}})
            res["tracked"] += 1
            if tag == "open" and today.isoformat() == r["entry_session"] and not r["_filled"] and plan:
                chk = live.after_open_check(r["direction"], plan, state.get("last"),
                                            _est_premium(r, a, listed, spot), q_ours.get("ask"),
                                            bid_now=q_ours.get("bid"), quote_given=True,
                                            contract_found=listed is not None)
                append_pick(j, {"pick_id": r["pick_id"], "kind": "fill", "ticker": ticker,
                                "created_at": datetime.now(timezone.utc).isoformat(), "our_contract": listed,
                                "decision": chk["decision"], "reason": chk["reason"],
                                "progress": round(chk["progress"], 4) if chk.get("progress") is not None else None,
                                "spread": round(chk["spread"], 4) if chk.get("spread") is not None else None,
                                "price_change": round(chk["price_change"], 4) if chk.get("price_change") is not None
                                else None})
                res["decisions"] += 1
    return res


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="whaleproof marks")
    p.add_argument("--at", choices=["early", "open", "close", "scan"], required=True)
    args = p.parse_args(argv)
    s = load_settings()
    client = UWClient(s.uw_api_key, s.live_request_cap)
    res = run_marks(client, Store(s.db_path), [s.journal_path, s.journal_path.parent / "pure.jsonl"],
                    datetime.now(mc.NY), args.at)
    print(f"marks ({args.at}): {res} · requests today {getattr(client.usage, 'daily_count', None)}")
    return 0
