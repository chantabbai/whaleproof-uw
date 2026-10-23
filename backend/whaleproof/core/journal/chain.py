from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

GENESIS = "GENESIS"


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _hash(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k != "hash"}
    return hashlib.sha256(canonical(body).encode()).hexdigest()


def read_picks(path: Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            break
    return out


def _repair_tail(path: Path) -> None:
    """Drop a partial last line left by a crash mid-append (earlier lines are fsynced and intact)."""
    if not path.exists():
        return
    raw = path.read_bytes()
    if raw and not raw.endswith(b"\n"):
        path.write_bytes(raw[: raw.rfind(b"\n") + 1])


def append_pick(path: Path, record: dict) -> dict:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    _repair_tail(path)
    if not verify_chain(path):
        raise ValueError(f"journal chain at {path} is broken — refusing to append")
    prev = read_picks(path)
    rec = {**record, "prev_hash": prev[-1]["hash"] if prev else GENESIS}
    rec["hash"] = _hash(rec)
    with path.open("a") as f:
        f.write(canonical(rec) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return rec


def verify_chain(path: Path) -> bool:
    path = Path(path)
    if not path.exists():
        return True
    prev = GENESIS
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            return False
        if rec.get("prev_hash") != prev or rec.get("hash") != _hash(rec):
            return False
        prev = rec["hash"]
    return True
