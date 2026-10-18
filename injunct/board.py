"""Freeze the ledger and the benchmark into two JSON files, then serve them.

The board is static on purpose: no framework, no build step, and it deploys to
any free static host exactly as it runs locally.
"""
from __future__ import annotations

import json
import shutil
from functools import partial
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path

from .db import Ledger

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def _pick_ledger() -> Path | None:
    for c in (ROOT / ".bench" / "C" / "1" / "ledger.db",
              ROOT / ".live" / "trial" / ".injunct" / "ledger.db",
              ROOT / ".demo" / "ledger.db"):
        if c.is_file():
            return c
    return None


def dump(ledger: Path | None = None) -> dict:
    ledger = Path(ledger) if ledger else _pick_ledger()
    WEB.mkdir(parents=True, exist_ok=True)

    data: dict = {"counts": {"cases": 0, "binding": 0, "persuasive": 0, "overruled": 0},
                  "holdings": [], "cases": []}
    if ledger and ledger.is_file():
        led = Ledger(ledger)
        holdings = led.holdings()
        for h in holdings:
            h["citations"] = led.citations(h["id"])
            h["case"] = led.case(h["case_id"])
        data = {"counts": led.counts(None), "holdings": holdings, "cases": led.cases(),
                "source": ledger.as_posix()}
        led.close()
    (WEB / "data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # A live three-arm run, if one has been done. It is kept separate from
    # report.json on purpose: one is a synthetic 300-run benchmark and the
    # other is a real model, and averaging them would be a lie.
    live = ROOT / "bench" / "live3.json"
    if live.is_file():
        shutil.copyfile(live, WEB / "live.json")

    curve = ROOT / "bench" / "compliance.json"
    if curve.is_file():
        shutil.copyfile(curve, WEB / "compliance.json")

    report = ROOT / "bench" / "report.json"
    if report.is_file():
        # rows are the bulk and the tape needs only the ordered outcomes
        full = json.loads(report.read_text(encoding="utf-8"))
        slim = {k: v for k, v in full.items() if k != "rows"}
        slim["tape"] = {}
        for arm in full.get("arms", []):
            # every seed, in sequence: the tape is all 300 runs, not a sample
            rows = sorted((r for r in full["rows"] if r["arm"] == arm),
                          key=lambda r: (r["seed"], r["order"]))
            slim["tape"][arm] = [{"p": int(r["passed"]), "b": int(bool(r["blocked"])),
                                  "t": r["trap"] or "", "task": r["task"]} for r in rows]
        (WEB / "report.json").write_text(json.dumps(slim, indent=2), encoding="utf-8")
    return data


# What the office is, and what each page needs to be honest. A page with no
# data still renders - it says what is missing instead of drawing nothing -
# but the person serving it should be told before a judge is.
PAGES = [
    ("index.html",     "the front door: everything below, in one list"),
    ("desk.html",      "the desk: live, or the recorded session"),
    ("cabinet.html",   "the docket, and every case file in it"),
    ("chart.html",     "the evidence: does it help, and where does it hurt"),
    ("tape.html",      "three hundred runs, replayed"),
    ("overruled.html", "how a rule loses its authority"),
]

NEEDS = [
    ("data.json",       "python -m injunct dump"),
    ("report.json",     "python -m injunct bench --arms A,C --seeds 1,2,3,4,5"),
    ("compliance.json", "python -m injunct bench --compliance"),
    ("replay.json",     "python -m injunct replay"),
]

# Not required - the pages say so when it is absent, because a live three-arm
# run needs a model and most people cloning this will not have one wired up.
OPTIONAL = [("live.json", "a live three-arm run (needs a model)")]


def missing() -> list[tuple[str, str]]:
    return [(f, cmd) for f, cmd in NEEDS if not (WEB / f).is_file()]


def main(port: int = 8850, ledger: Path | None = None) -> int:
    d = dump(ledger)
    c = d["counts"]
    print(f"  docket: {c['cases']} cases, {c['binding']} binding, "
          f"{c['persuasive']} advisory, {c['overruled']} overruled")
    print()
    for page, what in PAGES:
        print(f"  http://127.0.0.1:{port}/{page:<15} {what}")
    gaps = missing()
    if gaps:
        print()
        print("  missing, so those pages will say so rather than show it:")
        for f, cmd in gaps:
            print(f"    {f:<17} {cmd}")
    print()
    handler = partial(SimpleHTTPRequestHandler, directory=str(WEB))
    try:
        HTTPServer(("127.0.0.1", port), handler).serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
