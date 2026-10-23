"""W1-3: descriptive 'why it lost' notes for finished signals that lagged the S&P 500 (cache only, never a filter)."""
from datetime import date, timedelta

from whaleproof.core.data_layer.models import Bar
from whaleproof.desk.postmortem import SECTOR_ETF, why_lost

D0 = date(2026, 1, 5)          # Monday signal day; hold = Jan 6–12 (5 sessions)
DAYS = [D0 + timedelta(days=k) for k in (0, 1, 2, 3, 4, 7)]


def bars(opens_closes: list[tuple[float, float]]) -> list[Bar]:
    return [Bar(d, o, max(o, c), min(o, c), c, 1e6) for d, (o, c) in zip(DAYS, opens_closes)]


FLAT = bars([(100, 100)] * 6)


def row(ret: float, vs: float, direction: int = 1, sector: str | None = "Technology", status: str = "closed") -> dict:
    return {"session_date": D0.isoformat(), "ticker": "AAA", "direction": direction, "sector": sector,
            "stock": {"status": status, "entry_date": DAYS[1].isoformat(), "exit_date": DAYS[5].isoformat(),
                      "ret": ret, "vs_spy": vs, "spy_ret": 0.0}}


def kinds(out: dict) -> list[str]:
    return [n["kind"] for n in out["notes"]]


def test_only_finished_signals_that_lagged_the_sp500_get_notes():
    stock = bars([(100, 100), (100, 101), (101, 102), (102, 103), (103, 104), (104, 105)])
    assert why_lost(row(0.05, 0.04), stock, FLAT, FLAT, {}) is None
    assert why_lost(row(-0.02, -0.03, status="open"), stock, FLAT, FLAT, {}) is None


def test_bought_after_a_jump_then_faded():
    # signal-day close 100, opens 104 (+4% chase), fades to 100 by exit
    stock = bars([(100, 100), (104, 103), (103, 102), (102, 101), (101, 100.5), (100.5, 100)])
    out = why_lost(row(-0.039, -0.039), stock, FLAT, FLAT, {})
    assert "gap_chased" in kinds(out)
    note = next(n for n in out["notes"] if n["kind"] == "gap_chased")
    assert note["text"] == ("Paid up: opened 4.0% above the signal-day close, so part of the move came before the entry, "
                            "then went −3.8% from that open.")


def test_overnight_gap_against_during_hold_explains_most_of_the_loss():
    # entry 100, drifts flat, then gaps 100 → 94 overnight into day 4
    stock = bars([(100, 100), (100, 100), (100, 100), (94, 94), (94, 94), (94, 94)])
    out = why_lost(row(-0.061, -0.061), stock, FLAT, FLAT, {})
    n = next(n for n in out["notes"] if n["kind"] == "overnight_gap")
    assert n["text"] == "Gapped −6.0% against the signal overnight into Jan 8, most of the −6.0% move from entry."


def test_bearish_signal_gap_is_signed_by_direction():
    # short-side signal; price gaps UP 6% overnight = against
    stock = bars([(100, 100), (100, 100), (100, 100), (106, 106), (106, 106), (106, 106)])
    out = why_lost(row(-0.061, -0.061, direction=-1), stock, FLAT, FLAT, {})
    assert "overnight_gap" in kinds(out)
    chased = why_lost(row(-0.03, -0.03, direction=-1), bars([(100, 100), (97, 98)] + [(98, 100)] * 4), FLAT, FLAT, {})
    assert next(n for n in chased["notes"] if n["kind"] == "gap_chased")["text"].startswith(
        "Paid up: opened 3.0% below the signal-day close, so part of the move came before the entry")


