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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Raised with every change to the tables, so that a file written by an older
# version can be told and brought up to date.
SCHEMA_VERSION = 6

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
    -- which form it is, such as "present 1st singular". One spelling can be several.
    tags TEXT NOT NULL DEFAULT '',
    UNIQUE (entry_id, form, tags)
);
CREATE INDEX forms_folded ON forms (folded);
-- Words that were found not to belong in a category, so as not to ask again.
-- One found to be no word at all is kept under the category ''.
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
    """
-- What a word means, in each language it was translated into, apart from
-- what else is known about it, which is the same in every language.
CREATE TABLE IF NOT EXISTS meanings (
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    -- Which of the senses of the word they are of, where its senses are told
    -- apart by what goes with it, such as the article of a noun that has
    -- more than one; '' for a word that is not.
    sense TEXT NOT NULL DEFAULT '',
    -- the language they are written in, by its English name
    language TEXT NOT NULL,
    -- a JSON list, the most common first
    meanings TEXT NOT NULL,
    PRIMARY KEY (entry_id, sense, language)
);
-- They were kept with what else is known about a word, and in English.
INSERT OR IGNORE INTO meanings (entry_id, sense, language, meanings)
    SELECT id, '', 'English', json_extract(details, '$.meanings') FROM entries
    WHERE json_type(details, '$.meanings') = 'array';
UPDATE entries SET details = json_remove(details, '$.meanings');
""",
    """
-- A word is made of variants: as many as there are ways it differs in what
-- is known of it, such as die Bank with the plural Banken and die Bank with
-- Bänke, and most words have one. Each has what is known of it and its
-- forms, which are the same in every language, and its translations into
-- each language it was translated into.
CREATE TABLE variants (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    -- what else is known about it, as a JSON object
    details TEXT NOT NULL DEFAULT '{}',
    sense TEXT NOT NULL DEFAULT ''
);
CREATE INDEX variants_entry ON variants (entry_id);
CREATE TABLE translations (
    variant_id INTEGER NOT NULL REFERENCES variants (id) ON DELETE CASCADE,
    -- by its English name
    language TEXT NOT NULL,
    -- a JSON list, the most common first
    translations TEXT NOT NULL,
    PRIMARY KEY (variant_id, language)
);
-- Each sense the meanings were kept by is a variant, with what else was
-- known of the word, and a word that had none has one.
INSERT INTO variants (entry_id, details, sense)
    SELECT meanings.entry_id, entries.details, meanings.sense FROM meanings
    JOIN entries ON entries.id = meanings.entry_id
    GROUP BY meanings.entry_id, meanings.sense
    ORDER BY meanings.entry_id, MIN(meanings.rowid);
INSERT INTO variants (entry_id, details)
    SELECT id, details FROM entries
    WHERE id NOT IN (SELECT entry_id FROM meanings) ORDER BY id;
INSERT INTO translations (variant_id, language, translations)
    SELECT variants.id, meanings.language, meanings.meanings FROM meanings
    JOIN variants ON variants.entry_id = meanings.entry_id
        AND variants.sense = meanings.sense;
CREATE TABLE forms_of_variants (
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    -- the variant it is a form of, or 0 if it is of the word as a whole,
    -- such as a spelling it was met in that it was not described with
    variant_id INTEGER NOT NULL DEFAULT 0,
    form TEXT NOT NULL,
    -- the form in small letters, which is what words are looked up by
    folded TEXT NOT NULL,
    -- which form it is, such as "present 1st singular". One spelling can be several.
    tags TEXT NOT NULL DEFAULT '',
    UNIQUE (entry_id, variant_id, form, tags)
);
-- A sense was what the tags of the forms of the word in it start with, such
-- as an article; a form of a word of one variant is of that one.
INSERT INTO forms_of_variants (id, entry_id, variant_id, form, folded, tags)
    SELECT forms.id, forms.entry_id, COALESCE(
        (SELECT variants.id FROM variants
         WHERE variants.entry_id = forms.entry_id AND variants.sense <> ''
             AND (forms.tags = variants.sense OR forms.tags LIKE variants.sense || ' %')
         ORDER BY variants.id LIMIT 1),
        (SELECT MIN(variants.id) FROM variants
         WHERE variants.entry_id = forms.entry_id HAVING COUNT(*) = 1),
        0
    ), forms.form, forms.folded, forms.tags FROM forms;
DROP TABLE forms;
ALTER TABLE forms_of_variants RENAME TO forms;
CREATE INDEX forms_folded ON forms (folded);
ALTER TABLE variants DROP COLUMN sense;
DROP TABLE meanings;
ALTER TABLE entries DROP COLUMN details;
""",
]


