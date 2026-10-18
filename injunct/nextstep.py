"""Turn a verdict into an instruction the agent can actually execute.

A halt that says "do the missing work" is a verdict. A halt that says
"create migrations/002_phone_verified.sql" is an instruction. Small models act
on the second and stall on the first - and an agent that stalls after a block
has been stopped without being improved, which is the whole point missed.

The suggestion is derived from the repository, never invented: the naming
convention comes from the files already sitting in the required directory.
"""
from __future__ import annotations

import re
from pathlib import Path


def _required_glob(rule: str) -> str:
    if "->" in rule:
        return rule.split("->", 1)[1].strip(" )")
    if "(" in rule and ":" in rule:
        return rule.split("(", 1)[1].split(":")[0].strip(" )")
    return ""


def _trigger_glob(rule: str) -> str:
    if "(" in rule and "->" in rule:
        return rule.split("(", 1)[1].split("->", 1)[0].strip()
    return ""


def _command(rule: str) -> str:
    if "(" in rule and ":" in rule:
        return rule.rsplit(":", 1)[1].strip(" )")
    return ""


def _dir_of(glob: str) -> str:
    return glob.split("*", 1)[0].rstrip("/")


def _generator_named_in(path: Path) -> str | None:
    """'GENERATED FILE - run tools/gen.py' in a file's first lines is the
    repository telling us what to do; we only read it back."""
    from .compiler import GEN_CMD, GEN_MARKER
    try:
        head = chr(10).join(path.read_text(encoding="utf-8", errors="replace").splitlines()[:6])
    except OSError:
        return None
    if not GEN_MARKER.search(head):
        return None
    for tok in GEN_CMD.findall(head):
        if tok != path.name and "/" in tok:
            return tok
    return None


def _slug(touched: list[str], trigger: str = "") -> str:
    """Name the work after what the agent actually changed.

    After the file that tripped the rule, that is - not whatever else happens
    to be dirty. With `.claude/settings.json` uncommitted the card once asked
    for `003_settings.sql`; the agent had touched the patient model.
    """
    from fnmatch import fnmatch
    hit = [p for p in touched if trigger and fnmatch(p, trigger)]
    for p in hit + [p for p in touched if p not in hit]:
        stem = Path(p).stem
        if stem not in ("__init__", "index"):
            return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    return "change"


def _next_numbered(existing: list[str]) -> str | None:
    """Follow the convention already in the directory, if there is one."""
    nums = []
    width = 3
    for name in existing:
        m = re.match(r"^(\d+)[_-]", name)
        if m:
            nums.append(int(m.group(1)))
            width = len(m.group(1))
    return f"{max(nums) + 1:0{width}d}" if nums else None


def suggest(verdict, repo: Path, touched: list[str]) -> str:
    """One concrete next action, or "" when the repo cannot tell us one."""
    repo = Path(repo)
    template = getattr(verdict, "template", "")
    rule = getattr(verdict, "rule", "")

    if template in ("required_command", "must_run"):
        cmd = _command(rule)
        return f"run `{cmd}` and make it pass" if cmd else ""

    if template == "forbidden_edit":
        return "revert that file and change the source it is generated from instead"

    if template == "co_change":
        glob = _required_glob(rule)
        # the companion is one file, not a folder: registry.py, a lockfile
        if "*" not in glob and (repo / glob).is_file():
            return f"add {_slug(touched, _trigger_glob(rule))} to {glob}"
        d = _dir_of(glob)
        if not d:
            return ""
        folder = repo / d
        existing = sorted(p.name for p in folder.glob("*") if p.is_file()) \
            if folder.is_dir() else []
        # a companion that says it is generated names its own next step
        for name in existing:
            gen = _generator_named_in(folder / name)
            if gen:
                return f"run `{gen}` to regenerate {d}/{name}"
        ext = Path(existing[-1]).suffix if existing else ""
        nxt = _next_numbered(existing)
        slug = _slug(touched, _trigger_glob(rule))
        if nxt:
            return f"create {d}/{nxt}_{slug}{ext}"
        if existing:
            return f"create {d}/{slug}{ext}"
        return f"add the matching change under {d}/"

    # These two knew what was wrong and said nothing about what to do, which is
    # the half our own numbers say actually moves an agent. Both instructions
    # are read back out of the verdict's own reason - the caller list came from
    # the call graph, the location from the finding - so neither is invented.
    if template == "blast_radius":
        reason = getattr(verdict, "reason", "")
        name = reason.split("(", 1)[0].strip() if "(" in reason else ""
        who = reason.split("updated:", 1)[1].strip() if "updated:" in reason else ""
        if who:
            call = f"{name}()" if name else "the signature you changed"
            return f"update the callers of {call} that have not moved: {who}"
        return "update every caller of the signature you changed"

    if template == "no_quadratic":
        reason = getattr(verdict, "reason", "")
        where = reason.split(" line ", 1)[0].strip()
        fix = reason.rsplit(";", 1)[1].strip() if ";" in reason else ""
        if where and fix:
            return f"in {where}, {fix}"
        return "do that work once outside the loop"

    return ""
