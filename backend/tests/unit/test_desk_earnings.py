"""W2: earnings implied move vs the ticker's own past moves (descriptive; never feeds the frozen filter)."""
from datetime import date

from whaleproof.desk.earnings import (CHEAP, MIN_PAST, RICH, classify, parse_reports, past_median, score_reports,
                                      summarize)


def raw(d: str, implied, actual, time: str = "postmarket") -> dict:
    return {"report_date": d, "report_time": time, "expected_move_perc": None if implied is None else str(implied),
            "post_earnings_move_1d": None if actual is None else str(actual)}


QUARTERS = ["2023-01-26", "2023-04-27", "2023-07-27", "2023-10-26", "2024-01-25", "2024-04-25"]


def test_parse_keeps_dated_rows_and_reads_numbers_newest_last():
    rs = parse_reports([raw("2024-01-25", 0.05, -0.03), raw("2023-10-26", "0.04", None, "premarket"),
                        {"report_date": None}, raw("2024-04-25", None, None, "unknown")])
    assert [r.day for r in rs] == [date(2023, 10, 26), date(2024, 1, 25), date(2024, 4, 25)]
    assert rs[0].time == "premarket" and rs[0].implied == 0.04 and rs[0].actual is None
    assert rs[1].implied == 0.05 and rs[1].actual == -0.03
    assert rs[2].implied is None


def test_past_median_uses_only_earlier_reports_and_needs_four():
    rs = parse_reports([raw(d, 0.05, a) for d, a in zip(QUARTERS, [0.02, -0.04, 0.06, -0.08, 0.10, 0.5])])
    assert MIN_PAST == 4
    assert past_median(rs, date(2023, 10, 26)) is None                 # only 3 earlier
    assert past_median(rs, date(2024, 1, 25)) == 0.05                  # |.02 .04 .06 .08| → median .05
    assert past_median(rs, date(2024, 4, 25)) == 0.06                  # report day itself (0.10) included only after


def test_past_median_ignores_reports_older_than_three_years_and_keeps_last_eight():
    old = [raw(f"{y}-0{m}-15", 0.05, 0.50) for y in (2018, 2019) for m in (2, 5, 8)]   # >3y before 2023-06
    recent = [raw(f"2022-0{m}-15", 0.05, 0.02) for m in (1, 3, 5, 7)]
    rs = parse_reports(old + recent)
    assert past_median(rs, date(2023, 6, 1)) == 0.02
    many = parse_reports([raw(f"20{y}-{m:02d}-10", 0.05, a) for y, m, a in
                          [(22, 1, .9), (22, 3, .01), (22, 5, .01), (22, 7, .01), (22, 9, .01), (22, 11, .01),
                           (23, 1, .01), (23, 3, .01), (23, 5, .01)]])
    assert past_median(many, date(2023, 6, 1)) == 0.01                 # the 0.9 is the 9th-oldest → dropped


def test_classify_uses_pre_declared_bands():
    assert (CHEAP, RICH) == (0.8, 1.25)
    assert classify(0.039, 0.05) == "cheap"
    assert classify(0.04, 0.05) == "fair"
    assert classify(0.0625, 0.05) == "fair"
    assert classify(0.063, 0.05) == "rich"
    assert classify(None, 0.05) is None and classify(0.05, None) is None and classify(0.05, 0.0) is None


def test_score_reports_marks_beat_and_ratio_point_in_time():
    rs = parse_reports([raw(d, 0.05, a) for d, a in zip(QUARTERS[:4], [0.02, -0.04, 0.06, -0.08])]
                       + [raw("2024-01-25", 0.03, -0.07), raw("2024-04-25", 0.08, 0.01, "premarket")])
    out = score_reports("AAA", rs)
    assert [e["day"] for e in out] == ["2024-01-25", "2024-04-25"]      # first four lack past moves
    a, b = out
    assert a["label"] == "cheap" and a["beat"] is True and round(a["ratio"], 3) == 0.6
    assert round(a["move_vs_implied"], 3) == 2.333 and round(a["edge"], 3) == 0.04
    assert b["label"] == "rich" and b["beat"] is False and b["time"] == "premarket"


def test_summarize_gives_base_rate_and_bucket_by_year():
    ev = [{"day": "2024-02-01", "label": "cheap", "beat": True, "move_vs_implied": 1.5, "edge": 0.02, "time": "postmarket"},
          {"day": "2024-03-01", "label": "cheap", "beat": False, "move_vs_implied": 0.5, "edge": -0.02, "time": "premarket"},
          {"day": "2025-02-01", "label": "rich", "beat": False, "move_vs_implied": 0.4, "edge": -0.03, "time": "postmarket"},
          {"day": "2025-03-01", "label": "fair", "beat": True, "move_vs_implied": 1.2, "edge": 0.01, "time": "unknown"}]
    s = summarize(ev)
    assert s["all"] == {"reports": 4, "beat": 0.5, "median_move_vs_implied": 0.85, "mean_edge": -0.005}
    assert s["by_label"]["cheap"]["reports"] == 2 and s["by_label"]["cheap"]["beat"] == 0.5
    assert s["by_label_year"]["rich"]["2025"]["beat"] == 0.0
    assert s["by_time"]["premarket"]["reports"] == 1


