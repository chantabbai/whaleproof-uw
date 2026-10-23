from __future__ import annotations

from datetime import date

from whaleproof.core.data_layer.models import Bar


def forward_returns(bars: list[Bar], session_date: date, direction: int,
                    horizons: tuple[int, ...] = (1, 5, 20)) -> dict | None:
    after = [b for b in bars if b.date > session_date]
    if not after or not after[0].open:
        return None
    entry = after[0].open
    out: dict = {"entry_date": after[0].date, "entry": entry}
    for h in horizons:
        out[f"r{h}"] = (after[h - 1].close / entry - 1) * direction if len(after) >= h else None
    window = after[:max(horizons)]
    if direction > 0:
        out["mfe20"] = max(b.high for b in window) / entry - 1
        out["mae20"] = min(b.low for b in window) / entry - 1
    else:
        out["mfe20"] = 1 - min(b.low for b in window) / entry
        out["mae20"] = 1 - max(b.high for b in window) / entry
    return out
