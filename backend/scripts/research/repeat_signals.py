"""Same ticker signalled again while the first 5-session hold is still open — is the repeat signal worth adding to?

Cache only (no UW API calls). Reads the point-in-time history rows (scripts/desk_build_rows.py → data/desk/*.pkl).
Run:  cd backend && uv run python scripts/research/repeat_signals.py   →  journal/research/repeat-signals.json

Unit = one ticker-session (several signals on the same ticker the same day share one entry, so they count once).
"Repeat" = the ticker already had a signal in the previous 4 sessions (its 5-session hold is still open).
Outcome = x5: 5-session stock return in the signal direction minus SPY, entry next open, 0.10% cost.
Exploratory: run after the frozen filter's single holdout test; describes, cannot re-tune."""
from __future__ import annotations

import json
from datetime import date

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT, load_settings
from whaleproof.core.data_layer.store import Store
from whaleproof.desk.config import HOLDOUT, TRAIN

from vehicle_study import load, summ

WINDOWS = {"pre": (date(2023, 10, 1), TRAIN[0]), "train": TRAIN, "holdout": HOLDOUT,
           "post": (date(2026, 6, 1), date(2026, 9, 22))}
OUT = REPO_ROOT / "journal" / "research" / "repeat-signals.json"
HOLD = 5


def window_of(d: date) -> str | None:
    return next((k for k, (a, b) in WINDOWS.items() if a <= d <= b and not (k == "pre" and d == b)), None)


def main() -> None:
    _, rows = load(Store(load_settings().db_path))
    days: dict[tuple[str, date], float] = {}
    for h in rows:
        if h.tier and h.x5 is not None:
            days.setdefault((h.ticker, h.session_date), h.x5)   # same ticker + day → same entry, same x5
    by_t: dict[str, list[date]] = {}
    for t, d in days:
        by_t.setdefault(t, []).append(d)
    out: dict = {}
    for t, ds in by_t.items():
        ds.sort()
        for i, d in enumerate(ds):
            w = window_of(d)
            if not w:
                continue
            # sessions between the earlier signal and this one; < HOLD means the earlier hold is still open
            gaps = [len(mc.sessions(p, d)) - 1 for p in ds[:i]]
            open_prior = any(0 < g < HOLD for g in gaps)
            k = "repeat (earlier hold still open)" if open_prior else "first (no open hold)"
            out.setdefault(w, {}).setdefault(k, []).append(days[(t, d)])
    rep = {"meta": {"generated": date.today().isoformat(), "hold_sessions": HOLD,
                    "windows": {k: [str(a), str(b)] for k, (a, b) in WINDOWS.items()},
                    "note": __doc__.split("\n\n", 1)[1]},
           "by_window": {w: {k: summ(v) for k, v in d.items()} for w, d in out.items()}}
    OUT.write_text(json.dumps(rep, indent=1, default=str))
    for w, d in rep["by_window"].items():
        for k, s in d.items():
            print(f"{w:8} {k:34} n={s['n']:5} mean={s.get('mean', 0):+.2%} median={s.get('median', 0):+.2%} "
                  f"win={s.get('win_rate', 0):.0%}")


if __name__ == "__main__":
    main()
