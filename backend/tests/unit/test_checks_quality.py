"""Quality checks from the endpoint review: skew, option_sentiment, iv_rv, macro_event. All weight 0 — fit decides."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from whaleproof.core.checks import ALL_CHECKS
from whaleproof.core.checks.quality import iv_rv, macro_event, option_sentiment, skew
from whaleproof.core.data_layer import ingest
from whaleproof.core.data_layer.context import AlertContext
from whaleproof.core.verdict.weights import BACKTESTABLE, CURRENT

D = date(2026, 9, 22)          # Tuesday
AS_OF = datetime(2026, 9, 22, 20, 15, tzinfo=timezone.utc)
NEW = ("skew", "option_sentiment", "iv_rv", "macro_event")


def ctx(alert, **over):
    base = dict(alert=alert, as_of=AS_OF, gex=None, dp_levels=None, iv_rank=None, unusual_pct=None,
                tide=None, earnings=[], same_dir_recent=0, ref_price=None)
    base.update(over)
    return AlertContext(**base)


def bull(make_alert):
    return make_alert(created_at="2026-09-22T15:00:00Z")


def bear(make_alert):
    return make_alert(created_at="2026-09-22T15:00:00Z", type="put", option_chain="NVDA261016P00180000",
                      strike="180")


def history(last_value, n=100, base=0.02):
    """n daily rr25 points ending on D; all `base` except the last."""
    pts = [((D - timedelta(days=n - 1 - i)).isoformat(), base + 0.0001 * (i % 7)) for i in range(n)]
    pts[-1] = (D.isoformat(), last_value)
    return pts


# ---------- skew ----------
def test_skew_high_put_skew_is_bearish(make_alert):
    rr = history(0.10)                      # far above its own history → puts bid → bearish
    assert skew(ctx(bull(make_alert), rr25=rr)).score < -0.9
    assert skew(ctx(bear(make_alert), rr25=rr)).score > 0.9
    low = skew(ctx(bull(make_alert), rr25=history(-0.05)))
    assert low.score > 0.9 and "put skew" in low.reason


def test_skew_point_in_time_and_min_history(make_alert):
    future = history(0.0203) + [((D + timedelta(days=1)).isoformat(), 0.50)]
    assert abs(skew(ctx(bull(make_alert), rr25=future)).score) < 0.5     # D+1 value ignored
    assert not skew(ctx(bull(make_alert), rr25=history(0.1, n=30))).available   # < 60 points
    stale = [(d, v) for d, v in history(0.1) if d < (D - timedelta(days=5)).isoformat()]
    assert not skew(ctx(bull(make_alert), rr25=stale)).available         # no value within 3 days of D
    assert not skew(ctx(bull(make_alert))).available


def test_ingest_skew_stores_sorted_series(store):
    class F:
        calls = []

        def get(self, path, params=None):
            self.calls.append((path, params))
            return {"data": [{"date": "2026-09-21", "delta": 25, "risk_reversal": "0.031", "ticker": "NVDA"},
                             {"date": "2026-09-18", "delta": 25, "risk_reversal": "0.020", "ticker": "NVDA"},
                             {"date": "2026-09-19", "risk_reversal": None}]}
    f = F()
    ingest.ingest_skew(f, store, "NVDA", D)
    assert f.calls[0][0] == "/api/stock/NVDA/historical-risk-reversal-skew"
    assert f.calls[0][1]["delta"] == "25" and f.calls[0][1]["timeframe"] == "3Y"
    assert store.get_metric("NVDA", "all", "rr25") == [["2026-09-18", 0.02], ["2026-09-21", 0.031]]


# ---------- option_sentiment ----------
def test_option_sentiment_aligns_with_direction(make_alert):
    assert option_sentiment(ctx(bull(make_alert), opt_sentiment=0.6)).score == 0.6
    assert option_sentiment(ctx(bear(make_alert), opt_sentiment=0.6)).score == -0.6
    assert option_sentiment(ctx(bull(make_alert), opt_sentiment=5.0)).score == 1.0     # clipped
    assert not option_sentiment(ctx(bull(make_alert))).available


# ---------- iv_rv ----------
def vol_rows():
    # [iv_date, iv, rv, rv_window_end]
    return [["2026-08-20", 0.40, 0.30, "2026-09-18"],     # RV window ended before D → usable trailing RV
            ["2026-08-21", 0.41, 0.90, "2026-09-23"],     # window ends after D → future data, must be ignored
            ["2026-09-22", 0.36, None, None]]             # IV observed on D


def test_iv_rv_uses_iv_on_d_and_trailing_rv_only(make_alert):
    c = iv_rv(ctx(bull(make_alert), vol_hist=vol_rows()))
    assert c.available and "IV 36%" in c.reason and "RV 30%" in c.reason   # 0.36 / 0.30 = 1.2
    assert abs(c.score - (-0.1)) < 1e-9                                    # (1.15 − 1.2) / 0.5


def test_iv_rv_cheap_positive_rich_negative_and_unavailable(make_alert):
    cheap = [["2026-08-20", 0.4, 0.40, "2026-09-18"], ["2026-09-22", 0.2, None, None]]
    rich = [["2026-08-20", 0.4, 0.20, "2026-09-18"], ["2026-09-22", 0.6, None, None]]
    assert iv_rv(ctx(bull(make_alert), vol_hist=cheap)).score == 1.0
    assert iv_rv(ctx(bear(make_alert), vol_hist=rich)).score == -1.0        # not directional
    no_iv_today = [["2026-08-20", 0.4, 0.3, "2026-09-18"]]
    assert not iv_rv(ctx(bull(make_alert), vol_hist=no_iv_today)).available
    assert not iv_rv(ctx(bull(make_alert))).available


def test_ingest_realized_vol_keeps_window_end(store):
    class F:
        def get(self, path, params=None):
            assert path == "/api/stock/NVDA/volatility/realized" and params["days"] == 21
            return {"data": [{"date": "2026-08-20", "implied_volatility": "0.40", "realized_volatility": "0.30",
                              "unshifted_rv_date": "2026-09-18"},
                             {"date": "2026-09-22", "implied_volatility": "0.36", "realized_volatility": None,
                              "unshifted_rv_date": None}]}
    ingest.ingest_realized_vol(F(), store, "NVDA", D)
    assert store.get_metric("NVDA", "all", "vol_hist") == vol_rows()[::2]


# ---------- macro_event ----------
def ev(day, name, hour=12):
    return [f"{day}T{hour:02d}:30:00+00:00", name]


def test_macro_event_in_holding_window(make_alert):
    # entry Wed 09-23, hold 5 sessions → through Tue 09-29 close
    cal = [ev("2026-09-15", "Retail sales"), ev("2026-09-25", "PCE index"), ev("2026-10-02", "Employment situation")]
    c = macro_event(ctx(bull(make_alert), econ=cal))
    assert c.score == -1.0 and "PCE" in c.reason and "macro_event" in c.tags
    quiet = [ev("2026-09-15", "Retail sales"), ev("2026-10-02", "Employment situation")]
    assert macro_event(ctx(bull(make_alert), econ=quiet)).score == 0.0
    minor = [ev("2026-09-24", "Consumer sentiment (final)"), ev("2026-10-02", "CPI")]
    assert macro_event(ctx(bull(make_alert), econ=minor)).score == 0.0       # not a major event


def test_macro_event_unavailable_without_calendar_coverage(make_alert):
    assert not macro_event(ctx(bull(make_alert))).available
    far = [ev("2025-01-10", "CPI")]
    assert not macro_event(ctx(bull(make_alert), econ=far)).available      # calendar doesn't cover this week


def test_ingest_econ_calendar_merges(store):
    class F:
        def get(self, path, params=None):
            return {"data": [{"event": "FOMC", "time": "2026-10-28 18:00:00+00:00", "type": "fomc"}]}
    store.put_metric("MARKET", "all", "econ", [["2026-10-14 12:30:00+00:00", "CPI"]])   # from an earlier fetch
    ingest.ingest_econ_calendar(F(), store)
    got = store.get_metric("MARKET", "all", "econ")
    assert [e[1] for e in got] == ["CPI", "FOMC"]                          # accumulates across fetches


# ---------- wiring ----------
def test_registered_backtestable_weight_zero():
    names = [f.__name__ for f in ALL_CHECKS]
    for n in NEW:
        assert n in names and n in BACKTESTABLE and CURRENT.w[n] == 0.0
    assert abs(sum(CURRENT.w.values()) - 1) < 1e-9


def test_context_defaults_keep_old_callers_working(make_alert):
    c = ctx(bull(make_alert))
    assert c.rr25 is None and c.opt_sentiment is None and c.vol_hist is None and c.econ is None
    assert replace(c, econ=[]).econ == []
