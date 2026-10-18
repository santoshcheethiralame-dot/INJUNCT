"""The check borrowed from forge, which reads the syntax tree.

We had two regexes trying to spot dangerous calls. A regex cannot tell a call
from a comment, a string, or a variable whose name merely starts the same way,
and all three are false alarms that get a tool switched off.
"""
from pathlib import Path

import pytest

from injunct import packs, templates
from injunct.change import Change


def _check(tmp_path: Path, src: str, added: list[str]):
    (tmp_path / "x.py").write_text(src, encoding="utf-8")
    ch = Change(repo=tmp_path, touched=["x.py"], added={"x.py": added})
    return templates.forge_gate(ch, {"glob": "**/*.py"})


needs_forge = pytest.mark.skipif(not packs.forge_available(),
                                 reason="forge is not installed next door")


@needs_forge
def test_a_real_call_is_caught(tmp_path):
    assert _check(tmp_path, "payload = eval(u)\n", ["payload = eval(u)"])


@needs_forge
@pytest.mark.parametrize("src,line", [
    ("# never eval here\nx = 1\n", "# never eval here"),
    ('msg = "do not eval this"\n', 'msg = "do not eval this"'),
    ("def evaluate(x):\n    return x\n", "def evaluate(x):"),
])
def test_text_that_merely_looks_dangerous_is_not(tmp_path, src, line):
    assert _check(tmp_path, src, [line]) is None


@needs_forge
def test_a_sandbox_escape_through_dunders_is_caught(tmp_path):
    assert _check(tmp_path, "c = o.__class__.__bases__\n", ["c = o.__class__.__bases__"])


@needs_forge
def test_open_is_not_inherited(tmp_path):
    """forge bans open() because a generated tool has no business touching the
    disk. Ordinary application code opens files all day, so that one is
    dropped - a borrowed rule still has to make sense where it is applied."""
    assert _check(tmp_path, "with open('f') as f:\n    pass\n",
                  ["with open('f') as f:"]) is None


@needs_forge
def test_code_that_was_already_there_is_not_this_change_s_fault(tmp_path):
    assert _check(tmp_path, "payload = eval(z)\n", []) is None


def test_it_abstains_when_forge_is_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(packs, "forge_home", lambda: None)
    assert _check(tmp_path, "payload = eval(u)\n", ["payload = eval(u)"]) is None
