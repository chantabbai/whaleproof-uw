from whaleproof.core.checks.base import human, money
from whaleproof.core.checks.structure import dark_pool, regime
from whaleproof.core.data_layer.context import AlertContext
from datetime import datetime, timezone


def test_human():
    assert human(1_410_549) == "1.41M" and human(97_103) == "97.1K" and human(950) == "950"
    assert human(2_500_000_000) == "2.5B" and human(-270_000_000) == "-270M"


def test_money():
    assert money(-270e6) == "−$270M" and money(1.36e6) == "$1.36M" and money(0) == "$0"


def test_reasons_use_readable_numbers(make_alert):
    a = make_alert(underlying_price="100")
    c = AlertContext(a, datetime(2026, 9, 25, 20, 15, tzinfo=timezone.utc), None,
                     [(98.0, 1_410_549), (102.0, 97_103)], None, None, -270e6, [], 0, None)
    assert "1.41M vs 97.1K shares" in dark_pool(c).reason
    assert "−$270M" in regime(c).reason