def test_winners_get_notes_only_on_request_for_base_rates(tmp_path):
    from whaleproof.core.data_layer.store import Store
    from whaleproof.desk.postmortem import note_rates
    stock = bars([(100, 100), (104, 103), (103, 104), (104, 105), (105, 106), (106, 107)])
    assert why_lost(row(0.03, 0.03), stock, FLAT, FLAT, {}) is None
    assert "gap_chased" in kinds(why_lost(row(0.03, 0.03), stock, FLAT, FLAT, {}, any_result=True))
    s = Store(tmp_path / "t.sqlite")
    s.put_ohlc("AAA", stock)
    rates = note_rates(s, [row(0.03, 0.03), row(-0.01, -0.01, status="open")])
    assert rates["signals"] == {"losers": 0, "winners": 1} and rates["share"]["gap_chased"]["winners"] == 1.0


def test_market_tide_flipped_against_the_signal():
    tide = {D0: 5e7, DAYS[1]: -2e8, DAYS[2]: -1e8, DAYS[3]: 3e7, DAYS[4]: -5e7, DAYS[5]: -1e7}
    out = why_lost(row(-0.03, -0.03), bars([(100, 100)] + [(100, 97)] * 5), FLAT, FLAT, tide)
    n = next(n for n in out["notes"] if n["kind"] == "tide")
    assert n["text"] == ("Market options flow turned against the signal: call-heavy (+$50M) on the signal day, "
                         "put-heavy (−$330M) over the hold.")


def test_tide_already_against_is_not_called_a_flip_and_missing_tide_is_listed():
    tide = {D0: -5e7, DAYS[1]: -2e8, DAYS[2]: -1e8, DAYS[3]: -3e7}
    out = why_lost(row(-0.03, -0.03), FLAT, FLAT, FLAT, tide)
    assert next(n for n in out["notes"] if n["kind"] == "tide")["text"].startswith("Market options flow was against the signal throughout")
    assert "market tide" in why_lost(row(-0.03, -0.03), FLAT, FLAT, FLAT, {})["not_checked"]


def test_sector_dragged_vs_sp500():
    etf = bars([(100, 100), (100, 99), (99, 98), (98, 97), (97, 96.5), (96.5, 96)])      # -4% open→close
    out = why_lost(row(-0.05, -0.05), bars([(100, 100)] + [(100, 95)] * 5), FLAT, etf, {})
    n = next(n for n in out["notes"] if n["kind"] == "sector")
    assert n["text"] == "Sector headwind: Technology (XLK) lagged the S&P 500 by 4.0 points over the hold; the stock did 1.0 points worse than its sector."


def test_no_outside_cause_says_stock_specific_and_unknown_sector_is_listed():
    stock = bars([(100, 100), (100, 99), (99, 98), (98, 97), (97, 96), (96, 95)])
    out = why_lost(row(-0.051, -0.051, sector=None), stock, FLAT, [], {})
    assert kinds(out) == ["stock"] and "sector" in out["not_checked"]
    assert out["notes"][0]["text"] == "No outside cause in the saved data: the stock itself lagged the S&P 500 by 5.1 points."


def test_every_uw_sector_has_an_etf():
    assert set(SECTOR_ETF) == {"Technology", "Consumer Cyclical", "Financial Services", "Industrials", "Healthcare",
                               "Energy", "Basic Materials", "Communication Services", "Consumer Defensive", "Utilities",
                               "Real Estate"}


def test_market_tide_uses_daily_metric_then_a_complete_raw_day(tmp_path):
    import json

    from whaleproof.core.data_layer.store import Store
    from whaleproof.desk.postmortem import market_tide
    s = Store(tmp_path / "t.sqlite")
    s.put_metric("MARKET", date(2026, 9, 29), "tide", 4.5e7)
    for d, ts in (("2026-10-01", "2026-10-01T15:55:00-04:00"), ("2026-10-02", "2026-10-02T11:00:00-04:00")):
        s.cache_put("/api/market/market-tide?" + json.dumps({"date": d, "interval_5m": True}), "/api/market/market-tide",
                    {"data": [{"timestamp": ts, "date": d, "net_call_premium": "10", "net_put_premium": "-5"}]})
    assert market_tide(s, date(2026, 9, 28), date(2026, 10, 2)) == {date(2026, 9, 29): 4.5e7, date(2026, 10, 1): 15.0}


