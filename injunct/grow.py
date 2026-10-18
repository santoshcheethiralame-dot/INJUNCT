"""Grow a realistic repository with real history, for `injunct init` to read.

    python -m injunct.grow C:/vdclone/bigdemo

Sixty-odd commits of a small clinic app, committed the way a team actually
works: models change with their migrations, but migrations also land alone
(indexes, data fixes); the API spec changes with a regenerated client; plugins
land with the registry, but the registry also changes alone. That asymmetry is
what lets the miner tell a trigger from a companion. Every commit passes
`python oracle.py` - the history is a history of things that worked.

Stdlib only. Deterministic: the same script grows the same repository twice.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ------------------------------------------------------------------ state ---

state = {
    "models": {},          # name -> [(field, sqltype, pytype)]
    "migrations": [],      # (n, slug, sql)
    "spec": {},            # api types
    "plugins": [],         # (name, doc)
    "tests": {},           # file -> text
    "docs": {},            # file -> text
    "seed_rows": {"patients": [("Asha Rao", "98450 11234"), ("Imran Qureshi", "99001 55210"),
                               ("Meera Nair", "80889 30471"), ("Sandeep Kulkarni", "97417 66502")]},
}

# ---------------------------------------------------------------- render ---

def r_model(name: str) -> str:
    fields = state["models"][name]
    table = name.lower() + "s"
    lines = [f'"""The {name.lower()} record. Every field here must exist in the {table} table."""', "",
             "FIELDS = [" + ", ".join(f'"{f}"' for f, _, _ in fields) + "]",
             "LABELS = {" + ", ".join(f'"{f}": "{f.replace("_", " ").title()}"' for f, _, _ in fields) + "}",
             f'TABLE = "{table}"', ""]
    return chr(10).join(lines)


def r_store() -> str:
    return '''"""The database is whatever the migrations say it is. Nothing else builds it."""
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent


def build(path=":memory:"):
    con = sqlite3.connect(path)
    for sql in sorted((HERE / "migrations").glob("*.sql")):
        con.executescript(sql.read_text(encoding="utf-8"))
    con.commit()
    return con


def rows(con, table, fields):
    cur = con.execute(f"SELECT {', '.join(fields)} FROM {table} ORDER BY id")
    return [dict(zip(fields, row)) for row in cur.fetchall()]
'''


def r_app() -> str:
    return '''"""Bengaluru Dental - the front desk. Standard library only."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import store
import registry
from models import patient

HERE = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        con = store.build()
        if self.path == "/api/patients":
            body = json.dumps(store.rows(con, patient.TABLE, patient.FIELDS)).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
        elif self.path == "/api/plugins":
            body = json.dumps(registry.REGISTRY).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
        else:
            body = (HERE / "static" / "index.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type", "text/html")
        self.end_headers(); self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8000), Handler).serve_forever()
