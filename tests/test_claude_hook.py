"""The Claude Code hook gets the same contract test as the opencode plugin.

A gate that only works in one harness is a gate most people never see, so this
asserts the other one refuses for real: the right exit code, the right JSON, the
card the model actually reads, and - the half that gets forgotten - that it
fails OPEN on every path where something has gone wrong.

Every case drives the hook through a real subprocess, because the exit code is
the contract and asserting it in-process would prove nothing about what Claude
Code sees. INJUNCT_URL points at a dead port throughout, so the in-process
fallback is what is under test; if that path breaks, the hook is useless to
anyone who has not started the service.
"""
import json
import os
import subprocess
import sys

import pytest

from injunct import render, verbs
from injunct.workspace import restore
from tests.test_loop import SEED
from tests.test_serve import git, teach

DEAD = "http://127.0.0.1:9"          # nothing listens here; forces in-process


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "clinic"
    restore(SEED, r)
    git(r, "init", "-q")
    git(r, "add", "-A")
    git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")
    from injunct import serve
    serve.forget_ledgers()
    return r


def fire(repo, tool="Edit", tool_input=None, event="PreToolUse",
         mode="enforce", payload=None, url=DEAD):
    body = payload if payload is not None else {
        "hook_event_name": event, "cwd": str(repo),
        "tool_name": tool, "tool_input": tool_input or {}}
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo), "INJUNCT_URL": url}
    env.pop("INJUNCT_MODE", None)
    return subprocess.run(
        [sys.executable, "-m", "injunct.claude_hook", "--event", event, "--mode", mode],
        input=body if isinstance(body, str) else json.dumps(body),
        capture_output=True, text=True, cwd=repo, env=env)


# ---- it allows what it should ------------------------------------------------

def test_an_unrelated_edit_is_allowed(repo):
    teach(repo)
    r = fire(repo, tool_input={"file_path": "static/index.html"})
    assert r.returncode == 0
    assert r.stdout == ""


def test_a_read_is_never_gated(repo):
    teach(repo)
    r = fire(repo, tool="Read", tool_input={"file_path": "models/patient.py"})
    assert r.returncode == 0


def test_a_bash_call_is_never_gated(repo):
    teach(repo)
    r = fire(repo, tool="Bash", tool_input={"command": "rm -rf models"})
    assert r.returncode == 0


# ---- it refuses what it should ----------------------------------------------

def test_the_edit_that_failed_before_is_denied(repo):
    teach(repo)
    r = fire(repo, tool_input={"file_path": "models/patient.py"})
    assert r.returncode == 2, r.stdout + r.stderr


def test_the_denial_is_valid_hook_json(repo):
    teach(repo)
    r = fire(repo, tool_input={"file_path": "models/patient.py"})
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"].strip()


def test_the_card_names_the_holding_and_the_next_step(repo):
    """A verdict tells the agent it is wrong. An instruction tells it what to do."""
    teach(repo)
    r = fire(repo, tool_input={"file_path": "models/patient.py"})
    card = json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Holding No" in card
    assert "migrations" in card
    assert "DO THIS NEXT" in card
    assert "fire" in card              # the receipt that earned it the right
    assert card == r.stderr            # both channels carry the same card


def test_an_absolute_path_is_normalised(repo):
    """Agent runtimes hand out absolute paths; every rule is repo-relative."""
    teach(repo)
    r = fire(repo, tool_input={"file_path": str(repo / "models" / "patient.py")})
    assert r.returncode == 2


def test_a_multiedit_is_judged_by_its_edits(repo):
    teach(repo)
    r = fire(repo, tool="MultiEdit",
             tool_input={"edits": [{"file_path": "models/patient.py"}]})
    assert r.returncode == 2


# ---- the three arms differ --------------------------------------------------

def test_off_blocks_nothing(repo):
    teach(repo)
    assert fire(repo, tool_input={"file_path": "models/patient.py"}, mode="off").returncode == 0


