"""`whaleproof mcp` — run the WhaleProof MCP server over stdio for any MCP app (read-only, no UW calls)."""
from __future__ import annotations

from whaleproof.mcp_server import build_server, local_api


def main(argv: list[str]) -> int:
    build_server(local_api()).run(transport="stdio")
    return 0
