# Showing it

Everything here has been run end to end. Ports, commands and expected output are
literal — if a line below does not appear on screen, something is broken and the
demo should stop rather than be talked over.

---

## Before the room

Five minutes, once.

```bash
cd injunct
pip install -e .
python -m pytest -q                  # 281 passed, 9 skipped
```

The nine skips are environment-dependent — no model reachable, no `sleeper`
sibling installed, no opencode runtime — and they skip rather than fail on
purpose. If anything **fails**, stop and fix it; do not present over a red run.

Then make sure the two surfaces both come up:

```bash
python -m injunct board            # the office, port 8850
python -m injunct demo             # the race, ports 8900-8902
```

Leave both running in separate terminals. `demo` holds three ports and dies with
its shell.

**Check the board says nothing is missing.** It lists every page and names any
data file that is absent, along with the command that produces it:

```
  docket: 14 cases, 6 binding, 8 advisory, 0 overruled

  http://127.0.0.1:8850/index.html      the front door: everything below, in one list
  http://127.0.0.1:8850/desk.html       the desk: live, or the recorded session
  http://127.0.0.1:8850/cabinet.html    the docket, and every case file in it
  http://127.0.0.1:8850/chart.html      the evidence: does it help, and where does it hurt
  http://127.0.0.1:8850/tape.html       three hundred runs, replayed
  http://127.0.0.1:8850/overruled.html  how a rule loses its authority
```

**Read that first line before you present.** `board` re-freezes `web/data.json`
from whichever ledger it finds, and they are not equally good: a docket of pack
rules carries almost no empanelment receipts, and the receipt is the one thing
in this project nobody else has. If it comes back thin — lots of rules, almost
no receipts — point it at a benchmark ledger instead:

```bash
python -m injunct board --ledger .bench/C/3/ledger.db
```

The committed `web/data.json` already has six receipts in it, so the safe move
before a demo is to check `git status web/` and throw away a re-freeze you did
not want.

If it prints a `missing` block, run the command it names before you present.

---

## The ninety seconds

Open on **the race**, at `http://127.0.0.1:8900`, and say one sentence:

> Same task, same model, same seed, one clock. The left agent has no memory. The
> right one has been here before.

Press **Play**. Do not narrate while it runs.

| beat | what appears |
|---|---|
| ~0:02 | both agents read `models/patient.py` |
| ~0:05 | both write the field. **The right one is HALTED** |
| ~0:07 | the halt card slides in, citing holding No 1 and naming the file to create |
| ~0:10 | the right agent writes `migrations/003_phone_verified.sql` |
| ~0:14 | **left: "Service unavailable — no such column: phone_verified"**. Right: the patient list, with a new VERIFIED column |

Then the only line that matters:

> Nobody had to read a diff to see which one is still standing.

**If Play does nothing**, the previous run finished and the state is on the
server. Press it again — it now resets first — or hit **Reset** then **Play**.

---

## The five minutes, if they want depth

Go to `http://127.0.0.1:8850/desk.html`. With no watcher running it plays a
**recorded** session, labelled `replay` in the status pill. It is a real capture
of `injunct watch`, not an animation.

Three objects on that wall are doors. Click them in this order.

### 1. The cabinet → the docket

Four drawers by authority. Pull **binding**. The folders in the drawer are the
rules — click one and the file opens beside the cabinet.

Stop on **the receipt**. This is the part no other tool in this category has:

> `1/1` fired on its own case · `0/5` false on past successes · `6` times cited
>
> *It fired on the case that produced it, and stayed silent across 5 past runs
> that succeeded. That is what buys it the authority to stop a change.*

Then show a rule that **did not** get that authority — the advisory drawer, No 5:

> *It did not fire on the case that produced it. A rule that misses its own case
> cannot be trusted to catch the next one, so it was demoted to advice.*

That contrast is the argument. A memory layer that trusts every lesson it
extracts is one that gets confidently wrong.

### 2. The corkboard → the evidence

Lead with the result, which is what the page now does:

| | A — no memory | C — binding gates |
|---|---|---|
| first-try pass | 53% | **70%** |
| on trapped tasks | 39% | **61%** |
| fell for the same trap twice | 58% | **31%** |
| stopped, and passed anyway | — | **54 of 58** |

Then scroll to the second sheet and say the uncomfortable part out loud, because
they will find it anyway:

> Below about **21% compliance this makes agents worse than no memory at all.**
> A gate the agent ignores costs a run and buys nothing.

And the four caveats below it — false positives, the 9 regressions, arm B unrun,
the synthetic agent. **Do not skip these.** A panel that finds a caveat you hid
stops believing the headline; a panel that watches you volunteer one starts
believing everything else.

### 3. The in-tray → the tape

Press **run the tape**. 300 runs in about three seconds, five rows per arm, one
row per seed, left to right in the order they ran.

> Arm A stays scattered. Arm C greens toward the right of every row, because the
> precedents that stop it were established earlier in that same run.

The numbers under it: first ten tasks of a seed → last ten. **A: 46% → 48%.
C: 50% → 86%.** That is the claim with no sentence attached.

---

## If they ask to try it themselves