def test_advise_speaks_but_does_not_block(repo):
    teach(repo)
    assert fire(repo, tool_input={"file_path": "models/patient.py"},
                mode="advise").returncode == 0
    spoke = fire(repo, event="UserPromptSubmit", mode="advise",
                 payload={"hook_event_name": "UserPromptSubmit", "cwd": str(repo),
                          "prompt": "add an email field to the patient model"})
    ctx = json.loads(spoke.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.strip(), "arm B must actually reach the model with something"


def test_the_mode_env_var_overrides_the_installed_mode(repo):
    """The benchmark flips arms per process; it cannot rewrite settings.json."""
    teach(repo)
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(repo),
           "INJUNCT_URL": DEAD, "INJUNCT_MODE": "off"}
    r = subprocess.run(
        [sys.executable, "-m", "injunct.claude_hook", "--event", "PreToolUse",
         "--mode", "enforce"],
        input=json.dumps({"cwd": str(repo), "tool_name": "Edit",
                          "tool_input": {"file_path": "models/patient.py"}}),
        capture_output=True, text=True, cwd=repo, env=env)
    assert r.returncode == 0


# ---- and it fails open ------------------------------------------------------

def test_it_fails_open_with_no_ledger(tmp_path):
    r = fire(tmp_path, tool_input={"file_path": "models/patient.py"})
    assert r.returncode == 0


def test_it_fails_open_on_garbage_stdin(repo):
    teach(repo)
    r = fire(repo, payload="{not json")
    assert r.returncode == 0


def test_it_fails_open_when_the_service_lies(repo):
    """An unreachable service must fall back, not crash and not block."""
    teach(repo)
    r = fire(repo, tool_input={"file_path": "static/index.html"},
             url="http://127.0.0.1:9")
    assert r.returncode == 0


# ---- the installer ----------------------------------------------------------

def test_the_installer_registers_both_events(repo):
    out = verbs.claude(repo)
    cfg = json.loads((repo / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert out["config"].is_file()
    assert not (repo / ".claude" / "hooks" / "injunct_gate.py").exists()   # settings only, no shim
    assert set(cfg["hooks"]) == {"PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop"}
    pre = cfg["hooks"]["PreToolUse"][0]
    assert pre["matcher"] == "Write|Edit|MultiEdit|NotebookEdit|Bash"   # a shell edit is a write too
    assert verbs.MARK in pre["hooks"][0]["command"]


def test_the_merge_is_idempotent_and_keeps_foreign_hooks(repo):
    """A repository that already configures its own hooks must not lose them."""
    cfg_path = repo / ".claude" / "settings.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps({"hooks": {
        "PostToolUse": [{"matcher": "Write", "hooks": [
            {"type": "command", "command": "prettier --write"}]}],
        "PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "audit.sh"}]}],
    }}), encoding="utf-8")

    verbs.claude(repo)
    verbs.claude(repo, mode="advise")           # re-run, different mode
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    assert cfg["hooks"]["PostToolUse"][0]["hooks"][0]["command"] == "prettier --write"
    bash = [g for g in cfg["hooks"]["PreToolUse"] if g["matcher"] == "Bash"]
    assert bash and bash[0]["hooks"][0]["command"] == "audit.sh"

    ours = [h for g in cfg["hooks"]["PreToolUse"] for h in g["hooks"]
            if verbs.MARK in h["command"]]
    assert len(ours) == 1, "re-running must replace our entry, not stack another"
    assert "--mode advise" in ours[0]["command"]


def test_the_gate_cannot_be_switched_off_through_the_agent(repo):
    """An advisory tool has nothing worth disarming. This one does."""
    from injunct import packs
    rule = next(r for r in packs.RULES if r["key"] == "self_disarm")
    glob = rule["params"]["glob"]
    assert ".claude/settings.json" in glob
    assert ".claude/hooks/**" in glob


# ---- and both harnesses say the same thing ----------------------------------

