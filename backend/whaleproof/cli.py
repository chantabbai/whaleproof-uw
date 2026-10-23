from __future__ import annotations

import importlib
import sys

COMMANDS = ["probe", "backfill", "backtest", "scan", "track", "fit", "notify", "confirm", "health", "intraday", "serve", "schedule", "pure", "analyze", "mcp", "marks", "evidence", "quickstart", "forward", "desk"]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in COMMANDS:
        print(f"usage: whaleproof {{{','.join(COMMANDS)}}} [args]")
        return 2
    module = importlib.import_module(f"whaleproof.commands.{argv[0]}")
    return int(module.main(argv[1:]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
