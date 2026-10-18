"""What a stored run remembers decides what empanelment can ever disprove.

An artifact that drops the commands a run issued does not merely lose detail -
it makes every command-aware rule unfalsifiable, because the check abstains and
the abstention reads as silence. These assert the record is complete enough to
contradict a rule, and that an older, thinner record admits it is thin rather
than pretending nothing happened.
"""
import json

from injunct import artifacts
from injunct.change import Change


def test_it_round_trips_commands_and_removed(tmp_path):
    ch = Change(repo=tmp_path, touched=["client/generated.py"],
                added={"client/generated.py": ["x = 1"]},
                removed={"client/generated.py": ["x = 0"]},
                commands=["python tools/gen.py"])
    artifacts.save(tmp_path, 7, ch)
    back = artifacts.load(tmp_path, 7)

    assert back.touched == ["client/generated.py"]
    assert back.added == {"client/generated.py": ["x = 1"]}
    assert back.removed == {"client/generated.py": ["x = 0"]}
    assert back.commands == ["python tools/gen.py"]


def test_a_run_that_issued_no_commands_says_so(tmp_path):
    """[] is a finding. None is an absence. They must not collapse."""
    artifacts.save(tmp_path, 8, Change(repo=tmp_path, touched=["a.py"], commands=[]))
    assert artifacts.load(tmp_path, 8).commands == []


def test_an_old_artifact_reads_as_unknown_not_as_nothing(tmp_path):
    """A v1 record predates any of this. Treating its silence as evidence is
    exactly the bug; it has to come back as None so checks abstain."""
    d = tmp_path / ".injunct" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    (d / "run_9.json").write_text(
        json.dumps({"touched": ["models/patient.py"], "added": {}}), encoding="utf-8")

    back = artifacts.load(tmp_path, 9)
    assert back.touched == ["models/patient.py"]
    assert back.commands is None
    assert back.removed is None


def test_a_missing_artifact_is_none(tmp_path):
    assert artifacts.load(tmp_path, 404) is None