'''


def r_gen() -> str:
    return '''"""The client types are generated. Nobody writes them by hand."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PY = {"int": "int", "str": "str", "bool": "bool", "float": "float"}


def render() -> str:
    spec = json.loads((HERE / "api" / "types.json").read_text(encoding="utf-8"))
    out = ["# GENERATED FILE - run tools/gen.py, do not edit by hand", ""]
    for name, fields in spec.items():
        out.append(f"class {name}:")
        out.append("    __slots__ = (" + ", ".join(f'"{f}"' for f in fields) + ",)")
        for f, t in fields.items():
            out.append(f"    {f}: {PY[t]}")
        out.append("")
    return chr(10).join(out)


if __name__ == "__main__":
    (HERE / "client" / "generated.py").write_text(render(), encoding="utf-8")
    print("generated")
'''


def r_client() -> str:
    PY = {"int": "int", "str": "str", "bool": "bool", "float": "float"}
    out = ["# GENERATED FILE - run tools/gen.py, do not edit by hand", ""]
    for name, fields in state["spec"].items():
        out.append(f"class {name}:")
        out.append("    __slots__ = (" + ", ".join(f'"{f}"' for f in fields) + ",)")
        for f, t in fields.items():
            out.append(f"    {f}: {PY[t]}")
        out.append("")
    return chr(10).join(out)


def r_registry() -> str:
    return ('"""Every plugin has to be declared here. The loader reads nothing else."""' + chr(10) * 2
            + "REGISTRY = [" + chr(10) + "".join(f'    "{n}",' + chr(10) for n, _ in state["plugins"]) + "]" + chr(10))


def r_plugin(name: str, doc: str) -> str:
    return f'"""{doc}"""' + chr(10) * 2 + f'NAME = "{name}"' + chr(10) * 2 + "def run(con):" + chr(10) + "    return NAME" + chr(10)


def r_plugins_doc() -> str:
    rows = "".join(f"| {n} | {d} |" + chr(10) for n, d in state["plugins"])
    return "# Plugins" + chr(10) * 2 + "| name | what it does |" + chr(10) + "|---|---|" + chr(10) + rows


def r_oracle() -> str:
    return '''"""Three things must agree: the models and the database; the spec and the
