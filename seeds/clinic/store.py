"""The database is whatever the migrations say it is. Nothing else builds it."""
import sqlite3
from pathlib import Path

HERE = Path(__file__).parent


def build(path=":memory:"):
    con = sqlite3.connect(path)
    for sql in sorted((HERE / "migrations").glob("*.sql")):
        con.executescript(sql.read_text(encoding="utf-8"))
    con.commit()
    return con


def patients(con, fields):
    cur = con.execute(f"SELECT {', '.join(fields)} FROM patients ORDER BY id")
    return [dict(zip(fields, row)) for row in cur.fetchall()]
