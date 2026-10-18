"""Run the arms and write the report."""
from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from pathlib import Path

from ..change import Change
from ..db import Ledger
from ..harvest import Signal
from ..workspace import restore
from .. import harness, provider, record
from . import agent
from .tasks import ORACLE, SEEDS, all_tasks

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".bench"


def _learn(led: Ledger, res, repo: Path, output: str) -> dict:
    """File the failure. Deliberately does NOT hand over the oracle command:
    a rule that just says 'run the grader' would make the benchmark circular."""
    sig = Signal("command_fail", "high", "the working tree failed its check",
                 json.dumps({"output": output[:400]}))
    return record.file_case(led, res.run_id, str(repo.resolve()), sig,
                            Change.since(repo, res.before, res.commands), use_model=False)


def run_arm(arm: str, seed: int, p_recall: float, tasks, p_comply: float = 1.0,
            live: bool = False) -> list[dict]:
    """p_comply is the probability that a blocked agent does what the card asked.

    At 1.0 the harness hands the agent the exact companion it skipped, so the
    result is an UPPER BOUND: it measures whether the rule identified the right
    missing work, not whether a real agent acts on being told. Anything below
    1.0 models an agent that is stopped, told, and sometimes ignores it.
    """
    base = WORK / arm / str(seed)
    led = Ledger(base / "ledger.db")
    led.wipe()
    order = list(tasks)
    random.Random(seed).shuffle(order)
    rng = random.Random(seed * 7919 + 13)

    rows = []
    for n, task in enumerate(order):
        repo = base / task.repo
        restore(SEEDS / task.repo, repo)
        actions, skipped = agent.script(task, rng, p_recall)
        if live:
            # Hand the harness nothing, so it calls the model for every step.
            # This is the only path where arm B's prose is actually sent.
            actions = None

        cb = None
        if arm == "C":
            cb = (lambda verdicts, t=task, s=skipped:
                  agent.repair(t, s, verdicts, comply=rng.random() < p_comply))

        res = harness.run(repo, task.id, led, arm=arm, oracle=ORACLE,
                          scripted=list(actions) if actions is not None else None,
                          on_block=cb, seed=seed)
        if arm in ("B", "C"):
            if not res.passed:
                _learn(led, res, repo, "")
            # free signals: the agent contradicting itself, with no human involved
            record.file_free_signals(led, res.run_id, str(repo.resolve()),
                                     res.watch, Change.since(repo, res.before, res.commands))

        # A pristine repository passes its own oracle, so "did nothing" and
        # "did it correctly" are the same verdict unless we ask this.
        attempted = task.attempted(repo)
        # A run in which the model was never reachable is not evidence about
        # anything. Rate limiting produced ninety of them, all scored as passes.
        vacuous = live and any(
            (st.action or {}).get("tool") == "error" and "no model" in str(st.result)
            for st in res.steps)
        rows.append({
            "p_comply": p_comply,
            "arm": arm, "seed": seed, "order": n, "task": task.id,
                     "repo": task.repo, "trap": task.trap or "",
                     "passed": bool(res.passed and attempted and not vacuous),
                     "attempted": attempted, "vacuous": vacuous,
                     "blocked": res.blocked, "fired": sorted(set(res.fired)),
                     "skipped": len(skipped)})
    counts = led.counts(None)
    led.close()
    for r in rows:
        r["ledger"] = counts
    return rows


def metrics(rows: list[dict]) -> dict:
    out: dict = {}
    for arm in sorted({r["arm"] for r in rows}):
        a = [r for r in rows if r["arm"] == arm]
        traps = [r for r in a if r["trap"]]
        controls = [r for r in a if not r["trap"]]

        repeat_total = repeat_failed = 0
        for seed in sorted({r["seed"] for r in a}):
            seen: set[str] = set()
            for r in sorted([x for x in a if x["seed"] == seed], key=lambda x: x["order"]):
                if not r["trap"]:
                    continue
                if r["trap"] in seen:
                    repeat_total += 1
                    repeat_failed += not r["passed"]
                if not r["passed"]:
                    seen.add(r["trap"])

        out[arm] = {
            "runs": len(a),
            # If this is low the run says more about the model than the gate.
            "attempt_rate": round(sum(r.get("attempted", True) for r in a) / len(a), 4),
            "pass_rate": round(sum(r["passed"] for r in a) / len(a), 4),
            "trap_pass_rate": round(sum(r["passed"] for r in traps) / len(traps), 4) if traps else None,
            "repeat_failure_rate": round(repeat_failed / repeat_total, 4) if repeat_total else None,
            "repeat_seen": repeat_total,
            "false_positive_rate": round(sum(r["blocked"] > 0 for r in controls) / len(controls), 4)
            if controls else None,
            "blocks": sum(r["blocked"] for r in a),
            # Of the runs that were stopped, how many went on to pass. A gate
            # that halts an agent which then fails anyway has cost a run and
            # bought nothing - stopping is not the same as improving.
            "recovery_rate": round(
                sum(r["passed"] for r in a if r["blocked"]) /
                sum(1 for r in a if r["blocked"]), 4)
            if any(r["blocked"] for r in a) else None,
        }
    return out


