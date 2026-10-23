"""Cross-platform desk launcher (`whaleproof desk up|down|status|quickstart`): no real processes, sockets or kills."""
import signal
import subprocess
import sys

import pytest

from whaleproof import launcher as L

NETSTAT = """
Active Connections

  Proto  Local Address          Foreign Address        State           PID
  TCP    0.0.0.0:135            0.0.0.0:0              LISTENING       1012
  TCP    127.0.0.1:8100         0.0.0.0:0              LISTENING       4242
  TCP    127.0.0.1:8100         127.0.0.1:51000        ESTABLISHED     4242
  TCP    127.0.0.1:51000        127.0.0.1:8100         ESTABLISHED     7777
  TCP    127.0.0.1:81000        0.0.0.0:0              LISTENING       9999
  TCP    0.0.0.0:3100           0.0.0.0:0              ABHÖREN         5151
  TCP    127.0.0.1:3100         0.0.0.0:0              LISTENING       5151
  TCP    127.0.0.1:3100         0.0.0.0:0              LISTENING       0
"""


@pytest.fixture
def root(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def fake(monkeypatch):
    """Records spawns/kills/runs; `listening` = ports with something on them, `owners` = port → listener pids."""
    st = type("S", (), {})()
    st.listening, st.owners, st.spawned, st.killed, st.runs, st.pgids = set(), {}, [], [], [], {}
    st.windows = False
    monkeypatch.setattr(L, "_windows", lambda: st.windows)
    monkeypatch.setattr(L, "is_listening", lambda port: port in st.listening)
    monkeypatch.setattr(L, "listening_pids", lambda port: list(st.owners.get(port, [])))
    monkeypatch.setattr(L, "wait_http", lambda url, tries=60: True)
    monkeypatch.setattr(L.time, "sleep", lambda s: None)
    monkeypatch.setattr(L.shutil, "which", lambda name: f"/bin/{name}")

    def spawn(cmd, cwd, log):
        st.spawned.append((cmd, cwd, log))
        return 100 + len(st.spawned)
    monkeypatch.setattr(L, "spawn", spawn)

    def kill_tree(pid, force=False):
        st.killed.append(("tree", pid))
        for port, pids in list(st.owners.items()):
            if pid in pids or any(st.pgids.get(p) == pid for p in pids):
                st.owners.pop(port)
                st.listening.discard(port)
    monkeypatch.setattr(L, "kill_tree", kill_tree)

    def kill_pid(pid, force=False):
        st.killed.append(("pid", pid))
        for port, pids in list(st.owners.items()):
            if pid in pids:
                st.owners.pop(port)
                st.listening.discard(port)
    monkeypatch.setattr(L, "kill_pid", kill_pid)
    monkeypatch.setattr(L, "_pgid", lambda pid: st.pgids.get(pid, pid))

    def run(cmd, cwd=None, **kw):
        st.runs.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(L.subprocess, "run", run)
    return st


# --- up -------------------------------------------------------------------------------------------------------------

def test_up_starts_api_and_ui_when_ports_free(root, fake, capsys):
    (root / ".env").write_text("X=1\n")
    assert L.up(root) == 0
    (api, api_cwd, api_log), (ui, ui_cwd, ui_log) = fake.spawned
    assert api == [sys.executable, "-m", "whaleproof.cli", "serve", "--port", "8100"] and api_cwd == root / "backend"
    assert ui == ["/bin/npm", "run", "dev"] and ui_cwd == root / "frontend"
    assert api_log == root / "data" / "serve.log" and ui_log == root / "data" / "frontend.log"
    assert (root / "data" / "desk-api.pid").read_text().strip() == "101"
    assert (root / "data" / "desk-ui.pid").read_text().strip() == "102"
    out = capsys.readouterr().out
    assert "note: no .env" not in out
    assert out.strip().endswith("WhaleProof → http://127.0.0.1:3100  (API http://127.0.0.1:8100)")


def test_up_skips_ports_already_listening(root, fake):
    fake.listening = {8100, 3100}
    assert L.up(root) == 0
    assert fake.spawned == []


def test_up_without_env_prints_cache_only_note(root, fake, capsys):
    L.up(root)
    first = capsys.readouterr().out.splitlines()[0]
    assert first == "note: no .env → cache-only mode (copy .env.example and add UW_API_KEY for live data)"


def test_up_runs_npm_ci_only_when_node_modules_missing(root, fake):
    L.up(root)
    assert not any("ci" in cmd for cmd, _ in fake.runs)
    (root / "frontend" / "node_modules").rmdir()
    fake.spawned.clear()
    L.up(root)
    assert (["/bin/npm", "ci", "--silent"], root / "frontend") in fake.runs


def test_up_fails_when_npm_missing(root, fake, monkeypatch, capsys):
    monkeypatch.setattr(L.shutil, "which", lambda name: None)
    (root / "frontend" / "node_modules").rmdir()
    assert L.up(root) == 1
    assert "frontend setup failed (is npm installed?)" in capsys.readouterr().out
    assert fake.spawned == []


def test_up_fails_when_npm_ci_fails(root, fake, monkeypatch, capsys):
    (root / "frontend" / "node_modules").rmdir()
    monkeypatch.setattr(L.subprocess, "run", lambda cmd, cwd=None, **kw: subprocess.CompletedProcess(cmd, 1))
    assert L.up(root) == 1
    assert "frontend setup failed (is npm installed?)" in capsys.readouterr().out


def test_up_prints_url_even_if_ui_never_answers(root, fake, monkeypatch, capsys):
    monkeypatch.setattr(L, "wait_http", lambda url, tries=60: False)
    assert L.up(root) == 0
    assert "WhaleProof → http://127.0.0.1:3100" in capsys.readouterr().out


# --- spawn contract (the agent-hang fix: children never hold the parent's stdout) -----------------------------------

class FakePopen:
    calls = []

    def __init__(self, cmd, **kw):
        FakePopen.calls.append((cmd, kw))
        self.pid = 4321


def _spawn_kwargs(monkeypatch, tmp_path, windows):
    FakePopen.calls = []
    monkeypatch.setattr(L, "_windows", lambda: windows)
    monkeypatch.setattr(L.subprocess, "Popen", FakePopen)
    assert L.spawn(["x"], tmp_path, tmp_path / "data" / "x.log") == 4321
    return FakePopen.calls[-1][1]


def test_spawn_posix_detaches_into_own_session_with_log_file(monkeypatch, tmp_path):
    kw = _spawn_kwargs(monkeypatch, tmp_path, windows=False)
    assert kw["stdin"] is subprocess.DEVNULL and kw["stderr"] is subprocess.STDOUT
    assert hasattr(kw["stdout"], "fileno") and kw["stdout"].closed   # real file, closed in the parent after Popen
    assert kw["start_new_session"] is True and "creationflags" not in kw
    assert kw["env"]["PYTHONUTF8"] == "1" and kw["env"]["PYTHONIOENCODING"] == "utf-8"
    assert kw["cwd"] == tmp_path


def test_spawn_windows_uses_creationflags_not_sessions(monkeypatch, tmp_path):
    kw = _spawn_kwargs(monkeypatch, tmp_path, windows=True)
    assert "start_new_session" not in kw
    flags = kw["creationflags"]
    assert flags & L.CREATE_NEW_PROCESS_GROUP and flags & L.CREATE_NO_WINDOW and flags & L.CREATE_BREAKAWAY_FROM_JOB
    assert not flags & L.DETACHED_PROCESS   # would pop a console window for node under npm.cmd


def test_spawn_windows_retries_without_breakaway_when_job_forbids_it(monkeypatch, tmp_path, capsys):
    seen = []

    class Picky(FakePopen):
        def __init__(self, cmd, **kw):
            seen.append(kw["creationflags"])
            if kw["creationflags"] & L.CREATE_BREAKAWAY_FROM_JOB:
                raise PermissionError("access denied")
            self.pid = 99
    monkeypatch.setattr(L, "_windows", lambda: True)
    monkeypatch.setattr(L.subprocess, "Popen", Picky)
    assert L.spawn(["x"], tmp_path, tmp_path / "x.log") == 99
    assert len(seen) == 2 and not seen[1] & L.CREATE_BREAKAWAY_FROM_JOB
    assert "may stop when this command exits" in capsys.readouterr().err   # never a silent dead desk


def test_windows_flag_values():
    assert (L.CREATE_NEW_PROCESS_GROUP, L.DETACHED_PROCESS, L.CREATE_NO_WINDOW, L.CREATE_BREAKAWAY_FROM_JOB) == \
        (0x200, 0x8, 0x08000000, 0x01000000)


# --- down (safety: only kill a pid-file pid that owns the port) -----------------------------------------------------

def test_down_kills_pid_file_tree_when_it_owns_the_port(root, fake, capsys):
    (root / "data").mkdir()
    (root / "data" / "desk-api.pid").write_text("500\n")
    (root / "data" / "desk-ui.pid").write_text("600\n")
    fake.listening, fake.owners, fake.pgids = {8100, 3100}, {8100: [500], 3100: [601]}, {601: 600}
    assert L.down(root) == 0
    assert fake.killed == [("tree", 500), ("tree", 600)]
    assert not (root / "data" / "desk-api.pid").exists() and not (root / "data" / "desk-ui.pid").exists()
    assert capsys.readouterr().out.strip() == "stopped"


def test_down_never_kills_stale_pid_file_pid(root, fake):
    (root / "data").mkdir()
    (root / "data" / "desk-api.pid").write_text("500\n")   # 500 reused by some unrelated process
    fake.listening, fake.owners = {8100}, {8100: [777]}  # desk API started some other way
    L.down(root)
    assert ("tree", 500) not in fake.killed and ("pid", 500) not in fake.killed
    assert ("pid", 777) in fake.killed                    # fallback: whatever listens on our port (old desk.sh rule)
    assert not (root / "data" / "desk-api.pid").exists()


def test_down_with_nothing_running_kills_nothing(root, fake, capsys):
    (root / "data").mkdir()
    (root / "data" / "desk-ui.pid").write_text("600\n")
    assert L.down(root) == 0
    assert fake.killed == []
    assert capsys.readouterr().out.strip() == "stopped"


def test_down_escalates_when_port_stays_busy(root, fake, monkeypatch):
    fake.listening, fake.owners = {8100}, {8100: [777]}
    forced = []
    monkeypatch.setattr(L, "kill_pid", lambda pid, force=False: forced.append((pid, force)))
    L.down(root)
    assert (777, False) in forced and (777, True) in forced


def test_owns_port_unix_by_pid_or_process_group(fake):
    fake.owners, fake.pgids = {3100: [601]}, {601: 600}
    assert L.owns_port(600, 3100) and L.owns_port(601, 3100)
    assert not L.owns_port(602, 3100) and not L.owns_port(600, 8100)


def test_owns_port_windows_walks_parent_chain(fake, monkeypatch):
    fake.windows = True
    fake.owners = {8100: [30]}
    procs = {30: (20, 300), 20: (10, 200), 10: (4, 100), 4: (0, 50)}   # real python ← venv launcher ← pid file
    monkeypatch.setattr(L, "_parent_map", lambda: procs)
    assert L.owns_port(10, 8100) and L.owns_port(20, 8100) and L.owns_port(30, 8100)
    assert not L.owns_port(4242, 8100)
    monkeypatch.setattr(L, "_parent_map", lambda: {})                      # PowerShell missing → fail safe
    assert not L.owns_port(10, 8100) and L.owns_port(30, 8100)


def test_owns_port_windows_stops_at_reused_parent_pid(fake, monkeypatch):
    fake.windows = True
    fake.owners = {8100: [30]}
    # 20 died and its pid was reused by a younger, unrelated process whose parent is 10 (a stale pid file's pid)
    monkeypatch.setattr(L, "_parent_map", lambda: {30: (20, 300), 20: (10, 900), 10: (4, 100)})
    assert not L.owns_port(20, 8100) and not L.owns_port(10, 8100)
    monkeypatch.setattr(L, "_parent_map", lambda: {30: (20, 300), 20: (10, 0), 10: (4, 100)})   # unknown age
    assert not L.owns_port(10, 8100)


def test_owns_port_windows_caps_walk_depth(fake, monkeypatch):
    fake.windows = True
    fake.owners = {8100: [100]}
    monkeypatch.setattr(L, "_parent_map", lambda: {100 - i: (99 - i, 1000 - i) for i in range(20)})
    assert L.owns_port(99, 8100) and not L.owns_port(85, 8100)


def test_parse_netstat_listening_pids_for_exact_port():
    assert L.parse_netstat(NETSTAT, 8100) == [4242]
    assert L.parse_netstat(NETSTAT, 3100) == [5151]           # localized state still found via 0.0.0.0:0, pid 0 dropped
    assert L.parse_netstat(NETSTAT, 810) == [] and L.parse_netstat(NETSTAT, 51000) == []
    assert L.parse_netstat("", 8100) == []


def test_parse_parent_map():
    assert L.parse_parent_map("10 4 100\r\n20 10 200\nbad line x\n10 4\n\n30 20 0\n") == \
        {10: (4, 100), 20: (10, 200), 30: (20, 0)}


def test_listening_pids_unix_uses_lsof(monkeypatch):
    monkeypatch.setattr(L, "_windows", lambda: False)
    monkeypatch.setattr(L.shutil, "which", lambda name: "/usr/sbin/lsof" if name == "lsof" else None)
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="123\n456\n")
    monkeypatch.setattr(L.subprocess, "run", run)
    assert L.listening_pids(8100) == [123, 456]
    assert seen == [["/usr/sbin/lsof", "-ti", "tcp:8100", "-sTCP:LISTEN"]]
    monkeypatch.setattr(L.shutil, "which", lambda name: None)
    assert L.listening_pids(8100) == []


