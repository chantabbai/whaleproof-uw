"""Single source of Signal Desk settings: filter thresholds, windows, refresh intervals, budget, ports."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

API_PORT, UI_PORT = 8100, 3100

# Validation windows. Tune on TRAIN only; HOLDOUT is evaluated once by `whaleproof desk-holdout`.
TRAIN = (date(2024, 10, 1), date(2025, 9, 30))
HOLDOUT = (date(2025, 10, 1), date(2026, 5, 29))
POST = (date(2026, 6, 1), None)          # previously seen months: descriptive only
PRE = (date(2023, 10, 31), date(2024, 9, 27))   # second out-of-sample test, docs/PREPERIOD-TEST.md (run once)

FORWARD_START = date(2026, 9, 30)    # live forward record (signal tracker 'Live' period) starts here
HOLD_SESSIONS = 5                         # entry next open → close of the 5th session
RAW_MIN_PREMIUM = 100_000                 # the cache (and live pull) holds UW flow alerts at or above this premium


@dataclass(frozen=True)
class FilterConfig:
    """Conviction filter. Defaults were chosen on TRAIN only (see docs/METHODOLOGY.md) and frozen before the holdout."""
    whale_premium: float = 1_000_000      # tier "whale": premium at or above …
    whale_min_otm: float = 0.05           # … and more than 5% out of the money
    far_otm: float = 0.15                 # tier "far_otm": more than 15% OTM …
    far_otm_max_value: str = "fair"       # … and the option not rich (cheap or fair)
    longs_only: bool = True               # bearish buys lost money on train (hedge-heavy)
    min_stock_price: float = 5.0          # UW liquidity guidance: avoid < $5 stocks
    block_earnings_in_hold: bool = True   # IV crush + gap risk; train pre_earnings was clearly negative

    def as_dict(self) -> dict:
        return dict(self.__dict__)


DEFAULT_FILTER = FilterConfig()

# Live refresh (seconds). Past dates are cached forever.
TTL = {"flow": 60, "tide": 300, "gex": 900, "calendar": 5 * 3600, "context": 12 * 3600, "info": None, "oi": 3 * 3600}
UI_REFRESH_S = {"day": 60, "today": 300, "swing": 900}

# Budget: stop live pulls when the shared key's daily count is within this reserve of the limit.
LIVE_RESERVE = 1_500
EVENING_KEEP = 1_000        # calls kept for after-close refreshes before the 20:00 ET reset

# Live mode (owner 2026-09-30): "eod" = UW pulls only in the end-of-day window on trading days (final flow through the
# 4:15 PM decision, tide, GEX, OI, earnings, prices → confirm tomorrow's trades); "full" = all day. Env SIGNALDESK_LIVE.
LIVE_MODE_DEFAULT = "full"
EOD_ONLY_THROUGH = "2026-09-30"     # owner: today only (calls go to the option-leg fetch); full live again from 10-01
EOD_WINDOW = ((15, 30), (17, 0))
EOD_EVERY = {"flow": 300, "spot": 300, "tide": 900, "quotes": 900, "gex": 1800, "oi": 3600, "signals": 300}

# Live cadence while the market is open (seconds, before the budget governor stretches them)
OPEN_EVERY = {"flow": 60, "spot": 60, "tide": 120, "quotes": 300, "gex": 900, "oi": 1800, "signals": 60}
DAILY_LIMIT = 40_000

# Cash-settled index options: UW history replies omit their underlying price, so history days never had them; the
# live funnel, bets and the live evidence row leave them out too (10-04).
INDEX_TICKERS = frozenset({"SPX", "SPXW", "XSP", "NDX", "NDXP", "RUT", "RUTW", "MRUT", "VIX", "VIXW", "DJX", "OEX", "XEO"})
