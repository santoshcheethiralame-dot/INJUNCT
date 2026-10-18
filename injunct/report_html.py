"""The coverage report as one self-contained page, written for the person reading it.

    injunct coverage . --html coverage.html

No scripts, no fonts, no network: it has to open from a file, inside an agent
app's side panel, on a judge's laptop with the wifi off. Light and dark follow
the viewer's system setting.

The page speaks the reader's language, not the tool's. "Enforced" is
*guarded*, a template is a sentence in English, and every card ends with what
to do about it. The technical form is one click away, never in the way.
"""
from __future__ import annotations

import html
import re
import time

from . import templates

CSS = """
:root{--bg:#fbfaf7;--fg:#1c1b19;--dim:#6b6860;--line:#e6e2d9;--card:#ffffff;
--ok:#1f7a4d;--ok-bg:#e6f4ec;--warn:#9a5b00;--warn-bg:#fdf1dc;--off:#5f5d57;--off-bg:#efede8;
--accent:#3b4cca;--accent-bg:#eceefd}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--fg:#ecebe7;--dim:#9b988f;--line:#2c2b28;
--card:#1d1c1a;--ok:#5fd19a;--ok-bg:#16301f;--warn:#f0b35a;--warn-bg:#33270f;--off:#b3b0a8;
--off-bg:#262522;--accent:#93a0ff;--accent-bg:#1f2240}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:920px;margin:0 auto;padding:32px 16px 64px}
a{color:var(--accent)}header p{margin:.15rem 0;color:var(--dim)}
h1{font-size:1.15rem;margin:0 0 .3rem;font-weight:650}
.big{display:flex;gap:24px;align-items:flex-end;flex-wrap:wrap;margin:26px 0 6px}
.pct{font-size:4rem;font-weight:750;line-height:1;letter-spacing:-.03em}
.pct small{font-size:1rem;font-weight:500;color:var(--dim);letter-spacing:0;margin-left:.4rem}
.then{color:var(--accent);font-weight:600;padding-bottom:.4rem}
.lede{font-size:1.05rem;margin:10px 0 14px;max-width:46em}
.bar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--off-bg);margin:6px 0 8px}
.bar span{display:block}.b-ok{background:var(--ok)}.b-warn{background:var(--warn)}
.legend{display:flex;gap:8px 20px;flex-wrap:wrap;font-size:.9rem;color:var(--dim)}
.dot{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:6px;vertical-align:0}
.d-ok{background:var(--ok)}.d-warn{background:var(--warn)}.d-off{background:var(--off-bg);border:1px solid var(--line)}
.todo{background:var(--accent-bg);border-radius:12px;padding:16px 18px;margin:26px 0}
.todo h2{margin:0 0 8px;color:var(--fg)}.todo ol{margin:0;padding-left:20px}.todo li{margin:6px 0}
h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin:40px 0 12px;font-weight:650}
h2 small{text-transform:none;letter-spacing:0;font-weight:400}
.doc{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 0;overflow:hidden;margin:10px 0}
.doc summary{cursor:pointer;padding:0 16px 8px;font-weight:600}
.ln{display:flex;gap:12px;padding:1px 16px;font-size:.9rem;color:var(--dim);text-decoration:none}
.ln i{font-style:normal;min-width:2.4em;text-align:right;opacity:.6;font:12px/1.9 ui-monospace,Consolas,monospace}
.ln span{white-space:pre-wrap;overflow-wrap:anywhere}
a.ln{color:var(--fg);border-left:4px solid transparent}a.ln:hover{filter:brightness(.97)}
a.l-ok{background:var(--ok-bg);border-left-color:var(--ok)}
a.l-warn{background:var(--warn-bg);border-left-color:var(--warn)}
a.l-off{background:var(--off-bg);border-left-color:var(--line)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0;scroll-margin-top:16px}
.card:target{outline:2px solid var(--accent)}
.top{display:flex;gap:10px;align-items:baseline;justify-content:space-between;flex-wrap:wrap}
.text{font-weight:550}.where{color:var(--dim);font-size:.85rem;white-space:nowrap}
.stamp{display:inline-block;font-size:.72rem;font-weight:700;letter-spacing:.05em;padding:2px 8px;
border-radius:999px;margin-right:8px;vertical-align:2px}
.s-ok{color:var(--ok);background:var(--ok-bg)}.s-warn{color:var(--warn);background:var(--warn-bg)}
.s-off{color:var(--off);background:var(--off-bg)}
.plain{margin-top:8px}.why{color:var(--dim);font-size:.92rem;margin-top:4px}
.next{margin-top:8px;font-size:.92rem}.next b{color:var(--accent)}
code{font:13px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}
details.rule{margin-top:6px;font-size:.85rem;color:var(--dim)}details.rule summary{cursor:pointer}
ul.broke{margin:6px 0 0;padding-left:18px;font-size:.88rem}
.sug .was{color:var(--dim);text-decoration:line-through;text-decoration-color:var(--line)}
.sug .now{font-weight:600;margin-top:4px}
.how{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin-top:40px}
.how summary{cursor:pointer;font-weight:600}
footer{margin-top:32px;color:var(--dim);font-size:.85rem}
"""

