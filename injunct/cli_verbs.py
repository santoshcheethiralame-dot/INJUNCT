"""Terminal output for the everyday commands.

Kept apart from `verbs.py` so the logic stays testable without a terminal, and
apart from `__main__.py` so that file stays a router.
"""
from __future__ import annotations

from pathlib import Path

from . import mine, templates, verbs


def _rule_text(h: dict) -> str:
    return (templates.render(h["template"], h["params"])
            if h["template"] in templates.TEMPLATES else h["template"])


def cmd_init(a) -> int:
    pack = [] if getattr(a, "no_pack", False) else verbs.install_pack(Path(a.path))
    if pack:
        binding = sum(1 for r in pack if r["binding"])
        print()
        print(f"  {len(pack)} common-mistake rules installed "
              f"({binding} binding, {len(pack) - binding} advisory):")
        print()
        for r in pack:
            mark = "BINDING " if r["binding"] else "advisory"
            print(f"  {str(r['id']).rjust(3)}  {mark}  {r['says']}")
    found = verbs.init(Path(a.path))
    if not found:
        state = mine.history_state(Path(a.path))
        if state == "not-a-repo":
            print("  this is not a git repository, so there is no history to read.")
            print("  teach it directly instead:  injunct rule \"src/*.py needs tests/\"")
        elif state == "no-commits":
            print("  this repository has no commits yet, so there is nothing to learn from.")
            print("  teach it directly instead:  injunct rule \"src/*.py needs tests/\"")
        elif state == "thin":
            print("  too little history to be sure of anything (under 20 commits).")
            print("  come back later, or teach it directly:")
            print("    injunct rule \"src/*.py needs tests/\"")
        else:
            print("  nothing to learn yet.")
            print("  no habit in this history is strong enough to be a rule, and")
            print("  inventing one would be worse than saying so.")
        return 0
    print()
    print(f"  {len(found)} rule(s) proposed, all advisory until you confirm them:")
    print()
    for r in found:
        e = r["evidence"]
        detail = (f"seen {e['support']}x, held {e['confidence']:.0%} of the time"
                  if "support" in e else f"declared in {e.get('declared_in')}")
        print(f"  {str(r['id']).rjust(3)}  {r['says']}")
        print(f"       {detail}")
    ids = " ".join(str(r["id"]) for r in found)
    print()
    print(f"  injunct confirm {ids}    to make them binding")
    print()
    return 0


def cmd_confirm(a) -> int:
    for d in verbs.confirm(Path(a.path), a.ids):
        note = "" if d["status"] == "binding" else "   (it would have blocked past work)"
        print(f"  {d['id']}  {d['status'].upper()}{note}")
    return 0


def cmd_rule(a) -> int:
    out = verbs.rule(Path(a.path), a.sentence)
    if not out:
        print("  that did not parse. the three forms are:")
        print()
        print(verbs.HELP)
        return 2
    print(f"  {out['says']}")
    print(f"  {templates.render(out['template'], out['params'])}")
    if out["status"] == "binding":
        print("  BINDING")
    else:
        print("  ADVISORY  - it would have blocked work that already succeeded")
    return 0


def cmd_why(a) -> int:
    rows = verbs.why(Path(a.path), a.file)
    if not rows:
        print(f"  nothing applies to {a.file}.")
        return 0
    print()
    print(f"  {len(rows)} rule(s) apply to {a.file}:")
    print()
    for h in rows:
        print(f"  {str(h['id']).rjust(3)}  {h['status'].upper():<11} {h['says']}")
        print(f"       {_rule_text(h)}")
        print(f"       from a {h['source']} case: {h['reason'][:64]}")
    print()
    return 0


def cmd_off(a) -> int:
    d = verbs.mute(Path(a.path), a.id, on=False)
    if not d:
        print(f"  no rule {a.id}.")
        return 1
    print(f"  {a.id} muted (was {d['was']}). the case stays on the docket.")
    return 0


