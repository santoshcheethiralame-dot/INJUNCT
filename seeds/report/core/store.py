"""Where owner names come from.

Every lookup is counted. That is not instrumentation for its own sake: it lets
the oracle tell one query from fifty without timing anything, so "is this
quadratic?" is answered deterministically rather than by a stopwatch that goes
flaky on a loaded machine.
"""

OWNERS = {1: "asha", 2: "ravi", 3: "meera", 4: "juan", 5: "lin"}

CALLS = {"get": 0, "all": 0}


def reset():
    CALLS["get"] = 0
    CALLS["all"] = 0


class Store:
    def get(self, owner_id):
        """One owner. Cheap once, ruinous inside a loop."""
        CALLS["get"] += 1
        return OWNERS.get(owner_id, "unknown")

    def all(self):
        """Every owner, in one go."""
        CALLS["all"] += 1
        return dict(OWNERS)
