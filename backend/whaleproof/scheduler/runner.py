from __future__ import annotations

import subprocess
from datetime import date, datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from whaleproof import market_calendar as mc
from whaleproof.config import REPO_ROOT

TZ = "America/New_York"
BACKFILL_START = date(2024, 10, 1)


def subprocess_runner(*args: str) -> None:
    subprocess.run(["uv", "run", "whaleproof", *args], cwd=REPO_ROOT / "backend", check=False)


def commit_journal(label: str) -> None:
    """Commit derived journal files locally. Never pushes: publishing is the owner's manual step (owner 10-04)."""
    subprocess.run(["git", "add", "journal"], cwd=REPO_ROOT, check=False)
    subprocess.run(["git", "commit", "-m", f"{label}: {datetime.now(mc.NY).date().isoformat()}"],
                   cwd=REPO_ROOT, check=False)


def build_scheduler(run=subprocess_runner, commit=commit_journal) -> BlockingScheduler:
    s = BlockingScheduler(timezone=TZ)

    def today() -> date:
        return datetime.now(mc.NY).date()

    def official():
        if mc.is_session(today()):
            run("scan")
            run("marks", "--at", "scan")        # tomorrow's picks: real closing price of the option we'd buy
            commit("picks")

    def catch_up():
        # after the 20:00 budget reset: redo the official scan only if 16:30 failed (still valid before next open)
        if mc.is_session(today()):
            run("scan", "--catch-up")
            run("marks", "--at", "scan")        # the command only prices picks not yet entered
            commit("picks (catch-up)")

    def intraday():
        run("intraday")  # command enforces the 09:45–15:30 ET session window

    def confirm():
        if mc.is_session(today()):
            run("confirm")
            run("health")
            commit("confirm")

    def track():
        if mc.is_session(today()):
            run("track")
            run("health")
            commit("scorecard")

    def marks_early():
        if mc.is_session(today()):
            run("marks", "--at", "early")      # 09:35: closest to the tested open price (opening spread)

    def marks_open():
        # 09:45: real option prices once spreads settle + the after-open "still worth buying?" decision (journaled)
        if mc.is_session(today()):
            run("marks", "--at", "open")
            commit("after-open check")

    def marks_close():
        if mc.is_session(today()):
            run("marks", "--at", "close")      # daily mark; the cut-off day's close = real exit (DB only)

    def backfill():
        run("backfill", "--start", BACKFILL_START.isoformat(), "--end", mc.previous_session(today()).isoformat())

    s.add_job(official, CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone=TZ), id="official_scan",
              misfire_grace_time=6 * 3600, coalesce=True)  # scan's own guard stops post-open picks
    s.add_job(catch_up, CronTrigger(day_of_week="mon-fri", hour=20, minute=10, timezone=TZ), id="catch_up_scan",
              misfire_grace_time=3600, coalesce=True)
    s.add_job(confirm, CronTrigger(day_of_week="mon-fri", hour=8, minute=30, timezone=TZ), id="confirm",
              misfire_grace_time=45 * 60, coalesce=True)  # command refuses after 09:30 anyway
    s.add_job(intraday, CronTrigger(day_of_week="mon-fri", hour="9-15", minute="0,15,30,45", timezone=TZ),
              id="intraday", misfire_grace_time=300, coalesce=True, max_instances=1)
    s.add_job(track, CronTrigger(day_of_week="mon-fri", hour=17, minute=0, timezone=TZ), id="track")
    s.add_job(marks_early, CronTrigger(day_of_week="mon-fri", hour=9, minute=35, timezone=TZ), id="marks_early",
              misfire_grace_time=5 * 60, coalesce=True)
    s.add_job(marks_open, CronTrigger(day_of_week="mon-fri", hour=9, minute=45, timezone=TZ), id="marks_open",
              misfire_grace_time=30 * 60, coalesce=True)
    s.add_job(marks_close, CronTrigger(day_of_week="mon-fri", hour=15, minute=55, timezone=TZ), id="marks_close",
              misfire_grace_time=4 * 60, coalesce=True)          # must run before the 16:00 close
    # hourly slices; the backfill command itself stops before touching what live jobs still need
    s.add_job(backfill, CronTrigger(minute=5, timezone=TZ), id="backfill", max_instances=1, coalesce=True)
    return s
