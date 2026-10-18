"""The split screen. Two copies of the same app, two agents, one clock.

Left has no memory. Right has the ledger. You watch one of them go down.
Nothing here is mocked: the same gate, the same ledger, the same oracle.
"""
from __future__ import annotations

import json
import shutil
import socketserver
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .change import Change
from .db import Ledger
from .harness import register_failure, run
from .workspace import restore
from . import gate

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "seeds" / "clinic"
WORK = ROOT / ".demo"
PORTS = {"A": 8901, "C": 8902, "ui": 8900}

TASK = "Add a phone_verified field to the Patient model"
MODEL_SRC = ('FIELDS = ["id", "name", "phone", "phone_verified"]\n\n'
             'LABELS = {"id": "#", "name": "Patient", "phone": "Phone", '
             '"phone_verified": "Verified"}\n')
MIGRATION = "ALTER TABLE patients ADD COLUMN phone_verified INTEGER DEFAULT 0;\n"

# Round two, and the reason the project exists. Arm A repairs the first
# mistake so its app comes back - then makes exactly the same mistake on the
# next field. That is the repeat-failure rate the benchmark measures,
# happening on screen: an agent falls into a trap class it has already been
# burned by, more than half the time.
TASK2 = "Now add an insurer field"
MODEL_SRC2 = ('FIELDS = ["id", "name", "phone", "phone_verified", "insurer"]\n\n'
              'LABELS = {"id": "#", "name": "Patient", "phone": "Phone", '
              '"phone_verified": "Verified", "insurer": "Insurer"}\n')
MIGRATION2 = "ALTER TABLE patients ADD COLUMN insurer TEXT;\n"

# Round three: the mistake every single person in the room has made.
# Nobody needs a database explained to understand why pasting your API key
# into the code and pushing it is bad - and this rule was never learned from
# a failure. It ships on day one, because you should not have to leak a key
# once to find out the tool could have caught it.
TASK3 = "Add SMS reminders"
SMS_SRC = ('"""Send an appointment reminder."""\n'
           'import urllib.request\n\n'
           'API_KEY = "sk-DEMOKEYDEMOKEYDEMOKEY123456"\n\n'
           'def send(phone, text):\n'
           '    return urllib.request.urlopen("https://sms.example/send")\n')

STEPS = [
    {"label": "read the model",
     "why": "The code is about to say a patient has a new field.",
     "A": {"tool": "read_file", "path": "models/patient.py"},
     "C": {"tool": "read_file", "path": "models/patient.py"}},
    {"label": "add the field",
     "why": "Both add it to the code. Neither has told the database yet.",
     "A": {"tool": "write_file", "path": "models/patient.py", "content": MODEL_SRC},
     "C": {"tool": "write_file", "path": "models/patient.py", "content": MODEL_SRC}},
    {"label": "carry on",
     "why": "The left one stops here. The right one was stopped, and told which file to write.",
     "A": {"tool": "done"},
     "C": {"tool": "write_file", "path": "migrations/003_phone_verified.sql", "content": MIGRATION}},
    {"label": "finish",
     "why": "The left app is asking for a column the database has never heard of.",
     "A": {"tool": "done"},
     "C": {"tool": "done"}},

    # --- round two: the sentence the whole project is named after ---------
    {"label": "A repairs it", "task": TASK2, "fresh": True,
     "why": "The left one fixes it. Its app comes back. Everyone is happy.",
     "A": {"tool": "write_file", "path": "migrations/003_phone_verified.sql",
           "content": MIGRATION},
     "C": {"tool": "read_file", "path": "models/patient.py"}},
    {"label": "the same mistake again", "task": TASK2,
     "why": "New field, same story. It has already been burned by this once.",
     "A": {"tool": "write_file", "path": "models/patient.py", "content": MODEL_SRC2},
     "C": {"tool": "write_file", "path": "models/patient.py", "content": MODEL_SRC2}},
    {"label": "one of them was stopped", "task": TASK2,
     "why": "One of them remembered. That is the 58% repeat-failure rate, on screen.",
     "A": {"tool": "done"},
     "C": {"tool": "write_file", "path": "migrations/004_insurer.sql",
           "content": MIGRATION2}},
    {"label": "finish", "task": TASK2,
     "why": "Left is down for the second time. Right never went down at all.",
     "A": {"tool": "done"},
     "C": {"tool": "done"}},

    # --- round three: no failure had to happen first ----------------------
    {"label": "a new feature", "task": TASK3, "fresh": True,
     "why": "Different job now. Send SMS reminders.",
     "A": {"tool": "read_file", "path": "app.py"},
     "C": {"tool": "read_file", "path": "app.py"}},
    {"label": "the API key goes in the code", "task": TASK3,
     "why": "Both paste the API key straight into the file. You have done this.",
     "A": {"tool": "write_file", "path": "sms.py", "content": SMS_SRC},
     "C": {"tool": "write_file", "path": "sms.py", "content": SMS_SRC}},
    {"label": "one of them shipped it", "task": TASK3,
     "why": "Nobody had to leak a key first. That rule came with the tool.",
     "A": {"tool": "done"},
     "C": {"tool": "done"}},
]


