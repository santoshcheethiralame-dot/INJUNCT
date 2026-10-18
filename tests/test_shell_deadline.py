"""A subprocess that never exits must not stop the run.

The seeded repositories ship a web server, and a live agent may well decide
that running it is how you verify your work. With no timeout the benchmark
wedged mid-arm, silently, and looked like slowness.
"""
import sys

from injunct import shell


def test_a_command_that_never_returns_is_killed(tmp_path):
    script = tmp_path / "forever.py"
    script.write_text("import time\nwhile True: time.sleep(1)\n", encoding="utf-8")
    r = shell.run(f'"{sys.executable}" forever.py', tmp_path, timeout=3)
    assert r.returncode == 124
    assert "killed" in r.stderr


def test_a_normal_command_is_unaffected(tmp_path):
    r = shell.run(f'"{sys.executable}" -c "print(7)"', tmp_path)
    assert r.returncode == 0
    assert r.stdout.strip() == "7"


def test_there_is_always_a_deadline(tmp_path):
    """The default must never be None again."""
    assert shell._capped(None) == shell.DEADLINE
    assert shell._capped(5) == 5
