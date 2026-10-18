"""The clerk, drawn as data.

No asset is traced or downloaded: every pixel is placed here, so the sprite
sheet is versionable, diffable, and regenerates at any scale. Run

    python -m injunct.art.clerk

to write web/sprites/clerk.png, clerk@4x.png and clerk.json.

The character is a records clerk with a cathode-ray tube where a face would be.
It never emotes. The screen displays the record - a rule count, a holding
number, a verdict - which is the only reason a mascot is allowed here at all.
Every frame below corresponds to a state the system actually produces.
"""
from __future__ import annotations

import colorsys
import json
from pathlib import Path

from PIL import Image

W, H = 48, 74
OUT = Path(__file__).resolve().parents[2] / "web" / "sprites"

# ---- palette -------------------------------------------------------------
# Named so a frame reads as intent rather than hex. Values come from
# docs/DESIGN.md; nothing here invents a colour.
P = {
    "_": (0, 0, 0, 0),                # transparent

    # Outlines are warm dark brown, never black. Black reads as harsh and
    # cheap at this size; a brown line keeps the room soft.
    "K": (0x4A, 0x38, 0x2E, 255),     # outline
    "k": (0x6B, 0x55, 0x46, 255),     # soft outline / seam

    # --- the room: warm, light, and lit from the upper left ---------------
    "R1": (0xE8, 0xDC, 0xCA, 255),    # mortar
    "R2": (0xCE, 0x9A, 0x7C, 255),    # brick
    "R3": (0xB8, 0x82, 0x66, 255),    # brick, shaded
    "R4": (0xDD, 0xAE, 0x90, 255),    # brick, lit
    "F1": (0xC9, 0xA2, 0x7A, 255),    # floorboard
    "F2": (0xB2, 0x88, 0x62, 255),    # floorboard, shaded
    "F3": (0xD8, 0xB4, 0x8E, 255),    # floorboard, lit

    # --- wood ------------------------------------------------------------
    "W1": (0xB0, 0x76, 0x4C, 255),    # wood
    "W2": (0x8C, 0x59, 0x38, 255),    # wood, shaded
    "W3": (0xC9, 0x93, 0x68, 255),    # wood, lit
    "W4": (0x6E, 0x44, 0x2B, 255),    # wood, deep shadow

    # --- painted metal ----------------------------------------------------
    "M1": (0x9F, 0xB0, 0x8F, 255),    # sage
    "M2": (0x82, 0x93, 0x6F, 255),    # sage, shaded
    "M3": (0xBA, 0xC8, 0xAC, 255),    # sage, lit

    # --- paper and cloth ---------------------------------------------------
    "P1": (0xFD, 0xF6, 0xE7, 255),    # paper
    "P2": (0xEA, 0xDD, 0xC4, 255),    # paper, shaded
    "P3": (0xD3, 0xC2, 0xA4, 255),    # paper, ruled

    # --- the CRT ------------------------------------------------------------
    "C": (0xC7, 0xC2, 0xB3, 255),     # casing
    "c": (0xA8, 0xA2, 0x92, 255),     # casing, shaded
    "H": (0xE2, 0xDE, 0xD2, 255),     # casing, lit
    "S": (0x2B, 0x3A, 0x32, 255),     # glass
    "s": (0x36, 0x47, 0x3D, 255),     # glass, scanline

    # --- signal -------------------------------------------------------------
    "G": (0x5F, 0xC1, 0x8A, 255),     # phosphor / cleared
    "A": (0xF0, 0xB4, 0x4E, 255),     # amber / advisory
    "A1": (0xF7, 0xC9, 0x77, 255),    # manila, lit
    "A0": (0xCE, 0x93, 0x3B, 255),    # manila, shaded
    "R": (0xE0, 0x6B, 0x63, 255),     # coral / halt
    "r": (0xC4, 0x4E, 0x48, 255),     # coral, shaded

    # --- daylight ------------------------------------------------------------
    "d1": (0x9E, 0xDE, 0xE6, 255),    # glass
    "d2": (0xC4, 0xEE, 0xF2, 255),    # glass, lit
    "d3": (0xFF, 0xFF, 0xFF, 255),    # glare
    "gr": (0x6F, 0xA8, 0x6B, 255),    # foliage
    "g2": (0x54, 0x88, 0x52, 255),    # foliage, shaded

    # --- ledger spines --------------------------------------------------------
    "b1": (0xD4, 0x6A, 0x5F, 255),
    "b2": (0x6E, 0x9E, 0xC4, 255),
    "b3": (0x8F, 0xB8, 0x7A, 255),
    "b4": (0xF0, 0xB4, 0x4E, 255),
    "b5": (0xA9, 0x8A, 0xC4, 255),
    "b6": (0x5E, 0xB0, 0xA6, 255),

    # --- misc ---------------------------------------------------------------
    "T": (0xB0, 0x76, 0x4C, 255),     # legacy alias -> wood
    "t": (0x8C, 0x59, 0x38, 255),     # legacy alias -> wood shaded
    "B": (0x6E, 0x44, 0x2B, 255),     # leather / dark trim
    "O": (0x9F, 0xB0, 0x8F, 255),     # legacy alias -> sage
    "N": (0xE8, 0xDC, 0xCA, 255),     # the room behind
    "D": (0xB8, 0xAE, 0x9E, 255),     # dormant wash
    "W": (0xFD, 0xF6, 0xE7, 255),     # legacy alias -> paper
    "w": (0xEA, 0xDD, 0xC4, 255),     # legacy alias -> paper shaded
}


