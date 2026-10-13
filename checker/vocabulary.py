# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The vocabulary: every word that was taken in, stored once per category
under its dictionary form, with all the forms it can be met in.

Entries and forms each have a number of their own that never changes, for
whatever is kept about them later, such as how often a word or one of its
forms was used, to refer to. What is known about an entry beyond its forms
is kept as JSON, so that more can be added without changing the tables.
"""

from __future__ import annotations

import difflib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Raised with every change to the tables, so that a file written by an older
# version can be told and brought up to date.
SCHEMA_VERSION = 4

# What each version added to the one before it, from the first on.
_SCHEMA_STEPS = [
    """
CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    category TEXT NOT NULL,
    -- the dictionary form, written as it is in a dictionary
    lemma TEXT NOT NULL,
    -- what else is known about the word, as a JSON object
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (category, lemma)
);
CREATE TABLE forms (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    form TEXT NOT NULL,
    -- the form in small letters, which is what words are looked up by
    folded TEXT NOT NULL,
    -- which form it is, such as "präsens 1sg". One spelling can be several.
    tags TEXT NOT NULL DEFAULT '',
    UNIQUE (entry_id, form, tags)
);
CREATE INDEX forms_folded ON forms (folded);
-- words that were found not to belong in a category, so as not to ask again
CREATE TABLE rejected (
    category TEXT NOT NULL,
    folded TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    -- the category the word was found to be of instead, if it is a word
    belongs_to TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (category, folded)
);
""",
    """
