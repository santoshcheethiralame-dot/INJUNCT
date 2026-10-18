"""The coverage report as one self-contained page.

    injunct coverage . --html coverage.html

No scripts, no fonts, no network: it has to open from a file, inside an agent
app's side panel, on a judge's laptop with the wifi off. Light and dark follow
the viewer's system setting.
"""
from __future__ import annotations

import html
import re
import time

from . import templates

CSS = """
:root{--bg:#fbfaf7;--fg:#1c1b19;--dim:#6b6860;--line:#e6e2d9;--card:#ffffff;
--ok:#1f7a4d;--ok-bg:#e6f4ec;--warn:#9a5b00;--warn-bg:#fdf1dc;--off:#5f5d57;--off-bg:#efede8;
--accent:#3b4cca}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--fg:#ecebe7;--dim:#9b988f;--line:#2c2b28;
--card:#1d1c1a;--ok:#5fd19a;--ok-bg:#16301f;--warn:#f0b35a;--warn-bg:#33270f;--off:#b3b0a8;
--off-bg:#262522;--accent:#93a0ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:920px;margin:0 auto;padding:32px 16px 64px}
header p{margin:.2rem 0;color:var(--dim)}h1{font-size:1.05rem;margin:0 0 .2rem;font-weight:600}
.big{display:flex;gap:28px;align-items:flex-end;flex-wrap:wrap;margin:28px 0 12px}
.pct{font-size:4.2rem;font-weight:700;line-height:1;letter-spacing:-.03em}
.pct small{font-size:1rem;font-weight:500;color:var(--dim);letter-spacing:0;margin-left:.4rem}
.then{color:var(--accent);font-weight:600}
.bar{display:flex;height:12px;border-radius:6px;overflow:hidden;background:var(--off-bg);margin:8px 0 6px}
.bar span{display:block}.b-ok{background:var(--ok)}.b-warn{background:var(--warn)}
.legend{display:flex;gap:18px;flex-wrap:wrap;color:var(--dim);font-size:.9rem}
.legend b{color:var(--fg)}
h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.08em;color:var(--dim);margin:40px 0 12px;font-weight:600}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:10px 0}
.card .top{display:flex;gap:10px;align-items:baseline;justify-content:space-between;flex-wrap:wrap}
.text{font-weight:500}.where{color:var(--dim);font-size:.85rem;white-space:nowrap}
.stamp{display:inline-block;font-size:.72rem;font-weight:700;letter-spacing:.06em;padding:2px 8px;
border-radius:999px;margin-right:8px;vertical-align:2px}
.s-ok{color:var(--ok);background:var(--ok-bg)}.s-warn{color:var(--warn);background:var(--warn-bg)}
.s-off{color:var(--off);background:var(--off-bg)}
code,.rule{font:13px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace}
.rule{display:block;margin-top:8px;color:var(--fg);overflow-wrap:anywhere}
.why{color:var(--dim);font-size:.9rem;margin-top:6px}
ul.broke{margin:6px 0 0;padding-left:18px;color:var(--warn);font-size:.88rem}
.fixed{border-left:3px solid var(--accent)}
.sug .was{color:var(--dim);text-decoration:line-through;text-decoration-color:var(--line)}
.sug .now{font-weight:600;margin-top:4px}
footer{margin-top:48px;color:var(--dim);font-size:.85rem;border-top:1px solid var(--line);padding-top:16px}
"""

STAMP = {"enforced": ("ENFORCED", "s-ok"), "checkable": ("CHECKABLE", "s-warn"), "unchecked": ("UNCHECKED", "s-off")}


def _e(s) -> str:
    return html.escape(str(s), quote=True)


def _md(s) -> str:
    """Instruction text as written: escaped, with its `backticks` shown as code."""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", _e(s))


