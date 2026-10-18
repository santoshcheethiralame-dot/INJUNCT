"""Free signals. A human saying no is rare; the agent contradicting itself is not."""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from .change import Change


@dataclass
class Signal:
    source: str
    confidence: str      # high signals may become binding; low ones stay persuasive
    summary: str
    detail: str = ""


@dataclass
class RunWatch:
    """What the harness (or a recorder) saw during one run."""
    writes: list[str] = field(default_factory=list)          # every path written, in order
    contents: dict[str, list[str]] = field(default_factory=dict)  # path -> successive contents
    tests: list[bool] = field(default_factory=list)          # test outcomes, in order

    def note_write(self, path: str, content: str) -> None:
        self.writes.append(path)
        self.contents.setdefault(path, []).append(content)

    def note_test(self, passed: bool) -> None:
        self.tests.append(passed)


def command_fail(cmd: str, output: str = "") -> Signal:
    return Signal("command_fail", "high", f"`{cmd}` failed after the agent went idle.",
                  json.dumps({"cmd": cmd, "output": output[:2000]}))


def human_reject(reason: str) -> Signal:
    return Signal("human_reject", "high", reason.strip() or "The change was rejected.",
                  json.dumps({"note": reason}))


def churn(watch: RunWatch, threshold: float = 0.5) -> list[Signal]:
    """A file written twice in one run, the second write undoing most of the first."""
    out = []
    for path, versions in watch.contents.items():
        if len(versions) < 2:
            continue
        a, b = set(versions[-2].splitlines()), set(versions[-1].splitlines())
        if not a:
            continue
        undone = len(a - b) / len(a)
        if undone >= threshold:
            out.append(Signal("churn", "low",
                              f"{path} was rewritten inside one run, undoing {undone:.0%} of itself.",
                              json.dumps({"path": path, "undone": round(undone, 3)})))
    return out


def revert(watch: RunWatch) -> list[Signal]:
    """Content that came back to a state it had already left."""
    out = []
    for path, versions in watch.contents.items():
        seen = Counter(versions)
        if any(c > 1 for c in seen.values()) and len(versions) > 2:
            out.append(Signal("revert", "low", f"{path} was reverted to an earlier state.",
                              json.dumps({"path": path})))
    return out


def test_flip(watch: RunWatch) -> list[Signal]:
    """Tests that were passing and are not any more."""
    for i in range(1, len(watch.tests)):
        if watch.tests[i - 1] and not watch.tests[i]:
            return [Signal("test_flip", "high",
                           "Tests were passing and the agent broke them.",
                           json.dumps({"at": i}))]
    return []


def all_signals(watch: RunWatch) -> list[Signal]:
    return churn(watch) + revert(watch) + test_flip(watch)
