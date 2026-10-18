"""The eight things a holding is allowed to be.

The LLM never writes a checker. It picks one of these and fills the blanks, so
every verdict in the system is a deterministic function of the working tree.
"""
from __future__ import annotations

import fnmatch
import re
from typing import Callable

from .change import Change


def _braces(pattern: str) -> list[str]:
    """fnmatch has no brace expansion, so `*.{js,ts}` matches literally nothing."""
    i = pattern.find("{")
    if i == -1:
        return [pattern]
    j = pattern.find("}", i)
    if j == -1:
        return [pattern]
    head, body, tail = pattern[:i], pattern[i + 1:j], pattern[j + 1:]
    return [v for opt in body.split(",") for v in _braces(head + opt.strip() + tail)]


def _variants(pattern: str) -> list[str]:
    """`**/*.py` has to match `app.py` as well as `src/app.py`.

    fnmatch reads `**/` as requiring a slash, so a pattern written the way every
    tool writes it silently skips every file at the repository root - which is
    where app.py, main.py and index.ts usually live.
    """
    out = []
    for pat in _braces(pattern):
        out += [pat, f"{pat.rstrip('/')}/**"]
        if pat.startswith("**/"):
            out.append(pat[3:])
    return out


def _hits(paths: list[str], pattern: str) -> list[str]:
    pats = _variants(pattern)
    return [p for p in paths if any(fnmatch.fnmatch(p, q) for q in pats)]


# Each check returns None when it is satisfied, or a one-line reason when it fires.

def co_change(ch: Change, p: dict) -> str | None:
    trig, req = p["trigger"], p["required"]
    if _hits(ch.touched, trig) and not _hits(ch.touched, req):
        return f"{', '.join(_hits(ch.touched, trig))} changed, nothing under {req} did"
    return None


def required_command(ch: Change, p: dict) -> str | None:
    if _hits(ch.touched, p["glob"]) and ch.run(p["cmd"]) != 0:
        return f"`{p['cmd']}` fails after touching {p['glob']}"
    return None


def forbidden_edit(ch: Change, p: dict) -> str | None:
    hit = _hits(ch.touched, p["glob"])
    return f"{', '.join(hit)} may not be edited" if hit else None


def must_not_appear(ch: Change, p: dict) -> str | None:
    rx = re.compile(p["regex"])
    for path in _hits(ch.touched, p["glob"]):
        for line in ch.added.get(path, []):
            if rx.search(line):
                return f"{path} adds a line matching /{p['regex']}/"
    return None


def must_not_remove(ch: Change, p: dict) -> str | None:
    """Deleting the thing that was failing is the oldest trick there is."""
    rx = re.compile(p["regex"])
    for path in _hits(ch.touched, p["glob"]):
        for line in (ch.removed or {}).get(path, []):
            if rx.search(line):
                return f"{path} deletes a line matching /{p['regex']}/"
    return None


def blast_radius(ch: Change, p: dict) -> str | None:
    """You changed the shape of a function. Who else calls it?

    Path-based rules ask whether the other directory moved. This asks the
    semantic question, and it is the one nobody checks: a signature change is
    only finished when its callers are.

    Known limitation, found by its own benchmark fixture and left visible
    rather than quietly worked around: a parameter added WITH a default is
    backward compatible, and existing callers do not have to move - but the
    `def` line still changed, so this fires anyway. It over-blocks that case.
    Fixing it means parsing the parameter list and comparing defaults, which
    is a change to a check the published numbers were measured on, so it is
    written down here instead of slipped in.
    """
    from . import graph

    limit = int(p.get("max_untouched", 0))
    changed = graph.changed_signatures(ch)
    if not changed:
        return None
    touched = set(ch.touched)
    for name in sorted(changed):
        others = graph.callers(ch.repo, name, exclude=touched)
        if len(others) > limit:
            shown = ", ".join(others[:3]) + (" and more" if len(others) > 3 else "")
            return (f"{name}() changed shape; {len(others)} caller(s) were not "
                    f"updated: {shown}")
    return None


def no_quadratic(ch: Change, p: dict) -> str | None:
    """Cost regressions in the code the agent just wrote.

    Only lines this change ADDED are reported. A repository full of existing
    nested loops is not this change's fault, and a gate that blames you for
    code you did not touch gets switched off within the hour.
    """
    from . import efficiency

    for path in _hits(ch.touched, p.get("glob", "**/*.py")):
        added = set(ch.added.get(path, []))
        if not added:
            continue
        try:
            src = ch.text(path)
        except Exception:
            continue
        lines = src.splitlines()
        for finding in efficiency.findings(src):
            try:
                n = int(finding.split(":", 1)[0].split()[-1])
            except (ValueError, IndexError):
                continue
            if 1 <= n <= len(lines) and lines[n - 1] in added:
                return f"{path} {finding}"
    return None


