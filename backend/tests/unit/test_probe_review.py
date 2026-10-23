"""Endpoint-review probe (~45 calls): history depth for Tier A/B endpoints + uw_unusual coverage (Amendment 1)."""
import json
from datetime import date

from whaleproof.commands.probe_review import coverage_check, render_review, run_review


class Fake:
    def __init__(self, payloads=None, fail=()):
        self.calls, self.payloads, self.fail = [], payloads or {}, fail

    def get(self, path, params=None):
        from whaleproof.core.data_layer.client import UWError
        self.calls.append((path, dict(params or {})))
        if path in self.fail:
            raise UWError("422 missing param expiry")
        return self.payloads.get(path, {"data": [{"date": "2024-10-25", "x": 1}, {"date": "2026-09-25", "x": 2}]})


def test_review_probe_records_depth_and_errors():
    f = Fake(fail={"/api/stock/NVDA/volatility/option-sentiment"})
    res = run_review(f, date(2026, 9, 28))
    assert len(f.calls) <= 40
    names = {r["name"] for r in res}
    assert {"rr_skew", "realized_vol", "econ_calendar", "option_sentiment", "options_pulse_top"} <= names
    rr = next(r for r in res if r["name"] == "rr_skew")
    assert rr["oldest"] == "2024-10-25" and rr["newest"] == "2026-09-25" and rr["rows"] == 2
    bad = [r for r in res if r["name"] == "option_sentiment"]
    assert bad and all("422" in r["error"] for r in bad)
    md = render_review(res, None)
    assert "| rr_skew |" in md and "Not investment advice" not in md          # metadata only


def test_row_dates_mismatch_flags_stale_fallback():
    stale = {"data": [{"date": "2026-09-25", "ticker": "NVDA", "score": 1}]}
    f = Fake(payloads={"/api/volatility/option-sentiment/top": stale})
    res = run_review(f, date(2026, 9, 28))
    old = next(r for r in res if r["name"] == "option_sentiment_top" and r["when"] == "2024-10-25")
    assert old["stale"] is True                                             # asked 2024 → got 2026 rows


def test_coverage_check_compares_paging_and_slices_with_cached_list():
    cached = {"A", "B", "C"}
    pages = [[{"option_symbol": "A", "premium": "300000"}, {"option_symbol": "B", "premium": "300000"}],
             [{"option_symbol": "C", "premium": "300000"}], []]
    calls = []

    class F:
        def get(self, path, params=None):
            calls.append((path, dict(params or {})))
            if path == "/api/screener/option-contracts":
                return {"data": pages[params.get("page", 0)] if params.get("page", 0) < len(pages) else []}
            return {"data": [{"option_symbol": "A", "premium": "300000"}] if params.get("sectors[]") == "Technology"
                    else []}
    out = coverage_check(F(), date(2026, 7, 1), cached, page_size=2)
    assert out["paging_symbols"] == 3 and out["paging_matches_cached"] is True and out["pages"] == 3
    assert out["slices_symbols"] == 1 and out["slices_matches_cached"] is False
    assert all(p == "/api/screener/option-contracts" for p, _ in calls[:3])
    assert calls[0][1]["unusual"] == "true" and calls[0][1]["date"] == "2026-07-01"
    assert json.dumps(out)                                                  # serialisable for the report