-- Words that came on their own and were taken in, with what became of them,
-- so that whoever brings words in lots can tell which are still to come.
CREATE TABLE taken (
    folded TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    taken_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""",
    """
-- Every time a stored word was used, one row for each time, so that how
-- often and when can be worked out in any way that is wanted later.
CREATE TABLE uses (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    -- the form that was used, in small letters
    form TEXT NOT NULL,
    -- "user" if the learner wrote it, "assistant" if a model did
    role TEXT NOT NULL,
    -- where it was used: in a "message" of a chat, or in a "text"
    source TEXT NOT NULL,
    -- the id of the chat or the text
    source_id TEXT NOT NULL,
    -- which message of the chat, from 0
    position INTEGER NOT NULL DEFAULT 0,
    -- when, in seconds since the epoch
    used_at REAL NOT NULL
);
CREATE INDEX uses_entry ON uses (entry_id);
CREATE INDEX uses_source ON uses (source, source_id, position);
""",
    """
-- Sets of words picked out of the vocabulary, to be given to a model. What
-- makes a word one of a set is kept as the app describes it, in JSON: the
-- rule that words are picked by, and the words put in or taken out by hand.
CREATE TABLE sets (
    id TEXT PRIMARY KEY,
    body TEXT NOT NULL
);
""",
]


_WORD = re.compile(r"[^\W\d_]+")


def _words_after(folded: str, sentence: str) -> set[str]:
    """The words of a sentence that come after the first time `folded` is in
    it, in small letters."""
    words = [fold(word) for word in _WORD.findall(sentence)]
    if folded not in words:
        return set()
    return set(words[words.index(folded) + 1 :])


def _escaped(text: str) -> str:
    """A text to be found as it is by LIKE, with `!` as the escape."""
    return re.sub(r"([!%_])", r"!\1", text)


def fold(word: str) -> str:
    """A word as it is looked up: in small letters. Not casefold(), which
    would take "Maße" and "Masse" for the same word."""
    return word.strip().lower()


@dataclass
class Form:
    form: str
    # which form of the word it is, if that is known
    tags: str = ""
    id: int = 0


@dataclass
class Entry:
    id: int
    category: str
    lemma: str
    details: dict[str, Any] = field(default_factory=dict)
    forms: list[Form] = field(default_factory=list)
    # when it was stored, in UTC
    created_at: str = ""


@dataclass
class Listed:
    """A stored word as it is listed: without what is known about it."""

    id: int
    category: str
    lemma: str
    # when it was stored, in UTC
    created_at: str
    # how many forms it is stored with
    forms: int
    # how often the learner used it, and how often a model did
    used: int = 0
    seen: int = 0
    # when it was first and last used by either, in seconds since the epoch
    first_used: float | None = None
    last_used: float | None = None


@dataclass
class Rejection:
    """Why a word does not belong in a category."""

    reason: str
    # the category it was found to be of instead, if it is a word at all
    belongs_to: str = ""


class Vocabulary:
    """The stored words, in an SQLite file, or in memory if no path is
    given. It can be used from several threads."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        with self._lock, self._db:
            (version,) = self._db.execute("PRAGMA user_version").fetchone()
            for step in _SCHEMA_STEPS[version:]:
                self._db.executescript(step)
            self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._db.close()

    def find(self, category: str, word: str, sentence: str = "") -> Entry | None:
        """The entry of `category` that `word` is a form of, if there is
        one. Should it be a form of several, the one it is the dictionary
        form of is preferred, and then the one stored first.

        A separable verb comes apart in a sentence: "Der Film fängt abends
        an." So a word that is the first part of a stored form in two parts,
        such as "fängt an", is that form if the other part comes later in
        the `sentence` it was used in."""
        folded = fold(word)
        with self._lock:
            row = self._db.execute(
                "SELECT entries.id FROM forms"
                " JOIN entries ON entries.id = forms.entry_id"
                " WHERE entries.category = ? AND forms.folded = ?"
                " ORDER BY lower(entries.lemma) = ? DESC, entries.id LIMIT 1",
                (category, folded, folded),
            ).fetchone()
            if row:
                return self._entry(row[0])
            later = _words_after(folded, sentence)
            if not later:
                return None
            in_two_parts = self._db.execute(
                "SELECT entries.id, forms.folded FROM forms"
                " JOIN entries ON entries.id = forms.entry_id"
                " WHERE entries.category = ? AND forms.folded LIKE ? ESCAPE '!'"
                " ORDER BY entries.id",
                (category, _escaped(folded) + " %"),
            ).fetchall()
            for entry_id, stored in in_two_parts:
                parts = stored.split()
                if len(parts) == 2 and parts[1] in later:  # noqa: PLR2004
                    return self._entry(entry_id)
            return None

    def entry(self, category: str, lemma: str) -> Entry | None:
        """The entry stored under exactly this dictionary form."""
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM entries WHERE category = ? AND lemma = ?",
                (category, lemma),
            ).fetchone()
            return self._entry(row[0]) if row else None

    def get(self, entry_id: int) -> Entry | None:
        """The entry with this number, with all that is stored of it."""
        with self._lock:
            row = self._db.execute(
                "SELECT id FROM entries WHERE id = ?", (entry_id,)
            ).fetchone()
            return self._entry(row[0]) if row else None

    def listing(self) -> list[Listed]:
        """Every stored word, by category and then by the alphabet."""
        with self._lock:
            rows = self._db.execute(
                "SELECT entries.id, category, lemma, entries.created_at,"
                " COUNT(forms.id) FROM entries"
                " LEFT JOIN forms ON forms.entry_id = entries.id"
                " GROUP BY entries.id"
            ).fetchall()
            uses = {
                entry_id: counted
                for entry_id, *counted in self._db.execute(
                    "SELECT entry_id, SUM(role = 'user'), SUM(role <> 'user'),"
                    " MIN(used_at), MAX(used_at) FROM uses GROUP BY entry_id"
                )
            }
        listed = [Listed(*row, *uses.get(row[0], ())) for row in rows]
        return sorted(listed, key=lambda word: (word.category, fold(word.lemma)))

    def record_uses(
        self,
        source: str,
        source_id: str,
        position: int,
        role: str,
        used_at: float,
        uses: list[tuple[int, str]],
    ) -> None:
        """Record that words were used in one place: a message of a chat, or
        a text. `uses` has the entry of each word with the form that was
        used, once for every time it was. What was recorded for the place
        before is replaced, so that a message that is processed again is
        not counted twice."""
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM uses WHERE source = ? AND source_id = ? AND position = ?",
                (source, source_id, position),
            )
            self._db.executemany(
                "INSERT INTO uses"
                " (entry_id, form, role, source, source_id, position, used_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (entry_id, form, role, source, source_id, position, used_at)
                    for entry_id, form in uses
                ],
            )

    def sets(self) -> list[dict[str, Any]]:
        """The sets of words, as the app keeps them."""
        with self._lock:
            rows = self._db.execute("SELECT body FROM sets ORDER BY rowid").fetchall()
        return [json.loads(body) for (body,) in rows]

    def save_set(self, set_id: str, body: dict[str, Any]) -> None:
        """Keep a set as it is now. Raises ValueError for one that has no
        name, or not the id it is kept under."""
        name = body.get("name")
        if body.get("id") != set_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", set_id):
            raise ValueError("a set needs the id it is kept under")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("a set needs a name")
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO sets (id, body) VALUES (?, ?)",
                (set_id, json.dumps(body, ensure_ascii=False)),
            )

    def delete_set(self, set_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM sets WHERE id = ?", (set_id,))

    def uses_of(self, entry_id: int) -> list[tuple[str, str, float]]:
        """Every use of a word, as the form, who used it and when, in the
        order they were recorded."""
        with self._lock:
            return [
                (form, role, used_at)
                for form, role, used_at in self._db.execute(
                    "SELECT form, role, used_at FROM uses WHERE entry_id = ?"
                    " ORDER BY id",
                    (entry_id,),
                )
            ]

    def closest(self, category: str, word: str, count: int = 10) -> list[Entry]:
        """The entries of `category` whose dictionary forms are spelt most
        like `word`, the most alike first."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, lemma FROM entries WHERE category = ? ORDER BY id",
                (category,),
            ).fetchall()
            by_spelling: dict[str, int] = {}
            for entry_id, lemma in rows:
                by_spelling.setdefault(fold(lemma), entry_id)
            alike = difflib.get_close_matches(
                fold(word), list(by_spelling), n=count, cutoff=0.0
            )
            return [self._entry(by_spelling[spelling]) for spelling in alike]

    def save(
        self,
        category: str,
        lemma: str,
        details: dict[str, Any],
        forms: list[Form],
    ) -> tuple[Entry, bool]:
        """Store a word with its forms, and return its entry and whether it
        is a new one. If the word is stored already, which it may be when
        two of its forms were taken in at the same time, the forms it lacks
        are added to it and what is known about it is left as it is. The
        dictionary form is always one of the forms."""
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT id FROM entries WHERE category = ? AND lemma = ?",
                (category, lemma),
            ).fetchone()
            if row:
                entry_id = row[0]
            else:
                cursor = self._db.execute(
                    "INSERT INTO entries (category, lemma, details) VALUES (?, ?, ?)",
                    (category, lemma, json.dumps(details, ensure_ascii=False)),
                )
                assert cursor.lastrowid is not None
                entry_id = cursor.lastrowid
            self._add_forms(entry_id, forms)
            if not self._has_form(entry_id, lemma):
                self._add_forms(entry_id, [Form(lemma)])
            return self._entry(entry_id), row is None

    def add_forms(self, entry_id: int, forms: list[Form]) -> Entry:
        """Add the forms an entry lacks, and return the entry."""
        with self._lock, self._db:
            self._add_forms(entry_id, forms)
            return self._entry(entry_id)

    def reject(
        self, category: str, word: str, reason: str, belongs_to: str = ""
    ) -> None:
        """Remember that `word` does not belong in `category`, and which
        category it belongs in instead, if that is known."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO rejected"
                " (category, folded, reason, belongs_to) VALUES (?, ?, ?, ?)",
                (category, fold(word), reason, belongs_to),
            )

    def rejection(self, category: str, word: str) -> Rejection | None:
        """Why `word` was found not to belong in `category`, if it was."""
        with self._lock:
            row = self._db.execute(
                "SELECT reason, belongs_to FROM rejected"
                " WHERE category = ? AND folded = ?",
                (category, fold(word)),
            ).fetchone()
            return Rejection(*row) if row else None

    def note_taken(self, word: str, status: str) -> None:
        """Remember that `word`, on its own, was taken in, and what became
        of it."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO taken (folded, status) VALUES (?, ?)",
                (fold(word), status),
            )

    def not_taken(self, words: list[str]) -> list[str]:
        """Those of `words` that were never taken in, each once, in the
        order they were given."""
        with self._lock:
            taken = {row[0] for row in self._db.execute("SELECT folded FROM taken")}
        new: dict[str, str] = {}
        for word in words:
            if fold(word) not in taken:
                new.setdefault(fold(word), word)
        return list(new.values())

    # the rest is called with the lock held

    def _add_forms(self, entry_id: int, forms: list[Form]) -> None:
        self._db.executemany(
            "INSERT OR IGNORE INTO forms (entry_id, form, folded, tags)"
            " VALUES (?, ?, ?, ?)",
            [(entry_id, form.form, fold(form.form), form.tags) for form in forms],
        )

    def _has_form(self, entry_id: int, word: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM forms WHERE entry_id = ? AND folded = ?",
            (entry_id, fold(word)),
        ).fetchone()
        return row is not None

    def _entry(self, entry_id: int) -> Entry:
        category, lemma, details, created_at = self._db.execute(
            "SELECT category, lemma, details, created_at FROM entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        forms = self._db.execute(
            "SELECT form, tags, id FROM forms WHERE entry_id = ? ORDER BY id",
            (entry_id,),
        ).fetchall()
        return Entry(
            entry_id,
            category,
            lemma,
            json.loads(details),
            [Form(form, tags, form_id) for form, tags, form_id in forms],
            created_at,
        )


class Vocabularies:
    """The vocabularies, one for each language, each in a file of its own in
    one directory. They are opened as they are asked for."""

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)
        self._open: dict[str, Vocabulary] = {}
        self._lock = threading.Lock()

    def path_of(self, language: str) -> Path:
        name = re.sub(r"[^a-z0-9]+", "-", language.strip().lower()).strip("-")
        return self._directory / f"vocabulary.{name or 'language'}.db"

    def has(self, language: str) -> bool:
        """Whether there is a vocabulary of `language`, without making one."""
        path = self.path_of(language)
        german = path.name == "vocabulary.german.db"
        before = self._directory / "vocabulary.db"
        return path.exists() or (german and before.exists())

    def of(self, language: str) -> Vocabulary:
        path = self.path_of(language)
        with self._lock:
            if path.name not in self._open:
                # The vocabulary was of German before there was one for each
                # language, and in a file without the name of a language.
                before = self._directory / "vocabulary.db"
                if path.name == "vocabulary.german.db" and before.exists():
                    if not path.exists():
                        before.rename(path)
                self._open[path.name] = Vocabulary(path)
            return self._open[path.name]
