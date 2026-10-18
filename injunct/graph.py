"""What else in this repository depends on what the agent just changed.

A path-based rule asks "did the other directory move". This asks a semantic
question instead: you changed the shape of a function, and fourteen places call
it. Did you update them?

Everything here is `ast` and the standard library. No model, no index server,
no network - the graph is rebuilt from source on every check, which is fast
enough at repository scale and never goes stale.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

SKIP = {".git", "__pycache__", ".injunct", "node_modules", ".venv", "venv", "dist", "build"}


def _py_files(repo: Path) -> list[Path]:
    return [p for p in repo.rglob("*.py")
            if not any(part in SKIP for part in p.parts)]


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    a = node.args
    names = [x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    if a.vararg:
        names.append("*" + a.vararg.arg)
    if a.kwarg:
        names.append("**" + a.kwarg.arg)
    return f"{node.name}({', '.join(names)})"


def signatures(text: str) -> dict[str, str]:
    """name -> rendered signature, for one source file."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = _signature(node)
    return out


def callers(repo: Path, name: str, exclude: set[str]) -> list[str]:
    """Every file that calls `name`, other than the ones already changed."""
    repo = Path(repo)
    hits = []
    for f in _py_files(repo):
        rel = f.relative_to(repo).as_posix()
        if rel in exclude:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if name not in text:                     # cheap reject before parsing
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            called = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if called == name:
                hits.append(rel)
                break
    return sorted(set(hits))


def changed_signatures(ch) -> dict[str, tuple[str, str]]:
    """Functions whose parameter list changed in this diff.

    Read off the added and removed lines: a renamed parameter, an added one or
    a removed one all show up as the same `def` line leaving and a different
    one arriving.
    """
    out: dict[str, tuple[str, str]] = {}
    pat = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
    for path in ch.touched:
        if not path.endswith(".py"):
            continue
        gone = {m.group(1): line.strip()
                for line in (ch.removed or {}).get(path, []) if (m := pat.match(line))}
        came = {m.group(1): line.strip()
                for line in ch.added.get(path, []) if (m := pat.match(line))}
        for name, before in gone.items():
            after = came.get(name)
            if after and after != before:
                out[name] = (before, after)
    return out
