from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from whaleproof import market_calendar as mc
from whaleproof.core.data_layer.context import build_context
from whaleproof.core.data_layer.ingest import (
    ensure_day_bar, ingest_flow_day, ingest_market, ingest_unusualness)
from whaleproof.core.data_layer.models import FlowAlert, row_to_alert
from whaleproof.core.data_layer.store import Store

from whaleproof.commands.backfill import ingest_candidate

from .candidates import MAX_CANDIDATES, prefilter
from .setups import pure_only
from .verdict import Verdict, evaluate
from .weights import Weights


def live_candidates(store: Store, d: date, as_of: datetime) -> list[FlowAlert]:
    """v0.6: gate first, then biggest per (ticker, direction) — a big sold print can't evict a clean buy."""
    visible = [a for a in (row_to_alert(r) for r in store.alerts_between(d, d)) if a.created_at <= as_of]
    return prefilter(pure_only(visible, as_of))


def run_scan(client, store: Store, d: date, weights: Weights, live_unusualness: bool,
             max_candidates: int = MAX_CANDIDATES) -> list[Verdict]:
    ingest_flow_day(client, store, d, live=True)
    ingest_market(client, store, d, live=True)
    as_of = mc.session_close(d) + timedelta(minutes=15)
    cands = live_candidates(store, d, as_of)
    verdicts = []
    for a in cands[:max_candidates]:
        close = ensure_day_bar(client, store, a.ticker, d)
        ingest_candidate(client, store, a, d, datetime.now(mc.NY).date(), live=True)
        if live_unusualness:
            ingest_unusualness(client, store, a.ticker, d)
        ref = close if close is not None else a.underlying_price
        verdicts.append(evaluate(build_context(store, a, as_of, ref_price=ref), weights))
    return sorted(verdicts, key=lambda v: (-v.score_parity, v.ticker))  # rank on backtestable score


def select_go(verdicts: list, top: int) -> list:
    """GO verdicts, best score first, at most one per ticker (Amendment 10), then the top n."""
    out, seen = [], set()
    for v in sorted((v for v in verdicts if v.label == "GO"), key=lambda v: (-v.score_parity, v.ticker, v.direction)):
        if v.ticker not in seen:
            seen.add(v.ticker)
            out.append(v)
    return out[:top]


def pick_record(v: Verdict, kind: str) -> dict:
    d = v.to_dict()
    pid = hashlib.sha1(f"{v.session_date}|{v.ticker}|{v.direction}|{kind}".encode()).hexdigest()[:12]
    intraday = kind == "intraday"
    extra = {"entry_price": v.plan.entry_ref} if intraday else {}
    return extra | {
        "pick_id": pid, "kind": kind, "source_alert_id": v.alert_id, "created_at": datetime.now(timezone.utc).isoformat(),
        "as_of": d["as_of"], "session_date": d["session_date"],
        # official: next open; intraday: entered at the scan-time price on the same session
        "entry_session": (v.session_date if intraday else mc.next_session(v.session_date)).isoformat(),
        "weights_version": v.weights_version, "ticker": v.ticker, "direction": v.direction,
        "score": v.score, "score_parity": v.score_parity, "label": v.label, "coverage": v.coverage,
        "contract": v.plan.contract, "plan": d["plan"], "reasons_for": v.reasons_for,
        "reasons_against": v.reasons_against,
        "checks": {c.name: {"score": round(c.score, 4), "available": c.available} for c in v.checks},
    }