def cmd_on(a) -> int:
    d = verbs.mute(Path(a.path), a.id, on=True)
    if not d:
        print(f"  no rule {a.id}.")
        return 1
    print(f"  {a.id} is {d['status']} again.")
    return 0


def cmd_status(a) -> int:
    s = verbs.status(Path(a.path), a.days)
    print()
    print(f"  last {s['days']} days")
    print(f"    {s['stopped']} mistake(s) stopped before they landed")
    print(f"    {s['overridden']} time(s) you went ahead anyway")
    print()
    print(f"  {s['binding']} binding   {s['advisory']} advisory   "
          f"{s['muted']} muted   {s['overruled']} overruled   ({s['cases']} cases)")
    print()
    return 0


def cmd_hook(a) -> int:
    t = verbs.hook(Path(a.path))
    if not t:
        print("  not a git repository.")
        return 1
    print(f"  installed {t}")
    print("  `git commit` now refuses anything a binding precedent fires on.")
    return 0


MODES = {
    "enforce": "binding precedent aborts the write. This is the point.",
    "advise":  "past failures are injected as prose and nothing is blocked.",
    "off":     "installed but inert.",
}


def cmd_opencode(a) -> int:
    try:
        out = verbs.opencode(Path(a.path), a.mode)
    except FileNotFoundError as e:
        print(f"  {e}")
        return 1
    print(f"  installed {out['plugin']}")
    print(f"  configured {out['config']}")
    print()
    print("  the plugin decides nothing on its own. Start the service it asks:")
    print("    injunct serve")
    print()
    if a.mode != "enforce":
        print(f"  mode {a.mode}: {MODES[a.mode]}")
        print(f"    INJUNCT_MODE={a.mode} opencode")
    else:
        print("  then run opencode in this repository. A write that fires a")
        print("  binding precedent is aborted before it lands, and the card")
        print("  goes back to the model as the tool's error.")
    print()
    print("  `advise` is the same plugin with the throw removed - prose only,")
    print("  which is what every other memory layer does. It is arm B.")
    return 0


def cmd_claude(a) -> int:
    out = verbs.claude(Path(a.path), a.mode, a.check)
    print(f"  configured {out['config']}")
    print("  events: UserPromptSubmit briefs, PreToolUse denies, PostToolUse re-checks, Stop learns")
    if a.check:
        print(f"  check after each turn: {a.check}")
    print()
    if a.mode != "enforce":
        print(f"  mode {a.mode}: {MODES[a.mode]}")
        print(f"    INJUNCT_MODE={a.mode} claude")
    else:
        print("  Claude Code will now refuse a write that fires a binding")
        print("  holding, before the bytes land, and hand the card back to the")
        print("  model as the reason it was denied. No service to start.")
    print()
    # self_disarm is binding on .claude/**, and an uncommitted file counts as a
    # change - so a fresh install trips its own rule on the very next write
    # until these are in git. Better to say so than to let it look like a bug.
    print("  commit the install, or the gate fires on its own files:")
    print("    git add .claude && git commit -m \"install injunct\"")
    return 0


def _demo_dir(path: str, coverdemo) -> Path:
    """Build the demo where asked (fresh), or in a new temp folder."""
    import shutil
    import tempfile
    if path in (".", ""):
        return coverdemo.build(Path(tempfile.mkdtemp(prefix="injunct-demo-")) / "clinic")
    dest = Path(path).resolve()
    if dest.exists():
        if not (dest / ".git").exists() or not (dest / "AGENTS.md").exists():
            raise SystemExit(f"{dest} exists and is not a previous demo; refusing to overwrite it")
        shutil.rmtree(dest, onerror=lambda f, p, e: (Path(p).chmod(0o700), f(p)))
    return coverdemo.build(dest)


