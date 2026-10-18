

def test_the_box_never_breaks_however_long_the_text():
    """A row that overflows pushes the closing bar past the border, and the
    halt card is the one thing a person actually looks at."""
    from injunct import render

    class V:
        holding_id = 1
        established = 0
        empanel = {"fire": "n/a (no failing case)" * 3, "false": "0/0", "tested": 4}
        says = "x" * 300
        rule = "co_change( " + "y" * 200 + " )"
        reason = "z" * 300
        cited = 0

    lines = render.halt_card(V()).splitlines()
    widths = {len(l) for l in lines}
    assert widths == {render.W}, f"rows are ragged: {sorted(widths)}"


def test_a_mined_rule_does_not_claim_it_was_tested():
    from injunct import render

    class V:
        holding_id = 2
        established = 0
        empanel = {"mined": {"support": 11}, "fire": "n/a", "tested": 0}
        says = "Changing results/* means changing docs/ too."
        rule = "co_change( results/* -> docs/** )"
        reason = "results/x.json changed, nothing under docs/** did"
        cited = 0

    card = render.halt_card(V())
    assert "mined from history, not empanelled" in card
    assert "0/0 false" not in card, "0/0 implies it was tested and came back clean"
