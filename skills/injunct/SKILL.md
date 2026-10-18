---
name: injunct
description: Check a repository's binding rules before editing a file, and measure how much of its AGENTS.md, CLAUDE.md or CONTRIBUTING.md is actually enforced. Use before changing files in a repository that has an .injunct/ ledger, when a commit or edit was refused by injunct, or when someone writes or edits agent instructions and wants to know which ones a tool can enforce.
license: MIT
compatibility: Requires Python 3.10+, git, and the injunct package (pip install -e . from the Injunct repository). Coverage uses an OpenAI-compatible model endpoint set by INJUNCT_BASE_URL, INJUNCT_MODEL and INJUNCT_API_KEY (for example Gemma 4 through the Gemini API); everything else needs no model.
---

# Injunct

Injunct turns rules into checks that run on the working tree and refuse a bad
change before it lands. A rule only binds after it has been replayed against
the repository's own git history and stayed silent on work that already
shipped.

## Before editing a file

1. Run `injunct why <file>` from the repository root.
2. Every line marked BINDING is a rule that will refuse the change if it is
   broken. Plan the edit so it satisfies each one (for example, add the
   migration in the same change as the model).
3. Advisory lines are evidence about this repository's habits, not orders.
   Follow them unless there is a reason not to, and say what the reason is.

## When a change is refused

The refusal names the rule, the case that established it, and the next step,
such as a file to create. Do the next step, then run `injunct gate .`; it
exits 0 when nothing binding fires. Do not edit `.injunct/`, `.git/hooks/` or
`.claude/settings.json` to get around a refusal: that is itself a binding
rule. If the rule is wrong, tell the user; `injunct off <id>` is their call.

## Measuring agent instructions

1. Run `injunct coverage .` (or `injunct coverage owner/name` for a public
   GitHub repository).
2. Report the percentage and the three groups:
   - ENFORCED: compiled to a check and proven on past commits.
   - checkable: compiles, but not yet proven; the reason is printed, and
     "past commit(s) already break it" lists the commits.
   - unchecked: no check can express it (judgement, process, runtime, vague).
3. If the output ends with a WARNING about failed model calls, say the number
   is a floor, not a measurement.
4. `injunct coverage --adopt` puts the rules on the ledger so enforced ones
   bind. Only run it if the user asks.
