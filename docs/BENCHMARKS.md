# Benchmarks

The 300- and 410-run ablations behind the README's headline numbers, and
everything they cost to measure honestly. Every figure here can be checked
against the committed report that produced it under `bench/`.

## Headline: 300 runs

Two arms, five seeds, thirty tasks across three repos, **300 runs**. Identical
tasks, identical agent, identical seeds — the only thing that differs is whether
injunct is enforced.

| | A — no memory | C — binding gates |
|---|---|---|
| first-try pass | 53.3% | **70.0%** |
| pass on trapped tasks | 39.1% | **60.9%** |
| **fell for the same trap twice** | **58.1%** | **31.0%** |
| false positives on control tasks | 0.0% | 0.0% |
| runs stopped, that passed anyway | — | **54 of 58** |
| regressions vs arm A | — | **9** |

**That table was measured on the 30-task suite, and the suite now has 41.** So
running the benchmark today reproduces the 410-run numbers below, not these.
Both reports are committed — `bench/report.json` is the run above,
`bench/report.coverage.json` the current one — and the figures here are left as
they were measured rather than quietly restated against a corpus they never saw.

```bash
python -m injunct bench --arms A,C --seeds 1,2,3,4,5 --out bench/report.coverage.json
```

### Every trap class moved

| trap class | A | C |
|---|---|---|
| changing a model, no migration | 57% | **85%** |
| changing the API, not the client types | 35% | **65%** |
| editing a generated file by hand | 33% | **53%** |
| adding a plugin, not declaring it | 25% | **38%** |

The third row took a new template to move at all. A co-change rule asks whether
the right directory moved, and an agent that hand-edits `client/generated.py`
instead of running the generator *does* touch the right directory, with the wrong
content. `forbidden_edit` is the obvious fix and the wrong one, because a
legitimate regeneration touches that same path. What separates them is **whether
the generator ran** — so the recorder learned to see commands, and `must_run`
asks that question, with the rule read out of the file's own words
(`GENERATED FILE - run tools/gen.py, do not edit by hand`).

### Every shipped check now has a number

Two checks used to ship real and ship unmeasured — `blast_radius` and
`no_quadratic` had no trap class, so the benchmark could say nothing about them
either way. They have one now: a fourth seeded repo whose oracle fails for the
reason the rule predicts, counted rather than timed.

```bash
python -m injunct bench --arms A,C --seeds 1,2,3,4,5 --out bench/report.coverage.json
```

**410 runs, 41 tasks, four repos** (`bench/report.coverage.json`):

| | A — no memory | C — binding gates |
|---|---|---|
| first-try pass | 56.1% | **76.1%** |
| pass on trapped tasks | 41.9% | **68.4%** |
| fell for the same trap twice | 57.1% | **19.6%** |

| trap class | A | C |
|---|---|---|
| changing a model, no migration | 48% | **68%** |
| changing the API, not the client types | 50% | **75%** |
| editing a generated file by hand | 40% | **67%** |
| adding a plugin, not declaring it | 20% | **62%** |
| **changing a signature, not its callers** | 65% | **75%** |
| **a lookup per row instead of one query** | 45% | **70%** |

The two new rows are the previously unmeasured checks. Neither is a rewrite of
an existing rule: `blast_radius` asks *did you finish the job* rather than *did
the other folder move*, and `no_quadratic` only ever looks at lines this change
**added**.

Both were also mute until now — they could say what was wrong and not what to
do. Our own compliance sweep says the instruction is the mechanism, so both now
name the next action, read out of the verdict itself: the caller list comes
from the call graph, the location from the finding. Neither is invented.

### This run also costs us our 0.0%

**False positives on control tasks: 0.0% in the 300-run result, 6.0% here.**
That is worth stating plainly rather than publishing only the flattering one.

All three are the same rule on the same three control tasks —
`co_change( docs/*.md -> registry.py )`, firing on a task that edits
`docs/plugins.md` and nothing else. **It is not one of the new checks**, and it
cannot be: those controls touch no `.py` file at all, so a signature rule and a
cost rule have nothing to look at.

It is a flaw we had already written down. In this repository's own compiler:

> *So this stays first-match on co-occurrence, and `docs/ -> registry.py` stays
> a known false positive. The evidence that would refute it is evidence these
> runs do not produce.*

Every successful registry run touches `docs/` and `registry.py` together, so
nothing in history ever contradicts the rule — it is a correct inference from
the evidence available and still wrong about the world. What changed is only
**when** it gets established: tasks are shuffled per seed, so adding eleven
tasks moved the rule ahead of the controls it fires on. The 0.0% was ordering
luck, not the absence of the flaw.

The honest reading is that **0.0% was always the weaker claim**, and a bigger
corpus found the rule the smaller one stepped over. `mine.py` settles direction
with an asymmetry test that would reject this rule; the compiler cannot use it,
because inside one run's short history nothing ever moves alone.

### It starts level and pulls away

Pass rate over the first ten tasks of a seed, against the last ten:

| | first ten | last ten |
|---|---|---|
| A | 46% | 48% |
| **C** | 50% | **86%** |

Arm A has nothing to accumulate. Arm C greens toward the end of every seed
because the precedents that stop it were established earlier in that same run.

### And it depends entirely on the agent obeying

That headline was measured with an agent that always does what the halt card
asks. Sweeping that assumption is the more useful result — 5 points, 90 runs
each, 540 runs total:

```bash
python -m injunct bench --compliance
```

| the agent obeys the card... | pass rate | repeat-failure | recovery |
|---|---|---|---|
| never | 53.3% | 64.6% | 43.2% |
| a quarter of the time | 60.0% | 52.1% | 59.5% |
| half | 67.8% | 37.5% | 78.4% |
| three quarters | 68.9% | 35.4% | 81.1% |
| always | 74.4% | 25.0% | 89.7% |

Arm A, for comparison, sits at **58.9%** pass and **50.0%** repeat-failure.

> **Below roughly 21% compliance this makes an agent worse than no memory at
> all.** Blocking something that then ignores you costs a run and buys nothing.

So the gate is not the mechanism — the **instruction** is. That is why every
halt card names the exact next action rather than saying "do the missing work",
and why enforce mode now also puts the rules in the prompt before the agent
starts.
