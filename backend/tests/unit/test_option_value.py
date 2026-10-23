"""Is the option cheap or rich? Contract IV vs the stock's trailing realized vol; IV rank as fallback."""
from whaleproof.core.options.pricing import value_view


def test_iv_vs_realized_vol_decides_when_available():
    assert value_view(0.30, 0.40, 80)["verdict"] == "cheap"          # IV below what the stock actually moves
    assert value_view(0.60, 0.35, 10)["verdict"] == "rich"
    v = value_view(0.46, 0.40, 50)
    assert v["verdict"] == "fair" and round(v["iv_rv"], 2) == 1.15 and v["basis"] == "iv_rv"


def test_iv_rank_fallback_and_unknown():
    assert value_view(0.5, None, 20)["verdict"] == "cheap"
    assert value_view(0.5, None, 75)["verdict"] == "rich"
    assert value_view(0.5, None, 50)["verdict"] == "fair"
    assert value_view(None, None, None)["verdict"] == "unknown"
    assert "IV rank 20" in value_view(0.5, None, 20)["reason"]