# ---- derived shades ------------------------------------------------------
# A shadow is not the same colour turned down. Light that reaches a surface
# directly is the lamp's, which is yellow-leaning; light that reaches a surface
# in shadow is bounced and ambient, which is blue-leaning. So a shade rotates
# hue toward violet and a highlight rotates it toward yellow, and saturation
# moves the other way in each case - shadows hold their colour, highlights wash
# out. Doing this by arithmetic rather than by eye keeps every material on the
# sprite consistent with every other one.
#
#   shade      hue -14 deg (warm) / +14 (cool),  sat +10%,  value x0.74
#   highlight  hue +11 deg (warm) / -11 (cool),  sat -18%,  value x1.09
#   occlusion  where two forms meet: the shade, halved again
#
# Directions flip on cool hues because "toward violet" is a different way round
# the wheel from orange than it is from green.

def _shift(rgb, dh, ds, dv):
    r, g, b = (c / 255 for c in rgb[:3])
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    warm = h < 0.18 or h > 0.92          # reds through yellows
    h = (h + (dh if warm else -dh)) % 1.0
    s = max(0.0, min(1.0, s * (1 + ds)))
    v = max(0.0, min(1.0, v * dv))
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, s, v)) + (255,)


def _ramp(base: str, key: str):
    """Register shade / highlight / occlusion for a palette entry."""
    rgb = P[base]
    P[key + "-"] = _shift(rgb, -14 / 360, +0.10, 0.74)   # shade
    P[key + "+"] = _shift(rgb, +11 / 360, -0.18, 1.09)   # highlight
    P[key + "="] = _shift(rgb, -18 / 360, +0.16, 0.55)   # occlusion / contact


# The reflection on the tube. A specular is not one step up from the surface -
# it is the room's light arriving whole, so it gets its own value well above the
# ramp, while staying dark enough that the record on the screen still reads.
P["gl2"] = (0x4A, 0x5C, 0x50, 255)

# The room's own materials were hand-picked lighter/darker of one hue, which is
# what made the office read flat beside a figure that had been shaded properly.
# Recomputing them puts every surface in the building under the same lamp.
#
# A gentler value drop than the figure's: these are surface variants inside a
# lit room - a brick facing away from the window, a floorboard in its own shadow
# - not the deep core shadow of a form. P2 and A0 are deliberately NOT in here:
# they are paper and manila TINTS, and hue-shifting a tint turns paper grey.
for _b, _d, _lit in (("R2", "R3", 0), ("R2", "R4", 1),      # brick
                     ("F1", "F2", 0), ("F1", "F3", 1),      # floorboard
                     ("W1", "W2", 0), ("W1", "W3", 1),      # wood
                     ("M1", "M2", 0), ("M1", "M3", 1),      # painted metal
                     ("C", "c", 0),   ("C", "H", 1),        # casing plastic
                     ("gr", "g2", 0),                       # foliage
                     ("R", "r", 0)):                        # coral
    P[_d] = _shift(P[_b], (11 if _lit else -14) / 360,
                   -0.18 if _lit else 0.10, 1.09 if _lit else 0.80)

for _base, _key in (("W", "sh"),      # shirt
                    ("T", "tr"),      # trousers
                    ("B", "lc"),      # leather
                    ("R", "ti"),      # tie
                    ("C", "pl"),      # casing plastic
                    ("S", "gl")):     # screen glass
    _ramp(_base, _key)