def cmd_coverage(a) -> int:
    import json

    from . import coverage
    if a.demo:
        import tempfile

        from . import coverdemo, provider
        a.path = str(_demo_dir(a.path, coverdemo))
        coverage.CACHE, provider.MODEL = coverdemo.CACHE, coverdemo.MODEL
        print(f"  demo repository: {a.path}")
    s = coverage.run(a.path, use_model=not a.no_model, adopt=a.adopt, trust_history=a.trust_history)
    if a.badge:
        Path(a.badge).write_text(coverage.badge(s["percent"]), encoding="utf-8")
    if a.md:
        Path(a.md).write_text(coverage.markdown(s), encoding="utf-8")
    if a.json:
        print(json.dumps(s, indent=2))
        return 0
    if not s["docs"]:
        print("  no agent documents here (AGENTS.md, CLAUDE.md, CONTRIBUTING.md, ...).")
        return 0
    print()
    print(f"  {s['percent']}% of the instructions in {', '.join(s['docs'])} are enforced.")
    print(f"  {s['enforced']} enforced   {s['checkable']} checkable   {s['unchecked']} unchecked"
          f"   ({s['total']} instructions)")
    if s.get("discounted"):
        print()
        print(f"  {len(s['discounted'])} commit(s) left out of the proof, because a later commit fixed them:")
        for d in s["discounted"]:
            print(f"    {d['commit']}")
            print(f"      fixed by {d['fixed_by']}")
    print()
    mark = {"enforced": "ENFORCED ", "checkable": "checkable", "unchecked": "unchecked"}
    for r in s["rules"]:
        text = r["text"] if len(r["text"]) <= 72 else r["text"][:69] + "..."
        print(f"  {mark[r['status']]}  {text}")
        if r["template"]:
            print(f"             {templates.render(r['template'], r['params'])}")
        print(f"             {r['doc']}:{r['line']}  {r['reason']}")
        for c in r["broken_by"][:3]:
            print(f"               broken by {c}")
    print()
    print(f"  model: {s['model']}")
    if s.get("model_failed"):
        print(f"  WARNING: {s['model_failures']} instruction(s) got no answer from the model, even on retry;")
        print("  they are scored unchecked, so this number is a floor, not a measurement.")
    if not a.adopt and (s["enforced"] or s["checkable"]):
        print("  injunct coverage --adopt    to put these rules on the ledger")
    print()
    return 0


def cmd_hindsight(a) -> int:
    import json

    from . import coverage, hindsight
    if a.demo:
        import tempfile

        from . import coverdemo, provider
        a.path = str(_demo_dir(a.path, coverdemo))
        coverage.CACHE, provider.MODEL = coverdemo.CACHE, coverdemo.MODEL
        print(f"  demo repository: {a.path}")
    repo = Path(a.path) if Path(a.path).exists() else None
    if repo is not None:
        # Everything Injunct can know before anything goes wrong: the pack,
        # the habits in the history, and - if a model is set - the documents.
        verbs.install_pack(repo)
        verbs.init(repo)
        if not a.no_docs:
            coverage.run(repo, use_model=True, adopt=True)
    s = hindsight.run(a.path, window=a.window)
    if a.json:
        print(json.dumps(s, indent=2))
        return 0
    r = hindsight.rate
    print()
    print(f"  {s['fixes']} fix commits in the last {s['window']}; "
          f"{s['introducers']} commits they trace back to.")
    print(f"  {s['rules']} rules replayed against each, as it landed.")
    print()
    print(f"  caught      {r(s['caught'], s['introducers'])} of the commits that introduced a fixed problem")
    print(f"  baseline    fired on {r(s['clean_fired'], s['clean'])} of the other commits")
    print(f"  binding     {s['caught_binding']} of those catches came from a rule that blocks today")
    print()
    for c in s["catches"]:
        print(f"  {c['introduced']}")
        print(f"    fixed by  {c['fixed_by']}")
        for h in c["rules"][:3]:
            mark = "BINDING " if h["status"] == "binding" else "advisory"
            print(f"    {mark}  {h['says']}")
            print(f"              {h['why']}")
        print()
    print("  traced with SZZ (blame the lines each fix changed); check each pair by hand.")
    if s["shallow"]:
        print("  shallow clone: commits older than the clone could not be traced.")
    print()
    return 0


