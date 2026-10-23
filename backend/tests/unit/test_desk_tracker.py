"""Signal tracker: per-signal entry/exit, P/L, peak/drawdown, and the whale-option alternative — same definitions as
the backtest rows (forward_returns + COST, real_option_return fills)."""
from datetime import date

import pytest

from whaleproof.core.backtest.option_prices import real_option_return
from whaleproof.core.backtest.runner import COST
from whaleproof.core.data_layer.models import Bar
from whaleproof.desk.tracker import track_option, track_stock

D0 = date(2026, 9, 21)          # Monday flow day → entry Tue 09-22, 5th session Mon 09-28


def bars(closes, start_day=22, base=100.0):
    out = [Bar(date(2026, 9, 21), base, base, base, base, 1)]
    days = [22, 23, 24, 25, 28, 29, 30][: len(closes)]
    for i, (d, c) in enumerate(zip(days, closes)):
        o = base if i == 0 else closes[i - 1]
        out.append(Bar(date(2026, 9, d), o, max(o, c) + 1, min(o, c) - 1, c, 1))
    return out


def test_closed_signal_matches_backtest_definitions():
    b = bars([101, 103, 99, 104, 106, 120])            # 6th bar after exit must be ignored
    spy = bars([100.5, 100.5, 100.5, 100.5, 101, 101])
    t = track_stock(b, spy, D0, 1)
    assert t["status"] == "closed" and t["days_held"] == 5
    assert t["entry_date"] == "2026-09-22" and t["entry"] == 100
    assert t["exit_date"] == "2026-09-28" and t["exit"] == 106
    assert t["ret"] == pytest.approx(0.06 - COST)
    assert t["vs_spy"] == pytest.approx(0.06 - COST - 0.01)
    assert t["peak"] == pytest.approx(0.07) and t["peak_date"] == "2026-09-28"      # high 107 on day 5
    assert t["drawdown"] == pytest.approx(-0.02) and t["drawdown_date"] == "2026-09-24"   # low 98 on day 3
    assert t["priced_through"] == "2026-09-28"
    # daily close vs entry AFTER costs (owner 10-06: table showed +2.9% next to a +2.8% result), so the last point = ret
    assert t["path"][0] == ["2026-09-22", pytest.approx(0.01 - COST)] and t["path"][-1] == ["2026-09-28", pytest.approx(t["ret"])]
    assert len(t["path"]) == 5


def test_open_signal_marks_to_latest_close():
    t = track_stock(bars([101, 97]), bars([100, 100]), D0, 1)
    assert t["status"] == "open" and t["days_held"] == 2 and t["exit_date"] is None
    assert t["last"] == 97 and t["ret"] == pytest.approx(-0.03 - COST)
    assert t["priced_through"] == "2026-09-23"


def test_waiting_for_entry_has_no_prices():
    t = track_stock(bars([]), bars([]), D0, 1)
    assert t["status"] == "waiting" and t["ret"] is None and t["entry"] is None


def _opt_row(d, open_=None, bid=None, ask=None, last=None, high=None):
    return {"date": d, "open_price": open_, "nbbo_bid": bid, "nbbo_ask": ask, "last_price": last, "high_price": high}


class FakeStore:
    def __init__(self, rows):
        self.rows = rows

    def cache_get(self, key, max_age):
        return {"chains": self.rows}


def test_closed_option_equals_backtest_fill():
    rows = [_opt_row("2026-09-22", 2.0, 1.9, 2.1, 2.0), _opt_row("2026-09-23", 2.5, 2.6, 2.8, 2.7),
            _opt_row("2026-09-24", 1.5, 1.4, 1.6, 1.5), _opt_row("2026-09-28", 3.0, 3.1, 3.3, 3.2)]
    st = FakeStore(rows)
    o = track_option(st, "X", date(2026, 9, 22), date(2026, 9, 28), closed=True)
    ref = real_option_return(st, "X", date(2026, 9, 22), date(2026, 9, 28))
    assert o["ret"] == pytest.approx(ref["ret"]) and o["buy"] == pytest.approx(2.1)
    assert o["peak"] == pytest.approx(3.1 / 2.1 - 1) and o["peak_date"] == "2026-09-28"
    assert o["drawdown"] == pytest.approx(1.4 / 2.1 - 1) and o["drawdown_date"] == "2026-09-24"
    assert o["sell"] == pytest.approx(ref["sell"]) and o["sell_date"] == "2026-09-28"
    assert [p[0] for p in o["path"]] == ["2026-09-22", "2026-09-23", "2026-09-24", "2026-09-28"]
    assert o["path"][1][1] == pytest.approx(2.6 / 2.1 - 1)
    assert o["priced_through"] == "2026-09-28"


