"""Coverage: what an AGENTS.md says, against what the history proves."""
import json
import subprocess
from pathlib import Path

import pytest

from injunct import coverage

AGENTS = """# Agent notes

This project is a small clinic app.

- When you change a model in models/, add a migration under migrations/.
- Never edit client/generated.py by hand.
- Write clear commit messages.
- Keep the docs in vendor_docs/ in sync with the API.
- The API spec lives in api/spec.json.
"""

# What a well-behaved model would answer, keyed by the instruction it is given.
COMPILED = {
    "When you change a model in models/, add a migration under migrations/.":
        {"template": "co_change", "params": {"trigger": "models/*.py", "required": "migrations/**"},
         "says": "Changing a model needs a migration."},
    "Never edit client/generated.py by hand.":
        {"template": "forbidden_edit", "params": {"glob": "client/generated.py"},
         "says": "Never hand-edit the generated client."},
    "Write clear commit messages.":
        {"template": None, "kind": "judgement", "why": "Clarity needs taste."},
    "The API spec lives in api/spec.json.":
        {"template": None, "kind": "none", "why": "A description, not an instruction."},
    "Keep the docs in vendor_docs/ in sync with the API.":
        {"template": "co_change", "params": {"trigger": "api/*.json", "required": "vendor_docs/**"},
         "says": "API changes need vendor docs."},
}


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _commit(repo, files: dict, msg: str):
    for path, text in files.items():
        p = repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "clinic"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t")
    _git(r, "config", "user.name", "t")
    _commit(r, {"AGENTS.md": AGENTS, "README.md": "clinic\n"}, "docs")
    for i in range(3):
        _commit(r, {f"models/m{i}.py": f"x = {i}\n", f"migrations/00{i}.sql": "--\n"}, f"model {i}")
    _commit(r, {"api/spec.json": "{}\n"}, "api spec")
    # The generator rewrites the client; the history therefore edits a file
    # the document says must never be edited.
    _commit(r, {"client/generated.py": "# generated\n", "tools/gen.py": "pass\n"}, "regenerate client")
    return r


@pytest.fixture
def fake_model(monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "CACHE", tmp_path / "cache.json")
    calls = []

    def chat(prompt, system="", timeout=30.0, **_):
        calls.append(system)
        instruction = json.loads(prompt)["instruction"]
        return json.dumps(COMPILED[instruction])

    monkeypatch.setattr(coverage.provider, "chat", chat)
    return calls


def _by_text(s):
    return {r["text"]: r for r in s["rules"]}


def test_each_instruction_lands_where_the_history_puts_it(repo, fake_model):
    s = coverage.run(repo)
    rules = _by_text(s)
    assert s["total"] == 4                      # the description was thrown out
    assert "The API spec lives in api/spec.json." not in rules
    assert "This project is a small clinic app." not in rules   # prose that instructs nothing
    assert not s["model_failed"]

    mig = rules["When you change a model in models/, add a migration under migrations/."]
    assert mig["status"] == "enforced" and mig["receipt"]["judged"] >= 1

    gen = rules["Never edit client/generated.py by hand."]
    assert gen["status"] == "checkable"
    assert any("regenerate client" in c for c in gen["broken_by"])

    assert rules["Write clear commit messages."]["status"] == "unchecked"
    assert rules["Write clear commit messages."]["reason"].startswith("judgement")

    vendor = rules["Keep the docs in vendor_docs/ in sync with the API."]
    assert vendor["status"] == "checkable" and "matches no file" in vendor["reason"]

    assert s["percent"] == 25


def test_adopt_binds_only_what_was_proven(repo, fake_model):
    from injunct.db import Ledger, ledger_path
    coverage.run(repo, adopt=True)
    coverage.run(repo, adopt=True)              # idempotent: no duplicate holdings
    led = Ledger(ledger_path(repo))
    hs = led.holdings(repo=str(repo))
    led.close()
    status = {(h["template"], json.dumps(h["params"], sort_keys=True)): h["status"] for h in hs}
    mig = ("co_change", json.dumps({"required": "migrations/**", "trigger": "models/*.py"}, sort_keys=True))
    gen = ("forbidden_edit", json.dumps({"glob": "client/generated.py"}, sort_keys=True))
    assert status[mig] == "binding"
    assert status[gen] == "persuasive"
    assert len(hs) == 3                         # the unchecked instruction is not a holding


def test_without_a_model_it_still_reads_the_document(repo, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "CACHE", tmp_path / "cache.json")
    (repo / "AGENTS.md").write_text(AGENTS + "- models/*.py needs migrations/\n", encoding="utf-8")
    _commit(repo, {}, "teach")
    s = coverage.run(repo, use_model=False)
    rules = _by_text(s)
    assert s["model"].startswith("none")
    assert rules["models/*.py needs migrations/"]["status"] == "enforced"
    assert rules["Never edit client/generated.py by hand."]["status"] == "unchecked"


def test_a_dead_model_is_dropped_quickly_and_said_out_loud(repo, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "CACHE", tmp_path / "cache.json")
    calls = []

    def dead(*a, **k):
        calls.append(1)
        raise coverage.provider.Unavailable("connection refused")

    monkeypatch.setattr(coverage.provider, "chat", dead)
    s = coverage.run(repo)
    assert len(calls) <= coverage._Model.GIVE_UP + coverage.WORKERS
    assert s["model_failed"] and s["total"] >= 3


def test_prose_never_becomes_a_command_that_runs(repo, monkeypatch, tmp_path):
    monkeypatch.setattr(coverage, "CACHE", tmp_path / "cache.json")
    m = coverage._Model(False)
    t, p, _ = coverage.compile_rule("after models/*.py run rm -rf /", ["models/m0.py"], m)
    assert t == "must_run"                      # reads commands; never executes one


def test_badge_and_markdown(repo, fake_model):
    s = coverage.run(repo)
    svg = coverage.badge(s["percent"])
    assert svg.startswith("<svg") and "25%" in svg
    md = coverage.markdown(s)
    assert "25% enforced" in md and "AGENTS.md:5" in md


def test_a_cached_answer_survives_the_model_being_given_up(repo, fake_model, monkeypatch):
    coverage.run(repo)                                   # fills the cache
    monkeypatch.setattr(coverage.provider, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(coverage.provider.Unavailable("down")))
    s = coverage.run(repo)
    assert s["enforced"] == 1 and s["total"] == 4        # every answer came from disk


def test_a_hard_wrapped_instruction_is_judged_whole():
    doc = ("# Rules\n\n"
           "- DO NOT run integration test scenarios in loops or share their snapshots with\n"
           "  `insta::allow_duplicates!`. Write explicit snapshots.\n"
           "- Never edit client/generated.py.\n\n"
           "This tool is fast. Always run the linter before you\n"
           "commit. See the docs.\n\n"
           "```\nnever parsed: run rm -rf\n```\n")
    got = [t for _, t in coverage.extract(doc)]
    assert got[0].endswith("`insta::allow_duplicates!`. Write explicit snapshots.")
    assert "Never edit client/generated.py." in got
    assert "Always run the linter before you commit." in got
    assert "This tool is fast." not in got                    # prose that instructs nothing
    assert not any("rm -rf" in t for t in got)                # code blocks are never instructions
    assert dict((t, ln) for ln, t in coverage.extract(doc))["Never edit client/generated.py."] == 5
