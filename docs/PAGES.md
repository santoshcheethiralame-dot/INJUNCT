# The pages

Build spec for the records office. Each page names its furniture, its exact data
binding, the clerk state it shows, and what "done" means. Nothing here is
specified against data we do not have — where a gap exists it is written down.

Design law lives in [DESIGN.md](DESIGN.md). This is the execution.

---

## 0. The shell — build this first

Everything else inherits it, so it is not a page but it is the first task.

**`web/office.css`** carries the tokens, taken verbatim from
`injunct/art/clerk.py` so art and interface can never drift:

```
--ink #171219   --panel #1E1822  --line #2E2430  --paper #F2EAD8
--paper-dim #D8CDB6  --putty #A9B0A4  --glass #0C1410
--phos #6FCF97  --amber #C8A24A  --stamp #B4402C
--desk #6B4A32  --desk-dark #543A27  --olive #7C8A72  --dim #5E5348
```

**Primitives** (a small kit, reused everywhere):

| Class | What it is |
|---|---|
| `.plate` | a panel with a 3px ink border and a 1px inner bevel — the base surface |
| `.bevel-in` / `.bevel-out` | light top-left, dark bottom-right, and the reverse |
| `.stamped` | a rotated stamp mark, used for status |
| `.drawer` | a cabinet face with a pull handle, opens with `steps(4)` |
| `.card` | an index card: cream, ruled lines, 3px border |
| `.tape-strip` | a run of dots on a perforated paper band |
| `.pixel-type` | bitmap face, integer sizes only |

**Rules that bind every page**

1. Borders are 3px ink, never 1px. Radii are 0 or 4px, nothing between.
2. All motion `steps()`. One thing per page carries weight.
3. Body copy is a legible face at 13–15px. Bitmap type is for labels, numbers
   and the clerk's screen only.
4. The **header** carries the clerk at 1× as a live status light, wired to the
   same event stream as the Desk. It is the same component everywhere.
5. Every page must render with the service down.

---

## 1. The Desk — live *(replaces the current Live view)*

**Furniture.** A desk across the lower third. The clerk stands behind it at 3×.
Papers arrive on the desk as a change lands. Behind: the cabinet on the right,
the wall chart on the left, both clickable — that is the navigation.

**Regions.**
- Clerk, centre, 144×222 (3× of 48×74).
- Desk surface with the incoming change: filenames on a paper.
- Halt card slides out from under the stamp when a binding rule fires.
- Below the desk, the full panel: every rule that looked, with its verdict.

**Data.** `GET /v1/events` → `sitting` · `recovered` · `watch.start`.
Seat fields available: `holding_id, template, domain, says, status, verdict,
reason, next, took_ms`. Domains: `structure, hygiene, tests, context, cost,
borrowed, advice`.

**Clerk state.** `watch.start` → watching · `sitting` with any halt → halt ·
`sitting` all clear → reading then cleared · `recovered` → cleared then filing ·
a seat with `verdict=skip` → skip · no service → dormant.

**States to handle.** No service · connected idle · halt · cleared · skip ·
a rule that errored.

**Done when.** Editing a file in a watched repo moves the clerk within a second;
the halt card carries its `next` line; satisfying the rule plays cleared then
filing without a refresh; and with the service down the page shows the dormant
clerk and says how to start one.

---

## 2. The Cabinet — the docket

**Furniture.** A four-drawer olive filing cabinet, front on. One drawer per
status: **binding**, **advisory**, **overruled**, **all**. Clicking a drawer
slides it open in four steps and the cards inside rise.

**Regions.** Cabinet left, cards right. Each card: number, the rule in human
words, the machine form in bitmap type, status stamp, citation count.

**Data.** `web/data.json` → `counts` and `holdings[]`. Per holding:
`id, says, template, params, status, scope, established, citations[], case{}`.
Currently: **6 cases · 4 binding · 2 advisory · 0 overruled.**

**Clerk state.** Not present. This is a room the clerk is not in.

**States.** Empty ledger · a drawer with nothing in it · a rule never cited.

**Done when.** A drawer opens on click, the cards read as cards, and an empty
drawer says what would put something in it.

---

## 3. The Card — one case

**Furniture.** A single index card under a desk lamp, on the desk surface.

**Regions.** The rule large, in the serif. The machine form beneath in bitmap.
Then three blocks: **the facts** (task, what was touched, what failed), **the
receipt** (empanelment), **the citations** (every firing and its outcome).

**Data.** One holding plus `case{ source, confidence, summary, touched, filed }`
and `empanel{}`. Three provenances must look different: **empanelled**
(fire/false counts), **mined from history** (support/confidence), **you wrote
this** (no test possible).

**Clerk state.** Not present.

**States.** Never cited · empanelled · mined · authored · overruled.

**Done when.** The receipt is as prominent as the rule, and the three
provenances are distinguishable at a glance without reading the labels.

---

## 4. The Wall Chart — the evidence

**Furniture.** A chart pinned to the wall with four pins, slightly askew.

**Regions.** The compliance curve as a pixel line chart, the harmful zone below
25% shaded in stamp red and **labelled**, not merely coloured. Beside it: the
three honesty panels — false positives, regressions, arm B unrun.

**Data.** `bench/compliance.json` — 5 points, `harmful_at_or_below: 0.25`,
`baseline_A`. Plus `web/report.json` → `metrics`, `by_trap`, `regressions`.

**Clerk state.** Not present. This page is sober by law (DESIGN.md rule 2).

**Done when.** A reader can state, unprompted, that below a quarter compliance
the tool makes agents worse. Numbers stay in a legible face at full contrast.

---

## 5. The Tape — the benchmark

**Furniture.** A perforated printout feeding out of a dot-matrix printer, two
columns of runs, arm A red-heavy and arm C greening as it learns.

**Data.** `web/report.json` → `tape{A[], C[]}`, each entry `{p, b, t, task}`.

> **Data gap — fix before building.** The tape currently holds **arm A only,
> 30 entries**. A previous run overwrote the 300-run file. Regenerate with
> `python -m injunct bench --arms A,C --seeds 1,2,3,4,5` and re-dump.

**Clerk state.** Not present.

**Done when.** It reads in ten seconds with no narration, and the divergence is
visible without the legend.

---

## 6. The Withdrawn Drawer — overruled

**Furniture.** The bottom drawer of the cabinet, open, with the retired cards
face up and struck through in red.

**Data.** `holdings[]` where `status=overruled`. **Currently zero, and that is
the honest state.**

**Clerk state.** The overruled animation, once, on entry — the only page other
than the Desk where the clerk appears.

**Done when.** The empty state explains the mechanism and does not fake a row.

---

## Build order

Each ships and is judged before the next starts.

| | Page | Why here |
|---|---|---|
| 0 | The shell | Everything inherits it |
| 1 | The Desk | The only page that shows the product working |
| 2 | The Wall Chart | What survives scrutiny |
| 3 | The Cabinet | Browsing what was learned |
| 4 | The Card | Depth behind the cabinet |
| 5 | The Tape | Needs its data regenerated first |
| 6 | The Withdrawn Drawer | Smallest, honest by construction |

---

## What would make this fail

- Furniture that is decoration rather than navigation. If the cabinet does not
  open the docket, it is a background image and should be deleted.
- The clerk appearing on pages where it has no state to report. It is a
  readout, not a mascot, and putting it on the wall chart would prove otherwise.
- Numbers rendered in bitmap type. The moment a caveat is harder to read than a
  sprite, DESIGN.md rule 2 has been broken.
- A page that cannot render with the service down.
