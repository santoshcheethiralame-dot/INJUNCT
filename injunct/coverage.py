"""How much of what this repository tells its agents is actually enforced.

Every repository now carries instructions for coding agents - AGENTS.md,
CLAUDE.md, CONTRIBUTING.md, a copilot-instructions file - and every one of them
is prose. An agent reads it, mostly follows it, and under pressure skims past
it. Nobody knows which of those sentences would stop anything.

This reads those files and answers per sentence:

  ENFORCED    compiled to a template, and the repository's own history proves
              it: at least one past commit could have contradicted it, and none
              did. It can bind today.
  CHECKABLE   it compiles, but it has not earned the right to block. Either no
              past commit could test it, it names files that do not exist, or
              the history already breaks it - and those commits are listed.
  UNCHECKED   no template can express it: a judgement call, a human process,
              something only running code could tell, or too vague to test.

Candidate sentences are found deterministically - every bullet, and every
sentence that sounds like an instruction - so each one is a real line of the
document and nothing can be invented. The model then does one narrow job per
candidate: say whether it is an instruction at all, and if so fill the blanks
of a typed template. It never decides whether a rule binds - empanelment does
that, deterministically, against git history.

Nothing a model writes is executed here. Templates that run a command during a
replay (`required_command`, `regression_test`) are never produced from prose;
"after X run Y" becomes `must_run`, which reads commands rather than running
them.
"""
from __future__ import annotations

import hashlib
import threading
import json
import os
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import empanel, mine, provider, templates, verbs
from .change import Change
from .db import Ledger, ledger_path
from .shell import run as sh

DOC_NAMES = (
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md",
    ".github/copilot-instructions.md", ".cursorrules", ".windsurfrules",
    ".github/pull_request_template.md",
)

# The templates a sentence of prose may become. Each one decides from the diff
# alone; none of them runs anything.
FROM_PROSE = ("co_change", "forbidden_edit", "must_not_appear", "must_not_remove",
              "must_appear", "must_run")
REASONS = ("judgement", "process", "runtime", "vague")
NOT_AN_INSTRUCTION = "none"
WORKERS = 4            # parallel model calls; free tiers allow this, and 429s back off
HISTORY = 100          # commits replayed; enough to judge, quick on a laptop
CACHE = Path(os.environ.get("INJUNCT_COVERAGE_CACHE") or Path.home() / ".injunct" / "coverage-cache.json")


@dataclass
class Rule:
    doc: str
    line: int
    text: str
    status: str = "unchecked"            # enforced | checkable | unchecked
    template: str | None = None
    params: dict = field(default_factory=dict)
    says: str = ""
    reason: str = ""
    receipt: dict = field(default_factory=dict)
    broken_by: list[str] = field(default_factory=list)   # past commits that break it


# ---------------------------------------------------------------- the model --

