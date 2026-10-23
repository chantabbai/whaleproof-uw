from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from whaleproof import market_calendar as mc

from .ingest import KIND_DP, KIND_EARN, KIND_GEX, KIND_IVR, KIND_TIDE, KIND_UNUSUAL, MARKET
from .models import FlowAlert, GexLevels, row_to_alert
from .store import Store

PERSISTENCE_SESSIONS = 3
INSIDER_LOOKBACK_DAYS = 90
INSIDER_FILING_LAG_DAYS = 3        # Form 4 is filed within 2 business days — only count trades surely public
OI_PUBLISHED = time(8, 0)          # UW docs: OI updates once ~6:45 AM ET premarket → 08:00 ET is a safe buffer


@dataclass(frozen=True)
class AlertContext:
    alert: FlowAlert
    as_of: datetime
    gex: GexLevels | None
    dp_levels: list[tuple[float, int]] | None
    iv_rank: float | None
    unusual_pct: float | None
    tide: float | None
    earnings: list[date]
    same_dir_recent: int
    ref_price: float | None
    dp_blocks: dict | None = None
    net_prem: dict | None = None
    sector_tide: dict | None = None
    insider: list | tuple = ()
    oi_next: tuple[int, int] | None = None     # (OI on D, OI on D+1) — only known from D+1 morning
    uw_unusual: dict | None = None              # {"symbols": [...], "complete": bool} — UW's list for D
    rr25: list | None = None                    # [[date, put−call 25Δ IV], ...] ticker history (checks filter ≤ D)
    opt_sentiment: float | None = None          # UW options positioning score on D
    vol_hist: list | None = None                # [[iv_date, iv30, rv21, rv_window_end], ...]
    econ: list | None = None                    # [[iso_time, event], ...] economic calendar

    @property
    def expected_move(self) -> float:
        a = self.alert
        if a.iv:
            return a.underlying_price * a.iv * math.sqrt(max(a.dte, 1) / 365)
        return 0.05 * a.underlying_price


def _metric_same_day(store: Store, ticker: str, d: date, kind: str):
    hit = store.latest_metric(ticker, d, kind)
    return hit[1] if hit and hit[0] == d else None


def build_context(store: Store, alert: FlowAlert, as_of: datetime, ref_price: float | None = None) -> AlertContext:
    d = alert.session_date
    g = _metric_same_day(store, alert.ticker, d, KIND_GEX)
    dp = _metric_same_day(store, alert.ticker, d, KIND_DP)
    ivr = store.latest_metric(alert.ticker, d, KIND_IVR)
    unusual = _metric_same_day(store, alert.ticker, d, KIND_UNUSUAL)
    tide = _metric_same_day(store, MARKET, d, KIND_TIDE)
    earn = store.get_metric(alert.ticker, "all", KIND_EARN) or []

    start = d
    for _ in range(PERSISTENCE_SESSIONS - 1):
        start = mc.previous_session(start)
    recent = 0
    for row in store.alerts_between(start, d, alert.ticker):
        other = row_to_alert(row)
        if other.id != alert.id and other.created_at <= as_of and other.direction == alert.direction != 0:
            recent += 1

    sector = store.get_metric(alert.ticker, "all", "sector") or ""
    ins = [(date.fromisoformat(dt), p, p10) for dt, p, p10 in (store.get_metric(alert.ticker, "all", "insider") or [])]
    ins = [x for x in ins
           if d - timedelta(days=INSIDER_LOOKBACK_DAYS) <= x[0] <= d - timedelta(days=INSIDER_FILING_LAG_DAYS)]
    oi_next = None
    nxt = mc.next_session(d)
    if as_of >= datetime.combine(nxt, OI_PUBLISHED, tzinfo=mc.NY):
        o0, o1 = store.get_metric(alert.option_chain, d, "oi"), store.get_metric(alert.option_chain, nxt, "oi")
        if o0 is not None and o1 is not None:
            oi_next = (int(o0), int(o1))

    return AlertContext(
        alert=alert, as_of=as_of,
        gex=GexLevels(**g) if g else None,
        dp_levels=[(float(p), int(v)) for p, v in dp] if dp else None,
        iv_rank=ivr[1] if ivr else None,
        unusual_pct=unusual, tide=tide,
        earnings=[date.fromisoformat(x) for x in earn],
        same_dir_recent=recent, ref_price=ref_price,
        dp_blocks=_metric_same_day(store, alert.ticker, d, "dp_blocks"),
        net_prem=_metric_same_day(store, alert.ticker, d, "net_prem"),
        sector_tide=_metric_same_day(store, f"SECTOR:{sector}", d, "tide") if sector else None,
        insider=ins, oi_next=oi_next,
        uw_unusual=store.get_metric("UW_UNUSUAL", d, "contracts"),
        rr25=store.get_metric(alert.ticker, "all", "rr25"),
        opt_sentiment=_metric_same_day(store, alert.ticker, d, "opt_sentiment"),
        vol_hist=store.get_metric(alert.ticker, "all", "vol_hist"),
        econ=store.get_metric(MARKET, "all", "econ"),
    )


def oi_ratio(store: Store, alert: FlowAlert) -> float | None:
    """(OI on D+1 − OI on D) / alert size — the next-morning 'did the position stay open' measure."""
    size = alert.total_size or alert.volume
    o0 = store.get_metric(alert.option_chain, alert.session_date, "oi")
    o1 = store.get_metric(alert.option_chain, mc.next_session(alert.session_date), "oi")
    if not size or o0 is None or o1 is None:
        return None
    return round((o1 - o0) / size, 4)