def register(sub) -> None:
    hs = sub.add_parser("hindsight", help="replay the rules against the commits that later needed a fix")
    hs.add_argument("path", nargs="?", default=".", help="a repository path, GitHub URL or owner/name")
    hs.add_argument("--window", type=int, default=300, help="how many recent commits to read")
    hs.add_argument("--no-docs", action="store_true", help="skip compiling AGENTS.md (no model calls)")
    hs.add_argument("--demo", action="store_true", help="the clinic demo repository, offline")
    hs.add_argument("--json", action="store_true")
    hs.set_defaults(fn=cmd_hindsight)

    cv = sub.add_parser("coverage", help="how much of AGENTS.md / CONTRIBUTING.md is actually enforced")
    cv.add_argument("path", nargs="?", default=".", help="a repository path, GitHub URL or owner/name")
    cv.add_argument("--adopt", action="store_true", help="put the rules on the ledger (enforced ones bind)")
    cv.add_argument("--no-model", action="store_true", help="heuristic extraction, no model calls")
    cv.add_argument("--badge", help="write an SVG badge to this path")
    cv.add_argument("--md", help="write a markdown report to this path")
    cv.add_argument("--json", action="store_true")
    cv.add_argument("--trust-history", action="store_true",
                    help="count every commit as good work, even ones a later commit fixed")
    cv.add_argument("--demo", action="store_true",
                    help="build the clinic demo repository and run on Gemma 4's recorded answers (offline)")
    cv.set_defaults(fn=cmd_coverage)

    i = sub.add_parser("init", help="learn this repo's habits from its own history")
    i.add_argument("--no-pack", action="store_true",
                   help="skip the common-mistake rules, mine history only")
    i.add_argument("path", nargs="?", default=".")
    i.set_defaults(fn=cmd_init)

    cf = sub.add_parser("confirm", help="promote mined rules to binding")
    cf.add_argument("ids", nargs="+", type=int)
    cf.add_argument("--path", default=".")
    cf.set_defaults(fn=cmd_confirm)

    ru = sub.add_parser("rule", help="teach it a rule in one sentence")
    ru.add_argument("sentence")
    ru.add_argument("path", nargs="?", default=".")
    ru.set_defaults(fn=cmd_rule)

    wy = sub.add_parser("why", help="which rules apply to this file")
    wy.add_argument("file")
    wy.add_argument("path", nargs="?", default=".")
    wy.set_defaults(fn=cmd_why)

    of = sub.add_parser("off", help="mute a rule that is wrong")
    of.add_argument("id", type=int)
    of.add_argument("path", nargs="?", default=".")
    of.set_defaults(fn=cmd_off)

    on = sub.add_parser("on", help="unmute a rule")
    on.add_argument("id", type=int)
    on.add_argument("path", nargs="?", default=".")
    on.set_defaults(fn=cmd_on)

    st = sub.add_parser("status", help="what it caught this week")
    st.add_argument("path", nargs="?", default=".")
    st.add_argument("--days", type=int, default=7)
    st.set_defaults(fn=cmd_status)

    hk = sub.add_parser("hook", help="install the git pre-commit hook")
    hk.add_argument("path", nargs="?", default=".")
    hk.set_defaults(fn=cmd_hook)

    oc = sub.add_parser("opencode", help="install the plugin that stops a write before it lands")
    oc.add_argument("path", nargs="?", default=".")
    oc.add_argument("--mode", choices=sorted(MODES), default="enforce")
    oc.set_defaults(fn=cmd_opencode)

    cc = sub.add_parser("claude", help="install the Claude Code hook that stops a write")
    cc.add_argument("path", nargs="?", default=".")
    cc.add_argument("--mode", choices=sorted(MODES), default="enforce")
    cc.add_argument("--check", default=None,
                    help="the repo's pass/fail command, run when the agent stops "
                         "(default: INJUNCT_CHECK, else `python oracle.py` if present)")
    cc.set_defaults(fn=cmd_claude)
