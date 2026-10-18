"""The six commands, from the point of view of someone who just wants their
agent to stop repeating itself."""
import subprocess

import pytest

from injunct import gate, verbs
from injunct.change import Change
from injunct.db import Ledger
from injunct.workspace import restore
from tests.test_loop import SEED, model_file


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "clinic"
    restore(SEED, r)
    for c in (["git", "init", "-q"], ["git", "add", "-A"],
              ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "s"]):
        subprocess.run(c, cwd=r, capture_output=True)
    return r


# --- rule -------------------------------------------------------------------

def test_the_three_forms_parse():
    assert verbs.parse("models/*.py needs migrations/")[0] == "co_change"
    assert verbs.parse("never touch package-lock.json")[0] == "forbidden_edit"
    assert verbs.parse("after src/*.py run pytest -q")[0] == "required_command"


def test_a_trailing_slash_becomes_a_directory_glob():
    _, params, _ = verbs.parse("models/*.py needs migrations/")
    assert params["required"] == "migrations/**"


def test_nonsense_is_refused_rather_than_guessed():
    assert verbs.parse("please remember the migrations thing") is None


def test_a_taught_rule_binds_immediately(repo):
    """You know your own repo. Waiting to fail first is silly."""
    out = verbs.rule(repo, "models/*.py needs migrations/")
    assert out["status"] == "binding"
    led = Ledger(repo / ".injunct" / "ledger.db")
    ch = Change(repo=repo, touched=["models/patient.py"])
    assert gate.evaluate(led, str(repo.resolve()), ch)
    led.close()


def test_a_taught_rule_that_would_have_broken_past_work_is_only_advisory(repo):
    """Even a rule you wrote yourself gets replayed against history."""
    led = Ledger(repo / ".injunct" / "ledger.db")
    run_id = led.open_run(str(repo.resolve()), "a run that already passed")
    led.close_run(run_id, "pass")
    from injunct import artifacts
    artifacts.save(repo, run_id, Change(repo=repo, touched=["models/patient.py"]))
    led.close()

    out = verbs.rule(repo, "models/*.py needs migrations/")
    assert out["status"] == "persuasive"
    assert out["receipt"]["false_ids"]


# --- why --------------------------------------------------------------------

def test_why_names_the_rule_and_where_it_came_from(repo):
    verbs.rule(repo, "models/*.py needs migrations/")
    rows = verbs.why(repo, "models/patient.py")
    assert len(rows) == 1
    assert rows[0]["source"] == "taught"
    assert "migrations" in rows[0]["says"]


def test_why_is_quiet_about_files_nothing_applies_to(repo):
    verbs.rule(repo, "models/*.py needs migrations/")
    assert verbs.why(repo, "static/index.html") == []


# --- off / on ---------------------------------------------------------------

def test_muting_stops_the_gate_and_keeps_the_case(repo):
    """The escape hatch. Without it, one bad block and the whole thing goes."""
    out = verbs.rule(repo, "models/*.py needs migrations/")
    led = Ledger(repo / ".injunct" / "ledger.db")
    ch = Change(repo=repo, touched=["models/patient.py"])
    root = str(repo.resolve())
    assert gate.evaluate(led, root, ch)
    led.close()

    assert verbs.mute(repo, out["id"])["was"] == "binding"
    led = Ledger(repo / ".injunct" / "ledger.db")
    assert gate.evaluate(led, root, ch) == []
    assert len(led.cases(repo=root)) == 1, "the case is kept, only the rule is off"
    led.close()

    assert verbs.mute(repo, out["id"], on=True)["status"] == "binding"
    led = Ledger(repo / ".injunct" / "ledger.db")
    assert gate.evaluate(led, root, ch)
    led.close()


def test_muting_something_that_does_not_exist_says_so(repo):
    assert verbs.mute(repo, 999) is None


# --- init / status / hook ---------------------------------------------------

def test_init_on_a_repo_with_one_commit_proposes_nothing(repo):
    """A fresh repo has no habits. Saying so beats inventing rules."""
    assert verbs.init(repo) == []


def test_init_never_proposes_the_same_rule_twice(repo, monkeypatch):
    monkeypatch.setattr(verbs.mine, "propose", lambda *a, **k: [{
        "template": "co_change",
        "params": {"trigger": "models/*.py", "required": "migrations/**"},
        "says": "Changing models/*.py means changing migrations/ too.",
        "evidence": {"support": 9, "confidence": 1.0, "reverse": 0.2, "commits": 40},
    }])
    first = verbs.init(repo)
    assert len(first) == 1 and first[0]["id"]
    assert verbs.init(repo) == [], "running init twice must not duplicate rules"


def test_mined_rules_start_advisory(repo, monkeypatch):
    """History is evidence about habits, not proof that breaking one hurts."""
    monkeypatch.setattr(verbs.mine, "propose", lambda *a, **k: [{
        "template": "forbidden_edit", "params": {"glob": "*.lock"},
        "says": "Never edit *.lock.", "evidence": {"support": 8, "confidence": 1.0,
                                                   "reverse": 0.1, "commits": 40},
    }])
    verbs.init(repo)
    led = Ledger(repo / ".injunct" / "ledger.db")
    assert [h["status"] for h in led.holdings()] == ["persuasive"]
    led.close()


def test_status_counts_what_was_stopped(repo):
    out = verbs.rule(repo, "models/*.py needs migrations/")
    led = Ledger(repo / ".injunct" / "ledger.db")
    run_id = led.open_run(str(repo.resolve()), "gate", arm="cli")
    led.cite(run_id, out["id"], "blocked")
    led.cite(run_id, out["id"], "overridden_pass")
    led.close()

    s = verbs.status(repo)
    assert s["stopped"] == 1 and s["overridden"] == 1
    assert s["binding"] == 1


def test_hook_lands_where_git_will_run_it(repo):
    target = verbs.hook(repo)
    assert target and target.name == "pre-commit"
    assert "injunct gate" in target.read_text(encoding="utf-8")


def test_hook_declines_outside_a_git_repo(tmp_path):
    assert verbs.hook(tmp_path) is None


def test_init_says_which_kind_of_nothing_it_found(tmp_path):
    """'Nothing to learn' is three different problems with three different
    fixes, and a person who is told the wrong one just retries."""
    import subprocess
    from injunct import mine

    plain = tmp_path / "plain"
    plain.mkdir()
    assert mine.history_state(plain) == "not-a-repo"

    fresh = tmp_path / "fresh"
    fresh.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fresh, capture_output=True)
    assert mine.history_state(fresh) == "no-commits"

    for i in range(3):
        (fresh / f"f{i}.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=fresh, capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                        "commit", "-qm", f"c{i}"], cwd=fresh, capture_output=True)
    assert mine.history_state(fresh) == "thin", "under 20 commits proves nothing"