class Canvas:
    def __init__(self, w: int = W, h: int = H):
        self.w, self.h = w, h
        self.px = [["_"] * w for _ in range(h)]
        # Everything is drawn through this offset. The antenna reaches above the
        # casing at y=-1 and was being clipped by the top edge; shifting the
        # origin is cheaper and safer than renumbering every coordinate.
        self.oy = 0

    def set(self, x, y, c):
        y += self.oy
        if 0 <= x < self.w and 0 <= y < self.h and c != "_":
            self.px[y][x] = c

    def rect(self, x0, y0, x1, y1, c):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, c)

    def frame(self, x0, y0, x1, y1, c):
        for x in range(x0, x1 + 1):
            self.set(x, y0, c)
            self.set(x, y1, c)
        for y in range(y0, y1 + 1):
            self.set(x0, y, c)
            self.set(x1, y, c)

    def hline(self, x0, x1, y, c):
        for x in range(x0, x1 + 1):
            self.set(x, y, c)

    def vline(self, x, y0, y1, c):
        for y in range(y0, y1 + 1):
            self.set(x, y, c)

    def clear_px(self, x, y):
        y += self.oy
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = "_"

    def relight_outline(self):
        """Selective outlining, applied once to the finished silhouette.

        A single flat outline all the way round is what makes a sprite read as a
        sticker: the line is telling you where the shape ends and nothing else.
        A real edge is dark where the form turns away from the lamp and lighter
        where it turns into it, so the outline carries the lighting too.

        The lamp is upper left, so an outline pixel with empty space above or to
        its left is a lit edge and softens to `k`. Everything else stays `K`.
        Only the OUTER silhouette is touched - interior seams are structure, not
        lighting, and lifting those would dissolve the drawing.
        """
        lit = []
        for y in range(self.h):
            for x in range(self.w):
                if self.px[y][x] != "K":
                    continue
                up = self.px[y - 1][x] if y > 0 else "_"
                left = self.px[y][x - 1] if x > 0 else "_"
                if up == "_" or left == "_":
                    lit.append((x, y))
        for x, y in lit:
            self.px[y][x] = "k"

    def box(self, x0, y0, x1, y1, mid, lit=None, dark=None, outline="K"):
        """A shaded solid. Light along the top and left, shadow along the
        bottom and right - the one convention that stops pixel art reading
        flat, applied everywhere rather than by eye."""
        self.rect(x0, y0, x1, y1, mid)
        if lit:
            self.hline(x0 + 1, x1 - 1, y0 + 1, lit)
            self.vline(x0 + 1, y0 + 1, y1 - 1, lit)
        if dark:
            self.hline(x0 + 1, x1 - 1, y1 - 1, dark)
            self.vline(x1 - 1, y0 + 1, y1 - 1, dark)
        if outline:
            self.frame(x0, y0, x1, y1, outline)

    def grain(self, x0, y0, x1, y1, tone, step=3, offset=0):
        """Wood grain and cloth weave. Sparse, so it is texture not noise."""
        for y in range(y0, y1 + 1):
            if (y + offset) % step:
                continue
            for x in range(x0, x1 + 1, 2):
                if (x + y) % 4 == 0:
                    self.set(x, y, tone)

    def dither(self, x0, y0, x1, y1, tone):
        """A checker of one tone into another. Softens a hard edge without
        adding a colour."""
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if (x + y) % 2 == 0:
                    self.set(x, y, tone)

    def shadow(self, x0, y0, x1, y1, tone):
        """Contact shadow. Objects that do not cast one look pasted on."""
        self.rect(x0, y0, x1, y1, tone)
        self.dither(x0 - 2, y0, x0 - 1, y1, tone)
        self.dither(x1 + 1, y0, x1 + 2, y1, tone)

    def chamfer(self, x0, y0, x1, y1):
        """Knock the corners off so the casing reads as moulded plastic."""
        for (x, y) in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            self.clear_px(x, y)

    def shift_above(self, y_floor: int, dy: int):
        """Move everything above the floor line, with what is below held still.

        The floor limits where we WRITE, not where we read. An earlier version
        refused to read past it, so lifting the head pulled in blank rows and
        opened a gap between the neck and the collar instead of sliding the
        torso up behind it.
        """
        if dy == 0:
            return
        rows = [r[:] for r in self.px]
        blank = ["_"] * self.w
        for y in range(0, y_floor):
            src = y - dy
            self.px[y] = rows[src][:] if 0 <= src < self.h else blank[:]

    def image(self) -> Image.Image:
        im = Image.new("RGBA", (self.w, self.h))
        im.putdata([P[self.px[y][x]] for y in range(self.h) for x in range(self.w)])
        return im


# ---- a 3x5 face for the screen ------------------------------------------
FONT = {
    "0": ("111", "101", "101", "101", "111"), "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"), "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"), "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"), "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"), "9": ("111", "101", "111", "001", "111"),
    "N": ("101", "111", "111", "101", "101"), "O": ("111", "101", "101", "101", "111"),
    "K": ("101", "110", "100", "110", "101"), "o": ("000", "110", "101", "101", "110"),
    "-": ("000", "000", "111", "000", "000"), ".": ("000", "000", "000", "000", "100"),
    " ": ("000", "000", "000", "000", "000"), "?": ("111", "001", "011", "000", "010"),
    "X": ("101", "101", "010", "101", "101"), "z": ("000", "111", "010", "100", "111"),
    "*": ("101", "010", "111", "010", "101"), "L": ("100", "100", "100", "100", "111"),
    "E": ("111", "100", "111", "100", "111"), "D": ("110", "101", "101", "101", "110"),
    "F": ("111", "100", "111", "100", "100"), "I": ("111", "010", "010", "010", "111"),
    "A": ("111", "101", "111", "101", "101"), "H": ("101", "101", "111", "101", "101"),
    "T": ("111", "010", "010", "010", "010"),
}


