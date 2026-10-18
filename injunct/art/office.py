"""The records office, drawn as data.

Same method as the clerk: every pixel placed here, in the same palette, at the
same scale. Shop-bought sprite packs were considered and rejected - they carry
their own palette and their own light source, and a room assembled from two
sources reads as assembled.

    python -m injunct.art.office

writes web/sprites/office.png, office@4x.png and office.json.

Two rules hold this together. The light comes from the upper left, so every
solid is drawn with cv.box() and gets a lit edge and a shadowed one - a flat
fill is what makes pixel art look like a placeholder. And nothing here carries
text: labels belong to the page, which can change them, not to a sprite that
cannot.
"""
from __future__ import annotations

import json

from PIL import Image

from .clerk import Canvas, OUT

PIECES: dict[str, tuple] = {}


def piece(name: str, w: int, h: int):
    def wrap(fn):
        PIECES[name] = (w, h, fn)
        return fn
    return wrap


# ---- surfaces: the room itself -------------------------------------------

@piece("brick", 64, 32)
def brick(cv: Canvas):
    """A wall tile. Running bond, mortar lines, and no two bricks quite the
    same tone - a wall of identical rectangles reads as graph paper."""
    cv.rect(0, 0, 63, 31, "R1")
    shades = ("R2", "R4", "R3", "R2", "R4", "R2", "R3", "R4")
    i = 0
    for row, y in enumerate((0, 8, 16, 24)):
        offset = 0 if row % 2 == 0 else -16
        for x in range(offset, 64, 32):
            tone = shades[i % len(shades)]
            i += 1
            cv.rect(x + 1, y + 1, x + 30, y + 6, tone)
            cv.hline(x + 2, x + 29, y + 1, "R1" if tone == "R4" else "R4")
            cv.hline(x + 2, x + 29, y + 6, "R3")
            if i % 3 == 0:
                cv.set(x + 8, y + 4, "R3")
                cv.set(x + 21, y + 3, "R3")


@piece("floor", 64, 24)
def floor(cv: Canvas):
    """Floorboards."""
    cv.rect(0, 0, 63, 23, "F1")
    for y in (0, 8, 16):
        cv.hline(0, 63, y, "F2")
        cv.hline(0, 63, y + 1, "F3")
        cv.grain(0, y + 2, 63, y + 7, "F2", step=4)
    for x in (14, 46):
        cv.vline(x, 0, 7, "F2")
    cv.vline(30, 8, 15, "F2")
    cv.vline(6, 16, 23, "F2")


# ---- the desk ------------------------------------------------------------

@piece("desk", 168, 56)
def desk(cv: Canvas):
    """The centrepiece, so it gets the detail: an overhanging top, a centre
    drawer over the knee hole, two banks of three, and a modesty panel."""
    cv.box(0, 0, 167, 8, "W1", "W3", "W2")           # top, overhanging
    cv.grain(2, 2, 165, 6, "W2", step=2)
    cv.hline(1, 166, 7, "W4")                        # the lip under the edge
    cv.box(5, 9, 162, 15, "W2", "W1", "W4")          # apron

    # centre drawer, over the knee hole
    cv.box(58, 16, 110, 25, "W1", "W3", "W2")
    cv.grain(60, 18, 108, 23, "W2", step=3)
    cv.box(77, 19, 91, 22, "C", "H", "c")

    for (bx0, bx1) in ((6, 56), (112, 161)):
        cv.box(bx0, 16, bx1, 46, "W1", "W3", "W2")
        for y in (18, 28, 38):
            cv.box(bx0 + 3, y, bx1 - 3, y + 7, "W2", "W1", "W4")
            cv.grain(bx0 + 4, y + 1, bx1 - 4, y + 6, "W4", step=3)
            mx = (bx0 + bx1) // 2
            cv.box(mx - 7, y + 2, mx + 7, y + 5, "C", "H", "c")

    cv.rect(58, 26, 110, 46, "W4")                   # knee hole, in shadow
    cv.frame(58, 26, 110, 46, "K")
    cv.dither(59, 27, 109, 33, "W2")

    for x in (6, 50, 112, 156):                      # legs
        cv.box(x, 46, x + 6, 54, "W2", "W1", "W4")
    cv.shadow(4, 55, 163, 55, "F2")


