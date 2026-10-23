"""Lessons: fixed candidate rules applied to finished signals. Baseline must equal the tracker; rules use daily bars."""
import json
from datetime import UTC, date, datetime

import pytest

from whaleproof.core.data_layer.models import Bar
from whaleproof.desk import lessons as L
from whaleproof.desk.tracker import track_stock

D0 = date(2026, 9, 30)                                     # signal day; holds Oct 1, 2, 5, 6, 7


def bars(rows):
    days = [D0, date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)]
    return [Bar(d, *r, 1e6) for d, r in zip(days, rows)]   # (open, high, low, close)


FLAT = bars([(99, 100, 98, 100), (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100),
             (100, 101, 99, 102)])


def test_baseline_is_the_tracker_result_exactly():
    for dr in (1, -1):
        b = L.apply(None, FLAT, D0, dr)
        assert b["taken"] and b["net"] == pytest.approx(track_stock(FLAT, [], D0, dr)["ret"], abs=1e-12)
        assert b["exit_date"] == date(2026, 10, 7)


def test_take_profit_fills_at_the_level_or_at_a_gap_open():
    up = bars([(99, 100, 98, 100), (100, 103, 99, 102), (102, 106, 101, 104), (104, 108, 100, 101), (101, 101, 99, 100),
               (100, 101, 99, 100)])
    r = L.apply("take_profit_5", up, D0, 1)
    assert r["exit_date"] == date(2026, 10, 2) and r["net"] == pytest.approx(0.05 - L.COST)
    gap = bars([(99, 100, 98, 100), (100, 101, 99, 100), (107, 109, 106, 108), (100, 101, 99, 100), (100, 101, 99, 100),
                (100, 101, 99, 100)])
    r = L.apply("take_profit_5", gap, D0, 1)
    assert r["exit_date"] == date(2026, 10, 2) and r["net"] == pytest.approx(0.07 - L.COST)   # opened past +5%


def test_stop_loss_fills_at_the_level_or_at_a_gap_open():
    down = bars([(99, 100, 98, 100), (100, 101, 96, 97), (97, 98, 94, 95), (95, 96, 90, 91), (91, 92, 90, 91),
                 (91, 92, 90, 91)])
    r = L.apply("stop_loss_5", down, D0, 1)
    assert r["exit_date"] == date(2026, 10, 2) and r["net"] == pytest.approx(-0.05 - L.COST)
    gap = bars([(99, 100, 98, 100), (100, 101, 99, 100), (92, 93, 90, 91), (91, 92, 90, 91), (91, 92, 90, 91),
                (91, 92, 90, 91)])
    assert L.apply("stop_loss_5", gap, D0, 1)["net"] == pytest.approx(-0.08 - L.COST)
    assert L.apply("stop_loss_5", gap, D0, -1)["net"] == L.apply(None, gap, D0, -1)["net"]   # a short gains here


def test_skip_gap_chase_counts_a_skipped_trade_as_zero():
    chased = bars([(99, 100, 98, 100), (103, 104, 102, 103), (103, 104, 102, 103), (103, 104, 102, 103),
                   (103, 104, 102, 103), (103, 104, 102, 103)])
    r = L.apply("skip_gap_chase_2", chased, D0, 1)
    assert r == {"taken": False, "net": 0.0, "exit_date": None, "exit_price": None}
    assert L.apply("skip_gap_chase_2", FLAT, D0, 1)["taken"]
    assert L.apply("skip_gap_chase_2", FLAT[1:], D0, 1) is None          # no signal-day bar → not comparable


def test_exit_day_counts_sessions_not_calendar_days():
    r = L.apply("exit_day_3", FLAT, D0, 1)
    assert r["exit_date"] == date(2026, 10, 5)                            # Oct 1, 2, then Monday Oct 5


def test_unfinished_hold_is_not_compared():
    assert L.apply(None, FLAT[:4], D0, 1) is None


def test_freeze_writes_once_and_marks_the_forward_start(tmp_path):
    p = tmp_path / "lessons-frozen.json"
    at = datetime(2026, 10, 7, 15, 0, tzinfo=UTC)                         # 11:00 ET, before the 16:15 decision
    f = L.freeze(p, at, "abc123")
    assert json.loads(p.read_text())["hash"] == f["hash"] == L.candidates_hash()
    with pytest.raises(FileExistsError):
        L.freeze(p, at, "abc123")
    assert L.is_forward(date(2026, 10, 7), f) and not L.is_forward(date(2026, 10, 6), f)
