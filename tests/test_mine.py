"""The miner has to be conservative. A rule invented for a repo that has no
pattern is worse than no rule, because it blocks work for no reason."""
from pathlib import Path

import pytest

from injunct import mine


def history(*commits):
    return [list(c) for c in commits]


PAIR = ["models/a.py", "migrations/1.sql"]


def test_a_pairing_needs_enough_support():
    """Three times together is a coincidence; four is a habit.

    Asymmetry is held constant here - models/ moves alone plenty - so the only
    thing being tested is how often the pair was actually seen.
    """
    alone = [["models/b.py"]] * 14
    assert mine.pairings(history(*([PAIR] * 3 + alone))) == []
    assert mine.pairings(history(*([PAIR] * 4 + alone))) != []


def test_a_bulk_commit_teaches_nothing():
    """An initial import touches everything, which would pair everything with
    everything. This is exactly what broke the naive version."""
    everything = [f"dir{i}/file.py" for i in range(30)]
    assert mine.pairings(history(*[everything] * 20)) == []


def test_direction_needs_asymmetry():
    """If two things ALWAYS move together, the data supports 'A needs B' exactly
    as much as 'B needs A'. Emitting either is a guess, so emit neither."""
    assert mine.pairings(history(*[PAIR] * 10)) == []


def test_asymmetry_admits_the_real_rule():
    """models/ often moves alone; migrations/ never does. Now direction is real."""
    h = history(*([PAIR] * 6 + [["models/b.py"]] * 14))
    rules = mine.pairings(h)
    assert len(rules) == 1
    r = rules[0]
    assert r["params"]["trigger"].startswith("migrations")
    assert r["params"]["required"].startswith("models")
    assert r["evidence"]["reverse"] <= mine.MAX_REVERSE


def test_confidence_must_hold():
    """Six times together, five times apart, is not a rule."""
    h = history(*([PAIR] * 6 + [["migrations/2.sql"]] * 5 + [["other/x.py"]] * 9))
    assert all(r["params"]["trigger"] != "migrations/*" for r in mine.pairings(h))


def test_declared_hooks_need_a_files_pattern(tmp_path):
    """A hook with no files: pattern would fire on every change. That is a nag,
    not a rule."""
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - hooks:\n      - id: black\n        entry: black\n"
        "      - id: pytest\n        entry: pytest -q\n        files: '^src/.*'\n",
        encoding="utf-8")
    out = mine.declared(tmp_path)
    assert len(out) == 1
    assert out[0]["params"] == {"glob": "src/**", "cmd": "pytest -q"}


def test_no_config_is_not_an_error(tmp_path):
    assert mine.declared(tmp_path) == []


# --- against real history, because fixtures cannot prove restraint -----------

REAL = Path(r"C:\Users\carbo\projects")


@pytest.mark.skipif(not (REAL / "caliper" / ".git").is_dir(), reason="needs caliper")
def test_it_finds_a_real_habit_in_a_real_repo():
    """caliper's own commits say: results/ never moves without docs/. Read-only -
    this never writes a ledger into a repo that did not ask for one."""
    rules = mine.pairings(mine.commits(REAL / "caliper"))
    found = [r for r in rules if r["params"]["trigger"].startswith("results")]
    assert found, [r["says"] for r in rules]
    assert "docs" in found[0]["params"]["required"]


@pytest.mark.skipif(not (REAL / "lineup" / ".git").is_dir(), reason="needs lineup")
def test_it_invents_nothing_for_a_repo_with_no_pattern():
    assert mine.pairings(mine.commits(REAL / "lineup")) == []