def by_trap(rows: list[dict]) -> dict:
    out: dict = defaultdict(dict)
    for arm in sorted({r["arm"] for r in rows}):
        for trap in sorted({r["trap"] for r in rows if r["trap"]}):
            sel = [r for r in rows if r["arm"] == arm and r["trap"] == trap]
            if sel:
                out[trap][arm] = round(sum(r["passed"] for r in sel) / len(sel), 4)
    return dict(out)


def curve(rows: list[dict], bucket: int = 6) -> dict:
    """Trap pass rate against position in the sequence. This is the tape:
    arm C starts level with arm A and pulls away as precedent accumulates."""
    out: dict = {}
    for arm in sorted({r["arm"] for r in rows}):
        buckets: dict[int, list[bool]] = {}
        for r in rows:
            if r["arm"] != arm or not r["trap"]:
                continue
            buckets.setdefault(r["order"] // bucket, []).append(r["passed"])
        out[arm] = [{"from": b * bucket, "to": b * bucket + bucket - 1,
                     "n": len(v), "pass_rate": round(sum(v) / len(v), 4)}
                    for b, v in sorted(buckets.items())]
    return out


def regressions(rows: list[dict]) -> list[dict]:
    idx = {(r["arm"], r["seed"], r["task"]): r for r in rows}
    out = []
    for (arm, seed, task), r in idx.items():
        if arm != "C":
            continue
        a = idx.get(("A", seed, task))
        if a and a["passed"] and not r["passed"]:
            out.append({"seed": seed, "task": task, "trap": r["trap"]})
    return out


def main(arms=("A", "C"), seeds=(1, 2, 3, 4, 5), p_recall: float = 0.5,
         out: Path | None = None, live: bool = False) -> dict:
    if live and not provider.available():
        raise RuntimeError("--live needs a reachable model; none answered")
    tasks = all_tasks()
    rows: list[dict] = []
    t0 = time.time()
    for arm in arms:
        for seed in seeds:
            rows += run_arm(arm, seed, p_recall, tasks, live=live)
            print(f"  {arm}/{seed}  done", flush=True)

    dead = sum(r.get("vacuous", False) for r in rows)
    if dead:
        share = dead / len(rows)
        print(f"  {dead} of {len(rows)} runs never reached the model.")
        if share > 0.1:
            raise RuntimeError(
                f"refusing to write a report: {share:.0%} of runs never reached "
                "the model, so the numbers would be about a rate limit rather "
                "than about the gate. Wait for the quota, or point "
                "INJUNCT_BASE_URL at something that answers.")

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        # Label what ACTUALLY drove the run. Reporting the model name because a
        # provider happened to be reachable turns a synthetic result into what
        # looks like a live one, which is worse than having no result.
        "agent": provider.MODEL if live else "synthetic",
        "p_recall": p_recall,
        "arms": list(arms), "seeds": list(seeds),
        "tasks": len(tasks), "runs": len(rows), "seconds": round(time.time() - t0, 1),
        "metrics": metrics(rows), "by_trap": by_trap(rows), "curve": curve(rows),
        "regressions": regressions(rows), "rows": rows,
    }
    out = out or ROOT / "bench" / "report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def sweep(seeds=(1, 2, 3), p_recall: float = 0.5,
          levels=(0.0, 0.25, 0.5, 0.75, 1.0), out: Path | None = None) -> dict:
    """How much of the benefit needs the agent to actually do what it is told.

    The headline number was measured at p_comply=1.0, where the harness hands a
    blocked agent the exact companion it skipped. That is a ceiling. This walks
    the compliance axis so the floor and the break-even point are visible too.
    """
    tasks = all_tasks()
    a_rows = []
    for s_ in seeds:
        a_rows += run_arm("A", s_, p_recall, tasks)
    baseline = metrics(a_rows)["A"]

    curve_ = []
    for p in levels:
        rows = []
        for s_ in seeds:
            rows += run_arm("C", s_, p_recall, tasks, p_comply=p)
        m = metrics(rows)["C"]
        m["p_comply"] = p
        curve_.append(m)

    worse = [c["p_comply"] for c in curve_
             if c["repeat_failure_rate"] > baseline["repeat_failure_rate"]]
    report = {"generated": time.strftime("%Y-%m-%d %H:%M"),
              "seeds": list(seeds), "tasks": len(tasks), "p_recall": p_recall,
              "baseline_A": baseline, "curve": curve_,
              "harmful_at_or_below": max(worse) if worse else None}
    out = out or ROOT / "bench" / "compliance.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