def test_open_option_marks_latest_bid_and_missing_is_not_measured():
    rows = [_opt_row("2026-09-22", 2.0, 1.9, 2.1, 2.0), _opt_row("2026-09-23", 2.5, 2.2, 2.4, 2.3)]
    o = track_option(FakeStore(rows), "X", date(2026, 9, 22), date(2026, 9, 28), closed=False)
    assert o["ret"] == pytest.approx(2.2 / 2.1 - 1) and o["priced_through"] == "2026-09-23"
    assert o["sell"] == pytest.approx(2.2) and o["sell_date"] == "2026-09-23"
    assert o["drawdown"] == pytest.approx(1.9 / 2.1 - 1)
    assert track_option(FakeStore([]), "X", date(2026, 9, 22), date(2026, 9, 28), closed=False) is None
    no_trade = [_opt_row("2026-09-22", None, 1.9, 2.1, None)]
    assert track_option(FakeStore(no_trade), "X", date(2026, 9, 22), date(2026, 9, 28), closed=False) is None
    # closed but no exit-day row → not measured (never guessed), same as the backtest
    assert track_option(FakeStore(rows), "X", date(2026, 9, 22), date(2026, 9, 28), closed=True) is None


# ---------- row builder + close update ----------
from whaleproof.core.data_layer.store import Store   # noqa: E402
from whaleproof.desk.history import HistRow          # noqa: E402
from whaleproof.desk.tracker import build_rows, close_update   # noqa: E402


def _hist(d, t="AAA", contract=None):
    return HistRow(d, t, 1, 2_000_000, 0.08, 100.0, "fair", 30, "Tech", None, None, None, "signal", "whale bet",
                   "whale", f"id-{t}-{d}", contract)


def test_build_rows_merges_history_and_live_without_duplicates(tmp_path):
    st = Store(tmp_path / "c.sqlite")
    st.put_ohlc("AAA", bars([101, 103, 99, 104, 106]))
    st.put_ohlc("SPY", bars([100, 100, 100, 100, 100]))
    live = [{"id": "id-AAA-2026-09-21", "ticker": "AAA", "direction": 1, "tier": "whale", "label": "dup",
             "premium": 1, "otm_pct": 0.1, "sector": "Tech", "contract": None, "spot_at_alert": 100.0,
             "session_date": "2026-09-21"},
            {"id": "live-1", "ticker": "BBB", "direction": 1, "tier": "far_otm", "label": "far-OTM buy",
             "premium": 300_000, "otm_pct": 0.2, "sector": None, "contract": None, "spot_at_alert": 50.0,
             "session_date": "2026-09-30"}]
    rows = build_rows(st, [_hist(D0)], live)
    assert [r["id"] for r in rows] == ["live-1", "id-AAA-2026-09-21"]          # newest first, dup dropped
    a = rows[1]
    assert a["source"] == "history" and a["stock"]["status"] == "closed" and a["option"] is None
    assert a["period"].startswith("Recent months") and a["gap_at_entry"] == pytest.approx(0.0)
    b = rows[0]
    assert b["source"] == "live" and b["period"] == "Live (from Sep 30, 2026)" and b["stock"]["status"] == "waiting"
    assert b["entry_on"] == "2026-10-01" and b["exit_by"] == "2026-10-07"


class FakeClient:
    def __init__(self):
        self.paths = []


