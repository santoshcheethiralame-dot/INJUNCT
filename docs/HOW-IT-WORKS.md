# How Injunct works

The engine underneath every Injunct command: how a lesson becomes a rule that
blocks, what a rule can check, and the rules that ship built in. The README
has the short version; this is the long one.


## How a lesson becomes law

**Case** → a failed run: a human rejection, a failing check, or a free signal —
a file rewritten inside one run, a revert, tests that flipped green to red.

**Holding** → the case compiled into one of twelve typed checks. A model's only
job is choosing a template and filling its blanks; it never writes a checker,
because a small free model fills a schema reliably and writes novel code badly.
Nothing fits → a prose warning, labelled as the weaker tier.

**Empanelment** → the part that makes *binding* mean something. A holding is
replayed against history before it gets any authority: it must fire on the case
that produced it, and stay silent across the stored working trees of past
**successful** runs. Fail either and it is demoted to advice. With no history to
test against it stays advisory, and a later passing run can promote it.

Every card carries the receipt, and there are three distinct verdicts in the
ledger right now:

| | |
|---|---|
| `1/1 fire · 0/5 false` | fired on its own case, silent across five past successes → **binding** |
| `tested: 0` | *no successful run to test against yet* → advisory, untested |
| `0/1 fire` | **it did not fire on its own case** → advisory, and rightly distrusted |

**Citation** → every firing is recorded with what happened next: complied/passed,
complied/failed, overridden/passed, overridden/failed.

**Overruling** → only a run that overrode a rule and succeeded *anyway* counts
against it. At **3** such runs, with more against than for, the rule is retired,
stops blocking anything, and is published on the overruled page with the
evidence that killed it. Being wrong in public is the point.

### The pairing is learned, not authored

The fallback compiler needs no model at all. It reads the repo's own successful
runs and finds the directories that were **never changed alone** — then, when a
failing run changes one without the other, it proposes exactly that rule. In the
seeded app it learns `models/*.py -> migrations/**` from one run that went right
and enforces it on the one that goes wrong.


## What it checks

Twelve templates, grouped into seven domains a person can read.

| domain | what it asks |
|---|---|
| **structure** | the thing you touched has a partner that did not move — `co_change`, `must_run`, `required_command`, `forbidden_edit` |
| **security** | secrets, destructive migrations, TLS turned off, **and the agent editing the gate itself** |
| **hygiene** | debuggers, `console.log`, stubs, swallowed exceptions, empty catch blocks |
| **tests** | you deleted a test, you skipped one instead of fixing it, a generated regression test fails |
| **context** | `blast_radius` — you changed a function's shape and 14 callers did not move |
| **cost** | `no_quadratic` — the lines this change *added* have a quadratic shape |
| **borrowed** | four gates from the optional `sleeper` companion: what it imports, doc drift, measured-vs-claimed cost, duplicate functions. Abstains when sleeper is not installed |

**25 rules ship in the pack**, 9 of them binding, installed only where a repo can
trip over them. The split is about false positives, not severity: a live AWS key
is never intentional, but tests genuinely do get deleted during a refactor.

One of those rules exists only because this tool blocks:

> **`self_disarm`** — binding on `.injunct/`, `.git/hooks/`,
> `.opencode/plugins/`, `opencode.json`.
> *"This turns the gate off. Change it yourself, not through the agent."*

An advisory tool has nothing worth disarming. This one does, and this repository
has been disarmed twice by the thing it was restraining — once when an agent
wrote into the seed corpus from outside its worktree, once when a plugin file
went missing and every benchmark arm silently became a bare agent still printing
numbers that looked like results.


### `watch` is the one that works everywhere

It reads **git, not the agent**, so opencode, Cursor, Claude Code and a person
typing by hand all get the same treatment, and there is no plugin to keep up to
date per harness:

```
  HALT  Changing models/*.py means changing migrations/ too.
        models/patient.py changed, nothing under migrations/** did
        do this next: create migrations/105_patient.sql
  CLEARED  No 4 satisfied. The change may land.
```

That `do this next` filename is not a template. It is read off the repository's
own migration naming.

### `init` is the one that matters

An empty ledger on day one is useless — it is the single biggest adoption
problem a memory layer has. `init` reads your commit
history and proposes rules before anything has gone wrong. On real repositories
it finds real things: in one research repository it worked out that `results/` never moves
without `docs/`, a working practice nobody had written down.

It is also willing to find nothing. On a repo whose history shows no habit
strong enough to be a rule it says so, because inventing one would be worse.

Three tests decide whether a pairing becomes a proposal:

| | |
|---|---|
| **support** | seen together often enough to be a habit, not a coincidence |
| **confidence** | P(B given A) — touching A really does mean touching B |
| **asymmetry** | P(A given B) is *low* — otherwise the two simply move together and the data cannot say which is the trigger |

The third one took measuring. Without it, an initial commit that touches every
directory makes everything "always" pair with everything, and two things that
genuinely move as one support *"A needs B"* exactly as much as *"B needs A"*.

Everything `init` proposes lands **advisory**. History is evidence about habits,
not proof that breaking one causes harm. `injunct confirm <n>` promotes, and
empanelment still gates the promotion. A rule *you* write binds immediately,
because you know your own repo — but it is still replayed against past work and
demoted if it would have blocked something that already succeeded.

`gate` exits 1 when a binding holding fires, so it drops into a pre-commit hook or CI
without ceremony. `off` mutes a rule without deleting the case that produced it:
a tool that blocks you once for a bad reason and offers no way out gets
uninstalled, and everything it ever learned goes with it.


