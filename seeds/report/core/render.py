"""One row of a report, as a line of text.

Three view modules call this. That is the whole point of the fixture: changing
the shape of render() is only finished when its callers move too.
"""

COLUMNS = ("id", "name", "total")


def render(row):
    return " | ".join(str(row.get(c, "")) for c in COLUMNS)