def test_the_card_matches_the_opencode_plugin():
    """An agent should not be able to tell which harness refused it."""
    ts = (verbs.ROOT / "plugin" / "injunct.ts").read_text(encoding="utf-8")
    card = render.agent_card([{
        "n": 1, "says": "Changing models/*.py means changing migrations/ too.",
        "rule": "co_change( models/*.py -> migrations/** )",
        "reason": "models/patient.py changed, nothing under migrations/** did",
        "next": "create migrations/002_x.sql", "when": "11 Sep 2026",
        "empanel": {"fire": "1/1", "false": "0/5", "tested": 5}}])
    for line in ("BLOCKED BY INJUNCT - this exact change failed here before.",
                 "Holding No", "Rule:", "Reason:", "Tested:", "DO THIS NEXT:",
                 "Do the work named above in the same change, then try again."):
        assert line in card, line
        assert line in ts, f"the plugin no longer says {line!r}"
    # ASCII only, both sides: this card goes to stderr on a Windows console and
    # an unencodable character there makes the hook fail open instead of block.
    card.encode("ascii")


def test_a_documented_rule_does_not_claim_it_failed_here_before():
    ts = (verbs.ROOT / "plugin" / "injunct.ts").read_text(encoding="utf-8")
    card = render.agent_card([{
        "n": 1, "says": "Changing a model requires a migration.", "rule": "co_change( models/* -> migrations/* )",
        "reason": "models/patient.py changed", "next": "create migrations/009_patient.sql", "when": "18 Oct 2026",
        "empanel": {"fire": "n/a (documented)", "false": "0/13", "tested": 13, "documented": "AGENTS.md:7"}}])
    assert card.startswith("BLOCKED BY INJUNCT - this breaks a rule this repository wrote down, and its history proved it.") and "BLOCKED BY INJUNCT - this breaks a rule this repository wrote down, and its history proved it." in ts
    assert "failed here before" not in card
    for line in ("  Tested: held on 13 past commits, 0 false positives.", "  From:   AGENTS.md:7"):
        assert line in card, line
    assert "Tested: held on" in ts and "From:   " in ts
    card.encode("ascii")


def test_a_pack_rule_says_what_it_is_in_both_harnesses():
    ts = (verbs.ROOT / "plugin" / "injunct.ts").read_text(encoding="utf-8")
    card = render.agent_card([{
        "n": 14, "says": "Take the debugger breakpoint out before this lands.",
        "rule": "must_not_appear( /breakpoint/ in **/*.py )", "reason": "a.py adds a line",
        "when": "18 Oct 2026", "empanel": {"pack": "pdb"}}])
    assert card.startswith("BLOCKED BY INJUNCT - a mistake coding agents make everywhere; this repository's rule pack forbids it.") and "BLOCKED BY INJUNCT - a mistake coding agents make everywhere; this repository's rule pack forbids it." in ts
    assert "  Tested: a built-in rule, binding wherever it applies." in card
    assert "Tested: a built-in rule, binding wherever it applies." in ts
    card.encode("ascii")


def test_the_person_gets_one_readable_line_when_a_write_is_blocked():
    from injunct import claude_hook
    line = claude_hook.user_line([{
        "says": "Changing a model requires adding a migration in the same commit.",
        "next": "create migrations/009_patient.sql", "empanel": {"documented": "AGENTS.md:7"}}],
        ["C:/repo/models/patient.py"])
    assert line == ("Injunct blocked a write to patient.py: Changing a model requires adding a migration "
                    "in the same commit. (from AGENTS.md:7) Next: create migrations/009_patient.sql.")
    line.encode("ascii")


def test_a_content_rule_is_caught_before_the_turn_ends(tmp_path):
    """PreToolUse cannot see what a write puts in a file, so a leftover
    breakpoint lands. The Stop hook must hand it back in the same turn."""
    from injunct import claude_hook, coverdemo
    repo = coverdemo.build(tmp_path / "clinic")
    verbs.install_pack(repo)
    booking = repo / "app" / "booking.py"
    booking.write_text(booking.read_text(encoding="utf-8").replace(
        "def book(slot, doctor=None):\n", "def book(slot, doctor=None):\n    breakpoint()\n", 1), encoding="utf-8")
    code, _, err = claude_hook.stop({"cwd": str(repo), "hook_event_name": "Stop"}, "enforce")
    assert code == 2 and "breakpoint" in err and "Before you finish" in err
    # and it does not loop: a Stop that Claude Code marks as already continuing is left alone
    assert claude_hook.stop({"cwd": str(repo), "stop_hook_active": True}, "enforce")[0] == 0
