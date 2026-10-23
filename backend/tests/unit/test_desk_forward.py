"""Forward record export: the live signals (from Sep 30) as a committed, derived file anyone can read."""
from whaleproof.desk.forward import _day, forward_record, markdown
from whaleproof.desk.tracker import LIVE_PERIOD


def row(ticker, status, ret=None, vs=None, period=LIVE_PERIOD, d="2026-09-30"):
    return {"id": f"id-{ticker}", "source": "live", "session_date": d, "ticker": ticker, "direction": 1, "tier": "whale",
            "label": "Whale conviction bet", "premium": 1_500_000.0, "otm_pct": 0.1, "sector": "Technology",
            "contract": f"{ticker}261023C00107000", "spot_at_alert": 90.0, "entry_on": "2026-10-01",
            "exit_by": "2026-10-07", "period": period,
            "stock": {"status": status, "days_held": 5 if status == "closed" else 2, "ret": ret, "vs_spy": vs},
            "option": {"ret": 0.5}}


def test_only_live_rows_and_no_raw_uw_fields():
    rec = forward_record([row("AAA", "closed", 0.02, 0.01), row("OLD", "closed", 0.1, 0.1, period="Sealed test")],
                         as_of="2026-10-08T21:00:00+00:00")
    assert [s["ticker"] for s in rec["signals"]] == ["AAA"]
    s = rec["signals"][0]
    for raw in ("premium", "contract", "otm_pct", "spot_at_alert", "option", "id"):
        assert raw not in s                       # per-alert UW fields stay in the local cache (UW data is not redistributed)
    assert s["stock_return"] == 0.02 and s["vs_sp500"] == 0.01 and s["type"] == "Whale bet"


def test_summary_counts_finished_trades_only():
    rec = forward_record([row("A", "closed", 0.04, 0.03), row("B", "closed", -0.02, -0.01), row("C", "open", 0.5, 0.5),
                          row("D", "waiting")], as_of="x")
    sm = rec["summary"]
    assert (sm["finished"], sm["open"], sm["won"]) == (2, 2, 1)
    assert abs(sm["avg_stock_return"] - 0.01) < 1e-12 and abs(sm["avg_vs_sp500"] - 0.01) < 1e-12
    assert sm["beat_sp500"] == 1


def test_markdown_has_table_and_caveat():
    md = markdown(forward_record([row("A", "closed", 0.04, 0.03), row("D", "waiting")], as_of="2026-10-08T21:00:00+00:00"))
    assert "| Sep 30 | A | Whale bet |" in md and "+4.00%" in md and "not proof" in md


def test_empty_record_is_explicit():
    md = markdown(forward_record([], as_of="x"))
    assert "No live signals yet" in md


def test_forward_markdown_says_one_time_and_uses_a_true_minus():
    from whaleproof.desk.forward import _pct, _times
    assert _times(1) == "1 time" and _times(3) == "3 times"
    assert _pct(-0.0123) == "−1.23%" and _pct(0.02) == "+2.00%"


def test_day_label_has_no_leading_zero_on_every_os():
    # "%-d" is glibc/BSD only: Windows raises ValueError (found by the windows CI job)
    import inspect
    from whaleproof.desk import forward
    assert _day("2026-10-05") == "Oct 5" and _day("2026-10-21") == "Oct 21"
    assert "%-" not in inspect.getsource(forward._day)
