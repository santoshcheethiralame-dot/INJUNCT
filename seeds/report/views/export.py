"""The file view: the same lines, joined."""
from core.render import render


def export(rows):
    return "\n".join(render(r) for r in rows)