@piece("cabinet", 60, 96)
def cabinet(cv: Canvas):
    """Four drawers. No labels - the page writes those over the top."""
    cv.box(0, 0, 59, 95, "M1", "M3", "M2")
    for i in range(4):
        y = 4 + i * 23
        cv.box(4, y, 55, y + 19, "M1", "M3", "M2")
        cv.dither(5, y + 14, 54, y + 18, "M2")
        cv.box(20, y + 8, 39, y + 12, "C", "H", "c")
        cv.box(8, y + 3, 17, y + 6, "P1", None, "P2")
    cv.shadow(2, 95, 57, 95, "F2")


@piece("chair", 62, 42)
def chair(cv: Canvas):
    """Seen from behind the sitter: backrest, frame, post."""
    cv.box(0, 0, 61, 27, "W2", "W1", "W4")
    cv.box(4, 4, 57, 23, "B", "W2", "W4")
    for y in (9, 15, 21):
        cv.hline(7, 54, y, "W2")
    cv.box(27, 28, 34, 41, "W2", "W1", "W4")


# ---- on the wall ---------------------------------------------------------

@piece("window", 78, 70)
def window(cv: Canvas):
    """Daylight, with greenery over the head. The room's cool light."""
    cv.box(0, 6, 77, 65, "W1", "W3", "W2")
    cv.rect(4, 10, 73, 61, "d1")
    cv.frame(4, 10, 73, 61, "K")
    for (x0, y0) in ((5, 11), (41, 11), (5, 38), (41, 38)):
        cv.rect(x0, y0, min(x0 + 32, 72), min(y0 + 22, 60), "d2" if y0 < 36 else "d1")
        for d in range(0, 13):
            cv.set(x0 + 3 + d, y0 + 14 - d, "d3")
            cv.set(x0 + 4 + d, y0 + 14 - d, "d3")
    cv.box(38, 10, 40, 61, "W1", "W3", "W2")
    cv.box(4, 34, 73, 37, "W1", "W3", "W2")
    cv.box(0, 62, 77, 69, "W1", "W3", "W2")
    for x in range(2, 74, 5):
        cv.rect(x, 0, x + 3, 4, "gr")
        cv.set(x + 1, 5, "g2")
        cv.set(x + 3, 2, "g2")


@piece("bookcase", 104, 148)
def bookcase(cv: Canvas):
    """A floor-standing case: three shelves of ledgers, two drawers, a plinth.

    Wall shelves left the lower wall bare and the room read as top-heavy. This
    stands on the floorboards and gives the left side something with weight.
    """
    cv.box(0, 0, 103, 147, "W1", "W3", "W2")        # carcass
    cv.box(3, 3, 100, 144, "W2", "W1", "W4")

    tones = ["b1", "b2", "b4", "b3", "b5", "b6", "b2", "b1", "b4", "b3", "b5", "b6"]
    for row, top in enumerate((8, 44, 80)):
        cv.rect(7, top, 96, top + 28, "W4")          # the dark inside
        x, i = 9, row * 4
        while x < 92:
            t = tones[i % len(tones)]
            w = 4 + (i % 3)
            h = 26 - (i % 5) * 2
            cv.box(x, top + (27 - h), x + w, top + 27, t, None, None, "K")
            cv.vline(x + 1, top + (28 - h), top + 26, "P1")
            if i % 4 == 0:                            # a title band
                cv.hline(x + 1, x + w - 1, top + (31 - h), "P1")
            i += 1
            x += w + 2
        cv.box(4, top + 28, 99, top + 32, "W1", "W3", "W2")   # the board

    for (dx0, dx1) in ((7, 51), (53, 96)):           # two drawers
        cv.box(dx0, 114, dx1, 134, "W1", "W3", "W2")
        cv.grain(dx0 + 2, 116, dx1 - 2, 132, "W2", step=3)
        mx = (dx0 + dx1) // 2
        cv.box(mx - 8, 121, mx + 8, 126, "P1", None, "P2")

    cv.box(0, 135, 103, 147, "W2", "W1", "W4")       # plinth
    cv.shadow(2, 147, 101, 147, "F2")


