"""Deterministic pass/fail for the report fixture. No model anywhere near this.

Two things are checked, and neither is a style opinion:

  1. every view still runs. A signature change that left its callers behind
     raises TypeError here, which is the failure a blast-radius rule exists to
     predict.

  2. if an owner report has been written, it must be correct AND must not ask
     the store once per row. That second half is counted, not timed - a
     stopwatch on a loaded machine is how a benchmark starts lying.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import store                                          # noqa: E402
from views.summary import summary                               # noqa: E402
from views.detail import detail                                 # noqa: E402
from views.export import export                                 # noqa: E402

ROWS = [{"id": i, "name": f"row-{i}", "total": i * 3, "owner": (i % 5) + 1}
        for i in range(50)]

# One query for the whole report is the point; two is slack for an honest
# implementation that also looks something else up. Fifty is the bug.
QUERY_BUDGET = 2


def fail(why):
    print(f"FAIL: {why}")
    sys.exit(1)


# ---- 1. the views still work ------------------------------------------------

try:
    lines = summary(ROWS)
    numbered = detail(ROWS)
    blob = export(ROWS)
except TypeError as e:
    fail(f"a view no longer matches render(): {e}")

if len(lines) != len(ROWS) or len(numbered) != len(ROWS):
    fail("a view dropped rows")
if "row-7" not in blob:
    fail("export lost its content")

# ---- 2. the owner report, if it exists, is correct and not N+1 --------------

from reports import owners as owners_mod                        # noqa: E402

fn = getattr(owners_mod, "owner_names", None)
if fn is not None:
    store.reset()
    got = fn(ROWS)

    if len(got) != len(ROWS):
        fail("owner_names dropped rows")
    for row, out in zip(ROWS, got):
        want = store.OWNERS[row["owner"]]
        if out.get("owner_name") != want:
            fail(f"row {row['id']} got owner_name {out.get('owner_name')!r}, wanted {want!r}")

    if store.CALLS["get"] > QUERY_BUDGET:
        fail(f"owner_names asked the store {store.CALLS['get']} times for "
             f"{len(ROWS)} rows; fetch once outside the loop")

print("PASS: views render, and the owner report is correct and cheap")
