from __future__ import annotations

from whaleproof.core.data_layer.models import FlowAlert

ISSUE_TYPES = {"Common Stock", "ETF", "ADR"}
MIN_PRICE = 5.0
MIN_PREMIUM = 100_000
MAX_CANDIDATES = 40  # same cap for backfill, backtest and live scan — keeps them comparable


def prefilter(alerts: list[FlowAlert]) -> list[FlowAlert]:
    best: dict[tuple[str, int], FlowAlert] = {}
    for a in alerts:
        if a.direction == 0 or a.issue_type not in ISSUE_TYPES:
            continue
        if a.underlying_price < MIN_PRICE or a.total_premium < MIN_PREMIUM or not 1 <= a.dte <= 365:
            continue
        k = (a.ticker, a.direction)
        if k not in best or a.total_premium > best[k].total_premium:
            best[k] = a
    return sorted(best.values(), key=lambda a: (-a.total_premium, a.ticker))
