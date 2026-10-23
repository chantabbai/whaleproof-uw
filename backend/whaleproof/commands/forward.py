"""`whaleproof forward`: export the live forward record → journal/forward-record.json + docs/FORWARD-RECORD.md.
Cache only (reads the dashboard API in-process); no UW calls. Rerun and commit the two files to update the record."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from whaleproof.config import REPO_ROOT
from whaleproof.desk.forward import forward_record, markdown


def main(argv: list[str]) -> int:
    from whaleproof.mcp_server import local_api
    data = local_api()("/api/desk/tracker")
    if not data:
        print("tracker not available (is the cache present?)")
        return 1
    rec = forward_record(data["rows"], datetime.now(UTC).isoformat(timespec="minutes"))
    (REPO_ROOT / "journal" / "forward-record.json").write_text(json.dumps(rec, indent=1) + "\n")
    (REPO_ROOT / "docs" / "FORWARD-RECORD.md").write_text(markdown(rec))
    sm = rec["summary"]
    print(f"forward record: {sm['signals']} signals, {sm['finished']} finished → journal/forward-record.json, "
          "docs/FORWARD-RECORD.md")
    return 0
