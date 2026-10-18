"""Hallucination, context, cost and documentation - the four things people
actually complain about, plus the safety detectors."""
import subprocess
import tempfile
from pathlib import Path

import pytest

from injunct import efficiency, graph, packs, templates
from injunct.change import Change


def repo_with(files: dict, then: dict) -> Change:
    d = Path(tempfile.mkdtemp()) / "r"
    d.mkdir(parents=True)
    for name, text in files.items():
        f = d / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    for c in (["git", "init", "-q"], ["git", "add", "-A"],
              ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "s"]):
        subprocess.run(c, cwd=d, capture_output=True)
    for name, text in then.items():
        f = d / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return Change.from_git(d)


# ---- context graphing: blast radius --------------------------------------

def test_changing_a_signature_names_the_callers_left_behind():
    ch = repo_with(
        {"core.py": "def parse(a, b):\n    return a\n",
         "one.py": "from core import parse\n\ndef go():\n    return parse(1, 2)\n",
         "two.py": "from core import parse\n\ndef run():\n    return parse(3, 4)\n"},
        {"core.py": "def parse(a, b, c):\n    return a\n"})
    out = templates.fires("blast_radius", {}, ch)
    assert "parse() changed shape" in out
    assert "2 caller(s)" in out and "one.py" in out


def test_updating_the_callers_too_is_not_flagged():
    ch = repo_with(
        {"core.py": "def parse(a, b):\n    return a\n",
         "one.py": "from core import parse\n\ndef go():\n    return parse(1, 2)\n"},
        {"core.py": "def parse(a, b, c):\n    return a\n",
         "one.py": "from core import parse\n\ndef go():\n    return parse(1, 2, 3)\n"})
    assert templates.fires("blast_radius", {}, ch) is None


def test_a_function_nobody_calls_is_not_a_problem():
    ch = repo_with({"core.py": "def lonely(a):\n    return a\n"},
                   {"core.py": "def lonely(a, b):\n    return a\n"})
    assert templates.fires("blast_radius", {}, ch) is None


# ---- cost ----------------------------------------------------------------

@pytest.mark.parametrize("src,want", [
    ("def f(xs):\n    for a in xs:\n        for b in xs:\n            pass\n", "nested loop"),
    ("def f(xs, ids):\n    for a in xs:\n        if a in ids:\n            pass\n", "O(n) each time"),
    ("def f(xs):\n    s = ''\n    for a in xs:\n        s += 'x'\n", "collect and join"),
    ("def f(xs):\n    for a in xs:\n        r = db.query(a)\n", "N+1"),
])
def test_the_quadratic_shapes_are_recognised(src, want):
    found = " ".join(efficiency.findings(src))
    assert want in found, found


def test_efficient_code_is_left_alone():
    assert efficiency.findings(
        "def f(xs):\n    seen = set(xs)\n    return [x for x in xs if x in seen]\n") == []


def test_only_the_lines_this_change_added_are_blamed():
    """A repo full of existing nested loops is not this change's fault, and a
    gate that says otherwise gets switched off within the hour."""
    ch = repo_with(
        {"svc.py": "def old(rows):\n    for r in rows:\n        for q in rows:\n            pass\n"},
        {"svc.py": "def old(rows):\n    for r in rows:\n        for q in rows:\n            pass\n\n"
                   "def new(rows):\n    for r in rows:\n        x = db.query(r)\n"})
    out = templates.fires("no_quadratic", {}, ch)
    assert out and "N+1" in out, out


def test_a_pre_existing_problem_alone_is_not_reported():
    ch = repo_with(
        {"svc.py": "def old(rows):\n    for r in rows:\n        for q in rows:\n            pass\n"},
        {"README.md": "hello\n"})
    assert templates.fires("no_quadratic", {}, ch) is None


# ---- borrowed judgement --------------------------------------------------

def test_the_sleeper_gate_abstains_when_sleeper_is_absent(monkeypatch):
    """A gate that fires because a dependency is missing fires on everything."""
    monkeypatch.setattr(packs, "sleeper_home", lambda: None)
    ch = repo_with({"a.py": "import os\n"}, {"a.py": "import os\nimport nope\n"})
    monkeypatch.setattr("injunct.shell.run", lambda *a, **k: type(
        "R", (), {"returncode": 1, "stdout": "", "stderr": "no module"})())
    assert templates.fires("sleeper_gate", {"gate": "deps"}, ch) is None


def test_sleeper_rules_only_install_when_it_is_there(monkeypatch):
    monkeypatch.setattr(packs, "sleeper_available", lambda: False)
    assert packs.sleeper_rules() == []


# ---- safety --------------------------------------------------------------

def test_the_new_safety_regexes_catch_what_they_claim():
    import re
    by_key = {r["key"]: r for r in packs.RULES}
    assert re.search(by_key["swallowed"]["regex"], "except ValueError:  pass")
    assert not re.search(by_key["swallowed"]["regex"], "except ValueError:  raise")
    assert re.search(by_key["destructive_sql"]["regex"], "ALTER TABLE t DROP COLUMN c;")
    assert not re.search(by_key["destructive_sql"]["regex"], "ALTER TABLE t ADD COLUMN c TEXT;")
    assert re.search(by_key["removed_raise"]["regex"], "    raise ValueError('x')")


def test_no_pack_regex_carries_a_control_character():
    """`\b` written through a shell heredoc becomes a literal backspace, and the
    rule then silently matches nothing."""
    for r in packs.RULES:
        rx = r.get("regex")
        if rx:
            assert not any(ord(c) < 32 for c in rx), (r["key"], repr(rx))
