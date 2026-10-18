"""The clerk is generated, not drawn by hand, so it can be asserted about.

These exist because "it looks half built" is a real failure mode and a vague
one. Each test turns one part of that judgement into something checkable: the
character is one connected body, the screen actually displays the record, and
the sheet regenerates byte-identically.
"""
import pytest

from injunct.art import clerk


def frames():
    return [clerk.build_frame(spec) for spec in clerk.FRAMES]


def solid(cv, x0, y0, x1, y1):
    """How many pixels in a region are not transparent."""
    return sum(1 for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
               if cv.px[y][x] != "_")


def test_every_declared_state_has_frames():
    _, meta = clerk.sheet()
    assert set(meta["states"]) == {"dormant", "watching", "reading", "halt",
                                   "cleared", "filing", "skip", "overruled"}
    for state, idx in meta["states"].items():
        assert idx, f"{state} has no frames"


def test_the_sheet_is_the_size_it_claims():
    im, meta = clerk.sheet()
    assert im.size == (clerk.W * meta["count"], clerk.H)
    assert meta["frame"] == {"w": clerk.W, "h": clerk.H}


def test_generation_is_deterministic():
    """A sprite sheet that changes between runs cannot be reviewed in a diff."""
    assert clerk.sheet()[0].tobytes() == clerk.sheet()[0].tobytes()


@pytest.mark.parametrize("i", range(len(clerk.FRAMES)))
def test_no_frame_is_half_drawn(i):
    """Head, torso and legs must all carry pixels. An earlier pass shipped a
    frame whose body was missing and it read as a floating head."""
    cv = frames()[i]
    o = 2                                  # the drawing origin
    assert solid(cv, 8, 2 + o, 40, 25 + o) > 400, "the head is missing"
    assert solid(cv, 13, 31 + o, 35, 47 + o) > 200, "the torso is missing"
    assert solid(cv, 15, 50 + o, 33, 67 + o) > 150, "the legs are missing"
    assert solid(cv, 12, 67 + o, 36, 71 + o) > 60, "the shoes are missing"


@pytest.mark.parametrize("i", range(len(clerk.FRAMES)))
def test_the_head_is_joined_to_the_body(i):
    """The neck column must be solid from the casing to the shoulders, or the
    head floats - which is exactly how the first version looked."""
    cv = frames()[i]
    for y in range(28, 33):                # 26..31 plus the origin
        assert cv.px[y][24] != "_", f"neck gap at row {y}"


@pytest.mark.parametrize("spec", clerk.FRAMES, ids=lambda s: f"{s[0]}-{s[1]}")
def test_the_screen_displays_the_record(spec):
    """The only justification for a mascot here is that its face is a readout.
    Assert the label's colour actually appears inside the glass."""
    cv = clerk.build_frame(spec)
    colour = spec[2]
    found = sum(1 for y in range(8, 24) for x in range(12, 32) if cv.px[y][x] == colour)
    assert found > 0, "nothing is on the screen"


def test_the_halt_frames_carry_a_stamp():
    halt = [clerk.build_frame(s) for s in clerk.FRAMES if s[0] == "halt"]
    for cv in halt:
        red = sum(1 for row in cv.px for p in row if p == "R")
        assert red > 40, "the stamp is missing from a halt frame"


def test_only_states_that_should_loop_do():
    """A verdict holds; an idle breathes. Every state that ENDS in something
    must stop on its last frame rather than replaying the decision."""
    _, meta = clerk.sheet()
    for ending in ("halt", "cleared", "filing", "overruled"):
        assert meta["loop"][ending] is False, f"{ending} must hold, not replay"
    for idle in ("dormant", "watching", "reading", "skip"):
        assert meta["loop"][idle] is True, f"{idle} should keep breathing"


def test_every_state_has_a_timing():
    _, meta = clerk.sheet()
    assert set(meta["timing"]) == set(meta["states"])
    assert all(ms > 0 for ms in meta["timing"].values())


def test_the_antenna_is_not_clipped():
    """It reaches above the casing and was being cut off by the top edge."""
    cv = clerk.build_frame(clerk.FRAMES[2])
    assert any(cv.px[y][23] != "_" for y in range(0, 4)), "the antenna is gone"


def test_a_bob_does_not_open_a_seam():
    """Lifting the whole body left the torso hanging above the legs."""
    still = clerk.build_frame(("watching", "-", "G", "down", {"lamp": True}))
    bobbed = clerk.build_frame(("watching", "-", "G", "down", {"lamp": True, "bob": 1}))
    for cv in (still, bobbed):
        for y in range(36, 50):           # waist band must stay solid
            assert cv.px[y][24] != "_", f"seam at row {y}"


def test_the_card_states_carry_a_card():
    for state in ("filing", "overruled"):
        specs = [f for f in clerk.FRAMES if f[0] == state]
        assert specs, state
        assert any("card" in f[4] for f in specs), f"{state} has no card"


def test_no_colour_outside_the_palette():
    """Every pixel must be a named token, so the art cannot drift from
    docs/DESIGN.md by someone typing a hex value."""
    for cv in frames():
        for row in cv.px:
            for p in row:
                assert p in clerk.P, f"unknown colour {p!r}"