def _copy(dst: Path) -> None:
    restore(SEED, dst)


def teach(led: Ledger, repo: Path) -> dict:
    """Give the ledger the history it would have had: one good run, one bad one."""
    good = ('FIELDS = ["id", "name", "phone", "notes"]\n\n'
            'LABELS = {"id": "#", "name": "Patient", "phone": "Phone"}\n')
    run(repo, "add a notes field", led, arm="A", scripted=[
        {"tool": "write_file", "path": "models/patient.py", "content": good},
        {"tool": "write_file", "path": "migrations/002_notes.sql",
         "content": "ALTER TABLE patients ADD COLUMN notes TEXT;\n"},
        {"tool": "done"}])
    bad = run(repo, "add an email field", led, arm="A", scripted=[
        {"tool": "write_file", "path": "models/patient.py",
         "content": 'FIELDS = ["id", "name", "phone", "email"]\n\nLABELS = {"id": "#"}\n'},
        {"tool": "done"}])
    return register_failure(repo, led, bad, use_model=False)


class State:
    def __init__(self) -> None:
        self.led: Ledger | None = None
        self.reset()

    def reset(self) -> dict:
        self.step = 0
        self.edits = {"A": {}, "C": {}}
        self.trace = {"A": [], "C": []}
        self.blocked = None
        self.verdict = None
        self._seats: list[dict] = []
        self.judged: dict | None = None
        self.t0 = time.time()
        for arm in ("A", "C"):
            _copy(WORK / arm)
        if self.led is None:
            self.led = Ledger(WORK / "ledger.db")
        self.led.wipe()
        self.holding = teach(self.led, WORK / "C")
        # The pack as well, so the panel shows what a real repository looks
        # like: two dozen rules considering every change and quietly deciding
        # it is fine. One card on its own says a tripwire went off; a column of
        # rules clearing with one halting says a gate made a decision.
        #
        # It goes here rather than in teach(), which live.py also calls - its
        # arming guard reads the FIRST binding holding and assumes it is
        # path-triggered, and the pack puts aws_key at the front.
        try:
            from . import verbs
            # Not the borrowed gates: each one starts another Python
            # process, and four of them make a single change take twenty
            # seconds to judge. They are real checks; they are not a demo.
            verbs.install_pack(WORK / "C", self.led, skip=("sleeper_gate",))
        except Exception:
            pass                  # the demo still runs with the one rule
        _copy(WORK / "C")          # a pristine tree; the ledger keeps what it learned
        self._recount_seats()
        return self.snapshot()

    def advance(self) -> dict:
        if self.step >= len(STEPS):
            return self.snapshot()
        s = STEPS[self.step]
        # A new task is a new change. The gate judges what this run touched,
        # not everything that ever happened to the tree - otherwise round two
        # is waved through by round one's migration, and the agent gets credit
        # for work it did on a different task.
        if s.get("fresh"):
            self.edits = {"A": {}, "C": {}}
        self.blocked = None
        for arm in ("A", "C"):
            a = s[arm]
            line = a["tool"] + (" " + a.get("path", "") if a.get("path") else "")
            if a["tool"] == "write_file":
                p = WORK / arm / a["path"]
                p.parent.mkdir(parents=True, exist_ok=True)
                before = p.read_text(encoding="utf-8") if p.is_file() else None
                p.write_text(a["content"], encoding="utf-8")
                self.edits[arm][a["path"]] = a["content"]
                if arm == "C":
                    v = gate.evaluate(self.led, str((WORK / "C").resolve()),
                                      Change.from_edits(WORK / "C", self.edits["C"]))
                    if v:
                        # The plugin throws in tool.execute.before, so the
                        # bytes never reach the disk. Writing and then judging
                        # left arm C's app broken for a beat and its front desk
                        # showed "service unavailable" - the exact frame the
                        # whole demo exists to deny. Put the file back.
                        if before is None:
                            p.unlink(missing_ok=True)
                        else:
                            p.write_text(before, encoding="utf-8")
                        self.judged = dict(self.edits[arm])
                        self.edits[arm].pop(a["path"], None)
                        self.blocked = {
                            "n": v[0].holding_id, "says": v[0].says, "rule": v[0].rule,
                            "reason": v[0].reason, "cited": v[0].cited,
                            "empanel": v[0].empanel,
                            "when": time.strftime("%d %b", time.localtime(v[0].established)),
                        }
                        line += "   HALTED"
            self.trace[arm].append(line)
        self.step += 1
        self._recount_seats()
        self.judged = None
        return self.snapshot()

    def _verdicts(self) -> dict:
        """The oracle decides, not the browser. Same script the benchmark runs."""
        if self.verdict is None and self.step >= len(STEPS):
            self.verdict = {
                arm: subprocess.run("python oracle.py", cwd=WORK / arm, shell=True,
                                    capture_output=True, text=True).returncode == 0
                for arm in ("A", "C")}
        return self.verdict or {}

    def _recount_seats(self) -> None:
        """Every rule that looked at this change, including the quiet ones.

        One card appearing says a rule fired. This says how many rules
        considered the change and decided it was fine, which is the difference
        between a gate and a tripwire - and it is what the false-positive
        number is actually counting.
        """
        from . import panel
        self._seats = []
        if self.led is None:
            return
        try:
            sit = panel.sit(self.led, str((WORK / "C").resolve()),
                            Change.from_edits(WORK / "C",
                                              self.judged or self.edits["C"]))
        except Exception:
            return
        self._seats = [{"n": x.holding_id, "says": x.says, "verdict": x.verdict,
                        "domain": x.domain} for x in sit.seats]

    def snapshot(self) -> dict:
        # The sentence has to describe the frame you are LOOKING at, which is
        # the step just executed - not the one about to run. The label is the
        # opposite: it names what happens next.
        cur = STEPS[self.step - 1] if self.step else STEPS[0]
        return {"step": self.step, "total": len(STEPS), "blocked": self.blocked,
                "verdict": self._verdicts(), "seats": self._seats,
                "why": cur.get("why", ""),
                "trace": self.trace, "task": cur.get("task", TASK),
                "label": STEPS[self.step]["label"] if self.step < len(STEPS) else "finished",
                "counts": self.led.counts(str((WORK / "C").resolve())) if self.led else {}}


