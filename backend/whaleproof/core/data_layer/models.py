from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
SIDE_THRESHOLD = 0.7


def num(x: Any) -> float | None:
    if x is None or x == "":
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _int(x: Any) -> int | None:
    v = num(x)
    return int(v) if v is not None else None


def _dt(x: Any) -> datetime | None:
    if not x:
        return None
    if isinstance(x, (int, float)):
        return datetime.fromtimestamp(x / 1000 if x > 1e11 else x, tz=timezone.utc)
    try:
        d = datetime.fromisoformat(str(x).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _date(x: Any) -> date | None:
    try:
        return date.fromisoformat(str(x)[:10]) if x else None
    except ValueError:
        return None


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class GexLevels:
    call_wall: float | None
    put_wall: float | None
    gamma_flip: float | None
    gamma_magnet: float | None


def parse_gex(row: dict) -> GexLevels:
    return GexLevels(num(row.get("call_wall")), num(row.get("put_wall")),
                     num(row.get("gamma_flip")), num(row.get("gamma_magnet")))


@dataclass(frozen=True)
class FlowAlert:
    id: str
    ticker: str
    created_at: datetime
    session_date: date
    option_chain: str
    kind: str
    strike: float
    expiry: date
    underlying_price: float
    total_premium: float
    ask_prem: float
    bid_prem: float
    total_size: int | None
    open_interest: int | None
    volume: int | None
    volume_oi_ratio: float | None
    iv: float | None
    has_sweep: bool
    has_multileg: bool
    all_opening: bool
    issue_type: str
    alert_rule: str
    has_floor: bool = False
    delta: float | None = None

    @property
    def dte(self) -> int:
        return (self.expiry - self.session_date).days

    @property
    def ask_share(self) -> float:
        return self.ask_prem / self.total_premium if self.total_premium else 0.0

    @property
    def bid_share(self) -> float:
        return self.bid_prem / self.total_premium if self.total_premium else 0.0

    @property
    def direction(self) -> int:
        """+1 bullish, -1 bearish, 0 ambiguous (mixed side or multi-leg)."""
        if self.has_multileg:
            return 0
        call = 1 if self.kind == "call" else -1
        if self.ask_share >= SIDE_THRESHOLD:
            return call
        if self.bid_share >= SIDE_THRESHOLD:
            return -call
        return 0

    @property
    def otm_pct(self) -> float:
        s = self.underlying_price
        return (self.strike - s) / s if self.kind == "call" else (s - self.strike) / s


def parse_alert(raw: dict) -> FlowAlert | None:
    created = _dt(raw.get("created_at"))
    expiry = _date(raw.get("expiry"))
    under = num(raw.get("underlying_price"))
    prem = num(raw.get("total_premium"))
    strike = num(raw.get("strike"))
    kind = str(raw.get("type") or "").lower()
    ticker = raw.get("ticker")
    if not (created and expiry and under and prem and strike and ticker and kind in ("call", "put")):
        return None
    chain = str(raw.get("option_chain") or "")
    aid = raw.get("id") or hashlib.sha1(
        f"{chain}|{raw.get('created_at')}|{raw.get('total_size')}|{prem}".encode()).hexdigest()[:16]
    return FlowAlert(
        id=str(aid), ticker=str(ticker), created_at=created,
        session_date=created.astimezone(NY).date(), option_chain=chain, kind=kind,
        strike=strike, expiry=expiry, underlying_price=under, total_premium=prem,
        ask_prem=num(raw.get("total_ask_side_prem")) or 0.0,
        bid_prem=num(raw.get("total_bid_side_prem")) or 0.0,
        total_size=_int(raw.get("total_size")),
        open_interest=_int(raw.get("open_interest")),
        volume=_int(raw.get("volume")),
        volume_oi_ratio=num(raw.get("volume_oi_ratio")), iv=num(raw.get("iv")),
        has_sweep=bool(raw.get("has_sweep")), has_multileg=bool(raw.get("has_multileg")),
        all_opening=bool(raw.get("all_opening_trades")),
        issue_type=str(raw.get("issue_type") or ""), alert_rule=str(raw.get("alert_rule") or ""),
        has_floor=bool(raw.get("has_floor")), delta=num(raw.get("delta")),
    )


def alert_to_row(a: FlowAlert, raw: dict) -> dict:
    return {**raw, "id": a.id, "ticker": a.ticker, "created_at": a.created_at.isoformat(),
            "session_date": a.session_date.isoformat()}


def row_to_alert(row: dict) -> FlowAlert:
    a = parse_alert(row)
    assert a is not None, f"stored alert {row.get('id')} no longer parses"
    return a