def forge_gate(ch: Change, p: dict) -> str | None:
    """Dangerous constructs in the code this change ADDED, read off the syntax
    tree instead of matched as text.

    Borrowed from forge, the sibling project where an agent writes its own
    tools. Before forge keeps a tool it asks whether the code is doing anything
    it should not be allowed to do, and it asks by parsing rather than by
    grepping - because `eval` inside a string, a comment, or a variable called
    `evaluate` all match a regex and none of them are a call to eval.

    We had two regexes doing this job badly. This uses forge's own list of
    names, so if forge learns about a new one, so do we.

    It reports only what this change introduced. A repository that already
    contains an eval is not this change's fault, and a gate that blames you for
    code you did not touch gets switched off within the hour.
    """
    import ast
    import sys

    from . import packs

    home = packs.forge_home()
    if not home:
        return None                      # not installed: abstain, do not guess
    if str(home) not in sys.path:
        sys.path.insert(0, str(home))
    try:
        from forge import safety
    except Exception:
        return None

    banned = set(getattr(safety, "BANNED_NAMES", ()))
    allowed_dunders = set(getattr(safety, "ALLOWED_DUNDERS", ()))
    # forge forbids `open` in a generated tool because a tool has no business
    # touching the disk. Ordinary application code opens files all day, so that
    # one is dropped rather than inherited - a borrowed rule still has to make
    # sense where it is being applied.
    banned -= {"open", "input"}
    if not banned:
        return None

    for path in _hits(ch.touched, p.get("glob", "**/*.py")):
        added = set(ch.added.get(path, []))
        if not added:
            continue
        try:
            tree = ast.parse(ch.text(path))
        except SyntaxError:
            continue
        lines = ch.text(path).splitlines()
        for node in ast.walk(tree):
            n = getattr(node, "lineno", 0)
            if not (1 <= n <= len(lines)) or lines[n - 1] not in added:
                continue
            if isinstance(node, ast.Name) and node.id in banned:
                return f"{path}:{n} calls {node.id}()"
            if (isinstance(node, ast.Attribute) and node.attr.startswith("__")
                    and node.attr.endswith("__") and node.attr not in allowed_dunders):
                return f"{path}:{n} reaches into {node.attr}"
    return None


SLEEPER_DEADLINE = 4.0


def sleeper_gate(ch: Change, p: dict) -> str | None:
    """Borrow a sibling tool's judgement instead of reimplementing it.

    sleeper already decides what a coding agent may believe and ship - what it
    imports, what it claims about cost, whether the docs still match, whether
    the function already exists. Those are five detectors we do not need to
    build twice.

    If sleeper is not installed the check ABSTAINS. A gate that fires because a
    dependency is missing is a gate that fires on everything.
    """
    import json as _json
    import shutil

    from . import shell

    gate_name = p.get("gate", "deps")
    files = [f for f in _hits(ch.touched, p.get("glob", "**/*.py"))]
    if not files or not shutil.which("python"):
        return None

    from . import packs
    home = packs.sleeper_home()
    # A gate sits in front of a write, so it has to answer in the time a person
    # will wait. This one starts another Python process, and with four sleeper
    # rules installed a single change took forty seconds to judge - long enough
    # that the demo timed out and an agent would simply stall. Abstaining is
    # already what this check does when it cannot answer; being slow is just
    # another way of not answering.
    cmd = f"python -m sleeper review {' '.join(files[:20])} --json"
    budget = float(p.get("timeout", SLEEPER_DEADLINE))
    r = (shell.run_env(cmd, ch.repo, {"PYTHONPATH": str(home)}, timeout=budget) if home
         else shell.run(cmd, ch.repo, timeout=budget))
    if r.returncode == 124:
        return None
    if r.returncode not in (0, 1) or not (r.stdout or "").strip().startswith("{"):
        return None                      # not installed, or could not answer
    try:
        data = _json.loads(r.stdout)
    except ValueError:
        return None

    # sleeper grades three ways: trusted / provisional / quarantined.
    # `quarantined` is a verdict; `provisional` means it could not confirm -
    # offline, for instance - so the caller says which bar to use.
    bar = p.get("at_least", "quarantined")
    firing = {"quarantined"} if bar == "quarantined" else {"quarantined", "provisional"}

    for f in data.get("files", []):
        for g in f.get("gates", []):
            if g.get("key") != gate_name:
                continue
            if str(g.get("status", "")).lower() in firing:
                return f"{f.get('file', '?')}: {g.get('reason') or gate_name}"
    return None


def must_appear(ch: Change, p: dict) -> str | None:
    rx = re.compile(p["regex"])
    for path in _hits(ch.touched, p["glob"]):
        if not rx.search(ch.text(path)):
            return f"{path} is missing /{p['regex']}/"
    return None


def must_run(ch: Change, p: dict) -> str | None:
    """Touching this means running that.

    A generated file is the case in point: editing it by hand and regenerating
    it touch exactly the same path, so no structural rule can tell them apart.
    The difference is whether the generator ran.

    Where commands are invisible - a bare `git` view of a tree - this abstains
    rather than guessing. A gate that fires on missing evidence is a gate that
    fires on everything.
    """
    if ch.commands is None:
        return None
    hit = _hits(ch.touched, p["glob"])
    if hit and not any(p["cmd"] in c for c in ch.commands):
        return f"{', '.join(hit)} was written by hand; `{p['cmd']}` never ran"
    return None