def text(cv: Canvas, s: str, x: int, y: int, c: str):
    for ch in s:
        for dy, row in enumerate(FONT.get(ch, FONT[" "])):
            for dx, bit in enumerate(row):
                if bit == "1":
                    cv.set(x + dx, y + dy, c)
        x += 4


def centred(cv: Canvas, s: str, y: int, c: str):
    width = len(s) * 4 - 1
    text(cv, s, 11 + (22 - width) // 2, y, c)


# ---- the body ------------------------------------------------------------

def draw_body(cv: Canvas, dim: bool = False):
    """Everything that never moves: casing, neck, shoulders, torso, legs.

    Proportion matters more than detail here. An earlier pass gave the head 44%
    of the height and it read as a bobblehead with a floating skull; the tube is
    now a third, and the neck carries visible shoulders so head and body are one
    object rather than two.
    """
    shirt = "D" if dim else "W"
    shade = "D" if dim else "w"
    plastic = "D" if dim else "C"
    dark = "D" if dim else "c"

    # ---- CRT casing, lit from the upper left -------------------------------
    cv.rect(8, 2, 40, 25, plastic)
    cv.frame(8, 2, 40, 25, "K")
    cv.chamfer(8, 2, 40, 25)
    if not dim:
        cv.hline(10, 38, 3, "H")
        cv.vline(9, 4, 23, "H")
        cv.hline(10, 38, 24, dark)
        cv.vline(39, 4, 23, dark)
        for y in (9, 12, 15, 18):
            cv.hline(35, 38, y, dark)

    # antenna: a bent whip with a bead on the end. It is the one flourish on an
    # otherwise severe machine, and it gives the idle animation something to do.
    cv.vline(23, -1, 1, "k")
    cv.vline(23, 0, 1, "K")
    cv.set(24, 0, "K")

    cv.rect(34, 21, 37, 24, dark)          # the dial
    cv.frame(34, 21, 37, 24, "K")
    if not dim:
        cv.set(35, 22, "H")

    cv.set(12, 23, "k")                    # power lamp housing
    cv.rect(12, 6, 31, 21, "S")            # screen, inset
    cv.frame(11, 5, 32, 22, "K")
    for y in range(7, 21, 2):
        cv.hline(13, 30, y, "s")
    if not dim:
        # Glass is the only specular surface on the whole figure, and a CRT
        # without a reflection in it reads as a painted rectangle. The sweep
        # sits in the upper left, where the light is, and stops well clear of
        # row 11 so it never fights the text the screen exists to show.
        #
        # It is a diagonal of decreasing length, not a block: a reflection is a
        # shape the room casts, and three equal rows would be banding.
        cv.hline(13, 17, 7, "gl2")
        cv.hline(13, 15, 8, "gl2")
        cv.set(13, 9, "gl+")
        # The tube is curved, so the far corners fall away from the lamp. Only
        # the two AWAY from the light, and only one step down - four dark dots
        # in four corners read as dirt on the glass rather than as curvature.
        cv.set(31, 20, "gl-")
        cv.set(30, 21, "gl-")
        cv.set(31, 21, "gl=")

    # ---- neck: short, thick, and clearly joining two solids ----------------
    cv.rect(20, 26, 28, 31, plastic)
    cv.frame(20, 26, 28, 31, "K")
    if not dim:
        cv.vline(21, 27, 30, "H")
        cv.vline(27, 27, 30, dark)
        cv.vline(28, 27, 30, "pl-")        # rolls away from the light
        # The casing hangs over the neck and blocks the lamp. This single row is
        # what stops the head reading as balanced on a post.
        cv.hline(21, 27, 26, "pl=")

    # ---- shoulders and torso ----------------------------------------------
    cv.rect(14, 31, 34, 33, shirt)         # shoulders, narrower than the waist
    cv.frame(14, 31, 34, 33, "K")
    cv.chamfer(14, 31, 34, 33)
    cv.rect(13, 33, 35, 47, shirt)         # chest
    cv.frame(13, 33, 35, 47, "K")
    cv.hline(15, 33, 33, shirt)            # dissolve the seam

    if not dim:
        # The torso is a box lit from the upper left, so it gets three values
        # across, not one - and the bands are different widths on purpose. Two
        # equal strips running parallel to the edge is banding, which reinforces
        # the pixel grid and flattens the very form it is meant to build.
        cv.vline(14, 34, 46, "sh+")        # the lit face
        cv.vline(15, 34, 40, "sh+")
        cv.rect(31, 34, 34, 46, "sh-")     # the turn into shadow
        cv.vline(35, 36, 45, "sh=")        # the far edge rolls away
        # Contact shadow: the head sits ON the shoulders and occludes them.
        # Without this the two solids read as stacked rather than joined - but
        # it belongs UNDER the neck only. Run it the width of the shoulders and
        # it stops being a shadow and becomes a dirty stripe.
        cv.hline(20, 28, 31, "sh-")
    else:
        cv.rect(32, 34, 34, 46, shade)

    cv.hline(19, 22, 32, shade)            # collar
    cv.hline(26, 29, 32, shade)
    cv.set(20, 32, "K")
    cv.set(28, 32, "K")

    if not dim:                            # tie: a cylinder, not a flat strap
        cv.rect(23, 32, 25, 34, "R")       # knot
        cv.set(23, 32, "ti+")
        cv.set(25, 33, "ti-")
        cv.rect(22, 35, 26, 43, "R")
        cv.vline(22, 36, 42, "ti+")        # lit left edge
        cv.vline(25, 36, 43, "ti-")        # core shadow
        cv.vline(26, 37, 42, "ti=")        # the roll away from the light
        cv.set(22, 35, "K")
        cv.set(26, 35, "K")
        cv.hline(23, 25, 44, "K")
    for y in (38, 42):                     # buttons
        cv.set(17, y, "k")

    if not dim:                            # breast pocket with two pens
        cv.rect(28, 36, 32, 41, shade)
        cv.frame(28, 36, 32, 41, "k")
        cv.vline(29, 34, 37, "A")
        cv.vline(31, 34, 37, "R")

    if not dim:
        cv.hline(14, 34, 46, shade)        # shirt hem
    cv.rect(13, 47, 35, 50, "B")           # belt
    cv.frame(13, 47, 35, 50, "K")
    if not dim:
        cv.rect(23, 48, 25, 50, "A")

    # ---- legs: cylinders, not rectangles -----------------------------------
    # A tube in light reads as four values across, in this order: a lit edge, the
    # base, a core shadow, and then a BOUNCE - the far edge picks light back up
    # off the room and is never the darkest part. Leaving the bounce out is what
    # makes a cylinder look like a flat plank with a line down it, which is
    # exactly what these legs were.
    for x0 in (15, 26):
        cv.rect(x0, 50, x0 + 7, 67, "T")
        cv.frame(x0, 50, x0 + 7, 67, "K")
        if dim:
            continue
        cv.vline(x0 + 1, 51, 66, "tr+")    # the lit edge
        cv.vline(x0 + 4, 51, 66, "t")      # core shadow, off-centre
        cv.vline(x0 + 5, 51, 66, "tr-")
        cv.vline(x0 + 6, 52, 65, "tr+")    # bounce light off the floor
        # The belt overhangs the trousers, so the top of each leg is occluded.
        cv.hline(x0 + 1, x0 + 6, 51, "tr=")

    # ---- shoes: wider than the leg, so they read as feet -------------------
    for x0 in (12, 25):
        cv.rect(x0, 67, x0 + 11, 71, "B")
        cv.frame(x0, 67, x0 + 11, 71, "K")
        if dim:
            continue
        cv.hline(x0 + 1, x0 + 10, 68, "lc+")   # the polished cap catches light
        cv.hline(x0 + 1, x0 + 10, 70, "lc-")   # the welt below it
        # The one place the figure touches the world. Without a contact shadow a
        # sprite hovers, however well the rest of it is drawn.
        cv.hline(x0 + 2, x0 + 9, 71, "lc=")


def draw_arm_left(cv: Canvas, dim: bool = False):
    """The idle arm.

    It takes the SHADOW tone, not the shirt tone. Drawn in the same cream as the
    chest the arms vanished into the torso and the whole upper body read as one
    block - a hairline outline is not enough separation at this size.
    """
    sleeve = "D" if dim else "w"
    hand = "D" if dim else "C"
    cv.rect(8, 33, 13, 45, sleeve)
    cv.frame(8, 33, 13, 45, "K")
    cv.hline(9, 12, 33, sleeve)          # erase the seam at the shoulder
    cv.hline(9, 12, 44, "K")             # cuff line
    draw_hand(cv, 8, 46, hand, thumb_right=True)


# Each pose: the upper arm box, the hand box, and where a held stamp sits.
# Arms hang OUTSIDE the torso so the hands fall beside the hips. Tucked in, the
# hands landed on the belt and read as pockets.
ARM_POSES = {
    #          sleeve box              hand x,y
    "down":   ((35, 33, 40, 45), (35, 46)),
    "mid":    ((35, 31, 40, 42), (37, 43)),
    "up":     ((35, 28, 40, 38), (36, 24)),
    "strike": ((35, 33, 40, 44), (37, 47)),

    # The in-betweens of the stamp arc. Fluidity here comes from frame count,
    # never from easing - an interpolated tween would make the whole office read
    # as a modern UI wearing a costume (docs/DESIGN.md, law 3). So the arc is
    # sampled at six heights instead of three, and every frame is still a frame.
    "arc":    ((35, 29, 40, 39), (36, 29)),   # just below the raise
    "lift":   ((35, 30, 40, 40), (36, 34)),   # falling
    "swing":  ((35, 31, 40, 41), (37, 39)),   # gathering speed
    "recoil": ((35, 32, 40, 43), (37, 44)),   # the bounce after the blow
}


def stamp_pos(pose: str) -> tuple[int, int]:
    """Where the stamp sits so the hand closes around its shaft."""
    (_, _, _, _), (hx, hy) = ARM_POSES[pose]
    return hx - 2, hy - 2


def draw_hand(cv: Canvas, x: int, y: int, colour: str, thumb_right: bool = False):
    """Five pixels of hand, with a thumb, so it is not a grey square."""
    cv.rect(x, y, x + 4, y + 4, colour)
    cv.frame(x, y, x + 4, y + 4, "K")
    tx = x + 5 if thumb_right else x - 1
    cv.set(tx, y + 1, colour)
    cv.set(tx, y + 2, "K")


def draw_arm_right(cv: Canvas, pose: str, dim: bool = False):
    sleeve = "D" if dim else "w"
    hand = "D" if dim else "C"
    (ax0, ay0, ax1, ay1), (hx, hy) = ARM_POSES[pose]
    cv.rect(ax0, ay0, ax1, ay1, sleeve)
    cv.frame(ax0, ay0, ax1, ay1, "K")
    cv.hline(max(ax0 + 1, 15), min(ax1 - 1, 34), ay0, sleeve)  # seam into the shoulder
    cv.hline(ax0 + 1, ax1 - 1, ay1 - 1, "K")                   # cuff line
    draw_hand(cv, hx, hy, hand)


def draw_stamp(cv: Canvas, x: int, y: int):
    """A rubber stamp: red pad, wooden handle, gripped rather than floating.

    Deliberately chunky. It is the only object in the frame that carries weight,
    and at this size a delicate one reads as a smudge.
    """
    cv.rect(x + 1, y, x + 8, y + 3, "B")        # handle knob
    cv.frame(x + 1, y, x + 8, y + 3, "K")
    cv.hline(x + 2, x + 7, y + 1, "t")          # grain
    cv.rect(x + 3, y + 4, x + 6, y + 6, "B")    # shaft
    cv.frame(x + 3, y + 4, x + 6, y + 6, "K")
    cv.rect(x, y + 7, x + 9, y + 11, "R")       # pad
    cv.frame(x, y + 7, x + 9, y + 11, "K")
    cv.hline(x + 1, x + 8, y + 8, "W")          # ink face catches the light


def draw_lamp(cv: Canvas, on: bool):
    """The power lamp under the glass. Off in dormant, alive otherwise."""
    cv.set(12, 23, "G" if on else "k")


def draw_antenna_bead(cv: Canvas, lit: bool):
    cv.set(23, -1, "A" if lit else "k")
    cv.set(24, -1, "_")


def draw_card(cv: Canvas, x: int, y: int, mark: str | None = None):
    """An index card. Held while filing, crossed through when withdrawn."""
    cv.rect(x, y, x + 11, y + 8, "W")
    cv.frame(x, y, x + 11, y + 8, "K")
    cv.hline(x + 2, x + 9, y + 2, "w")
    cv.hline(x + 2, x + 7, y + 4, "w")
    cv.hline(x + 2, x + 9, y + 6, "w")
    if mark == "cross":
        for i in range(8):
            cv.set(x + 2 + i, y + 1 + i, "R")
            cv.set(x + 9 - i, y + 1 + i, "R")
    elif mark == "tick":
        for i in range(3):
            cv.set(x + 3 + i, y + 4 + i, "G")
        for i in range(4):
            cv.set(x + 6 + i, y + 6 - i, "G")


def draw_impact(cv: Canvas, x: int, y: int):
    """Three short marks. The only moment anything here has weight."""
    for dx in (-3, 0, 3):
        cv.vline(x + dx, y, y + 1, "A")


# ---- frames --------------------------------------------------------------
# Each entry: (state, screen text, screen colour, arm pose, extras)
# state, screen text, colour, arm pose, extras
#   bob   - pixels the body lifts, feet planted
#   lamp  - the power lamp under the glass
#   bead  - the antenna tip
#   card  - (x, y, mark) an index card in hand
FRAMES = [
    # dormant: the tube is cold. Nothing is watching. Long, unhurried, and the
    # only state where the lamp is out - that is what "no service" looks like.
    ("dormant",  ".",     "s", "down", {"lamp": False}),
    ("dormant",  ".",     "s", "down", {"lamp": False}),
    ("dormant",  "z",     "k", "down", {"lamp": False}),
    ("dormant",  "z",     "k", "down", {"lamp": False}),
    ("dormant",  ".",     "s", "down", {"lamp": False, "bob": 1}),
    ("dormant",  ".",     "s", "down", {"lamp": False}),

    # watching: connected, tree unchanged. One slow breath per cycle, sampled
    # finely enough to read as breathing rather than as a twitch, with the scan
    # line sweeping the glass and the bead blinking off the beat.
    ("watching", "-",     "G", "down", {"lamp": True, "bead": True}),
    ("watching", "-",     "G", "down", {"lamp": True, "bob": 1}),
    ("watching", "-",     "G", "down", {"lamp": True, "bob": 1, "scan": 10}),
    ("watching", "- -",   "G", "down", {"lamp": True, "bob": 2, "scan": 13}),
    ("watching", "- -",   "G", "down", {"lamp": True, "bob": 2, "scan": 16}),
    ("watching", "- -",   "G", "down", {"lamp": True, "bob": 1, "scan": 19}),
    ("watching", "-",     "G", "down", {"lamp": True, "bob": 1, "bead": True}),
    ("watching", "-",     "G", "down", {"lamp": True}),
    ("watching", "-",     "G", "down", {"lamp": True, "bead": True}),
    ("watching", "-",     "G", "down", {"lamp": True}),

    # reading: a change arrived and the rules are sitting. Quick, busy, and the
    # scan sweeps the full height of the glass twice per cycle.
    ("reading",  ".",     "A", "mid",  {"lamp": True, "scan": 10}),
    ("reading",  "..",    "A", "mid",  {"lamp": True, "scan": 13}),
    ("reading",  "...",   "A", "mid",  {"lamp": True, "scan": 16}),
    ("reading",  "...",   "A", "mid",  {"lamp": True, "scan": 19, "bead": True}),
    ("reading",  "..",    "A", "mid",  {"lamp": True, "scan": 22}),
    ("reading",  ".",     "A", "mid",  {"lamp": True, "scan": 19}),
    ("reading",  "..",    "A", "mid",  {"lamp": True, "scan": 16}),
    ("reading",  "...",   "A", "mid",  {"lamp": True, "scan": 13, "bead": True}),
    ("reading",  "..",    "A", "mid",  {"lamp": True, "scan": 10}),
    ("reading",  ".",     "A", "mid",  {"lamp": True}),

    # halt: raise, hold, fall, land, bounce, settle. It does not loop - a
    # verdict holds. This is the one animation on the desk carrying real weight,
    # so it gets the frames; everything around it stays quiet.
    ("halt",     "HALT", "R", "up",     {"lamp": True, "stamp": True}),
    ("halt",     "HALT", "R", "up",     {"lamp": True, "stamp": True, "bead": True}),
    ("halt",     "HALT", "R", "arc",    {"lamp": True, "stamp": True}),
    ("halt",     "HALT", "R", "lift",   {"lamp": True, "stamp": True}),
    ("halt",     "HALT", "R", "swing",  {"lamp": True, "stamp": True}),
    ("halt",     "HALT", "R", "mid",    {"lamp": True, "stamp": True}),
    ("halt",     "HALT", "R", "strike", {"lamp": True, "stamp": True, "impact": True,
                                          "bob": -1}),
    ("halt",     "HALT", "R", "recoil", {"lamp": True, "stamp": True}),
    ("halt",     "HALT", "R", "strike", {"lamp": True, "stamp": True}),
    ("halt",     "HALT", "R", "strike", {"lamp": True, "stamp": True}),

    # cleared: a hop with a real arc to it, then the card is ticked.
    ("cleared",  "OK",    "G", "down", {"lamp": True}),
    ("cleared",  "OK",    "G", "down", {"lamp": True, "bob": 1}),
    ("cleared",  "OK",    "G", "down", {"lamp": True, "bob": 2, "bead": True}),
    ("cleared",  "OK",    "G", "down", {"lamp": True, "bob": 2, "bead": True}),
    ("cleared",  "OK",    "G", "down", {"lamp": True, "bob": 1}),
    ("cleared",  "OK",    "G", "down", {"lamp": True}),
    ("cleared",  "OK",    "G", "mid",  {"lamp": True, "card": (33, 44, "tick")}),
    ("cleared",  "OK",    "G", "mid",  {"lamp": True, "card": (33, 44, "tick")}),

    # filing: the citation is recorded. The card travels down into the drawer
    # a few pixels at a time instead of teleporting through it.
    ("filing",   "FILED", "G", "mid",  {"lamp": True, "card": (33, 42, "tick")}),
    ("filing",   "FILED", "G", "mid",  {"lamp": True, "card": (33, 45, "tick")}),
    ("filing",   "FILED", "G", "down", {"lamp": True, "card": (32, 49, "tick")}),
    ("filing",   "FILED", "G", "down", {"lamp": True, "card": (32, 53, "tick")}),
    ("filing",   "FILED", "G", "down", {"lamp": True, "card": (32, 57, None)}),
    ("filing",   "FILED", "G", "down", {"lamp": True, "card": (32, 61, None)}),
    ("filing",   "FILED", "G", "down", {"lamp": True}),
    ("filing",   "FILED", "G", "down", {"lamp": True}),

    # skip: a rule could not be evaluated. It shrugs rather than pretending.
    ("skip",     "?",     "A", "mid",  {"lamp": True}),
    ("skip",     "?",     "A", "mid",  {"lamp": True, "bob": 1}),
    ("skip",     "?",     "A", "up",   {"lamp": True, "bob": 1}),
    ("skip",     "?",     "A", "up",   {"lamp": True}),
    ("skip",     "?",     "A", "mid",  {"lamp": True}),

    # overruled: a holding lost its authority. The strike lands, then the card
    # falls out of the drawer rather than blinking out of existence.
    ("overruled", "X",    "R", "mid",  {"lamp": True, "card": (33, 42, None)}),
    ("overruled", "X",    "R", "mid",  {"lamp": True, "card": (33, 42, None)}),
    ("overruled", "X",    "R", "mid",  {"lamp": True, "card": (33, 42, "cross")}),
    ("overruled", "X",    "R", "mid",  {"lamp": True, "card": (33, 42, "cross"),
                                         "bob": -1}),
    ("overruled", "X",    "R", "mid",  {"lamp": True, "card": (33, 45, "cross")}),
    ("overruled", "X",    "R", "down", {"lamp": True, "card": (32, 50, "cross")}),
    ("overruled", "X",    "R", "down", {"lamp": True, "card": (32, 56, "cross")}),
    ("overruled", "X",    "R", "down", {"lamp": True, "card": (32, 62, "cross")}),
]


def build_frame(spec) -> Canvas:
    state, label, colour, pose, extra = spec
    cv = Canvas()
    cv.oy = 2
    draw_body(cv)
    draw_arm_left(cv)
    # The stamp goes down BEFORE the hand, so the fingers close over the shaft
    # instead of the tool floating beside an open palm.
    if extra.get("stamp"):
        draw_stamp(cv, *stamp_pos(pose))
    draw_arm_right(cv, pose)

    scan = extra.get("scan")
    if scan:
        # An int sweeps the line down the glass; True keeps the old fixed row.
        # A CRT that refreshes in one place is a sticker, not a screen.
        cv.hline(13, 30, 12 if scan is True else int(scan), "s")
    centred(cv, label, 11, colour)
    draw_lamp(cv, extra.get("lamp", True))
    draw_antenna_bead(cv, extra.get("bead", False))

    if extra.get("impact"):
        sx, sy = stamp_pos(pose)
        draw_impact(cv, sx + 4, sy + 10)

    bob = extra.get("bob", 0)
    if bob:
        # Only the head and neck move. Lifting the whole body opened a seam at
        # the waist where the torso left the legs behind; a head that rises on
        # its neck reads as a breath and cannot gap, because the torso top sits
        # directly under the neck either way.
        cv.shift_above(32 + cv.oy, -bob)

    if "card" in extra:                   # props ride above the bob
        draw_card(cv, *extra["card"])
    # Last, so it sees the finished silhouette including whatever the arms and
    # props added to it.
    cv.relight_outline()
    return cv


def sheet() -> tuple[Image.Image, dict]:
    frames = [build_frame(f) for f in FRAMES]
    im = Image.new("RGBA", (W * len(frames), H))
    order: dict[str, list[int]] = {}
    for i, (cv, spec) in enumerate(zip(frames, FRAMES)):
        im.paste(cv.image(), (i * W, 0))
        order.setdefault(spec[0], []).append(i)
    meta = {
        "frame": {"w": W, "h": H},
        "count": len(frames),
        "states": order,
        # Milliseconds per frame, per state. Stepped, never eased - so the way
        # to make a motion smoother is to shorten the frame and add more of
        # them, which is what these numbers are. Each state still takes about
        # as long end to end as it did at a quarter of the frames.
        "timing": {"dormant": 900, "watching": 300, "reading": 110,
                   "halt": 70, "cleared": 110, "filing": 110,
                   "skip": 220, "overruled": 150},
        "loop": {"dormant": True, "watching": True, "reading": True,
                 "halt": False, "cleared": False, "filing": False,
                 "skip": True, "overruled": False},
    }
    return im, meta


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    im, meta = sheet()
    im.save(OUT / "clerk.png")
    im.resize((im.width * 4, im.height * 4), Image.NEAREST).save(OUT / "clerk@4x.png")
    (OUT / "clerk.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  {meta['count']} frames -> {OUT / 'clerk.png'} ({im.width}x{im.height})")
    for state, idx in meta["states"].items():
        print(f"    {state:<9} {len(idx)} frame(s)  {idx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
