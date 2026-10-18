"""The live harness has produced a plausible-looking but disarmed result before.
These tests exist so that cannot happen quietly again."""
import os
from pathlib import Path

import pytest

from injunct import gate, live
from injunct.change import Change
from injunct.db import Ledger

SEED = Path(__file__).resolve().parents[1] / "seeds" / "clinic"


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "trial"
    taught = live.setup(SEED, repo)
    return repo, taught


def test_setup_arms_a_binding_precedent(workspace):
    _, taught = workspace
    assert taught["status"] == "binding", taught.get("receipt")


def test_setup_leaves_the_agents_own_configuration_in_place(workspace):
    """restore() deletes anything the seed lacks. The plugin is not in the seed,
    so installing it before the last restore silently disarms every arm."""
    repo, _ = workspace
    assert (repo / ".opencode" / "plugins" / "injunct.ts").is_file()
    assert (repo / "opencode.json").is_file()
    assert (repo / "AGENTS.md").is_file()


def test_the_baseline_is_the_seed_not_the_teaching_run(workspace):
    repo, _ = workspace
    assert Change.from_git(repo).touched == [], "a clean baseline shows no changes"
    assert '["id", "name", "phone"]' in (repo / "models" / "patient.py").read_text(encoding="utf-8")


def test_the_recorder_sees_work_and_the_gate_judges_it(workspace):
    repo, _ = workspace
    f = repo / "models" / "patient.py"
    f.write_text(f.read_text(encoding="utf-8").replace(
        '["id", "name", "phone"]', '["id", "name", "phone", "zzz"]'), encoding="utf-8")
    ch = Change.from_git(repo)
    assert ch.touched == ["models/patient.py"]
    led = Ledger(repo / ".injunct" / "ledger.db")
    assert gate.evaluate(led, str(repo.resolve()), ch), "the armed precedent must fire"
    led.close()


def test_reset_clears_the_work_without_committing_it(workspace):
    """Committing here folds the last trial into HEAD, and the recorder then
    reports that the agent touched nothing at all."""
    repo, _ = workspace
    (repo / "migrations" / "999_stray.sql").write_text("-- stray", encoding="utf-8")
    f = repo / "models" / "patient.py"
    f.write_text("FIELDS = []\n", encoding="utf-8")
    live._reset_tree(repo)
    assert Change.from_git(repo).touched == []
    assert not (repo / "migrations" / "999_stray.sql").exists()
    assert (repo / ".opencode" / "plugins" / "injunct.ts").is_file()


def test_armed_refuses_a_workspace_with_no_plugin(workspace):
    repo, _ = workspace
    (repo / ".opencode" / "plugins" / "injunct.ts").unlink()
    led = Ledger(repo / ".injunct" / "ledger.db")
    with pytest.raises(RuntimeError, match="plugin is not installed"):
        live._armed(repo, led)
    led.close()


def test_armed_refuses_a_ledger_with_nothing_to_enforce(workspace, tmp_path):
    repo, _ = workspace
    empty = Ledger(tmp_path / "empty.db")
    with pytest.raises(RuntimeError, match="no binding precedent"):
        live._armed(repo, empty)
    empty.close()


def test_a_trial_where_the_agent_never_ran_is_not_a_pass():
    """A 504 or a timeout leaves an untouched tree, and an untouched tree
    passes the oracle. Counting that as a success credits the arm for work
    that never happened - which is how a provider outage becomes a finding."""
    assert live.vacuous({"touched": [], "halted": False, "oracle_passed": True})
    assert not live.vacuous({"touched": [], "halted": True, "oracle_passed": True})
    assert not live.vacuous({"touched": ["models/patient.py"], "halted": False})


def test_dead_trials_are_excluded_from_the_score_and_declared():
    rows = [
        {"mode": "off", "touched": [], "halted": False, "oracle_passed": True, "fired": []},
        {"mode": "off", "touched": ["a.py"], "halted": False, "oracle_passed": False, "fired": []},
    ]
    real = [r for r in rows if not live.vacuous(r)]
    assert len(real) == 1
    s = live.score(real)
    assert s["trials"] == 1 and s["agent_failed"] == 1, \
        "the empty trial must not dilute the failure rate"


def test_armed_refuses_when_the_service_is_not_listening(workspace):
    """The plugin file existing proves nothing. It was present, the service was
    not, and all three arms silently ran bare while reporting numbers."""
    repo, _ = workspace
    led = Ledger(repo / ".injunct" / "ledger.db")
    with pytest.raises(RuntimeError, match="not answering"):
        live._armed(repo, led, port=59999)      # nothing is there
    led.close()


def test_armed_passes_only_when_the_gate_actually_fires(workspace):
    """End to end: start the service, ask it the question the plugin asks, and
    require the answer that means the treatment is live."""
    repo, _ = workspace
    httpd = live.start_service(4111)
    try:
        led = Ledger(repo / ".injunct" / "ledger.db")
        live._armed(repo, led, port=4111)       # must not raise
        led.close()
    finally:
        if httpd:
            httpd.shutdown()


def test_the_trigger_path_comes_from_the_rule_itself(workspace):
    _, taught = workspace
    from injunct.db import Ledger as L
    repo, _ = workspace
    led = L(repo / ".injunct" / "ledger.db")
    binding = [h for h in led.holdings() if h["status"] == "binding"][0]
    led.close()
    assert live._trigger_path(binding).endswith(".py")
