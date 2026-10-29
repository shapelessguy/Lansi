# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The databases of the notes of the tutor.

Each note the tutor writes has a SQLite database of its own besides its
title and what it says, in which it keeps what it works on as tables, such
as the words its exercises used and how often, and which it reads and
changes with SQL, a statement at a time, rather than writing all of it
again. A database is made when the tutor first writes in it.

A statement reaches nothing but its own database: it cannot attach
another, nor change how SQLite runs with a pragma, nor hold a transaction
open; each statement is kept as soon as it is run. One that runs too long
is stopped. What a query gives is not cut, but given a page at a time.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

# how many rows of what a query gives are given at once
PAGE_ROWS = 500
# how long a statement may run before it is stopped
QUERY_SECS = 10.0

_DENIED = {
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_DETACH,
    sqlite3.SQLITE_PRAGMA,
    sqlite3.SQLITE_TRANSACTION,
    sqlite3.SQLITE_SAVEPOINT,
    sqlite3.SQLITE_CREATE_VTABLE,
    sqlite3.SQLITE_DROP_VTABLE,
}


class NoteError(Exception):
    """A statement could not be run on the database of a note; the message
    says why, for the tutor to correct it."""


def _authorized(action: int, *_: object) -> int:
    return sqlite3.SQLITE_DENY if action in _DENIED else sqlite3.SQLITE_OK


def run(path: Path, query: str, offset: int = 0) -> dict[str, Any]:
    """Run one SQL statement on the database at `path`. What a query gives
    is its columns and its rows from `offset`, as many as PAGE_ROWS, with
    how many there are in all; what another statement gives is how many
    rows it changed. Raises NoteError."""
    if not query.strip():
        raise NoteError("the query is an SQL statement")
    base = sqlite3.connect(str(path), isolation_level=None, timeout=5)
    try:
        base.set_authorizer(_authorized)
        until = time.monotonic() + QUERY_SECS
        base.set_progress_handler(lambda: time.monotonic() > until, 10_000)
        try:
            cursor = base.execute(query)
            if cursor.description is None:
                return {"changed": max(cursor.rowcount, 0)}
            rows = cursor.fetchall()
        except sqlite3.OperationalError as error:
            if str(error) == "interrupted":
                raise NoteError(
                    f"the statement ran longer than {QUERY_SECS:g} seconds"
                ) from None
            raise NoteError(str(error)) from None
        except (sqlite3.Error, ValueError) as error:
            raise NoteError(str(error)) from None
    finally:
        base.close()
    page = rows[offset : offset + PAGE_ROWS]
    given: dict[str, Any] = {
        "columns": [column[0] for column in cursor.description],
        "rows": [[_value(value) for value in row] for row in page],
        "total": len(rows),
    }
    if offset + len(page) < len(rows):
        given["more"] = len(rows) - offset - len(page)
        given["next_offset"] = offset + len(page)
    return given


def tables(path: Path) -> list[dict[str, Any]]:
    """The tables of the database at `path`, each with its columns and how
    many rows it has; none if it was not made yet."""
    if not path.exists():
        return []
    base = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        names = [
            name
            for (name,) in base.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
                " AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        quoted = {name: '"' + name.replace('"', '""') + '"' for name in names}
        return [
            {
                "name": name,
                "columns": [
                    {"name": column, "type": kind}
                    for (_, column, kind, *_) in base.execute(
                        "SELECT * FROM pragma_table_info(?)", (name,)
                    )
                ],
                "rows": base.execute(f"SELECT count(*) FROM {quoted[name]}").fetchone()[
                    0
                ],
            }
            for name in names
        ]
    finally:
        base.close()


def _value(value: object) -> object:
    """A value of a row as JSON can give it."""
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value