client; the plugins, the registry and the docs. One command says whether they do."""
import importlib
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

problems = []

# 1. every model field exists in the database the migrations build
import store  # noqa: E402
con = store.build()
for f in sorted((HERE / "models").glob("*.py")):
    if f.name.startswith("_"):
        continue
    m = importlib.import_module(f"models.{f.stem}")
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({m.TABLE})")}
    missing = [x for x in m.FIELDS if x not in cols]
    if missing:
        problems.append(f"no such column: {', '.join(missing)} in {m.TABLE}")

# 2. the client is exactly what the generator would produce
import gen  # noqa: E402
current = (HERE / "client" / "generated.py").read_text(encoding="utf-8")
if current.strip() != gen.render().strip():
    problems.append("client/generated.py has drifted from api/types.json")

# 3. plugins on disk, in the registry, and in the docs agree
on_disk = set()
for f in sorted((HERE / "plugins").glob("*.py")):
    m = re.search(r'^NAME\\s*=\\s*"([^"]+)"', f.read_text(encoding="utf-8"), re.M)
    if m:
        on_disk.add(m.group(1))
import registry  # noqa: E402
declared = set(registry.REGISTRY)
doc_rows = set(re.findall(r"^\\|\\s*([a-z_]+)\\s*\\|", (HERE / "docs" / "plugins.md").read_text(encoding="utf-8"), re.M))
doc_rows.discard("name")
if on_disk != declared:
    problems.append(f"registry.py disagrees with plugins/: {sorted(on_disk ^ declared)}")
if on_disk != doc_rows:
    problems.append(f"docs/plugins.md disagrees with plugins/: {sorted(on_disk ^ doc_rows)}")

if problems:
    print("FAIL: " + "; ".join(problems))
    sys.exit(1)
print("PASS: models match the database, client matches the spec, plugins are declared")
'''


def r_test_models() -> str:
    return '''import store
from models import patient


def test_patients_table_has_every_model_field():
    con = store.build()
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({patient.TABLE})")}
    assert set(patient.FIELDS) <= cols


def test_seed_rows_present():
    con = store.build()
    assert len(store.rows(con, patient.TABLE, patient.FIELDS)) == 4
'''


def r_index() -> str:
    return '''<!doctype html>
<title>Bengaluru Dental</title>
<h1>Bengaluru Dental</h1>
<p>front desk</p>
<script>
fetch("/api/patients").then(r => r.json()).then(rows => {
  const t = document.createElement("table");
  for (const row of rows) { const tr = t.insertRow(); for (const k in row) tr.insertCell().textContent = row[k]; }
  document.body.appendChild(t);
});
</script>
'''

# ------------------------------------------------------------------ repo ----

ROOT: Path
DAY = 0


def w(path: str, text: str) -> None:
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline=chr(10))


def rm(path: str) -> None:
    p = ROOT / path
    if p.exists():
        p.unlink()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def commit(msg: str, hours: float = 9.0) -> None:
    global DAY
    DAY += 1
    when = (datetime(2026, 5, 4) + timedelta(days=DAY * 1.3, hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    env = {**os.environ, "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when,
           "GIT_AUTHOR_NAME": "Priya Menon", "GIT_AUTHOR_EMAIL": "priya@bengalurudental.example",
           "GIT_COMMITTER_NAME": "Priya Menon", "GIT_COMMITTER_EMAIL": "priya@bengalurudental.example"}
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    r = subprocess.run(["python", "oracle.py"], cwd=ROOT, capture_output=True, text=True)
    if (ROOT / "oracle.py").exists() and r.returncode != 0:
        raise SystemExit(f"history must be green; commit '{msg}' fails: {r.stdout}{r.stderr}")
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, env=env, check=True)


# ----------------------------------------------------------------- steps ----

def add_migration(slug: str, sql: str) -> None:
    n = len(state["migrations"]) + 1
    state["migrations"].append((n, slug, sql))
    w(f"migrations/{n:03d}_{slug}.sql", sql)


def add_model(name: str, fields: list[tuple[str, str, str]], seed: list[tuple] | None = None) -> None:
    state["models"][name] = list(fields)
    table = name.lower() + "s"
    cols = ",".join(chr(10) + f"    {f:<10} {t}" for f, t, _ in fields)
    sql = f"CREATE TABLE {table} ({cols}" + chr(10) + ");" + chr(10)
    if seed:
        names = ", ".join(f for f, _, _ in fields[1:])
        vals = ("," + chr(10) + "    ").join("(" + ", ".join(repr(v) for v in row) + ")" for row in seed)
        sql += f"INSERT INTO {table} ({names}) VALUES" + chr(10) + "    " + vals + ";" + chr(10)
    w(f"models/{name.lower()}.py", r_model(name))
    add_migration(f"create_{table}", sql)


def add_field(model: str, field: str, sqltype: str, pytype: str = "str") -> None:
    state["models"][model].append((field, sqltype, pytype))
    w(f"models/{model.lower()}.py", r_model(model))
    add_migration(f"{model.lower()}_{field}", f"ALTER TABLE {model.lower()}s ADD COLUMN {field} {sqltype};" + chr(10))


def spec_set(name: str, fields: dict) -> None:
    state["spec"][name] = fields
    w("api/types.json", json.dumps(state["spec"], indent=2) + chr(10))
    w("client/generated.py", r_client())


def add_plugin(name: str, doc: str) -> None:
    state["plugins"].append((name, doc))
    w(f"plugins/{name}.py", r_plugin(name, doc))
    w("registry.py", r_registry())
    w("docs/plugins.md", r_plugins_doc())


def registry_touch(note: str) -> None:
    """The registry changes on its own too - a comment, an ordering, a note."""
    w("registry.py", r_registry().replace('"""Every plugin', f'"""{note}' + chr(10) + "Every plugin", 1))


def main(target: str) -> None:
    global ROOT
    ROOT = Path(target).resolve()
    if ROOT.exists() and any(ROOT.iterdir()):
        raise SystemExit(f"{ROOT} is not empty")
    ROOT.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", "main")
    git("config", "core.autocrlf", "false")
    w(".gitignore", "__pycache__/" + chr(10) + "*.pyc" + chr(10) + ".pytest_cache/" + chr(10))

    # ---- week 1: the skeleton
    w("README.md", "# Bengaluru Dental" + chr(10) * 2 + "The front desk app. Standard library only." + chr(10))
    commit("Start the front desk app")
    w("store.py", r_store()); w("models/__init__.py", "")
    add_model("Patient", [("id", "INTEGER PRIMARY KEY", "int"), ("name", "TEXT NOT NULL", "str"), ("phone", "TEXT", "str")],
              seed=state["seed_rows"]["patients"])
    w("oracle.py", '''import sys, store
from models import patient
con = store.build()
cols = {r[1] for r in con.execute(f"PRAGMA table_info({patient.TABLE})")}
missing = [x for x in patient.FIELDS if x not in cols]
if missing: print("FAIL: no such column:", missing); sys.exit(1)
print("PASS")
''')
    commit("Patient model, first migration, and a check that they agree")
    w("app.py", r_app().replace("import registry" + chr(10), "").replace(
        '        elif self.path == "/api/plugins":' + chr(10) + '            body = json.dumps(registry.REGISTRY).encode()' + chr(10) + '            self.send_response(200); self.send_header("Content-Type", "application/json")' + chr(10), ""))
    w("static/index.html", r_index())
    commit("Serve the patient list over HTTP")
    w("tests/test_models.py", r_test_models())
    commit("First tests")
    w("docs/setup.md", "# Setup" + chr(10) * 2 + "`python app.py` and open http://127.0.0.1:8000" + chr(10))
    commit("Setup notes")

    # ---- week 2: the API spec and its generated client
    w("tools/gen.py", r_gen())
    spec_set("Patient", {"id": "int", "name": "str", "phone": "str"})
    commit("API types spec and a generator for the client")
    add_field("Patient", "email", "TEXT")
    spec_set("Patient", {"id": "int", "name": "str", "phone": "str", "email": "str"})
    commit("Patients can have an email")
    add_migration("index_patients_name", "CREATE INDEX idx_patients_name ON patients(name);" + chr(10))
    commit("Index patients by name")
    w("docs/setup.md", (ROOT / "docs/setup.md").read_text() + chr(10) + "Run `python oracle.py` before you push." + chr(10))
    commit("Document the check")
    w("README.md", (ROOT / "README.md").read_text() + chr(10) + "See docs/setup.md." + chr(10))
    commit("README points at the docs")

    # ---- week 3: plugins
    w("registry.py", '"""Every plugin has to be declared here. The loader reads nothing else."""' + chr(10) * 2 + "REGISTRY = [" + chr(10) + "]" + chr(10))
    (ROOT / "plugins").mkdir(exist_ok=True); w("plugins/__init__.py", "")
    w("docs/plugins.md", r_plugins_doc())
    w("app.py", r_app())
    w("oracle.py", r_oracle())
    commit("A plugin registry, and the check now covers spec, client and plugins")
    add_plugin("csv_export", "Export the patient list as CSV.")
    commit("csv_export plugin")
    add_field("Patient", "date_of_birth", "TEXT")
    commit("Patients have a date of birth")
    add_plugin("reminder_sms", "Text a patient the day before.")
    commit("reminder_sms plugin")
    registry_touch("Plugins load in this order.")
    commit("Note the load order in the registry")
    w("tests/test_registry.py", '''import registry
from pathlib import Path

def test_every_plugin_file_is_registered():
    names = {p.stem for p in Path("plugins").glob("*.py") if not p.stem.startswith("_")}
    assert names == set(registry.REGISTRY)
''')
    commit("Test that every plugin is registered")

    # ---- week 4: appointments
    add_model("Appointment", [("id", "INTEGER PRIMARY KEY", "int"), ("patient_id", "INTEGER NOT NULL", "int"), ("at", "TEXT NOT NULL", "str")])
    spec_set("Appointment", {"id": "int", "patient_id": "int", "at": "str"})
    commit("Appointment model, migration, and API type")
    add_migration("index_appointments_patient", "CREATE INDEX idx_appt_patient ON appointments(patient_id);" + chr(10))
    commit("Index appointments by patient")
    w("static/index.html", r_index().replace("<p>front desk</p>", "<p>front desk - today</p>"))
    commit("Front desk page says which day it is")
    add_field("Appointment", "notes", "TEXT")
    commit("Appointment notes")
    w("tests/test_appointments.py", '''import store
from models import appointment

def test_appointments_table_exists():
    con = store.build()
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({appointment.TABLE})")}
    assert set(appointment.FIELDS) <= cols
''')
    commit("Appointment tests")
    add_plugin("waitlist", "Fill a cancelled slot from the waitlist.")
    commit("waitlist plugin")
    spec_set("Appointment", {"id": "int", "patient_id": "int", "at": "str", "notes": "str"})
    commit("Appointment notes reach the API")
    add_migration("backfill_patient_email", "UPDATE patients SET email = lower(replace(name, ' ', '.')) || '@example.com' WHERE email IS NULL;" + chr(10))
    commit("Backfill placeholder emails")
    w("docs/plugins.md", r_plugins_doc() + chr(10) + "Plugins run after the day closes." + chr(10))
    commit("Explain when plugins run")

    # ---- week 5: staff, more habits
    add_model("Staff", [("id", "INTEGER PRIMARY KEY", "int"), ("name", "TEXT NOT NULL", "str"), ("role", "TEXT NOT NULL", "str")])
    commit("Staff model and migration")
    spec_set("Staff", {"id": "int", "name": "str", "role": "str"})
    commit("Staff API type")
    registry_touch("Plugins load in this order. csv_export must stay first.")
    commit("Pin csv_export first in the registry")
    add_field("Patient", "insurer", "TEXT")
    commit("Track each patient's insurer")
    add_plugin("insurance_claim", "Draft a claim for the insurer.")
    commit("insurance_claim plugin")
    add_migration("index_patients_phone", "CREATE INDEX idx_patients_phone ON patients(phone);" + chr(10))
    commit("Index patients by phone")
    add_migration("index_staff_role", "CREATE INDEX idx_staff_role ON staffs(role);" + chr(10))
    commit("Index staff by role")
    w("tests/test_models.py", r_test_models() + chr(10) + "def test_email_backfilled():" + chr(10) + "    con = store.build()" + chr(10) + "    assert all(r['email'] for r in store.rows(con, patient.TABLE, patient.FIELDS))" + chr(10))
    commit("Test the email backfill")
    w("README.md", (ROOT / "README.md").read_text() + chr(10) + "## Plugins" + chr(10) * 2 + "See docs/plugins.md." + chr(10))
    commit("README mentions plugins")
    add_field("Staff", "phone", "TEXT")
    commit("Staff phone numbers")
    spec_set("Staff", {"id": "int", "name": "str", "role": "str", "phone": "str"})
    commit("Staff phone reaches the API")
    add_field("Appointment", "staff_id", "INTEGER")
    commit("Appointments are assigned to staff")
    spec_set("Appointment", {"id": "int", "patient_id": "int", "at": "str", "notes": "str", "staff_id": "int"})
    commit("staff_id reaches the API")
    w("static/index.html", r_index().replace("<h1>Bengaluru Dental</h1>", "<h1>Bengaluru Dental</h1>" + chr(10) + "<nav>patients | appointments | staff</nav>"))
    commit("Navigation on the front page")
    registry_touch("Plugins load in this order. csv_export must stay first; reminder_sms needs the phone column.")
    commit("Registry note on reminder_sms")

    # ---- week 6: hardening
    add_migration("patients_email_unique", "CREATE UNIQUE INDEX idx_patients_email ON patients(email);" + chr(10))
    commit("Emails are unique")
    add_plugin("audit_log", "Write every change to an append-only log.")
    commit("audit_log plugin")
    w(".pre-commit-config.yaml", """repos:
- repo: local
  hooks:
  - id: oracle
    name: the repo's own check
    entry: python oracle.py
    language: system
    files: ^api/.*
""")
    commit("pre-commit runs the check whenever the API spec changes")
    add_migration("index_patients_insurer", "CREATE INDEX idx_patients_insurer ON patients(insurer);" + chr(10))
    commit("Index patients by insurer")
    w("docs/setup.md", (ROOT / "docs/setup.md").read_text() + chr(10) + "## Migrations" + chr(10) * 2 + "Numbered, applied in order, never edited after they land." + chr(10))
    commit("Document the migration rule")
    add_field("Patient", "phone_verified", "INTEGER DEFAULT 0", "bool")
    commit("Track whether a phone number was verified")
    spec_set("Patient", {"id": "int", "name": "str", "phone": "str", "email": "str", "phone_verified": "bool"})
    commit("phone_verified reaches the API")
    add_migration("backfill_phone_verified", "UPDATE patients SET phone_verified = 1 WHERE phone IS NOT NULL;" + chr(10))
    commit("Existing phones count as verified")
    w("tests/test_api_types.py", '''import sys
from pathlib import Path
sys.path.insert(0, str(Path("tools")))
import gen

def test_client_matches_spec():
    assert Path("client/generated.py").read_text(encoding="utf-8").strip() == gen.render().strip()
''')
    commit("Test that the client matches the spec")
    registry_touch("Plugins load in this order. csv_export must stay first; reminder_sms needs the phone column; audit_log last.")
    commit("audit_log goes last")
    add_field("Staff", "active", "INTEGER DEFAULT 1", "bool")
    commit("Staff can be deactivated")
    add_plugin("recall_letters", "Six-month recall letters.")
    commit("recall_letters plugin")
    w("static/index.html", (ROOT / "static/index.html").read_text().replace("<p>front desk", "<p id=count></p>" + chr(10) + "<p>front desk", 1))
    commit("Show the patient count")
    add_migration("index_appointments_at", "CREATE INDEX idx_appt_at ON appointments(at);" + chr(10))
    commit("Index appointments by time")
    w("docs/api.md", "# API" + chr(10) * 2 + "`GET /api/patients`, `GET /api/plugins`. Types in `api/types.json`; the client is generated." + chr(10))
    commit("API docs")
    add_field("Appointment", "status", "TEXT DEFAULT 'booked'")
    commit("Appointment status")
    spec_set("Appointment", {"id": "int", "patient_id": "int", "at": "str", "notes": "str", "staff_id": "int", "status": "str"})
    commit("status reaches the API")
    registry_touch("Plugins load in this order. csv_export must stay first; reminder_sms needs the phone column; audit_log last. recall_letters is monthly.")
    commit("Registry note on recall_letters")
    w("README.md", (ROOT / "README.md").read_text() + chr(10) + "## Checks" + chr(10) * 2 + "`python oracle.py` - models vs database, spec vs client, plugins vs registry." + chr(10))
    commit("README lists the checks")
    add_migration("backfill_appointment_status", "UPDATE appointments SET status = 'booked' WHERE status IS NULL;" + chr(10))
    commit("Backfill appointment status")
    add_migration("index_appointments_status", "CREATE INDEX idx_appt_status ON appointments(status);" + chr(10))
    commit("Index appointments by status")
    add_field("Patient", "preferred_language", "TEXT")
    commit("Patients have a preferred language")
    w("tests/test_models.py", (ROOT / "tests/test_models.py").read_text() + chr(10) + "def test_language_column():" + chr(10) + "    con = store.build()" + chr(10) + "    assert 'preferred_language' in {r[1] for r in con.execute('PRAGMA table_info(patients)')}" + chr(10))
    commit("Test the language column")

    n = git("rev-list", "--count", "HEAD").strip()
    print(f"grew {ROOT} : {n} commits, {len(state['models'])} models, {len(state['migrations'])} migrations, "
          f"{len(state['plugins'])} plugins, {len(state['spec'])} API types")
    print("history is green: every commit passed python oracle.py")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bigdemo")
