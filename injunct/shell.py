"""Every subprocess we launch, launched the same way.

PYTHONDONTWRITEBYTECODE matters more than it looks. A .pyc records the source
mtime to one-second granularity, and these runs write a file and import it
inside the same second - so Python cannot tell the cache is stale and serves
the PREVIOUS version of the module. A failing run then reads the last run's
field list and its oracle passes. Bytecode caching quietly inverts the result.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

ENV = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

# Nothing here may block forever. The seeded repositories contain a web server,
# and a live agent is perfectly entitled to decide that running it is how you
# check your work: `python app.py` never returns, subprocess.run with no
# timeout never returns either, and the benchmark stops dead partway through an
# arm with no error and no output. That is exactly what happened - twice, at
# the same task - and it looks like slowness rather than a hang.
DEADLINE = 60.0


def _capped(timeout: float | None) -> float:
    return DEADLINE if timeout is None else timeout


def _timed_out(cmd: str, timeout: float) -> subprocess.CompletedProcess:
    """A command that outran its deadline is a failed command, not a crash.

    Returning 124 - the code `timeout(1)` uses - keeps every caller's
    `returncode == 0` test meaningful without any of them learning about
    TimeoutExpired.
    """
    return subprocess.CompletedProcess(
        args=cmd, returncode=124, stdout="",
        stderr=f"injunct: no output after {timeout:.0f}s, killed")


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the shell AND everything it started.

    subprocess.run's own timeout kills the direct child, which with shell=True
    is cmd.exe. The python process cmd.exe launched survives, keeps the stdout
    pipe open, and the communicate() that follows the kill blocks forever - so
    a timeout that was supposed to end a hang produced a different hang. Take
    the whole process tree.
    """
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                           capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass


def _launch(cmd: str, cwd, env: dict, timeout: float | None) -> subprocess.CompletedProcess:
    t = _capped(timeout)
    kw = {} if sys.platform == "win32" else {"start_new_session": True}
    proc = subprocess.Popen(cmd, cwd=cwd, shell=True, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace", **kw)
    try:
        out, err = proc.communicate(timeout=t)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        return _timed_out(cmd, t)
    return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


def run(cmd: str, cwd: Path | str, timeout: float | None = None) -> subprocess.CompletedProcess:
    return _launch(cmd, cwd, ENV, timeout)


def run_env(cmd: str, cwd, extra: dict | None = None, timeout: float | None = None):
    """Same launcher, with extra environment - used to select a benchmark arm."""
    return _launch(cmd, cwd, {**ENV, **(extra or {})}, timeout)
