# The script

Written the way you'd explain it to a friend. No jargon unless it's explained
the line before. Every claim here is one the project can actually back up.

---

## Part 1 — The idea, in the simplest words

### The problem

You tell an AI to add a field to your database model. It edits the model file.
It forgets the migration — the separate file that actually changes the database.
Your app breaks.

You tell it off. It fixes it. Fine.

**Next week, same thing.** Different field, same mistake. Nothing remembered.

This isn't a rare bug. We measured it: **an agent falls into a trap it has
already been burned by 58% of the time.** More than half. It's the single most
annoying thing about working with these tools.

### What everyone else does

The obvious fix: write the mistake down, and paste it into the AI's instructions
next time. *"Remember: when you change a model, write a migration."*

That's what the existing tool in this space does. And it's better than nothing.

But here's the catch. **A note in the instructions is a suggestion.** The model
reads it, and then it reads ten thousand other tokens, and by the time it's
actually editing the file the note is a distant memory. Under pressure — long
context, complicated task — it just doesn't follow it.

We're not guessing about this. The tool we're comparing against has a plugin
that *could* stop the write, and its own source code comment says it
**"never blocks a tool call, even if the service returns block=true."** They
built the hook and chose not to pull the trigger.

### What we do

We take that same mistake and turn it into **a check that actually stops the
write.** Not a note. A wall.

The AI goes to save the file, our check runs, and if it breaks a rule **the save
is cancelled before anything touches the disk.** The AI gets told why, and what
to do instead.

> **Their tool tells the agent about the crash. Ours takes the keys.**

### The part that makes it trustworthy

Now, the obvious worry: *if it blocks things, won't it block the wrong things and
drive me mad?*

Yes — that's exactly the failure mode, and it's why most tools stay advisory.
Advisory is safe because it can't be wrong in a way that costs you anything.