def test_listening_pids_windows_uses_netstat(monkeypatch):
    monkeypatch.setattr(L, "_windows", lambda: True)
    monkeypatch.setattr(L.shutil, "which", lambda name: "C:/netstat.exe" if name == "netstat" else None)
    monkeypatch.setattr(L.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout=NETSTAT))
    assert L.listening_pids(8100) == [4242]


def test_kill_tree_unix_signals_process_group(monkeypatch):
    monkeypatch.setattr(L, "_windows", lambda: False)
    sent = []
    monkeypatch.setattr(L.os, "killpg", lambda pgid, sig: sent.append((pgid, sig)), raising=False)
    L.kill_tree(500)
    L.kill_tree(500, force=True)
    assert sent == [(500, signal.SIGTERM), (500, getattr(signal, "SIGKILL", signal.SIGTERM))]


def test_kill_tree_unix_signals_pid_when_it_leads_no_group(monkeypatch):
    # stale pid file whose pid was reused by the listener itself (not a group leader): killpg finds no group
    monkeypatch.setattr(L, "_windows", lambda: False)

    def killpg(pgid, sig):
        raise ProcessLookupError

    sent = []
    monkeypatch.setattr(L.os, "killpg", killpg, raising=False)
    monkeypatch.setattr(L.os, "kill", lambda pid, sig: sent.append((pid, sig)))
    L.kill_tree(500)
    assert sent == [(500, signal.SIGTERM)]


