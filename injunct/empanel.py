"""A holding is not binding until it has been tested against history.

It MUST fire on the case that produced it, and it MUST NOT fire on the stored
working trees of past successful runs. Fail either and it is demoted to
persuasive authority, where being wrong costs nothing.

There is a third way to fail, and it is the one that actually bit us. A check
whose evidence is missing from a stored run abstains - and an abstention is
indistinguishable from silence unless you go looking. `must_run` asks whether a
generator ran; artifacts once recorded no commands at all; so every replay
abstained, no past run could ever contradict the rule, and it went binding on
an empty proof. It then fired on a task that only edited a README.

That is why `judged` is counted separately from `tested`. A rule that nothing
could test has not earned the right to block anything, and the receipt now says
so out loud rather than showing a confident 0/5.
"""
from __future__ import annotations

from pathlib import Path

from .change import Change
from .db import Ledger
from . import artifacts, templates

# How many past runs must have been *able* to contradict a rule before it may
# bind. One is the smallest honest bar: at least something could have said no.
MIN_JUDGED = 1


def empanel(led: Ledger, repo: str, template: str, params: dict,
            origin: Change, sample: int = 40) -> tuple[str, dict]:
    """Return (status, receipt)."""
    if not templates.valid(template, params):
        return "persuasive", {"error": "template parameters incomplete"}

    fired_on_origin = templates.fires(template, params, origin) is not None

    false_positives: list[int] = []
    tested = judged = 0
    for run in led.successful_runs(repo, limit=sample):
        past = artifacts.load(Path(repo), run["id"])
        if past is None:
            continue
        tested += 1
        # A check that cannot see the evidence it needs returns None, exactly as
        # it does when satisfied. Counting that as "stayed silent" is how a rule
        # becomes binding without anything ever having been able to contradict
        # it - unfalsifiable rather than merely untested.
        if not templates.can_judge(template, params, past):
            continue
        judged += 1
        if templates.fires(template, params, past) is not None:
            false_positives.append(run["id"])

    receipt = {
        "fire": f"{int(fired_on_origin)}/1",
        "false": f"{len(false_positives)}/{judged}",
        "false_ids": false_positives[:5],
        "tested": tested,
        "judged": judged,
    }
    if not tested:
        receipt["note"] = "no successful run to test against yet"
        return "persuasive", receipt
    if judged < MIN_JUDGED:
        receipt["note"] = (f"none of {tested} past run(s) could test this rule; "
                           "it has not earned the right to block")
        return "persuasive", receipt
    if fired_on_origin and not false_positives:
        return "binding", receipt
    return "persuasive", receipt


def reconsider(led: Ledger, repo: str) -> list[int]:
    """New evidence arrives with every passing run. Advisory holdings get retried."""
    promoted = []
    for h in led.holdings(repo=repo, status="persuasive"):
        if h["template"] not in templates.TEMPLATES:
            continue
        case = led.case(h["case_id"])
        origin = artifacts.load(Path(repo), case["run_id"]) if case else None
        if origin is None:
            continue
        status, receipt = empanel(led, repo, h["template"], h["params"], origin)
        if status == "binding":
            led.set_status(h["id"], "binding", receipt)
            promoted.append(h["id"])
    return promoted
