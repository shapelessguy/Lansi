# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What a user has written and been written: the chats with their messages,
what was written in the exercises of practice, and the settings. The books a
user reads are kept here as well.

Every message and everything written in an exercise carries when it was
processed, which is not yet until its words have been taken into the
vocabulary and counted. A message that is changed is to be processed again.
What was written in an exercise is processed once the exercise is over.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Raised with every change to the tables.
SCHEMA_VERSION = 15

_SCHEMA = """
CREATE TABLE chats (
    id TEXT PRIMARY KEY,
    -- the instructions the chat was started with, by their id in the settings
    context_id TEXT NOT NULL DEFAULT '',
    -- the language that was being learned when the chat was started
    language TEXT NOT NULL DEFAULT '',
    -- when a message was last added, in milliseconds since the epoch
    updated_at INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    chat_id TEXT NOT NULL REFERENCES chats (id) ON DELETE CASCADE,
    -- where the message is in its chat, from 0
    position INTEGER NOT NULL,
    -- "user" for what the user wrote, "assistant" for what the model did
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    -- when the content last changed, in seconds since the epoch
    changed_at REAL NOT NULL,
    -- when its words were taken into the vocabulary and counted, if they were
    processed_at REAL,
    UNIQUE (chat_id, position)
);
-- single things kept as JSON, such as the settings
CREATE TABLE kept (
    name TEXT PRIMARY KEY,
    body TEXT NOT NULL
);
"""

# What came with version 2.
_BOOKS = """
CREATE TABLE books (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL DEFAULT '',
    -- as the book names it, such as "de"
    language TEXT NOT NULL DEFAULT '',
    -- when it was added, in milliseconds since the epoch
    added_at INTEGER NOT NULL,
    -- its paragraphs, each with its text and its size, in JSON
    blocks TEXT NOT NULL
);
"""

# What came with version 3: where a book that is from the folder of books is
# from, which is the name of its file there, and what tells that file from a
# later one of the same name.
_BOOK_SOURCES = """
ALTER TABLE books ADD COLUMN source TEXT;
ALTER TABLE books ADD COLUMN stamp TEXT;
"""

# What came with version 4: the kind of file the picture on the cover of a
# book is, if the book has one.
_BOOK_COVERS = """
ALTER TABLE books ADD COLUMN cover_type TEXT;
"""

# What came with version 5: the sentences of the books that were read
# aloud, as they were written then and with who read them. The audio of each
# is in a file. The sentences of the chats that were read aloud are kept the
# same way, with the id of the chat for that of a book.
_BOOK_SPEECH = """
CREATE TABLE book_speech (
    book_id TEXT NOT NULL,
    sentence_id TEXT NOT NULL,
    text TEXT NOT NULL,
    model TEXT NOT NULL,
    voice TEXT NOT NULL,
    content_type TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (book_id, sentence_id)
);
"""