So we built a test that every rule has to pass before it's allowed to block
anything. We call it **empanelment** (from a jury being empanelled — sworn in
before it's allowed to judge).

Before a rule gets any power, we replay it against your history:

1. **Does it catch the failure that created it?** If it can't even catch its own
   case, it's useless.
2. **Does it stay quiet on work that already went fine?** We run it against your
   past successful runs. If it would have blocked something that worked, it's
   wrong.

**Fail either test and it's demoted to advice.** It still tells you, it just
can't stop you.

And every rule carries its receipt, visible on screen:

> `1/1 fired on its own case · 0/5 false on past successes · cited 6 times`

### And rules can be fired

A rule that was right in March can be wrong in July. Code changes.

So every time a rule fires, we write down what happened next. Did the agent
obey and the work passed? Did the agent override it and succeed anyway?

**Three overrides that succeeded anyway and the rule is retired** — it stops
blocking, and it's published on a page of our own retracted rules.

That last part is deliberate. A memory that can only grow can only get more
wrong. And publishing the ones we got wrong is cheaper credibility than any
feature.

---

## Part 2 — Every feature, explained properly

### The three ways a rule gets created

**1. It watched you fail.**
The normal path. Something broke — a test went red, a command exited non-zero,
you rejected a change — and we turn that into a rule automatically.

We also catch mistakes **with nobody watching at all**, which the competing tool
can't:
- **churn** — the agent wrote a file, then rewrote it and undid most of what it
  just did. It argued with itself. That's a mistake with no human in the loop.
- **revert** — the change got reverted.
- **test flip** — a test that was passing started failing inside one run.

**2. You told it.**

```bash
injunct rule "models/*.py needs migrations/"
```

One sentence, plain English. Three shapes it understands: *"X needs Y"*,
*"never touch X"*, *"after X run Y"*. Anything else and it prints the three
shapes rather than guessing.

Why this matters: **you already know your repo's rules.** Making you wait to be
burned before the tool knows them is silly.

**3. It read your git history.**

```bash
injunct init
```

This is the one that solves the real adoption problem. Every memory tool has the
same flaw: **on day one it knows nothing.** Useless until something breaks.

`init` reads your commit history and works out your habits before anything goes
wrong. On a real project of ours it figured out *"touching `results/` always
means touching `docs/`"* — a working practice nobody had ever written down.

It's also willing to find **nothing**. On a repo with no strong habit it says so,
because inventing a rule would be worse than having none.

Three tests decide whether a pattern becomes a rule:
- **support** — did this happen often enough to be a habit, not a coincidence?
- **confidence** — when A moves, does B really move too?
- **asymmetry** — when B moves, does A *not* move? This one took us the longest.
  If two things always move together, the data can't tell you which one is the
  trigger. Without this test, one big initial commit makes everything "always"
  pair with everything.

Everything `init` finds lands as **advice**, never a block. History tells you
about habits, not about harm.

### The seven kinds of thing it checks

**1. Structure — "you moved one thing but not its partner"**

The classic. Model without migration. API spec without regenerating the client.
Config without the docs.

**2. Security — the only group where everything blocks**

Never commit an AWS key, a private key, an API token. Never write a migration
that deletes a column. Never turn off certificate verification. Plus: you
removed a login check, you removed a CSRF token, a password is being hashed with
a broken algorithm, debug mode is on in a config file, a shell command is being
built from user input, untrusted data is being unpickled.

No failure required. These ship on day one because **nobody should have to leak
a key once to learn the tool could have caught it.**

**3. The agent can't switch us off**

This one deserves its own paragraph.

The AI is not allowed to edit `.injunct/`, the git hooks, the plugin file, the
CI workflows, or its own permissions config. If it could turn off its restraints,
nothing else here means anything.

**And this is not hypothetical — it's happened to us twice.** Once an agent
walked out of its own folder and wrote into our test data, silently changing
what every future measurement meant. Another time a plugin file quietly went
missing and every arm of our benchmark became a bare agent with no memory —
still printing numbers that looked like results.

An advisory tool has nothing worth disarming. Ours does. So we guard it.

**4. Hygiene — the small stuff you're embarrassed to ship**

A `pdb` breakpoint or a `debugger;` left in (these block — nobody ever meant
those). A `console.log`, a stray TODO, an exception swallowed silently, an empty
catch block, a removed `raise` (these just tell you).

**5. Tests — making the red go away the wrong way**

You deleted a test. You marked one as skipped instead of fixing it. These are
advisory on purpose — tests genuinely do get deleted during a real refactor, and
a tool that blocks a legitimate refactor gets uninstalled.

**6. Context — "you changed this, but who else uses it?"**

This one is genuinely clever. You changed a function's *shape* — added an
argument, changed what it returns. **Fourteen other places still call the old
version.**

We build a map of your code — what calls what — from scratch on every check,
using Python's own parser. No model, no index server, nothing that goes stale.

A structure rule asks *"did the other folder move?"* This asks *"did you finish
the job?"*

**7. Cost — a slow thing you just wrote**

Nested loops over the same list, a database query inside a loop, a string being
built with `+=` in a loop. Things that work fine with 10 rows and die with
10,000.

**Only lines you just added.** A codebase full of existing slow code is not this
change's fault, and a tool that blames you for code you didn't touch gets
switched off within the hour.

**Plus four borrowed.** Hallucinated imports (the agent imported a package that
doesn't exist), documentation that no longer matches the code, a claimed
complexity that doesn't match reality, and a function that already exists
elsewhere. Taken from our sibling project rather than rebuilt. If it isn't
installed, they **abstain** — a check that fires because a dependency is missing
fires on everything.

### Three ways to run it

**`injunct watch` — works with everything, stops nothing**

It reads **git**, not the AI. So it doesn't care whether you're using opencode,
Cursor, Claude Code, or typing by hand. It sees every change and reports every
rule's decision live.

**The competing tool only works with one AI harness.** Ours works with all of
them, and there's no plugin to keep updated as each one changes.

The trade-off: it watches, it can't refuse. It tells you after the fact.

**The Claude Code hook — refuses, and this is the one most people can use**

```bash
injunct claude
```

That's it. No service to start, nothing running in the background, no key. It
registers itself on the moment *before* a file is written, and if a binding
rule fires the write is **denied** — the AI is handed the card as the reason it
was refused, and told the one thing to do about it.

It also puts the rules into the AI's instructions before it starts. That half
matters more than it looks, and our own numbers say so: being blocked costs a
whole turn while the model works out what happened, but being *told* costs one
sentence and it just does it right.

**The opencode plugin — refuses**

```bash
injunct opencode
injunct serve
```

This one hooks the same moment and **throws**, which cancels the save. The
bytes never reach the disk, and the explanation goes back to the AI as the
error.

Both build the same card from the same code, and a test asserts they stay
identical — an AI shouldn't be able to tell which tool refused it.

Both **fail open**: if anything at all goes wrong — our service is down, the
rules file is missing, our own code crashes — the write goes through. A memory
layer that can freeze your agent by being broken is worse than no memory layer.

### Telling the agent before it acts

This is the half people miss.

Blocking is the safety net. But being blocked costs a whole turn — the agent has
to work out what happened and try again. **Being told costs one sentence and it
just does it right the first time.**

So before the agent starts, we put the relevant rules straight into its
instructions:

> *This repository will STOP a change that breaks these. They are not
> suggestions:*
> *— Changing models/*.py means changing migrations/ too.*

We found a real bug here during this build: this was returning an **empty
string**. The code was ranking rules by word-similarity, and *"add a
phone_verified field to the patient model"* scored **exactly zero** against
`models/*.py`. The gate doesn't consult a similarity score before firing, so the
briefing shouldn't either. Now every binding rule is named.

### Telling it what to do, not just "no"

Every block names the next action:

> **DO THIS NEXT: create migrations/002_injunct.sql**

**That filename is not a template.** We read your repo's own migration naming
and produce the next one in your sequence. If your files are called
`104_allergy.sql`, you get `105_something.sql`.

This matters more than it looks. Our own numbers show **the gate is not the
mechanism — the instruction is.** Blocking something that then ignores you costs
a run and buys nothing.

### Getting out of it

```bash
injunct off 4
```

Mutes a rule. Keeps the case that created it. `injunct on 4` brings it back.

A tool that blocks you once for a bad reason and offers no way out gets
uninstalled — **and everything it ever learned goes with it.**

---

## Part 3 — How it's built

```
Python 3.12, standard library only.
6,151 lines. 239 tests.
One SQLite file per repo. Four tables.
No Docker. No Postgres. No server. No API key needed.
Runs offline on a closed laptop. Costs nothing.
```

**Compare:** the competing tool needs Postgres 16, the pgvector extension,
Docker Compose, a FastAPI backend, a Next.js frontend, and a Google API key for
embeddings.

We need a file.

**Where's the AI in our system?** Almost nowhere. A model is used *only* to pick
which of eleven check-shapes fits a failure and fill in the blanks. It never
writes code, and it is **never** involved in deciding whether to block you —
that's all deterministic. Take the model away and a fallback handles it.

**Why no knowledge graph?** They built 9 node types and 8 edge types with a
3-hop recursive database query. Over about 40 failures, that encodes nothing
that four tables and a bit of arithmetic don't. We'd rather spend the complexity
on proving the thing works — and we say that out loud rather than hiding it.

---

## Part 4 — The numbers

300 runs. Same tasks, same random seeds, same order, same agent. **The only
difference is whether the gate is switched on.**

| | no memory | with injunct |
|---|---|---|
| got it right first try | 53% | **70%** |
| got it right on a trap task | 39% | **61%** |
| **fell for the same trap twice** | **58%** | **31%** |
| false alarms on innocent tasks | 0% | **0%** |

Said the way that actually lands:

> ### Same task, run twice. The gate won 34 and lost 9.

And it **learns during the run**. First ten tasks of a session vs the last ten:

| | first ten | last ten |
|---|---|---|
| no memory | 46% | 48% |
| with injunct | 50% | **86%** |

The first arm has nothing to accumulate, so it stays flat. That gap is the whole
thesis in two rows.

### The honest half — say this before anyone asks

**One. If the agent ignores us, we make things worse.** We swept this properly:
540 more runs at five different obedience levels. **Below about 21% compliance,
having the tool is worse than not having it.** You spend runs and buy nothing.

**Two. Nine tasks passed without us and failed with us.** Out of 150. Six of
them on one trap class. We publish the list.

**Three. Our agent is scripted, not a real AI.** It measures the enforcement
layer, not a language model's intelligence. The page says so.

**Four. We have not proved we beat prose.** This is the big one. Our claim is
*"warnings are optional, gates are not."* We've proved **gates beat no memory**.
We have **not** proved gates beat warnings, because that needs a real model
running all three arms and we haven't completed that run.

Four attempts, four different problems — every one a real bug we found by
trying: a subprocess with no timeout froze the run; our success check rewarded
an agent that did nothing; a rate limit produced 90 runs that never reached the
model and scored them all as passes; and the free models we can reach only
attempt the task one time in four.

All four are now fixed or guarded — the benchmark **refuses to write a report**
if more than 10% of runs never reached the model.

**Why volunteering this is the right move:** a judge who finds a caveat you hid
stops believing your headline. A judge who watches you volunteer one starts
believing everything else you said.

---

## Part 5 — The demo

Two things to start. Do it before you present.

```bash
injunct board      # the office  -> http://127.0.0.1:8850
injunct demo       # the race    -> http://127.0.0.1:8900
```

### The race — 90 seconds, don't talk over it

Open `http://127.0.0.1:8900`. One sentence before you press Play:

> Same task, same model, same seed, one clock. Left has no memory. Right has
> been here before.

Press **Play**.

| beat | what's on screen | what to say after |
|---|---|---|
| both agents read the model | identical so far | — |
| both write the field | right one says **HALTED** in red | — |
| **22 rules looked, 21 said fine, 1 stopped it** | a row of green dots, one red | *"that's a gate, not a tripwire"* |
| the card appears with its receipt | the rule, the reason, the next file | — |
| right writes the migration | it was told exactly which file | — |
| **left app dies** — *Service unavailable* | right app still live, new column | *"you don't need to read code"* |
| left agent repairs it, app comes back | agents do fix things when told | — |
| **both add another field — left forgets again** | left dies a second time | **this is the whole project** |
| right is halted again, stays up | the memory is still there | — |

The closing line:

> Nobody had to read a diff to see which one is still standing. And the left one
> made the same mistake twice — that's the 58% we measured.

**Notice the left panel says "nothing is watching this change."** That emptiness
next to 22 green dots is the argument, without a word.

### The office — 3 minutes

`http://127.0.0.1:8850/desk.html`. The clerk is working; no server needed, it
plays a real recorded session.

Four things on the wall are doors:

| click | what you get | what to say |
|---|---|---|
| **the window** | the race | — |
| **the filing cabinet** | every rule, in drawers by authority | pull *binding*, click a folder |
| **the corkboard** | the evidence, the numbers, the caveats | lead with 53→70, then volunteer the harmful zone |
| **the in-tray** | 300 runs replayed in 3 seconds | press *run the tape*, point at **34–9** |

**In the cabinet, do this one thing.** Open **binding → No 4** and read its
receipt. Then open **advisory → No 5**:

> *It did not fire on the case that produced it. A rule that misses its own case
> cannot be trusted to catch the next one, so it was demoted to advice.*

**That contrast is the pitch.** We don't trust our own lessons until they pass a
test. Nobody else in this space does that.

### Let them try it — 90 seconds, their repo, nothing seeded

```bash
injunct rule "models/*.py needs migrations/"
# now edit a model and don't write a migration
injunct gate .
```

Point at the last line. That filename came from **their** repo's naming.

---

## Part 6 — The three reviews

Three checkpoints, roughly five hours apart. Here's exactly what's ready, what
to show, what to say, and what they'll push on.

---

### REVIEW 1 — *"What are you building, and why should it exist?"*

**Time: the first five hours. Goal: they believe the problem is real.**

#### Open with the problem, not the product

> "Everyone here has used an AI coding assistant. Everyone here has watched it
> make the same mistake twice. We measured how often that happens: **58% of the
> time**, an agent falls back into a trap it has already been burned by."

#### Show — the race, left pane only

Press Play. Let the left app die. Don't explain while it's dying.

> "It edited the model and skipped the migration. Nothing remembered that it did
> this last week."

#### Then explain the existing answer, and why it isn't enough

> "There's a tool that does this already. It writes the mistake down and pastes
> it into the AI's instructions. That's genuinely better than nothing.
>
> But a note in the instructions is a **suggestion**. Their own plugin has the
> hook to block a write, and their own code comment says it *never blocks, even
> when told to*. They built the door and chose not to close it."

#### The one-liner

> "We turn the mistake into a check that **stops the write**. Their tool tells
> the agent about the crash. Ours takes the keys."

#### Then the hard question you must answer before they ask it

> "The obvious worry is: if it blocks things, won't it block the wrong things?
> That's exactly why everyone else stays advisory. Our answer is that a rule has
> to pass a test before it's allowed to block anything — and that's what we're
> building next."

#### Have ready
- The problem statement and the 58% figure
- Why prose isn't enough, with the competitor's own comment as evidence
- The seven categories of thing you'll check
- **An honest "not built yet" list.** At review 1 that's most of it, and saying
  so buys you credibility for reviews 2 and 3.

#### They will ask
- *"Isn't this just a linter?"* → "A linter is rules somebody wrote in advance.
  Ours come from **this repository's own failures**, they carry the case that
  created them, and they expire when the evidence turns against them."
- *"What if I disagree with a rule?"* → `injunct off 4`. Mutes it, keeps the
  case. A tool with no escape hatch gets uninstalled.

---

### REVIEW 2 — *"Does the core actually work, and can I trust it?"*

**Time: hours five to ten. Goal: they believe the mechanism, not just the idea.**

#### Open by doing it live, in a fresh folder

Nothing seeded. This is the strongest thing you can do.

```bash
injunct rule "models/*.py needs migrations/"
#   Changing models/*.py means changing migrations/ too.
#   co_change( models/*.py -> migrations/** )
#   BINDING
```

> "One sentence of English became a typed check."

Now edit a model, skip the migration:

```bash
injunct gate .
#   HALT   BINDING HOLDING No 1
#   models/patient.py changed, nothing under migrations/** did
#   DO THIS NEXT:  create migrations/002_injunct.sql
```

> "And that filename isn't a template. We read **your** repo's migration naming
> and produced the next one in your sequence."

#### Then the trust mechanism — this is the heart of review 2

Open the cabinet. Show a binding rule's receipt:

> `1/1 fired on its own case · 0/5 false on past successes · cited 6 times`

> "Before this rule was allowed to block anything, we replayed it against
> history. It had to catch its own failure, and stay quiet across five past runs
> that already worked."

Now show the advisory one that **failed** the test:

> *"It did not fire on the case that produced it. A rule that misses its own
> case cannot be trusted to catch the next one, so it was demoted to advice."*

> "We don't trust our own lessons until they pass a test. That's the difference
> between a memory layer and a memory layer you'd actually leave switched on."

#### Then show it can be wrong and admit it

Open the overruled page.

> "If three runs override a rule and succeed anyway, we retire it and publish it
> on this page. A memory that can only grow can only get more wrong."

#### Then the day-one problem

```bash
injunct init
```

Run it on a real repo in front of them.

> "Every memory tool has the same flaw — on day one it knows nothing. This reads
> your git history and finds your habits before anything breaks. And it's
> willing to find nothing, because inventing a rule is worse than having none."

#### Have ready
- The eleven check shapes, and why a model never writes code
- The four-table schema, and why not a knowledge graph
- The 25 rules that ship on day one, and **the one that stops the agent
  disarming the gate** — tell the story of it happening to you twice
- The loop test: failure → rule → block → pass, all asserted

#### They will ask
- *"How do I know the rule is right?"* → the receipt. Show it again.
- *"Does this need an API key / a database / the internet?"* → No, no, no.
  Python and one file. The model is optional and never decides a block.
- *"What about false positives?"* → 0% across 540 runs, and it's a headline
  number on our own evidence page, not a footnote. We also found a real one in
  live testing and put it on the page.

---

### REVIEW 3 — *"Prove it, and is this a product?"*

**Time: the last stretch. Goal: they believe the numbers and the polish.**

#### Open with the full race — both rounds

Press Play and say nothing for ninety seconds. Round two is the moment: the left
agent repairs its mistake, then **makes the same mistake again** on the next
field.

> "That second failure is the 58%. That's the whole project, happening on
> screen."

#### Then the evidence

Open the corkboard. Lead with the win:

> "300 runs. Identical tasks, identical seeds. **53% to 70%** first-try pass.
> Repeat failures **halved**, 58% down to 31%."

Then the tape:

> "Same 150 tasks, run twice. **The gate won 34 and lost 9.**"

Then — **before they ask** — volunteer the bad news:

> "Three things you should know. **One**: if the agent ignores the card, we make
> things *worse* — below 21% compliance we cost runs and buy nothing. **Two**:
> nine tasks passed without us and failed with us; here's the list. **Three**:
> our agent is scripted, so this measures the enforcement layer, not a language
> model."

#### Then the honest gap, stated as a strength

> "Our claim is *warnings are optional, gates are not.* We've proved gates beat
> **no memory**. We have not proved gates beat **warnings** — that needs a real
> model running all three arms and we haven't completed that run.
>
> We tried four times. Each attempt found a real bug in our own harness: a
> subprocess with no timeout froze the run, our success check rewarded an agent
> that did nothing, a rate limit scored 90 empty runs as passes, and the free
> models we can reach only attempt the task one time in four. All four are fixed
> and the benchmark now **refuses to publish** if the model wasn't reachable.
>
> We'd rather show you a gap than a number we can't stand behind."

#### Then the product

```bash
pip install -e .
```

> "No dependencies. Works in any repo, with any AI, on a laptop with no
> internet."

Show the opencode plugin blocking a live write. Then walk the office — five
pages, static, every one renders with nothing running.

#### Have ready
- `bench/report.json`, `bench/compliance.json` — open them if asked
- The regressions list
- The README, this script, and the demo run sheet
- A clear statement of what's next: finish arm B on a capable model, fix the one
  live false positive we found, restyle nothing else — it's done

#### They will ask
- *"Why should I believe your benchmark?"* → "Run it. One command, 150 seconds,
  same numbers. And we publish the runs where we lost."
- *"What's the business case?"* → "Every repeat mistake is a wasted agent run
  and a wasted human review. We cut repeat failures by nearly half, and we
  install with one command and no services."
- *"What would you do with more time?"* → "Finish arm B. Replace bag-of-words
  retrieval with real embeddings — theirs is genuinely better than ours and we
  can prove ours is weak. And consolidate rules: three specific rules should
  become one general one, carrying all three cases as evidence."

---

## Part 7 — Every page in one line

| page | what it's for |
|---|---|
| **the race** `:8900` | the 90-second proof. Two agents, one clock, one app dies twice |
| **the desk** `desk.html` | the clerk working, live or recorded. The way in to everything |
| **the docket** `cabinet.html` | every rule in drawers by authority; click a folder for its whole case |
| **the evidence** `chart.html` | does it work, what does it cost, what we couldn't prove |
| **the tape** `tape.html` | 300 runs in 3 seconds, and the 34–9 record |
| **overruled** `overruled.html` | how a rule dies, and where every rule stands today |

---

## Part 8 — Never do these

- **Never claim you beat prose-based tools.** Say you beat **no memory**. The
  prose-vs-gate comparison isn't finished and someone will ask.
- **Never hide the harmful zone.** Say it first. It's the most credible thing on
  the page.
- **Never run the live benchmark on stage.** 11 to 50 minutes.
- **Never open the race from the board.** It lives on **8900** under
  `injunct demo`. The copy at 8850 has no apps behind it and the panes go
  blank.
- **Never call it a linter** without immediately explaining it's a linter
  **nobody wrote**.
