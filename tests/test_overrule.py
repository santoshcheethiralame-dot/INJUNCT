from injunct import overrule
from injunct.db import Ledger


def setup(tmp_path):
    L = Ledger(tmp_path / "l.db")
    repo = str(tmp_path)
    rid = L.open_run(repo, "t")
    cid = L.file_case(rid, repo, "human_reject", "high", "s", [])
    hid = L.establish(cid, repo, "forbidden_edit", {"glob": "*.lock"}, "never touch the lockfile",
                      status="binding")
    return L, repo, rid, hid


def test_a_precedent_that_keeps_being_overridden_and_passing_is_overruled(tmp_path):
    L, repo, rid, hid = setup(tmp_path)
    for _ in range(overrule.COUNTER_THRESHOLD):
        overrule.record_outcome(L, rid, hid, complied=False, passed=True)
    assert overrule.review(L, hid) == "overruled"
    assert L.holdings(repo=repo, status="binding") == []


def test_compliance_defends_a_precedent(tmp_path):
    L, repo, rid, hid = setup(tmp_path)
    for _ in range(overrule.COUNTER_THRESHOLD):
        overrule.record_outcome(L, rid, hid, complied=False, passed=True)
    for _ in range(overrule.COUNTER_THRESHOLD + 1):
        overrule.record_outcome(L, rid, hid, complied=True, passed=True)
    assert overrule.review(L, hid) == "unchanged"
    assert len(L.holdings(repo=repo, status="binding")) == 1


def test_one_bad_call_is_not_enough_to_overrule(tmp_path):
    L, repo, rid, hid = setup(tmp_path)
    overrule.record_outcome(L, rid, hid, complied=False, passed=True)
    assert overrule.review(L, hid) == "unchanged"


def test_sweep_reports_what_it_demoted(tmp_path):
    L, repo, rid, hid = setup(tmp_path)
    for _ in range(overrule.COUNTER_THRESHOLD):
        overrule.record_outcome(L, rid, hid, complied=False, passed=True)
    assert overrule.sweep(L, repo) == [hid]
