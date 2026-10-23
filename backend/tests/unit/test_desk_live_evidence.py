"""Live row of 'Does the filter help?' (owner 10-07): live days scored exactly like the four history periods."""
from datetime import date

from tests.unit.test_simple_backtest import D0, bars, put_alert, seed
from whaleproof.desk import live_evidence as LE
from whaleproof.desk.history import classify_rows, load_raw


def test_live_rows_equal_what_the_history_builder_would_pickle(store, tmp_path):
    """Same run_simple_backtest + the same row/extra conversion the pickles use, so the scoring can't drift."""
    import dataclasses
    import pickle

    from whaleproof.core.backtest.simple import run_simple_backtest
    seed(store)
    rows, _ = run_simple_backtest(store, D0, D0)
    blob = {"rows": [dataclasses.asdict(r) for r in rows], "extra": LE.extras(store, rows), "skipped": 0}
    (tmp_path / f"rows_{D0}_{D0}.pkl").write_bytes(pickle.dumps(blob))
    hist = classify_rows(load_raw(tmp_path), {})
    live = LE.rows(store, D0, D0)["rows"]
    assert [(h.alert_id, h.x5, h.stage, h.tier) for h in hist] == [(h.alert_id, h.x5, h.stage, h.tier) for h in live]


def test_index_options_are_left_out_like_the_history_days(store):
    seed(store)
    put_alert(store, id="spx", ticker="SPXW", created_at="2026-09-22T15:00:00Z", underlying_price="6600",
              strike="6700", expiry="2026-10-16", option_chain="SPXW261016C06700000")
    bars(store, "SPXW", 1.0)
    out = LE.rows(store, D0, date(2026, 9, 29))                          # D0's hold over
    assert "SPXW" not in {r.ticker for r in out["rows"]}
    assert out["unpriced"] == 1                                          # NP: a bet with no prices yet


def test_due_tickers_are_bets_whose_hold_ended_without_an_exit_price(store):
    seed(store)
    put_alert(store, id="spx", ticker="SPXW", created_at="2026-09-22T15:00:00Z", underlying_price="6600",
              strike="6700", expiry="2026-10-16", option_chain="SPXW261016C06700000")
    # D0 = Tue Sep 22 → hold Sep 23..29; seeded bars run 40 days except NP (none) and SPXW (index, skipped)
    assert LE.due_tickers(store, date(2026, 9, 28), start=D0) == []        # hold not over yet
    assert LE.due_tickers(store, date(2026, 9, 29), start=D0) == ["NP"]


def test_exit_tickers_are_bets_whose_hold_ended_on_that_day_priced_or_not(store):
    """10-13: the exit-day bar fetched at 16:15 can be the last trade before the closing auction; these get refetched
    the next morning (tracker.settle_update)."""
    seed(store)
    put_alert(store, id="spx", ticker="SPXW", created_at="2026-09-22T15:00:00Z", underlying_price="6600",
              strike="6700", expiry="2026-10-16", option_chain="SPXW261016C06700000")
    got = LE.exit_tickers(store, date(2026, 9, 29), start=D0)              # D0's hold ends Sep 29
    assert "NP" in got and "SPXW" not in got and got == sorted(got) and len(got) > 1
    assert LE.exit_tickers(store, date(2026, 9, 28), start=D0) == []        # nothing ended that day


def test_bets_still_in_their_hold_are_open_not_unpriced(store):
    """Owner 10-07: '1,288 still unpriced' was mostly bets whose 5-session hold hadn't ended — count those as open."""
    seed(store)
    out = LE.rows(store, D0, date(2026, 9, 28))                          # D0 hold ends Sep 29: not over yet
    assert out["unpriced"] == 0 and out["open"] > 0
    out = LE.rows(store, D0, date(2026, 9, 29))                          # hold over: only NP lacks prices
    assert out["unpriced"] == 1 and out["open"] == 0
