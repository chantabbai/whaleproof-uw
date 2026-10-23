"""Today 'Coming up': when no open signal or watchlist ticker reports in the next 10 days, name the next one instead
of a bare 'None' (owner 10-06)."""
from datetime import date

from whaleproof.core.data_layer.fetch import cache_key
from whaleproof.core.data_layer.store import Store


def _earn(st, t, rows):
    st.cache_put(cache_key(f"/api/earnings/{t}", {}), f"/api/earnings/{t}", {"data": rows})


def test_earnings_next_is_the_soonest_future_report_beyond_the_window(tmp_path):
    from whaleproof.api.desk import _earnings_next
    st = Store(tmp_path / "c.sqlite")
    _earn(st, "AAA", [{"report_date": "2026-07-20", "report_time": "premarket"},
                      {"report_date": "2026-10-29", "report_time": "postmarket"}])
    _earn(st, "BBB", [{"report_date": "2026-10-22", "report_time": "premarket"}])
    nxt = _earnings_next(st, ["AAA", "BBB", "NOCACHE"], date(2026, 10, 6))
    assert nxt == {"ticker": "BBB", "date": "2026-10-22", "time": "premarket"}


def test_earnings_next_none_when_nothing_ahead(tmp_path):
    from whaleproof.api.desk import _earnings_next
    st = Store(tmp_path / "c.sqlite")
    _earn(st, "AAA", [{"report_date": "2026-07-20", "report_time": "premarket"}])
    assert _earnings_next(st, ["AAA"], date(2026, 10, 6)) is None
