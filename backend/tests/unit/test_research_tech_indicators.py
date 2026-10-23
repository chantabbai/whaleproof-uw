"""Exploratory technical-indicators study (scripts/research/tech_indicators.py): pure helpers."""
import importlib.util
from pathlib import Path

import pytest

_p = Path(__file__).resolve().parents[2] / "scripts" / "research" / "tech_indicators.py"
_spec = importlib.util.spec_from_file_location("tech_indicators", _p)
ti = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ti)


def test_rsi_all_gains_is_100_all_losses_is_0():
    assert ti.rsi(list(range(1, 30))) == pytest.approx(100)
    assert ti.rsi(list(range(30, 1, -1))) == pytest.approx(0)


def test_rsi_wilder_on_alternating_moves_is_50():
    closes = [100 + (i % 2) for i in range(40)]          # +1, -1, ... equal gains and losses (last move weighs 1/14)
    assert ti.rsi(closes) == pytest.approx(50, abs=4)


def test_rsi_none_without_enough_closes():
    assert ti.rsi(list(range(14))) is None


def test_sma_and_none_when_short():
    assert ti.sma([1, 2, 3, 4], 2) == pytest.approx(3.5)
    assert ti.sma([1, 2, 3], 50) is None


def test_groups_flip_for_bearish_signal():
    # stock ran up hard (RSI 100) and sits above its 50-day: stretched + with trend for a bullish bet,
    # against + against trend for a bearish bet (RSI read in the bet's direction = 100 − RSI)
    closes = list(range(1, 80))
    assert ti.groups(closes, 1) == {"rsi": "stretched", "trend50": "with"}
    assert ti.groups(closes, -1) == {"rsi": "rest", "trend50": "against"}
