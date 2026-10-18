"""A small repository whose AGENTS.md lands in every bucket coverage has.

    injunct coverage --demo [DIR]       injunct hindsight --demo [DIR]

The history is written so each outcome is earned rather than staged. Three
mistakes land and are each fixed later by a commit that rewrites the line the
mistake wrote: a debug print() in app/, a model without its migration, and a
`# type: ignore` in models/. Trusting every commit, the history breaks all
three rules and none can bind (0%); leaving out the three commits a later
commit had to fix, all three bind (33%), and hindsight catches every mistake
with a binding rule. The changelog rule stays unproven, because "Cancel a
booking" skipped it and nobody ever fixed that.

Gemma 4's answers for this exact repository ship with the package
(coverdemo.json), so the demo runs with no network and no key, and any answer
can be checked by rerunning against a live model.

Stdlib only. Deterministic: the same script builds the same repository twice.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

CACHE = Path(__file__).with_name("coverdemo.json")
MODEL = "gemma-4-26b-a4b-it"

AGENTS = """# Working on the clinic app

This repository is a small clinic scheduling app in Python.

## Rules

- When you change a model in `models/`, add a migration under `migrations/` in the same commit.
- Never hand-edit `client/generated.py`; it is regenerated from `api/spec.json`.
- Do not leave `print(` debugging calls in `app/`.
- Never add `# type: ignore` to anything under `models/`.
- Update `CHANGELOG.md` whenever you change code in `app/`.
- Write clear, descriptive commit messages.
- Open an issue and wait for a maintainer before starting a large refactor.
- Make sure the app still starts and serves the booking page.
- Keep functions small and focused.
"""

# (message, {path: text}). Later entries overwrite earlier text for the same path.
HISTORY = [
    ("Start the clinic app", {
        "AGENTS.md": AGENTS, "CHANGELOG.md": "# Changelog\n",
        "app/__init__.py": "", "app/booking.py": "def book(slot):\n    return {'slot': slot}\n",
        "models/__init__.py": "", "models/patient.py": "class Patient:\n    name: str\n",
        "migrations/001_init.sql": "CREATE TABLE patient (name TEXT);\n",
        "api/spec.json": '{"Patient": {"name": "str"}}\n',
        "client/generated.py": "# GENERATED from api/spec.json\nclass Patient: ...\n",
        "tools/gen.py": "print('regenerating client')\n",
    }),
    ("Add phone to Patient", {
        "models/patient.py": "class Patient:\n    name: str\n    phone: str\n",
        "migrations/002_phone.sql": "ALTER TABLE patient ADD phone TEXT;\n",
    }),
    ("Booking returns the doctor", {
        "app/booking.py": "def book(slot, doctor=None):\n    return {'slot': slot, 'doctor': doctor}\n",
        "CHANGELOG.md": "# Changelog\n- booking returns the doctor\n",
    }),
    ("Add Appointment model", {
        "models/appointment.py": "class Appointment:\n    slot: str\n",
        "migrations/003_appointment.sql": "CREATE TABLE appointment (slot TEXT);\n",
    }),
    ("quick debug for the double-booking bug", {
        "app/booking.py": ("def book(slot, doctor=None):\n    print('booking', slot)\n"
                           "    return {'slot': slot, 'doctor': doctor}\n"),
    }),
    ("Regenerate client from the spec", {
        "api/spec.json": '{"Patient": {"name": "str", "phone": "str"}}\n',
        "client/generated.py": "# GENERATED from api/spec.json\nclass Patient: ...  # phone\n",
    }),
    ("Index appointment slots", {
        "migrations/004_slot_index.sql": "CREATE INDEX slot_idx ON appointment(slot);\n",
    }),
    ("Appointment gets a doctor", {
        "models/appointment.py": "class Appointment:\n    slot: str\n    doctor: str\n",
        "migrations/005_doctor.sql": "ALTER TABLE appointment ADD doctor TEXT;\n",
    }),
    ("Fix stray debug print in booking", {
        "app/booking.py": "def book(slot, doctor=None):\n    return {'slot': slot, 'doctor': doctor}\n",
        "CHANGELOG.md": "# Changelog\n- booking returns the doctor\n- fix double booking\n",
    }),
    ("Cancel a booking", {
        "app/cancel.py": "def cancel(slot):\n    return {'cancelled': slot}\n",
    }),
    ("Patient email", {
        "models/patient.py": "class Patient:\n    name: str\n    phone: str\n    email: str\n",
        "migrations/006_email.sql": "ALTER TABLE patient ADD email TEXT;\n",
    }),
    # Two more mistakes, each repaired later by a commit that rewrites the very
    # line the mistake wrote - which is what lets SZZ trace the fix home.
    ("Add Visit model", {
        "models/visit.py": "class Visit:\n    patient: str\n    when: str\n",
    }),
    ("Silence the Appointment type error", {
        "models/appointment.py": ("class Appointment:\n    slot: str\n    doctor: str\n"
                                  "    room: int = None  # type: ignore\n"),
    }),
    ("Validate booking slots", {
        "app/booking.py": ("def book(slot, doctor=None):\n    if not slot:\n        raise ValueError('slot')\n"
                           "    return {'slot': slot, 'doctor': doctor}\n"),
        "CHANGELOG.md": ("# Changelog\n- booking returns the doctor\n- fix double booking\n"
                         "- booking slots are validated\n"),
    }),
    ("Fix Visit: add the missing migration and store a real date", {
        "models/visit.py": "class Visit:\n    patient: str\n    when: date\n",
        "migrations/007_visit.sql": "CREATE TABLE visit (patient TEXT, when DATE);\n",
    }),
    ("Fix Appointment.room properly instead of ignoring the type", {
        "models/appointment.py": ("class Appointment:\n    slot: str\n    doctor: str\n"
                                  "    room: int | None = None\n"),
        "migrations/008_room.sql": "ALTER TABLE appointment ADD room INTEGER;\n",
    }),
]


def build(dest: Path) -> Path:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "clinic", "GIT_AUTHOR_EMAIL": "clinic@example.com",
           "GIT_COMMITTER_NAME": "clinic", "GIT_COMMITTER_EMAIL": "clinic@example.com"}

    def git(*args, date=None):
        e = {**env, **({"GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date} if date else {})}
        subprocess.run(["git", "-C", str(dest), *args], check=True, capture_output=True, env=e)

    git("init", "-q")
    for n, (msg, files) in enumerate(HISTORY):
        for path, text in files.items():
            p = dest / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text.encode("utf-8"))
        git("add", "-A")
        git("commit", "-q", "-m", msg, date=f"2026-09-{n + 1:02d}T10:00:00+05:30")
    return dest
