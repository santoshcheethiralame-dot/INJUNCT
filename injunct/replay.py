"""Record one real session so the desk has something to show with no service.

The desk is a live view of `injunct watch`. Nobody opening the static site
is going to start a watcher, so the only state it ever showed was `dormant` -
a clerk doing nothing, on the page that is supposed to demonstrate the tool.

This records a genuine session instead of faking one. It drives the same
`watch._report` the live watcher drives, against a real ledger with real
binding precedents, and captures exactly what `serve.emit` produced. The
playback pacing is ours; every event in the file was emitted by the product.

    python -m injunct replay

writes web/replay.json and puts the repository back as it found it.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import serve, watch
from .change import Change
from .db import Ledger

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
REPO = ROOT / ".bench" / "C" / "1" / "clinic"
LEDGER = ROOT / ".bench" / "C" / "1" / "ledger.db"

# How long each beat sits on screen during playback. The capture happens in
# milliseconds; a viewer needs time to read a card.
BEATS = {"watch.start": 2600, "sitting": 2600, "recovered": 4200}

TRAP = "models/patient.py"
TRAP_TEXT = """FIELDS = ['id', 'name', 'phone', 'allergy', 'next_visit']

LABELS = {'id': '#', 'name': 'Patient', 'phone': 'Phone',
          'allergy': 'Allergy', 'next_visit': 'Next visit'}
"""
FIX = "migrations/105_next_visit.sql"
FIX_TEXT = "ALTER TABLE patient ADD COLUMN next_visit TEXT;\n"


def record(repo: Path = REPO, ledger: Path = LEDGER,
           out: Path | None = None) -> dict:
    repo, ledger = Path(repo), Path(ledger)
    if not repo.is_dir() or not ledger.is_file():
        raise SystemExit(
            f"  no recorded ledger at {ledger}.\n"
            "  run: python -m injunct bench --arms A,C --seeds 1")

    out = Path(out) if out else WEB / "replay.json"
    before = Change.snapshot(repo)
    led = Ledger(ledger)
    root = str(repo.resolve())
    serve._events.clear()

    try:
        serve.emit("watch.start", repo=root, port=serve.PORT)

        # 1. the agent edits a model and stops. A binding precedent fires.
        (repo / TRAP).write_text(TRAP_TEXT, encoding="utf-8")
        ch = Change.since(repo, before)
        watch._report(led, root, ch, ())
        halted = tuple(s.holding_id for s in watch._sitting(led, root, ch).seats
                       if s.verdict == "halt")
        if not halted:
            raise SystemExit(
                "  nothing halted, so there is no session worth recording.\n"
                "  the ledger has no binding rule covering " + TRAP)

        # 2. it does the work the card asked for, and the halt clears.
        (repo / FIX).write_text(FIX_TEXT, encoding="utf-8")
        ch = Change.since(repo, before)
        watch._report(led, root, ch, halted)

        events = [dict(e) for e in serve._events]
    finally:
        led.close()
        _restore(repo, before)

    # Relative timings for playback, and the real clock kept alongside so the
    # recording can still be checked against when it happened.
    t = 0
    for e in events:
        e["t"] = t
        t += BEATS.get(e["kind"], 1800)

    doc = {"recorded": time.strftime("%Y-%m-%d %H:%M"),
           "repo": repo.name, "source": ledger.as_posix(),
           "events": events}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def _restore(repo: Path, before: dict) -> None:
    """Put every file back. A recording that leaves the tree dirty would show
    up in the next benchmark as a result, which is how this repo has been
    burned before."""
    for path, text in before.items():
        p = repo / path
        if not p.is_file() or p.read_text(encoding="utf-8", errors="replace") != text:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
    for p in list(repo.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(repo)).replace("\\", "/")
        if rel not in before and not rel.startswith(".injunct/"):
            p.unlink()


def main(repo: str | None = None) -> int:
    doc = record(Path(repo) if repo else REPO)
    kinds = ", ".join(e["kind"] for e in doc["events"])
    print(f"  recorded {len(doc['events'])} events from {doc['repo']}: {kinds}")
    print(f"  wrote {(WEB / 'replay.json')}")
    return 0
