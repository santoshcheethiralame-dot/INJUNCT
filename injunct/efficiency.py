"""Cost regressions that can be seen without running anything.

Sleeper measures what a function actually costs by timing it at growing input
sizes, which is the right way to check a CLAIM. This is the cheaper, narrower
question: did the change introduce a shape that is known to be quadratic, when
nothing was quadratic before?

Only added code is examined, and every finding names the line, because "this is
slow" is not actionable and "line 42 does a list lookup inside a loop" is.
"""
from __future__ import annotations

import ast

QUERY_HINTS = ("query", "get", "fetch", "find", "select", "filter", "execute", "all")


def _loop_targets(node: ast.For) -> set[str]:
    t = node.target
    if isinstance(t, ast.Name):
        return {t.id}
    return {e.id for e in ast.walk(t) if isinstance(e, ast.Name)}


def _iter_name(node: ast.For) -> str | None:
    it = node.iter
    if isinstance(it, ast.Name):
        return it.id
    if isinstance(it, ast.Call) and isinstance(it.func, ast.Name):
        return None
    return None


def findings(source: str) -> list[str]:
    """Every quadratic-shaped thing in this source, one line each."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.For):
            continue
        outer_iter = _iter_name(node)

        for inner in ast.walk(node):
            # nested loop over the same collection -> n^2 over one input
            if isinstance(inner, ast.For) and inner is not node:
                if outer_iter and _iter_name(inner) == outer_iter:
                    out.append(f"line {inner.lineno}: nested loop over `{outer_iter}` "
                               f"is quadratic in one collection")

            # membership test against a list inside a loop -> n^2
            if isinstance(inner, ast.Compare) and any(
                    isinstance(o, ast.In) for o in inner.ops):
                right = inner.comparators[0] if inner.comparators else None
                if isinstance(right, ast.List):
                    out.append(f"line {inner.lineno}: `in` against a list inside a loop; "
                               f"a set is O(1)")
                elif isinstance(right, ast.Name) and right.id != outer_iter:
                    out.append(f"line {inner.lineno}: `in {right.id}` inside a loop is "
                               f"O(n) each time; use a set if {right.id} is a list")

            # string built by repeated concatenation -> quadratic copying
            if isinstance(inner, ast.AugAssign) and isinstance(inner.op, ast.Add):
                if isinstance(inner.value, ast.Constant) and \
                        isinstance(inner.value.value, str):
                    out.append(f"line {inner.lineno}: string built by += in a loop; "
                               f"collect and join instead")

            # a query inside a loop -> the N+1 problem
            if isinstance(inner, ast.Call):
                fn = inner.func
                called = getattr(fn, "attr", None) or getattr(fn, "id", None) or ""
                if any(h == called.lower() for h in QUERY_HINTS) and \
                        isinstance(fn, ast.Attribute):
                    out.append(f"line {inner.lineno}: `{called}()` called inside a loop "
                               f"- N+1 queries; fetch once outside")

    seen, unique = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return unique
