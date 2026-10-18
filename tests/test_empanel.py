from pathlib import Path

from injunct import artifacts, empanel
from injunct.change import Change
from injunct.db import Ledger


def led(tmp_path):
    return Ledger(tmp_path / ".injunct" / "ledger.db")


def test_a_holding_that_does_not_fire_on_its_own_case_is_not_binding(tmp_path):
    L = led(tmp_path)
    origin = Change(repo=tmp_path, touched=["models/a.py", "migrations/1.py"])
    status, receipt = empanel.empanel(L, str(tmp_path), "co_change",
                                      {"trigger": "models/*.py", "required": "migrations/**"}, origin)
    assert status == "persuasive"
    assert receipt["fire"] == "0/1"


def test_a_holding_that_fires_on_past_successes_is_not_binding(tmp_path):
    L = led(tmp_path)
    repo = str(tmp_path)
    # a past run that passed while touching models/ and no migration
    rid = L.open_run(repo, "past task")
    L.close_run(rid, "pass")
    artifacts.save(tmp_path, rid, Change(repo=tmp_path, touched=["models/old.py"]))

    origin = Change(repo=tmp_path, touched=["models/a.py"])
    status, receipt = empanel.empanel(L, repo, "co_change",
                                      {"trigger": "models/*.py", "required": "migrations/**"}, origin)
    assert status == "persuasive"
    assert receipt["false"].startswith("1/")


def test_a_clean_holding_is_binding(tmp_path):
    L = led(tmp_path)
    repo = str(tmp_path)
    rid = L.open_run(repo, "past task")
    L.close_run(rid, "pass")
    artifacts.save(tmp_path, rid, Change(repo=tmp_path, touched=["docs/readme.md"]))

    origin = Change(repo=tmp_path, touched=["models/a.py"])
    status, receipt = empanel.empanel(L, repo, "co_change",
                                      {"trigger": "models/*.py", "required": "migrations/**"}, origin)
    assert status == "binding"
    assert receipt == {"fire": "1/1", "false": "0/1", "false_ids": [],
                       "tested": 1, "judged": 1}


def test_with_no_history_a_holding_is_only_advisory(tmp_path):
    L = led(tmp_path)
    origin = Change(repo=tmp_path, touched=["models/a.py"])
    status, receipt = empanel.empanel(L, str(tmp_path), "co_change",
                                      {"trigger": "models/*.py", "required": "migrations/**"}, origin)
    assert status == "persuasive", "binding is a claim that it was tested"
    assert receipt["tested"] == 0 and "note" in receipt


# ---- the false positive we published, and why it happened -------------------
#
# `must_run( client/*.py : tools/gen.py )` went binding and then fired on a
# control task that only edited a README. The cause was not bad luck in which
# runs happened to exist: artifacts recorded no commands, so `must_run`
# abstained on every replay, no past run could contradict it, and it bound on a
# proof that was empty by construction.


def test_a_command_rule_cannot_bind_when_no_past_run_recorded_its_commands(tmp_path):
    L = led(tmp_path)
    repo = str(tmp_path)
    rid = L.open_run(repo, "past task")
    L.close_run(rid, "pass")
    # a v1-era artifact: commands were never stored
    artifacts.save(tmp_path, rid, Change(repo=tmp_path, touched=["client/generated.py"],
                                         commands=None))

    origin = Change(repo=tmp_path, touched=["client/generated.py"], commands=[])
    status, receipt = empanel.empanel(L, repo, "must_run",
                                      {"glob": "client/generated.py",
                                       "cmd": "tools/gen.py"}, origin)
    assert status == "persuasive", "nothing could have contradicted it"
    assert receipt["tested"] == 1
    assert receipt["judged"] == 0
    assert "could test this rule" in receipt["note"]


def test_a_command_rule_binds_once_a_past_run_recorded_its_commands(tmp_path):
    """The fix is not 'never bind' - it is 'bind on evidence that exists'."""
    L = led(tmp_path)
    repo = str(tmp_path)
    rid = L.open_run(repo, "past task")
    L.close_run(rid, "pass")
    artifacts.save(tmp_path, rid, Change(repo=tmp_path, touched=["client/generated.py"],
                                         commands=["python tools/gen.py"]))

    origin = Change(repo=tmp_path, touched=["client/generated.py"], commands=[])
    status, receipt = empanel.empanel(L, repo, "must_run",
                                      {"glob": "client/generated.py",
                                       "cmd": "tools/gen.py"}, origin)
    assert status == "binding", receipt
    assert receipt["judged"] == 1 and receipt["false"] == "0/1"


def test_a_readme_only_change_does_not_trip_the_generated_file_rule(tmp_path):
    """The shape of the published false positive, asserted directly."""
    from injunct import templates
    rule = {"glob": "client/generated.py", "cmd": "tools/gen.py"}
    readme_only = Change(repo=tmp_path, touched=["README.md"], commands=[])
    assert templates.fires("must_run", rule, readme_only) is None


def test_the_generated_file_rule_names_the_file_not_its_whole_directory(tmp_path):
    """A directory-wide glob is how a rule about one file reaches its neighbours."""
    from injunct import compiler
    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "generated.py").write_text(
        "# GENERATED FILE - run tools/gen.py, do not edit by hand\nX = 1\n",
        encoding="utf-8")
    ch = Change(repo=tmp_path, touched=["client/generated.py"], commands=[])

    template, params, _says = compiler.fallback({"summary": "hand-edited"}, ch)
    assert template == "must_run"
    assert params["glob"] == "client/generated.py", "not client/*.py"


def test_a_passing_run_can_promote_an_advisory_holding(tmp_path):
    L = led(tmp_path)
    repo = str(tmp_path)

    failing = L.open_run(repo, "add a field")
    L.close_run(failing, "fail")
    artifacts.save(tmp_path, failing, Change(repo=tmp_path, touched=["models/a.py"]))
    cid = L.file_case(failing, repo, "command_fail", "high", "the app went down", ["models/a.py"])
    hid = L.establish(cid, repo, "co_change",
                      {"trigger": "models/*.py", "required": "migrations/**"},
                      "changing models means changing migrations", status="persuasive")

    assert empanel.reconsider(L, repo) == [], "nothing has been proven yet"

    passing = L.open_run(repo, "unrelated work")
    L.close_run(passing, "pass")
    artifacts.save(tmp_path, passing, Change(repo=tmp_path, touched=["static/index.html"]))

    assert empanel.reconsider(L, repo) == [hid]
    assert L.holdings(repo=repo, status="binding")[0]["id"] == hid
