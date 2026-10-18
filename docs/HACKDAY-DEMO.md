# Hack Day run sheet

Five minutes, offline, from this laptop. Every line under "you will see" is real
output from a rehearsal on 18 Oct 2026. If a line does not appear, stop and
say so rather than talking over it.

The clinic repository is planted, and the pitch says so. Its history contains
three mistakes, each fixed later by a commit that rewrites the line the mistake
wrote. Every verdict below is computed from that history; none is hardcoded.
uv is the proof that the same thing runs on a real repository.

---

## Before the room (once, 2 minutes)

PowerShell, from `C:\Users\carbo\projects\hackathons\demo-repos`:

```powershell
$env:INJUNCT_MODEL = "gemma-4-26b-a4b-it"
```

```powershell
$env:INJUNCT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
```

The model name must be set even offline: recorded answers are keyed by model.
No API key is needed for anything on this sheet; every answer is cached.

```powershell
python -m injunct coverage --demo clinic --adopt
```

This builds `demo-repos\clinic` fresh and puts its proven rules on the ledger
(about 14 seconds). Then check uv answers from cache in under 15 seconds:

```powershell
python -m injunct coverage uv
```

If uv takes minutes instead of seconds, the cache is cold on this machine.
Then do the uv beat from the saved output in `demo-repos\uv-coverage.txt`.

---

## 1. "Your AGENTS.md is a suggestion" (60 s)

```powershell
python -m injunct coverage clinic
```

You will see:

```
  33% of the instructions in AGENTS.md are enforced.
  3 enforced   2 checkable   4 unchecked   (9 instructions)
```

Point at three things on screen:

- **ENFORCED**, e.g. `co_change( models/* -> migrations/* )` "held on all 13
  past commits that could test it". Gemma 4 compiled the sentence; the
  repository's history proved it.
- **checkable** "Never hand-edit `client/generated.py`": broken by
  `Regenerate client from the spec`. The repository's own generator touches
  that file, so a plain "never edit" rule would block the team's own tooling.
  Coverage catches that before the rule ever binds.
- **unchecked**, each with its reason: judgement, process, runtime. No tool
  will ever enforce "keep functions small", and this says so.

## 2. "A commit someone had to fix is not evidence of good work" (45 s)

Scroll to the top of the same output:

```
  3 commit(s) left out of the proof, because a later commit fixed them:
    744e19f: quick debug for the double-booking bug
      fixed by a1650dd Fix stray debug print in booking
    8e112ba: Add Visit model
      fixed by 9f500f5 Fix Visit: add the missing migration and store a real date
    7267f8b: Silence the Appointment type error
      fixed by 415d28f Fix Appointment.room properly instead of ignoring the type
```

Then show what happens if every commit is trusted:

```powershell
python -m injunct coverage clinic --trust-history
```

```
  0% of the instructions in AGENTS.md are enforced.
  0 enforced   5 checkable   4 unchecked   (9 instructions)
```

Line to say: *trusting every commit, the bugs themselves make every rule look
wrong. Take out the three commits somebody came back and fixed, and three
rules earn the right to block.* Run the plain command once more so the ledger
is back to 33%:

```powershell
python -m injunct coverage clinic
```

## 3. "What would it have caught?" (45 s)

```powershell
python -m injunct hindsight clinic --no-docs
```

```
  3 fix commits in the last 16; 3 commits they trace back to.
  ...
  caught      3/3 (100%) of the commits that introduced a fixed problem
  baseline    fired on 3/10 (30%) of the other commits
  binding     3 of those catches came from a rule that blocks today
```

Line to say: *we trace each fix back with SZZ, blaming the lines the fix had
to change, and replay the rules against the commit that broke them. The
baseline is there because a rule that fires on everything catches every bug
for free.*

## 4. The block (45 s)

```powershell
cd clinic
```

```powershell
Add-Content models\patient.py "    verified: bool"
```

```powershell
python -m injunct gate .
```

```
|  HALT   BINDING HOLDING No 1   ESTABLISHED 18 OCT 2026                 |
|  Changing a model requires adding a migration in the same commit.      |
|  co_change( models/* -> migrations/* )                                 |
|  models/patient.py changed, nothing under migrations/* did             |
|  from AGENTS.md:7   held on 13 past commits    cited 0                 |
|  DO THIS NEXT:  create migrations/009_patient.sql                      |
```

Exit code 1, so it drops into CI or a pre-commit hook as it is. Do the next step:

```powershell
Set-Content migrations\009_patient.sql "ALTER TABLE patient ADD verified BOOLEAN;"
```

```powershell
python -m injunct gate .
```

```
no binding precedent fires on this working tree.
```

The same card reaches Claude Code and opencode before the write lands
(`injunct claude`, `injunct opencode`), and `action.yml` runs this gate on
every pull request. Reset for the next run:

```powershell
git checkout -- models/patient.py; Remove-Item migrations\009_patient.sql; cd ..
```

## 5. A real repository: astral-sh/uv (45 s)

```powershell
python -m injunct coverage uv
```

```
  3% of the instructions in AGENTS.md, CONTRIBUTING.md, .github/PULL_REQUEST_TEMPLATE.md are enforced.
  2 enforced   3 checkable   58 unchecked   (63 instructions)
```

- ENFORCED: no `#[allow(clippy::…)]` in Rust, and no `pull_request_target` in
  workflows (a security rule). Both held on 90 commits.
- checkable: "avoid `matches!` and wildcard arms" was already broken by 5 of
  uv's own recent commits, which coverage lists by name.
- 58 unchecked: 22 process, 15 judgement, 12 runtime, 9 vague.

Line to say: *most of what teams write for agents is process and judgement.
That is the finding, and it is why a low number is honest rather than a bug.*

---

## Questions you will get

- **"Isn't the clinic repo rigged?"** It is planted, and we say so. The
  verdicts are computed; the uv run is the same code on a repository we did
  not write.
- **"What does the model actually do?"** It reads each candidate sentence and
  fills the blanks of one of six templates, or says why none fits. It never
  writes a checker and never decides what binds. The history replay decides.
- **"Why Gemma 4?"** It's open-weight, free on the Gemini API, and good
  enough at filling a schema. Any OpenAI-compatible endpoint works, including
  a local Ollama, so the whole thing can run with no network.
- **"Does hindsight work on real repos?"** On uv's last 300 commits, 7
  bug-introducing commits trace cleanly. The rules fire on 4 of them against a
  29% baseline, but those matches are not causal. It is a method, shown
  honestly, not yet a result.
- **"What was built today?"** See `docs/SUBMISSION.md`, under Origin.

## If something breaks

- **uv slow:** the cache is cold. Show `demo-repos\uv-coverage.txt` instead.
- **Clinic numbers differ:** rebuild it with
  `python -m injunct coverage --demo clinic --adopt` and start again.
- **Wi-fi down:** nothing on this sheet needs it.