STATE = State()


class UI(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/state"):
            return self._json(STATE.snapshot())
        if self.path.startswith("/step"):
            return self._json(STATE.advance())
        if self.path.startswith("/reset"):
            return self._json(STATE.reset())
        # The race is drawn in the same room as every other page, so it needs
        # the sprites. Without this every path returned demo.html, the sprite
        # fetches parsed HTML as JSON, and the room quietly did not appear.
        if self.path.startswith("/sprites/"):
            return self._static(self.path.lstrip("/"))
        return self._static("demo.html")

    TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json",
             ".png": "image/png"}

    def _static(self, rel: str) -> None:
        root = (ROOT / "web").resolve()
        target = (root / rel).resolve()
        # A path from the network may not leave web/.
        if root not in target.parents or not target.is_file():
            self.send_error(404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type",
                         self.TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve_app(arm: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "app.py", str(PORTS[arm])],
                            cwd=WORK / arm, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    STATE.reset()
    procs = [serve_app("A"), serve_app("C")]
    print(f"  arm A  http://127.0.0.1:{PORTS['A']}")
    print(f"  arm C  http://127.0.0.1:{PORTS['C']}")
    print(f"  demo   http://127.0.0.1:{PORTS['ui']}\n")
    try:
        HTTPServer(("127.0.0.1", PORTS["ui"]), UI).serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()
    return 0