@piece("shelf", 96, 58)
def shelf(cv: Canvas):
    """Ledgers. Where the colour in this room comes from."""
    cv.box(0, 0, 95, 57, "W2", "W1", "W4")
    tones = ["b1", "b2", "b4", "b3", "b5", "b6", "b2", "b1", "b4", "b3", "b5", "b6"]
    for row, top in enumerate((4, 30)):
        cv.rect(3, top, 92, top + 20, "W4")
        x, i = 5, row * 5          # a different starting colour per row
        while x < 86:
            t = tones[i % len(tones)]
            w = 4 + (i % 3)
            h = 18 - (i % 4)
            cv.box(x, top + (20 - h), x + w, top + 19, t, None, None, "K")
            cv.vline(x + 1, top + (21 - h), top + 18, "P1")
            i += 1
            x += w + 2
        cv.box(1, top + 20, 94, top + 23, "W1", "W3", "W2")
    cv.shadow(2, 57, 93, 57, "R3")


@piece("chart", 84, 60)
def chart(cv: Canvas):
    """A framed chart. The line is drawn by the page, not baked in here."""
    cv.box(0, 0, 83, 59, "W1", "W3", "W2")
    cv.box(4, 4, 79, 55, "P1", None, "P2")
    for y in range(10, 52, 7):
        cv.hline(7, 76, y, "P3")


@piece("clock", 28, 28)
def clock(cv: Canvas):
    """Hands only. Nothing to read."""
    cv.box(0, 0, 27, 27, "W1", "W3", "W2")
    cv.box(3, 3, 24, 24, "P1", None, "P2")
    for (x, y) in ((13, 5), (13, 22), (5, 13), (22, 13)):
        cv.set(x, y, "K")
    cv.vline(13, 8, 13, "K")
    cv.hline(13, 18, 14, "K")
    cv.set(13, 14, "R")


@piece("corkboard", 116, 76)
def corkboard(cv: Canvas):
    """Where a firing rule gets pinned. Big enough to hold the card, so the
    verdict never has to lie across the desk it is judging."""
    cv.box(0, 0, 115, 75, "W1", "W3", "W2")
    cv.box(4, 4, 111, 71, "b4", None, "W2")
    cv.grain(6, 6, 109, 69, "W2", step=3)
    cv.dither(6, 62, 109, 69, "W2")


@piece("pin", 10, 10)
def pin(cv: Canvas):
    """A pushpin. Four of them hold a card to the board."""
    cv.rect(3, 6, 6, 9, "W4")
    cv.box(1, 1, 8, 6, "R", "r", "r")
    cv.set(3, 2, "P1")


# ---- small things ---------------------------------------------------------

@piece("lamp", 30, 48)
def lamp(cv: Canvas):
    """A coral shade with a warm centre, on a wooden stem."""
    for i, y in enumerate(range(0, 12)):
        inset = 6 - i // 2
        cv.hline(5 + inset, 24 - inset, y, "R")
        cv.set(4 + inset, y, "K")
        cv.set(25 - inset, y, "K")
    for i, y in enumerate(range(0, 12)):
        inset = 6 - i // 2
        # A cone takes light across its width, not down its middle: lit on the
        # side facing the window, rolling into shadow on the other.
        cv.vline(5 + inset, y, y, "ti+")
        cv.hline(23 - inset, 24 - inset, y, "ti-")
    for i, y in enumerate(range(3, 12)):
        w = i // 2
        cv.hline(14 - w, 15 + w, y, "A")
    cv.hline(8, 21, 1, "P1")
    cv.box(2, 12, 27, 15, "r", "R", "K")
    cv.hline(4, 25, 16, "A")
    cv.box(13, 16, 16, 39, "W2", "W1", "W4")
    cv.box(6, 40, 23, 46, "W2", "W1", "W4")
    cv.shadow(5, 47, 24, 47, "W2")


