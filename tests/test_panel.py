"""What a person watching needs, which is not what the agent needs.

The gate answers one question - does anything stop this. A screen that only ever
shows failures cannot show a change being cleared, and a rule that stayed silent
is as informative as one that did not.
"""
import subprocess
import tempfile
from pathlib import Path

import pytest

from injunct import panel, serve, verbs
from injunct.change import Change
from injunct.db import Ledger, ledger_path


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    (r / "models").mkdir(parents=True)
    (r / "migrations").mkdir()
    (r / "models" / "patient.py").write_text('FIELDS = ["id"]\n', encoding="utf-8")
    (r / "migrations" / "001_init.sql").write_text("-- init\n", encoding="utf-8")
    for c in (["git", "init", "-q"], ["git", "add", "-A"],
              ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "s"]):
        subprocess.run(c, cwd=r, capture_output=True)
    verbs.rule(r, "models/*.py needs migrations/")
    return r


def sit(repo):
    led = Ledger(ledger_path(repo))
    out = panel.sit(led, str(repo.resolve()), Change.from_git(repo))
    led.close()
    return out


def test_a_cleared_rule_is_reported_not_omitted(repo):
    """Silence is a result. A rule that looked and found nothing is evidence."""
    (repo / "README.md").write_text("hi\n", encoding="utf-8")
    s = sit(repo)
    assert s.seats, "the panel must report every rule, including the quiet ones"
    assert all(x.verdict == panel.CLEAR for x in s.seats)
    assert not s.halted


def test_a_firing_rule_carries_its_reason_and_next_step(repo):
    (repo / "models" / "patient.py").write_text('FIELDS = ["id", "email"]\n', encoding="utf-8")
    s = sit(repo)
    assert s.halted
    halt = [x for x in s.seats if x.verdict == panel.HALT][0]
    assert halt.domain == "structure"
    assert "migrations" in halt.reason
    assert halt.next.startswith("create migrations/")


def test_halts_sort_above_everything_else(repo):
    (repo / "models" / "patient.py").write_text('FIELDS = ["id", "email"]\n', encoding="utf-8")
    verdicts = [x.verdict for x in sit(repo).seats]
    assert verdicts[0] == panel.HALT, verdicts


def test_a_broken_rule_is_skipped_and_the_panel_survives(repo):
    """One bad rule must not take the whole sitting down with it."""
    led = Ledger(ledger_path(repo))
    run_id = led.open_run(str(repo.resolve()), "bad", arm="test")
    led.close_run(run_id, "fail")
    case = led.file_case(run_id, str(repo.resolve()), "human_reject", "high", "bad rule", [], "{}")
    led.establish(case, str(repo.resolve()), "must_not_appear",
                  {"regex": "([unclosed", "glob": "**"}, "a rule that cannot compile",
                  status="binding", empanel={})
    out = panel.sit(led, str(repo.resolve()), Change.from_git(repo))
    led.close()
    assert any(x.verdict == panel.SKIP for x in out.seats)
    assert len(out.seats) >= 2, "the other rules still sat"


def test_every_seat_says_which_domain_it_belongs_to(repo):
    for x in sit(repo).seats:
        assert x.domain and x.domain != "other", x.template


def test_the_event_buffer_is_bounded():
    """A long session must not grow the server without limit."""
    serve._events.clear()
    for i in range(serve._EVENT_CAP + 40):
        serve.emit("noise", i=i)
    assert len(serve._events) == serve._EVENT_CAP
    assert serve._events[-1]["i"] == serve._EVENT_CAP + 39, "newest are kept, oldest dropped"


def test_both_paths_emit_the_same_shape(repo):
    """A page should not care whether a plugin or the watcher noticed."""
    serve._events.clear()
    serve.gate_check(str(repo), pending=["models/patient.py"])
    kinds = [e["kind"] for e in serve._events]
    assert kinds == ["sitting"]
    assert {"touched", "halted", "seats", "at"} <= set(serve._events[0])
