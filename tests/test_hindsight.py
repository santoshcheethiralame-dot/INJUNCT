"""Hindsight: the rules, replayed against the commits that later needed a fix."""
import subprocess
from types import SimpleNamespace
from pathlib import Path

import pytest

from injunct import hindsight
from injunct.db import Ledger, ledger_path


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def _commit(repo, files: dict, msg: str):
    for path, text in files.items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)
    return _git(repo, "rev-parse", "HEAD").strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "app"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    _commit(r, {"app/a.py": "def a():\n    return 1\n"}, "start")
    bad = _commit(r, {"app/a.py": "def a():\n    print('dbg')\n    return 1\n"}, "quick debug for the bug")
    _commit(r, {"app/b.py": "def b():\n    return 2\n"}, "add b")
    fix = _commit(r, {"app/a.py": "def a():\n    return 1\n"}, "Fix stray print in a")
    reverted = _commit(r, {"app/c.py": "x = 1\n"}, "add c")
    _git(r, "revert", "--no-edit", "HEAD")
    led = Ledger(ledger_path(r))
    run = led.open_run(str(r.resolve()), "t", arm="t")
    case = led.file_case(run, str(r.resolve()), "t", "high", "no print", [], "{}")
    led.establish(case, str(r.resolve()), "must_not_appear", {"regex": r"print\(", "glob": "app/**"},
                  "No print in app/.", status="persuasive")
    led.close()
    return SimpleNamespace(path=r, bad=bad, fix=fix, reverted=reverted)


def test_a_bug_word_alone_is_not_a_fix():
    assert not hindsight.FIX.search("quick debug for the bug")
    assert hindsight.FIX.search("Fix stray print") and hindsight.FIX.search("Add missing migration")


def test_szz_traces_a_fix_to_the_commit_that_broke_it(repo):
    assert hindsight.introducers(repo.path, repo.fix, "", set()) == {repo.bad}


def test_a_revert_names_its_target(repo):
    head = _git(repo.path, "rev-parse", "HEAD").strip()
    body = _git(repo.path, "log", "-1", "--format=%b")
    assert hindsight.introducers(repo.path, head, body, set()) == {repo.reverted}


def test_a_shallow_boundary_is_never_blamed(repo):
    assert hindsight.introducers(repo.path, repo.fix, "", {repo.bad}) == set()


def test_the_rule_catches_the_bad_commit_and_the_baseline_is_reported(repo):
    s = hindsight.run(repo.path)
    assert s["caught"] == 1 and s["introducers"] >= 1
    assert repo.bad[:7] in s["catches"][0]["introduced"]
    assert repo.fix[:7] in s["catches"][0]["fixed_by"]
    assert s["clean"] >= 2 and s["clean_fired"] == 0       # the rule is not firing on everything


def test_the_demo_catches_every_planted_bug_with_a_binding_rule(monkeypatch):
    import tempfile
    from injunct import coverage, coverdemo, verbs
    monkeypatch.setattr(coverage, "CACHE", coverdemo.CACHE)
    monkeypatch.setattr(coverage.provider, "MODEL", coverdemo.MODEL)
    repo = coverdemo.build(Path(tempfile.mkdtemp()) / "clinic")
    verbs.install_pack(repo)
    coverage.run(repo, adopt=True)
    s = hindsight.run(repo)
    assert (s["caught"], s["introducers"], s["caught_binding"]) == (3, 3, 3)
    assert s["clean_fired"] < s["clean"]               # the rules are not firing on everything


def test_a_rule_that_fired_on_a_bug_it_did_not_cause_is_not_a_catch(tmp_path):
    r = tmp_path / "app"
    r.mkdir()
    _git(r, "init", "-q"); _git(r, "config", "user.email", "t@t"); _git(r, "config", "user.name", "t")
    _commit(r, {"app/a.py": "def a():\n    return 1\n"}, "start")
    # The bad commit adds a print (the rule fires) AND an off-by-one (the real bug).
    _commit(r, {"app/a.py": "def a():\n    print('hi')\n    return 2\n"}, "change a")
    # The fix repairs the off-by-one and leaves the print alone.
    _commit(r, {"app/a.py": "def a():\n    print('hi')\n    return 1\n"}, "Fix the return value of a")
    led = Ledger(ledger_path(r))
    run = led.open_run(str(r.resolve()), "t", arm="t")
    case = led.file_case(run, str(r.resolve()), "t", "high", "no print", [], "{}")
    led.establish(case, str(r.resolve()), "must_not_appear", {"regex": r"print\(", "glob": "app/**"},
                  "No print in app/.", status="binding")
    led.close()
    s = hindsight.run(r)
    assert s["introducers"] == 1 and s["caught"] == 0 and s["unrelated"] == 1