def test_close_update_fetches_once_per_day_and_retries_until_the_close_is_in(tmp_path, monkeypatch):
    import whaleproof.desk.tracker as tr
    st = Store(tmp_path / "c.sqlite")
    calls = []
    day = date(2026, 9, 23)

    def fake_bars(client, store, ticker, ttl):
        calls.append(("bars", ticker, ttl))
        if ticker != "LATE":
            store.put_ohlc(ticker, [Bar(day, 1, 1, 1, 1, 1)])

    def fake_opt(client, store, chain, ttl=None):
        calls.append(("opt", chain, ttl))
    monkeypatch.setattr(tr, "ingest_bars", fake_bars)
    monkeypatch.setattr(tr, "ingest_contract_oi", fake_opt)
    out = close_update(object(), st, [("AAA", "C1"), ("LATE", None)], day)
    assert ("bars", "AAA", 0) in calls and ("bars", "SPY", 0) in calls and ("opt", "C1", 0) in calls
    assert out["bars_missing"] == ["LATE"]
    calls.clear()
    close_update(object(), st, [("AAA", "C1"), ("LATE", None)], day)
    assert [c[1] for c in calls if c[0] == "bars"] == ["LATE"]                 # AAA/SPY done for the day; LATE retried


def test_rows_that_just_exited_keep_getting_option_prices_until_the_exit_day_is_in():
    from whaleproof.desk.tracker import needs_close_prices
    day = date(2026, 10, 1)
    base = {"ticker": "AAA", "contract": "C1", "exit_by": "2026-10-01",
            "stock": {"status": "closed"}, "option": None}
    assert needs_close_prices(base, day)                                         # exit-day option row still missing
    assert not needs_close_prices({**base, "option": {"priced_through": "2026-10-01"}}, day)
    assert not needs_close_prices({**base, "exit_by": "2026-09-25"}, day)        # long gone: not measured, stop asking
    assert not needs_close_prices({**base, "contract": None}, day)
    assert needs_close_prices({**base, "stock": {"status": "open"}, "exit_by": "2026-10-05"}, day)


def test_close_update_gives_up_after_four_tries_a_day(tmp_path, monkeypatch):
    import whaleproof.desk.tracker as tr
    st = Store(tmp_path / "c.sqlite")
    calls = []
    monkeypatch.setattr(tr, "ingest_bars", lambda c, s, t, ttl: calls.append(t))
    monkeypatch.setattr(tr, "ingest_contract_oi", lambda c, s, ch, ttl=None: calls.append(ch))
    for _ in range(6):
        close_update(object(), st, [("NOPE", "C9")], date(2026, 9, 23))
    assert calls.count("NOPE") == 4 and calls.count("C9") == 4


def test_live_day_signals_are_frozen_once_decided(tmp_path):
    from whaleproof.desk.tracker import frozen_day
    calls = []
    def compute():
        calls.append(1)
        return [{"id": "a", "ticker": "AAA"}]
    assert frozen_day(tmp_path / "live", "2026-10-01", compute) == [{"id": "a", "ticker": "AAA"}]
    assert frozen_day(tmp_path / "live", "2026-10-01", lambda: []) == [{"id": "a", "ticker": "AAA"}]   # file wins
    assert calls == [1]


def test_option_that_never_closed_above_cost_has_no_peak():
    rows = [_opt_row("2026-09-22", 2.0, 1.9, 2.1, 2.0), _opt_row("2026-09-23", 1.5, 1.2, 1.4, 1.3)]
    o = track_option(FakeStore(rows), "X", date(2026, 9, 22), date(2026, 9, 28), closed=False)
    assert o["peak"] is None and o["peak_date"] is None
    assert o["drawdown"] == pytest.approx(1.2 / 2.1 - 1) and o["drawdown_date"] == "2026-09-23"


def test_close_job_items_add_sector_etfs_of_signals_needing_prices():
    """'Why it lost' compares with the sector ETF over the same days, so the close job keeps those bars current too."""
    from whaleproof.desk.tracker import close_items
    rows = [{"ticker": "AAA", "contract": "C1", "sector": "Technology", "stock": {"status": "open"}, "exit_by": "2026-10-09"},
            {"ticker": "BBB", "contract": None, "sector": "Energy", "stock": {"status": "open"}, "exit_by": "2026-10-09"},
            {"ticker": "CCC", "contract": None, "sector": None, "stock": {"status": "open"}, "exit_by": "2026-10-09"},
            {"ticker": "DDD", "contract": None, "sector": "Utilities", "stock": {"status": "closed"}, "exit_by": "2026-01-09"}]
    assert close_items(rows, date(2026, 10, 2)) == [("AAA", "C1"), ("BBB", None), ("CCC", None), ("XLK", None),
                                                    ("XLE", None)]