@piece("papers", 30, 11)
def papers(cv: Canvas):
    """A short stack seen edge on. It is the signal that a change landed, so
    it has to read at a glance and it has to sit IN the tray - the earlier
    version was as tall as the tray itself and looked glued to the front of
    it rather than filed in it."""
    for (dx, dy) in ((0, 4), (2, 2), (4, 0)):
        cv.box(dx, dy, dx + 25, dy + 6, "P1", None, "P2")
    cv.hline(8, 27, 2, "P3")
    cv.hline(8, 25, 4, "P3")


@piece("intray", 42, 21)
def intray(cv: Canvas):
    """Two tiers of wire. The upper one is where the paper goes, so it is a
    frame and not a solid: a stack drawn behind a filled box can only ever
    look stuck to it."""
    cv.box(0, 8, 41, 20, "M1", "M3", "M2")
    cv.hline(1, 40, 9, "M3")                       # the rim, catching light
    cv.dither(2, 16, 39, 19, "M2")
    cv.vline(0, 0, 8, "K")
    cv.vline(41, 0, 8, "K")
    cv.hline(0, 41, 0, "K")
    cv.hline(1, 40, 1, "M2")


@piece("outtray", 42, 20)
def outtray(cv: Canvas):
    cv.box(0, 7, 41, 19, "W1", "W3", "W2")
    cv.vline(0, 0, 7, "K")
    cv.vline(41, 0, 7, "K")
    cv.hline(0, 41, 0, "K")


@piece("mug", 17, 17)
def mug(cv: Canvas):
    cv.box(1, 4, 11, 16, "P1", None, "P2")
    cv.rect(3, 6, 9, 8, "W4")
    cv.hline(3, 9, 6, "W2")
    cv.box(12, 8, 15, 12, "P1", None, "P2")
    cv.rect(13, 9, 14, 11, "N")


@piece("plant", 30, 44)
def plant(cv: Canvas):
    """Fuller fronds. A one-pixel stroke reads as wire, not a plant."""
    cv.box(7, 30, 22, 41, "R", "ti+", "ti-")
    cv.box(5, 26, 24, 31, "R", "ti+", "ti-")
    cv.vline(22, 32, 40, "ti=")   # the pot rolls away from the light
    cv.rect(8, 29, 21, 30, "W4")

    def frond(x, y, h, tone):
        cv.vline(x, y, y + h, tone)
        for d in range(2, h, 3):
            cv.rect(x - 2, y + d, x - 1, y + d + 1, tone)
            cv.rect(x + 1, y + d + 2, x + 2, y + d + 3, tone)
        cv.set(x, y - 1, tone)

    frond(15, 2, 25, "gr")
    frond(9, 8, 19, "g2")
    frond(21, 8, 19, "g2")
    frond(6, 15, 12, "gr")
    frond(24, 15, 12, "gr")
    cv.shadow(6, 42, 23, 42, "F2")


@piece("bin", 24, 28)
def bin_(cv: Canvas):
    for y in range(4, 26):
        inset = (y - 4) // 9
        cv.hline(2 + inset, 21 - inset, y, "M1")
        cv.set(1 + inset, y, "K")
        cv.set(22 - inset, y, "K")
    cv.box(0, 1, 23, 5, "M2", "M3", "M2")
    for x in (7, 12, 17):
        cv.vline(x, 7, 24, "M2")
    cv.shadow(3, 27, 20, 27, "F2")


