from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

GATES = {"liquidity", "chase_guard"}
# Checks whose inputs exist historically (docs/endpoint-matrix.md Decisions).
BACKTESTABLE = {"flow_quality", "persistence", "gamma_room", "dark_pool", "vol_price", "regime", "catalyst",
                "dp_blocks", "ticker_flow", "sector_flow", "insider", "uw_flagged",
                "skew", "option_sentiment", "iv_rv", "macro_event"}


@dataclass(frozen=True)
class Weights:
    version: str
    w: dict[str, float]
    meta: dict = field(default_factory=dict)


V0 = Weights("v0", {"flow_quality": 0.25, "persistence": 0.15, "gamma_room": 0.15, "dark_pool": 0.10,
                    "vol_price": 0.10, "unusualness": 0.10, "regime": 0.10, "catalyst": 0.05},
             {"source": "hand-set prior (spec §10)"})

# v0.5 (Plan 1.5): adds dark-pool blocks, ticker/sector flow, insiders. oi_confirm is a pre-open stage, not scored.
V05 = Weights("v0.5", {"flow_quality": 0.20, "persistence": 0.10, "gamma_room": 0.12, "dark_pool": 0.08,
                           "dp_blocks": 0.08, "ticker_flow": 0.10, "vol_price": 0.08, "unusualness": 0.06,
                           "regime": 0.06, "sector_flow": 0.06, "catalyst": 0.03, "insider": 0.03,
                           "uw_flagged": 0.0, "skew": 0.0, "option_sentiment": 0.0, "iv_rv": 0.0,
                           "macro_event": 0.0},   # weight 0: pre-registered test, fit decides (docs/preregistration.md)
                  {"source": "hand-set prior (Plan 1.5)"})

# v0.6 (Amendment 9): v0.5 weights; live candidates must pass the pure-directional gate before the top-40 cut.
CURRENT = Weights("v0.6", dict(V05.w), {"source": "v0.5 weights + gated candidates (Amendment 9)"})


def save_weights(weights: Weights, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": weights.version, "w": weights.w, "meta": weights.meta},
                               indent=2, sort_keys=True))


def load_weights(path: Path) -> Weights:
    d = json.loads(Path(path).read_text())
    return Weights(d["version"], d["w"], d.get("meta", {}))
