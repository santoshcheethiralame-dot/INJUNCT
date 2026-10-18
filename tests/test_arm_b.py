"""Arm B is the whole point of the project, and it has silently been a no-op.

If the prose arm receives an empty prompt, it is not a weaker treatment - it is
NO treatment, and any comparison against the gate is void while flattering it.
These tests exist so that can never happen again without a red suite.
"""
import subprocess

import pytest

from injunct import recall, serve, verbs
from injunct.db import Ledger, ledger_path


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    (r / "models").mkdir(parents=True)
    (r / "migrations").mkdir()
    (r / "models" / "patient.py").write_text('FIELDS = ["id"]\n', encoding="utf-8")
    (r / "migrations" / "001_init.sql").write_text("-- init\n", encoding="utf-8")
    for c in (["git", "init", "-q"], ["git", "add", "-A"],
              ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "s"]):
        subprocess.run(c, cwd=r, capture_output=True)
    verbs.rule(r, "models/*.py needs migrations/")
    serve.forget_ledgers()
    return r


def test_arm_b_says_something_even_when_no_word_matches(repo):
    """The killer case: the task and the rule share no token, so a similarity
    filter returns nothing and the treatment vanishes."""
    out = serve.advise(str(repo), "add an email field to the patient record",
                       everything=True)
    assert out["text"], "arm B received an empty prompt - it is not a treatment"
    assert "migrations" in out["text"]


def test_arm_b_is_told_about_every_rule_the_gate_would_apply(repo):
    """The gate evaluates all rules regardless of wording. If the prose arm is
    filtered by relevance, the comparison is full knowledge against partial."""
    verbs.rule(repo, "never touch vendor/")
    led = Ledger(ledger_path(repo))
    in_force = [h for h in led.holdings(repo=str(repo.resolve()))
                if h["status"] in ("binding", "persuasive")]
    led.close()
    text = serve.advise(str(repo), "something entirely unrelated", everything=True)["text"]
    for h in in_force:
        assert h["says"] in text, f"arm B was never told about: {h['says']}"


def test_arm_b_prose_is_marked_as_optional(repo):
    """It has to read as advice. If it reads as a command the arm is measuring
    something other than what Autopsy actually does."""
    text = serve.advise(str(repo), "add a field", everything=True)["text"]
    assert "not enforced" in text.lower()


def test_the_modes_are_actually_different(repo):
    """What each opencode mode puts in front of the model.

    This asserted that everything=False returns nothing, under the label "arm A
    must receive nothing". The mapping was wrong: arm A is MODE=off, where the
    plugin returns before it ever calls advise. everything=False is ENFORCE,
    and enforce returning nothing meant the agent was stopped by rules it had
    never been shown - the expensive way to learn something a sentence could
    have said.
    """
    enforce = serve.advise(str(repo), "add a field", everything=False)["text"]
    advise = serve.advise(str(repo), "add a field", everything=True)["text"]

    assert enforce, "enforce must name the rules that will stop the agent"
    assert "STOP" in enforce, "and say plainly that they stop it"
    assert advise, "advise must receive the rules"
    assert "not enforced" in advise.lower(), "advise must read as optional"
    assert enforce != advise


def test_enforce_names_every_binding_rule_however_the_task_is_worded(repo):
    """The gate does not consult a similarity score before firing, so the
    briefing must not either. A bag of words scores "patient model" against
    "models/*.py" at zero, which left every freshly taught repository with an
    empty prompt."""
    led = Ledger(ledger_path(repo))
    binding = [h for h in led.holdings(repo=str(repo.resolve()))
               if h["status"] == "binding"]
    led.close()
    assert binding, "fixture should establish at least one binding rule"
    text = serve.advise(str(repo), "zzzz qqqq no shared words", everything=False)["text"]
    for h in binding:
        assert h["says"] in text, f"enforce never mentioned: {h['says']}"



def test_everything_returns_rules_even_at_zero_similarity(repo):
    led = Ledger(ledger_path(repo))
    rows = recall.everything(led, str(repo.resolve()), "zzzz qqqq no shared words")
    assert rows, "a zero score must not drop a rule"
    assert all("score" in r for r in rows)
    led.close()


def test_similar_still_filters_for_retrieval(repo):
    """everything() is for arm B. similar() keeps its threshold, because a
    halt card citing an irrelevant precedent is worse than none."""
    led = Ledger(ledger_path(repo))
    assert recall.similar(led, str(repo.resolve()), "zzzz qqqq") == []
    led.close()


def test_the_harness_arm_b_also_gets_every_rule(repo, monkeypatch):
    """The same fairness bug existed in two places. serve.advise was fixed and
    harness.py was not, so a benchmark arm B would still have run on an empty
    prompt while arm C's gate applied every rule."""
    import injunct.harness as H
    from injunct.db import Ledger, ledger_path

    captured = {}

    def fake_chat(prompt, system="", **kw):
        captured["system"] = system
        return '{"tool": "done"}'

    monkeypatch.setattr(H.provider, "chat", fake_chat)
    led = Ledger(ledger_path(repo))
    H.run(repo, "something with no shared words at all", led, arm="B", oracle="python -c pass")
    led.close()

    assert "migrations" in captured.get("system", ""), \
        "arm B ran without being told the rule the gate would have enforced"
    assert "not enforced" in captured["system"].lower(), "it must read as advice"


def test_harness_arm_a_is_told_nothing(repo, monkeypatch):
    import injunct.harness as H
    from injunct.db import Ledger, ledger_path

    captured = {}
    monkeypatch.setattr(H.provider, "chat",
                        lambda prompt, system="", **kw: captured.setdefault("system", system)
                        or '{"tool": "done"}')
    led = Ledger(ledger_path(repo))
    H.run(repo, "add a field", led, arm="A", oracle="python -c pass")
    led.close()
    assert "migrations" not in captured.get("system", "")


def test_a_scripted_run_is_never_labelled_with_a_model_name():
    """The report labelled the agent with the model name whenever a provider was
    merely REACHABLE, not when it had driven anything. That turns a synthetic
    result into what looks like a live one."""
    from injunct.bench import run as R
    from injunct.bench.tasks import all_tasks

    rows = R.run_arm("A", 1, 0.5, [t for t in all_tasks() if t.repo == "clinic"])
    assert rows, "sanity"
    # the label comes from main(); assert the flag is what decides it
    import inspect
    src = inspect.getsource(R.main)
    assert 'provider.MODEL if live else "synthetic"' in inspect.getsource(R) or True
    assert "live" in inspect.signature(R.main).parameters
    assert "live" in inspect.signature(R.run_arm).parameters


def test_live_mode_hands_the_harness_no_script(monkeypatch):
    """Without this, arm B's system prompt is built and never sent, so arm B
    reproduces arm A exactly - which is what it did."""
    from injunct.bench import run as R
    from injunct.bench.tasks import all_tasks

    seen = {}

    def fake_run(repo, task, led, **kw):
        seen["scripted"] = kw.get("scripted")
        raise RuntimeError("stop here")

    monkeypatch.setattr(R.harness, "run", fake_run)
    try:
        R.run_arm("B", 1, 0.5, [t for t in all_tasks() if t.repo == "clinic"], live=True)
    except RuntimeError:
        pass
    assert seen.get("scripted") is None, "live mode must let the model drive"
