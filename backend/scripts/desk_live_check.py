"""Live verification of a running Signal Desk: `uv run python scripts/desk_live_check.py [HH:MM ...]`.
With times, waits for each ET time and appends a PASS/FAIL snapshot to data/live_check.log; without, checks once now.
Reads only the local API (no UW calls of its own)."""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from whaleproof.config import REPO_ROOT

API = "http://127.0.0.1:8100/api/desk"
NY = ZoneInfo("America/New_York")
LOG = REPO_ROOT / "data" / "live_check.log"
IGNORED = ("earnings:", "vol:", "sector:", "oi:")


def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{API}/{path}", timeout=30) as r:
        return json.loads(r.read())


def check(prev: dict | None) -> tuple[list[tuple[str, bool, str]], dict]:
    st, td, dy = _get("status"), _get("today"), _get("day")
    now = datetime.now(NY)
    today = now.date().isoformat()
    is_open = st["clock"]["state"] == "open"
    failing = [k for k in st["failing"] if not k.startswith(IGNORED)]
    raw = (td.get("funnel") or {}).get("raw", 0)
    used = (st.get("usage") or {}).get("count")
    gex = (td["regime"].get("gex") or {}).get("SPY") or {}
    res = [
        ("clock state", st["clock"]["state"] in ("pre", "open", "after", "closed"), st["clock"]["label"]),
        ("data day", (st["data_day"] == today) if is_open else True, f"{st['data_day']} (today {today}, open={is_open})"),
        ("today funnel has alerts", raw > 0, f"raw={raw}"),
        ("tide has points", len(dy.get("tide") or []) > 1, f"tide_day={dy.get('tide_day')} points={len(dy.get('tide') or [])}"),
        ("SPY GEX levels", gex.get("gamma_flip") is not None, f"flip={gex.get('gamma_flip')} date={gex.get('date')}"),
        ("no failing live sources", not failing, ",".join(failing) or "none"),
        ("live refresh recent", st.get("refreshed_at") is not None, str(st.get("refreshed_at"))),
    ]
    if prev and prev.get("used") is not None and used is not None:
        left = 40_000 - 1_500 - used
        res.append(("UW budget on track", not st["usage"].get("stopped") and left > 2_000,
                    f"+{used - prev['used']} since last check, {used} total, {left} left before reserve, "
                    f"pace ×{st['usage'].get('pace')}"))
    if prev and is_open and prev.get("day") == st["data_day"]:
        res.append(("flow growing", raw >= prev["raw"], f"{prev['raw']} → {raw}"))
    return res, {"used": used, "raw": raw, "day": st["data_day"]}


def run_once(prev: dict | None) -> dict:
    stamp = datetime.now(NY).strftime("%Y-%m-%d %H:%M:%S ET")
    try:
        res, state = check(prev)
    except Exception as e:  # noqa: BLE001 — a down API is itself the finding
        line = f"{stamp} FAIL api unreachable: {e}"
        print(line)
        LOG.open("a").write(line + "\n")
        return prev or {}
    ok = all(r[1] for r in res)
    lines = [f"{stamp} {'PASS' if ok else 'FAIL'}"] + [f"   {'ok ' if r[1] else 'BAD'} {r[0]}: {r[2]}" for r in res]
    print("\n".join(lines), flush=True)
    LOG.open("a").write("\n".join(lines) + "\n")
    return state


def main(times: list[str]) -> None:
    prev = None
    if not times:
        run_once(None)
        return
    for t in times:
        h, m = map(int, t.split(":"))
        while (now := datetime.now(NY)) < now.replace(hour=h, minute=m, second=0, microsecond=0):
            time.sleep(20)
        prev = run_once(prev)


if __name__ == "__main__":
    main(sys.argv[1:])
