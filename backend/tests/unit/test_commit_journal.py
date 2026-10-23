"""Scheduler journal commits stay local: never push, even when a remote exists (owner 10-04)."""
from types import SimpleNamespace

from whaleproof.scheduler import runner


def test_commit_journal_never_pushes(monkeypatch):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return SimpleNamespace(stdout="origin\n", returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    runner.commit_journal("scan")
    assert ["git", "add", "journal"] in calls
    assert any(c[:2] == ["git", "commit"] for c in calls)
    assert not any("push" in c for c in calls)
