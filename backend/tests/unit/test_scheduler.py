from whaleproof.scheduler.runner import build_scheduler


def test_jobs_registered_in_new_york_time():
    s = build_scheduler(run=lambda *a: None)
    jobs = {j.id: j for j in s.get_jobs()}
    assert set(jobs) == {"official_scan", "confirm", "intraday", "track", "backfill", "catch_up_scan",
                         "marks_early", "marks_open", "marks_close"}
    trig = str(jobs["official_scan"].trigger)
    assert "hour='16'" in trig and "minute='30'" in trig and "day_of_week='mon-fri'" in trig
    assert str(jobs["official_scan"].trigger.timezone) == "America/New_York"


def test_catch_up_scan_at_2010_runs_scan_with_flag():
    calls = []
    s = build_scheduler(run=lambda *a: calls.append(a), commit=lambda label: calls.append(("commit", label)))
    job = {j.id: j for j in s.get_jobs()}["catch_up_scan"]
    t = str(job.trigger)
    assert "hour='20'" in t and "minute='10'" in t and "day_of_week='mon-fri'" in t
    import whaleproof.scheduler.runner as r
    orig = r.mc.is_session
    r.mc.is_session = lambda d: True
    try:
        job.func()
    finally:
        r.mc.is_session = orig
    assert calls == [("scan", "--catch-up"), ("marks", "--at", "scan"), ("commit", "picks (catch-up)")]


def test_live_option_marks_at_0935_0945_and_1555():
    calls = []
    s = build_scheduler(run=lambda *a: calls.append(a), commit=lambda label: calls.append(("commit", label)))
    jobs = {j.id: j for j in s.get_jobs()}
    assert "hour='9'" in str(jobs["marks_early"].trigger) and "minute='35'" in str(jobs["marks_early"].trigger)
    assert "hour='9'" in str(jobs["marks_open"].trigger) and "minute='45'" in str(jobs["marks_open"].trigger)
    assert "hour='15'" in str(jobs["marks_close"].trigger) and "minute='55'" in str(jobs["marks_close"].trigger)
    import whaleproof.scheduler.runner as r
    orig = r.mc.is_session
    r.mc.is_session = lambda d: True
    try:
        jobs["marks_early"].func()
        jobs["marks_open"].func()
        jobs["marks_close"].func()
    finally:
        r.mc.is_session = orig
    assert calls == [("marks", "--at", "early"), ("marks", "--at", "open"), ("commit", "after-open check"),
                     ("marks", "--at", "close")]


def test_official_scan_then_closing_option_prices():
    calls = []
    s = build_scheduler(run=lambda *a: calls.append(a), commit=lambda label: calls.append(("commit", label)))
    job = {j.id: j for j in s.get_jobs()}["official_scan"]
    import whaleproof.scheduler.runner as r
    orig = r.mc.is_session
    r.mc.is_session = lambda d: True
    try:
        job.func()
    finally:
        r.mc.is_session = orig
    assert calls == [("scan",), ("marks", "--at", "scan"), ("commit", "picks")]
