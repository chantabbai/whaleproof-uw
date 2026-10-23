"""Exploratory holding-period study (scripts/research/holding_period.py): pure helpers."""
import importlib.util
from datetime import date
from pathlib import Path

import pytest

from whaleproof.core.data_layer.models import Bar

_p = Path(__file__).resolve().parents[2] / "scripts" / "research" / "holding_period.py"
_spec = importlib.util.spec_from_file_location("holding_period", _p)
hp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hp)


def _bars(t, closes, start=1):
    return [Bar(date=date(2026, 1, start + i), open=c, high=c, low=c, close=c, volume=1)
            for i, c in enumerate(closes)]


def test_excess_return_matches_x5_definition():
    # flow day Jan 1; entry Jan 2 open 100; close of the 3rd session (Jan 4) = 110 → +10% - 0.1% cost; SPY +2%
    stock, spy = _bars("A", [99, 100, 105, 110]), _bars("SPY", [50, 50, 50, 51])
    x, exit_day = hp.excess_return(stock, spy, date(2026, 1, 1), 1, 3)
    assert x == pytest.approx(0.10 - 0.001 - 0.02) and exit_day == date(2026, 1, 4)


def test_excess_return_none_without_enough_future_bars():
    stock, spy = _bars("A", [99, 100, 105]), _bars("SPY", [50, 50, 50])
    assert hp.excess_return(stock, spy, date(2026, 1, 1), 1, 5) == (None, None)


def test_earnings_between_is_report_time_aware():
    d, end = date(2026, 1, 1), date(2026, 1, 10)
    assert hp.earnings_between(d, end, [(date(2026, 1, 1), "postmarket")])       # lands before entry open
    assert not hp.earnings_between(d, end, [(date(2026, 1, 1), "premarket")])    # already in flow-day close
    assert hp.earnings_between(d, end, [(date(2026, 1, 5), "unknown")])
    assert hp.earnings_between(d, end, [(date(2026, 1, 10), "premarket")])
    assert not hp.earnings_between(d, end, [(date(2026, 1, 10), "postmarket")])  # out at the close
    assert not hp.earnings_between(d, end, [(date(2026, 1, 11), "premarket")])


def test_summarize_reports_no_range_when_too_few_days():
    s = hp.summarize([(date(2026, 1, d), 0.01) for d in range(1, 6)], 30)
    assert s["trades"] == 5 and s["range95_day_mean"] == [None, None] and s["range_includes_zero"] is None
