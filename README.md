# Injunct

**Your AGENTS.md is a suggestion. Injunct makes it a rule.**

Injunct reads the instructions your repository gives coding agents (AGENTS.md,
CLAUDE.md, CONTRIBUTING.md), works out which of them a machine can actually
check, proves each one against your own git history, and then stops an agent's
edit before it lands when it breaks one: in Claude Code, in opencode, in a git
hook, or on a pull request.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)
![Dependencies: none](https://img.shields.io/badge/dependencies-none-brightgreen.svg)
![Model: Gemma 4](https://img.shields.io/badge/model-Gemma%204%20(open%20weights)-4285F4.svg)
![Agent Skills](https://img.shields.io/badge/Agent%20Skills-open%20standard-8A2BE2.svg)
![Tests: 439 passing](https://img.shields.io/badge/tests-439%20passing-brightgreen.svg)

<p align="center">
  <img src="docs/img/coverage-report.png" alt="Injunct coverage report: 33% of AGENTS.md guarded, with each instruction colour-coded" width="720">
</p>

## Contents

- [Why](#why)
- [What it does](#what-it-does)
- [Quick start](#quick-start)
- [Use it on your repository](#use-it-on-your-repository)
- [Stop the edit, wherever the agent runs](#stop-the-edit-wherever-the-agent-runs)
- [How it works](#how-it-works)
- [Everything it does](#everything-it-does)
- [Results](#results)
- [Limitations](#limitations)
- [Configuration](#configuration)
- [Command reference](#command-reference)
- [Development](#development)
- [License](#license)

## Why

Every repository now tells its coding agents what to do, in prose. An agent
reads that prose, mostly follows it, and under pressure skips it, and nobody can
say which instructions are actually enforced and which are wishes. Teams find
out when the migration is missing again.

Prose is the wrong place for a rule a machine could check. Injunct moves those
rules out of the prompt and into a check that runs on the change itself, and is
honest about the ones it cannot move.

## What it does

| | |
|---|---|
| **Learn** | Rules come from five places: your agent documents, the habits in your git history, failures and rejections as they happen, 25 built-in rules for mistakes every agent makes, and a sentence you type. |
| **Prove** | No rule may block anything until it has been replayed against your repository's own commits and stayed silent on work that already shipped. A rule that keeps being overridden while the work succeeds anyway is retired in public. |
| **Enforce** | Proven rules refuse the edit **before it is written**: a Claude Code hook, an opencode plugin, a git pre-commit hook, a GitHub Action that comments on the pull request, `gate` in any CI, or `watch` beside any editor. Every refusal names the next step. |
| **Measure** | `coverage` shows how much of your AGENTS.md is **guarded**, **could be guarded**, or **needs a human**, as a visual report, and `--suggest` proposes rewrites that would be guarded today. |
| **Look back** | `hindsight` traces each past bug fix to the commit that caused it and reports which of those bugs the rules would have stopped, beside a baseline. |
| **Show its work** | A six-page board of every rule and the evidence behind it, a split-screen live demo, and a reproducible benchmark. |

Three properties hold throughout:

- **A model never decides what blocks.** It only fills in one of twelve typed
  checks. Whether a check binds is decided by replaying it against your
  repository's own commits.
- **Nothing a model writes is executed.** Rules are patterns over a diff, never
  generated code.
- **It runs on open weights at no cost.** Gemma 4 through the free Gemini API by
  default, or any OpenAI-compatible endpoint including a local Ollama. The engine
  itself is the Python standard library and one SQLite file.

## Quick start

Requires Python 3.12+ and git.

```bash
pip install git+https://github.com/santoshcheethiralame-dot/INJUNCT
```

See it work in under a minute, offline, with no API key. `--demo` builds a small
sample repository whose history contains three planted mistakes, and replays the
model's recorded answers for it:

```bash
python -m injunct coverage --demo
python -m injunct hindsight --demo
```

```
  33% of the instructions in AGENTS.md are guarded.
  3 guarded   2 could be guarded   4 need a human   (9 instructions)

  3 commit(s) not counted as good work, because a later commit fixed them:
    744e19f: quick debug for the double-booking bug
      fixed by a1650dd Fix stray debug print in booking
  ...
  caught      3/3 (100%) of the commits that introduced a fixed problem,
              counted only where the fix did what the rule asks for
```

## Use it on your repository

Set up a model once (see [Configuration](#configuration)), then run these from
your repository's root:

```bash
python -m injunct coverage . --html coverage.html    # the visual report
python -m injunct coverage . --suggest               # rewrites that would be guarded
python -m injunct coverage . --adopt                 # turn the guarded rules on
python -m injunct hindsight .                        # what they would have caught
```

`coverage` also accepts a public repository by name, for example
`python -m injunct coverage astral-sh/uv`. Answers are cached, so a second run
takes seconds and the number does not drift.

Rules can come from more than your documents:

```bash
python -m injunct init                                  # mine habits from git history
python -m injunct rule "models/*.py needs migrations/"  # state one directly
python -m injunct why models/patient.py                 # what applies to this file
python -m injunct off 4                                 # mute a rule that is wrong
```

## Stop the edit, wherever the agent runs

| Where | Set up | What happens |
|---|---|---|
| **Claude Code** | `python -m injunct claude`, then commit `.claude/` | The edit is denied before it reaches disk. The model receives the full card; you see one line. |
| **opencode** | `python -m injunct opencode` and `python -m injunct serve` | The tool call throws before the write. |
| **git** | `python -m injunct hook` | The pre-commit hook refuses the commit. |
| **GitHub** | copy [`examples/workflows/injunct.yml`](examples/workflows/injunct.yml) | The check fails and the card is posted on the pull request. |
| **Any CI** | `python -m injunct gate .` | Exits 1 when a guarded rule fires. |

What the agent receives when Claude Code refuses an edit:

```
BLOCKED BY INJUNCT - this breaks a rule this repository wrote down, and its history proved it.

  Holding No 1, established 18 Oct 2026. Changing a model requires adding a migration in the same commit.
  Rule:   co_change( models/* -> migrations/* )
  Reason: models/patient.py changed, nothing under migrations/* did
  Tested: held on 14 past commits, 0 false positives.
  From:   AGENTS.md:7
  DO THIS NEXT: create migrations/009_patient.sql
```

And what you see:

> Injunct blocked a write to patient.py: Changing a model requires adding a
> migration in the same commit. (from AGENTS.md:7) Next: create
> migrations/009_patient.sql.

Injunct gates its own pull requests. [PR #1](https://github.com/santoshcheethiralame-dot/INJUNCT/pull/1)
leaves a stray `breakpoint()` in the code; the check fails and the Action posts
the card on the pull request.

**Agent Skills.** [`skills/`](skills/) holds four skills to the Agent Skills open
standard. `injunct` teaches an agent to check the rules before editing, and three
work as one-word commands in Claude Code: `/injunct-check`, `/injunct-coverage`
(opens the visual report) and `/injunct-hindsight`. Install them by copying the
folders into `~/.claude/skills/`.

## How it works

Injunct has one idea: **a rule has to earn the right to block.** Everything
else is where rules come from and where they act.

```mermaid
flowchart LR
    subgraph SRC["Where rules come from"]
        direction TB
        s1["Agent documents<br/>AGENTS.md · CLAUDE.md"]
        s2["Habits in<br/>git history"]
        s3["Failures and<br/>rejections"]
        s4["25 built-in<br/>rules"]
        s5["A sentence<br/>you type"]
    end
    subgraph CORE["How a rule earns authority"]
        direction TB
        c1["Compile into one of<br/>12 typed checks"]
        c2["Prove against<br/>past commits"]
        c3[("Ledger<br/>one SQLite file")]
        c1 --> c2 --> c3
    end
    subgraph GATE["Where it acts"]
        direction TB
        g1["Claude Code hook"]
        g2["opencode plugin"]
        g3["git pre-commit"]
        g4["GitHub Action"]
        g5["gate · watch"]
    end
    SRC --> c1
    c3 --> GATE
```

**A model only fills in a form.** When a rule starts as prose (a sentence in
AGENTS.md, a reviewer's rejection), a model chooses one of twelve typed checks
and fills its blanks: a file that must change with another, a file that must
never be edited, a pattern no added line may contain, and so on. It never
writes a checker and never decides whether the rule blocks. With no model
available, a deterministic fallback reads the failure and the history itself.

**Every rule then goes through the same life:**

```mermaid
flowchart TB
    A["Case<br/>a failure, a rejection,<br/>or a line in AGENTS.md"] --> B["Compile<br/>into a typed check"]
    B --> C{"Prove<br/>fires on its own case,<br/>silent on past successes?"}
    C -- yes --> D["Binding<br/>blocks the edit"]
    C -- no --> E["Advisory<br/>told to the agent"]
    E -. "new evidence" .-> C
    D --> F["Cited<br/>every time it fires"]
    F -- "overridden 3 times,<br/>work still passed" --> G["Overruled<br/>retired in public"]
```

- **Proving** replays the rule against the repository's past commits. It must
  catch the case that created it and stay silent on every commit that worked. A
  rule no past commit could test does not bind either, because a check that
  abstains and a check that approves look identical from outside. A commit that
  a later commit had to fix is not counted as an example of good work.
- **Binding** rules block; **advisory** rules are put in front of the agent as
  guidance and are retried as new evidence arrives.
- **Citations** record what happened each time a rule fired: complied or
  overridden, passed or failed. A rule overridden three times by work that
  succeeded anyway is retired and published, with the evidence, on the board.
- **The gate** is deterministic and fails open: a crashed or slow check allows
  the edit rather than blocking it by accident. The one exception is the agent
  trying to turn the gate off, which is itself a binding rule.

The full design, every check, the built-in rules and the data model are in
[docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md).

## Everything it does

**Learning rules**

- `coverage --adopt` turns the guarded instructions in your agent documents into rules.
- `init` reads your commit history for habits ("`models/` never changes without
  `migrations/`") using support, confidence and an asymmetry test, and proposes
  them as advisory; `confirm <n>` promotes one.
- `rule "models/*.py needs migrations/"` adds a rule in one sentence.
- `reject "forgot the migration"` files a rejection against the current change.
  Injunct also learns from free signals: a file rewritten within one run, a
  revert, tests that flipped from green to red.
- 25 built-in rules for mistakes agents make everywhere, 9 of them binding:
  committed AWS keys, private keys and tokens, TLS verification turned off,
  leftover `pdb` or `debugger` statements, destructive migrations, a manifest
  changed without its lockfile, and an agent editing the gate itself.
- A rule learned independently in two repositories becomes global and applies
  to the next one.

**Proving and maintaining rules**

- Every rule is replayed against history before it can block (see above), and
  carries its receipt: how many past commits it was tested on and how many it
  would have wrongly blocked.
- `sweep` re-decides every binding rule from its citations; `off <n>` and
  `on <n>` mute a rule without deleting the history behind it.

**Enforcing**

- **Claude Code** (`injunct claude`): denies a write, edit or shell command
  before it lands, briefs the model on the rules at the start of a turn, and
  re-checks after shell commands and before the turn ends. You see one line;
  the model gets the full card.
- **opencode** (`injunct opencode` with `injunct serve`), **git**
  (`injunct hook`), **GitHub** ([`action.yml`](action.yml)) and **any CI**
  (`injunct gate`, exit code 1).
- `watch` reads git rather than the agent, so Cursor, any other editor or a
  person typing by hand get the same decisions, live.
- Every refusal names the next step, read from the repository itself, for
  example `create migrations/009_patient.sql`.
- Three modes, set per hook: `off`, `advise` (rules as prose, nothing blocked)
  and `enforce` (rules in the prompt and the write refused).

**Measuring and inspecting**

- `coverage` (text, `--html`, `--md`, `--json`, `--badge`, `--suggest`) and
  `hindsight`, described above.
- `why <file>` lists the rules that apply to a file and where each came from;
  `status` shows what was stopped this week; `docket` lists every case and the
  rule it established; `dump` exports the ledger as JSON.
- `board` serves six static pages: a front page, the live desk, the docket, the evidence, a
  replay of 300 benchmark runs, and the overruled rules.

**Showing it**

- `demo` runs two agents on the same task side by side, one with Injunct and
  one without; the one without breaks its app on screen.
- `bench` reproduces the published benchmark (one seed takes about 25
  seconds); `bench --compliance` sweeps how much depends on the agent obeying
  the card; `live` drives the same comparison with a real opencode agent;
  `replay` records a real session for the board.
- `coverage --demo` and `hindsight --demo` run offline on a sample repository
  with three planted mistakes.
- Four [Agent Skills](skills/), including the slash commands `/injunct-check`,
  `/injunct-coverage` and `/injunct-hindsight`.

## Results

**Coverage on real repositories** (Gemma 4 26B, 18 Oct 2026):

| Repository | Instructions | Guarded | Could be guarded | Needs a human |
|---|---|---|---|---|
| astral-sh/uv | 63 | **2**: no `#[allow(clippy::…)]` in Rust; no `pull_request_target` in workflows. Both held on 90 commits | 3, two of them already broken by recent commits | 58 (22 process, 15 judgement, 12 runtime, 9 vague) |
| sample repository (`--demo`) | 9 | **3** | 2 | 4 |

On astral-sh/uv, `--suggest` proposes 6 rewrites that would be guarded today,
taking it from **3% to 13%**, each proven on 69 commits.

**Hindsight.** On the sample repository the rules catch all 3 planted bugs,
each by a rule that blocks today, with the fix doing exactly what the rule
asks. On uv's last 300 commits, 21 fixes trace to 7 causes and none is caught
that way, which is the honest answer and the one the tool prints.

**Enforcement, measured.** A 300-run ablation (30 tasks, 3 repositories, 5
seeds) compared the same agent with and without binding rules:

| | Without Injunct | With Injunct |
|---|---|---|
| First-try pass rate | 53.3% | **70.0%** |
| Fell for the same mistake twice | 58.1% | **31.0%** |
| False positives on control tasks | 0.0% | 0.0% |

The extended 410-run suite gives 56.1% → **76.1%** and 57.1% → **19.6%**, and a
6.0% false-positive rate from one known rule. Method, every table, the
compliance sweep and the regressions are in
[docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## Limitations

- **Most agent instructions cannot be enforced.** Process and judgement are
  most of what teams write, and a low coverage number is the finding.
- **Suggested rewrites are proven against history, not intent.** Read each one
  before adopting it.
- **Hindsight is a method, not yet a result** on real repositories.
- **The benchmark agent is synthetic,** and the prose-only arm was not run
  against a real model.
- **When a model call fails,** the instruction is scored as needing a human and
  the output says the number is a floor.

The full list, with how each was found, is in
[docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Configuration

Only `coverage` and `--suggest` use a model; enforcement never does. Set it
with environment variables:

```bash
export INJUNCT_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
export INJUNCT_MODEL=gemma-4-26b-a4b-it
export INJUNCT_API_KEY=...        # a free key from Google AI Studio
```

or with `~/.injunct/provider.json`, which agent apps also read when they do not
inherit your shell's environment. It names the key file instead of holding the
key:

```json
{
  "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
  "model": "gemma-4-26b-a4b-it",
  "api_key_file": "~/.injunct/gemini.key"
}
```

Any OpenAI-compatible endpoint works the same way. With nothing configured,
Injunct uses a local Ollama at `http://localhost:11434/v1`.

## Command reference

| Command | What it does |
|---|---|
| `coverage [repo]` | how much of the agent documents is guarded. `--html`, `--md`, `--json`, `--badge`, `--suggest`, `--adopt`, `--trust-history`, `--demo` |
| `hindsight [repo]` | which past bugs the rules would have caught, beside a baseline. `--window`, `--no-docs`, `--demo` |
| `init` | learn habits from git history and install the built-in rules |
| `rule "..."` | add a rule in one sentence |
| `confirm <n>` | promote a learned rule so it blocks |
| `why <file>` | the rules that apply to a file, and where each came from |
| `gate [path]` | exit 1 if a guarded rule fires on the working tree. `--plain` prints the text card |
| `off <n>` / `on <n>` | mute or unmute a rule without deleting its history |
| `status` | what was stopped this week |
| `claude` / `opencode` / `hook` | install the Claude Code hook, the opencode plugin, or the git hook |
| `watch` | show every decision live, with any agent or editor |
| `serve` | local HTTP interface for agent runtimes |
| `docket`, `sweep`, `reject`, `dump` | inspect and maintain the rule ledger |
| `board`, `demo`, `bench`, `live`, `replay` | the visual board, the split-screen demo, and the benchmark |

Every command is `python -m injunct <command>`. If your Python scripts folder is
on `PATH`, `injunct <command>` works too.

## Development

```bash
git clone https://github.com/santoshcheethiralame-dot/INJUNCT
cd INJUNCT
pip install -e .
python -m pytest -q
```

The suite needs no network and no API key. Design notes for contributors are in
[CLAUDE.md](CLAUDE.md), and the five-minute presentation run sheet is
[docs/HACKDAY-DEMO.md](docs/HACKDAY-DEMO.md).

## License

[MIT](LICENSE).
