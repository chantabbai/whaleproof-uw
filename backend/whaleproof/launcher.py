"""Cross-platform desk launcher behind `whaleproof desk quickstart|up|down|status` (and `scripts/desk.sh`).

Acts ONLY on this project's ports (8100 API, 3100 UI). Children are detached (own session / process group, stdout to
a log file, stdin from devnull) so they outlive the launcher and never hold its stdout. A pid from a pid file is
killed only when it (or its process tree) owns our listening port; stale pids may belong to unrelated processes.
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from whaleproof.config import REPO_ROOT

API_PORT, UI_PORT = 8100, 3100
# Windows process-creation flags (literals: the subprocess constants exist only on Windows builds of Python)
CREATE_NEW_PROCESS_GROUP = 0x00000200
DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def _windows() -> bool:
    return os.name == "nt"


def safe_console() -> None:
    """Never crash printing '→' on a cp1252 Windows console/pipe."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass


def _child_env() -> dict[str, str]:
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


# --- ports ----------------------------------------------------------------------------------------------------------

def is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def parse_netstat(text: str, port: int) -> list[int]:
    """Listening pids for `port` from `netstat -ano -p TCP` (state names are localized: also accept foreign 0.0.0.0:0)."""
    locals_ = {f"127.0.0.1:{port}", f"0.0.0.0:{port}"}
    out: list[int] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0].upper() != "TCP" or parts[1] not in locals_:
            continue
        if parts[3].upper() != "LISTENING" and parts[2] != "0.0.0.0:0":
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid and pid not in out:
            out.append(pid)
    return out


