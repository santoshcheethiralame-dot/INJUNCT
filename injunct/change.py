"""What the agent did to the working tree, in the only shape a check needs."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path


IGNORED = (".injunct/", "__pycache__/", ".git/")


def _ours(path: str) -> bool:
    return any(seg in path for seg in IGNORED)


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return out.stdout


@dataclass
class Change:
    repo: Path
    touched: list[str] = field(default_factory=list)          # repo-relative, forward slashes
    added: dict[str, list[str]] = field(default_factory=dict)    # path -> added lines
    # None means "not observable", exactly as `commands` does. Only a v1
    # artifact replayed by empanelment carries that; a live Change always
    # observes removals, and {} truthfully means "looked, found none".
    removed: dict[str, list[str]] | None = field(default_factory=dict)  # path -> removed lines
    commands: list[str] | None = None   # None means "we could not see them"

    def text(self, path: str) -> str:
        p = self.repo / path
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def run(self, cmd: str) -> int:
        from .shell import run as sh
        return sh(cmd, self.repo).returncode

    @classmethod
    def from_git(cls, repo: Path) -> "Change":
        """Uncommitted work: staged, unstaged, and untracked."""
        repo = Path(repo)
        names = set()
        for args in (("diff", "--name-only", "HEAD"), ("diff", "--name-only"),
                     ("ls-files", "--others", "--exclude-standard")):
            names.update(x for x in _git(repo, *args).splitlines() if x.strip())
        touched = sorted(n for n in (x.replace("\\", "/") for x in names) if not _ours(n))

        added: dict[str, list[str]] = {}
        removed: dict[str, list[str]] = {}
        current = None
        for line in _git(repo, "diff", "HEAD", "-U0").splitlines():
            if line.startswith("+++ b/"):
                current = line[6:].replace("\\", "/")
                if _ours(current):
                    current = None
                    continue
                added.setdefault(current, [])
                removed.setdefault(current, [])
            elif line.startswith("+") and not line.startswith("+++") and current:
                added[current].append(line[1:])
            elif line.startswith("-") and not line.startswith("---") and current:
                removed[current].append(line[1:])
        # untracked files are entirely "added"
        tracked = {x for x in _git(repo, "ls-files").splitlines()}
        for t in touched:
            if t not in tracked and t not in added:
                added[t] = (repo / t).read_text(encoding="utf-8", errors="replace").splitlines() \
                    if (repo / t).is_file() else []
        return cls(repo=repo, touched=touched, added=added, removed=removed)

    @classmethod
    def snapshot(cls, repo: Path) -> dict[str, str]:
        repo = Path(repo)
        return {str(p.relative_to(repo)).replace("\\", "/"): p.read_text(encoding="utf-8", errors="replace")
                for p in repo.rglob("*")
                if p.is_file() and not _ours(str(p.relative_to(repo)).replace("\\", "/"))}

    @classmethod
    def since(cls, repo: Path, before: dict[str, str],
              commands: list[str] | None = None) -> "Change":
        """Everything that changed, including work a command did on the agent's behalf."""
        now = cls.snapshot(repo)
        touched, added, removed = [], {}, {}
        for path, text in now.items():
            if before.get(path) == text:
                continue
            touched.append(path)
            old_lines = before.get(path, "").splitlines()
            new_lines = text.splitlines()
            old_set, new_set = set(old_lines), set(new_lines)
            added[path] = [ln for ln in new_lines if ln not in old_set]
            removed[path] = [ln for ln in old_lines if ln not in new_set]
        touched += [p for p in before if p not in now]
        return cls(repo=Path(repo), touched=sorted(touched), added=added,
                   removed=removed, commands=commands)

    @classmethod
    def from_edits(cls, repo: Path, edits: dict[str, str]) -> "Change":
        """Used by the harness, which knows exactly what it wrote."""
        return cls(repo=Path(repo), touched=sorted(edits),
                   added={k: v.splitlines() for k, v in edits.items()})