This takes ninety seconds in any repository and it is the strongest thing you
can do, because nothing is seeded:

```bash
cd ~/some-project
injunct rule "models/*.py needs migrations/"
#   Changing models/*.py means changing migrations/ too.
#   co_change( models/*.py -> migrations/** )
#   BINDING

# edit a model, do not write a migration
injunct gate .
#   HALT   BINDING HOLDING No 1   ESTABLISHED 11 SEP 2026
#   models/patient.py changed, nothing under migrations/** did
#   DO THIS NEXT:  create migrations/002_injunct.sql
```

Point at the last line. **That filename is not a template** — it is read off
their repository's own migration naming.

Then:

```bash
injunct why models/patient.py     # which rules apply here, and the case behind each
injunct off 1                     # this rule is wrong
injunct gate .                    # passes now; the case is still on file
injunct init                      # mine their git history for rules
```

`init` is worth running on a real repo in front of them, because it is also
willing to find nothing — on a history with no habit strong enough to be a rule
it says so rather than inventing one.

---

## Inside Claude Code — do this one live

This is the strongest ninety seconds you have after the race, because it
happens in the tool the room already uses, on a repository you make in front of
them, with nothing seeded.

```bash
mkdir demo && cd demo && git init -q
mkdir -p models migrations
printf 'FIELDS = ["id","name"]\n'          > models/patient.py
printf 'CREATE TABLE patients(id INT);\n'  > migrations/001_init.sql
git add -A && git commit -qm seed

injunct rule "models/*.py needs migrations/"
injunct claude
git add .claude && git commit -qm "install injunct"
```

Say the setup out loud, because the absence is the point: **no service, no
daemon, no key, no model.** Then open Claude Code in that directory and ask it
to add a field to the patient model.

The write is **denied before the bytes land**, and the model is handed this:

```
BLOCKED BY INJUNCT - this exact change failed here before.

  Holding No 1, established 12 Sep 2026. Changing models/*.py means changing migrations/ too.
  Rule:   co_change( models/*.py -> migrations/** )
  Reason: models/patient.py changed, nothing under migrations/** did
  Tested: not empanelled - you wrote this rule yourself.
  DO THIS NEXT: create migrations/002_patient.sql
```

Three things to point at, in this order:

1. **`002_patient.sql`** — not a template. It read the repo's own migration
   naming off `001_init.sql` and produced the next one in the sequence.
2. **`Tested: not empanelled - you wrote this rule yourself.`** — it will not
   claim evidence it does not have. Contrast it with a benchmark rule in the
   cabinet reading `1/1 fire, 0/5 false positives`.
3. Let the agent write the migration, then watch the same edit **go straight
   through**. A gate that only ever says no is a gate nobody keeps.

If someone asks what happens when it breaks: delete `.injunct/ledger.db` and
try again. The write succeeds. Every failure path — no ledger, bad payload,
unreachable service, an outright crash — allows the write, because a memory
layer that can wedge your agent by being broken is worse than not having one.

---

## Inside opencode

```bash
injunct opencode        # installs the plugin into .opencode/plugins/
injunct serve           # the plugin decides nothing on its own
opencode
```

Ask it to add a field to a model. The write is **aborted before the bytes land**
and the card goes back to the model as the tool's error.

Worth naming: an advisory memory plugin can sit on the same hook and still
let every call through. Ours throws. That is the whole difference between
advice and enforcement, in one line.

---

## Questions you will get

**"Isn't this just a linter?"**
It is a linter nobody wrote. The rules come from this repository's own failures,
they carry the case that created them, and they are retired when the evidence
turns against them. Show the receipt and the overruled page.

**"What if it blocks something it shouldn't?"**
`injunct off <n>` mutes it and keeps the case. A tool that blocks you once for
a bad reason and gives you no way out gets uninstalled, and everything it ever
learned goes with it. Also: false positives are a headline metric on the
evidence page, not a footnote — measured at 0.0% across 540 runs, and we found a
real one in live testing and put it on the page.

**"Does it need a model / an API key / a database?"**
No, no and no. Python and the standard library. One SQLite file. The model is
optional and only fills in a typed schema when compiling a case; with none
reachable the deterministic fallback takes over. It runs on a closed laptop.

**"Has it been proven against a real agent?"**
Partly, and here is exactly how far. The 300-run benchmark uses a scripted
agent, which measures the enforcement layer rather than a language model — the
page says so. Against real models the plugin has been shown to block live. The
three-arm comparison against a live model is **not** done, and the reason is on
the page.

**"Why not a knowledge graph like theirs?"**
At 41 cases, 9 node types and 8 edge types with a 3-hop recursive query encodes
nothing that four tables and a cosine do not. We would rather spend the
complexity on proving it works. That is on the slide, deliberately.

---

## What not to do

- **Do not run the live benchmark in the room.** It takes 11–50 minutes and it
  depends on a provider being reachable.
- **Do not open `demo.html` from the board.** The race lives on port **8900**
  under `injunct demo`; the copy served at 8850 has no apps behind it and the
  panes will read "unable to connect".
- **Do not claim arm B.** "Gates beat warnings" is the thesis, not the finding.
  The finding is "gates beat no memory", and it is worth having on its own.
