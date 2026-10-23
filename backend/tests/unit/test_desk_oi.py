"""Open-interest trail for a signal's contract: did the whale's position stay open?"""
from whaleproof.desk.oi import oi_view


def test_oi_view_trail_and_confirmation(store):
    for d, v in (("2026-09-25", 166), ("2026-09-28", 177), ("2026-09-29", 1194), ("2026-09-30", 1250)):
        store.put_metric("MRVL261030C00280000", d, "oi", v)
    v = oi_view(store, "MRVL261030C00280000", "2026-09-28", 1000)
    assert [p["date"] for p in v["trail"]] == ["2026-09-28", "2026-09-29", "2026-09-30"]
    assert v["next_morning"] == {"date": "2026-09-29", "change": 1017, "ratio": 1.017}
    assert v["confirmed"] is True and v["latest"] == {"date": "2026-09-30", "oi": 1250}


def test_oi_view_not_confirmed_and_missing(store):
    store.put_metric("X", "2026-09-28", "oi", 500)
    store.put_metric("X", "2026-09-29", "oi", 520)
    v = oi_view(store, "X", "2026-09-28", 1000)
    assert v["confirmed"] is False
    assert oi_view(store, "NONE", "2026-09-28", 1000)["confirmed"] is None


def test_oi_record_reads_all_periods_or_none(tmp_path):
    from whaleproof.desk.oi import oi_record
    p = tmp_path / "oi-confirm.json"
    assert oi_record(p) is None
    p.write_text('{"periods": {"All periods": {"groups": {"confirmed": {"trades": 1366, "mean_vs_spy": 0.0076}}, '
                 '"unconfirmed": {"trades": 42, "mean_vs_spy": 0.008}, "unconfirmed_minus_confirmed": [-0.038, 0.035]}}}')
    assert oi_record(p) == {"unconfirmed": {"trades": 42, "mean_vs_spy": 0.008},
                            "confirmed": {"trades": 1366, "mean_vs_spy": 0.0076}, "difference_range": [-0.038, 0.035]}


def test_oi_by_session_puts_each_number_on_the_day_it_describes(store):
    """Owner 10-07: daily OI in the Track record day table. UW's OI dated X = open after X−1's session, so it sits on
    X−1's row (IREN 10-06 signal: 567 → 1,610 overnight shows on the Oct 6 row)."""
    from whaleproof.desk.oi import oi_by_session
    for d, v in (("2026-10-05", 132), ("2026-10-06", 567), ("2026-10-07", 1610), ("2026-10-08", 1580)):
        store.put_metric("IREN261106C00049000", d, "oi", v)
    rows = oi_by_session(store, "IREN261106C00049000", "2026-10-06", "2026-10-13")
    assert rows == [["2026-10-06", 1610, 1043], ["2026-10-07", 1580, -30]]          # signal day on; 567 is the base
    assert oi_by_session(store, None, "2026-10-06", "2026-10-13") == []
