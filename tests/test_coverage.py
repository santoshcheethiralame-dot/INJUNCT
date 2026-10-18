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
    # one give-up on the parallel pass, one more on the retry pass
    assert len(calls) <= 2 * coverage._Model.GIVE_UP + coverage.WORKERS
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


def test_the_demo_runs_offline_on_recorded_answers(monkeypatch):
    """The stage demo must not depend on wifi, a key, or a rate limit."""
    import tempfile
    from injunct import coverdemo
    monkeypatch.setattr(coverage, "CACHE", coverdemo.CACHE)
    monkeypatch.setattr(coverage.provider, "MODEL", coverdemo.MODEL)
    monkeypatch.setattr(coverage.provider, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("demo went to the network")))
    repo = coverdemo.build(Path(tempfile.mkdtemp()) / "clinic")
    s = coverage.run(repo)
    assert (s["enforced"], s["checkable"], s["unchecked"]) == (3, 2, 4)
    assert {d["commit"].split(":", 1)[1].strip() for d in s["discounted"]} == {
        "quick debug for the double-booking bug", "Add Visit model", "Silence the Appointment type error"}


def test_a_commit_someone_fixed_is_not_evidence_of_good_work(monkeypatch):
    """Trusting every commit, the history breaks all three rules; leaving out
    the three commits a later commit had to fix, all three bind."""
    import tempfile
    from injunct import coverdemo
    monkeypatch.setattr(coverage, "CACHE", coverdemo.CACHE)
    monkeypatch.setattr(coverage.provider, "MODEL", coverdemo.MODEL)
    repo = coverdemo.build(Path(tempfile.mkdtemp()) / "clinic")
    trusting = coverage.run(repo, trust_history=True)
    assert trusting["enforced"] == 0 and not trusting["discounted"]
    honest = coverage.run(repo)                       # same ledger: the marking is recomputed, not stacked
    assert honest["enforced"] == 3 and len(honest["discounted"]) == 3
    again = coverage.run(repo)
    assert again["enforced"] == 3 and len(again["discounted"]) == 3
    trusting_after = coverage.run(repo, trust_history=True)   # must not inherit the marks
    assert trusting_after["enforced"] == 0


def test_a_sentence_that_fails_once_is_retried_and_not_reported(repo, fake_model, monkeypatch):
    """One timeout is not a dead model: the second, smaller try answers it, and
    the run must not then warn that its number is only a floor."""
    real = coverage.provider.chat
    failed = []

    def flaky(prompt, system="", **k):
        if system == coverage.COMPILE and "commit messages" in prompt and not failed:
            failed.append(1)
            raise coverage.provider.Unavailable("The read operation timed out")
        return real(prompt, system=system, **k)

    monkeypatch.setattr(coverage.provider, "chat", flaky)
    s = coverage.run(repo)
    assert failed and not s["model_failed"] and s["model_failures"] == 0
    assert {r["text"]: r for r in s["rules"]}["Write clear commit messages."]["reason"].startswith("judgement")


def test_a_rate_limit_does_not_switch_the_model_off(repo, fake_model, monkeypatch):
    real = coverage.provider.chat
    limited = []

    def busy(prompt, system="", **k):
        if system == coverage.COMPILE and len(limited) < 5:
            limited.append(1)
            raise coverage.provider.Unavailable("HTTP Error 429: Too Many Requests")
        return real(prompt, system=system, **k)

    monkeypatch.setattr(coverage.provider, "chat", busy)
    s = coverage.run(repo)
    assert len(limited) == 5 and not s["model_failed"] and s["enforced"] == 1


def test_two_runs_at_once_do_not_erase_each_others_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(coverage, "CACHE", tmp_path / "cache.json")
    monkeypatch.setattr(coverage.provider, "chat", lambda p, system="", **k: '{"answer": "%s"}' % p)
    a, b = coverage._Model(True), coverage._Model(True)   # both load the same (empty) cache
    a.ask("one", "s")
    b.ask("two", "s")                                       # b never saw a's answer in memory
    fresh = coverage._Model(True)
    monkeypatch.setattr(coverage.provider, "chat", lambda *x, **k: (_ for _ in ()).throw(AssertionError("miss")))
    assert fresh.ask("one", "s") == {"answer": "one"} and fresh.ask("two", "s") == {"answer": "two"}


def test_the_demo_scores_the_same_under_any_model_setting(monkeypatch):
    """An app session does not inherit a terminal's INJUNCT_MODEL; the demo's
    recorded answers must still be found, and credited to the model that gave them."""
    import tempfile
    from injunct import coverdemo
    monkeypatch.setattr(coverage.provider, "MODEL", "qwen2.5-coder:7b")
    monkeypatch.setattr(coverage.provider, "chat",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("went to the network")))
    s = coverage.run(coverdemo.build(Path(tempfile.mkdtemp()) / "clinic"))
    assert s["enforced"] == 3 and s["model"] == coverdemo.MODEL and not s["model_failed"]


def test_installing_the_hook_does_not_change_what_the_model_is_shown(tmp_path):
    import tempfile
    from injunct import coverdemo, verbs
    repo = coverdemo.build(Path(tempfile.mkdtemp()) / "clinic")
    before = coverage._files(repo)
    verbs.claude(repo)
    _git(repo, "add", ".claude")
    _git(repo, "commit", "-q", "-m", "install injunct")
    assert coverage._files(repo) == before
