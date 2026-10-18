---
name: injunct-coverage
description: Show how much of this repository's AGENTS.md, CLAUDE.md and CONTRIBUTING.md is actually enforced, as a visual report, with rewrites that would make more of it enforceable. Use when the user types /injunct-coverage or asks whether their agent instructions are enforced.
license: MIT
compatibility: Requires Python 3.10+, git, and the injunct package. Uses the model configured by INJUNCT_* variables or ~/.injunct/provider.json (for example Gemma 4 through the Gemini API).
---

# Injunct coverage

1. From the repository root, run:
   `python -m injunct coverage . --suggest --html .injunct/coverage.html`
2. Tell the user, in three short lines:
   - the percentage guarded, and the guarded / could be guarded / needs a human counts;
   - how many commits were not counted as good work because a later commit fixed them, if any;
   - how many rewrites were suggested and the percentage they would reach.
3. Show the report. If you have a tool that shows a file to the user (one that
   renders HTML in a side panel, for example), use it on
   `.injunct/coverage.html`. Otherwise give the user the file path to open.
4. If the output ends with a WARNING about the model, say the number is a floor.
5. Suggested rewrites are proposals: they never contradict this history, but
   the user must check each still says what they meant. Do not edit
   AGENTS.md or run `--adopt` unless the user asks.