def test_spy_is_a_benchmark():
    """SPY's own signals can't be judged against the S&P (always −costs), so the ticker page shows the plain move."""
    from whaleproof.desk.tracker import BENCHMARKS
    assert "SPY" in BENCHMARKS and "VOO" in BENCHMARKS and "QQQ" not in BENCHMARKS


def test_stock_move_is_one_definition_for_every_page():
    """Same signal, same number: the price move (what a broker shows on an open position) and the net result after
    the 0.10% round trip (what the backtest and Track record score) come from one helper."""
    from whaleproof.desk.tracker import stock_move
    m = stock_move(100.0, 103.0, 1)
    assert m["move"] == pytest.approx(0.03) and m["net"] == pytest.approx(0.029)
    s = stock_move(100.0, 97.0, -1)
    assert s["move"] == pytest.approx(0.03) and s["net"] == pytest.approx(0.029)
    assert stock_move(None, 10.0, 1) == {"move": None, "net": None}
    assert stock_move(10.0, None, 1) == {"move": None, "net": None}


def test_track_stock_carries_the_price_move_next_to_the_net_result():
    from whaleproof.desk.tracker import track_stock
    t = track_stock(bars([101, 102, 103, 104, 105]), [], D0, 1)
    assert t["move"] == pytest.approx(0.05) and t["ret"] == pytest.approx(0.049)


def test_mark_price_uses_live_only_while_the_market_is_open():
    """After the close every page marks an open hold at the session's close, so Sightings, the ticker page, the MCP
    and Track record agree to the cent (ZETA 10-06: a late quote showed +6.0% on Sightings vs +2.8% on Track record)."""
    from datetime import datetime, timezone
    from whaleproof.desk.tracker import mark_price
    from whaleproof.core.data_layer.models import Bar
    bars = [Bar(date(2026, 10, 6), 32.0, 33.0, 31.9, 32.95, 1e6)]
    open_now = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)        # 11:00 ET, market open
    after = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)            # 23:00 ET
    assert mark_price(33.95, "2026-10-06T14:59:00+00:00", bars, open_now) == (33.95, "live")
    assert mark_price(33.95, "2026-10-07T02:59:00+00:00", bars, after) == (32.95, "close")
    assert mark_price(None, None, bars, open_now) == (32.95, "close")
    assert mark_price(33.95, "2026-10-05T19:00:00+00:00", bars, open_now) == (32.95, "close")   # yesterday's quote
    assert mark_price(None, None, [], after) == (None, None)


def test_live_mark_is_the_one_open_hold_price_for_sightings_and_track_record():
    """Owner 10-07: Track record's open holds sat on the last close while Sightings moved live. One helper now
    prices an open hold for both: entry = first open on/after the entry day, price = mark_price, move/net = stock_move."""
    from datetime import datetime, timezone
    from whaleproof.desk.tracker import live_mark
    from whaleproof.core.data_layer.models import Bar
    bars = [Bar(date(2026, 10, 5), 30.0, 31.0, 29.0, 30.5, 1e6),     # signal day, before entry
            Bar(date(2026, 10, 6), 32.0, 33.0, 31.9, 32.95, 1e6)]
    open_now = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
    m = live_mark(bars, date(2026, 10, 6), 1, 33.6, "2026-10-06T14:59:00+00:00", open_now)
    assert m["entry"] == 32.0 and m["price"] == 33.6 and m["source"] == "live" and m["at"] == "2026-10-06T14:59:00+00:00"
    assert m["move"] == pytest.approx(0.05) and m["net"] == pytest.approx(0.049)
    after = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)
    m = live_mark(bars, date(2026, 10, 6), -1, 33.6, "2026-10-07T02:59:00+00:00", after)
    assert m["price"] == 32.95 and m["source"] == "close" and m["at"] is None and m["move"] == pytest.approx(-0.0296875)
    m = live_mark(bars[:1], date(2026, 10, 6), 1, 33.6, "2026-10-06T14:59:00+00:00", open_now)
    assert m["entry"] is None and m["move"] is None                   # entry day not traded yet → no result


