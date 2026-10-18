"""Point a real coding agent at a seeded repo and ask one question:

    does the precedent fire on exactly the runs the agent gets wrong?

The harness does not drive the agent and does not touch its prompt. It restores
the tree, invokes whatever command is configured, then reads the working tree
with the same git-based recorder the CLI uses. That is the whole point of an
agent-agnostic recorder: nothing here knows what opencode is.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .change import Change
from .db import Ledger
from .workspace import restore
from . import gate, shell

ROOT = Path(__file__).resolve().parents[1]

# The trial repo lives OUTSIDE this repository, deliberately.
#
# opencode resolves the enclosing git worktree, so a trial repo nested inside
# precedent let a real agent wander out of its workspace and edit seeds/ twice.
# Both times it silently changed the fixture the whole benchmark depends on.
# Containment is not a tidiness concern here; an agent with file access will
# use all of it.
WORKROOT = Path(
    __import__("os").environ.get("INJUNCT_LIVE_HOME", Path.home() / ".injunct-live"))

TASKS = [
    "Add a phone_verified field to the Patient model.",
    "Add an email field to the Patient model.",
    "Add a date_of_birth field to the Patient model.",
    "The front desk needs to record each patient's insurer. Add it.",
    "Patients should have an allergy note on their record. Add that field.",
    "Add a last_visit field to the Patient model.",
]

AGENTS_MD = """# Bengaluru Dental - front desk

