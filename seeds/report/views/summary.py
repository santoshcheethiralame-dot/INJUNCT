"""The short view: one line per row."""
from core.render import render


def summary(rows):
    return [render(r) for r in rows]