NAME = {"enforced": "Guarded", "checkable": "Could be guarded", "unchecked": "Needs a human"}
STAMP_CLASS = {"enforced": "s-ok", "checkable": "s-warn", "unchecked": "s-off"}
LINE_CLASS = {"enforced": "l-ok", "checkable": "l-warn", "unchecked": "l-off"}
KIND = {"judgement": "needs taste, not a pattern", "process": "a team process, not a file change",
        "runtime": "only running the code could tell", "vague": "too general to test"}


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _md(s) -> str:
    """Instruction text as written: escaped, with its `backticks` shown as code."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", _e(s))


def _name(repo: str) -> str:
    """owner/name for a GitHub repository, the folder name for a local one -
    a report is often shared, and a full local path says more than it should."""
    return repo.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] if ":" in repo or repo.startswith("/") else repo


def _anchor(doc: str, line: int) -> str:
    return "i-" + re.sub(r"[^a-z0-9]+", "-", doc.lower()) + f"-{line}"


def _commits(text: str, github: str | None) -> str:
    """Escape, and link every short commit hash to GitHub when the repository is there."""
    out = _e(text)
    if github:
        out = re.sub(r"\b([0-9a-f]{7,40})\b",
                     lambda m: f'<a href="https://github.com/{_e(github)}/commit/{m.group(1)}">{m.group(1)}</a>', out)
    return out


def english(t: str, p: dict) -> str:
    """A template as a sentence a person would write."""
    c = lambda k: f"<code>{_e(p.get(k, ''))}</code>"
    return {
        "co_change": f"When a file matching {c('trigger')} changes, something in {c('required')} must change in the same commit.",
        "forbidden_edit": f"Files matching {c('glob')} must never be edited.",
        "must_not_appear": f"No line added to {c('glob')} may match {c('regex')}.",
        "must_not_remove": f"No line removed from {c('glob')} may match {c('regex')}.",
        "must_appear": f"Every changed file matching {c('glob')} must contain {c('regex')}.",
        "must_run": f"After changing {c('glob')}, {c('cmd')} must have been run.",
    }.get(t, f"<code>{_e(templates.render(t, p))}</code>")


def _why_and_next(r: dict, suggested: set) -> tuple[str, str]:
    """The reason in plain words, and the one thing worth doing about it."""
    reason = r.get("reason") or ""
    m = re.match(r"held on all (\d+) past commits", reason)
    if r["status"] == "enforced":
        n = m.group(1) if m else "the"
        return (f"All {n} past commits we could check it against followed it.",
                "Once adopted, an agent that breaks this is stopped before the edit lands.")
    if r["status"] == "checkable":
        if r.get("broken_by"):
            k = len(r["broken_by"])
            return (f"{k} of your past commits broke it, so it cannot block yet without blocking work that already shipped.",
                    "If those commits did it on purpose, narrow the rule (for example, allow the generator); "
                    "otherwise keep it as guidance.")
        if "matches no file" in reason:
            return ("It names files that do not exist in this repository.",
                    "Fix the path in the sentence, then run coverage again.")
        return ("None of your past commits could test it: it depends on commands an agent ran, which git does not record.",
                "It can start guarding once Injunct has watched agent sessions in this repository.")
    kind, _, detail = reason.partition(":")
    plain = KIND.get(kind.strip(), "no check can express it")
    nxt = ("A rewrite that could be guarded is suggested above."
           if (r["doc"], r["line"]) in suggested else "Keep it as guidance for people and agents, or put it on a review checklist.")
    return (f"No automatic check can enforce this: {plain}." + (f" {_e(detail.strip())}" if detail.strip() else ""), nxt)


def _card(r: dict, gh: str | None, suggested: set) -> str:
    why, nxt = _why_and_next(r, suggested)
    plain = f'<div class="plain">{english(r["template"], r["params"])}</div>' if r.get("template") else ""
    rule = (f'<details class="rule"><summary>show the rule</summary><code>'
            f'{_e(templates.render(r["template"], r["params"]))}</code></details>') if r.get("template") else ""
    broke = ""
    if r.get("broken_by"):
        items = "".join(f"<li>{_commits(c.removeprefix('commit '), gh)}</li>" for c in r["broken_by"][:5])
        broke = f'<ul class="broke">{items}</ul>'
    return (f'<div class="card" id="{_anchor(r["doc"], r["line"])}"><div class="top"><div class="text">'
            f'<span class="stamp {STAMP_CLASS[r["status"]]}">{NAME[r["status"]].upper()}</span>{_md(r["text"])}</div>'
            f'<div class="where">{_e(r["doc"])} line {r["line"]}</div></div>{plain}'
            f'<div class="why">{why}</div>{broke}<div class="next"><b>Next:</b> {nxt}</div>{rule}</div>')


def _doc_view(doc: str, text: str, rules: list[dict]) -> str:
    """The document itself, each instruction coloured by what Injunct can do with it."""
    starts = {r["line"]: r for r in rules if r["doc"] == doc}
    rows, current, fence = [], None, False
    for i, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            fence = not fence
        if i in starts:
            current = starts[i]
        elif not stripped or fence or stripped.startswith(("#", "-", "*", "+", "|")) or re.match(r"\d+[.)]\s", stripped):
            current = None                                  # a new block starts; the instruction above has ended
        if current is not None:
            rows.append(f'<a class="ln {LINE_CLASS[current["status"]]}" href="#{_anchor(doc, current["line"])}" '
                        f'title="{NAME[current["status"]]}: click for details"><i>{i}</i><span>{_e(raw) or " "}</span></a>')
        else:
            rows.append(f'<div class="ln"><i>{i}</i><span>{_e(raw) or " "}</span></div>')
    return f'<details class="doc" open><summary>{_e(doc)}</summary>{"".join(rows)}</details>'


def render(s: dict) -> str:
    n = s["total"] or 1
    e, c, u = s["enforced"], s["checkable"], s["unchecked"]
    gh = s.get("github")
    sugs = s.get("suggestions") or []
    suggested = {(g["doc"], g["line"]) for g in sugs}
    plural = lambda k, w: f"{k} {w}{'' if k == 1 else 's'}"

    lede = (f"<b>{e} of your {s['total']} instructions {'is' if e == 1 else 'are'} guarded</b>: if an agent breaks "
            f"{'it' if e == 1 else 'one'}, Injunct stops the edit before it lands. "
            f"{c} could be guarded but {'is' if c == 1 else 'are'} not proven yet, and {u} need{'s' if u == 1 else ''} "
            f"a human, because no automatic check can express {'it' if u == 1 else 'them'}.")
    then = (f'<div class="then">&rarr; {s["percent_if_rewritten"]}% with {plural(len(sugs), "suggested rewrite")}</div>'
            if sugs else "")

    todo = []
    if e:
        todo.append(f"<b>Turn on the {plural(e, 'guarded rule')}.</b> Run <code>injunct coverage . --adopt</code>, "
                    "and an agent that breaks one is stopped before the write lands.")
    if sugs:
        todo.append(f"<b>Read the {plural(len(sugs), 'suggested rewrite')}.</b> Each would be guarded today; "
                    "keep the ones that still say what you meant.")
    broken = [r for r in s["rules"] if r["status"] == "checkable" and r.get("broken_by")]
    if broken:
        todo.append(f"<b>Look at the {plural(len(broken), 'rule')} your own history breaks.</b> "
                    "Either the rule is too strict or the habit is real; each card names the commits.")
    if u:
        todo.append(f"<b>Keep the {plural(u, 'instruction')} that need{'s' if u == 1 else ''} a human</b> as guidance; "
                    "no tool will ever enforce taste or process.")

    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Injunct coverage</title><style>{CSS}</style></head><body><main>
<header><h1>Your agent instructions, checked</h1>
<p>{_e(_name(s["repo"]))} &middot; {_e(", ".join(s["docs"]) or "no agent documents found")}</p></header>
<div class="big"><div class="pct">{s["percent"]}%<small>guarded</small></div>{then}</div>
<p class="lede">{lede}</p>
<div class="bar" role="img" aria-label="{e} guarded, {c} could be guarded, {u} need a human">
<span class="b-ok" style="width:{100 * e / n:.1f}%"></span><span class="b-warn" style="width:{100 * c / n:.1f}%"></span></div>
<div class="legend"><span><i class="dot d-ok"></i>Guarded: stops an agent today</span>
<span><i class="dot d-warn"></i>Could be guarded: not proven yet</span>
<span><i class="dot d-off"></i>Needs a human: no check can express it</span></div>"""]

    if todo:
        parts.append('<div class="todo"><h2>What you can do now</h2><ol>'
                     + "".join(f"<li>{t}</li>" for t in todo) + "</ol></div>")

    if s.get("documents"):
        parts.append("<h2>Your documents, colour-coded <small>&middot; click an instruction for details</small></h2>")
        for doc, text in s["documents"].items():
            parts.append(_doc_view(doc, text, s["rules"]))

    if sugs:
        parts.append("<h2>Suggested rewrites <small>&middot; each would be guarded today</small></h2>")
        parts.append('<p class="why">Proposed by the model and checked against your history: none would have '
                     "blocked work that already shipped. The check cannot tell you a rewrite still says what you "
                     "meant, so read each one before adopting it.</p>")
        for g in sugs:
            parts.append(f'<div class="card sug"><div class="top"><div class="was">{_md(g["was"])}</div>'
                         f'<div class="where">{_e(g["doc"])} line {g["line"]}</div></div>'
                         f'<div class="now">{_md(g["rewrite"])}</div><div class="plain">{english(g["template"], g["params"])}</div>'
                         f'<div class="why">All {g["held"]} past commits we could check it against followed it.</div></div>')

    for k in NAME:
        rows = [r for r in s["rules"] if r["status"] == k]
        if rows:
            parts.append(f"<h2>{NAME[k]} ({len(rows)})</h2>")
            parts += [_card(r, gh, suggested) for r in rows]

    if s.get("discounted"):
        parts.append("<h2>Commits we did not count</h2>")
        parts.append('<p class="why">These commits introduced a problem that a later commit had to fix, so they are '
                     "not counted as examples of good work when a rule is checked against your history.</p>")
        for d in s["discounted"]:
            parts.append(f'<div class="card"><div class="text">{_commits(d["commit"], gh)}</div>'
                         f'<div class="why">fixed later by {_commits(d["fixed_by"], gh)}</div></div>')

    warn = (f"<p><b>{s['model_failures']} instruction(s) got no answer from the model,</b> so this number is a "
            "floor, not a measurement.</p>") if s.get("model_failed") else ""
    parts.append(f"""<details class="how"><summary>How this works</summary>
<p>Injunct reads the documents your agents are given and finds every sentence that sounds like an instruction.
A model ({_e(s["model"])}) sorts each one: either it can be written as one of six simple checks on a commit,
or it cannot, and it says why. Then each check is replayed against this repository's own past commits.
A check that every past commit already followed is <b>guarded</b>: it can stop an agent without ever
blocking work that already shipped. Nothing the model wrote is ever run.</p></details>
<footer>{warn}<p>injunct &middot; {time.strftime("%d %b %Y %H:%M")}</p></footer>
</main></body></html>""")
    return "\n".join(parts)
