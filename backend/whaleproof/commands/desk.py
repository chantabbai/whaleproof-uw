"""`whaleproof desk quickstart|up|down|status`: start/stop the dashboard on Windows, macOS and Linux (ports 8100/3100)."""
from __future__ import annotations

from whaleproof import launcher

USAGE = "usage: whaleproof desk {quickstart,up,down,status} [args]"


def main(argv: list[str]) -> int:
    launcher.safe_console()
    cmd, rest = (argv[0], argv[1:]) if argv else ("up", [])
    if cmd == "quickstart":
        return launcher.quickstart(rest)
    if cmd == "up":
        return launcher.up()
    if cmd == "down":
        return launcher.down()
    if cmd == "status":
        return launcher.status()
    print(USAGE)
    return 2
