"""The terminal is a design surface. Two colours, one box, no emoji."""
from __future__ import annotations

import os
import sys
import time

W = 74
VER, AMB, GRN, DIM, OFF, BOLD = "\033[38;5;203m", "\033[38;5;214m", "\033[38;5;114m", "\033[38;5;242m", "\033[0m", "\033[1m"


def _colour() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(s: str, code: str) -> str:
    return f"{code}{s}{OFF}" if _colour() else s


def _row(text: str, code: str = "", pad: int = 2) -> str:
    room = W - 2 - pad
    if len(text) > room:                       # a long line must not break the box
        text = text[:room - 3] + "..."
    body = " " * pad + text
    fill = " " * max(0, W - 2 - len(body))
    return f"{_c('|', VER)}{_c(body, code) if code else body}{fill}{_c('|', VER)}"


def agent_card(verdicts: list[dict]) -> str:
    """The halt card as a *model* reads it, arriving as a tool error.

    halt_card below is 74 columns of box-drawing for a person at a terminal.
    An agent gets this instead: no colour, no box, no width to wrap against -
    just the holding, why it fired, the receipt that earned it the right to
    fire, and the one action that clears it.

    Kept identical to the card the opencode plugin builds, because an agent
    should not be able to tell which harness refused it. A test asserts that.
    """
    lines = ["BLOCKED BY INJUNCT - this exact change failed here before."]
    for v in verdicts:
        e = v.get("empanel") or {}
        lines.append("")
        lines.append(f"  Holding No {v.get('n')}, established {v.get('when')}. {v.get('says')}")
        lines.append(f"  Rule:   {v.get('rule')}")
        lines.append(f"  Reason: {v.get('reason')}")
        # Three provenances, and they must not read as one. A rule replayed
        # against history has earned something a rule you typed has not, and
        # flattening them would claim evidence that was never gathered.
        # taught/mined first: their receipts carry a `tested` count too, but
        # "n/a (you wrote it) fire" is not a sentence anyone should read.
        if e.get("taught"):
            lines.append("  Tested: not empanelled - you wrote this rule yourself.")
        elif e.get("mined"):
            lines.append("  Tested: mined from this repo's history, not empanelled.")
        elif e.get("tested"):
            lines.append(f"  Tested: {e.get('fire')} fire, {e.get('false')} false positives.")
        # A rule compiled from the repository's own documents says which line
        # it came from, so the agent can read the sentence it ignored.
        if e.get("documented"):
            lines.append(f"  From:   {e['documented']}")
        # A verdict tells the agent it is wrong; an instruction tells it what to
        # do. Without this a small model retries the same edit and stalls.
        if v.get("next"):
            lines.append(f"  DO THIS NEXT: {v['next']}")
    lines.append("")
    lines.append("Do the work named above in the same change, then try again.")
    return chr(10).join(lines)


def halt_card(v, number: int | None = None, repo=None,
              touched: list[str] | None = None) -> str:
    n = number if number is not None else v.holding_id
    when = time.strftime("%d %b %Y", time.localtime(v.established)).upper()
    e = v.empanel or {}
    if e.get("documented"):
        receipt = (f"from {e['documented']}   held on {e.get('false', '?').split('/')[-1]}"
                   f" past commits    cited {v.cited}")
    elif e.get("tested"):
        receipt = (f"empanelled {e.get('fire','?')} fire  {e.get('false','?')} false"
                   f"    cited {v.cited}")
    elif e.get("taught"):
        # Authored by the person, not derived from anything. Saying "mined from
        # history" here would credit evidence that was never gathered.
        receipt = f"you wrote this rule    cited {v.cited}"
    elif e.get("mined"):
        receipt = f"mined from history, not empanelled    cited {v.cited}"
    else:
        receipt = f"not empanelled    cited {v.cited}"

    # A verdict tells the agent it is wrong. An instruction tells it what to do.
    step = []
    if repo is not None:
        try:
            from .nextstep import suggest
            hint = suggest(v, repo, touched or [])
        except Exception:
            hint = ""
        if hint:
            step = [_row(""), _row(f"DO THIS NEXT:  {hint}", AMB)]

    top = _c("+" + "-" * (W - 2) + "+", VER)
    sep = _c("+" + "-" * (W - 2) + "+", VER)
    return "\n".join([
        top,
        _row(f"HALT   BINDING HOLDING No {n}   ESTABLISHED {when}", VER),
        sep,
        _row(v.says, BOLD),
        _row(""),
        _row(v.rule, AMB),
        _row(v.reason, DIM),
        _row(""),
        _row(receipt, DIM),
    ] + step + [top])


def note_line(v) -> str:
    """Advisory. Said once, plainly, and it does not stop anything."""
    head = f"  {_c('note', AMB)}  {v.says}"
    body = f"        {_c(v.reason, DIM)}"
    return head + chr(10) + body


def clear_line() -> str:
    return _c("no binding precedent fires on this working tree.", GRN)


def docket_line(h: dict, case: dict) -> str:
    stamp = {"binding": _c("BINDING  ", AMB), "persuasive": _c("advisory ", DIM),
             "overruled": _c("OVERRULED", VER), "retired": _c("retired  ", DIM)}.get(h["status"], h["status"])
    return f"  {_c('No ' + str(h['id']).rjust(3), DIM)}  {stamp}  {h['says'][:48]:<48} {_c(case.get('source',''), DIM)}"

def watch_halt(seat, touched) -> str:
    head = f"  {_c('HALT', VER)}  {seat.says}"
    why = f"        {_c(seat.reason, DIM)}"
    nxt = f"        {_c('do this next: ' + seat.next, AMB)}" if seat.next else ""
    return chr(10).join(x for x in (head, why, nxt) if x)


def watch_recovered(ids) -> str:
    which = ", ".join(f"No {i}" for i in ids)
    return f"  {_c('CLEARED', GRN)}  {which} satisfied. The change may land."


def watch_clear(touched) -> str:
    n = len(touched)
    what = touched[0] if n == 1 else f"{n} files"
    return f"  {_c('ok', GRN)}      {what} - nothing objects."
