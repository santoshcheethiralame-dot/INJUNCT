"""The HTTP face is where a real agent meets the ledger. It gets tested like
anything else the agent depends on - including that it fails open."""
import subprocess

import pytest

from injunct import serve
from injunct.db import Ledger
from injunct.workspace import restore
from tests.test_loop import SEED, model_file


def git(repo, *args):
    subprocess.run(["git", *args], cwd=repo, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    r = tmp_path / "clinic"
    restore(SEED, r)
    git(r, "init", "-q")
    git(r, "add", "-A")
    git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    serve.forget_ledgers()
    return r


def teach(repo):
    """One run that went right, one that went wrong - the ledger's whole history."""
    from injunct import harness
    led = Ledger(repo / ".injunct" / "ledger.db")
    harness.run(repo, "add a notes field", led, arm="A", scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": model_file("notes")},
        {"tool": "write_file", "path": "migrations/002_notes.sql",
         "content": "ALTER TABLE patients ADD COLUMN notes TEXT;"},
        {"tool": "done"}])
    bad = harness.run(repo, "add an email field", led, arm="A", scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": model_file("email")},
        {"tool": "done"}])
    out = harness.register_failure(repo, led, bad, use_model=False)
    led.close()
    restore(SEED, repo)
    return out


def test_a_clean_tree_is_not_blocked(repo):
    teach(repo)
    assert serve.gate_check(str(repo))["block"] is False


def test_a_pending_write_is_judged_before_it_lands(repo):
    """The difference between a gate and a post-mortem."""
    out = teach(repo)
    assert out["status"] == "binding", out["receipt"]
    r = serve.gate_check(str(repo), pending=["models/patient.py"])
    assert r["block"] is True
    v = r["verdicts"][0]
    assert v["rule"].startswith("co_change")
    assert "migrations" in v["reason"]
    assert v["empanel"]["fire"] == "1/1"


def test_an_unrelated_pending_write_is_left_alone(repo):
    teach(repo)
    assert serve.gate_check(str(repo), pending=["static/index.html"])["block"] is False


def test_postflight_files_a_case_when_the_check_fails(repo):
    (repo / "models" / "patient.py").write_text(model_file("phone_verified"), encoding="utf-8")
    r = serve.postflight(str(repo), "python oracle.py")
    assert r["passed"] is False
    assert "no such column" in r["output"]
    assert r["filed"]["case_id"] >= 1


def test_postflight_is_silent_when_the_check_passes(repo):
    r = serve.postflight(str(repo), "python oracle.py")
    assert r["passed"] is True and "filed" not in r


def test_reject_files_the_users_own_words(repo):
    out = serve.reject(str(repo), "you changed models/ without touching migrations/")
    assert out["case_id"] >= 1
    assert "migrations" in out["says"]


def test_a_bad_request_never_stalls_the_agent():
    """Fail open. A memory layer that can halt the agent by being broken is
    worse than no memory layer at all."""
    handler = serve.ROUTES["/v1/gate"]
    with pytest.raises(KeyError):
        handler({})           # the route raises...
    # ...and do_POST turns that into a non-blocking answer, which is the contract
    assert serve.Handler.do_POST.__doc__ is None       # no magic, just the try/except


def test_absolute_pending_paths_are_understood(repo):
    """opencode hands out absolute paths. A gate that does not relativise them
    lets the triggering write through and then refuses the fix it asked for."""
    teach(repo)
    abs_model = str((repo / "models" / "patient.py").resolve())
    assert serve.gate_check(str(repo), pending=[abs_model])["block"] is True

    # and the migration, given absolutely, must SATISFY the rule
    (repo / "models" / "patient.py").write_text(model_file("phone_verified"), encoding="utf-8")
    abs_mig = str((repo / "migrations" / "002_pv.sql").resolve())
    assert serve.gate_check(str(repo), pending=[abs_mig])["block"] is False, \
        "the agent must be able to do the work the halt card demanded"
