"""INJUNCT as a Claude Code hook - the other harness that can actually refuse.

`watch` reads git and reports; it cannot stop anything. The opencode plugin
stops a write by throwing in tool.execute.before. This is the same enforcement
for Claude Code, which reaches far more people: a PreToolUse hook that inspects
the write *before* it lands and denies it, handing the halt card back to the
model as the reason.

Two events, both registered by `injunct claude`:

  PreToolUse         a write is about to happen -> allow, or deny with the card
  UserPromptSubmit   the turn is starting -> put the rules in front of the model

The second one matters more than it looks. Being blocked costs a whole turn and
the model has to work out why; being told costs a sentence and it complies the
first time. Our own numbers say the gate is not the mechanism - the instruction
is.

Nothing here decides anything. Every verdict comes from the same
`serve.gate_check` the plugin and the watcher call, so a rule cannot mean one
thing in one harness and something else in another.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

# Tools that put bytes on disk. Anything else is not a change we can judge, and
# gating a read is how a memory layer gets uninstalled in an afternoon.
WRITERS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# The shell puts bytes on disk too. The first live run in the desktop app went
# straight past the gate: told to prefer shell edits, the model ran `sed -i` on
# the model file, and a matcher that only knew Edit never saw a write. So a
# Bash command that looks like it writes is judged on every path it names -
# and PostToolUse re-checks the tree afterwards for whatever this misses.
_WRITES = re.compile(
    r"(\bsed\b[^|;&]*\s-[a-zA-Z]*i\b|\bperl\b[^|;&]*\s-[a-zA-Z]*i\b"      # in-place edits
    r"|(?<![<>&\d])>(?![&>])|>>"                                            # redirects
    r"|\btee\b|\b(mv|cp|rm|patch|truncate|install)\b|\bgit\s+(apply|checkout|restore|stash)\b"
    r"|<<|\bpython3?\s+(-c\b|-\s|\S+\.py\b))")                             # inline / script python, not -m
_PATHISH = re.compile(r"(?:[A-Za-z]:)?[\w.~-]*[/\\][\w./\\~-]*|\b[\w-]+\.[A-Za-z]{1,6}\b")


def _msys(path: str) -> str:
    """Git Bash spells C:\\x as /c/x. Claude Code on Windows sends both."""
    m = re.match(r"^/([A-Za-z])/(.*)$", path)
    return f"{m.group(1).upper()}:/{m.group(2)}" if m else path


def shell_paths(command: str) -> list[str]:
    """Paths a shell command names, if it looks like it writes; else nothing."""
    if not isinstance(command, str) or not _WRITES.search(command):
        return []
    out = []
    # quoted strings first - a path with a space in it only survives quoted
    quoted = [a or b for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", command)]
    for tok in quoted + _PATHISH.findall(command):
        tok = tok.strip("'\"`,;:")
        if not tok or tok.startswith("-") or tok in ("/dev/null", "..", ".") or "://" in tok:
            continue
        if tok.count(".") == 1 and tok.split(".")[1].isdigit():        # 2.4, 0.9
            continue
        out.append(tok)
    return list(dict.fromkeys(out))

URL = os.environ.get("INJUNCT_URL", "http://127.0.0.1:4000")
MODE_ENV = "INJUNCT_MODE"
CHECK_ENV = "INJUNCT_CHECK"
CHECK: str | None = None      # set from --check; the repo's own pass/fail command


def pending_paths(tool_name: str, tool_input: dict) -> list[str]:
    """Which files this call is about to write.

    Claude Code names them in snake_case and differs per tool: `file_path` for
    Write/Edit/MultiEdit, `notebook_path` for NotebookEdit, and MultiEdit can
    carry a list of edits. Getting this wrong makes the gate silently useless -
    it would return "nothing pending" and allow every write.
    """
    if tool_name == "Bash":
        return [_msys(p) for p in shell_paths((tool_input or {}).get("command", ""))]
    if tool_name not in WRITERS:
        return []
    out: list[str] = []
    for key in ("file_path", "notebook_path"):
        v = (tool_input or {}).get(key)
        if isinstance(v, str) and v.strip():
            out.append(v.strip())
    edits = (tool_input or {}).get("edits")
    if isinstance(edits, list):
        for e in edits:
            v = e.get("file_path") if isinstance(e, dict) else None
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
    return [_msys(p) for p in dict.fromkeys(out)]


def _apply(text: str, old: object, new: object, every: bool = False) -> str | None:
    """One Edit, the way Claude Code applies it; None if it would not apply."""
    if not isinstance(old, str) or not isinstance(new, str):
        return None
    if old == "":
        return new if text == "" else None
    if old not in text:
        return None
    return text.replace(old, new) if every else text.replace(old, new, 1)


def pending_contents(tool_name: str, tool_input: dict) -> dict[str, str]:
    """What each file will hold once this call lands.

    Paths alone let every content rule through: the first live run wrote an
    AWS key into a new app/config.py and only Stop noticed. So a Write is
    judged on its content and an Edit on the file with the edit applied. An
    edit that would not apply gets nothing here - it fails in Claude Code
    anyway, and inventing content for it would be guessing. Shell writes stay
    with PostToolUse, which sees the tree after the command.
    """
    ti = tool_input or {}
    path = ti.get("file_path")
    if tool_name not in ("Write", "Edit", "MultiEdit") or not isinstance(path, str) or not path.strip():
        return {}
    path = _msys(path.strip())
    if tool_name == "Write":
        return {path: ti["content"]} if isinstance(ti.get("content"), str) else {}
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace") if Path(path).is_file() else ""
    except OSError:
        return {}
    edits = [ti] if tool_name == "Edit" else ti.get("edits")
    if not isinstance(edits, list) or not edits:
        return {}
    for e in edits:
        if not isinstance(e, dict):
            return {}
        text = _apply(text, e.get("old_string"), e.get("new_string"), bool(e.get("replace_all")))
        if text is None:
            return {}
    return {path: text}


def _post(path: str, body: dict, timeout: float) -> dict | None:
    req = urllib.request.Request(
        f"{URL}{path}", data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def gate(repo: str, pending: list[str], timeout: float = 0.9,
         contents: dict[str, str] | None = None) -> dict:
    """Ask the service if it is up, otherwise answer in-process.

    The service is preferred only so the desk page lights up while someone is
    watching it - the decision is identical either way. `serve.gate_check` is a
    pure function of (repo, pending) and needs no server, so there is no daemon
    to start and nothing to keep running.
    """
    try:
        got = _post("/v1/gate", {"repo": repo, "pending": pending,
                                 "contents": contents or {}}, timeout)
        if isinstance(got, dict) and "block" in got:
            return got
    except Exception:
        pass
    from . import serve
    return serve.gate_check(repo, pending, contents)


def advise(repo: str, task: str, everything: bool, timeout: float = 0.9) -> str:
    try:
        got = _post("/v1/advise", {"repo": repo, "task": task,
                                   "everything": everything}, timeout)
        if isinstance(got, dict) and isinstance(got.get("text"), str):
            return got["text"]
    except Exception:
        pass
    from . import serve
    return serve.advise(repo, task, everything).get("text", "")


def _repo(payload: dict) -> str:
    """The repository whose ledger judges this call.

    CLAUDE_PROJECT_DIR is the obvious answer and it is wrong often enough to
    matter: a session opened without a folder and moved into the repository
    afterwards keeps the scratch path in that variable, and trusting it means
    the gate looks for a ledger in an empty directory and allows everything.
    So every candidate is tried, walking up from each, and the first one that
    actually holds a ledger wins. With no ledger anywhere, the old preference
    stands and the caller finds nothing to enforce - as before.
    """
    candidates = [os.environ.get("CLAUDE_PROJECT_DIR"), payload.get("cwd"), os.getcwd()]
    for c in candidates:
        if not c:
            continue
        try:
            here = Path(c).resolve()
        except OSError:
            continue
        for d in (here, *here.parents):
            if (d / ".injunct" / "ledger.db").is_file():
                return str(d)
    return next((c for c in candidates if c), os.getcwd())


def _deny(reason: str, user: str = "") -> tuple[int, str, str]:
    """Deny in both the shapes Claude Code accepts.

    The structured form on stdout is what current versions read; exit 2 with the
    reason on stderr is the older contract and still honoured. Emitting both
    costs nothing and means the gate does not quietly stop working when someone
    is on a different version.
    """
    body = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}
    if user:
        # The card above is for the model. The person watching gets one line
        # they can read at a glance, without opening the tool's error.
        body["systemMessage"] = user
    return 2, json.dumps(body), reason


def user_line(verdicts: list[dict], pending: list[str]) -> str:
    """One ASCII line for the person: what was refused, why, where it came from, what next."""
    v = verdicts[0]
    e = v.get("empanel") or {}
    where = (f" (from {e['documented']})" if e.get("documented")
             else " (built-in rule)" if e.get("pack") else "")
    files = ", ".join(sorted({Path(f).name for f in pending})[:3]) or "this change"
    line = f"Injunct blocked a write to {files}: {v.get('says')}{where}"
    if v.get("next"):
        line += f" Next: {v['next']}."
    if len(verdicts) > 1:
        line += f" (+{len(verdicts) - 1} more rule{'s' if len(verdicts) > 2 else ''})"
    return line.encode("ascii", "replace").decode("ascii")


def pretooluse(payload: dict, mode: str) -> tuple[int, str, str]:
    if mode == "off":
        return 0, "", ""
    pending = pending_paths(payload.get("tool_name", ""), payload.get("tool_input") or {})
    if not pending:
        return 0, "", ""
    repo = _repo(payload)
    if not (Path(repo) / ".injunct" / "ledger.db").is_file():
        return 0, "", ""            # nothing has been learned here yet
    got = gate(repo, pending, contents=pending_contents(
        payload.get("tool_name", ""), payload.get("tool_input") or {}))
    if not got.get("block") or not got.get("verdicts"):
        return 0, "", ""
    if mode == "advise":
        # Arm B: the model is told everything and stopped by nothing. This is
        # what every other memory layer in this space does.
        return 0, "", ""
    from . import render
    return _deny(render.agent_card(got["verdicts"]), user_line(got["verdicts"], pending))


# Claude Code appends additionalContext to the user message, and the message
# stays in the transcript. Saying the same twelve rules on every turn is the
# same text sixty times in a long session - tens of thousands of tokens spent
# repeating what the model already read. So the briefing goes out once per
# session, again if the rules change, and again every REBRIEF turns in case
# compaction has dropped it. Everything a turn needs to be *stopped* lives in
# PreToolUse, which never needed the words.
REBRIEF = 25


def _briefed(repo: str, session: str, text: str) -> bool:
    """True if this session was told exactly this recently. Fails open: any
    trouble with the state file means "say it", never "stay quiet"."""
    import hashlib
    # A repository may commit its ledger; it must never be asked to commit
    # which session has been told what. The directory ignores itself.
    folder = Path(repo) / ".injunct" / "session"
    state = folder / "briefed.json"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    try:
        prev = json.loads(state.read_text(encoding="utf-8"))
    except Exception:
        prev = {}
    same = prev.get("session") == session and prev.get("digest") == digest
    turn = prev.get("turn", 0) + 1 if same else 0
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".gitignore").write_text("*" + chr(10), encoding="utf-8")
        state.write_text(json.dumps({"session": session, "digest": digest,
                                     "turn": turn}), encoding="utf-8")
    except Exception:
        return False
    return same and turn % REBRIEF != 0


# Who is speaking, and what happens if the model ignores it. Without this the
# model narrates "a hook" and "repo rules"; with it, it names the thing. One
# paragraph, once per session - the rules themselves follow.
HEADER = {
    "enforce": (
        "INJUNCT is installed in this repository as a Claude Code hook. It turns "
        "this repo's confirmed past failures into binding checks: PreToolUse denies "
        "a Write/Edit - or a shell command that writes - when a binding holding "
        "fires, and PostToolUse re-checks the tree after every shell command. A "
        "refused write comes back as a halt card naming the holding, the evidence "
        "behind it, and the one thing to do next (DO THIS NEXT). Do that in the same "
        "change, then retry - the same edit then goes through. A binding rule cannot "
        "be argued with from here; `injunct off <n>` is the human's switch, not yours - "
        "it mutes a rule. A rule is overruled only when three overrides succeed anyway."),
    "advise": (
        "INJUNCT is installed in this repository as a Claude Code hook in advise "
        "mode: it briefs, it does not block. These rules come from this repo's own "
        "confirmed past failures. Follow them if they apply."),
}


def userpromptsubmit(payload: dict, mode: str) -> tuple[int, str, str]:
    if mode == "off":
        return 0, "", ""
    repo = _repo(payload)
    if not (Path(repo) / ".injunct" / "ledger.db").is_file():
        return 0, "", ""
    # In advise mode the binding rules are spoken rather than enforced, so the
    # two arms differ only in whether the model may ignore what it is told.
    text = advise(repo, payload.get("prompt", "") or "", everything=(mode == "advise"))
    if not text.strip():
        return 0, "", ""
    text = HEADER.get(mode, HEADER["enforce"]) + chr(10) + chr(10) + text
    session = str(payload.get("session_id") or "")
    if session and _briefed(repo, session, text):
        return 0, "", ""
    return 0, json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": text}}), ""


def posttooluse(payload: dict, mode: str) -> tuple[int, str, str]:
    """After a shell command: is the tree it left behind in breach?

    The bytes are already down, so this cannot refuse. What it can do is hand
    the card back before the model moves on, so the fix lands in the same turn
    instead of at commit time. Exit 2 here is "show stderr to the model".
    """
    if mode != "enforce" or payload.get("tool_name") != "Bash":
        return 0, "", ""
    repo = _repo(payload)
    if not (Path(repo) / ".injunct" / "ledger.db").is_file():
        return 0, "", ""
    got = gate(repo, [])
    if not got.get("block") or not got.get("verdicts"):
        return 0, "", ""
    from . import render
    return 2, "", ("The command ran. The tree it left behind fires a binding holding.\n\n"
                   + render.agent_card(got["verdicts"]))


def _check_command(repo: str) -> str | None:
    """The command that says whether the tree is good: --check, then the
    environment, then `python oracle.py` if the repo has one. Nothing → skip."""
    cmd = CHECK or os.environ.get(CHECK_ENV)
    if cmd:
        return cmd
    if (Path(repo) / "oracle.py").is_file():
        return "python oracle.py"
    return None


def _already_filed(repo: str, session: str, output: str) -> bool:
    """The same failing output, filed once per session. An agent that stops
    twice to ask a question must not file the same case twice."""
    import hashlib
    folder = Path(repo) / ".injunct" / "session"
    state = folder / "postflight.json"
    digest = hashlib.sha1(output.strip().encode("utf-8")).hexdigest()
    try:
        prev = json.loads(state.read_text(encoding="utf-8"))
    except Exception:
        prev = {}
    if prev.get("session") == session and prev.get("digest") == digest:
        return True
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".gitignore").write_text("*" + chr(10), encoding="utf-8")
        state.write_text(json.dumps({"session": session, "digest": digest}), encoding="utf-8")
    except Exception:
        pass
    return False


def stop(payload: dict, mode: str) -> tuple[int, str, str]:
    """The agent has gone quiet. Run the repo's own check; a failure is a case.

    This is the half that makes it *learn* inside Claude Code - the opencode
    plugin does the same on session.idle. The check runs only when the tree
    has changed, the failure is filed once, and the compiled holding is handed
    back to the model so the fix lands in the same session. Exit 2 on Stop
    means "keep going, here is why"; stop_hook_active guards the loop.
    """
    if mode == "off" or payload.get("stop_hook_active"):
        return 0, "", ""
    repo = _repo(payload)
    if not (Path(repo) / ".injunct" / "ledger.db").is_file():
        return 0, "", ""
    if mode == "enforce":
        # PreToolUse sees which files a write touches, not what it puts in
        # them, so a content rule (a committed key, a leftover breakpoint) can
        # only fire once the bytes are down. Checking the tree before the turn
        # ends puts that fix in this turn instead of at commit time.
        got = gate(repo, [])
        if got.get("block") and got.get("verdicts"):
            from . import render
            return 2, "", ("Before you finish: the tree you left fires a binding rule. Fix it in this turn.\n\n"
                           + render.agent_card(got["verdicts"]))
    cmd = _check_command(repo)
    if not cmd:
        return 0, "", ""
    from .change import Change
    if not Change.from_git(Path(repo)).touched:
        return 0, "", ""                      # nothing changed, nothing to judge
    from . import serve, shell
    r = shell.run(cmd, repo, timeout=100)
    if r.returncode == 0:
        return 0, "", ""
    output = (r.stdout + r.stderr)[-1500:].strip()
    session = str(payload.get("session_id") or "")
    if session and _already_filed(repo, session, output):
        return 0, "", ""                      # same failure, already on file
    filed = serve.file_check_failure(repo, cmd, output)
    tail = chr(10).join(output.splitlines()[-6:])
    lines = [f"INJUNCT: after your change, this repository's check failed (`{cmd}`):",
             "", *("  " + l for l in tail.splitlines()), ""]
    if filed.get("holding_id"):
        lines += [f"Filed as case {filed.get('case_id')}. Holding No {filed['holding_id']} is now "
                  f"{str(filed.get('status', '')).upper()}: {filed.get('says', '')}",
                  "The next attempt at this shape of mistake will be stopped before the write."]
    lines += ["", "Fix the check now, in this same change."]
    return 2, "", chr(10).join(lines)


EVENTS = {"PreToolUse": pretooluse, "PostToolUse": posttooluse,
          "UserPromptSubmit": userpromptsubmit, "Stop": stop}


def main(argv: list[str] | None = None) -> int:
    """Fail open, structurally.

    Every path out of here returns 0 unless a binding holding actually fired.
    A memory layer that can wedge someone's agent by being broken is worse than
    no memory layer, so a crash, a malformed payload, a missing ledger and an
    unreachable service all mean "allow".
    """
    try:
        p = argparse.ArgumentParser(prog="injunct-hook")
        p.add_argument("--event", default="PreToolUse", choices=sorted(EVENTS))
        p.add_argument("--mode", default="enforce")
        p.add_argument("--check", default=None, help="the repo's pass/fail command, for Stop")
        a = p.parse_args(argv)
        global CHECK
        CHECK = a.check
        mode = (os.environ.get(MODE_ENV) or a.mode or "enforce").lower()

        payload = json.loads(sys.stdin.read() or "{}")
        code, out, err = EVENTS[a.event](payload, mode)
        if out:
            sys.stdout.write(out)
        if err:
            sys.stderr.write(err)
        return code
    except BaseException:
        return 0


if __name__ == "__main__":
    sys.exit(main())
