"""A small agent loop, so the gate has a real place to stand and the benchmark
is reproducible. Four tools, JSON actions, one interception point.

Arms:  A - no memory at all
       B - persuasive prose in the system prompt (how advisory memory layers work)
       C - binding precedent, enforced
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .change import Change
from .db import Ledger
from .harvest import RunWatch, command_fail
from . import artifacts, gate, overrule, provider, recall, record, render, shell

SYSTEM = """You are editing a small codebase. Reply with ONE JSON action, nothing else:
{"tool":"list_files"}
{"tool":"read_file","path":"..."}
{"tool":"write_file","path":"...","content":"..."}
{"tool":"run","cmd":"..."}
{"tool":"done"}
Write whole files, never fragments. Finish with done only when the task is complete."""


@dataclass
class Step:
    action: dict
    result: str


@dataclass
class Result:
    run_id: int
    arm: str
    passed: bool
    blocked: int = 0
    steps: list[Step] = field(default_factory=list)
    edits: dict[str, str] = field(default_factory=dict)
    fired: list[int] = field(default_factory=list)
    before: dict = field(default_factory=dict)
    watch: RunWatch | None = None
    commands: list[str] = field(default_factory=list)


class Escaped(Exception):
    """The agent named a path outside the repository it was given."""


def _inside(repo: Path, path: str) -> Path:
    """Resolve a path the MODEL chose, and refuse anything outside the repo.

    `repo / path` is not a containment check. Python replaces the base when the
    right-hand side is absolute, and `..` walks out - so one bad path from the
    model writes wherever it likes. It has: a live agent wrote `phone_verified`
    into seeds/clinic, the pristine corpus every benchmark run restores from,
    which quietly changes what every future run measures.
    """
    repo = Path(repo).resolve()
    target = (repo / path).resolve()
    if target != repo and repo not in target.parents:
        raise Escaped(path)
    return target


def _apply(repo: Path, path: str, content: str) -> None:
    p = _inside(repo, path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _oracle(repo: Path, cmd: str) -> bool:
    return shell.run(cmd, repo).returncode == 0


def run(repo: Path, task: str, led: Ledger, arm: str = "C", oracle: str = "python oracle.py",
        max_steps: int = 24, seed: int = 0, scripted: list[dict] | None = None,
        on_block=None) -> Result:
    repo = Path(repo).resolve()
    run_id = led.open_run(str(repo), task, arm=arm, model=provider.MODEL, seed=seed)
    res = Result(run_id=run_id, arm=arm, passed=False)
    watch = RunWatch()
    before = Change.snapshot(repo)
    commands: list[str] = []

    system = SYSTEM
    if arm == "B":
        # Every rule the gate would apply, not the ones a bag-of-words search
        # matched. briefing() filters on score > 0 and returns nothing when the
        # task shares no token with the rule - which makes arm B an empty prompt
        # and turns the comparison into full knowledge against no knowledge.
        rows = recall.everything(led, str(repo), task)
        if rows:
            lines_ = ["Rules this repository has learned from its own past failures.",
                      "They are not enforced. Follow them if they apply."]
            lines_ += ["- " + r["says"] for r in rows]
            system += chr(10) + chr(10) + chr(10).join(lines_)

    history: list[str] = [f"TASK: {task}"]
    script = list(scripted or [])

    for _ in range(max_steps):
        if script:
            action = script.pop(0)
        else:
            try:
                raw = provider.chat("\n\n".join(history[-8:]), system=system)
            except provider.Unavailable as e:
                res.steps.append(Step({"tool": "error"}, f"no model: {e}"))
                break
            m = re.search(r"\{.*\}", raw, re.S)
            if not m:
                history.append("Reply with one JSON action.")
                continue
            try:
                action = json.loads(m.group(0))
            except json.JSONDecodeError:
                history.append("That was not valid JSON. One JSON action only.")
                continue

        tool = action.get("tool")
        out = ""

        if tool == "list_files":
            out = "\n".join(sorted(
                str(p.relative_to(repo)).replace("\\", "/")
                for p in repo.rglob("*") if p.is_file() and ".injunct" not in p.parts
                and "__pycache__" not in p.parts))
        elif tool == "read_file":
            try:
                f = _inside(repo, action.get("path", ""))
            except Escaped as e:
                out = f"{e} is outside this repository"
            else:
                out = (f.read_text(encoding="utf-8", errors="replace")
                       if f.is_file() else "no such file")
        elif tool == "write_file":
            path, content = action.get("path", ""), action.get("content", "")
            try:
                _apply(repo, path, content)
            except Escaped as e:
                # Told, not silently dropped: the model can correct itself, and
                # the step is on the record rather than looking like a write.
                out = f"refused: {e} is outside this repository"
                res.steps.append(Step(action, out))
                history.append(out)
                continue
            res.edits[path] = content
            watch.note_write(path, content)
            out = f"wrote {path}"
            if arm == "C":
                verdicts = gate.evaluate(led, str(repo), Change.since(repo, before, commands))
                if verdicts:
                    res.blocked += 1
                    res.fired += [v.holding_id for v in verdicts]
                    out = "BLOCKED BY INJUNCT. " + " ".join(
                        f"{v.says} Rule: {v.rule}. Reason: {v.reason}." for v in verdicts)
                    if on_block:
                        script[:0] = on_block(verdicts)
        elif tool == "run":
            cmd = action.get("cmd", "")
            commands.append(cmd)
            r = shell.run(cmd, repo)
            out = (r.stdout + r.stderr)[-1500:] or f"exit {r.returncode}"
            watch.note_test(r.returncode == 0)
        elif tool == "done":
            if arm == "C":
                verdicts = gate.evaluate(led, str(repo), Change.since(repo, before, commands))
                if verdicts:
                    res.blocked += 1
                    res.fired += [v.holding_id for v in verdicts]
                    out = "NOT DONE. BLOCKED BY INJUNCT. " + " ".join(
                        f"{v.says} Rule: {v.rule}." for v in verdicts)
                    res.steps.append(Step(action, out))
                    history.append(f"{json.dumps(action)}\n{out}")
                    continue
            res.steps.append(Step(action, "done"))
            break
        else:
            out = "unknown tool"

        res.steps.append(Step(action, out))
        history.append(f"{json.dumps(action)}\n{out[:1200]}")

    ch = Change.since(repo, before, commands)
    res.before = before
    res.watch = watch
    res.commands = commands
    res.passed = _oracle(repo, oracle)

    if res.passed:
        record.record_success(led, run_id, str(repo), ch)
    else:
        led.close_run(run_id, "fail")

    for hid in set(res.fired):
        overrule.record_outcome(led, run_id, hid, complied=res.blocked > 0, passed=res.passed)

    return res


def register_failure(repo: Path, led: Ledger, res: Result, oracle: str = "python oracle.py",
                     use_model: bool = True) -> dict:
    """Turn a failed run into precedent. Postflight, exactly as it would happen live."""
    ch = Change.since(Path(repo), res.before, res.commands)
    return record.file_case(led, res.run_id, str(Path(repo).resolve()),
                            command_fail(oracle, "the oracle rejected the working tree"),
                            ch, use_model=use_model)
