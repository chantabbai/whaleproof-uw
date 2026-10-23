from whaleproof.scheduler.runner import build_scheduler


def main(argv: list[str]) -> int:
    print("WhaleProof scheduler running (Ctrl+C to stop): confirm 08:30, scan 16:30, track 17:00, backfill 20:05 ET",
          flush=True)
    build_scheduler().start()
    return 0