@piece("rug", 190, 40)
def rug(cv: Canvas):
    """A woven runner. The first two were a flat slab and then a slab with
    white teeth for fringe; this one has a border, a repeating diamond, and a
    fringe in the rug's own colour rather than bare paper."""
    cv.box(7, 0, 182, 39, "b1", None, "r")
    cv.frame(11, 4, 178, 35, "b4")          # outer band
    cv.frame(13, 6, 176, 33, "r")
    cv.rect(16, 9, 173, 30, "b1")           # field
    cv.grain(17, 10, 172, 29, "r", step=4)

    for cx in range(30, 170, 23):           # diamonds down the field
        for (dx, dy) in ((0, -5), (0, 5), (-5, 0), (5, 0)):
            cv.set(cx + dx, 19 + dy, "b4")
        for d in range(1, 5):
            cv.set(cx - d, 19 - (5 - d), "b4")
            cv.set(cx + d, 19 - (5 - d), "b4")
            cv.set(cx - d, 19 + (5 - d), "b4")
            cv.set(cx + d, 19 + (5 - d), "b4")
        cv.set(cx, 19, "b4")

    for y in range(3, 38, 4):               # short fringe, in the rug's tone
        cv.hline(3, 6, y, "r")
        cv.hline(183, 186, y, "r")
    cv.shadow(9, 39, 180, 39, "F2")


@piece("bigplant", 44, 58)
def bigplant(cv: Canvas):
    """A floor plant, tall enough to hold the left corner on its own. A
    wastebasket was too small for that much empty floor."""
    cv.box(9, 38, 34, 54, "R", "r", "r")        # pot
    cv.box(6, 32, 37, 40, "R", "r", "r")        # rim
    cv.rect(10, 36, 33, 38, "W4")               # soil
    cv.hline(11, 32, 34, "P2")                  # a highlight along the rim

    def frond(x, y, h, tone, spread=3):
        cv.vline(x, y, y + h, tone)
        for d in range(2, h, 3):
            cv.rect(x - spread, y + d, x - 1, y + d + 1, tone)
            cv.rect(x + 1, y + d + 2, x + spread, y + d + 3, tone)
        cv.set(x, y - 1, tone)

    frond(22, 1, 33, "gr", 4)
    frond(14, 6, 27, "g2", 3)
    frond(30, 6, 27, "g2", 3)
    frond(9, 13, 20, "gr", 3)
    frond(35, 13, 20, "gr", 3)
    frond(18, 17, 15, "g2", 2)
    frond(27, 17, 15, "g2", 2)
    cv.shadow(8, 55, 35, 55, "F2")


@piece("nameplate", 46, 14)
def nameplate(cv: Canvas):
    cv.box(0, 4, 45, 13, "b4", "A", "W2")
    cv.box(0, 0, 45, 4, "W2", "W1", "W4")


@piece("stamppad", 28, 14)
def stamppad(cv: Canvas):
    cv.box(0, 5, 27, 13, "W4", "W2", "W4")
    cv.box(3, 0, 24, 6, "W2", "W1", "W4")
    cv.rect(5, 2, 22, 4, "R")


# ---- the docket: a cabinet you can open ---------------------------------
#
# The geometry is fixed here rather than in the page. A closed front is 48
# rows on a 50-row pitch; an open drawer is 20 rows of opening with a taller
# front thrown forward below it, anchored at the same row as the closed one.

@piece("cab_body", 132, 232)
def cab_body(cv: Canvas):
    """The carcass: folded sheet metal, and detailed as such. A lipped top
    that throws a line, a return around the drawer bay, seams down the
    corners, a lock in the top rail, and a kick plate the feet stand under."""
    cv.box(0, 0, 131, 221, "M1", "M3", "M2")
    cv.vline(2, 10, 218, "M3")                     # the left face, in the light
    cv.vline(129, 10, 218, "M2")                   # the right face, turned away

    cv.box(0, 0, 131, 8, "M1", "M3", "M2")         # the top, overhanging
    cv.hline(2, 129, 9, "W4")                      # the line it throws
    cv.dither(3, 10, 128, 11, "W4")

    cv.box(4, 11, 127, 219, "M2", "M1", "M2")      # the return around the bay
    cv.rect(8, 14, 123, 215, "W4")                 # the bay, unlit
    cv.dither(9, 15, 122, 38, "M2")

    cv.box(112, 1, 122, 7, "c", "H", "C")          # lock barrel, in the top rail
    cv.rect(116, 3, 118, 5, "W4")

    cv.box(4, 216, 127, 221, "M2", "M1", "W4")     # kick plate
    for x in (12, 107):                            # feet
        cv.box(x, 222, x + 13, 231, "B", "W2", "W4")
    cv.shadow(8, 231, 123, 231, "F2")


