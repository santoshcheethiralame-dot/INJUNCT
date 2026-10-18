"""Cross-repo precedent.

A lesson learned in one repository is worth something in the next one, but not
immediately: one repo's layout is not evidence about another's. The rule here is
deliberately conservative — a holding only becomes GLOBAL once the same rule has
been derived independently in two different repositories. One sighting is a
local habit; two is a pattern.

The global ledger is an ordinary ledger at ~/.injunct/global.db, so everything
that reads a ledger already reads this.
"""
from __future__ import annotations

import json
from pathlib import Path

from .db import Ledger, ledger_path

MIN_REPOS = 2


def _global() -> Ledger:
    return Ledger(ledger_path(Path.home(), glob=True))


def note(repo: str, template: str, params: dict, says: str, status: str,
         led: Ledger | None = None) -> dict:
    """Record that this repo derived this rule, and promote if it is now shared."""
    if template == "prose":
        return {"scope": "repo", "repos": 1}
    g = led or _global()
    repo = str(Path(repo).resolve())

    same = [h for h in g.holdings() if h["template"] == template and h["params"] == params]
    seen = {h["repo"] for h in same}

    if repo not in seen:
        run_id = g.open_run(repo, f"derived: {says}", arm="transfer")
        g.close_run(run_id, "fail")
        case_id = g.file_case(run_id, repo, "cross_repo", "high", says, [],
                              json.dumps({"origin": repo}))
        g.establish(case_id, repo, template, params, says, status="persuasive",
                    scope="repo", empanel={"note": "sighting recorded from another repository"})
        seen.add(repo)
        same = [h for h in g.holdings() if h["template"] == template and h["params"] == params]

    if len(seen) >= MIN_REPOS:
        # binding across repos only where it was trusted in every repo that saw it
        everywhere = status == "binding" and all(
            h["empanel"].get("note") or h["status"] != "persuasive" for h in same)
        for h in same:
            g.set_status(h["id"], "binding" if everywhere else "persuasive")
            g.con.execute("UPDATE holdings SET scope='global' WHERE id=?", (h["id"],))
        g.con.commit()

    out = {"scope": "global" if len(seen) >= MIN_REPOS else "repo", "repos": len(seen)}
    if led is None:
        g.close()
    return out


def borrowed(repo: str, led: Ledger | None = None) -> list[dict]:
    """Global holdings, which apply to a repo that has never failed this way."""
    g = led or _global()
    rows = [h for h in g.holdings() if h["scope"] == "global"]
    if led is None:
        g.close()
    return rows