def listening_pids(port: int) -> list[int]:
    try:
        if _windows():
            exe = shutil.which("netstat")
            if not exe:
                return []
            r = subprocess.run([exe, "-ano", "-p", "TCP"], capture_output=True, text=True, errors="replace")
            return parse_netstat(r.stdout or "", port)
        exe = shutil.which("lsof")
        if not exe:
            return []
        r = subprocess.run([exe, "-ti", f"tcp:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
        return [int(x) for x in (r.stdout or "").split() if x.isdigit()]
    except OSError:
        return []


def parse_parent_map(text: str) -> dict[int, tuple[int, int]]:
    """'pid ppid created_ticks' lines → {pid: (ppid, created_ticks)}; ticks 0 = unknown."""
    out: dict[int, tuple[int, int]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            out[int(parts[0])] = (int(parts[1]), int(parts[2]))
    return out


def _parent_map() -> dict[int, tuple[int, int]]:
    """Windows pid → (parent pid, creation ticks) via PowerShell CIM (no psutil). Empty on failure (→ not owned)."""
    exe = shutil.which("powershell") or shutil.which("pwsh")
    if not exe:
        return {}
    cmd = ('Get-CimInstance Win32_Process | ForEach-Object { $t = if ($_.CreationDate) '
           '{ $_.CreationDate.ToUniversalTime().Ticks } else { 0 }; "$($_.ProcessId) $($_.ParentProcessId) $t" }')
    try:
        r = subprocess.run([exe, "-NoProfile", "-Command", cmd], capture_output=True, text=True, errors="replace",
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return {}
    return parse_parent_map(r.stdout or "")


def _pgid(pid: int) -> int | None:
    try:
        return os.getpgid(pid)
    except (OSError, AttributeError):
        return None


def owns_port(pid: int, port: int) -> bool:
    """True only if `pid` is a listener on `port` or an ancestor (Windows) / process-group leader (Unix) of one."""
    listeners = listening_pids(port)
    if pid in listeners:
        return True
    if not _windows():
        return any(_pgid(lp) == pid for lp in listeners)
    # Windows never reparents orphans: a dead parent's pid can be reused, so follow a link only to a parent created
    # no later than its child (else it's an impostor) and stop after a few hops (cmd → npm → next → next-server).
    procs = _parent_map()
    for lp in listeners:
        cur = lp
        for _ in range(6):
            if cur not in procs:
                break
            ppid, born = procs[cur]
            if ppid not in procs:
                break
            p_born = procs[ppid][1]
            if not born or not p_born or p_born > born:
                break
            if ppid == pid:
                return True
            cur = ppid
    return False


# --- processes ------------------------------------------------------------------------------------------------------

def spawn(cmd: list[str], cwd: Path, log: Path) -> int:
    """Start a detached child writing to `log`; returns its pid."""
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "wb") as fh:
        kw = dict(cwd=cwd, stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, env=_child_env())
        if not _windows():
            return subprocess.Popen(cmd, start_new_session=True, **kw).pid
        flags = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        try:   # leave uv's job object so the desk outlives `uv run`
            return subprocess.Popen(cmd, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **kw).pid
        except OSError:   # job forbids breakaway
            print("note: could not detach from this console's job; the desk may stop when this command exits",
                  file=sys.stderr, flush=True)
            return subprocess.Popen(cmd, creationflags=flags, **kw).pid


def kill_tree(pid: int, force: bool = False) -> None:
    try:
        if _windows():   # always /F: a console-less child ignores a plain taskkill
            subprocess.run([shutil.which("taskkill") or "taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True)
        else:
            os.killpg(pid, getattr(signal, "SIGKILL", signal.SIGTERM) if force else signal.SIGTERM)
    except ProcessLookupError:   # pid leads no group (reused by the listener itself)
        kill_pid(pid, force)
    except OSError:
        pass


def kill_pid(pid: int, force: bool = False) -> None:
    if _windows():
        kill_tree(pid, force)
        return
    try:
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM) if force else signal.SIGTERM)
    except OSError:
        pass


def wait_http(url: str, tries: int = 60) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # never route 127.0.0.1 via a proxy
    for _ in range(tries):
        try:
            with opener.open(url, timeout=30) as r:
                if r.status < 400:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _pidfile(root: Path, name: str) -> Path:
    return root / "data" / f"desk-{name}.pid"


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


# --- commands -------------------------------------------------------------------------------------------------------

def up(root: Path = REPO_ROOT) -> int:
    data = root / "data"
    data.mkdir(parents=True, exist_ok=True)
    if not (root / ".env").is_file():
        print("note: no .env → cache-only mode (copy .env.example and add UW_API_KEY for live data)", flush=True)
    npm = shutil.which("npm")
    if not (root / "frontend" / "node_modules").is_dir():
        if not npm or subprocess.run([npm, "ci", "--silent"], cwd=root / "frontend").returncode != 0:
            print("frontend setup failed (is npm installed?)")
            return 1
    if not is_listening(API_PORT):
        pid = spawn([sys.executable, "-m", "whaleproof.cli", "serve", "--port", str(API_PORT)], root / "backend",
                    data / "serve.log")
        _pidfile(root, "api").write_text(f"{pid}\n")
    if not is_listening(UI_PORT):
        if not npm:
            print("frontend setup failed (is npm installed?)")
            return 1
        pid = spawn([npm, "run", "dev"], root / "frontend", data / "frontend.log")
        _pidfile(root, "ui").write_text(f"{pid}\n")
    wait_http(f"http://127.0.0.1:{UI_PORT}/")
    print(f"WhaleProof → http://127.0.0.1:{UI_PORT}  (API http://127.0.0.1:{API_PORT})")
    return 0


def _stop_round(root: Path, force: bool) -> None:
    for name, port in (("api", API_PORT), ("ui", UI_PORT)):
        pid = _read_pid(_pidfile(root, name))
        if pid and owns_port(pid, port):
            kill_tree(pid, force)
        else:
            for lp in listening_pids(port):   # no valid pid file (e.g. started by the old desk.sh): port owners
                kill_pid(lp, force)


def _ports_busy() -> bool:
    return bool(listening_pids(API_PORT) or listening_pids(UI_PORT))


def down(root: Path = REPO_ROOT) -> int:
    _stop_round(root, force=False)
    for _ in range(20):   # ≤10 s, so 'down; up' restarts
        if not _ports_busy():
            break
        time.sleep(0.5)
    else:
        _stop_round(root, force=True)
        for _ in range(10):
            if not _ports_busy():
                break
            time.sleep(0.5)
    for name in ("api", "ui"):
        _pidfile(root, name).unlink(missing_ok=True)
    print("stopped")
    return 0


def status() -> int:
    for port in (API_PORT, UI_PORT):
        print(f"port {port}: " + "".join(f"{p} " for p in listening_pids(port)))
    return 0


def quickstart(args: list[str], root: Path = REPO_ROOT) -> int:
    r = subprocess.run([sys.executable, "-m", "whaleproof.cli", "quickstart", *args], cwd=root / "backend",
                       env=_child_env())
    if r.returncode != 0:
        return 1
    if "-h" in args or "--help" in args:
        return 0
    return up(root)