# --- review: what went well / what could have gone better, for every finished signal (owner 10-07) ---
from whaleproof.desk.postmortem import review  # noqa: E402


def full(ret, vs, peak=0.0, dd=0.0, opt=None, direction=1, sector="Technology"):
    r = row(ret, vs, direction, sector)
    r["stock"] |= {"move": ret + 0.001, "peak": peak, "peak_date": DAYS[2].isoformat(), "drawdown": dd,
                   "drawdown_date": DAYS[3].isoformat()}
    r["option"] = None if opt is None else {"ret": opt}
    return r


def test_review_names_what_helped_a_winner():
    up = bars([(100, 100), (100, 101), (101, 102), (102, 103), (103, 104), (104, 105)])
    sector = bars([(100, 100), (100, 101), (101, 102), (102, 103), (103, 103), (103, 103)])
    tide = {DAYS[i]: 5e8 for i in range(6)}
    out = review(full(0.049, 0.04, peak=0.05, opt=0.6), up, FLAT, sector, tide)
    assert [n["kind"] for n in out["went_well"]] == ["beat_spx", "tide_with", "sector_with", "option_beat"]
    assert out["went_well"][0]["text"] == "Beat the S&P 500 by 4.0 points over the hold."
    assert out["better"] == []


def test_review_flags_gains_given_back_and_a_recovery():
    out = review(full(0.004, 0.002, peak=0.07, dd=-0.01), FLAT, FLAT, FLAT, {})
    gb = next(n for n in out["better"] if n["kind"] == "gave_back")
    assert gb["text"] == "Was up 7.0% at its best (Jan 7) but finished up 0.5%: most of the gain went back."
    out = review(full(0.02, 0.01, peak=0.03, dd=-0.05), FLAT, FLAT, FLAT, {})
    rc = next(n for n in out["went_well"] if n["kind"] == "recovered")
    assert rc["text"] == "Was down 5.0% at its worst (Jan 8) and still finished up 2.1%."


def test_review_of_a_loser_keeps_the_why_it_lagged_notes_and_the_option_gap():
    out = review(full(-0.03, -0.04, opt=-0.5), FLAT, FLAT, FLAT, {})
    assert [n["kind"] for n in out["better"]] == ["stock", "option_lagged"]
    assert out["went_well"] == []
    assert review(full(0.02, 0.01) | {"stock": {"status": "open"}}, FLAT, FLAT, FLAT, {}) is None


def test_tide_that_flipped_the_signals_way_says_so():
    """Owner 10-07 screenshot: −$416M on the signal day, +$407M over the hold read as 'leaned with'; it flipped."""
    tide = {DAYS[0]: -4.16e8} | {DAYS[i]: 1.36e8 for i in range(1, 4)}
    out = review(full(0.049, 0.04), FLAT, FLAT, FLAT, tide)
    t = next(n for n in out["went_well"] if n["kind"] == "tide_with")
    assert t["text"] == ("Market options flow turned the signal's way: put-heavy (−$416M) on the signal day, call-heavy "
                         "(+$408M) over the hold.")


def test_note_dates_outside_this_year_carry_the_year_and_minus_is_a_true_minus():
    from whaleproof.desk.postmortem import _md, _pct
    assert _md(date(2024, 1, 8), today=date(2026, 10, 13)) == "Jan 8, 2024"     # a sealed-test trade read "(Jan 8)"
    assert _md(date(2026, 1, 8), today=date(2026, 10, 13)) == "Jan 8"
    assert _pct(-0.82) == "−82.0%"                                               # Track record read "-82.0%"
    assert _pct(0.05) == "+5.0%"
