"""The two checks that shipped real and shipped unmeasured.

`blast_radius` and `no_quadratic` were both live in the pack and both absent
from the benchmark, so nothing could say whether they helped, hurt, or fired at
random. A fixture is only worth adding if its oracle fails for the reason the
rule predicts - otherwise the number measures the fixture, not the rule. These
assert exactly that correspondence in both directions.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from injunct import nextstep, templates
from injunct.bench.tasks import all_tasks
from injunct.change import Change

SEED = Path(__file__).resolve().parents[1] / "seeds" / "report"
REPORT = [t for t in all_tasks() if t.repo == "report"]


def build(tmp_path, actions):
    repo = tmp_path / "report"
    shutil.copytree(SEED, repo)
    touched, added, removed = [], {}, {}
    for a in actions:
        if a["tool"] != "write_file":
            continue
        p = repo / a["path"]
        before = p.read_text(encoding="utf-8").splitlines() if p.is_file() else []
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["content"], encoding="utf-8")
        after = a["content"].splitlines()
        touched.append(a["path"])
        added[a["path"]] = [ln for ln in after if ln not in set(before)]
        removed[a["path"]] = [ln for ln in before if ln not in set(after)]
    return repo, Change(repo=repo, touched=sorted(set(touched)), added=added,
                        removed=removed, commands=[])


def oracle(repo):
    return subprocess.run([sys.executable, "oracle.py"], cwd=repo,
                          capture_output=True, text=True).returncode


def task(trap):
    return next(t for t in REPORT if t.trap == trap)


def companion_actions(t):
    return [a for c in t.companions for a in c["actions"]]


# ---- the fixture itself -----------------------------------------------------

def test_the_pristine_seed_passes_its_own_oracle(tmp_path):
    repo, _ = build(tmp_path, [])
    assert oracle(repo) == 0


def test_every_report_task_family_is_present():
    assert {t.trap for t in REPORT} == {"signature_without_callers",
                                        "lookup_per_row", ""}
    assert sum(1 for t in REPORT if not t.trap) >= 3, "controls measure false positives"


# ---- blast_radius -----------------------------------------------------------

def test_a_signature_change_without_its_callers_fails_and_fires(tmp_path):
    t = task("signature_without_callers")
    repo, ch = build(tmp_path, t.primary)
    assert oracle(repo) != 0, "the oracle must fail for the reason the rule predicts"
    reason = templates.fires("blast_radius", {}, ch)
    assert reason and "caller(s) were not updated" in reason
    assert "views/summary.py" in reason


def test_updating_the_callers_passes_and_silences_the_rule(tmp_path):
    t = task("signature_without_callers")
    repo, ch = build(tmp_path, t.primary + companion_actions(t))
    assert oracle(repo) == 0
    assert templates.fires("blast_radius", {}, ch) is None


# ---- no_quadratic -----------------------------------------------------------

def test_a_lookup_per_row_fails_and_fires(tmp_path):
    t = task("lookup_per_row")
    repo, ch = build(tmp_path, t.primary)
    assert oracle(repo) != 0
    reason = templates.fires("no_quadratic", {"glob": "reports/*.py"}, ch)
    assert reason and "N+1" in reason


def test_fetching_once_passes_and_silences_the_rule(tmp_path):
    t = task("lookup_per_row")
    repo, ch = build(tmp_path, t.primary + companion_actions(t))
    assert oracle(repo) == 0
    assert templates.fires("no_quadratic", {"glob": "reports/*.py"}, ch) is None


def test_the_oracle_counts_queries_rather_than_timing_them(tmp_path):
    """A stopwatch on a loaded machine is how a benchmark starts lying."""
    src = (SEED / "oracle.py").read_text(encoding="utf-8")
    assert "CALLS" in src and "QUERY_BUDGET" in src
    for wallclock in ("import time", "time.time", "perf_counter", "timeit"):
        assert wallclock not in src, f"no {wallclock} in the decision path"


# ---- the controls stay clean ------------------------------------------------

@pytest.mark.parametrize("t", [t for t in REPORT if not t.trap], ids=lambda t: t.id)
def test_a_control_task_trips_nothing(tmp_path, t):
    repo, ch = build(tmp_path, t.primary)
    assert oracle(repo) == 0
    assert templates.fires("blast_radius", {}, ch) is None
    assert templates.fires("no_quadratic", {"glob": "**/*.py"}, ch) is None


# ---- and the card now says what to do ---------------------------------------

class _V:
    def __init__(self, template, reason):
        self.template, self.reason, self.rule = template, reason, ""


def test_blast_radius_names_the_callers_to_update(tmp_path):
    t = task("signature_without_callers")
    repo, ch = build(tmp_path, t.primary)
    reason = templates.fires("blast_radius", {}, ch)
    step = nextstep.suggest(_V("blast_radius", reason), repo, ch.touched)
    assert "views/summary.py" in step
    assert step.startswith("update the callers")


def test_no_quadratic_names_the_file_and_the_fix(tmp_path):
    t = task("lookup_per_row")
    repo, ch = build(tmp_path, t.primary)
    reason = templates.fires("no_quadratic", {"glob": "reports/*.py"}, ch)
    step = nextstep.suggest(_V("no_quadratic", reason), repo, ch.touched)
    assert "reports/owners.py" in step
    assert "fetch once outside" in step


def test_a_card_with_no_instruction_is_the_thing_this_fixes():
    """Both of these used to return "" - a verdict with no next action. Our own
    compliance sweep says the instruction is the mechanism, not the gate."""
    for template in ("blast_radius", "no_quadratic"):
        step = nextstep.suggest(_V(template, "something unparseable"), Path("."), [])
        assert step, f"{template} must always offer some instruction"
