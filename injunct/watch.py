"""Watch a working tree and show every decision as it happens.

This is the harness-agnostic path, and it is the important one. A plugin has to
be written per agent - opencode, Cursor, Claude Code, whatever comes next - and
each one is a separate thing to maintain and a separate thing to be broken by an
upstream change.

A working tree is a working tree. `injunct watch` looks at git, not at the
agent, so it works with every one of them at once, and with a person typing by
hand. The plugin remains worth having for one reason only: it can stop a write
before it lands. The watcher can only report - but it reports everything.
"""
from __future__ import annotations

import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

from .change import Change
from .db import Ledger, ledger_path
from . import render, serve, transfer

POLL_SECONDS = 0.7


def _serve_in_background(port: int) -> ThreadingHTTPServer | None:
    try:
        httpd = ThreadingHTTPServer(("127.0.0.1", port), serve.Handler)
    except OSError:
        return None                       # already running; we just emit into it
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def main(path: str = ".", port: int = 4000, poll: float = POLL_SECONDS) -> int:
    repo = Path(path).resolve()
    led = Ledger(ledger_path(repo))
    root = str(repo)

    httpd = _serve_in_background(port)
    where = "serving" if httpd else "sending to an existing server on"
    print(f"  watching {repo}")
    print(f"  {where} http://127.0.0.1:{port}  (board: /v1/events)")
    print("  any agent, any editor - this reads the tree, not the agent.")
    print()

    serve.emit("watch.start", repo=root, port=port)
    last: dict | None = None
    last_halt: tuple = ()

    try:
        while True:
            snap = Change.snapshot(repo)
            if snap != last:
                if last is not None:                  # skip the first, it is just "here is the repo"
                    ch = Change.from_git(repo)
                    if ch.touched:
                        _report(led, root, ch, last_halt)
                        last_halt = tuple(
                            s.holding_id for s in _sitting(led, root, ch).seats
                            if s.verdict == "halt")
                last = snap
            time.sleep(poll)
    except KeyboardInterrupt:
        print()
        print("  stopped watching.")
    finally:
        led.close()
    return 0


def _sitting(led, root, ch):
    from . import panel
    return panel.sit(led, root, ch, borrowed=transfer.borrowed(root))


def _report(led, root: str, ch: Change, previously_halted: tuple) -> None:
    from . import panel

    s = _sitting(led, root, ch)
    serve.emit("sitting", **s.as_dict())

    halted = [x for x in s.seats if x.verdict == panel.HALT]
    now = tuple(x.holding_id for x in halted)

    if halted:
        for x in halted:
            print(render.watch_halt(x, ch.touched))
    elif previously_halted and not now:
        # It was stopped, and now it is not. This is the only moment that
        # actually shows the tool working, so it gets said out loud.
        print(render.watch_recovered(previously_halted))
        serve.emit("recovered", holdings=list(previously_halted), touched=ch.touched)
    else:
        for x in s.notes:
            print(render.note_line(x))
        if not s.notes:
            print(render.watch_clear(ch.touched))
