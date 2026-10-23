from datetime import date, timedelta

import pytest

from whaleproof.core.backtest.outcomes import forward_returns
from whaleproof.core.backtest.stats import summarize_returns, wilson
from whaleproof.core.data_layer.models import Bar


def bars(start, closes):
    out, d = [], start
    for c in closes:
        out.append(Bar(d, c, c * 1.02, c * 0.98, c, 1))
        d += timedelta(days=1)
    return out


def test_entry_is_next_bar_open_and_returns_signed():
    b = bars(date(2026, 1, 1), [100, 100, 110] + [120] * 25)
    r = forward_returns(b, date(2026, 1, 1), +1)
    assert r["entry_date"] == date(2026, 1, 2) and r["entry"] == 100
    assert r["r1"] == 0.0 and r["r5"] == pytest.approx(0.2)
    short = forward_returns(b, date(2026, 1, 1), -1)
    assert short["r5"] == pytest.approx(-0.2)
    assert r["mfe20"] == pytest.approx(0.224) and r["mae20"] == pytest.approx(-0.02)


def test_not_enough_bars_gives_none_horizons():
    r = forward_returns(bars(date(2026, 1, 1), [100, 101, 102]), date(2026, 1, 1), 1)
    assert r["r1"] is not None and r["r5"] is None and r["r20"] is None


def test_no_bar_after_session_returns_none():
    assert forward_returns(bars(date(2026, 1, 1), [100]), date(2026, 1, 1), 1) is None
    assert forward_returns([], date(2026, 1, 1), 1) is None


def test_wilson_known_values():
    lo, hi = wilson(60, 100)
    assert round(lo, 3) == 0.502 and round(hi, 3) == 0.691
    assert wilson(0, 0) == (0.0, 0.0)


def test_summarize_returns():
    s = summarize_returns([0.1, -0.05, 0.2, -0.1])
    assert s["n"] == 4 and s["hit_rate"] == 0.5
    assert s["mean"] == pytest.approx(0.0375) and s["profit_factor"] == pytest.approx(2.0)
    assert summarize_returns([])["n"] == 0