class _Model:
    """One wrapper around the model for a whole run.

    A single slow sentence must not cost the run its model, but a dead
    endpoint must not cost one timeout per sentence either: three failures in
    a row and the model is switched off, and the summary says so loudly.

    Answers are cached on disk by (model, prompt): a demo rerun is instant and
    a coverage number does not drift between two runs of the same model.
    """

    GIVE_UP = 3

    def __init__(self, enabled: bool = True):
        self.wanted = self.enabled = enabled
        self.used = False
        self.failed = 0
        self._streak = 0
        self._lock = threading.Lock()
        self._cache = {}
        if enabled:
            try:
                self._cache = json.loads(CACHE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._cache = {}

    def revive(self) -> None:
        with self._lock:
            self.enabled, self._streak = self.wanted, 0

    def ask(self, prompt: str, system: str) -> dict | None:
        if not self.wanted:
            return None
        key = hashlib.sha1(f"{provider.MODEL}\0{system}\0{prompt}".encode()).hexdigest()
        raw = self._cache.get(key)
        if raw is None:
            # Giving up stops new calls only. An answer already on disk is
            # still the model's answer, and throwing it away would score a
            # sentence "no model reachable" when the model did reach it.
            if not self.enabled:
                return None
            try:
                raw = provider.chat(prompt, system=system, timeout=180)
            except provider.Unavailable:
                with self._lock:
                    self.failed += 1
                    self._streak += 1
                    if self._streak >= self.GIVE_UP:
                        self.enabled = False
                return None
            with self._lock:
                self._streak = 0
                self._cache[key] = raw
                try:
                    CACHE.parent.mkdir(parents=True, exist_ok=True)
                    CACHE.write_text(json.dumps(self._cache), encoding="utf-8")
                except OSError:
                    pass
        self.used = True
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            return json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            return None


# ------------------------------------------------------------ the documents --

def find_docs(repo: Path) -> list[Path]:
    """The agent-facing documents, matched case-insensitively at their usual paths."""
    tracked = {p.lower(): p for p in _files(repo)}
    seen, out = set(), []
    for name in DOC_NAMES:
        hit = tracked.get(name.lower())
        if hit and hit.lower() not in seen:
            seen.add(hit.lower())
            out.append(repo / hit)
    return out


def _files(repo: Path) -> list[str]:
    r = sh("git ls-files", repo)
    if r.returncode == 0 and r.stdout.strip():
        return [x.strip().replace("\\", "/") for x in r.stdout.splitlines() if x.strip()]
    return [p.relative_to(repo).as_posix() for p in repo.rglob("*")
            if p.is_file() and ".git" not in p.parts and ".injunct" not in p.parts]


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[`*_>#]", "", s).split()).lower()


DIRECTIVE = re.compile(
    r"\b(must|never|always|do not|don't|dont|should|shall|required?|make sure|ensure|avoid|"
    r"only|run|use|keep|add|update|prefer|needs|no )\b", re.I)
BULLET = re.compile(r"^([-*+]|\d+[.)])\s+")


SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*\"(])")


def _blocks(text: str) -> list[tuple[int, str, bool]]:
    """Bullets and paragraphs as (first line, joined text, is_bullet).

    Markdown is often hard-wrapped at 80 columns, so one instruction spans
    several lines. Judged line by line, "DO NOT share their snapshots with"
    and "`insta::allow_duplicates!`" are two fragments neither of which means
    anything; a continuation line belongs to the bullet or paragraph above it.
    """
    blocks: list[list] = []
    fence = False
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("```"):
            fence = not fence
            blocks.append(None)
            continue
        if fence or not line or line.startswith(("#", "|", "<", "![", "---")):
            blocks.append(None)
            continue
        if BULLET.match(line):
            blocks.append([i, BULLET.sub("", line), True])
        elif blocks and blocks[-1] is not None:
            blocks[-1][1] += " " + line
        else:
            blocks.append([i, line, False])
    return [tuple(b) for b in blocks if b is not None]


def extract(text: str) -> list[tuple[int, str]]:
    """Every candidate instruction in a document, as (line, exact text).

    Bullets always count - in a document written for agents nearly every
    bullet is an instruction. Paragraphs are split into sentences, and a
    sentence counts when it sounds like one. The model later throws out the
    candidates that instruct nothing.
    """
    out, seen = [], set()
    for line, text, bullet in _blocks(text):
        for piece in ([text] if bullet else SENTENCE.split(text)):
            piece = piece.strip()
            if len(piece) >= 12 and (bullet or DIRECTIVE.search(piece)) and _norm(piece) not in seen:
                seen.add(_norm(piece))
                out.append((line, piece))
    return out


# ------------------------------------------------------------ the compiling --

COMPILE = """You turn one instruction from a repository's agent documentation into a deterministic check, if one exists.
A check may only be one of these templates:
  co_change       {"trigger": glob, "required": glob}   changing a trigger file requires changing a required file in the same commit
  forbidden_edit  {"glob": glob}                         these files must never be edited by hand
  must_not_appear {"regex": re, "glob": glob}            no added line in these files may match the regex
  must_not_remove {"regex": re, "glob": glob}            no removed line in these files may match the regex
  must_appear     {"regex": re, "glob": glob}            every changed file matching glob must contain the regex
  must_run        {"glob": glob, "cmd": shell}           after changing these files, this command must have been run
Globs must name paths that exist in the file list you are given. Regexes are Python syntax.
If the text is not an instruction at all (a description, a heading, a list of links), use kind "none".
If no template can express the instruction, say why, with one of:
  judgement (needs taste: naming, clarity, style beyond a pattern)
  process   (a human workflow: issues, reviews, CLAs, communication)
  runtime   (only running the code could tell)
  vague     (too unspecific to test)
Reply with JSON only, either
  {"template": "...", "params": {...}, "says": "one plain sentence, under 14 words"}
or
  {"template": null, "kind": "none|judgement|process|runtime|vague", "why": "one short sentence"}"""


UNANSWERED = ("no model reachable, and it is not in a form `injunct rule` understands")


def compile_rule(text: str, files: list[str], model: _Model,
                 compact: bool = False) -> tuple[str | None, dict, str]:
    """(template, params, says) or (None, {"kind":..}, why).

    `compact` is the second try for a sentence whose first call failed: a
    smaller slice of the tree, so a model that ran out of time on the full
    prompt has less to read.
    """
    parsed = verbs.parse(text)
    if parsed:
        t, p, says = parsed
        if t == "required_command":
            t = "must_run"
        return t, p, says
    sample = _sample(files, 30) if compact else _sample(files)
    d = model.ask(json.dumps({"instruction": text, "files": sample}, indent=1), COMPILE)
    if d is None:
        return None, {"kind": "vague", "unanswered": True}, UNANSWERED
    t = d.get("template")
    if not t:
        kind = d.get("kind") if d.get("kind") in REASONS + (NOT_AN_INSTRUCTION,) else "vague"
        return None, {"kind": kind}, str(d.get("why") or "no template fits")[:160]
    if t == "required_command":
        t = "must_run"
    p = d.get("params") or {}
    if t not in FROM_PROSE or not templates.valid(t, p):
        return None, {"kind": "vague"}, f"the model proposed `{t}` with unusable blanks"
    if "regex" in p:
        try:
            re.compile(p["regex"])
        except re.error:
            return None, {"kind": "vague"}, "the model's pattern is not a valid regex"
    says = (d.get("says") or "").strip() or templates.render(t, p)
    return t, {k: str(v) for k, v in p.items()}, says


def _sample(files: list[str], n: int = 80) -> list[str]:
    """Enough of the tree for real globs: every top-level entry, then a spread of paths."""
    tops = sorted({f.split("/", 1)[0] + ("/" if "/" in f else "") for f in files})
    rest = [f for f in files if f not in tops]
    step = max(1, len(rest) // max(1, n - len(tops)))
    return (tops + rest[::step])[:n]


def anchored(t: str, p: dict, files: list[str]) -> str | None:
    """A rule about files that do not exist can never fire, so it proves nothing."""
    keys = ("trigger", "required") if t == "co_change" else ("glob",)
    for k in keys:
        if p.get(k) and not templates._hits(files, p[k]):
            return f"`{p[k]}` matches no file in this repository"
    return None


# --------------------------------------------------------------- the proof --

def prove(led: Ledger, repo: Path, t: str, p: dict) -> tuple[str, dict, list[str]]:
    """Replay a documented rule against the commits that already landed.

    A documented rule has no failing case of its own, so only the half of
    empanelment that matters here applies: it must stay silent on past work,
    and at least one past commit must have been able to say otherwise.
    """
    _, receipt = empanel.empanel(led, str(repo), t, p, Change(repo=repo), sample=HISTORY)
    receipt = {**receipt, "fire": "n/a (documented)"}
    if receipt.get("false_ids"):
        broke = [r["task"] for r in led.successful_runs(str(repo), limit=10_000)
                 if r["id"] in set(receipt["false_ids"])]
        return "checkable", receipt, broke
    if receipt.get("judged", 0) < empanel.MIN_JUDGED:
        return "checkable", receipt, []
    return "enforced", receipt, []


# ------------------------------------------------------------------ the run --

def run(target: str | Path, use_model: bool = True, adopt: bool = False) -> dict:
    repo, remote = _resolve(target)
    model = _Model(use_model)
    files = _files(repo)
    docs = find_docs(repo)
    led = Ledger(ledger_path(repo))
    mine.record_history(repo, led, limit=HISTORY)

    found = [(doc.relative_to(repo).as_posix(), line, text) for doc in docs
             for line, text in extract(doc.read_text(encoding="utf-8", errors="replace"))]
    with ThreadPoolExecutor(WORKERS) as pool:
        compiled = list(pool.map(lambda f: compile_rule(f[2], files, model), found))
    # A failed call is usually one timeout or one bad 500, not a dead model.
    # Each gets one more try, one at a time, on a smaller prompt - and the
    # endpoint gets a fresh chance even if the first pass gave up on it.
    again = [i for i, c in enumerate(compiled) if c[1].get("unanswered")]
    if again and model.wanted:
        model.revive()
        for i in again:
            compiled[i] = compile_rule(found[i][2], files, model, compact=True)
    unanswered = sum(1 for c in compiled if c[1].get("unanswered"))

    rules: list[Rule] = []
    for (rel, line, text), (t, p, says) in zip(found, compiled):
        if t is None and p.get("kind") == NOT_AN_INSTRUCTION:
            continue
        r = Rule(doc=rel, line=line, text=text)
        if t is None:
            r.reason = f"{p['kind']}: {says}"
        else:
            r.template, r.params, r.says = t, p, says
            why = anchored(t, p, files)
            if why:
                r.status, r.reason = "checkable", why
            else:
                r.status, r.receipt, r.broken_by = prove(led, repo, t, p)
                if r.status == "enforced":
                    r.reason = f"held on all {r.receipt.get('judged')} past commits that could test it"
                elif r.broken_by:
                    r.reason = f"{len(r.broken_by)} past commit(s) already break it"
                else:
                    r.reason = r.receipt.get("note") or "no past commit could test it"
        rules.append(r)

    if adopt:
        _adopt(led, repo, rules)
    led.close()
    return _summary(repo, remote, docs, rules, model, unanswered)


def _resolve(target) -> tuple[Path, str | None]:
    if Path(target).exists():
        return Path(target).resolve(), None
    slug = str(target).removeprefix("https://github.com/").removesuffix(".git").strip("/")
    dest = Path(tempfile.mkdtemp(prefix="injunct-cov-")) / slug.replace("/", "__")
    r = sh(f'git -c core.longpaths=true clone -q --depth {HISTORY + 20} "https://github.com/{slug}.git" "{dest}"', dest.parent,
           timeout=180)
    if r.returncode != 0:
        raise SystemExit(f"could not clone {target}: {r.stderr.strip()[:200]}")
    return dest, slug


def _adopt(led: Ledger, repo: Path, rules: list[Rule]) -> None:
    """Put the documented rules on the ledger: enforced ones bind, the rest advise."""
    have = {(h["template"], json.dumps(h["params"], sort_keys=True)) for h in led.holdings(repo=str(repo))}
    for r in rules:
        if not r.template or (r.template, json.dumps(r.params, sort_keys=True)) in have:
            continue
        run_id = led.open_run(str(repo), f"documented: {r.doc}:{r.line}", arm="coverage")
        led.close_run(run_id, "fail")
        case_id = led.file_case(run_id, str(repo), "documented", "high", r.text, [],
                                json.dumps({"doc": r.doc, "line": r.line}))
        led.establish(case_id, str(repo), r.template, r.params, r.says,
                      status="binding" if r.status == "enforced" else "persuasive",
                      empanel={**r.receipt, "documented": f"{r.doc}:{r.line}"})


def _summary(repo, remote, docs, rules: list[Rule], model: _Model, unanswered: int = 0) -> dict:
    n = len(rules)
    count = {s: sum(r.status == s for r in rules) for s in ("enforced", "checkable", "unchecked")}
    return {
        "repo": remote or str(repo),
        "docs": [d.relative_to(repo).as_posix() for d in docs],
        "model": provider.MODEL if model.used else "none (`injunct rule` forms only)",
        # Only what is still unanswered at the end counts: a call that failed
        # and then succeeded on its second try cost time, not accuracy.
        "model_failed": model.wanted and (unanswered > 0 or not model.used),
        "model_failures": unanswered,
        "total": n,
        **count,
        "percent": round(100 * count["enforced"] / n) if n else 0,
        "rules": [asdict(r) for r in rules],
    }


# ---------------------------------------------------------------- outputs --

def badge(percent: int, label: str = "agent rules enforced") -> str:
    """A shields-style SVG, drawn here so the badge needs no network."""
    color = "#4c1" if percent >= 70 else "#dfb317" if percent >= 40 else "#e05d44"
    value = f"{percent}%"
    lw, vw = 6 * len(label) + 12, 7 * len(value) + 12
    w = lw + vw
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="20" role="img" '
            f'aria-label="{label}: {value}"><title>{label}: {value}</title>'
            f'<rect width="{lw}" height="20" fill="#555"/><rect x="{lw}" width="{vw}" height="20" fill="{color}"/>'
            f'<g fill="#fff" text-anchor="middle" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">'
            f'<text x="{lw / 2}" y="14">{label}</text><text x="{lw + vw / 2}" y="14">{value}</text></g></svg>')


def markdown(s: dict) -> str:
    mark = {"enforced": "ENFORCED", "checkable": "checkable", "unchecked": "unchecked"}
    out = [f"## Agent-rule coverage: {s['percent']}% enforced", "",
           f"{s['enforced']} enforced · {s['checkable']} checkable · {s['unchecked']} unchecked "
           f"· {s['total']} instructions in {', '.join(s['docs']) or 'no agent documents'}", "",
           "| | instruction | where | rule | why |", "|---|---|---|---|---|"]
    for r in s["rules"]:
        rule = f"`{templates.render(r['template'], r['params'])}`" if r["template"] else ""
        text = r["text"].replace("|", "\\|")
        out.append(f"| {mark[r['status']]} | {text} | {r['doc']}:{r['line']} | {rule} | "
                   f"{(r['reason'] or r['receipt'].get('false', '')).replace('|', '/')} |")
    out += ["", f"<sub>model: {s['model']} · proven against git history by injunct</sub>"]
    return "\n".join(out)