# What came with version 6: the sessions of practice, the exercises done in
# each, and the logs of what the learner answered in them.
_PRACTICE = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    -- the language being learned, which the lesson is of
    language TEXT NOT NULL,
    lesson TEXT NOT NULL,
    -- the ids of the topics, in JSON
    topics TEXT NOT NULL,
    -- in seconds since the epoch
    started_at REAL NOT NULL,
    finished_at REAL,
    -- "running", "finished" or "abandoned"
    status TEXT NOT NULL
);
CREATE TABLE session_exercises (
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    exercise TEXT NOT NULL,
    -- where it is among the exercises of the session, from 0
    position INTEGER NOT NULL,
    -- how many instances of it there are to be
    instances INTEGER NOT NULL,
    -- What the exercise keeps from one step to the next, and what it last
    -- showed, in JSON, once it has started.
    state TEXT,
    shown TEXT,
    -- what it reported when it finished, in JSON
    results TEXT,
    finished_at REAL,
    PRIMARY KEY (session_id, exercise)
);
CREATE TABLE logs (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    exercise TEXT NOT NULL,
    -- "right", "wrong" or "partial"
    result TEXT NOT NULL,
    answer TEXT NOT NULL,
    correction TEXT NOT NULL,
    note TEXT NOT NULL
);
"""

# What came with version 7: the topics a session can be about, each with a
# picture of its own in a file; the words of every session, and whether its
# topics are mixed; and the embeddings of the texts that were embedded, such
# as the words of the vocabulary and the topics, by the model that made them.
_TOPICS = """
CREATE TABLE topics (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at REAL NOT NULL,
    -- the kind of file its icon is, once it has one
    icon_type TEXT
);
CREATE TABLE embeddings (
    model TEXT NOT NULL,
    text TEXT NOT NULL,
    -- the vector, as float16 numbers one after another
    vector BLOB NOT NULL,
    PRIMARY KEY (model, text)
);
-- the words the exercises are to use, {"mode": ..., "lemmas": [...]} in JSON
ALTER TABLE sessions ADD COLUMN words TEXT;
ALTER TABLE sessions ADD COLUMN mix_topics INTEGER NOT NULL DEFAULT 0;
"""

# What came with version 8: what each exercise of a session was told to
# heed besides its lesson, topics and words, such as what was used before.
_GUIDANCE = """
ALTER TABLE session_exercises ADD COLUMN guidance TEXT NOT NULL DEFAULT '';
"""

# What came with version 9: what each request to a model used. `id` is set
# for a request that may be reported more than once, so that it is counted
# only the first time; `chat_id` is what it was made for, such as a chat or a
# text, and `category` the kind of work it was.
_USAGE = """
CREATE TABLE usage (
    number INTEGER PRIMARY KEY,
    id TEXT UNIQUE,
    at INTEGER NOT NULL,
    category TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    cost REAL
);
CREATE INDEX usage_by_time ON usage (at);
CREATE INDEX usage_by_chat ON usage (chat_id);
"""

# What came with version 10: the lessons a review goes over, in JSON, for a
# session that is not of one lesson, whose `lesson` is then empty.
_REVIEWS = """
ALTER TABLE sessions ADD COLUMN lessons TEXT NOT NULL DEFAULT '[]';
"""

# What came with version 11: what the learner and the models wrote in each
# exercise of a session, so that its words are taken into the vocabulary
# once the exercise is over; and the options each exercise was chosen with,
# in JSON. The generated texts, which were kept before, are no more.
_WRITTEN = """
CREATE TABLE written (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    exercise TEXT NOT NULL,
    -- "user" for what the learner wrote, "assistant" for what a model did
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    -- in seconds since the epoch
    written_at REAL NOT NULL,
    -- when its words were taken into the vocabulary and counted, if they were
    processed_at REAL
);
CREATE INDEX written_by_exercise ON written (session_id, exercise);
ALTER TABLE session_exercises ADD COLUMN options TEXT NOT NULL DEFAULT '{}';
DROP TABLE IF EXISTS texts;
"""

# What came with version 12: the grades of what the learner answered, which
# were the logs before; and the log of each exercise of a session, written
# by a model once it is over. The logs there were are not kept.
_LOGS = """
DROP TABLE IF EXISTS logs;
CREATE TABLE grades (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    exercise TEXT NOT NULL,
    -- "right", "wrong" or "partial"
    result TEXT NOT NULL,
    answer TEXT NOT NULL,
    correction TEXT NOT NULL,
    note TEXT NOT NULL
);
CREATE TABLE logs (
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    exercise TEXT NOT NULL,
    -- what worked and what did not, for the app rather than the learner
    content TEXT NOT NULL,
    -- in seconds since the epoch
    written_at REAL NOT NULL,
    PRIMARY KEY (session_id, exercise)
);
"""

# What came with version 13: the findings of the logs, left from a sorting of
# errors that was taken out again, are no more. They named the logs there
# were before, and kept any log from being written.
_FINDINGS = """
DROP TABLE IF EXISTS findings;
"""

# What came with version 14: what the exercise gave the learner to answer,
# for each grade, so that it is told from what the learner wrote.
_TASKS = """
ALTER TABLE grades ADD COLUMN task TEXT NOT NULL DEFAULT '';
"""

# What came with version 15: the logs are of whatever the learner did, not
# only of the exercises of the sessions, such as what they had translated
# and what they asked about it. Those of an exercise still name its session
# and the exercise, and the others where what they are of was done.
_ACTIVITY_LOGS = """
ALTER TABLE logs RENAME TO exercise_logs;
CREATE TABLE logs (
    id INTEGER PRIMARY KEY,
    -- "exercise", "translation" or "question"
    kind TEXT NOT NULL,
    -- the language being learned
    language TEXT NOT NULL,
    -- what it is about, in a few words, such as the words translated
    subject TEXT NOT NULL,
    -- what happened, for the models rather than the learner
    content TEXT NOT NULL,
    -- in seconds since the epoch
    written_at REAL NOT NULL,
    -- the session and the exercise of the log of an exercise
    session_id TEXT REFERENCES sessions (id) ON DELETE CASCADE,
    exercise TEXT,
    -- where else it was done, such as a page of a book, in JSON
    source TEXT NOT NULL DEFAULT '{}',
    UNIQUE (session_id, exercise)
);
INSERT INTO logs
    (kind, language, subject, content, written_at, session_id, exercise)
SELECT 'exercise', sessions.language, exercise_logs.exercise,
    exercise_logs.content, exercise_logs.written_at, exercise_logs.session_id,
    exercise_logs.exercise
