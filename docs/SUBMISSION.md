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

- `injunct coverage --demo`: offline, on Gemma 4's recorded answers. The demo
  repository scores 22%. Two rules are proven on 11 commits. A "never edit the
  generated client" rule is caught being broken by the repository's own
  regeneration commit, which is exactly the rule that would have blocked the
  team's generator.
- A real repository: openai/openai-agents-python. Of 129 instructions, 1 is
  enforced (never edit the translated docs, held on 92 commits), and most of
  the rest are process and judgement. That gap is the finding.

## Built with

Python standard library only (no dependencies), SQLite, Gemma 4 on the free
Gemini API tier, MIT licence. 400+ tests.

## Origin

Injunct grows out of VOID DIRE, our team's earlier project: the ledger, the
rule templates, the history replay and the Claude Code hook. At this Hack Day
we built:

- `injunct coverage`;
- the Gemma 4 provider work (system-prompt folding, stripping `<thought>`
  blocks, retrying 5xx errors);
- extraction that keeps hard-wrapped instructions whole;
- the offline demo;
- the Agent Skill;
- the pull-request Action.