# what a word that is no word of any category is rejected as
NO_CATEGORY = ""

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


def _together(counted: list[list[Any]]) -> tuple[Any, ...]:
    """The uses of several entries, each as how often the learner and a
    model used it, when it was first and last used, and when last by each,
    taken together as the uses of one word."""

    def least(values: list[float | None]) -> float | None:
        return min((value for value in values if value is not None), default=None)

    def most(values: list[float | None]) -> float | None:
        return max((value for value in values if value is not None), default=None)

    used, seen, first, last, by_user, by_assistant = zip(*counted, strict=True)
    return (
        sum(used),
        sum(seen),
        least(list(first)),
        most(list(last)),
        most(list(by_user)),
        most(list(by_assistant)),
    )


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
    # the variant it is a form of, by its id, or 0 if of the word as a whole
    variant: int = 0


@dataclass
class Variant:
    """One of the variants a word is made of, as the variants table
    describes them."""

    id: int
    # what is known about it beyond its forms and its translations
    details: dict[str, Any] = field(default_factory=dict)
    # its translations, in each language it was translated into
    translations: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class Described:
    """A variant of a word as it is described, to be stored."""

    details: dict[str, Any]
    # in the language it was described in
    translations: list[str]
    forms: list[Form]


@dataclass
class Entry:
    id: int
    category: str
    lemma: str
    # every form of each variant, and of the word as a whole
    forms: list[Form] = field(default_factory=list)
    # when it was stored, in UTC
    created_at: str = ""
    variants: list[Variant] = field(default_factory=list)

    def shown_in(self, language: str) -> str:
        """The language its translations are best given in: `language` if it
        has any there, or else the first other one it has any in."""
        languages = [lang for variant in self.variants for lang in variant.translations]
        return language if language in languages or not languages else languages[0]

    def translations_into(self, language: str) -> list[str]:
        """The translations of every variant, in the language `shown_in`
        gives for `language`."""
        shown = self.shown_in(language)
        return [
            translation
            for variant in self.variants
            for translation in variant.translations.get(shown, [])
        ]


