"""Turn a case into a holding.

The model's only job is to pick one of six templates and fill its blanks. It
never writes a checker, because a small free model fills a schema reliably and
writes novel code badly. With no model reachable, an evidence-driven fallback
reads the failure text for the paths it names. Anything that does not validate
becomes persuasive prose instead.
"""
from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from .change import Change
from . import provider, templates

SYSTEM = """You convert one coding-agent failure into a single reusable check.
Reply with JSON only, no prose, no code fences:
{"template": "...", "params": {...}, "says": "one plain sentence, under 12 words"}

Templates and their params:
  co_change        {"trigger": glob, "required": glob}   - touching trigger requires touching required
  required_command {"glob": glob, "cmd": shell}          - after touching glob, cmd must exit 0
  forbidden_edit   {"glob": glob}                        - never edit this
  must_not_appear  {"regex": re, "glob": glob}           - banned pattern in added lines
  must_appear      {"regex": re, "glob": glob}           - required pattern in the file
  regression_test  {"path": path}                        - this test must pass

Rules: globs are repo-relative and use * and **. Prefer the narrowest rule that
would have caught this exact failure. If none fit, reply {"template": null}."""


def _globify(path: str) -> str:
    p = Path(path)
    return f"{p.parent.as_posix()}/*{p.suffix}" if p.parent.as_posix() not in (".", "") else f"*{p.suffix}"


def _paths_named(text: str) -> list[str]:
    return re.findall(r"[\w.*-]+/[\w./*-]*|[\w*-]+\.\w+", text or "")


GEN_MARKER = re.compile(r"generated|auto-?generated|do not edit", re.I)
GEN_CMD = re.compile(r"[\w./-]+\.(?:py|sh|js|ts|mjs)")


def _generator_of(ch: Change, path: str) -> str | None:
    """A generated file usually says so, and says what makes it.

    'GENERATED FILE - run tools/gen.py, do not edit by hand' is evidence, not a
    convention we invented: the rule comes out of the repository's own words.
    """
    head = chr(10).join(ch.text(path).splitlines()[:6])
    if not GEN_MARKER.search(head):
        return None
    for tok in GEN_CMD.findall(head):
        if tok != path:
            return tok
    return None


def _units(paths: list[str]) -> set[str]:
    """A top-level directory, or a root-level file - both are things that move together."""
    return {(p.split("/", 1)[0] + "/") if "/" in p else p for p in paths}


def _required(unit: str) -> str:
    return f"{unit}**" if unit.endswith("/") else unit


def history_pairs(past: list[Change]) -> dict[str, set[str]]:
    """Directories that past *successful* runs never changed alone.

    This is learned from the repo's own history, not a table someone wrote.
    """
    seen: dict[str, list[set[str]]] = {}
    for c in past:
        ds = _units(c.touched)
        for d in ds:
            seen.setdefault(d, []).append(ds - {d})
    return {d: set.intersection(*obs) for d, obs in seen.items() if obs and set.intersection(*obs)}


def fallback(case: dict, ch: Change, past: list[Change] | None = None) -> tuple[str | None, dict, str]:
    """Evidence-driven, deterministic, no model required."""
    units = _units(ch.touched)
    # A hand-edited generated file touches exactly the path a regeneration would.
    # No structural rule separates them; whether the generator ran does.
    #
    # The rule names the one file whose own header declared it generated, not
    # _globify'd to its whole directory. The evidence is that file's words, and
    # widening it to client/*.py is what let this rule fire on a task that had
    # merely touched something else in the same folder.
    for path in ch.touched:
        gen = _generator_of(ch, path)
        if gen and not any(gen in c for c in (ch.commands or [])):
            return "must_run", {"glob": path, "cmd": gen}, \
                f"{path} is generated. Run {gen} instead of editing it."

    # A signature that moved without its callers. This asks the semantic
    # question rather than the path one - "did you finish the job?" instead of
    # "did the other folder move?" - so it is checked before the co-occurrence
    # rules, which would otherwise answer a narrower question first and hide it.
    #
    # Deliberately narrow: it proposes nothing unless a name really did change
    # shape AND real callers really were left behind, both read out of the tree.
    if templates.fires("blast_radius", {}, ch):
        return "blast_radius", {}, \
            "A function that changed shape is not finished until its callers move."

    # A cost regression in the lines this change ADDED. Same restraint: the
    # finding has to be in new code, so a repository full of existing nested
    # loops never becomes this change's fault.
    for path in ch.touched:
        if not path.endswith(".py"):
            continue
        glob = _globify(path)
        if templates.fires("no_quadratic", {"glob": glob}, ch):
            return "no_quadratic", {"glob": glob}, \
                f"Work added under {glob} has to stay linear in its input."

    # Correlation is not direction, and this path cannot fix that.
    #
    # mine.pairings settles direction with an asymmetry test, and it works on
    # real history: caliper's results/ -> docs/ has reverse confidence 20%.
    # It CANNOT be used here. In a run's own short history nothing ever moves
    # alone - in the benchmark, migrations/ never once changes without models/,
    # so reverse confidence is 100% and the test would reject the single most
    # useful rule the system has. Measured, not assumed.
    #
    # So this stays first-match on co-occurrence, and docs/ -> registry.py
    # stays a known false positive. The evidence that would refute it is
    # evidence these runs do not produce.
    for d, partners in sorted(history_pairs(past or []).items()):
        missing = partners - units
        if d in units and missing:
            e = sorted(missing)[0]
            hit = next((t for t in ch.touched if t.startswith(d.rstrip("/"))), d)
            trig = _globify(hit) if "/" in hit else hit
            return "co_change", {"trigger": trig, "required": _required(e)},                 f"Changing {trig} means changing {e} too."

    detail = case.get("detail") or ""
    try:
        hint = json.loads(detail) if detail.strip().startswith("{") else {}
    except json.JSONDecodeError:
        hint = {}

    if hint.get("cmd") and ch.touched:
        glob = _globify(ch.touched[0])
        return "required_command", {"glob": glob, "cmd": hint["cmd"]}, \
            f"After changing {glob}, `{hint['cmd']}` has to pass."

    blob = f"{case.get('summary','')} {detail}"
    for tok in _paths_named(blob):
        if not tok.endswith("/"):
            continue
        if any(fnmatch.fnmatch(t, f"{tok}*") for t in ch.touched):
            continue
        if ch.touched:
            trig = _globify(ch.touched[0])
            return "co_change", {"trigger": trig, "required": f"{tok}**"}, \
                f"Changing {trig} means changing {tok} too."
    return None, {}, (case.get("summary") or "This has gone wrong here before.")


def compile_case(case: dict, ch: Change, use_model: bool = True,
                 past: list[Change] | None = None) -> tuple[str | None, dict, str]:
    if use_model:
        prompt = json.dumps({
            "task_failure": case.get("summary", ""),
            "detail": (case.get("detail") or "")[:1500],
            "files_the_agent_touched": ch.touched[:25],
        }, indent=2)
        try:
            raw = provider.chat(prompt, system=SYSTEM)
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                d = json.loads(m.group(0))
                t, p = d.get("template"), d.get("params") or {}
                if t and templates.valid(t, p):
                    says = (d.get("says") or "").strip() or f"{t} was violated here before."
                    return t, p, says
        except (provider.Unavailable, json.JSONDecodeError, AttributeError):
            pass
    return fallback(case, ch, past)
