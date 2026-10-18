"""The lifecycle. A precedent that keeps being wrong stops being law."""
from __future__ import annotations

from .db import Ledger

COUNTER_THRESHOLD = 3   # overridden runs that passed anyway
DEMOTE_TO = "overruled"


def record_outcome(led: Ledger, run_id: int, holding_id: int, complied: bool, passed: bool) -> str:
    outcome = f"{'complied' if complied else 'overridden'}_{'pass' if passed else 'fail'}"
    led.cite(run_id, holding_id, outcome)
    return outcome


def review(led: Ledger, holding_id: int) -> str:
    """Re-decide a holding's status from its citation history."""
    cits = led.citations(holding_id)
    against = sum(1 for c in cits if c["outcome"] == "overridden_pass")
    for_ = sum(1 for c in cits if c["outcome"] in ("complied_pass", "overridden_fail"))
    if against >= COUNTER_THRESHOLD and against > for_:
        led.set_status(holding_id, DEMOTE_TO)
        return DEMOTE_TO
    return "unchanged"


def sweep(led: Ledger, repo: str | None = None) -> list[int]:
    """Review every binding holding. Returns the ids that were overruled."""
    out = []
    for h in led.holdings(repo=repo, status="binding"):
        if review(led, h["id"]) == DEMOTE_TO:
            out.append(h["id"])
    return out
