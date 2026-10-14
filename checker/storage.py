# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What a user has written and been written: the chats with their messages,
the generated texts with their audio, and the settings. The books a user
reads are kept here as well.

Every message and every text carries when it was processed, which is not yet
until its words have been taken into the vocabulary and counted. A message
or text that is changed is to be processed again.
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
SCHEMA_VERSION = 5

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
CREATE TABLE texts (
    id TEXT PRIMARY KEY,
    -- the text with what is known about it, as the app keeps it, in JSON
    body TEXT NOT NULL,
    -- the text itself, to tell when it has changed
    content TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    changed_at REAL NOT NULL,
    processed_at REAL,
    -- the kind of file its audio is, if it has any
    audio_type TEXT
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

# the id of a sentence of a book: the place of its paragraph, and its own in it
_SENTENCE_ID = re.compile(r"\d{1,9}\.\d{1,9}")

# What is listed of a book.
_LISTED = "id, title, author, language, added_at, source, cover_type"

# An id is given by the app, and is part of the name of a file for a text.
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}")


@dataclass
class Unprocessed:
    """A message or a text whose words have not been taken into the
    vocabulary and counted yet."""

    # "message" or "text"
    kind: str
    # the id of the chat the message is in, or of the text
    source_id: str
    # where the message is in its chat, from 0; 0 for a text
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


class UserStore:
    """The chats, texts and settings of one user, in a directory of the
    user's own. It can be used from several threads."""

    def __init__(
        self, directory: str | Path, now: Callable[[], float] = time.time
    ) -> None:
        self._directory = Path(directory)
        self._directory.mkdir(parents=True, exist_ok=True)
        self._audio = self._directory / "audio"
        self._covers = self._directory / "covers"
        self._speech = self._directory / "speech"
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

    # texts

    def texts(self) -> list[dict[str, Any]]:
        """Every text, as the app keeps them."""
        with self._lock:
            rows = self._db.execute("SELECT body, processed_at FROM texts").fetchall()
        return [
            {**json.loads(body), "processed": processed_at is not None}
            for body, processed_at in rows
        ]

    def save_text(self, text_id: str, text: dict[str, Any]) -> None:
        """Keep a text as it is now. Its audio stays, and so does its having
        been processed if what it says is as it was. Raises ValueError for a
        text that is not one."""
        content = text.get("text")
        if not is_id(text_id) or text.get("id") != text_id:
            raise ValueError("a text needs the id it is kept under")
        if not isinstance(content, str):
            raise ValueError("a text needs its text")
        body = json.dumps(
            {name: value for name, value in text.items() if name != "processed"},
            ensure_ascii=False,
        )
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT content FROM texts WHERE id = ?", (text_id,)
            ).fetchone()
            if row and row[0] == content:
                self._db.execute(
                    "UPDATE texts SET body = ? WHERE id = ?", (body, text_id)
                )
            else:
                self._db.execute(
                    "INSERT INTO texts (id, body, content, language, changed_at)"
                    " VALUES (?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET"
                    " body = excluded.body, content = excluded.content,"
                    " changed_at = excluded.changed_at, processed_at = NULL",
                    (
                        text_id,
                        body,
                        content,
                        str(text.get("language") or ""),
                        self._now(),
                    ),
                )

    def delete_text(self, text_id: str) -> None:
        """Remove a text and its audio."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM texts WHERE id = ?", (text_id,))
        if is_id(text_id):
            (self._audio / text_id).unlink(missing_ok=True)

    def save_audio(self, text_id: str, audio: bytes, content_type: str) -> bool:
        """Keep the audio of a text. Returns whether there is such a text."""
        with self._lock, self._db:
            changed = self._db.execute(
                "UPDATE texts SET audio_type = ? WHERE id = ?",
                (content_type, text_id),
            ).rowcount
            if not changed:
                return False
            self._audio.mkdir(exist_ok=True)
            (self._audio / text_id).write_bytes(audio)
        return True

    def audio(self, text_id: str) -> tuple[bytes, str] | None:
        """The audio of a text with the kind of file it is, if it has any."""
        with self._lock:
            row = self._db.execute(
                "SELECT audio_type FROM texts WHERE id = ?", (text_id,)
            ).fetchone()
            file = self._audio / text_id
            if not row or not row[0] or not file.exists():
                return None
            return file.read_bytes(), row[0]

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
        """The messages and texts that are not processed, and were last
        changed before `before`, the oldest first. What the app wrote to
        start a chat with, the "system" messages, is never processed."""
        with self._lock:
            messages = self._db.execute(
                "SELECT 'message', chat_id, position, role, content, language,"
                " changed_at FROM messages JOIN chats ON chats.id = chat_id"
                " WHERE processed_at IS NULL AND changed_at < ?"
                " AND role IN ('user', 'assistant')",
                (before,),
            ).fetchall()
            texts = self._db.execute(
                "SELECT 'text', id, 0, 'assistant', content, language, changed_at"
                " FROM texts WHERE processed_at IS NULL AND changed_at < ?",
                (before,),
            ).fetchall()
        waiting = [Unprocessed(*row) for row in messages + texts]
        return sorted(waiting, key=lambda item: item.changed_at)

    def mark_processed(self, item: Unprocessed, at: float) -> bool:
        """Note that a message or a text has been processed, unless it was
        changed since it was read. Returns whether it was noted."""
        with self._lock, self._db:
            if item.kind == "text":
                cursor = self._db.execute(
                    "UPDATE texts SET processed_at = ? WHERE id = ? AND changed_at = ?",
                    (at, item.source_id, item.changed_at),
                )
            else:
                cursor = self._db.execute(
                    "UPDATE messages SET processed_at = ? WHERE chat_id = ?"
                    " AND position = ? AND changed_at = ?",
                    (at, item.source_id, item.position, item.changed_at),
                )
            return cursor.rowcount > 0

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