RECENT = ["2025-07-24", "2025-10-23", "2026-01-22", "2026-04-23", "2026-07-23"]


def test_upcoming_labels_next_reports_from_cached_history_and_flags_junk():
    from whaleproof.desk.earnings import upcoming
    hist = parse_reports([raw(d, 0.05, a) for d, a in zip(RECENT, [0.02, -0.04, 0.06, -0.08, 0.10])])
    cal = [{"ticker": "AAA", "report_date": "2026-10-06", "report_time": "postmarket", "expected_move_perc": 0.03,
            "sector": "Technology", "marketcap": 5e9},
           {"ticker": "BBB", "report_date": "2026-10-07", "report_time": "premarket", "expected_move_perc": 0.05},
           {"ticker": "CCC", "report_date": "2026-10-07", "report_time": "premarket", "expected_move_perc": 0.9},
           {"ticker": "DDD", "report_date": "2026-10-08", "report_time": "premarket", "expected_move_perc": None}]
    out = upcoming(cal, {"AAA": hist, "CCC": hist, "DDD": hist})
    a, b, c, d = out
    assert a["ticker"] == "AAA" and a["past"] == 0.06 and a["label"] == "cheap" and round(a["ratio"], 2) == 0.5
    assert [p["day"] for p in a["history"]] == RECENT[::-1] and a["history"][0]["beat"] is True
    assert a["history_reports"] == 5
    assert b["label"] is None and b["note"] == "no past reports cached"
    assert c["label"] is None and "implied move looks wrong" in c["note"]
    assert d["label"] is None and d["note"] == "No implied move yet"


def test_upcoming_needs_four_past_reports():
    from whaleproof.desk.earnings import upcoming
    hist = parse_reports([raw(d, 0.05, 0.05) for d in RECENT[:3]])
    [r] = upcoming([{"ticker": "AAA", "report_date": "2026-10-06", "report_time": "postmarket",
                     "expected_move_perc": 0.05}], {"AAA": hist})
    assert r["label"] is None and r["note"] == "only 3 past reports (need 4)"


def test_ticker_view_never_labels_a_report_outside_the_calendar_window():
    """A report weeks away comes from the cached history: its implied move is an old front-month straddle that may
    expire before the report, so the label waits until the report is inside the five-session calendar."""
    from whaleproof.desk.earnings import ticker_view
    rs = parse_reports([raw(d, 0.05, a) for d, a in zip(RECENT, [0.02, -0.04, 0.06, -0.08, 0.10])]
                       + [raw("2026-10-29", 0.03, None, "unknown")])
    v = ticker_view("AAA", rs, [], date(2026, 10, 4))
    n = v["next"]
    assert n["date"] == "2026-10-29" and n["implied"] == 0.03 and n["from_history"] is True
    assert n["label"] is None and n["ratio"] is None and "within 5 sessions" in n["note"]
    cal = [{"ticker": "AAA", "report_date": "2026-10-06", "report_time": "postmarket", "expected_move_perc": 0.03}]
    assert ticker_view("AAA", rs, cal, date(2026, 10, 4))["next"]["label"] == "cheap"


def test_one_past_report_reads_singular():
    from whaleproof.desk.earnings import _past_note
    assert _past_note(1) == "only 1 past report (need 4)"
    assert _past_note(3) == "only 3 past reports (need 4)"


def test_reported_marks_todays_reports_once_they_are_out():
    from datetime import datetime, timezone
    from whaleproof.desk.earnings import reported
    utc = lambda h, m=0: datetime(2026, 10, 13, h, m, tzinfo=timezone.utc)   # EDT = UTC−4
    pre = {"date": "2026-10-13", "time": "premarket"}
    post = {"date": "2026-10-13", "time": "postmarket"}
    assert not reported(pre, utc(13, 29))                     # 9:29 ET, before the open
    assert reported(pre, utc(13, 30))                         # 9:30 ET, the open: it's out
    assert not reported(post, utc(21, 0)) and not reported({**post, "time": "afterhours"}, utc(21, 0))  # time varies
    assert not reported({"date": "2026-10-14", "time": "premarket"}, utc(20, 0))   # tomorrow's
    assert not reported({"date": "2026-10-13", "time": "unknown"}, utc(21, 0))     # time unknown: don't guess


def test_history_rows_list_a_report_once_when_uw_repeats_it():
    """10-23: UW lists HLN's Oct 30, 2025 report twice (same numbers). The past-moves bars are keyed by day, so React
    flagged two children with the same key (dev overlay on Earnings) and the bar showed twice."""
    from whaleproof.desk.earnings import history_rows
    row = {"report_date": "2025-10-30", "report_time": "premarket", "expected_move_perc": "0.0928", "post_earnings_move_1d": "0.0144"}
    rs = parse_reports([row, dict(row), {**row, "report_date": "2025-07-31"}])
    h = history_rows(rs, date(2026, 10, 23))
    assert [x["day"] for x in h] == ["2025-10-30", "2025-07-31"]