`models/patient.py` declares which columns the app reads.
`store.py` builds the database from the files in `migrations/`.
`python oracle.py` checks the app can still read its patients.
"""

MODEL = "opencode/nemotron-3.5-lightning-free"
ARMS = ("off", "advise", "enforce")   # A: nothing · B: prose · C: gates


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True,
                   encoding="utf-8", errors="replace")


def _reset_ledger(repo: Path) -> None:
    """Every trial starts from the same knowledge, or the arms are not comparable."""
    pristine = repo / ".injunct" / "ledger.seed.db"
    live = repo / ".injunct" / "ledger.db"
    if pristine.is_file():
        shutil.copy2(pristine, live)


def start_service(port: int = 4000):
    """The plugin talks to a local service. Nothing was starting one.

    Without it every post() from the plugin fails, the plugin returns early,
    and all three arms silently become a bare agent - which is exactly how the
    previous run produced numbers that looked like a result.
    """
    import threading
    from http.server import ThreadingHTTPServer
    from . import serve

    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), serve.Handler)
    except OSError:
        return None                      # already up; fine
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def setup(seed: Path, repo: Path) -> dict:
    """Build the trial workspace once, and commit it as the baseline.

    The agent's own configuration - its plugin, its permissions, its AGENTS.md -
    is NOT part of the seed, so restoring the seed over the workspace deletes it.
    That is how an earlier run silently disarmed itself: the plugin went away on
    trial one and every arm after that was a bare agent with no memory, printing
    numbers that looked like a result. So the config is installed here, committed,
    and each trial resets with git rather than by restoring the seed again.
    """
    from .demo import teach

    if repo.exists():
        shutil.rmtree(repo, ignore_errors=True)
    restore(seed, repo)

    # Teach first: it dirties the tree, and the baseline must be the seed.
    led = Ledger(repo / ".injunct" / "ledger.db")
    taught = teach(led, repo)
    led.close()
    restore(seed, repo)
    shutil.copy2(repo / ".injunct" / "ledger.db", repo / ".injunct" / "ledger.seed.db")

    # The agent's own configuration goes in LAST, because restore() deletes
    # anything the seed does not contain - which is how the plugin vanished
    # from an earlier run and left every arm identical.
    plugins = repo / ".opencode" / "plugins"
    plugins.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "plugin" / "injunct.ts", plugins / "injunct.ts")
    # `edit: allow` on its own permits editing ANY absolute path, and with bash
    # the agent can walk up and find this repository - which is exactly what it
    # did: editing seeds/clinic and writing a migrations/ directory at the root
    # while the recorder watched an untouched workspace. Deny anything outside.
    (repo / "opencode.json").write_text(json.dumps({
        "$schema": "https://opencode.ai/config.json",
        "permission": {
            "edit": "allow",
            "bash": "allow",
            "webfetch": "deny",
            "external_directory": "deny",
        },
    }, indent=2), encoding="utf-8")
    (repo / "AGENTS.md").write_text(AGENTS_MD, encoding="utf-8")

    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "baseline")
    return taught


def _reset_tree(repo: Path) -> None:
    """Back to the baseline commit, without creating one.

    Committing here instead - which an earlier version did - folds the previous
    trial's work into HEAD, so `git diff HEAD` comes back empty and the recorder
    reports that the agent touched nothing at all.
    """
    _git(repo, "checkout", "--", ".")
    _git(repo, "clean", "-fdq")


def _repo_untouched() -> None:
    """The agent must not have wandered into this repository.

    It has, twice. opencode was pointed at a workspace outside the repo and
    still edited seeds/, injunct/ and wrote a migrations/ directory at the
    root - which a `git add -A` then committed. A trial that corrupts the
    fixtures it is measured against poisons every result after it, so the run
    stops the moment it happens rather than at the end.
    """
    import subprocess as _sp

    r = _sp.run(["git", "status", "--porcelain"], cwd=str(ROOT),
                capture_output=True, text=True)
    dirty = [l for l in r.stdout.splitlines() if l.strip()]
    if dirty:
        raise RuntimeError(
            "the agent modified the injunct repository during a trial:"
            + chr(10) + chr(10).join("  " + d for d in dirty[:10])
            + chr(10) + "the run is void; restore with: git checkout -- .")


def _armed(repo: Path, led: Ledger, port: int = 4000) -> None:
    """Refuse to start unless the treatment actually FIRES.

    Checking that the parts exist is not enough and has failed twice. The
    plugin file was present while the service it calls was not listening, so
    every arm ran bare and reported numbers. This asks the service the same
    question the plugin will ask, and demands the right answer.
    """
    import json as _json
    import urllib.request

    plugin = repo / ".opencode" / "plugins" / "injunct.ts"
    if not plugin.is_file():
        raise RuntimeError(f"the plugin is not installed at {plugin}")
    binding = [h for h in led.holdings() if h["status"] == "binding"]
    if not binding:
        raise RuntimeError("the ledger holds no binding precedent; there is nothing to enforce")

    base = f"http://127.0.0.1:{port}"
    trigger = _trigger_path(binding[0])
    try:
        body = _json.dumps({"repo": str(repo), "pending": [trigger]}).encode()
        req = urllib.request.Request(f"{base}/v1/gate", data=body,
                                     headers={"Content-Type": "application/json"})
        gate_says = _json.loads(urllib.request.urlopen(req, timeout=5).read())
    except Exception as e:
        raise RuntimeError(f"the service the plugin depends on is not answering on {base}: {e}")
    if not gate_says.get("block"):
        raise RuntimeError(
            f"the gate did not fire on {trigger}, so enforce mode would enforce nothing")

    try:
        body = _json.dumps({"repo": str(repo), "task": "add a field",
                            "everything": True}).encode()
        req = urllib.request.Request(f"{base}/v1/advise", data=body,
                                     headers={"Content-Type": "application/json"})
        prose = _json.loads(urllib.request.urlopen(req, timeout=5).read()).get("text", "")
    except Exception as e:
        raise RuntimeError(f"the advise endpoint is not answering: {e}")
    if not prose.strip():
        raise RuntimeError("advise returned nothing, so arm B would be an empty prompt")


def _trigger_path(holding: dict) -> str:
    """A path the first binding rule is known to fire on."""
    p = holding.get("params") or {}
    trig = p.get("trigger") or p.get("glob") or ""
    return trig.replace("**/", "").replace("*", "patient") or "models/patient.py"


def trial(repo: Path, seed: Path, led: Ledger, task: str, model: str = MODEL,
          timeout: int = 420, mode: str = "enforce") -> dict:
    _reset_tree(repo)
    _reset_ledger(repo)

    t0 = time.time()
    # opencode is a .cmd shim on Windows, so it needs a shell and one string.
    cmd = f'opencode run -m {model} "{task.replace(chr(34), chr(39))}"'
    # One launcher, one decoding policy. opencode writes UTF-8 and ANSI;
    # Windows would decode it as cp1252 and take the whole run down.
    proc = shell.run_env(cmd, repo, {"INJUNCT_MODE": mode}, timeout=timeout)
    said = (proc.stdout or "") + (proc.stderr or "")
    took = round(time.time() - t0, 1)

    ch = Change.from_git(repo)
    verdicts = gate.evaluate(led, str(repo.resolve()), ch)
    oracle = shell.run("python oracle.py", repo)

    return {
        "task": task, "mode": mode, "seconds": took, "exit": proc.returncode,
        "halted": "BLOCKED BY INJUNCT" in said,
        "touched": ch.touched,
        "oracle_passed": oracle.returncode == 0,
        "oracle": ((oracle.stdout or "") + (oracle.stderr or "")).strip()[:200],
        "fired": [{"n": v.holding_id, "says": v.says, "rule": v.rule, "reason": v.reason}
                  for v in verdicts],
    }


def vacuous(r: dict) -> bool:
    """The agent never actually did anything.

    A trial where nothing was written and nothing was halted measures the
    provider - a 504, a timeout, a refusal - not the treatment. Scoring it as
    a pass silently credits the arm for work that never happened.
    """
    return not r.get("touched") and not r.get("halted")


def score(rows: list[dict]) -> dict:
    """A gate is only useful if it fires on the wrong runs and stays quiet on the right ones."""
    tp = sum(1 for r in rows if r["fired"] and not r["oracle_passed"])
    fp = sum(1 for r in rows if r["fired"] and r["oracle_passed"])
    fn = sum(1 for r in rows if not r["fired"] and not r["oracle_passed"])
    tn = sum(1 for r in rows if not r["fired"] and r["oracle_passed"])
    return {
        "trials": len(rows),
        "agent_failed": tp + fn,
        "caught": tp, "missed": fn, "false_alarms": fp, "correctly_silent": tn,
        "precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "recall": round(tp / (tp + fn), 3) if tp + fn else None,
    }


def main(n: int | None = None, model: str = MODEL, out: Path | None = None,
         arms: tuple[str, ...] = ARMS, retries: int = 3) -> dict:
    """The arm B question, asked of a real model.

    Same tasks, same model, same repository state. Arm `advise` is told about
    every past failure in prose and may ignore it; arm `enforce` is stopped.
    Nothing here is synthetic - this is the comparison the synthetic benchmark
    could not make.
    """
    seed = ROOT / "seeds" / "clinic"
    repo = (WORKROOT / "trial").resolve()
    taught = setup(seed, repo)
    start_service(4000)
    led = Ledger(repo / ".injunct" / "ledger.db")
    _armed(repo, led, port=4000)
    print(f"  armed: {taught['status']} - {taught['says']}", flush=True)
    tasks = TASKS[:n] if n else TASKS

    rows = []
    for mode in arms:
        for i, task in enumerate(tasks, 1):
            print(f"  [{mode} {i}/{len(tasks)}] {task}", flush=True)
            # The free provider returns intermittent 504s. A trial where the
            # model never answered measures the provider, not the treatment, so
            # it is retried rather than recorded - and if it keeps failing it is
            # marked dead and excluded, never counted as a pass.
            r = {}
            for attempt in range(1, retries + 1):
                try:
                    r = trial(repo, seed, led, task, model=model, mode=mode)
                except subprocess.TimeoutExpired:
                    r = {"task": task, "mode": mode, "timeout": True, "fired": [],
                         "oracle_passed": False, "touched": [], "seconds": None,
                         "halted": False}
                r["attempts"] = attempt
                _repo_untouched()          # stop the moment it wanders
                if not vacuous(r):
                    break
                if attempt < retries:
                    print(f"        no answer from the model; retry {attempt}/{retries - 1}",
                          flush=True)
            rows.append(r)
            print(f"        oracle={'pass' if r['oracle_passed'] else 'FAIL'}"
                  f"  halted={r.get('halted')}  touched={r['touched']}", flush=True)

    real = [r for r in rows if not vacuous(r)]
    by_arm = {m: score([r for r in real if r.get("mode") == m]) for m in arms}

    # A disarmed run produces numbers that look exactly like a result. The only
    # honest thing to do with one is refuse to report it.
    invalid = []
    dead = len(rows) - len(real)
    if dead:
        invalid.append(f"{dead}/{len(rows)} trials had no agent activity at all "
                       f"(provider error or timeout) and were excluded")
    if "enforce" in arms:
        e = [r for r in rows if r.get("mode") == "enforce"]
        if not any(r.get("halted") or r.get("fired") for r in e):
            invalid.append("the enforce arm never halted or fired a precedent - "
                           "the treatment was not engaged")
    if all(not r.get("touched") for r in rows):
        invalid.append("the recorder saw no file changes in any trial - "
                       "the workspace reset is wrong")

    report = {"generated": time.strftime("%Y-%m-%d %H:%M"), "model": model,
              "agent": "opencode", "arms": list(arms), "by_arm": by_arm,
              "trials": len(rows), "scored": len(real), "dead": dead,
              "valid": not invalid, "invalid_because": invalid,
              "score": score(real), "rows": rows}
    out = out or ROOT / "bench" / "live.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    led.close()
    return report
