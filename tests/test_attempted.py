"""Doing nothing must not score a pass.

The oracle asks whether the repository is consistent, and a repository nobody
touched is consistent. A live three-arm run scored 100% in all three arms with
no blocks and no failures because the model read files and stopped.
"""
from pathlib import Path

from injunct.bench.tasks import all_tasks, SEEDS


def _trapped():
    return [t for t in all_tasks() if t.trap]


def test_a_pristine_seed_is_never_an_attempt():
    for t in _trapped():
        assert not t.attempted(SEEDS / t.repo), f"{t.id} looks done without being done"


def test_doing_the_primary_edit_counts_as_an_attempt(tmp_path):
    import shutil
    for t in _trapped()[:6]:
        repo = tmp_path / t.id
        shutil.copytree(SEEDS / t.repo, repo)
        for act in t.primary:
            if act.get("tool") != "write_file":
                continue
            f = repo / act["path"]
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(act["content"], encoding="utf-8")
        assert t.attempted(repo), f"{t.id} was done and still reads as untouched"
