# The records office — UI and design requirements

One room. Every screen is a piece of furniture in it. Navigation is walking
around a place you already understand, not clicking tabs.

The character is a clerk with a CRT for a head. It never emotes, because
nothing here feels anything — the screen where a face would be **displays the
record**. That is the whole reason the mascot is allowed to exist: it is a
readout, not a personality.

---

## 0. Non-negotiables

These decide arguments before they start.

| | Rule | Why |
|---|---|---|
| 1 | **Every state shown is a real state** | The clerk's five poses map to verdicts the system actually produces. No idle animation that means nothing. |
| 2 | **Charm on the live surface, sobriety on the evidence** | The tape, wall chart and withdrawn drawer stay legible and typographic. Our strongest asset is that we measured ourselves honestly; pixel art must not undercut it. |
| 3 | **Motion is stepped, never eased** | `steps()` only. Smooth easing makes retro read as a modern UI in a costume. |
| 4 | **Pixel type for chrome, real type for reading** | Bitmap for labels, numbers, the clerk's screen. Anything a person must actually read stays in a legible face. |
| 5 | **No face, ever** | A face has to emote and emoting is fiction. A screen displays. |
| 6 | **Assets must be ours or CC0** | Kenney.nl packs restyled to the CRT head. No watermarked stock. |

---

## 1. Design system

**Palette** — 12 colours, no gradients, no glow.

```
ink        #171219   the room
panel      #1E1822   furniture
line       #2E2430   every border
paper      #F2EAD8   documents
paper-dim  #B9AC96   ruled lines
putty      #A9B0A4   CRT plastic
phosphor   #6FCF97   cleared, pass
amber      #C8A24A   authority, advisory
stamp      #B4402C   halt, binding, withdrawn
desk       #6B4A32   surfaces
olive      #7C8A72   filing cabinet
dim        #5E5348   anything receding
```

**Grid** — everything on 4px. `image-rendering: pixelated`. Borders are 2px or
3px, never 1px.

**Type**
- Chrome, labels, numbers, clerk screen: a bitmap face at 8/16px steps only.
- Body, reasons, caveats, curve annotations: system serif/sans, 13–15px.
- Never set a bitmap face below its design size. It stops being retro and
  starts being unreadable.

**Motion**
- `steps(2)` for flicker, `steps(3)` for the stamp arm, `steps(4)` for drawers.
- One motion budget per screen: exactly one thing has weight. On the Desk it is
  the stamp landing; in the Cabinet it is the drawer travelling.
- `prefers-reduced-motion` removes all of it and loses nothing.
- **Smoothness is bought with frames, never with interpolation.** When motion
  reads as choppy the answer is more drawn frames and a shorter interval — the
  clerk went from 26 frames to 65 and from four states of four frames to ten —
  not an eased tween inventing the in-betweens. An interpolated curve is what
  makes pixel art read as a modern UI wearing a costume, which is law 3 above.
- Durations are whole multiples of one frame (70ms), named in `web/motion.css`
  as `--t-tick` / `--t-quick` / `--t-beat` / `--t-heavy`.

**Where motion lives.** `web/motion.css` — every page links it, because a
drawer that opens in four steps on one screen and glides on another is two
different buildings. It is additive only: no colour, no font, no box, so it
cannot move a page's furniture. Colours stay per-page (and in `office.css` for
the front door), since each room is lit differently.

---

## 2. The clerk

Eight states, each driven by a real event from `/v1/events`. Frame counts are
whatever it takes to read as motion rather than as a flicker-book — the stamp
gets ten because it is the one thing on the screen with weight.

| State | When | Screen shows | Frames | Pose |
|---|---|---|---|---|
| **Dormant** | no service connected | `·` | 6 | dim, still, lamp out |
| **Watching** | connected, tree unchanged | `-` | 10 | one slow breath, scan sweeps, bead blinks |
| **Reading** | a `sitting` arrived | rule count | 10 | leaning, scan crossing the glass twice |
| **Halt** | any seat `verdict=halt` | `HALT` | 10 | raise, hold, fall, land, recoil, settle |
| **Cleared** | `recovered` event | `OK` | 8 | a hop with a real arc, then the card is ticked |
| **Filing** | after cleared | `FILED` | 8 | the card travels down into the drawer |
| **Skip** | a seat could not be evaluated | `?` | 5 | a shrug, rather than a pretence |
| **Overruled** | a holding lost authority | `X` | 8 | struck through, then the card falls |

The clerk is one component with a `state` prop. It appears on the Desk at full
size and in the header at 24px as a live status indicator on every screen.

---

## 3. The screens

Each has: a job, its data, the states it must handle, and what "done" means.

### 3.1 The Desk — live
**Job:** show every rule's decision as it happens, with any agent or editor.
**Data:** `GET /v1/events` (SSE) → `sitting`, `recovered`, `watch.start`.
**Must handle:** no service · connected but idle · halt · cleared · a rule that
could not be evaluated (`skip`).
**Done when:** editing a file in a watched repo moves the clerk within one
second, the halt card carries its next step, and satisfying it produces
CLEARED without a refresh.

### 3.2 The Cabinet — the docket
**Job:** what this repo has learned, and how much authority each rule holds.
**Data:** `web/data.json` → holdings.
**Must handle:** empty ledger · binding vs advisory vs overruled · a rule with
zero citations.
**Done when:** a drawer opens on click, rules read as cards inside it, and the
empty state explains the mechanism rather than apologising.

### 3.3 The Card — one case
**Job:** prove a rule is not a guess.
**Data:** one holding + its case + citations.
**Must handle:** empanelled · mined from history · authored by you · never yet
cited.
**Done when:** the empanelment receipt is as prominent as the rule, and the
three provenances are visually distinct.

### 3.4 The Wall Chart — the evidence
**Job:** the compliance curve and what it costs to be wrong.
**Data:** `bench/compliance.json`, `bench/report.json`.
**Must handle:** the harmful zone below 25% compliance must be as visible as
the good news.
**Done when:** a reader can state, unprompted, that below a quarter compliance
the tool makes agents worse.

### 3.5 The Tape — the benchmark
**Job:** 300 runs replayed; one column learns, the other does not.
**Data:** `report.json` → `tape`.
**Must handle:** playing · finished · replay.
**Done when:** it reads in ten seconds with no narration.

### 3.6 The Withdrawn Drawer — overruled
**Job:** precedents we retired, and what overturned them.
**Data:** holdings with `status=overruled`.
**Must handle:** **currently empty, and that is the honest state.**
**Done when:** the empty state explains the mechanism and does not fake a row.

---

## 4. Build order

Each step ships and is judged before the next begins.

1. **Design tokens + the clerk component** — five states, driven by fake events
   first, then real. Nothing else can be judged until the character exists.
2. **The Desk** — replace the current Live view. Highest value: it is the only
   screen that shows the product working.
3. **The Wall Chart** — the evidence, restyled. Second because it is what
   survives scrutiny.
4. **The Cabinet + The Card** — browsing what was learned.
5. **The Tape** — restyle the existing dot replay into the room.
6. **The Withdrawn Drawer** — smallest, and honest by construction.

The scroll-film front door is a separate artefact and comes after all six, or
not at all.

---

## 5. What would make this fail

- A room that is decoration rather than navigation. If the furniture does not
  do the job of the screen, it is a background image and should be deleted.
- Pixel art that makes numbers hard to read. The moment a caveat is less
  legible than a sprite, rule 2 has been broken.
- States that exist for charm. Every pose must trace to an event in the stream.
- A demo that needs narration. The Desk and the Tape must both land silently.
