---
name: injunct-hindsight
description: Show which past bugs in this repository the rules would have caught, by tracing each fix commit back to the commit that caused the problem. Use when the user types /injunct-hindsight or asks what injunct would have prevented.
license: MIT
compatibility: Requires Python 3.10+, git, and the injunct package. No model needed when run with --no-docs.
---

# Injunct hindsight

1. From the repository root, run `python -m injunct hindsight . --no-docs`.
   (Drop `--no-docs` only if the user wants AGENTS.md compiled first; that
   needs the model.)
2. Report the four numbers exactly as printed: caught, binding, unrelated,
   baseline. A catch only counts when the fix did what the rule asks for, so
   do not round "unrelated" firings up into catches.
3. For each catch, give one line: the commit that broke it, the commit that
   fixed it, and the rule that would have blocked it.
4. If nothing was caught, say so plainly; that is a real result.
