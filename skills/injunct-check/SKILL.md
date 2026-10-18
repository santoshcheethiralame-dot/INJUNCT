---
name: injunct-check
description: Say which binding rules apply to the files about to change, and whether the current working tree passes them. Use when the user types /injunct-check, before a commit, or when they ask what would stop a change here.
license: MIT
compatibility: Requires Python 3.10+, git, and the injunct package. No model needed.
---

# Injunct check

1. List the files the user is working on (from the conversation, or
   `git status --short`). For each, run `python -m injunct why <file>` and
   collect the lines marked BINDING.
2. Run `python -m injunct gate .`.
3. Reply in this shape, and keep it short:
   - **Clear** or **Blocked**, from the gate's exit code (0 clear, 1 blocked).
   - If blocked: the rule, the reason, and the `DO THIS NEXT` step from the card.
   - The binding rules that apply to the files in play, one line each, with
     where each came from (an AGENTS.md line, the built-in pack, or history).
4. Offer to do the DO THIS NEXT step. Never edit `.injunct/`, `.git/hooks/`
   or `.claude/settings.json` to get past a rule.
