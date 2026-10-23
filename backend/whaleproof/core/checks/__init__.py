from .base import CheckResult, clip, unavailable
from .confluence import dp_blocks, insider, oi_confirm, sector_flow, ticker_flow, uw_flagged
from .quality import iv_rv, macro_event, option_sentiment, skew
from .flow import chase_guard, flow_quality, liquidity, persistence
from .structure import catalyst, dark_pool, gamma_room, regime, unusualness, vol_price

ALL_CHECKS = [flow_quality, persistence, gamma_room, dark_pool, vol_price,
              unusualness, regime, catalyst, liquidity, chase_guard,
              dp_blocks, ticker_flow, sector_flow, insider, oi_confirm, uw_flagged,
              skew, option_sentiment, iv_rv, macro_event]
