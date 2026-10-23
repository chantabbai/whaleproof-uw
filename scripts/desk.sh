#!/usr/bin/env bash
# WhaleProof one-command run: `scripts/desk.sh quickstart|up|down|status`. Acts ONLY on this project's ports (8100 API, 3100 UI).
# Thin wrapper: the logic lives in `uv run whaleproof desk ...` (backend/whaleproof/launcher.py), which also runs on Windows.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/data"
[ $# -eq 0 ] && set -- up
case "$1" in
  quickstart)   # fresh key + empty cache: fetch the last 5 sessions (no call cap unless --max-calls N; resumable), then start
    (cd "$ROOT/backend" && uv sync -q) || exit 1;;
  up)
    (cd "$ROOT/backend" && uv sync -q) || { echo "backend setup failed (is uv installed?)"; exit 1; };;
  down|status) ;;
  *) exit 0;;
esac
cd "$ROOT/backend" && exec uv run whaleproof desk "$@"