def _card(r: dict) -> str:
    label, cls = STAMP[r["status"]]
    rule = (f'<code class="rule">{_e(templates.render(r["template"], r["params"]))}</code>'
            if r.get("template") else "")
    broke = ""
    if r.get("broken_by"):
        items = "".join(f"<li>{_e(c)}</li>" for c in r["broken_by"][:5])
        broke = f'<ul class="broke">{items}</ul>'
    return (f'<div class="card"><div class="top"><div class="text"><span class="stamp {cls}">{label}</span>'
            f'{_md(r["text"])}</div><div class="where">{_e(r["doc"])}:{r["line"]}</div></div>'
            f'{rule}<div class="why">{_e(r.get("reason") or "")}</div>{broke}</div>')


def render(s: dict) -> str:
    n = s["total"] or 1
    ok, warn = 100 * s["enforced"] / n, 100 * s["checkable"] / n
    sugs = s.get("suggestions") or []
    then = (f'<div class="then">{s["percent_if_rewritten"]}% with {len(sugs)} rewrite'
            f'{"s" if len(sugs) != 1 else ""}</div>') if sugs else ""
    groups = {k: [r for r in s["rules"] if r["status"] == k] for k in STAMP}

    parts = [f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Injunct coverage</title><style>{CSS}</style></head><body><main>
<header><h1>Is this repository's agent guidance enforced?</h1>
<p>{_e(s["repo"])}</p><p>{_e(", ".join(s["docs"]) or "no agent documents found")}</p></header>
<div class="big"><div class="pct">{s["percent"]}%<small>enforced</small></div>{then}</div>
<div class="bar" role="img" aria-label="{s['enforced']} enforced, {s['checkable']} checkable, {s['unchecked']} unchecked">
<span class="b-ok" style="width:{ok:.1f}%"></span><span class="b-warn" style="width:{warn:.1f}%"></span></div>
<div class="legend"><span><b>{s["enforced"]}</b> enforced: proven on this history, blocks today</span>
<span><b>{s["checkable"]}</b> checkable: compiles, not yet proven</span>
<span><b>{s["unchecked"]}</b> unchecked: no check can express it</span></div>"""]

    if sugs:
        parts.append("<h2>Rewrite these and they would be enforced today</h2>")
        parts.append('<p class="why">Proposed by the model and proven against this history: none would have '
                     'blocked work that already shipped. The proof cannot tell you the rewrite still says what '
                     'you meant, so read each one before adopting it.</p>')
        for g in sugs:
            parts.append(f'<div class="card sug"><div class="top"><div class="was">{_md(g["was"])}</div>'
                         f'<div class="where">{_e(g["doc"])}:{g["line"]}</div></div>'
                         f'<div class="now">{_md(g["rewrite"])}</div>'
                         f'<code class="rule">{_e(templates.render(g["template"], g["params"]))}</code>'
                         f'<div class="why">held on all {g["held"]} past commits that could test it</div></div>')

    if s.get("discounted"):
        parts.append("<h2>Left out of the proof: a later commit had to fix these</h2>")
        for d in s["discounted"]:
            parts.append(f'<div class="card fixed"><div class="text"><code>{_e(d["commit"])}</code></div>'
                         f'<div class="why">fixed by <code>{_e(d["fixed_by"])}</code></div></div>')

    titles = {"enforced": "Enforced", "checkable": "Checkable, not yet proven", "unchecked": "Unchecked"}
    for k, rows in groups.items():
        if rows:
            parts.append(f"<h2>{titles[k]} ({len(rows)})</h2>")
            parts += [_card(r) for r in rows]

    warn_line = (f"<p><b>{s['model_failures']} instruction(s) got no answer from the model;</b> "
                 "this number is a floor, not a measurement.</p>") if s.get("model_failed") else ""
    parts.append(f"""<footer>{warn_line}<p>Candidate sentences come from the documents themselves.
The model ({_e(s["model"])}) only sorts each one into a template or a reason it cannot be checked;
whether a rule binds is decided by replaying it against this repository's own commits.
Nothing the model wrote was executed.</p><p>injunct · {time.strftime("%d %b %Y %H:%M")}</p></footer>
</main></body></html>""")
    return "\n".join(parts)