def test_kill_tree_windows_uses_taskkill(monkeypatch):
    monkeypatch.setattr(L, "_windows", lambda: True)
    monkeypatch.setattr(L.shutil, "which", lambda name: "taskkill.exe")
    runs = []
    monkeypatch.setattr(L.subprocess, "run", lambda cmd, **kw: runs.append(cmd))
    L.kill_tree(500)
    assert runs == [["taskkill.exe", "/PID", "500", "/T", "/F"]]


# --- status / quickstart --------------------------------------------------------------------------------------------

def test_status_matches_desk_sh_format(fake, capsys):
    fake.owners = {8100: [11, 12]}
    assert L.status() == 0
    assert capsys.readouterr().out == "port 8100: 11 12 \nport 3100: \n"


@pytest.mark.parametrize("code,expect_up,ret", [(0, True, 0), (1, False, 1), (2, False, 1)])
def test_quickstart_runs_then_starts_desk(root, fake, monkeypatch, code, expect_up, ret):
    started = []
    monkeypatch.setattr(L, "up", lambda r=None: started.append(r) or 0)
    monkeypatch.setattr(L.subprocess, "run", lambda cmd, **kw: fake.runs.append((cmd, kw.get("cwd")))
                        or subprocess.CompletedProcess(cmd, code))
    assert L.quickstart(["--sessions", "3"], root) == ret
    assert fake.runs[0] == ([sys.executable, "-m", "whaleproof.cli", "quickstart", "--sessions", "3"], root / "backend")
    assert bool(started) is expect_up


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_quickstart_help_exits_without_starting(root, fake, monkeypatch, flag):
    monkeypatch.setattr(L, "up", lambda r=None: pytest.fail("must not start"))
    assert L.quickstart([flag], root) == 0


def test_desk_command_dispatch(monkeypatch, capsys):
    from whaleproof.commands import desk
    called = []
    monkeypatch.setattr(L, "up", lambda: called.append("up") or 0)
    monkeypatch.setattr(L, "status", lambda: called.append("status") or 0)
    assert desk.main([]) == 0 and desk.main(["status"]) == 0
    assert called == ["up", "status"]
    assert desk.main(["bogus"]) == 2
