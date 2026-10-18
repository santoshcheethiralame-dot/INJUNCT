"""Filing a case and, if it survives empanelment, establishing precedent."""
from __future__ import annotations

from pathlib import Path

from .change import Change
from .db import Ledger
from .harvest import RunWatch, Signal, all_signals
from . import artifacts, compiler, empanel, templates, transfer  # noqa: F401


def file_case(led: Ledger, run_id: int, repo: str, sig: Signal, ch: Change,
              use_model: bool = True, share: bool = False) -> dict:
    """Record the failure, compile a holding, and test it against history."""
    case_id = led.file_case(run_id, repo, sig.source, sig.confidence,
                            sig.summary, ch.touched, sig.detail)
    artifacts.save(Path(repo), run_id, ch)   # the case's own tree, for re-empanelment
    case = led.case(case_id)

    past = [c for c in (artifacts.load(Path(repo), r["id"])
                        for r in led.successful_runs(repo, limit=40)) if c]
    template, params, says = compiler.compile_case(case, ch, use_model=use_model, past=past)
    if not template:
        hid = led.establish(case_id, repo, "prose", {"text": says}, says, status="persuasive")
        return {"case_id": case_id, "holding_id": hid, "status": "persuasive",
                "template": None, "says": says, "receipt": {"error": "no template fit"},
                "shared": {"scope": "repo", "repos": 1}}

    status, receipt = empanel.empanel(led, repo, template, params, ch)
    if sig.confidence != "high" and status == "binding":
        status, receipt = "persuasive", {**receipt, "note": "low-confidence signal"}

    hid = led.establish(case_id, repo, template, params, says, status=status, empanel=receipt)
    shared = transfer.note(repo, template, params, says, status) if share else {"scope": "repo"}
    return {"case_id": case_id, "holding_id": hid, "status": status,
            "template": template, "params": params, "says": says, "receipt": receipt,
            "shared": shared}


def revisit(led: Ledger, repo: str) -> list[int]:
    """A case that could not be turned into a rule yet is not closed.

    Every passing run adds history, and history is what the fallback compiler
    reads. Prose holdings are re-derived when the evidence finally exists.
    """
    past = [c for c in (artifacts.load(Path(repo), r["id"])
                        for r in led.successful_runs(repo, limit=40)) if c]
    if not past:
        return []
    derived = []
    for h in led.holdings(repo=repo):
        if h["template"] != "prose" or h["status"] in ("overruled", "retired"):
            continue
        case = led.case(h["case_id"])
        origin = artifacts.load(Path(repo), case["run_id"]) if case else None
        if origin is None:
            continue
        t, params, says = compiler.fallback(case, origin, past)
        if not t:
            continue
        status, receipt = empanel.empanel(led, repo, t, params, origin)
        led.update_holding(h["id"], t, params, says, status, receipt)
        derived.append(h["id"])
    return derived


def file_free_signals(led: Ledger, run_id: int, repo: str, watch: RunWatch | None,
                      ch: Change, use_model: bool = False) -> list[dict]:
    """Learn without waiting for anyone to say no.

    A human rejection is rare. An agent rewriting a file it just wrote, reverting
    itself, or breaking a test that was green is common, free, and needs nobody.
    These are low-confidence by construction, so they can only ever become
    persuasive authority - the gate stays reserved for evidence we trust.
    """
    if watch is None:
        return []
    return [file_case(led, run_id, repo, sig, ch, use_model=use_model)
            for sig in all_signals(watch)]


def record_success(led: Ledger, run_id: int, repo: str, ch: Change) -> None:
    """A passing run is evidence too: it is what future holdings get tested against."""
    led.close_run(run_id, "pass")
    artifacts.save(Path(repo), run_id, ch)
    revisit(led, repo)
    empanel.reconsider(led, repo)
