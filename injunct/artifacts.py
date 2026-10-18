"""Working-tree snapshots, kept on disk so a holding can be replayed against history."""
from __future__ import annotations

import json
from pathlib import Path

from .change import Change


def _dir(repo: Path) -> Path:
    d = Path(repo) / ".injunct" / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save(repo: Path, run_id: int, ch: Change) -> None:
    """Everything a check might need to judge this run later.

    `commands` and `removed` are here because empanelment replays proposed
    rules against these snapshots, and a check that cannot see what it needs
    abstains - which silently makes it unfalsifiable rather than merely
    untested. See empanel.py.
    """
    (_dir(repo) / f"run_{run_id}.json").write_text(
        json.dumps({"v": 2, "touched": ch.touched, "added": ch.added,
                    "removed": ch.removed, "commands": ch.commands}),
        encoding="utf-8")


def load(repo: Path, run_id: int) -> Change | None:
    p = _dir(repo) / f"run_{run_id}.json"
    if not p.is_file():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    # A v1 artifact recorded neither, and the honest reading of that is
    # "unknown", not "nothing ran" and not "nothing was removed". `.get` with
    # no default is doing real work here: None is the value that makes a
    # command-aware check abstain instead of judging on absent evidence.
    return Change(repo=Path(repo), touched=d["touched"], added=d.get("added", {}),
                  removed=d.get("removed"), commands=d.get("commands"))
