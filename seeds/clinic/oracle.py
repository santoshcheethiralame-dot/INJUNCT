"""Deterministic pass/fail. No model anywhere near this."""
import sys

import store
from models.patient import FIELDS

try:
    con = store.build()
    rows = store.patients(con, FIELDS)
    assert len(rows) == 4, f"expected 4 patients, got {len(rows)}"
except Exception as e:
    print(f"FAIL: {e}")
    sys.exit(1)
print(f"PASS: {len(rows)} patients, {len(FIELDS)} fields")
