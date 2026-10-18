"""The mistakes every agent makes. These are the rules a person recognises
before they have read anything about the tool."""
import subprocess
from pathlib import Path

import pytest

from injunct import gate, packs, verbs
from injunct.change import Change
from injunct.db import Ledger, ledger_path
from injunct.templates import _hits


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    (r / "tests").mkdir(parents=True)
    (r / "app.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (r / "tests" / "test_app.py").write_text(
        "def test_add():\n    assert add(1, 2) == 3\n\n"
        "def test_more():\n    assert add(0, 0) == 0\n", encoding="utf-8")
    for c in (["git", "init", "-q"], ["git", "add", "-A"],
              ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "s"]):
        subprocess.run(c, cwd=r, capture_output=True)
    verbs.install_pack(r)
    return r


def fires(repo, status="binding"):
    led = Ledger(ledger_path(repo))
    ch = Change.from_git(repo)
    out = (gate.evaluate(led, str(repo.resolve()), ch) if status == "binding"
           else gate.firing_advice(led, str(repo.resolve()), ch))
    led.close()
    return [v.says for v in out]


# ---- glob handling, which silently broke two of these ---------------------

def test_a_root_level_file_is_matched_by_a_recursive_glob():
    """`**/*.py` skipping app.py is how a rule quietly protects nothing."""
    assert _hits(["app.py"], "**/*.py") == ["app.py"]
    assert _hits(["src/app.py"], "**/*.py") == ["src/app.py"]


def test_braces_expand():
    """fnmatch has no brace expansion, so `*.{js,ts}` matched literally nothing."""
    assert _hits(["web/a.tsx"], "**/*.{js,ts,jsx,tsx}") == ["web/a.tsx"]
    assert _hits(["tests/t.py"], "**/{test,tests}/**") == ["tests/t.py"]
    assert _hits(["README.md"], "**/*.{js,ts}") == []


# ---- the mistakes themselves ---------------------------------------------

def test_a_committed_token_is_blocked(repo):
    (repo / "app.py").write_text('KEY = "sk-abcdefghijklmnopqrstuvwxyz012345"\n', encoding="utf-8")
    assert any("API token" in s for s in fires(repo))


def test_a_left_behind_breakpoint_is_blocked(repo):
    (repo / "app.py").write_text("import pdb; pdb.set_trace()\n", encoding="utf-8")
    assert any("breakpoint" in s for s in fires(repo))


def test_deleting_a_test_is_advisory_not_a_block(repo):
    f = repo / "tests" / "test_app.py"
    f.write_text(f.read_text(encoding="utf-8").split("def test_more")[0], encoding="utf-8")
    assert fires(repo, "binding") == [], "a real refactor deletes tests; do not block"
    assert any("deleted a test" in s for s in fires(repo, "persuasive"))


def test_skipping_a_test_is_advisory(repo):
    f = repo / "tests" / "test_app.py"
    f.write_text("@pytest.mark.skip\n" + f.read_text(encoding="utf-8"), encoding="utf-8")
    assert any("skipped a test" in s for s in fires(repo, "persuasive"))


def test_a_clean_change_trips_nothing(repo):
    (repo / "app.py").write_text("def add(a, b):\n    return a + b\n\n"
                                 "def sub(a, b):\n    return a - b\n", encoding="utf-8")
    assert fires(repo, "binding") == []
    assert fires(repo, "persuasive") == []


def test_only_rules_the_repo_can_trip_are_installed(tmp_path):
    py = tmp_path / "py"
    (py / "s").mkdir(parents=True)
    (py / "s" / "a.py").write_text("x = 1\n", encoding="utf-8")
    keys = {r["key"] for r in packs.applicable(py)}
    assert "pdb" in keys and "debugger" not in keys, "no JS rules in a Python repo"


def test_a_lockfile_pair_is_only_installed_when_both_exist(tmp_path):
    assert packs.manifest_pairs(tmp_path) == []
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    pairs = packs.manifest_pairs(tmp_path)
    assert pairs and pairs[0]["trigger"] == "package.json"