def test_option_now_is_the_live_bid_against_what_was_paid():
    """Owner 10-07: open holds show the whale's option live too. Same sell rule as the record (the bid), only while
    the market is open and the quote is from today; otherwise None and the page keeps the last closing bid."""
    from datetime import datetime, timezone
    from whaleproof.desk.tracker import option_now
    open_now = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)
    o = option_now(10.0, {"bid": 12.5, "ask": 12.9}, "2026-10-06T14:55:00+00:00", open_now)
    assert o == {"bid": 12.5, "at": "2026-10-06T14:55:00+00:00", "ret": pytest.approx(0.25)}
    after = datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)
    assert option_now(10.0, {"bid": 12.5}, "2026-10-07T02:55:00+00:00", after) is None
    assert option_now(10.0, {"bid": None, "ask": 1.0}, "2026-10-06T14:55:00+00:00", open_now) is None   # no trade yet
    assert option_now(10.0, {"bid": 12.5}, "2026-10-05T19:55:00+00:00", open_now) is None             # yesterday
    assert option_now(None, {"bid": 12.5}, "2026-10-06T14:55:00+00:00", open_now) is None             # not bought yet


def test_hold_day_is_one_count_for_every_page():
    """'day N of 5' = sessions since the entry open, today counted once the market has opened; holidays skipped."""
    from datetime import datetime, timezone
    from whaleproof.desk.tracker import hold_day
    entry = date(2026, 10, 5)                                                     # Monday
    assert hold_day(entry, datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc)) == 0  # 09:00 ET, before the open
    assert hold_day(entry, datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)) == 1
    assert hold_day(entry, datetime(2026, 10, 7, 3, 0, tzinfo=timezone.utc)) == 2   # Tue 23:00 ET
    assert hold_day(entry, datetime(2026, 10, 20, 15, 0, tzinfo=timezone.utc)) == 5  # capped
    assert hold_day(date(2026, 11, 25), datetime(2026, 11, 27, 15, 0, tzinfo=timezone.utc)) == 2  # Thanksgiving skipped


def test_a_hold_is_open_until_its_sell_day_close():
    """Owner 10-07: after the Oct 7 close, Sightings still showed the Sep 30 signals as 'day 5 of 5, sells Oct 7'."""
    from datetime import datetime, timezone
    from whaleproof.desk.tracker import still_holding
    sell = date(2026, 10, 7)                                                       # Wednesday
    assert still_holding(sell, datetime(2026, 10, 7, 19, 0, tzinfo=timezone.utc))      # 15:00 ET, sells at the close
    assert not still_holding(sell, datetime(2026, 10, 7, 20, 30, tzinfo=timezone.utc))  # 16:30 ET, sold
    assert not still_holding(sell, datetime(2026, 10, 8, 13, 0, tzinfo=timezone.utc))   # next morning
    assert still_holding(date(2026, 10, 8), datetime(2026, 10, 7, 23, 0, tzinfo=timezone.utc))
def test_today_move_is_since_yesterdays_close_or_since_this_mornings_entry():
    """Owner 10-07: Sightings tape shows each open hold's move today (and the book's average)."""
    from datetime import datetime, timezone
    from whaleproof.desk.tracker import today_move
    b = [Bar(date(2026, 10, 5), 10, 10, 10, 10.0, 1), Bar(date(2026, 10, 6), 10.2, 11, 10, 10.5, 1),
         Bar(date(2026, 10, 7), 10.4, 11, 10, 10.8, 1)]
    after_close = datetime(2026, 10, 7, 22, 0, tzinfo=timezone.utc)                 # 18:00 ET, prices = closes
    m = today_move(b, date(2026, 10, 6), 1, None, None, after_close)
    assert m["day"] == date(2026, 10, 7) and abs(m["move"] - (10.8 / 10.5 - 1)) < 1e-12 and m["price"] == 10.8
    assert m["since"] == "prev_close"
    m = today_move(b, date(2026, 10, 7), 1, None, None, after_close)                 # bought at today's open
    assert abs(m["move"] - (10.8 / 10.4 - 1)) < 1e-12 and m["since"] == "entry_open"
    live = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)                         # 11:00 ET, live quote
    m = today_move(b[:2], date(2026, 10, 6), -1, 10.0, "2026-10-07T14:59:00+00:00", live)
    assert m["day"] == date(2026, 10, 7) and abs(m["move"] - -(10.0 / 10.5 - 1)) < 1e-12   # bearish: falling = gain
    assert today_move([], date(2026, 10, 6), 1, None, None, after_close)["since"] is None
    assert today_move([], date(2026, 10, 6), 1, None, None, after_close)["move"] is None
    assert today_move(b[:2], date(2026, 10, 7), 1, 10.0, "2026-10-07T14:59:00+00:00", live)["move"] is None  # open unknown


