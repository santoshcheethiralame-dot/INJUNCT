# Limitations

What is not proven, stated here rather than discovered by someone else.

## The engine and its benchmark

**1. The agent is synthetic.** It performs each companion action with
probability `p_recall` from a seeded generator. This measures the enforcement
layer, not a language model.

**2. Arm B was not run.** Its entire mechanism is whether a model obeys a
paragraph in its prompt, which a scripted agent cannot answer. Four attempts,
four different blockers — and each one was a real bug found by trying:

- a subprocess with no deadline wedged the run (the agent started the seeded web
  server, which never exits)
- the oracle asked whether the repo was *consistent*, and a repo nobody touched
  is consistent — so a model that read files and stopped scored **100% in all
  three arms**
- a rate limit produced 90 runs that never reached the model, all scored as
  passes
- every free model reachable attempts only 1 task in 4, and `gpt-4o-mini`
  attempts **0 of 19** typegen and registry tasks

All four are fixed or guarded — the bench now refuses to write a report when
more than 10% of runs never reached the model, and "did nothing" no longer
counts as a pass. *"Gates beat warnings"* remains a thesis. *"Gates beat no
memory"* is the finding, and it stands on its own.

**3. Nine regressions.** Nine of 150 tasks passed without memory and failed with
it, six on `plugin_without_declaration`. A result showing the tool never hurts
would be the less trustworthy one.

**4. A live false positive — found, root-caused, fixed.** Testing against a real
model surfaced one the synthetic benchmark never could:
`must_run( client/*.py : tools/gen.py )` fired on a control task that only
edited a README.

We first wrote this off as bad luck — no past successful run had happened to
edit `docs/` alone, so the false-positive test passed vacuously. That was
wrong, and the truth was worse. Stored run artifacts recorded only `touched`
and `added`, never the commands a run issued. `must_run` asks whether a
generator ran, so on every single replay it **abstained** — and an abstention
is indistinguishable from silence. Its false-positive count was empty *by
construction*. The rule was not under-tested; it was **unfalsifiable**, and it
bound on a proof that could never have existed.

Three changes, and a rule like it cannot bind that way again:

- artifacts persist `commands` and `removed`, so a past run can actually
  contradict a command-aware rule;
- empanelment counts `judged` separately from `tested` and **refuses to bind
  anything no past run was able to test** — the receipt now says
  *"none of 5 past runs could test this rule"* instead of a confident `0/5`;
- the rule names the one file whose own header declared it generated, rather
  than the whole directory around it.

The reproduction is `tests/test_empanel.py`. This is the general lesson and it
cost us a published caveat to learn: **a check that abstains and a check that
approves look identical from the outside, and only one of them is evidence.**

**5. `blast_radius` over-blocks a backward-compatible change.** Adding a
parameter *with a default* does not require callers to move, but the `def` line
changed, so the rule fires anyway. Its own benchmark fixture surfaced this.
Fixing it means comparing parameter defaults inside a check the published
numbers were measured on, so it is written down here and in the check's
docstring rather than slipped in quietly.

**6. The control-task false-positive rate is 0.0% on 300 runs and 6.0% on the
410-run extended set** — one pre-existing co-change rule, not a new check. The
reasoning is in [This run also costs us our 0.0%](BENCHMARKS.md#this-run-also-costs-us-our-00).

An earlier run was scored under a bytecode-cache bug and is kept as
`bench/report.prebugfix.json`. A `.pyc` records source mtime to one-second
granularity, and these runs write a module and import it inside the same second,
so Python could serve the previous version and score a failing run as a pass.
Every subprocess now sets `PYTHONDONTWRITEBYTECODE`.

## Coverage, hindsight and suggestions

**Most agent instructions cannot be enforced, and that is the finding.** Process
and judgement ("write a regression test", "keep the change small") are most of
what teams write, and no deterministic check will ever enforce them. A low
coverage number says how much of a document is a suggestion; it is not a defect
in the tool.

**A model sorts the sentences, so a number can be a floor.** When a model call
fails even after a retry, that instruction is scored unchecked and the output
says so with a WARNING. On openai/openai-agents-python, 39 of 162 sentences got
no answer from the free tier on the day it was run, so that repository is not
in the README's results table.

**Suggested rewrites are proven against history, not against intent.** A
rewrite is shown only if no past commit contradicts it. That cannot show the
rewrite still means what the team meant: on astral-sh/uv, "put integration
tests in the relevant module" became "every changed test file must contain a
doc comment". The report asks a person to read each one before adopting it.

**Hindsight is a method, not yet a result on real repositories.** Tracing a
fix to its cause uses SZZ (Śliwerski, Zimmermann and Zeller, 2005), which is
noisy: a fix that only adds lines points at nothing, and a refactor in between
points at the wrong commit. A catch counts only when the fix did what the rule
asks for. On uv's last 300 commits, 21 fixes traced to 7 causes, and none was
caught that way; before that test existed, the rules appeared to catch 4 of 7,
and every one was a coincidence. The planted demo catches 3 of 3.

**Command-aware rules cannot be proven from git alone.** Git does not record
which commands a person or agent ran, so a rule like "after changing
`Cargo.lock`, run `cargo update --precise`" stays checkable until Injunct has
watched agent sessions in the repository.
