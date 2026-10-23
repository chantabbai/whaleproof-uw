import pytest

from whaleproof.core.data_layer.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "t.sqlite")
from whaleproof.core.data_layer.models import parse_alert


def raw_alert(**over):
    base = {
        "id": "a1", "ticker": "NVDA", "created_at": "2026-09-25T14:30:00Z", "option_chain": "NVDA261016C00200000",
        "type": "call", "strike": "200", "expiry": "2026-10-16", "underlying_price": "190.00",
        "total_premium": "500000", "total_ask_side_prem": "450000", "total_bid_side_prem": "50000",
        "total_size": 2000, "open_interest": 1500, "volume": 2500, "volume_oi_ratio": "1.67",
        "iv": "0.45", "has_sweep": True, "has_multileg": False, "all_opening_trades": True,
        "issue_type": "Common Stock", "alert_rule": "RepeatedHits",
    }
    base.update(over)
    return base


@pytest.fixture
def make_alert():
    def _make(**over):
        return parse_alert(raw_alert(**over))
    return _make
