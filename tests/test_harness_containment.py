"""The agent may not write outside the repository it was given.

A live run wrote phone_verified into seeds/clinic - the pristine corpus every
benchmark restores from - because `repo / path` is not a containment check:
Python drops the base when the right-hand side is absolute, and `..` walks out.
Contaminating the seeds changes what every future run measures, silently.
"""
import pytest

from injunct import harness


def test_a_relative_escape_is_refused(tmp_path):
    (tmp_path / "inside").mkdir()
    with pytest.raises(harness.Escaped):
        harness._apply(tmp_path / "inside", "../../outside.py", "x = 1")
    assert not (tmp_path.parent / "outside.py").exists()


def test_an_absolute_path_is_refused(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    victim = tmp_path / "seeds" / "patient.py"
    victim.parent.mkdir(parents=True)
    victim.write_text("original", encoding="utf-8")
    with pytest.raises(harness.Escaped):
        harness._apply(repo, str(victim), "clobbered")
    assert victim.read_text(encoding="utf-8") == "original"


def test_ordinary_paths_still_work(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    harness._apply(repo, "models/patient.py", "FIELDS = []")
    assert (repo / "models" / "patient.py").read_text(encoding="utf-8") == "FIELDS = []"