def _front(cv: Canvas, y: int, w: int, tall: int):
    """The face of a drawer, open or closed. Same pressing either way: a
    chrome card holder the page writes into, and a finger pull sunk into a
    cavity that is dark where the light cannot reach it."""
    x1, mid = w - 1, w // 2
    cv.box(0, y, x1, y + tall - 1, "M1", "M3", "M2")
    cv.hline(2, x1 - 2, y + 1, "M3")               # the pressed top bevel
    cv.dither(2, y + tall - 8, x1 - 2, y + tall - 3, "M2")

    cv.box(mid - 24, y + 3, mid + 23, y + 19, "c", "H", "C")     # the holder
    cv.box(mid - 21, y + 5, mid + 20, y + 17, "P1", None, "P2")  # its card
    cv.hline(mid - 19, mid + 18, y + 16, "P3")

    cv.box(mid - 27, y + 25, mid + 26, y + 39, "M2", "M1", "W4")  # the cavity
    cv.rect(mid - 25, y + 27, mid + 24, y + 29, "W4")             # its unlit top
    cv.box(mid - 23, y + 30, mid + 22, y + 36, "C", "H", "c")     # the pull
    cv.hline(mid - 21, mid + 20, y + 31, "H")
    for x in (6, w - 7):                                          # fixing screws
        cv.box(x - 1, y + 23, x + 1, y + 25, "c", "H", "C")


@piece("cab_drawer", 118, 48)
def cab_drawer(cv: Canvas):
    """A closed drawer front, flush with the case."""
    _front(cv, 0, 118, 48)


@piece("cab_open", 132, 74)
def cab_open(cv: Canvas):
    """A drawer pulled out: the opening above, the front thrown forward below
    it. The front is wider than a closed one - nearer to you is bigger."""
    cv.rect(5, 0, 126, 19, "W4")                   # the opening
    cv.frame(5, 0, 126, 19, "K")
    cv.rect(9, 1, 122, 5, "M2")                    # the back wall of the drawer
    cv.hline(9, 122, 1, "M1")
    cv.dither(9, 5, 122, 9, "W4")
    cv.vline(7, 1, 18, "M2")                       # near side, catching light
    cv.vline(124, 1, 18, "W4")                     # far side, turned away

    _front(cv, 20, 132, 54)                        # the front, thrown forward
    cv.shadow(2, 73, 129, 73, "F2")


def _file(cv: Canvas, tx: int, paper: tuple = ()):
    """One file in a drawer, and it has to read as a folder in twenty rows.
    The silhouette does that work, not the colour: a low band of folder with
    a wide tab stepping up out of it, one shape with the seam between them
    rubbed out. Drawn as two boxes it reads as a brick sitting on a brick,
    which is how the first attempt failed.

    Only some files show paper, and none of them show much. A white rectangle
    beside every tab stops reading as the contents of the folder and starts
    reading as a card propped against it."""
    if paper:                                              # sheets, edge on
        px, py = paper
        cv.rect(px, py, px + 11, 13, "P1")
        cv.vline(px + 11, py + 1, 13, "P2")
        cv.hline(px, px + 11, py, "k")
        for y in range(py + 3, 13, 3):
            cv.hline(px + 1, px + 10, y, "P3")

    cv.rect(1, 13, 24, 18, "A")                            # the folder, filled
    cv.rect(tx + 1, 8, tx + 12, 12, "A")                   # and its tab
    cv.frame(0, 12, 25, 19, "k")
    cv.frame(tx, 7, tx + 13, 12, "k")
    cv.hline(tx + 1, tx + 12, 12, "A")                     # rub out the seam

    cv.hline(1, 24, 13, "A1")                              # the fold, in light
    cv.vline(1, 13, 18, "A1")
    cv.hline(2, 24, 18, "A0")                              # and the far edges
    cv.vline(24, 14, 18, "A0")
    cv.hline(tx + 1, tx + 12, 8, "A1")
    cv.vline(tx + 1, 8, 11, "A1")
    cv.vline(tx + 12, 9, 11, "A0")


