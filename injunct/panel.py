"""Every rule's decision about the current change - not only the ones that fire.

`gate.evaluate` answers one question: does anything stop this? That is what an
agent needs. It is not what a person watching needs, because a screen that only
ever shows failures cannot show a change being cleared, and a rule that stayed
silent is as informative as one that did not.

So this returns the whole panel: every rule, what it looked at, and what it
decided. Nothing here calls a model; each verdict is a deterministic function of
the working tree.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from .change import Change
from .db import Ledger
from . import nextstep, templates

CLEAR, NOTE, HALT, SKIP = "clear", "note", "halt", "skip"

# The grouping a person reads, rather than the template name a machine needs.
DOMAIN = {
    "co_change": "structure", "must_run": "structure", "required_command": "structure",
    "forbidden_edit": "structure", "regression_test": "tests",
    "must_not_appear": "hygiene", "must_not_remove": "tests", "must_appear": "hygiene",
    "blast_radius": "context", "no_quadratic": "cost", "sleeper_gate": "borrowed", "forge_gate": "borrowed",
    "prose": "advice",
}


@dataclass
class Seat:
    holding_id: int
    template: str
    domain: str
    says: str
    status: str            # binding | persuasive
    verdict: str           # clear | note | halt | skip
    reason: str = ""
    next: str = ""
    took_ms: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Sitting:
    """One evaluation of one working tree, in full."""
    touched: list[str] = field(default_factory=list)
    seats: list[Seat] = field(default_factory=list)
    at: float = 0.0

    @property
    def halted(self) -> bool:
        return any(s.verdict == HALT for s in self.seats)

    @property
    def notes(self) -> list[Seat]:
        return [s for s in self.seats if s.verdict == NOTE]

    def as_dict(self) -> dict:
        return {"at": self.at, "touched": self.touched, "halted": self.halted,
                "seats": [s.as_dict() for s in self.seats]}


def sit(led: Ledger, repo: str, ch: Change, borrowed: list[dict] | None = None) -> Sitting:
    """Put the change in front of every rule and record what each one says."""
    out = Sitting(touched=list(ch.touched), at=time.time())
    holdings = list(led.holdings(repo=repo)) + list(borrowed or [])

    for h in holdings:
        if h["status"] not in ("binding", "persuasive"):
            continue                                   # overruled and retired do not sit
        t0 = time.perf_counter()
        try:
            reason = templates.fires(h["template"], h["params"], ch)
            verdict = (HALT if h["status"] == "binding" else NOTE) if reason else CLEAR
        except Exception as e:                         # a broken rule must not stop the panel
            reason, verdict = f"could not be evaluated: {e}", SKIP
        took = int((time.perf_counter() - t0) * 1000)

        seat = Seat(holding_id=h["id"], template=h["template"],
                    domain=DOMAIN.get(h["template"], "other"),
                    says=h["says"], status=h["status"], verdict=verdict,
                    reason=reason or "", took_ms=took)
        if verdict == HALT:
            seat.next = nextstep.suggest(
                type("V", (), {"template": h["template"],
                               "rule": templates.render(h["template"], h["params"])})(),
                Path(repo), ch.touched)
        out.seats.append(seat)

    order = {HALT: 0, NOTE: 1, SKIP: 2, CLEAR: 3}
    out.seats.sort(key=lambda s: (order[s.verdict], s.domain, s.holding_id))
    return out
