"""A block that does not say what to do next stops the agent without improving
it. The live run showed exactly that: blocked four times, recovered never."""
from pathlib import Path

from injunct import nextstep

SEEDS = Path(__file__).resolve().parents[1] / "seeds"


class V:
    def __init__(self, template, rule):
        self.template, self.rule = template, rule


def test_it_follows_the_numbering_already_in_the_directory():
    s = nextstep.suggest(V("co_change", "co_change( models/*.py -> migrations/** )"),
                         SEEDS / "clinic", ["models/patient.py"])
    assert s == "create migrations/002_patient.sql", s


def test_it_names_the_command_for_a_must_run_rule():
    s = nextstep.suggest(V("must_run", "must_run( api/*.json : python tools/gen.py )"),
                         SEEDS / "typegen", ["api/types.json"])
    assert s == "run `python tools/gen.py` and make it pass", s


def test_it_sends_a_forbidden_edit_back_to_the_source():
    s = nextstep.suggest(V("forbidden_edit", "forbidden_edit( client/generated.py )"),
                         SEEDS / "typegen", ["client/generated.py"])
    assert "revert" in s and "generated from" in s


def test_an_empty_directory_gets_honest_vagueness_not_a_guess(tmp_path):
    (tmp_path / "models").mkdir()
    s = nextstep.suggest(V("co_change", "co_change( models/*.py -> migrations/** )"),
                         tmp_path, ["models/patient.py"])
    assert s == "add the matching change under migrations/", s


def test_it_says_nothing_rather_than_invent_a_step():
    assert nextstep.suggest(V("prose", "no rule"), SEEDS / "clinic", ["a.py"]) == ""


def test_the_card_carries_the_instruction_and_keeps_its_box():
    from injunct import render

    class Full:
        holding_id = 1
        established = 0
        empanel = {"taught": True}
        says = "Changing models/*.py means changing migrations/ too."
        rule = "co_change( models/*.py -> migrations/** )"
        reason = "models/patient.py changed, nothing under migrations/** did"
        template = "co_change"
        cited = 0

    card = render.halt_card(Full(), repo=SEEDS / "clinic", touched=["models/patient.py"])
    assert "DO THIS NEXT:  create migrations/002_patient.sql" in card
    assert {len(l) for l in card.splitlines()} == {render.W}


def test_a_taught_rule_is_not_described_as_mined():
    from injunct import render

    class Taught:
        holding_id = 1
        established = 0
        empanel = {"taught": True, "fire": "n/a (you wrote it)"}
        says = "x"
        rule = "co_change( a/* -> b/** )"
        reason = "r"
        template = "co_change"
        cited = 0

    card = render.halt_card(Taught())
    assert "you wrote this rule" in card
    assert "mined from history" not in card
