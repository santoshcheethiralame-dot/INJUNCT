"""What the rules would have caught, if they had been there.

    injunct hindsight [repo]

Every tool claims it prevents bugs. This asks the repository instead. Walk its
recent history, find the commits that fixed something, trace each fix back to
the commit that introduced the problem, and replay every rule Injunct knows
against that commit as it landed.

Tracing uses SZZ (Sliwerski, Zimmermann, Zeller 2005): the lines a fix had to
change were last written by the commit that broke them, and `git blame` on the
fix's parent names it. A revert names its target outright. SZZ is noisy - a
fix that only adds lines points at nothing, and a refactor in between points
at the wrong commit - so every catch is printed with both commits, for a
person to check, and the method is stated rather than hidden.

A rule that fires on everything "catches" every bug for free. So the same
rules are replayed against every other commit in the window, and the report
puts the two rates side by side: caught N of the bug-introducing commits,
fired on M of the clean ones. Only the gap between them is evidence.

Only checks that decide from the diff alone are replayed. `must_appear`,
`regression_test`, `no_quadratic` and `blast_radius` read the working tree as
it is today, not as it was then, and replaying them against old commits would
be judging the past by the present.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import templates
from .change import Change
from .db import Ledger, ledger_path
from .shell import run as sh

# A subject that says it fixes something. "bug" alone is not enough: "quick
# debug for the double-booking bug" is the commit that caused one.
FIX = re.compile(r"\b(fix(e[sd]|ing)?|hotfix|bugfix|revert(s|ed)?|regression|forgot|missing)\b", re.I)
REVERTS = re.compile(r"This reverts commit ([0-9a-f]{7,40})")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", re.M)
REPLAYABLE = ("co_change", "forbidden_edit", "must_not_appear", "must_not_remove")
# The miner skips commits over 12 files because a huge commit is no evidence of
# a habit. Replay is a different question - a big commit can still break a
# rule - so the bar here is only there to skip vendored dumps and mass renames.
MAX_FILES = 50
WINDOW = 300


@dataclass
class Catch:
    introduced: str          # "sha subject"
    fixed_by: str
    rules: list[dict] = field(default_factory=list)   # {"id", "status", "says", "why"}


def _git(repo: Path, args: str) -> str:
    return sh(f"git {args}", repo, timeout=60).stdout


def _subject(repo: Path, sha: str) -> str:
    return _git(repo, f"log -1 --format=%h%x20%s {sha}").strip()


def _shallow(repo: Path) -> set[str]:
    """Boundary commits of a shallow clone. Blame credits them with every line
    older than the clone, so they can never be named as the cause of anything."""
    p = repo / ".git" / "shallow"
    try:
        return {x.strip() for x in p.read_text().splitlines() if x.strip()}
    except OSError:
        return set()


def change_of(repo: Path, sha: str) -> Change | None:
    """A commit as the gate would have seen it the moment before it landed."""
    names = [x.strip().replace("\\", "/") for x in
             _git(repo, f"show --name-only --pretty=format: {sha}").splitlines() if x.strip()]
    if not names or len(names) > MAX_FILES:
        return None
    added: dict[str, list[str]] = {}
    removed: dict[str, list[str]] = {}
    cur = None
    for raw in _git(repo, f"show -U0 --pretty=format: --no-color {sha}").splitlines():
        if raw.startswith("+++ "):
            cur = raw[6:].replace("\\", "/") if raw.startswith("+++ b/") else None
            if cur:
                added.setdefault(cur, []), removed.setdefault(cur, [])
        elif raw.startswith(("--- ", "diff --git", "@@")):
            continue
        elif cur and raw.startswith("+"):
            added[cur].append(raw[1:])
        elif cur and raw.startswith("-"):
            removed[cur].append(raw[1:])
    return Change(repo=repo, touched=sorted(names), added=added, removed=removed, commands=None)


def commits(repo: Path, window: int = WINDOW) -> list[tuple[str, str, str]]:
    """(sha, subject, body), newest first, merges excluded."""
    raw = _git(repo, f"log -{window} --no-merges --format=%H%x1f%s%x1f%b%x1e")
    out = []
    for rec in raw.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) == 3 and parts[0].strip():
            out.append((parts[0].strip(), parts[1], parts[2]))
    return out


def introducers(repo: Path, sha: str, body: str, boundary: set[str]) -> set[str]:
    """The commits whose lines this fix had to change."""
    m = REVERTS.search(body)
    if m:
        full = _git(repo, f"rev-parse --verify --quiet {m.group(1)}").strip()
        return {full} if full and full not in boundary else set()
    if sha in boundary:
        return set()
    found: set[str] = set()
    files = [f for f in _git(repo, f"show --name-only --pretty=format: {sha}").splitlines() if f.strip()]
    for f in files[:MAX_FILES]:
        f = f.strip()
        # `~1`, never `^`: commands reach git through cmd.exe on Windows,
        # where `^` is the escape character and `sha^` silently becomes `sha`.
        diff = _git(repo, f'diff -U0 --no-color {sha}~1 {sha} -- "{f}"')
        for hm in HUNK.finditer(diff):
            start, length = int(hm.group(1)), int(hm.group(2) if hm.group(2) is not None else 1)
            if length == 0:            # a pure addition: SZZ has nothing to blame
                continue
            blame = _git(repo, f'blame --porcelain -L {start},+{length} {sha}~1 -- "{f}"')
            for line in blame.splitlines():
                head = line.split(" ", 1)[0]
                if re.fullmatch(r"[0-9a-f]{40}", head) and head not in boundary:
                    found.add(head)
    found.discard(sha)
    return found


def _rules(led: Ledger, repo: Path) -> list[dict]:
    return [h for h in led.holdings(repo=str(repo)) if h["template"] in REPLAYABLE]


def run(target, window: int = WINDOW) -> dict:
    from .coverage import _resolve
    repo, remote = _resolve(target)
    led = Ledger(ledger_path(repo))
    rules = _rules(led, repo)
    led.close()
    boundary = _shallow(repo)

    log = commits(repo, window)
    in_window = {sha for sha, _, _ in log}
    fixes = [(sha, subj, body) for sha, subj, body in log if FIX.search(subj) or REVERTS.search(body)]
    cause: dict[str, list[str]] = {}          # introducer -> the fixes that point at it
    for sha, subj, body in fixes:
        for b in introducers(repo, sha, body, boundary):
            if b in in_window:
                cause.setdefault(b, []).append(sha)

    def fired(sha: str) -> list[dict] | None:
        ch = change_of(repo, sha)
        if ch is None:
            return None
        out = []
        for h in rules:
            why = templates.fires(h["template"], h["params"], ch)
            if why:
                out.append({"id": h["id"], "status": h["status"], "says": h["says"], "why": why})
        return out

    catches, bug_judged = [], 0
    for b, fixed in cause.items():
        hits = fired(b)
        if hits is None:
            continue
        bug_judged += 1
        if hits:
            catches.append(Catch(_subject(repo, b), _subject(repo, fixed[0]), hits))

    fix_set = {sha for sha, _, _ in fixes}
    clean_judged = clean_fired = 0
    for sha, _, _ in log:
        if sha in cause or sha in fix_set:
            continue
        hits = fired(sha)
        if hits is None:
            continue
        clean_judged += 1
        clean_fired += bool(hits)

    binding = [c for c in catches if any(r["status"] == "binding" for r in c.rules)]
    return {
        "repo": remote or str(repo),
        "window": len(log),
        "rules": len(rules),
        "fixes": len(fixes),
        "introducers": bug_judged,
        "caught": len(catches),
        "caught_binding": len(binding),
        "clean": clean_judged,
        "clean_fired": clean_fired,
        "catches": [asdict(c) for c in catches],
        "shallow": bool(boundary),
    }


def rate(n: int, d: int) -> str:
    return f"{n}/{d} ({round(100 * n / d)}%)" if d else "0/0"
