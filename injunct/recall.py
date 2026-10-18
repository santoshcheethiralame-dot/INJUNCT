"""Retrieval. Cosine over a few hundred rows, in the standard library.

sentence-transformers is a drop-in upgrade and deliberately not a requirement:
at this n a bag-of-words cosine returns the same neighbours and costs nothing.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .db import Ledger
from . import templates

_WORD = re.compile(r"[a-z0-9_]+")


def _vec(text: str) -> Counter:
    return Counter(_WORD.findall((text or "").lower()))


def _cos(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    num = sum(a[t] * b[t] for t in common)
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def similar(led: Ledger, repo: str, task: str, k: int = 5,
            statuses: tuple[str, ...] = ("binding", "persuasive")) -> list[dict]:
    q = _vec(task)
    scored = []
    for h in led.holdings(repo=repo):
        if h["status"] not in statuses:
            continue
        case = led.case(h["case_id"]) or {}
        score = _cos(q, _vec(f"{h['says']} {case.get('summary','')} {' '.join(case.get('touched', []))}"))
        scored.append((score, h))
    scored.sort(key=lambda x: -x[0])
    return [dict(h, score=round(s, 3)) for s, h in scored[:k] if s > 0]


def everything(led: Ledger, repo: str, task: str, cap: int = 40) -> list[dict]:
    """Every rule in force, most relevant first - but none dropped.

    similar() filters on score > 0, which silently returns NOTHING when the task
    wording shares no token with the rule. For a prose arm that is the whole
    treatment disappearing, and the comparison against the gate becomes void.
    """
    q = _vec(task)
    rows = [h for h in led.holdings(repo=repo)
            if h["status"] in ("binding", "persuasive")]
    for h in rows:
        case = led.case(h["case_id"]) or {}
        h["score"] = round(_cos(q, _vec(
            f"{h['says']} {case.get('summary','')} {' '.join(case.get('touched', []))}")), 3)
    rows.sort(key=lambda h: -h["score"])
    return rows[:cap]


def briefing(led: Ledger, repo: str, task: str, k: int = 5, cap: int = 12) -> str:
    """What to tell the agent BEFORE it acts.

    Two bugs lived here and they had the same shape: an empty prompt.

    It used to ask for persuasive holdings only, reasoning that a binding rule
    needs no words because it will stop the agent anyway. That is backwards.
    Being stopped costs a turn and the model has to work out why; being told
    costs a sentence and it complies the first time.

    Then, having asked for binding rules too, it still filtered them by
    similarity - and a bag of words scores "add a phone_verified field to the
    patient model" against "models/*.py" at exactly zero. So a repository
    taught its rules directly, which is every repository on day one, got
    nothing.

    The gate does not consult a similarity score before firing. It evaluates
    every binding rule whatever the task was called. So every binding rule is
    named here, and only advisory ones - which stop nothing - are ranked by
    relevance.
    """
    binding = [h for h in led.holdings(repo=repo) if h["status"] == "binding"]
    advisory = [r for r in similar(led, repo, task, k=k, statuses=("persuasive",))]
    if not binding and not advisory:
        return ""

    lines: list[str] = []
    if binding:
        lines.append("This repository will STOP a change that breaks these. "
                     "They are not suggestions:")
        for r in binding[:cap]:
            lines.append(f"- {r['says']}")
            if r["template"] in templates.TEMPLATES:
                lines.append(f"  ({templates.render(r['template'], r['params'])})")
        if len(binding) > cap:
            lines.append(f"- ...and {len(binding) - cap} more.")
    if advisory:
        if lines:
            lines.append("")
        lines.append("Past failures on tasks like this one:")
        lines += [f"- {r['says']}" for r in advisory]
    return chr(10).join(lines)