FROM exercise_logs JOIN sessions ON sessions.id = exercise_logs.session_id
ORDER BY exercise_logs.written_at;
DROP TABLE exercise_logs;
"""

# what the logs are of
LOG_KINDS = ("exercise", "translation", "question")
# What is said of a log when they are listed.
_LOG_COLUMNS = (
    "id, kind, language, subject, content, written_at, session_id, exercise, source"
)

# what the learner and the models are, as what they wrote is kept
ROLES = ("user", "assistant")

# What is added up of some of the usage.
_TOTALS = (
    "COUNT(*), COALESCE(SUM(prompt_tokens), 0),"
    " COALESCE(SUM(completion_tokens), 0), COALESCE(SUM(cost), 0),"
    " COALESCE(MAX(cost IS NULL), 0)"
)

# What a grade says of an answer.
RESULTS = ("right", "wrong", "partial")

# the id of a sentence of a book: the place of its paragraph, and its own in it
_SENTENCE_ID = re.compile(r"\d{1,9}\.\d{1,9}")

# What is listed of a book.
_LISTED = "id, title, author, language, added_at, source, cover_type"

# An id is given by the app, and is part of the name of a file for a topic.
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}")


@dataclass
class Unprocessed:
    """A message, or what was written in an exercise, whose words have not
    been taken into the vocabulary and counted yet."""

    # "message" or "exercise"
    kind: str
    # The id of the chat the message is in, or that of the session and the
    # exercise, as "SESSION/EXERCISE".
    source_id: str
    # Where the message is in its chat, from 0, or what was written goes by
    # among all that was written in exercises.
    position: int
    # "user" if the user wrote it, "assistant" if a model did
    role: str
    content: str
    # the language that was being learned when it was written, if known
    language: str
    # when it last changed, which tells it from what it may be changed to
    changed_at: float


def is_id(value: object) -> bool:
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _listed(
    book_id: str,
    title: str,
    author: str,
    language: str,
    added_at: int,
    source: str | None,
    cover_type: str | None,
) -> dict[str, Any]:
    """A book as it is listed, without what it says."""
    return {
        "id": book_id,
        "title": title,
        "author": author,
        "language": language,
        "addedAt": added_at,
        # the name of its file in the folder of books, if it is from there
        "source": source,
        # whether there is a picture of its cover
        "cover": cover_type is not None,
    }


def _log(
    log_id: int,
    kind: str,
    language: str,
    subject: str,
    content: str,
    written_at: float,
    session_id: str | None,
    exercise: str | None,
    source: str,
) -> dict[str, Any]:
    """A log as it is listed."""
    return {
        "id": log_id,
        "kind": kind,
        "language": language,
        "subject": subject,
        "content": content,
        "writtenAt": written_at,
        # those of an exercise of a session
        "session": session_id,
        "exercise": exercise,
        "source": json.loads(source),
    }


class UserStore:
    """The chats, the practice and the settings of one user, in a directory
    of the user's own. It can be used from several threads."""

    def __init__(
        self, directory: str | Path, now: Callable[[], float] = time.time
    ) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._covers = self._directory / "covers"
        self._speech = self._directory / "speech"
        self._icons = self._directory / "topics"
        self._now = now
        self._db = sqlite3.connect(
            str(self._directory / "app.db"), check_same_thread=False
        )
        self._db.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()
        with self._lock, self._db:
            (version,) = self._db.execute("PRAGMA user_version").fetchone()
            if version == 0:
                self._db.executescript(_SCHEMA)
            if version < 2:
                self._db.executescript(_BOOKS)
            if version < 3:
                self._db.executescript(_BOOK_SOURCES)
            if version < 4:
                self._db.executescript(_BOOK_COVERS)
            if version < 5:
                self._db.executescript(_BOOK_SPEECH)
            if version < 6:
                self._db.executescript(_PRACTICE)
            if version < 7:
                self._db.executescript(_TOPICS)
            if version < 8:
                self._db.executescript(_GUIDANCE)
            if version < 9:
                self._db.executescript(_USAGE)
            if version < 10:
                self._db.executescript(_REVIEWS)
            if version < 11:
                self._db.executescript(_WRITTEN)
            if version < 12:
                self._db.executescript(_LOGS)
            if version < 13:
                self._db.executescript(_FINDINGS)
            if version < 14:
                self._db.executescript(_TASKS)
            if version < 15:
                self._db.executescript(_ACTIVITY_LOGS)
            self._db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def close(self) -> None:
        self._db.close()

    # chats

    def chats(self) -> list[dict[str, Any]]:
        """Every chat with its messages, as the app keeps them."""
        with self._lock:
            chats = {
                chat_id: {
                    "id": chat_id,
                    "contextId": context_id,
                    "language": language,
                    "updatedAt": updated_at,
                    "messages": [],
                }
                for chat_id, context_id, language, updated_at in self._db.execute(
                    "SELECT id, context_id, language, updated_at FROM chats"
                )
            }
            for chat_id, role, content, processed_at in self._db.execute(
                "SELECT chat_id, role, content, processed_at FROM messages"
                " ORDER BY chat_id, position"
            ):
                chats[chat_id]["messages"].append(
                    {
                        "role": role,
                        "content": content,
                        "processed": processed_at is not None,
                    }
                )
        return list(chats.values())

    def save_chat(self, chat: dict[str, Any]) -> None:
        """Keep a chat as it is now. A message that is as it was keeps
        having been processed; one that is new or changed has not been.
        Raises ValueError for a chat that is not one."""
        messages = chat.get("messages")
        if not is_id(chat.get("id")) or not isinstance(messages, list):
            raise ValueError("a chat needs an id and messages")
        for message in messages:
            if (
                not isinstance(message, dict)
                or message.get("role") not in ("system", "user", "assistant")
                or not isinstance(message.get("content"), str)
            ):
                raise ValueError("a message needs a role and a content")
        updated_at = chat.get("updatedAt")
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO chats (id, context_id, language, updated_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET"
                " context_id = excluded.context_id, updated_at = excluded.updated_at,"
                " language = CASE WHEN chats.language = ''"
                " THEN excluded.language ELSE chats.language END",
                (
                    chat["id"],
                    str(chat.get("contextId") or ""),
                    str(chat.get("language") or ""),
                    updated_at if isinstance(updated_at, int) else 0,
                ),
            )
            stored = dict(
                (position, (role, content))
                for position, role, content in self._db.execute(
                    "SELECT position, role, content FROM messages WHERE chat_id = ?",
                    (chat["id"],),
                )
            )
            for position, message in enumerate(messages):
                as_it_is = (message["role"], message["content"])
                if stored.get(position) != as_it_is:
                    self._db.execute(
                        "INSERT OR REPLACE INTO messages"
                        " (chat_id, position, role, content, changed_at)"
                        " VALUES (?, ?, ?, ?, ?)",
                        (chat["id"], position, *as_it_is, self._now()),
                    )
            self._db.execute(
                "DELETE FROM messages WHERE chat_id = ? AND position >= ?",
                (chat["id"], len(messages)),
            )

    def delete_chat(self, chat_id: str) -> None:
        """Remove a chat, and the audio of what was read aloud of it."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            # the audio of a chat is kept as that of a book is, under its id
            self._db.execute("DELETE FROM book_speech WHERE book_id = ?", (chat_id,))
        if is_id(chat_id):
            shutil.rmtree(self._speech / chat_id, ignore_errors=True)

    # books

    def books(self) -> list[dict[str, Any]]:
        """Every book, without what it says."""
        with self._lock:
            rows = self._db.execute(f"SELECT {_LISTED} FROM books").fetchall()
        return [_listed(*row) for row in rows]

    def book(self, book_id: str) -> dict[str, Any] | None:
        """A book with its paragraphs, if there is such a book."""
        with self._lock:
            row = self._db.execute(
                f"SELECT {_LISTED}, blocks FROM books WHERE id = ?", (book_id,)
            ).fetchone()
        return {**_listed(*row[:7]), "blocks": json.loads(row[7])} if row else None

    def add_book(
        self,
        book_id: str,
        title: str,
        author: str,
        language: str,
        blocks: list[dict[str, Any]],
        source: str | None = None,
        stamp: str | None = None,
        cover: tuple[bytes, str] | None = None,
    ) -> dict[str, Any]:
        """Keep a book, and return it as it is listed. A book that is from
        the folder of books has the name of its file there as its `source`,
        and what tells that file from a later one of the same name as its
        `stamp`. `cover` is the picture on its cover with the kind of file
        it is. A book that was kept before stays as long ago added as it
        was. Raises ValueError for an id that is not one."""
        if not is_id(book_id):
            raise ValueError("a book needs an id")
        with self._lock, self._db:
            if cover:
                self._covers.mkdir(exist_ok=True)
                (self._covers / book_id).write_bytes(cover[0])
            else:
                (self._covers / book_id).unlink(missing_ok=True)
            self._db.execute(
                "INSERT INTO books (id, title, author, language, added_at, blocks,"
                " source, stamp, cover_type)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET"
                " title = excluded.title, author = excluded.author,"
                " language = excluded.language, blocks = excluded.blocks,"
                " source = excluded.source, stamp = excluded.stamp,"
                " cover_type = excluded.cover_type",
                (
                    book_id,
                    title,
                    author,
                    language,
                    int(self._now() * 1000),
                    json.dumps(blocks, ensure_ascii=False),
                    source,
                    stamp,
                    cover[1] if cover else None,
                ),
            )
            row = self._db.execute(
                f"SELECT {_LISTED} FROM books WHERE id = ?", (book_id,)
            ).fetchone()
        return _listed(*row)

    def cover(self, book_id: str) -> tuple[bytes, str] | None:
        """The picture on the cover of a book with the kind of file it is,
        if the book has one."""
        with self._lock:
            row = self._db.execute(
                "SELECT cover_type FROM books WHERE id = ?", (book_id,)
            ).fetchone()
            file = self._covers / book_id
            if not row or not row[0] or not file.exists():
                return None
            return file.read_bytes(), row[0]

    def delete_book(self, book_id: str) -> None:
        """Remove a book, the picture on its cover and the audio of its
        sentences."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM books WHERE id = ?", (book_id,))
            self._db.execute("DELETE FROM book_speech WHERE book_id = ?", (book_id,))
        if is_id(book_id):
            (self._covers / book_id).unlink(missing_ok=True)
            shutil.rmtree(self._speech / book_id, ignore_errors=True)

    def save_speech(
        self,
        book_id: str,
        sentence_id: str,
        text: str,
        model: str,
        voice: str,
        audio: bytes,
        content_type: str,
    ) -> None:
        """Keep the audio of a sentence of a book, with the sentence as it
        was read and who read it. Audio there was of it before is replaced.
        Raises ValueError for ids that cannot be the names of files."""
        if not is_id(book_id) or not _SENTENCE_ID.fullmatch(sentence_id):
            raise ValueError("not the id of a sentence of a book")
        with self._lock, self._db:
            (self._speech / book_id).mkdir(parents=True, exist_ok=True)
            (self._speech / book_id / sentence_id).write_bytes(audio)
            self._db.execute(
                "INSERT OR REPLACE INTO book_speech VALUES (?, ?, ?, ?, ?, ?, ?)",
                (book_id, sentence_id, text, model, voice, content_type, self._now()),
            )

    def speech(self, book_id: str, sentence_id: str) -> tuple[bytes, str] | None:
        """The audio of a sentence of a book with the kind of file it is,
        if it is kept."""
        with self._lock:
            row = self._db.execute(
                "SELECT content_type FROM book_speech"
                " WHERE book_id = ? AND sentence_id = ?",
                (book_id, sentence_id),
            ).fetchone()
            if not row or not is_id(book_id):
                return None
            file = self._speech / book_id / sentence_id
            return (file.read_bytes(), row[0]) if file.exists() else None

    def spoken(self, book_id: str) -> dict[str, tuple[str, str, str]]:
        """The sentences of a book whose audio is kept, by their ids: each
        as it was read, with the model and the voice that read it."""
        with self._lock:
            rows = self._db.execute(
                "SELECT sentence_id, text, model, voice FROM book_speech"
                " WHERE book_id = ?",
                (book_id,),
            ).fetchall()
        return {
            sentence_id: (text, model, voice)
            for sentence_id, text, model, voice in rows
        }

    def books_from_folder(self) -> dict[str, tuple[str, str]]:
        """The books that are from the folder of books: the id and the stamp
        of each, by the name of its file."""
        with self._lock:
            rows = self._db.execute(
                "SELECT source, id, stamp FROM books WHERE source IS NOT NULL"
            ).fetchall()
        return {source: (book_id, stamp or "") for source, book_id, stamp in rows}

    def books_folder(self) -> str:
        """The folder the books are taken from, or nothing if there is none."""
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM kept WHERE name = 'books_folder'"
            ).fetchone()
        return str(json.loads(row[0])) if row else ""

    def save_books_folder(self, folder: str) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO kept (name, body) VALUES ('books_folder', ?)",
                (json.dumps(folder, ensure_ascii=False),),
            )

    # processing

    def unprocessed(self, before: float) -> list[Unprocessed]:
        """The messages that are not processed, and were last changed
        before `before`, with what was written in the exercises that are
        over, the oldest first. An exercise is over once it is finished or
        its session has ended. What the app wrote to start a chat with, the
        "system" messages, is never processed."""
        with self._lock:
            messages = self._db.execute(
                "SELECT 'message', chat_id, position, role, content, language,"
                " changed_at FROM messages JOIN chats ON chats.id = chat_id"
                " WHERE processed_at IS NULL AND changed_at < ?"
                " AND role IN ('user', 'assistant')",
                (before,),
            ).fetchall()
            written = self._db.execute(
                "SELECT 'exercise', written.session_id || '/' || written.exercise,"
                " written.id, role, content, sessions.language, written_at"
                " FROM written JOIN sessions ON sessions.id = written.session_id"
                " JOIN session_exercises ON"
                " session_exercises.session_id = written.session_id"
                " AND session_exercises.exercise = written.exercise"
                " WHERE written.processed_at IS NULL AND written_at < ?"
                " AND (session_exercises.finished_at IS NOT NULL"
                " OR sessions.status != 'running')",
                (before,),
            ).fetchall()
        waiting = [Unprocessed(*row) for row in messages + written]
        return sorted(waiting, key=lambda item: item.changed_at)

    def mark_processed(self, item: Unprocessed, at: float) -> bool:
        """Note that a message, or what was written in an exercise, has been
        processed, unless it was changed since it was read. Returns whether
        it was noted."""
        with self._lock, self._db:
            if item.kind == "exercise":
                cursor = self._db.execute(
                    "UPDATE written SET processed_at = ? WHERE id = ?",
                    (at, item.position),
                )
            else:
                cursor = self._db.execute(
                    "UPDATE messages SET processed_at = ? WHERE chat_id = ?"
                    " AND position = ? AND changed_at = ?",
                    (at, item.source_id, item.position, item.changed_at),
                )
            return cursor.rowcount > 0

    # practice

    def start_session(
        self,
        session_id: str,
        language: str,
        lesson: str,
        topics: list[str],
        exercises: dict[str, int],
        words: dict[str, Any] | None = None,
        mix_topics: bool = False,
        guidance: dict[str, str] | None = None,
        lessons: list[str] | None = None,
        options: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Start a session of practice with the exercises given, each with
        how many instances of it there are to be, the `words` they are to
        use, if any, and the `guidance` each is given and the `options` it
        was chosen with, by exercise. A review has no `lesson`, and goes
        over `lessons`. A session that is still running is abandoned: there
        is one at a time. Raises ValueError."""
        guidance = guidance or {}
        options = options or {}
        if not is_id(session_id):
            raise ValueError("a session needs an id")
        if not exercises:
            raise ValueError("a session needs an exercise")
        now = self._now()
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET status = 'abandoned', finished_at = ?"
                " WHERE status = 'running'",
                (now,),
            )
            self._db.execute(
                "INSERT INTO sessions (id, language, lesson, topics, started_at,"
                " status, words, mix_topics, lessons)"
                " VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)",
                (
                    session_id,
                    language,
                    lesson,
                    json.dumps(topics),
                    now,
                    None if words is None else json.dumps(words, ensure_ascii=False),
                    int(mix_topics),
                    json.dumps(lessons or []),
                ),
            )
            self._db.executemany(
                "INSERT INTO session_exercises"
                " (session_id, exercise, position, instances, guidance, options)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        session_id,
                        exercise,
                        position,
                        instances,
                        guidance.get(exercise, ""),
                        json.dumps(options.get(exercise, {}), ensure_ascii=False),
                    )
                    for position, (exercise, instances) in enumerate(exercises.items())
                ],
            )
        session = self.session(session_id)
        assert session
        return session

    def _sessions(self, where: str, values: tuple[Any, ...]) -> list[dict[str, Any]]:
        sessions = {
            session_id: {
                "id": session_id,
                "language": language,
                "lesson": lesson,
                # those a review goes over, which has no lesson
                "lessons": json.loads(lessons),
                "topics": json.loads(topics),
                "started_at": started_at,
                "finished_at": finished_at,
                "status": status,
                "words": None if words is None else json.loads(words),
                "mix_topics": bool(mix_topics),
                "exercises": {},
                # what each exercise was told to heed, by exercise
                "guidance": {},
                # the options each exercise was chosen with, by exercise
                "options": {},
                # what can be told of each exercise from what was kept of it
                "progress": {},
            }
            for (
                session_id,
                language,
                lesson,
                topics,
                started_at,
                finished_at,
                status,
                words,
                mix_topics,
                lessons,
            ) in (
                self._db.execute(
                    "SELECT id, language, lesson, topics, started_at, finished_at,"
                    " status, words, mix_topics, lessons FROM sessions"
                    f" {where} ORDER BY started_at DESC",
                    values,
                )
            )
        }
        # how many grades of each result each exercise kept
        graded: dict[tuple[str, str], dict[str, int]] = {}
        for session_id, exercise, result, count in self._db.execute(
            "SELECT session_id, exercise, result, COUNT(*) FROM grades GROUP BY 1, 2, 3"
        ):
            if session_id in sessions:
                graded.setdefault((session_id, exercise), {})[result] = count
        for (
            session_id,
            exercise,
            instances,
            started,
            finished,
            guidance,
            options,
        ) in self._db.execute(
            "SELECT session_id, exercise, instances, state IS NOT NULL,"
            " finished_at IS NOT NULL, guidance, options FROM session_exercises"
            " ORDER BY position"
        ):
            if session_id not in sessions:
                continue
            sessions[session_id]["exercises"][exercise] = instances
            sessions[session_id]["guidance"][exercise] = guidance
            sessions[session_id]["options"][exercise] = json.loads(options)
            sessions[session_id]["progress"][exercise] = {
                "status": "finished"
                if finished
                else "started"
                if started
                else "pending",
                "answered": sum(graded.get((session_id, exercise), {}).values()),
                "results": {
                    result: graded.get((session_id, exercise), {}).get(result, 0)
                    for result in ("right", "partial", "wrong")
                },
            }
        return list(sessions.values())

    def session(self, session_id: str) -> dict[str, Any] | None:
        """A session with its exercises, and with how far each has got."""
        with self._lock:
            found = self._sessions("WHERE id = ?", (session_id,))
        return found[0] if found else None

    def sessions(self) -> list[dict[str, Any]]:
        """Every session, the latest first."""
        with self._lock:
            return self._sessions("", ())

    def end_session(self, session_id: str, status: str) -> None:
        """Bring a running session to an end, as "finished" or "abandoned"."""
        if status not in ("finished", "abandoned"):
            raise ValueError("a session ends finished or abandoned")
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET status = ?, finished_at = ?"
                " WHERE id = ? AND status = 'running'",
                (status, self._now(), session_id),
            )

    def exercise_state(
        self, session_id: str, exercise: str
    ) -> tuple[bool, Any, Any] | None:
        """Whether an exercise of a session has started, what it keeps from
        one step to the next and what it last showed, if the session has it."""
        with self._lock:
            row = self._db.execute(
                "SELECT state, shown FROM session_exercises"
                " WHERE session_id = ? AND exercise = ?",
                (session_id, exercise),
            ).fetchone()
        if row is None:
            return None
        state, shown = row
        if state is None:
            return False, None, None
        return True, json.loads(state), json.loads(shown)

    def save_exercise_state(
        self, session_id: str, exercise: str, state: Any, shown: Any
    ) -> None:
        """Keep what an exercise keeps from one step to the next, and what
        it shows, which also has it started."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE session_exercises SET state = ?, shown = ?"
                " WHERE session_id = ? AND exercise = ?",
                (
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(shown, ensure_ascii=False),
                    session_id,
                    exercise,
                ),
            )

    def finish_exercise(self, session_id: str, exercise: str, results: Any) -> None:
        """Keep what an exercise reported when it finished."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE session_exercises SET results = ?, finished_at = ?"
                " WHERE session_id = ? AND exercise = ?",
                (
                    json.dumps(results, ensure_ascii=False),
                    self._now(),
                    session_id,
                    exercise,
                ),
            )

    def results(self, session_id: str, exercise: str) -> Any:
        """What an exercise reported when it finished, if it did."""
        with self._lock:
            row = self._db.execute(
                "SELECT results FROM session_exercises"
                " WHERE session_id = ? AND exercise = ?",
                (session_id, exercise),
            ).fetchone()
        return json.loads(row[0]) if row and row[0] is not None else None

    def add_grades(
        self, session_id: str, exercise: str, grades: list[dict[str, str]]
    ) -> None:
        """Keep the grades an exercise reported, each a `{"result": ...,
        "task": ..., "answer": ..., "correction": ..., "note": ...}`. Raises
        ValueError, and keeps none, if one is not a grade."""
        rows = []
        for grade in grades:
            if grade.get("result") not in RESULTS:
                raise ValueError(
                    f"the result of a grade is one of {', '.join(RESULTS)}"
                )
            parts = [
                grade.get(name, "") for name in ("task", "answer", "correction", "note")
            ]
            if not all(isinstance(part, str) for part in parts):
                raise ValueError(
                    "the task, answer, correction and note of a grade are text"
                )
            rows.append((session_id, exercise, grade["result"], *parts))
        with self._lock, self._db:
            self._db.executemany(
                "INSERT INTO grades"
                " (session_id, exercise, result, task, answer, correction, note)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def add_written(
        self, session_id: str, exercise: str, written: dict[str, list[str]]
    ) -> None:
        """Keep what an exercise reported was written in a step, as
        `{"user": [...], "assistant": [...]}`: what the learner wrote, and
        what the models did. Raises ValueError, and keeps none of it, if it
        is not that."""
        rows = []
        now = self._now()
        for role, texts in written.items():
            if role not in ROLES:
                raise ValueError(f"what was written is by one of {', '.join(ROLES)}")
            if not isinstance(texts, list) or not all(
                isinstance(text, str) for text in texts
            ):
                raise ValueError("what was written is a list of texts")
            rows += [
                (session_id, exercise, role, text, now)
                for text in texts
                if text.strip()
            ]
        with self._lock, self._db:
            self._db.executemany(
                "INSERT INTO written (session_id, exercise, role, content, written_at)"
                " VALUES (?, ?, ?, ?, ?)",
                rows,
            )

    def written(self, session_id: str, exercise: str) -> dict[str, list[str]]:
        """What was written in an exercise of a session, by the learner as
        "user" and by the models as "assistant", in the order it was."""
        with self._lock:
            rows = self._db.execute(
                "SELECT role, content FROM written"
                " WHERE session_id = ? AND exercise = ? ORDER BY id",
                (session_id, exercise),
            ).fetchall()
        found: dict[str, list[str]] = {role: [] for role in ROLES}
        for role, content in rows:
            found[role].append(content)
        return found

    def grades(
        self, session_id: str, exercise: str | None = None
    ) -> list[dict[str, str]]:
        """The grades of a session, or of one exercise of it, in the order
        they were kept."""
        with self._lock:
            rows = self._db.execute(
                "SELECT session_id, exercise, result, task, answer, correction, note"
                " FROM grades WHERE session_id = ? AND exercise = COALESCE(?, exercise)"
                " ORDER BY id",
                (session_id, exercise),
            ).fetchall()
        names = (
            "session",
            "exercise",
            "result",
            "task",
            "answer",
            "correction",
            "note",
        )
        return [dict(zip(names, row)) for row in rows]

    def set_log(
        self, session_id: str, exercise: str, content: str, subject: str = ""
    ) -> None:
        """Keep the log of an exercise of a session, in place of any it had.
        `subject` is what it was about, the exercise if it is not given."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO logs (kind, language, subject, content,"
                " written_at, session_id, exercise)"
                " SELECT 'exercise', language, ?, ?, ?, id, ? FROM sessions"
                " WHERE id = ?",
                (subject or exercise, content, self._now(), exercise, session_id),
            )

    def logs(self, session_id: str) -> dict[str, str]:
        """The logs of the exercises of a session that have one, by exercise."""
        with self._lock:
            rows = self._db.execute(
                "SELECT exercise, content FROM logs WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        return dict(rows)

    def add_log(
        self,
        kind: str,
        language: str,
        subject: str,
        content: str,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Keep the log of something that was not an exercise of a session,
        with `source` saying where it was done, and return it as it is
        listed. Raises ValueError."""
        if kind not in LOG_KINDS or kind == "exercise":
            raise ValueError(f"there are no logs of the kind {kind!r}")
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO logs (kind, language, subject, content, written_at,"
                " source) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    kind,
                    language,
                    subject,
                    content,
                    self._now(),
                    json.dumps(source or {}),
                ),
            )
            row = self._db.execute(
                f"SELECT {_LOG_COLUMNS} FROM logs WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return _log(*row)

    def all_logs(
        self, before: int | None = None, most: int = 100
    ) -> list[dict[str, Any]]:
        """The logs of everything, the latest first: at most `most` of them,
        and only those kept before the log `before` if it is given."""
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_LOG_COLUMNS} FROM logs WHERE id < COALESCE(?, id + 1)"
                " ORDER BY id DESC LIMIT ?",
                (before, most),
            ).fetchall()
        return [_log(*row) for row in rows]

    def used_before(self, exercise: str, sessions: int) -> list[str]:
        """What `exercise` was answered with in the last `sessions` sessions
        it was in, the latest first, each once: the correction of an answer
        that had one, and else the answer."""
        with self._lock:
            rows = self._db.execute(
                "SELECT CASE WHEN grades.correction != '' THEN grades.correction"
                " ELSE grades.answer END FROM grades"
                " JOIN sessions ON sessions.id = grades.session_id"
                " WHERE grades.exercise = ? AND grades.session_id IN ("
                "  SELECT session_id FROM session_exercises"
                "  JOIN sessions ON sessions.id = session_exercises.session_id"
                "  WHERE exercise = ? ORDER BY sessions.started_at DESC LIMIT ?)"
                " ORDER BY sessions.started_at DESC, grades.id",
                (exercise, exercise, sessions),
            ).fetchall()
        return list(dict.fromkeys(text for (text,) in rows if text.strip()))

    # topics

    def topics(self) -> list[dict[str, Any]]:
        """Every topic, the newest first, with whether it has an icon."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, title, description, created_at, icon_type FROM topics"
                " ORDER BY created_at DESC"
            ).fetchall()
        return [
            {
                "id": topic_id,
                "title": title,
                "description": description,
                "created_at": created_at,
                "icon": icon_type is not None,
            }
            for topic_id, title, description, created_at, icon_type in rows
        ]

    def topic(self, topic_id: str) -> dict[str, Any] | None:
        return next((each for each in self.topics() if each["id"] == topic_id), None)

    def add_topic(self, topic_id: str, title: str, description: str) -> dict[str, Any]:
        """Keep a topic, without an icon yet. Raises ValueError."""
        if not is_id(topic_id):
            raise ValueError("a topic needs an id")
        if not title.strip():
            raise ValueError("a topic needs a title")
        with self._lock, self._db:
            self._db.execute(
                "INSERT INTO topics (id, title, description, created_at)"
                " VALUES (?, ?, ?, ?)",
                (topic_id, title.strip(), description.strip(), self._now()),
            )
        topic = self.topic(topic_id)
        assert topic
        return topic

    def add_starter_topics(self, topics: list[tuple[str, str]]) -> int:
        """Keep `topics`, each a title and what it is about, without icons,
        the first of them listed first, unless they were added before: they
        are added once, so that one deleted stays deleted. A topic of the
        same title as one there is is left out. Returns how many were
        added."""
        with self._lock, self._db:
            if self._db.execute(
                "SELECT 1 FROM kept WHERE name = 'starter_topics'"
            ).fetchone():
                return 0
            had = {
                title.casefold()
                for (title,) in self._db.execute("SELECT title FROM topics")
            }
            now = self._now()
            rows = [
                (f"starter-{number}", title, description, now - number)
                for number, (title, description) in enumerate(topics)
                if title.casefold() not in had
            ]
            self._db.executemany(
                "INSERT OR IGNORE INTO topics (id, title, description, created_at)"
                " VALUES (?, ?, ?, ?)",
                rows,
            )
            self._db.execute(
                "INSERT INTO kept (name, body) VALUES ('starter_topics', 'true')"
            )
        return len(rows)

    def delete_topic(self, topic_id: str) -> None:
        """Remove a topic and its icon. The sessions about it keep its id."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        if is_id(topic_id):
            (self._icons / topic_id).unlink(missing_ok=True)

    def save_icon(self, topic_id: str, icon: bytes, content_type: str) -> bool:
        """Keep the icon of a topic, in place of any it had. False if there
        is no such topic."""
        if not is_id(topic_id):
            return False
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE topics SET icon_type = ? WHERE id = ?", (content_type, topic_id)
            )
            if cursor.rowcount == 0:
                return False
            self._icons.mkdir(exist_ok=True)
            (self._icons / topic_id).write_bytes(icon)
        return True

    def icon(self, topic_id: str) -> tuple[bytes, str] | None:
        """The icon of a topic with the kind of file it is, if it has one."""
        with self._lock:
            row = self._db.execute(
                "SELECT icon_type FROM topics WHERE id = ?", (topic_id,)
            ).fetchone()
        file = self._icons / topic_id
        if not row or row[0] is None or not is_id(topic_id) or not file.exists():
            return None
        return file.read_bytes(), row[0]

    # embeddings

    def embedded(self, model: str) -> dict[str, bytes]:
        """Every text `model` has embedded, with its vector as it is kept."""
        with self._lock:
            return dict(
                self._db.execute(
                    "SELECT text, vector FROM embeddings WHERE model = ?", (model,)
                )
            )

    def save_embeddings(self, model: str, vectors: dict[str, bytes]) -> None:
        with self._lock, self._db:
            self._db.executemany(
                "INSERT OR REPLACE INTO embeddings (model, text, vector)"
                " VALUES (?, ?, ?)",
                [(model, text, vector) for text, vector in vectors.items()],
            )

    # usage

    def add_usage(self, entries: list[Any]) -> int:
        """Keeps what each of `entries`, as the app sends them, used, but for
        those whose id was counted already. Returns how many were kept.
        Nothing is kept if any of them is not a usage entry."""
        rows = [_usage_row(entry) for entry in entries]
        with self._lock, self._db:
            before = self._db.total_changes
            self._db.executemany(
                "INSERT OR IGNORE INTO usage (id, at, category, chat_id, model,"
                " prompt_tokens, completion_tokens, cost)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            return self._db.total_changes - before

    def usage(self, chat_id: str, since: int) -> dict[str, Any]:
        """The totals of the usage of the chat or text `chat_id`, of the
        usage from `since` on, in milliseconds since the epoch, and of all
        of it, with all of it added up for each category and model."""

        def totals(where: str = "1", values: tuple[Any, ...] = ()) -> dict[str, Any]:
            query = f"SELECT {_TOTALS} FROM usage WHERE {where}"
            return _totals(self._db.execute(query, values).fetchone())

        with self._lock:
            grouped = self._db.execute(
                f"SELECT category, model, {_TOTALS} FROM usage"
                " GROUP BY category, model"
                " ORDER BY category, SUM(cost) DESC, model"
            ).fetchall()
            return {
                "chat": totals("chat_id = ?", (chat_id,)),
                "since": totals("at >= ?", (since,)),
                "everything": totals(),
                "byModel": [
                    {"category": category, "model": model, **_totals(rest)}
                    for category, model, *rest in grouped
                ],
            }

    # settings

    def settings(self) -> dict[str, Any] | None:
        """The settings, if any were ever kept."""
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM kept WHERE name = 'settings'"
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_settings(self, settings: dict[str, Any]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO kept (name, body) VALUES ('settings', ?)",
                (json.dumps(settings, ensure_ascii=False),),
            )


def _usage_row(entry: Any) -> tuple[Any, ...]:
    """A usage entry, as the app sends it, as a row of the usage table."""
    if not isinstance(entry, dict):
        raise ValueError("a usage entry is an object")
    texts = [entry.get(name) for name in ("category", "chatId", "model")]
    counts = [entry.get(name) for name in ("at", "promptTokens", "completionTokens")]
    cost, entry_id = entry.get("cost"), entry.get("id")
    if (
        not all(isinstance(text, str) and text for text in texts)
        or not all(_is_count(count) for count in counts)
        or not (cost is None or _is_count(cost))
        or not (entry_id is None or isinstance(entry_id, str))
    ):
        raise ValueError(
            "a usage entry has a category, chatId, model, at, promptTokens,"
            " completionTokens and cost"
        )
    category, chat_id, model = texts
    # each was checked to be a number above
    at, prompt_tokens, completion_tokens = (int(count or 0) for count in counts)
    return (
        entry_id,
        at,
        category,
        chat_id,
        model,
        prompt_tokens,
        completion_tokens,
        cost,
    )


def _is_count(value: Any) -> bool:
    """Whether `value` is a number that is not below 0, which a JSON true is
    not."""
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
    )


def _totals(row: Any) -> dict[str, Any]:
    """Totals of the usage, from a row of `_TOTALS`, in the names the app
    gives them."""
    requests, prompt_tokens, completion_tokens, cost, incomplete = row
    return {
        "requests": requests,
        "promptTokens": prompt_tokens,
        "completionTokens": completion_tokens,
        "cost": cost,
        "costIncomplete": bool(incomplete),
    }
