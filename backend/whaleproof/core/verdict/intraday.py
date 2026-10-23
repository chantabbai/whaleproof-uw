"""Intraday feed: every 15 min during the session, score the day's flow so far and log fresh GO setups.

Separate `kind="intraday"` record and scorecard; the official 16:30 record is unaffected.
"""
from __future__ import annotations

import os
from datetime import datetime, time

from whaleproof import market_calendar as mc
from whaleproof.commands.backfill import ingest_candidate
from whaleproof.core.data_layer.context import build_context
from whaleproof.core.data_layer.ingest import ingest_flow_day, ingest_market
from whaleproof.core.data_layer.models import row_to_alert
from whaleproof.core.data_layer.store import Store

from .candidates import prefilter
from .setups import pure_only
from .verdict import Verdict, evaluate
from .weights import CURRENT, Weights

START, END = time(9, 45), time(15, 30)


def intraday_candidates() -> int:
    return int(os.environ.get("WHALEPROOF_INTRADAY_CANDIDATES", "20"))


def in_intraday_window(now: datetime) -> bool:
    local = now.astimezone(mc.NY)
    return mc.is_session(local.date()) and START <= local.time() <= END


def run_intraday(client, store: Store, now: datetime, weights: Weights = CURRENT,
                 max_candidates: int | None = None) -> list[Verdict]:
    d = now.astimezone(mc.NY).date()
    ingest_flow_day(client, store, d, live=True)
    ingest_market(client, store, d, live=True)
    visible = [a for a in (row_to_alert(r) for r in store.alerts_between(d, d)) if a.created_at <= now]
    latest_px: dict[str, float] = {}
    for a in sorted(visible, key=lambda x: x.created_at):
        latest_px[a.ticker] = a.underlying_price          # freshest underlying price seen in the flow
    out = []
    for a in prefilter(pure_only(visible, now))[: max_candidates or intraday_candidates()]:
        ingest_candidate(client, store, a, d, d, live=True)
        out.append(evaluate(build_context(store, a, now, ref_price=latest_px.get(a.ticker)), weights))
    return sorted(out, key=lambda v: (-v.score_parity, v.ticker))
