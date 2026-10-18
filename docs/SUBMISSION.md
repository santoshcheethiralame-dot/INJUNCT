# Injunct: submission draft

Hacktoberfest Hack Day Bengaluru x BMSCE IEEE CS · Theme 1, AI to build developer tools ·
categories: Best Open-Source AI Project, Best Use of Gemma 4

## One line

Your AGENTS.md is a suggestion. Injunct tells you which of its sentences would
actually stop a bad change, proves it against your own git history, and turns
the ones that hold into checks that refuse the write before it lands.

## The problem

Every repository now has instructions for coding agents: AGENTS.md, CLAUDE.md,
CONTRIBUTING.md. They are prose. An agent reads them, mostly follows them, and
skips them under pressure, and nobody can say which rules are enforced and
which are wishes. Teams find out when the migration is missing again.

## What it does

`injunct coverage <repo>` reads the agent documents and puts every instruction
in one of three places:

- **ENFORCED**: compiled into a deterministic check and replayed against the
  repository's past commits; it held on every one that could test it.
- **checkable**: it compiles, but it has not earned the right to block. Often
  this is because the repository's own history already breaks it, and Injunct
  lists those commits.
- **unchecked**: no check can express it, with the reason (judgement, process,
  runtime, vague).

It prints a percentage and a README badge. `--adopt` puts the proven rules on
the ledger, and from then on they block: inside Claude Code and opencode before
a write lands, in a git pre-commit hook, and in CI through `action.yml`, which
comments the report on the pull request.

## How Gemma 4 is used

Gemma 4 (26B A4B, through the Gemini API's OpenAI-compatible endpoint) reads
each candidate sentence and decides whether it is an instruction. If it is,
Gemma fills the blanks of one of six typed templates: co_change,
forbidden_edit, must_not_appear, must_not_remove, must_appear and must_run.

Three choices keep the model honest:

1. **It never writes a checker or decides what binds.** Replaying the rule
   against git history decides that, deterministically.
2. **It cannot invent instructions.** Candidates come from the document
   deterministically, so every one is a real line.
3. **Nothing it writes is executed.** "After X run Y" becomes a check that
   reads the commands a session ran; it never runs them.

Any OpenAI-compatible endpoint works, including a local Ollama, so the whole
tool can run on open weights with no network.

## Show it

The run sheet is `docs/HACKDAY-DEMO.md`: five minutes, offline.

- **Coverage on the planted clinic repo:** 33% of its AGENTS.md is enforced.
  Three rules are proven on 13 commits. A "never edit the generated client"
  rule is caught being broken by the repo's own regeneration commit, which is
  exactly the rule that would have blocked the team's generator.
- **Commits that needed a fix are left out.** Trusting every commit, the
  planted bugs make every rule look wrong (0%). Leaving out the three commits
  somebody came back and fixed, three rules bind (33%).
- **Hindsight:** it traces each fix to the commit that caused the problem
  (SZZ) and replays the rules. A catch only counts when the fix did what the
  rule asks for. All 3 planted bugs are caught that way, by binding rules. On
  uv's real history the honest answer is 0 of 7, and the tool prints it.
- **The block:** edit a model without a migration and `injunct gate` halts
  with "from AGENTS.md:7, held on 13 past commits" and "DO THIS NEXT: create
  migrations/009_patient.sql". The same card stops the write inside Claude
  Code and opencode, and in CI.
- **A real repository, astral-sh/uv:** 63 instructions, 2 enforced (no
  `#[allow(clippy::…)]`, no `pull_request_target`; both held on 90 commits),
  3 checkable, 58 unchecked. Most agent instructions are process and
  judgement, and that gap is the finding.

## Built with

Python standard library only (no dependencies), SQLite, Gemma 4 on the free
Gemini API tier, MIT licence. 400+ tests.

## Origin

Injunct grows out of VOID DIRE, our team's earlier project: the ledger, the
rule templates, the history replay and the Claude Code hook. At this Hack Day
we built:

- `injunct coverage`;
- `injunct hindsight`, and leaving later-fixed commits out of the proof;
- the Gemma 4 provider work (system-prompt folding, stripping `<thought>`
  blocks, retrying 5xx errors);
- extraction that keeps hard-wrapped instructions whole;
- the offline demo;
- the Agent Skill;
- the pull-request Action.