@dataclass
class Listed:
    """A stored word as it is listed: without what is known about it. Its
    uses are those of every stored word spelt as it is, whatever the
    capitals and the category, as to whoever uses it they are one word."""

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
    # when the learner last used it, and when a model last did
    last_used_by_user: float | None = None
    last_used_by_assistant: float | None = None


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

        A form in two words, such as one of a verb whose parts come apart
        in a sentence, has words between them where it is used. So a word
        that is the first of a stored form in two words is that form if the
        other comes later in the `sentence` it was used in."""
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
        """Every stored word, by category and then by the alphabet, each with
        the uses of all the words spelt as it is."""
        with self._lock:
            rows = self._db.execute(
                "SELECT entries.id, category, lemma, entries.created_at,"
                " COUNT(DISTINCT forms.form || ' ' || forms.tags) FROM entries"
                " LEFT JOIN forms ON forms.entry_id = entries.id"
                " GROUP BY entries.id"
            ).fetchall()
            uses = {
                entry_id: counted
                for entry_id, *counted in self._db.execute(
                    "SELECT entry_id, SUM(role = 'user'), SUM(role <> 'user'),"
                    " MIN(used_at), MAX(used_at),"
                    " MAX(CASE WHEN role = 'user' THEN used_at END),"
                    " MAX(CASE WHEN role <> 'user' THEN used_at END)"
                    " FROM uses GROUP BY entry_id"
                )
            }
        # Words spelt alike are one word to whoever uses them, whatever
        # their categories, so they share what is known of their uses.
        spelt: dict[str, list[list[Any]]] = {}
        for entry_id, _, lemma, *_ in rows:
            if entry_id in uses:
                spelt.setdefault(fold(lemma), []).append(uses[entry_id])
        shared = {spelling: _together(counted) for spelling, counted in spelt.items()}
        listed = [Listed(*row, *shared.get(fold(row[2]), ())) for row in rows]
        return sorted(listed, key=lambda word: (word.category, fold(word.lemma)))

    def having_forms(self, words: list[str]) -> set[int]:
        """The entries that any of `words` is a form of, whatever the
        capitals, by their numbers."""
        folded = {fold(word) for word in words}
        with self._lock:
            return {
                entry_id
                for entry_id, form in self._db.execute(
                    "SELECT entry_id, folded FROM forms"
                )
                if form in folded
            }

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
        translations: list[str] | None = None,
        language: str = "",
    ) -> tuple[Entry, bool]:
        """Store a word of one variant, as `save_variants` does."""
        return self.save_variants(
            category, lemma, [Described(details, translations or [], forms)], language
        )

    def save_variants(
        self,
        category: str,
        lemma: str,
        variants: list[Described],
        language: str = "",
        forms: list[Form] | None = None,
    ) -> tuple[Entry, bool]:
        """Store a word with its variants, their translations in `language`,
        and `forms` of the word as a whole, and return its entry and whether
        it is a new one. If the word is stored already, which it may be when
        two of its forms were taken in at the same time, the forms it lacks
        are added to it as forms of the word as a whole and what is known
        about it is left as it is. The dictionary form is always one of the
        forms."""
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT id FROM entries WHERE category = ? AND lemma = ?",
                (category, lemma),
            ).fetchone()
            if row:
                entry_id = row[0]
                described = [
                    Form(form.form, form.tags)
                    for each in variants
                    for form in each.forms
                ]
                self._add_forms(entry_id, described)
            else:
                cursor = self._db.execute(
                    "INSERT INTO entries (category, lemma) VALUES (?, ?)",
                    (category, lemma),
                )
                assert cursor.lastrowid is not None
                entry_id = cursor.lastrowid
                for each in variants:
                    variant_id = self._add_variant(entry_id, each.details)
                    if each.translations:
                        self._set_translations(variant_id, language, each.translations)
                    self._add_forms(
                        entry_id,
                        [
                            Form(form.form, form.tags, variant=variant_id)
                            for form in each.forms
                        ],
                    )
            self._add_forms(entry_id, forms or [])
            if not self._has_form(entry_id, lemma):
                self._add_forms(entry_id, [Form(lemma)])
            return self._entry(entry_id), row is None

    def set_translations(
        self, entry_id: int, language: str, translations: list[list[str]]
    ) -> Entry:
        """Store the translations of each variant of an entry in `language`,
        in the order of its variants, in place of those they had there, and
        return the entry."""
        with self._lock, self._db:
            variants = [
                variant_id
                for (variant_id,) in self._db.execute(
                    "SELECT id FROM variants WHERE entry_id = ? ORDER BY id",
                    (entry_id,),
                )
            ]
            if len(variants) != len(translations):
                raise ValueError("the translations are not those of every variant")
            for variant_id, listed in zip(variants, translations, strict=True):
                self._set_translations(variant_id, language, listed)
            return self._entry(entry_id)

    def lacking_translations(self, language: str) -> list[int]:
        """The entries that have a variant without translations in
        `language`, in the order they were stored in."""
        with self._lock:
            rows = self._db.execute(
                "SELECT DISTINCT variants.entry_id FROM variants"
                " WHERE NOT EXISTS (SELECT 1 FROM translations"
                " WHERE variant_id = variants.id AND language = ?)"
                " ORDER BY variants.entry_id",
                (language,),
            ).fetchall()
        return [entry_id for (entry_id,) in rows]

    def add_forms(self, entry_id: int, forms: list[Form]) -> Entry:
        """Add the forms an entry lacks, and return the entry."""
        with self._lock, self._db:
            self._add_forms(entry_id, forms)
            return self._entry(entry_id)

    def respell(self, category: str, spelt: Callable[[str], str]) -> None:
        """Store every dictionary form of `category` as `spelt` writes it.
        An entry that comes to be spelt as another one is merged into
        it: its forms and its uses go to that one, and so do the sets that
        named it."""
        with self._lock, self._db:
            rows = self._db.execute(
                "SELECT id, lemma FROM entries WHERE category = ? ORDER BY id",
                (category,),
            ).fetchall()
            by_lemma = {lemma: entry_id for entry_id, lemma in rows}
            merged: dict[int, int] = {}
            for entry_id, lemma in rows:
                new = spelt(lemma)
                if new == lemma:
                    continue
                del by_lemma[lemma]
                twin = by_lemma.get(new)
                if twin is None:
                    self._db.execute(
                        "UPDATE entries SET lemma = ? WHERE id = ?", (new, entry_id)
                    )
                    by_lemma[new] = entry_id
                    continue
                # as forms of the twin as a whole, as its variants are its own
                self._db.execute(
                    "INSERT OR IGNORE INTO forms (entry_id, form, folded, tags)"
                    " SELECT ?, form, folded, tags FROM forms WHERE entry_id = ?",
                    (twin, entry_id),
                )
                self._db.execute(
                    "UPDATE uses SET entry_id = ? WHERE entry_id = ?", (twin, entry_id)
                )
                self._db.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
                merged[entry_id] = twin
            if merged:
                self._renumber_sets(merged)

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

    def discard(self, word: str, reason: str) -> None:
        """Remember that `word` is no word of any category, such as one
        misspelt, so that it is not sorted into one again."""
        self.reject(NO_CATEGORY, word, reason)

    def discarded(self, word: str) -> str | None:
        """Why `word` was found to be no word, if it was. A word spelt as a
        stored word is, whatever its capitals, is not taken to be no word,
        since it may be that word where it is met."""
        with self._lock:
            row = self._db.execute(
                "SELECT reason FROM rejected WHERE category = ? AND folded = ?"
                " AND NOT EXISTS (SELECT 1 FROM forms WHERE folded = ?)"
                " AND NOT EXISTS (SELECT 1 FROM entries WHERE lower(lemma) = ?)",
                (NO_CATEGORY, *[fold(word)] * 3),
            ).fetchone()
            return row[0] if row else None

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
        """Add the forms an entry lacks. One of the word as a whole is one it
        lacks only if none of its variants has it either."""
        stored = set(
            self._db.execute(
                "SELECT form, tags FROM forms WHERE entry_id = ?", (entry_id,)
            ).fetchall()
        )
        self._db.executemany(
            "INSERT OR IGNORE INTO forms (entry_id, variant_id, form, folded, tags)"
            " VALUES (?, ?, ?, ?, ?)",
            [
                (entry_id, form.variant, form.form, fold(form.form), form.tags)
                for form in forms
                if form.variant or (form.form, form.tags) not in stored
            ],
        )

    def _add_variant(self, entry_id: int, details: dict[str, Any]) -> int:
        cursor = self._db.execute(
            "INSERT INTO variants (entry_id, details) VALUES (?, ?)",
            (entry_id, json.dumps(details, ensure_ascii=False)),
        )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def _set_translations(
        self, variant_id: int, language: str, translations: list[str]
    ) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO translations (variant_id, language, translations)"
            " VALUES (?, ?, ?)",
            (variant_id, language, json.dumps(translations, ensure_ascii=False)),
        )

    def _renumber_sets(self, merged: dict[int, int]) -> None:
        """Have the sets name each entry of `merged` by the one it went into."""
        for set_id, body in self._db.execute("SELECT id, body FROM sets").fetchall():
            kept = json.loads(body)
            for key in ("added", "removed"):
                if isinstance(kept.get(key), list):
                    ids = [merged.get(word, word) for word in kept[key]]
                    kept[key] = list(dict.fromkeys(ids))
            self._db.execute(
                "UPDATE sets SET body = ? WHERE id = ?",
                (json.dumps(kept, ensure_ascii=False), set_id),
            )

    def _has_form(self, entry_id: int, word: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM forms WHERE entry_id = ? AND folded = ?",
            (entry_id, fold(word)),
        ).fetchone()
        return row is not None

    def _entry(self, entry_id: int) -> Entry:
        category, lemma, created_at = self._db.execute(
            "SELECT category, lemma, created_at FROM entries WHERE id = ?",
            (entry_id,),
        ).fetchone()
        forms = self._db.execute(
            "SELECT form, tags, id, variant_id FROM forms WHERE entry_id = ? ORDER BY id",
            (entry_id,),
        ).fetchall()
        variants = {
            variant_id: Variant(variant_id, json.loads(details))
            for variant_id, details in self._db.execute(
                "SELECT id, details FROM variants WHERE entry_id = ? ORDER BY id",
                (entry_id,),
            )
        }
        for variant_id, language, listed in self._db.execute(
            "SELECT variant_id, language, translations FROM translations"
            " JOIN variants ON variants.id = variant_id WHERE entry_id = ?"
            " ORDER BY translations.rowid",
            (entry_id,),
        ):
            variants[variant_id].translations[language] = json.loads(listed)
        return Entry(
            entry_id,
            category,
            lemma,
            [Form(*row) for row in forms],
            created_at,
            list(variants.values()),
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
