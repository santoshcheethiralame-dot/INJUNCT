"""A rule learned in one repo travelling to another that has never failed that way."""
from pathlib import Path

import pytest

from injunct import transfer
from injunct.change import Change
from injunct.db import Ledger
from injunct import gate


@pytest.fixture
def gl(tmp_path):
    return Ledger(tmp_path / "global.db")


RULE = ("co_change", {"trigger": "models/*.py", "required": "migrations/**"},
        "Changing models/*.py means changing migrations/ too.")


def test_one_repo_is_a_habit_not_a_pattern(gl, tmp_path):
    t, p, says = RULE
    out = transfer.note(str(tmp_path / "repo_a"), t, p, says, "binding", led=gl)
    assert out == {"scope": "repo", "repos": 1}
    assert transfer.borrowed("anywhere", led=gl) == []


def test_two_repos_make_it_travel(gl, tmp_path):
    t, p, says = RULE
    transfer.note(str(tmp_path / "repo_a"), t, p, says, "binding", led=gl)
    out = transfer.note(str(tmp_path / "repo_b"), t, p, says, "binding", led=gl)
    assert out["scope"] == "global" and out["repos"] == 2
    assert len(transfer.borrowed("anywhere", led=gl)) == 2


def test_borrowed_precedent_fires_in_a_repo_that_never_failed(gl, tmp_path):
    """The point of the whole thing: repo C is gated by what A and B learned."""
    t, p, says = RULE
    transfer.note(str(tmp_path / "repo_a"), t, p, says, "binding", led=gl)
    transfer.note(str(tmp_path / "repo_b"), t, p, says, "binding", led=gl)

    fresh = Ledger(tmp_path / "repo_c" / "ledger.db")
    repo_c = str(tmp_path / "repo_c")
    ch = Change(repo=Path(repo_c), touched=["models/patient.py"])

    assert gate.evaluate(fresh, repo_c, ch) == [], "repo C has learned nothing itself"
    borrowed = transfer.borrowed(repo_c, led=gl)
    verdicts = gate.evaluate(fresh, repo_c, ch, borrowed=borrowed)
    assert len(verdicts) >= 1
    assert "migrations" in verdicts[0].reason


def test_a_rule_only_advisory_at_home_does_not_bind_abroad(gl, tmp_path):
    t, p, says = RULE
    transfer.note(str(tmp_path / "repo_a"), t, p, says, "persuasive", led=gl)
    transfer.note(str(tmp_path / "repo_b"), t, p, says, "persuasive", led=gl)
    assert all(h["status"] == "persuasive" for h in transfer.borrowed("x", led=gl))
