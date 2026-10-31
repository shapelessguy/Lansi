# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The checks of sentences a user has had made, kept between runs.

What a model answered about a sentence is kept under what was asked, so
that the same question about the same sentence, asked of the same model,
is answered from here rather than paid for again. Each sentence is kept
under the source it was written in, exercises or anything else, and each
source keeps as many sentences as its limit allows: once it has more, the
sentence used longest ago is forgotten, with everything kept about it.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

EXERCISES = "exercises"
REST = "rest"
# how many sentences each source keeps
LIMITS = {EXERCISES: 5000, REST: 2500}

# A sentence's wording, the model asked with the language the sentence is
# judged by, and the name and content of what was asked about it.
Key = tuple[str, str, str, str]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sentences (
    source TEXT NOT NULL,
    sentence TEXT NOT NULL,
    -- higher for a sentence used more lately
    used INTEGER NOT NULL,
    PRIMARY KEY (source, sentence)
);
CREATE INDEX IF NOT EXISTS sentences_used ON sentences (source, used);
CREATE TABLE IF NOT EXISTS checks (
    source TEXT NOT NULL,
    sentence TEXT NOT NULL,
    model TEXT NOT NULL,
    name TEXT NOT NULL,
    content TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (sentence, model, name, content, source)
);
CREATE INDEX IF NOT EXISTS checks_of ON checks (source, sentence);
"""


class CheckCache:
    """The checks kept in the SQLite database at `path`, made when first
    needed. It may be used from several threads at once."""

    def __init__(self, path: Path, limits: dict[str, int] | None = None) -> None:
        self._path = path
        self._limits = LIMITS if limits is None else limits
        self._base: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def get(self, key: Key) -> Any | None:
        """What was kept under `key`, from whichever source it was kept in,
        or None. Each source that has the sentence counts it as used now."""
        with self._lock:
            base = self._open()
            row = base.execute(
                "SELECT value FROM checks"
                " WHERE sentence = ? AND model = ? AND name = ? AND content = ?"
                " LIMIT 1",
                key,
            ).fetchone()
            if row is None:
                return None
            with base:
                base.execute(
                    "UPDATE sentences SET used = ? WHERE sentence = ?",
                    (self._next_use(base), key[0]),
                )
            return json.loads(row[0])

    def put(self, key: Key, source: str, value: Any) -> None:
        """Keep `value`, anything JSON can hold, under `key` for `source`,
        and forget the sentences of the source used longest ago if it now
        has more than it may keep. A source with no limit is taken as the
        rest."""
        if source not in self._limits:
            source = REST
        with self._lock:
            base = self._open()
            with base:
                base.execute(
                    "INSERT INTO sentences (source, sentence, used) VALUES (?, ?, ?)"
                    " ON CONFLICT DO UPDATE SET used = excluded.used",
                    (source, key[0], self._next_use(base)),
                )
                base.execute(
                    "INSERT OR REPLACE INTO checks"
                    " (sentence, model, name, content, source, value)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (*key, source, json.dumps(value)),
                )
                self._forget_beyond(base, source)

    def count(self, source: str) -> int:
        """How many sentences `source` keeps."""
        with self._lock:
            row = (
                self._open()
                .execute("SELECT COUNT(*) FROM sentences WHERE source = ?", (source,))
                .fetchone()
            )
            return int(row[0])

    def _open(self) -> sqlite3.Connection:
        if self._base is None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            base = sqlite3.connect(str(self._path), check_same_thread=False, timeout=5)
            base.executescript(_SCHEMA)
            self._base = base
        return self._base

    def _next_use(self, base: sqlite3.Connection) -> int:
        row = base.execute(
            "SELECT COALESCE(MAX(used), 0) + 1 FROM sentences"
        ).fetchone()
        return int(row[0])

    def _forget_beyond(self, base: sqlite3.Connection, source: str) -> None:
        stale = base.execute(
            "SELECT sentence FROM sentences WHERE source = ?"
            " ORDER BY used DESC LIMIT -1 OFFSET ?",
            (source, self._limits[source]),
        ).fetchall()
        for (sentence,) in stale:
            base.execute(
                "DELETE FROM sentences WHERE source = ? AND sentence = ?",
                (source, sentence),
            )
            base.execute(
                "DELETE FROM checks WHERE source = ? AND sentence = ?",
                (source, sentence),
            )
