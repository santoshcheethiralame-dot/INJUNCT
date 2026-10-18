"""The closed loop, end to end: it fails, it learns, it refuses to fail the same way."""
import shutil
from pathlib import Path

import pytest

from injunct.db import Ledger
from injunct import harness

SEED = Path(__file__).resolve().parents[1] / "seeds" / "clinic"
ORACLE = "python oracle.py"

MODEL = 'FIELDS = {fields}\n\nLABELS = {{"id": "#", "name": "Patient", "phone": "Phone"}}\n'


def model_file(*extra):
    return MODEL.format(fields=repr(["id", "name", "phone", *extra]))


def reset(repo: Path):
    """Restore the working tree, keep the ledger. Runs share one repo identity."""
    for item in SEED.iterdir():
        if item.name in ("__pycache__", ".injunct"):
            continue
        dst = repo / item.name
        if item.is_dir():
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(item, dst, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(item, dst)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "clinic"
    r.mkdir()
    reset(r)
    return r


def test_the_loop_closes(repo):
    led = Ledger(repo / ".injunct" / "ledger.db")

    # 1. a run that goes right - the model and its migration, together
    good = harness.run(repo, "add a notes field", led, arm="A", oracle=ORACLE, scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": model_file("notes")},
        {"tool": "write_file", "path": "migrations/002_notes.sql",
         "content": "ALTER TABLE patients ADD COLUMN notes TEXT;"},
        {"tool": "done"},
    ])
    assert good.passed, "the seeded app should survive a change that brings its migration"

    # 2. the same shape of task, done badly
    reset(repo)
    bad = harness.run(repo, "add a phone_verified field", led, arm="A", oracle=ORACLE, scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": model_file("phone_verified")},
        {"tool": "done"},
    ])
    assert not bad.passed, "a field with no migration must take the app down"

    # 3. the failure becomes precedent, and it is binding because it survived replay
    out = harness.register_failure(repo, led, bad, oracle=ORACLE, use_model=False)
    assert out["template"] == "co_change", out
    assert out["params"]["required"].startswith("migrations")
    assert out["status"] == "binding", out["receipt"]
    assert out["receipt"]["fire"] == "1/1" and out["receipt"]["false"].startswith("0/")

    # 4. the same mistake, with the ledger on - it is stopped, then it does the work
    reset(repo)
    fixed = harness.run(repo, "add a phone_verified field", led, arm="C", oracle=ORACLE, scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": model_file("phone_verified")},
        {"tool": "write_file", "path": "migrations/003_phone_verified.sql",
         "content": "ALTER TABLE patients ADD COLUMN phone_verified INTEGER DEFAULT 0;"},
        {"tool": "done"},
    ])
    assert fixed.blocked == 1, "the gate must fire on the model edit"
    assert fixed.passed, "and the run must succeed once the migration exists"

    # 5. an unrelated change is not touched by the precedent
    reset(repo)
    quiet = harness.run(repo, "fix a typo in the page title", led, arm="C", oracle=ORACLE, scripted=[
        {"tool": "write_file", "path": "static/index.html",
         "content": (repo / "static" / "index.html").read_text(encoding="utf-8")},
        {"tool": "done"},
    ])
    assert quiet.blocked == 0, "a precedent that fires on everything is a false positive"
    assert quiet.passed


def test_arm_a_has_no_memory_and_repeats_itself(repo):
    led = Ledger(repo / ".injunct" / "ledger.db")
    good = harness.run(repo, "add a notes field", led, arm="A", oracle=ORACLE, scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": model_file("notes")},
        {"tool": "write_file", "path": "migrations/002_notes.sql",
         "content": "ALTER TABLE patients ADD COLUMN notes TEXT;"},
        {"tool": "done"},
    ])
    assert good.passed
    reset(repo)
    bad = harness.run(repo, "add a phone_verified field", led, arm="A", oracle=ORACLE, scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": model_file("phone_verified")},
        {"tool": "done"},
    ])
    harness.register_failure(repo, led, bad, oracle=ORACLE, use_model=False)

    reset(repo)
    again = harness.run(repo, "add a phone_verified field", led, arm="A", oracle=ORACLE, scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": model_file("phone_verified")},
        {"tool": "done"},
    ])
    assert again.blocked == 0, "arm A must not be gated - that is the whole comparison"
    assert not again.passed