def test_todays_unfinished_bar_does_not_finish_a_hold_or_count_as_a_close():
    """Daily bars include today's unfinished candle; on the sell day a hold read 'finished' at a mid-day price and
    Track record said 'Prices through the Tue, Oct 13 close' at 10 AM (owner 10-13 sweep)."""
    b = bars([101, 103, 99, 104, 106])                  # 5th bar = Mon 09-28, still trading
    t = track_stock(b, [], D0, 1, unfinished=date(2026, 9, 28))
    assert t["status"] == "open" and t["exit"] is None and t["priced_through"] == "2026-09-25"
    done = track_stock(b, [], D0, 1)                    # after the close the same bars finish it
    assert done["status"] == "closed" and done["priced_through"] == "2026-09-28"


def _srow(t, through, sector=None):
    return {"ticker": t, "sector": sector, "stock": {"priced_through": through}}


def test_settle_items_are_every_hold_priced_through_that_close_plus_spy_and_sector_etfs():
    """Owner 10-13: CRDO's exit was UW's 16:15 bar (198.45), not the official close (198.31) UW shows by morning."""
    from whaleproof.desk.tracker import settle_items
    rows = [_srow("CRDO", "2026-10-13", "Technology"), _srow("CEG", "2026-10-13"), _srow("OLD", "2026-10-02"),
            {"ticker": "NOPE", "stock": None}]
    assert settle_items(rows, date(2026, 10, 13)) == ["SPY", "CRDO", "CEG", "XLK"]
    assert settle_items(rows, date(2026, 10, 2)) == ["SPY", "OLD"]


def test_settle_update_refetches_the_next_morning_once_per_ticker(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import whaleproof.desk.tracker as tr
    st = Store(tmp_path / "c.sqlite")
    calls = []
    monkeypatch.setattr(tr, "ingest_bars", lambda c, s, t, ttl: calls.append((t, ttl)))
    items = lambda d: ["SPY", f"T{d.day}"]                                         # noqa: E731
    utc = lambda d, h: datetime(2026, 10, d, h, 0, tzinfo=timezone.utc)            # noqa: E731  EDT = UTC−4
    # Tue 21:00 ET: Tue's close is too fresh; Monday's is due (the desk was off Tue morning)
    assert tr.settle_update(object(), st, items, date(2026, 10, 13), utc(14, 1)) == ["SPY", "T12"]
    assert calls == [("SPY", 0), ("T12", 0)]
    calls.clear()
    assert tr.settle_update(object(), st, items, date(2026, 10, 13), utc(14, 12)) == ["SPY", "T13"]   # Wed 08:00 ET
    calls.clear()
    assert tr.settle_update(object(), st, items, date(2026, 10, 13), utc(14, 13)) == [] and calls == []  # once
    assert tr.settle_update(object(), st, items, date(2026, 10, 16), utc(17, 12)) == ["SPY", "T15", "T16"]  # Sat 08:00


def test_live_day_is_saved_only_once_caught_up(tmp_path):
    """Bug 10-16: Oct 16 was saved from a partial alert list. A day not yet caught up shows its signals but writes
    nothing, so the next look (after the catch-up) can still add a late signal; a caught-up day is saved once."""
    from whaleproof.desk.tracker import saved_day
    early = [{"id": "e", "ticker": "EWY"}]
    assert saved_day(tmp_path / "live", "2026-10-16", lambda: early, final=False) == early
    assert not (tmp_path / "live" / "2026-10-16.json").exists()
    full = early + [{"id": "c", "ticker": "CIEN"}]
    assert saved_day(tmp_path / "live", "2026-10-16", lambda: full, final=True) == full
    assert saved_day(tmp_path / "live", "2026-10-16", lambda: early, final=True) == full         # saved file wins
    assert saved_day(tmp_path / "live", "2026-10-16", lambda: early, final=False) == full        # …either way