def regression_test(ch: Change, p: dict) -> str | None:
    if ch.run(f"python -m pytest -q {p['path']}") != 0:
        return f"the regression test {p['path']} fails"
    return None


TEMPLATES: dict[str, Callable[[Change, dict], str | None]] = {
    "co_change": co_change,
    "required_command": required_command,
    "forbidden_edit": forbidden_edit,
    "must_not_appear": must_not_appear,
    "must_not_remove": must_not_remove,
    "blast_radius": blast_radius,
    "no_quadratic": no_quadratic,
    "sleeper_gate": sleeper_gate,
    "forge_gate": forge_gate,
    "must_appear": must_appear,
    "regression_test": regression_test,
    "must_run": must_run,
}

REQUIRED_PARAMS = {
    "co_change": ("trigger", "required"),
    "required_command": ("glob", "cmd"),
    "forbidden_edit": ("glob",),
    "must_not_appear": ("regex", "glob"),
    "must_not_remove": ("regex", "glob"),
    "blast_radius": (),
    "no_quadratic": (),
    "sleeper_gate": ("gate",),
    "forge_gate": (),
    "must_appear": ("regex", "glob"),
    "regression_test": ("path",),
    "must_run": ("glob", "cmd"),
}


def render(template: str, p: dict) -> str:
    """The rule as a machine reads it, for the halt card's mono line."""
    return {
        "co_change": lambda: f"co_change( {p.get('trigger')} -> {p.get('required')} )",
        "required_command": lambda: f"required_command( {p.get('glob')} : {p.get('cmd')} )",
        "forbidden_edit": lambda: f"forbidden_edit( {p.get('glob')} )",
        "must_not_appear": lambda: f"must_not_appear( /{p.get('regex')}/ in {p.get('glob')} )",
        "must_not_remove": lambda: f"must_not_remove( /{p.get('regex')}/ in {p.get('glob')} )",
        "blast_radius": lambda: "blast_radius( callers must be updated )",
        "no_quadratic": lambda: f"no_quadratic( {p.get('glob', '**/*.py')} )",
        "sleeper_gate": lambda: f"sleeper_gate( {p.get('gate')} )",
        "forge_gate": lambda: f"forge_gate( {p.get('glob', '**/*.py')} : ast )",
        "must_appear": lambda: f"must_appear( /{p.get('regex')}/ in {p.get('glob')} )",
        "regression_test": lambda: f"regression_test( {p.get('path')} )",
        "must_run": lambda: f"must_run( {p.get('glob')} : {p.get('cmd')} )",
    }[template]()


def valid(template: str, p: dict) -> bool:
    return template in TEMPLATES and all(p.get(k) for k in REQUIRED_PARAMS[template])


# Which checks can actually reach a verdict on a given change, and which are
# only silent because the evidence they need is missing.
#
# `fires()` returns None for both, and it has to: every caller treats None as
# "nothing to say" and blocking on an abstention would fire on everything. But
# empanelment must tell them apart. A rule replayed against past runs that all
# abstained has not been tested against anything - it is unfalsifiable, not
# innocent - and promoting it is how a false positive gets the authority to
# block. So the distinction lives here, as a separate question, and nothing
# about the gate's behaviour changes.
def _judges_commands(ch: Change, p: dict) -> bool:
    return ch.commands is not None


def _judges_removals(ch: Change, p: dict) -> bool:
    return ch.removed is not None


def _judges_forge(ch: Change, p: dict) -> bool:
    from . import packs
    return packs.forge_home() is not None


def _judges_sleeper(ch: Change, p: dict) -> bool:
    from . import packs
    return packs.sleeper_home() is not None


# Only checks that ABSTAIN on missing evidence belong here. `required_command`,
# `must_appear`, `no_quadratic` and `regression_test` do reach a verdict on a
# replayed run - but they reach it by reading the working tree as it is *now*
# (ch.text, ch.run), not as it was then. That is a real and separate weakness,
# documented rather than half-fixed here: papering over it with an abstention
# would stop those rules ever binding.
JUDGEABLE: dict[str, Callable[[Change, dict], bool]] = {
    "must_run": _judges_commands,
    "must_not_remove": _judges_removals,
    "blast_radius": _judges_removals,
    "forge_gate": _judges_forge,
    "sleeper_gate": _judges_sleeper,
}


def can_judge(template: str, p: dict, ch: Change) -> bool:
    """Could this check reach a verdict on this change at all?"""
    if not valid(template, p):
        return False
    return JUDGEABLE.get(template, lambda _c, _p: True)(ch, p)


def fires(template: str, p: dict, ch: Change) -> str | None:
    if not valid(template, p):
        return None
    return TEMPLATES[template](ch, p)
