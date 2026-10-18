"""The long view: the same lines, numbered."""
from core.render import render


def detail(rows):
    return [f"{i + 1}. {render(r)}" for i, r in enumerate(rows)]
