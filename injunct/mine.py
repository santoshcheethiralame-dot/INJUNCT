"""What this repository already knows about itself.

An empty ledger is useless on day one, and a solo developer will not wait to
fail four times before the tool earns its place. Every repository already
carries its own conventions in two places nobody reads: its commit history, and
whatever it declares to its own CI.

The naive version of this does not work. "These two directories always change
together" is true of every pair in a repository whose first commit added
everything, and it is equally true in both directions when two things genuinely
move as one. Both failures were measured before this was written.

So a pairing has to survive three tests:

  support     seen together often enough to be a habit, not a coincidence
  confidence  P(B | A) - touching A really does mean touching B
  asymmetry   P(A | B) is LOW - otherwise the two simply move together and the
              data cannot tell you which one is the trigger

The last one is the interesting one, and it is also the fix for the only
false positive the benchmark could not explain.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .compiler import _required, _units
from .shell import run as sh

MAX_FILES = 12       # a commit that touches everything says nothing about anything
MIN_SUPPORT = 4      # a habit, not a coincidence
MIN_CONFIDENCE = 0.85
MAX_REVERSE = 0.60   # above this the pairing is symmetric and direction is a guess


def commits(repo: Path, limit: int = 600) -> list[list[str]]:
    """File lists, newest first, one per commit."""
    out = sh(f'git log -{limit} --name-only --pretty=format:%H', repo).stdout
    got: list[list[str]] = []
    files: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        if len(line) == 40 and " " not in line:
            if files:
                got.append(files)
            files = []
        else:
            files.append(line.replace("\\", "/"))
    if files:
        got.append(files)
    return got


def pairings(history: list[list[str]], max_files: int = MAX_FILES,
             min_support: int = MIN_SUPPORT, min_confidence: float = MIN_CONFIDENCE,
             max_reverse: float = MAX_REVERSE) -> list[dict]:
    """Directory pairings that survive all three tests."""
    seen: Counter = Counter()
    together: Counter = Counter()
    used = 0
    for files in history:
        if len(files) > max_files:
            continue
        u = _units(files)
        used += 1
        for a in u:
            seen[a] += 1
            for b in u:
                if a != b:
                    together[(a, b)] += 1

    rules = []
    for (a, b), n in together.items():
        confidence = n / seen[a]
        reverse = n / seen[b]
        if n >= min_support and confidence >= min_confidence and reverse <= max_reverse:
            trigger = f"{a.rstrip('/')}/*" if a.endswith("/") else a
            rules.append({
                "template": "co_change",
                "params": {"trigger": trigger, "required": _required(b)},
                "says": f"Changing {trigger} means changing {b} too.",
                "evidence": {"support": n, "confidence": round(confidence, 2),
                             "reverse": round(reverse, 2), "commits": used},
            })
    rules.sort(key=lambda r: (-r["evidence"]["support"], r["params"]["trigger"]))
    return rules


HOOK_ID = re.compile(r"^\s*-?\s*id:\s*(\S+)", re.M)
HOOK_ENTRY = re.compile(r"^\s*entry:\s*(.+)$", re.M)
HOOK_FILES = re.compile(r"^\s*files:\s*(.+)$", re.M)


def declared(repo: Path) -> list[dict]:
    """What the repo already tells its own CI to do.

    Only pre-commit hooks that name the files they apply to are used. A hook
    with no `files:` pattern would become a rule that fires on every change,
    which is not a rule, it is a nag.
    """
    cfg = Path(repo) / ".pre-commit-config.yaml"
    if not cfg.is_file():
        return []
    text = cfg.read_text(encoding="utf-8", errors="replace")
    out = []
    for block in text.split("- id:")[1:]:
        block = "- id:" + block
        ident = HOOK_ID.search(block)
        files = HOOK_FILES.search(block)
        if not ident or not files:
            continue
        entry = HOOK_ENTRY.search(block)
        cmd = (entry.group(1) if entry else ident.group(1)).strip().strip("'\"")
        pattern = files.group(1).strip().strip("'\"")
        glob = _pattern_to_glob(pattern)
        if not glob:
            continue
        out.append({
            "template": "required_command",
            "params": {"glob": glob, "cmd": cmd},
            "says": f"After changing {glob}, `{cmd}` has to pass.",
            "evidence": {"declared_in": ".pre-commit-config.yaml"},
        })
    return out


def _pattern_to_glob(pattern: str) -> str | None:
    """pre-commit `files:` is a regex. Only the simple shapes are worth reading."""
    m = re.fullmatch(r"\^?\(?([\w/]+)/\)?\.\*", pattern)
    if m:
        return f"{m.group(1)}/**"
    m = re.search(r"\\.(\w+)\$?$", pattern)
    if m:
        return f"*.{m.group(1)}"
    return None


def propose(repo: Path, limit: int = 600) -> list[dict]:
    """Everything this repository can tell us before anything has gone wrong."""
    return pairings(commits(Path(repo), limit)) + declared(Path(repo))


def record_history(repo: Path, led, limit: int = 40) -> int:
    """File the repo's own commits as past runs that succeeded.

    A commit that landed is the best evidence a repository has of work that
    went right. With these on the ledger, a mined rule can be empanelled
    against them ("0/40 false on past commits"), and a rule learned later has
    a history to be tested against on day one instead of after forty runs.
    Commands are unknown for a commit, so command-aware checks abstain on
    these rather than judge on absent evidence. Idempotent per commit.
    """
    from . import artifacts
    from .change import Change
    repo = Path(repo).resolve()
    log = sh(f'git log -{limit} --no-merges --pretty=format:%H%x09%s', repo).stdout
    # A commit coverage set aside as `fixed-later` is still recorded; it must
    # not come back as a fresh success the next time history is read.
    have = {r["task"] for r in led.successful_runs(str(repo), limit=10_000)} | {
        r["task"] for r in led.con.execute(
            "SELECT task FROM runs WHERE repo=? AND result='fixed-later'", (str(repo),))}
    n = 0
    for line in reversed(log.splitlines()):          # oldest first, so ids read in order
        if chr(9) not in line:
            continue
        sha, subject = line.split(chr(9), 1)
        task = f"commit {sha[:7]}: {subject}"
        if task in have:
            continue
        names = [x.replace("\\", "/") for x in
                 sh(f"git show --name-only --pretty=format: {sha}", repo).stdout.splitlines() if x.strip()]
        if not names or len(names) > MAX_FILES:
            continue
        added: dict[str, list[str]] = {}
        removed: dict[str, list[str]] = {}
        cur = None
        for raw in sh(f"git show -U0 --pretty=format: --no-color {sha}", repo).stdout.splitlines():
            if raw.startswith("+++ b/"):
                cur = raw[6:].replace("\\", "/"); added.setdefault(cur, []); removed.setdefault(cur, [])
            elif raw.startswith("--- ") or raw.startswith("diff --git") or raw.startswith("@@"):
                continue
            elif cur and raw.startswith("+"):
                added[cur].append(raw[1:])
            elif cur and raw.startswith("-"):
                removed[cur].append(raw[1:])
        run_id = led.open_run(str(repo), task, arm="history")
        led.close_run(run_id, "pass")
        artifacts.save(repo, run_id, Change(repo=repo, touched=sorted(names), added=added,
                                             removed=removed, commands=None))
        n += 1
    return n


def history_state(repo) -> str:
    """Why `init` found nothing - the three answers need different next steps."""
    from pathlib import Path as _P
    from . import shell
    repo = _P(repo)
    if not (repo / ".git").exists():
        r = shell.run("git rev-parse --git-dir", repo)
        if r.returncode != 0:
            return "not-a-repo"
    r = shell.run("git rev-list --count HEAD", repo)
    if r.returncode != 0 or not (r.stdout or "").strip().isdigit():
        return "no-commits"
    return "thin" if int(r.stdout.strip()) < 20 else "no-habit"
