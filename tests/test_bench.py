"""The benchmark makes a claim about itself: same seed, same behaviour, and the
only difference between arms is enforcement. That claim gets tested."""
import random

from injunct.bench import agent, run
from injunct.bench.tasks import all_tasks


def test_the_suite_is_what_it_says():
    tasks = all_tasks()
    assert len(tasks) == 41
    assert sum(1 for t in tasks if not t.trap) == 10, "controls measure false positives"
    assert {t.repo for t in tasks} == {"clinic", "typegen", "registry", "report"}
    # Every shipped check that can be trapped has a trap. Adding a template
    # without one is how blast_radius and no_quadratic went unmeasured.
    assert {t.trap for t in tasks if t.trap} == {
        "schema_without_migration", "handedit_generated", "types_without_regen",
        "plugin_without_declaration", "signature_without_callers", "lookup_per_row"}
    for t in tasks:
        assert t.primary, t.id
        for c in t.companions:
            assert c["actions"] and c["produces"], t.id


def test_the_agent_is_identical_across_arms_for_one_seed():
    task = [t for t in all_tasks() if t.trap == "schema_without_migration"][0]
    a, _ = agent.script(task, random.Random(11), 0.5)
    b, _ = agent.script(task, random.Random(11), 0.5)
    assert a == b, "arms must differ by enforcement, not by the agent"


def test_recall_is_the_only_knob():
    task = [t for t in all_tasks() if t.trap == "schema_without_migration"][0]
    never, skipped = agent.script(task, random.Random(3), 0.0)
    assert skipped == [0] and len(never) == 2
    always, skipped = agent.script(task, random.Random(3), 1.0)
    assert skipped == [] and len(always) == 3


def test_a_run_is_reproducible(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "WORK", tmp_path)
    subset = [t for t in all_tasks() if t.repo == "clinic"]
    first = run.run_arm("A", 7, 0.5, subset)
    second = run.run_arm("A", 7, 0.5, subset)
    assert [r["task"] for r in first] == [r["task"] for r in second]
    assert [r["passed"] for r in first] == [r["passed"] for r in second]


def test_arm_a_never_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "WORK", tmp_path)
    rows = run.run_arm("A", 2, 0.5, [t for t in all_tasks() if t.repo == "clinic"])
    assert sum(r["blocked"] for r in rows) == 0
    assert all(r["passed"] for r in rows if not r["trap"]), "controls must pass unaided"


def test_repeat_failure_only_counts_traps_already_seen():
    rows = [
        {"arm": "X", "seed": 1, "order": 0, "trap": "t", "passed": False, "blocked": 0},
        {"arm": "X", "seed": 1, "order": 1, "trap": "t", "passed": False, "blocked": 0},
        {"arm": "X", "seed": 1, "order": 2, "trap": "t", "passed": True, "blocked": 0},
        {"arm": "X", "seed": 1, "order": 3, "trap": "", "passed": True, "blocked": 1},
    ]
    m = run.metrics(rows)["X"]
    assert m["repeat_seen"] == 2, "the first failure of a class is not a repeat"
    assert m["repeat_failure_rate"] == 0.5
    assert m["false_positive_rate"] == 1.0, "a control that was blocked is a false positive"


def test_regressions_are_a_passed_c_failed():
    rows = [
        {"arm": "A", "seed": 1, "order": 0, "task": "x", "trap": "t", "passed": True, "blocked": 0},
        {"arm": "C", "seed": 1, "order": 0, "task": "x", "trap": "t", "passed": False, "blocked": 1},
        {"arm": "A", "seed": 1, "order": 1, "task": "y", "trap": "t", "passed": False, "blocked": 0},
        {"arm": "C", "seed": 1, "order": 1, "task": "y", "trap": "t", "passed": True, "blocked": 1},
    ]
    assert [r["task"] for r in run.regressions(rows)] == ["x"]


def test_the_agent_teaches_us_without_a_human(tmp_path):
    """Churn, reverts and broken tests are free signals. Nobody has to say no."""
    from injunct import harness, record
    from injunct.change import Change
    from injunct.db import Ledger
    from injunct.workspace import restore
    from tests.test_loop import SEED, model_file

    repo = tmp_path / "clinic"
    restore(SEED, repo)
    led = Ledger(repo / ".injunct" / "ledger.db")

    nl = chr(10)
    sprawling = nl.join([f"HELPER_{i} = {i}" for i in range(12)]) + nl + model_file("notes")
    reconsidered = model_file("notes")          # most of the first attempt thrown away

    res = harness.run(repo, "add a field, then think better of it", led, arm="A", scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": sprawling},
        {"tool": "write_file", "path": "models/patient.py", "content": reconsidered},
        {"tool": "write_file", "path": "migrations/002.sql",
         "content": "ALTER TABLE patients ADD COLUMN notes TEXT;"},
        {"tool": "done"},
    ])
    filed = record.file_free_signals(led, res.run_id, str(repo.resolve()), res.watch,
                                     Change.since(repo, res.before))
    assert filed, "rewriting a file inside one run is a signal"
    assert any(led.case(f["case_id"])["source"] == "churn" for f in filed)
    assert all(f["status"] != "binding" for f in filed), \
        "a low-confidence signal must never reach binding authority"