## Stop the write before it lands

`watch` reports; it cannot refuse. Two integrations actually refuse.

### Claude Code

```bash
injunct claude                    # installs the hook into .claude/
git add .claude && git commit -m "install injunct"
```

That is the whole setup — **no service to start, no daemon, no key.** It
registers a `PreToolUse` hook that sees `Write`, `Edit`, `MultiEdit` and
`NotebookEdit` *before* the bytes reach the disk, and denies the call if a
binding holding fires. The card goes back to the model as the reason it was
refused:

```
BLOCKED BY INJUNCT - this exact change failed here before.

  Holding No 1, established 12 Sep 2026. Changing models/*.py means changing migrations/ too.
  Rule:   co_change( models/*.py -> migrations/** )
  Reason: models/patient.py changed, nothing under migrations/** did
  Tested: 1/1 fire, 0/5 false positives.
  DO THIS NEXT: create migrations/002_patient.sql
```

It also registers `UserPromptSubmit`, which puts the rules in front of the
model *before* it starts. That half matters more than it looks: being blocked
costs a whole turn and the model has to work out why; being told costs a
sentence and it complies the first time. Our own compliance sweep says the gate
is not the mechanism — the instruction is.

If `injunct serve` happens to be running it will use it, so the desk page
lights up as decisions happen; if not, it answers in-process. Either way the
verdict is identical, and **every failure path allows the write** — no ledger,
bad payload, unreachable service, or an outright crash all mean *allow*.

### opencode

```bash
injunct opencode          # installs into .opencode/plugins/
injunct serve             # the plugin decides nothing on its own
opencode
```

It throws in `tool.execute.before`, which aborts the tool call **before the
bytes reach the disk**, and the halt card goes back to the model as the tool's
error. It fails open on a timeout: a memory layer that can stall your agent by
being down is worse than no memory layer.

Both surfaces build the same card from the same `gate.evaluate`, and a test
asserts they stay byte-identical — an agent should not be able to tell which
harness refused it.

Three modes, and they are the three arms of the benchmark:

| mode | what the agent gets |
|---|---|
| `--mode off` | nothing. Arm A |
| `--mode advise` | every rule as prose in the prompt, nothing blocked. Arm B |
| `--mode enforce` | the rules named in the prompt **and** the write refused. Arm C |

Enforce tells the agent up front *and* stops it. Being stopped costs a whole
turn and the model has to work out why; being told costs a sentence and it
complies the first time.

End to end, in a repository with one rule and no failure yet:

```
$ injunct rule "models/*.py needs migrations/"
  Changing models/*.py means changing migrations/ too.
  co_change( models/*.py -> migrations/** )
  BINDING

$ injunct gate .
  HALT   BINDING HOLDING No 1   ESTABLISHED 11 SEP 2026
  Changing models/*.py means changing migrations/ too.
  models/patient.py changed, nothing under migrations/** did
  DO THIS NEXT:  create migrations/002_injunct.sql
```


## Look at what it learned

```bash
injunct board
```

Six pages, static, no build step, and every one renders with nothing running.

| | |
|---|---|
| **the front door** | every page below, in one list, and it says where the race is instead of linking a page that cannot work without a server |
| **the desk** | live while `injunct watch` runs; otherwise it plays a **recorded** session, labelled as a replay. Not an animation — a real capture of the watcher |
| **the docket** | every case on file. Click a folder in the drawer to open its file: the holding, the receipt, the facts, the citations, its overruling standing |
| **the evidence** | the result first, then the compliance curve including the zone where the tool makes agents *worse*, then the caveats |
| **the tape** | 300 runs replayed in three seconds, arm A against arm C |
| **overruled** | how a rule loses its authority, and where every binding rule currently stands |

`board` names any missing data file and the command that produces it, so a page
never quietly shows less than it should.


## Architecture

```
agent run ──► recorder (git + fs + harvesters) ──► cases
                                                    │
                                        compiler (typed schema)
                                                    │
                                     empanelment (replay against history)
                                                    │
                      binding ◄──────────── holdings ────────► persuasive
                         │                      ▲                  │
                    gate: blocks            citations        prose in prompt
                         │                      │                  │
                         └────► run outcome ────┴──────────────────┘
                                      │
                                 overruling
```

Four tables: `runs`, `cases`, `holdings`, `citations`. Artifacts on disk, keyed
by run id.

**Everything free and local.** SQLite via stdlib `sqlite3`. Retrieval is a
bag-of-words cosine over a few hundred rows — no pgvector, no ANN index, no
Postgres, no Docker, no embedding API. A model is optional, speaks the
OpenAI-compatible protocol, and is used **only** to fill a typed schema when
compiling a case. It is never on the path of a gate decision.

```bash
export INJUNCT_BASE_URL=...   # default http://localhost:11434/v1 (Ollama)
export INJUNCT_MODEL=...
export INJUNCT_API_KEY=...    # optional
```

With no model reachable the deterministic fallback takes over.

Standard library only. Run the tests with:

```bash
python -m pytest -q
```


## Why the name

An injunction is a court order that stops something before the harm is done.
That is the mechanism: a rule here does not warn after the commit, it refuses
the write before the bytes reach the disk.

An injunction is also never issued blind. No rule gets to refuse a change
until it has been replayed against this repository's own history and shown
that it catches its own case and stays silent on work that already succeeded.
And an injunction can be lifted: a binding rule that three runs overrode and
succeeded anyway is retired, stripped of its authority, and published on the
overruled page with the citations that lifted it.

A memory that can only grow can only get more wrong. The name carries both
directions.