# The tab is cut at the left corner of every folder, never in the middle and
# never alternating: a bump in the centre reads as a lip or a handle, and a
# row that swaps sides reads as a mistake rather than as a set of files.
@piece("file_l", 26, 20)
def file_l(cv: Canvas):
    _file(cv, 0)


@piece("file_m", 26, 20)
def file_m(cv: Canvas):
    _file(cv, 0, paper=(13, 5))


@piece("file_r", 26, 20)
def file_r(cv: Canvas):
    _file(cv, 0)


@piece("printer", 76, 42)
def printer(cv: Canvas):
    """A dot-matrix printer with the run feeding out of the front. It is here
    to say what the strip below it is and nothing else - the strip carries
    three hundred outcomes and has to stay legible, so it is not a sprite."""
    cv.box(4, 0, 71, 7, "c", "C", "c")             # the lid
    cv.dither(7, 2, 68, 5, "C")
    cv.box(0, 6, 75, 32, "C", "H", "c")            # the case
    for y in (12, 15, 18):                         # vents
        cv.hline(7, 31, y, "c")
    cv.box(44, 10, 70, 20, "S", "s", "S")          # the window over the ribbon
    cv.rect(46, 12, 68, 18, "s")
    cv.hline(47, 67, 14, "S")
    cv.box(7, 23, 35, 29, "c", "C", "c")           # control panel
    cv.rect(10, 25, 12, 27, "G")                   # running
    cv.rect(15, 25, 17, 27, "A")                   # paper
    cv.rect(3, 33, 72, 35, "K")                    # the slot, in shadow
    cv.box(9, 35, 66, 40, "P1", None, "P2")        # paper on its way out
    cv.hline(11, 64, 37, "P3")
    cv.shadow(2, 41, 73, 41, "F2")


# ---- sheet ---------------------------------------------------------------

def sheet() -> tuple[Image.Image, dict]:
    """One row, pieces laid left to right, each padded to the tallest."""
    # The two surfaces that TILE must keep a flat outline: relighting an edge
    # that repeats puts a seam every 64 pixels across the whole wall.
    TILING = {"brick", "floor"}

    built = []
    for name, (w, h, fn) in PIECES.items():
        cv = Canvas(w, h)
        fn(cv)
        # Selective outlining, same rule the figure gets: the line lightens
        # where the form turns into the lamp, upper and left, and stays dark
        # where it turns away. One flat outline all round is what makes a piece
        # of furniture read as a sticker on the wall.
        if name not in TILING:
            cv.relight_outline()
        built.append((name, cv))

    total_w = sum(cv.w for _, cv in built)
    max_h = max(cv.h for _, cv in built)
    im = Image.new("RGBA", (total_w, max_h))
    meta: dict = {"pieces": {}, "sheet": {"w": total_w, "h": max_h}}
    x = 0
    for name, cv in built:
        im.paste(cv.image(), (x, 0))
        meta["pieces"][name] = {"x": x, "y": 0, "w": cv.w, "h": cv.h}
        x += cv.w
    return im, meta


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    im, meta = sheet()
    im.save(OUT / "office.png")
    im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(OUT / "office@4x.png")
    # Tileable surfaces need their own files: CSS cannot crop one piece out of
    # an atlas and repeat only that, so a `repeat` background of the sheet tiles
    # the whole sheet - desks and cabinets scattered across the wall.
    for name in ("brick", "floor"):
        w, h, fn = PIECES[name]
        cv = Canvas(w, h)
        fn(cv)
        cv.image().save(OUT / f"{name}.png")
    meta["tiles"] = ["brick", "floor"]
    (OUT / "office.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  {len(meta['pieces'])} pieces -> {OUT / 'office.png'} "
          f"({meta['sheet']['w']}x{meta['sheet']['h']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
