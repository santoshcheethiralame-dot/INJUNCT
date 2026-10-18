"""Enforcement. A binding holding either fires on this working tree or it does not."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .change import Change
from .db import Ledger
from . import templates


@dataclass
class Verdict:
    holding_id: int
    case_id: int
    says: str
    rule: str
    reason: str
    template: str
    cited: int
    empanel: dict
    established: float


def evaluate(led: Ledger, repo: str, ch: Change,
             borrowed: list[dict] | None = None) -> list[Verdict]:
    """Every binding holding that fires. Empty list means the tree is clear.

    `borrowed` carries precedent established in *other* repositories that has
    been seen often enough to travel. It is evaluated the same way; nothing
    about the gate cares where a rule came from.
    """
    out: list[Verdict] = []
    local = led.holdings(repo=repo, status="binding")
    for h in local + [b for b in (borrowed or []) if b["status"] == "binding"]:
        reason = templates.fires(h["template"], h["params"], ch)
        if reason:
            out.append(Verdict(
                holding_id=h["id"], case_id=h["case_id"], says=h["says"],
                rule=templates.render(h["template"], h["params"]), reason=reason,
                template=h["template"], cited=len(led.citations(h["id"])),
                empanel=h["empanel"], established=h["established"],
            ))
    return out


def advisories(led: Ledger, repo: str) -> list[dict]:
    """Persuasive authority: prose, clearly labelled as the weaker tier."""
    return led.holdings(repo=repo, status="persuasive")


def firing_advice(led: Ledger, repo: str, ch: Change) -> list[Verdict]:
    """Advisory holdings that actually fire on this tree.

    These never change the exit code. But a rule nobody sees until it is
    binding teaches nobody anything - someone who just deleted a test should be
    told, and then left to decide.
    """
    out = []
    for h in led.holdings(repo=repo, status="persuasive"):
        reason = templates.fires(h["template"], h["params"], ch)
        if reason:
            out.append(Verdict(
                holding_id=h["id"], case_id=h["case_id"], says=h["says"],
                rule=templates.render(h["template"], h["params"]), reason=reason,
                template=h["template"], cited=len(led.citations(h["id"])),
                empanel=h["empanel"], established=h["established"],
            ))
    return out


def check(repo: Path, led: Ledger | None = None) -> tuple[list[Verdict], Change]:
    from .db import ledger_path
    repo = Path(repo).resolve()
    led = led or Ledger(ledger_path(repo))
    ch = Change.from_git(repo)
    from . import transfer
    return evaluate(led, str(repo), ch, borrowed=transfer.borrowed(str(repo))), ch
