# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What a user has written and been written: the chats with their messages,
what was written in the exercises of practice, and the settings. The books a
user reads are kept here as well, as their text and as the files they came
in.

Every message and everything written in an exercise carries when it was
processed, which is not yet until its words have been taken into the
vocabulary and counted. A message that is changed is to be processed again.
What was written in an exercise is processed once the exercise is over.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

# Raised with every change to the tables.
SCHEMA_VERSION = 31

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

# What came with version 3: where a book that was from the folder of books
# was from, and what told its file from a later one of the same name. Books
# are no longer taken from a folder, and the two are left empty.
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

# What came with version 16: the evaluations, mock exams of a level, each
# part of which is a session of one exercise; and for every exercise of a
# session how long it may take, when it started, the scores it reported and
# what an exam told it of the part it is.
_EVALUATIONS = """
ALTER TABLE sessions ADD COLUMN kind TEXT NOT NULL DEFAULT 'practice';
ALTER TABLE session_exercises ADD COLUMN minutes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE session_exercises ADD COLUMN started_at REAL;
ALTER TABLE session_exercises ADD COLUMN scores TEXT;
ALTER TABLE session_exercises ADD COLUMN exam TEXT NOT NULL DEFAULT '';
CREATE TABLE evaluations (
    id TEXT PRIMARY KEY,
    -- the language being learned, and the level of the exam
    language TEXT NOT NULL,
    level TEXT NOT NULL,
    -- how long it was to take, in half hours
    length INTEGER NOT NULL,
    -- whether each part had to be done in its time
    timed INTEGER NOT NULL,
    -- the parts, in the order they are done, in JSON: each with its module,
    -- its exercise, how it is set and how much it counts
    plan TEXT NOT NULL,
    -- "running", "finished" or "abandoned"
    status TEXT NOT NULL,
    -- in seconds since the epoch
    started_at REAL NOT NULL,
    finished_at REAL,
    -- the scores and whether it was passed, in JSON, once it is over
    result TEXT
);
CREATE TABLE evaluation_parts (
    evaluation_id TEXT NOT NULL REFERENCES evaluations (id) ON DELETE CASCADE,
    -- where it is among the parts of the evaluation, from 0
    position INTEGER NOT NULL,
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    PRIMARY KEY (evaluation_id, position)
);
"""

# What came with version 17: the scores are named in English, by the skill
# or the criterion they are of, not by the words of the German exams, in the
# scores of the exercises and in the plans and the results of evaluations.
_SCORE_NAMES = {
    "hoeren": "listening",
    "lesen": "reading",
    "schreiben": "writing",
    "sprechen": "speaking",
    "aufgabe": "task",
    "kohaerenz": "coherence",
    "wortschatz": "vocabulary",
    "strukturen": "structures",
    "aussprache": "pronunciation",
}
_RENAMED_SCORES = {
    **_SCORE_NAMES,
    **{
        f"{module}_{criterion}": f"{_SCORE_NAMES[module]}_{english}"
        for module in ("schreiben", "sprechen")
        for criterion, english in list(_SCORE_NAMES.items())[4:]
    },
}


def _renaming_scores(column: str) -> str:
    """`column`, of JSON, with every name of a score that is a string of
    its own renamed."""
    for old, new in _RENAMED_SCORES.items():
        column = f"replace({column}, '\"{old}\"', '\"{new}\"')"
    return column


_ENGLISH_SCORES = f"""
UPDATE session_exercises SET scores = {_renaming_scores("scores")}
    WHERE scores IS NOT NULL;
UPDATE evaluations SET plan = {_renaming_scores("plan")},
    result = {_renaming_scores("result")};
"""

# What came with version 18: the chats with the tutor, with only what the
# learner wrote and what the tutor answered; what the tutor looked up and was
# told besides is made again whenever it is needed.
_TUTOR = """
CREATE TABLE tutor_chats (
    id TEXT PRIMARY KEY,
    -- the language being learned
    language TEXT NOT NULL,
    -- in seconds since the epoch
    started_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE tutor_messages (
    chat_id TEXT NOT NULL REFERENCES tutor_chats (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    -- "user" for the learner, "assistant" for the tutor
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    -- in seconds since the epoch
    written_at REAL NOT NULL,
    PRIMARY KEY (chat_id, position)
);
"""

# What came with version 19: when a chat with the tutor was closed, after
# which nothing more is said in it, and the memories of the tutor: what it
# keeps of the learner from one chat to the next, made when a chat closes.
# A memory that is removed is kept, with why and by whom, so that what was
# forgotten can be seen.
_MEMORIES = """
ALTER TABLE tutor_chats ADD COLUMN closed_at REAL;
CREATE TABLE tutor_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    -- in seconds since the epoch
    created_at REAL NOT NULL,
    -- the chat it was made of, if it was
    chat_id TEXT,
    removed_at REAL,
    removed_why TEXT NOT NULL DEFAULT '',
    -- "tutor" or "learner"
    removed_by TEXT NOT NULL DEFAULT ''
);
"""

# What came with version 20: the texts the learner writes, such as their
# homework, and the corrections of them, which are texts too. A text that
# was corrected is locked: it stays as it was corrected.
_TEXTS = """
CREATE TABLE learner_texts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    -- in Markdown
    content TEXT NOT NULL,
    -- the language being learned when it was started
    language TEXT NOT NULL,
    -- "text" for one the learner writes, "correction" for one made of it
    kind TEXT NOT NULL CHECK (kind IN ('text', 'correction')),
    -- the text a correction is of
    corrects TEXT REFERENCES learner_texts (id) ON DELETE SET NULL,
    -- the session of practice it was corrected in
    session_id TEXT,
    -- in seconds since the epoch
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    -- when it was corrected, after which it is not changed
    locked_at REAL
);
"""
# What came with version 21: the kinds of memories of the tutor. Besides
# what it keeps of the learner for good, every chat that is closed leaves a
# recap of it, a few lines on what was done in it.
_RECAPS = """
ALTER TABLE tutor_memories ADD COLUMN kind TEXT NOT NULL DEFAULT 'fact';
"""
# What came with version 22: what else a message of a chat with the tutor
# holds besides what it says, as JSON: for an answer of the tutor, the
# messages the model was told and added on the way, with the tools it called
# and what they came to, the steps and the reasoning shown of it, and the
# exercises and mock exams it offered, each exercise with the session it was
# started as and how far it got. A chat taken up again is made of it whole.
_TUTOR_TURNS = """
ALTER TABLE tutor_messages ADD COLUMN turn TEXT NOT NULL DEFAULT '{}';
"""
# What came with version 23: the day an entry of the calendar of the tutor
# is for, as YYYY-MM-DD, a memory of what the tutor and the learner planned
# to do then; the other memories have none.
_CALENDAR = """
ALTER TABLE tutor_memories ADD COLUMN day TEXT;
"""
# What came with version 24: what the exercises made for the learner, each
# instance, such as a set of sentences, kept as a file of its own, JSON of
# the shape the manifest of its exercise declares, in exercises/, by its
# exercise and its id; and, for an exercise of a session that does again
# what one of another did, the ids of the instances it replays, in order.
_INSTANCES = """
CREATE TABLE instances (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    exercise TEXT NOT NULL,
    -- where it is among those the exercise made in the session, from 0
    position INTEGER NOT NULL,
    -- in seconds since the epoch
    made_at REAL NOT NULL
);
CREATE INDEX instances_by_exercise ON instances (session_id, exercise, position);
ALTER TABLE session_exercises ADD COLUMN replay TEXT;
"""
# What came with version 25: whether a session is hidden: one left before
# anything was done in it, kept only for what its exercises made, which can
# be done again, and listed nowhere else.
_HIDDEN = """
ALTER TABLE sessions ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0;
"""
# What came with version 26: the parts of a grade of an instance of several
# answers, such as a text with its questions, each graded as a grade is, in
# JSON, so that each is shown as it was answered; empty for one of a single
# answer.
_GRADE_PARTS = """
ALTER TABLE grades ADD COLUMN parts TEXT NOT NULL DEFAULT '[]';
"""
# What came with version 27: what the learner had to go on in what a grade
# is of, such as the text the questions were on, which is shown with it.
_GRADE_ABOUT = """
ALTER TABLE grades ADD COLUMN about TEXT NOT NULL DEFAULT '';
"""
# What came with version 28: an evaluation is of a size, from 1 to 5, the
# last the exam in full, in place of a length in half hours; one before is
# given the size nearest to its length.
_EVALUATION_SIZES = """
ALTER TABLE evaluations RENAME COLUMN length TO size;
UPDATE evaluations SET size = MIN(5, MAX(1, (size + 1) / 2));
"""
# What came with version 29: when a message of a chat with the tutor was
# processed, its words taken into the vocabulary as those of the chats are.
_TUTOR_PROCESSED = """
ALTER TABLE tutor_messages ADD COLUMN processed_at REAL;
"""

# What came with version 30: what a book lists of itself, its table of
# contents and its landmarks, in JSON as `{"contents": ..., "landmarks": ...}`.
# A book kept before has neither.
_BOOK_NAVIGATION = """
ALTER TABLE books ADD COLUMN navigation TEXT;
"""

# What came with version 31: the versions of a book, each kept as a book of
# its own, a copy of what it says: the book it is a version of, which is
# never a version itself, and what it is, in JSON as `{"kind": ...,
# "name": ...}`.
_BOOK_VERSIONS = """
ALTER TABLE books ADD COLUMN parent_id TEXT;
ALTER TABLE books ADD COLUMN version TEXT;
"""
# how far an exercise the tutor offered got
OFFER_STATUSES = ("running", "done", "abandoned")

# The kinds of memories: a "fact" of the learner that lasts, a "strategy",
# a way of holding the lessons the tutor and the learner agreed on, an
# entry of the "calendar", something they planned to do on a day, or the
# "recap" of a chat. Each line of a recap is kept, as there are a few.
MEMORY_KINDS = ("fact", "strategy", "calendar", "recap")

# the longest a text and its title may be, in characters
MAX_TEXT = 200_000
MAX_TEXT_TITLE = 200

# who may remove a memory
REMOVERS = ("tutor", "learner")

# what sessions are for: practice, or a part of an evaluation
SESSION_KINDS = ("practice", "evaluation")

# what the logs are of
LOG_KINDS = ("exercise", "translation", "question", "evaluation")
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
_LISTED = "id, title, author, language, added_at, cover_type"

# An id is given by the app, and is part of the name of a file for a topic.
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}")


# A picture an instance holds, as a data URL, which is kept as a file of its
# own beside it: the kind of file it is, and what it is in base64.
_PICTURE = re.compile(r"data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=\s]+)")


def _pictures_out(value: Any, instance_id: str, files: list[tuple[str, bytes]]) -> Any:
    """An instance with each picture it holds as a data URL taken out into
    `files`, each a name beside the instance and what it is, and named in
    its place as `{"$file": NAME, "type": ...}`."""
    if isinstance(value, dict):
        return {
            key: _pictures_out(each, instance_id, files) for key, each in value.items()
        }
    if isinstance(value, list):
        return [_pictures_out(each, instance_id, files) for each in value]
    found = _PICTURE.fullmatch(value) if isinstance(value, str) else None
    if found is None:
        return value
    kind = found.group(1)
    name = f"{instance_id}-{len(files)}.{'jpg' if kind == 'jpeg' else kind}"
    files.append((name, base64.b64decode(found.group(2))))
    return {"$file": name, "type": f"image/{kind}"}


def _pictures_in(value: Any, folder: Path) -> Any:
    """An instance as it was made, with each picture taken out of it by
    `_pictures_out` put back as a data URL."""
    if isinstance(value, list):
        return [_pictures_in(each, folder) for each in value]
    if not isinstance(value, dict):
        return value
    name = value.get("$file")
    if (
        isinstance(name, str)
        and set(value) == {"$file", "type"}
        and is_id(name.split(".")[0])
    ):
        data = base64.b64encode((folder / name).read_bytes()).decode()
        return f"data:{value['type']};base64,{data}"
    return {key: _pictures_in(each, folder) for key, each in value.items()}


# what a grade says of what was answered, each text
_GRADE_TEXTS = ("task", "answer", "correction", "note")


def _check_grade(grade: object) -> None:
    """Raises ValueError for what is not a grade."""
    if not isinstance(grade, dict) or grade.get("result") not in RESULTS:
        raise ValueError(f"the result of a grade is one of {', '.join(RESULTS)}")
    if not all(isinstance(grade.get(name, ""), str) for name in _GRADE_TEXTS):
        raise ValueError("the task, answer, correction and note of a grade are text")


def read_day(value: object) -> str:
    """A day as YYYY-MM-DD, as `value` gives it. Raises ValueError for one
    that is not a day of the calendar."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("a day is YYYY-MM-DD")
    date.fromisoformat(value)
    return value


@dataclass
class Unprocessed:
    """A message, or what was written in an exercise, whose words have not
    been taken into the vocabulary and counted yet."""

    # "message" of a chat, "tutor" for one of a chat with the tutor, or
    # "exercise"
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


_TEXT_COLUMNS = (
    "id, title, content, language, kind, corrects, session_id, created_at,"
    " updated_at, locked_at"
)


def _text(
    text_id: str,
    title: str,
    content: str,
    language: str,
    kind: str,
    corrects: str | None,
    session_id: str | None,
    created_at: float,
    updated_at: float,
    locked_at: float | None,
) -> dict[str, Any]:
    """A text as it is told."""
    return {
        "id": text_id,
        "title": title,
        "content": content,
        "language": language,
        "kind": kind,
        "corrects": corrects,
        "session": session_id,
        "createdAt": created_at,
        "updatedAt": updated_at,
        "lockedAt": locked_at,
    }


def _listed(
    book_id: str,
    title: str,
    author: str,
    language: str,
    added_at: int,
    cover_type: str | None,
) -> dict[str, Any]:
    """A book as it is listed, without what it says."""
    return {
        "id": book_id,
        "title": title,
        "author": author,
        "language": language,
        "addedAt": added_at,
        # whether there is a picture of its cover
        "cover": cover_type is not None,
    }


def _listed_version(version_id: str, added_at: int, version: str) -> dict[str, Any]:
    """A version of a book as it is listed: what it is called and what kind
    it is."""
    made = json.loads(version)
    return {
        "id": version_id,
        "name": made["name"],
        "kind": made["kind"],
        "addedAt": added_at,
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
        self._originals = self._directory / "books"
        self._speech = self._directory / "speech"
        self._icons = self._directory / "topics"
        self._instances = self._directory / "exercises"
        # the last request the tutor made to its model, for the inspector
        self._last_request = self._directory / "tutor-request.json"
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
            if version < 16:
                self._db.executescript(_EVALUATIONS)
            if version < 17:
                self._db.executescript(_ENGLISH_SCORES)
            if version < 18:
                self._db.executescript(_TUTOR)
            if version < 19:
                self._db.executescript(_MEMORIES)
            if version < 20:
                self._db.executescript(_TEXTS)
            if version < 21:
                self._db.executescript(_RECAPS)
            if version < 22:
                self._db.executescript(_TUTOR_TURNS)
            if version < 23:
                self._db.executescript(_CALENDAR)
            if version < 24:
                self._db.executescript(_INSTANCES)
            if version < 25:
                self._db.executescript(_HIDDEN)
            if version < 26:
                self._db.executescript(_GRADE_PARTS)
            if version < 27:
                self._db.executescript(_GRADE_ABOUT)
            if version < 28:
                self._db.executescript(_EVALUATION_SIZES)
            if version < 29:
                self._db.executescript(_TUTOR_PROCESSED)
            if version < 30:
                self._db.executescript(_BOOK_NAVIGATION)
            if version < 31:
                self._db.executescript(_BOOK_VERSIONS)
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

    # the tutor

    def tutor_chats(self) -> list[dict[str, Any]]:
        """Every chat with the tutor, the latest first, without its messages
        but with the first thing the learner wrote, to tell it by."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, language, started_at, updated_at, closed_at,"
                " (SELECT content FROM tutor_messages WHERE chat_id = tutor_chats.id"
                "  AND role = 'user' ORDER BY position LIMIT 1),"
                " (SELECT COUNT(*) FROM tutor_messages WHERE chat_id = tutor_chats.id)"
                " FROM tutor_chats ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {
                "id": chat_id,
                "language": language,
                "startedAt": started_at,
                "updatedAt": updated_at,
                "closedAt": closed_at,
                "first": first or "",
                "count": count,
            }
            for chat_id, language, started_at, updated_at, closed_at, first, count in rows
        ]

    def tutor_chat(self, chat_id: str) -> dict[str, Any] | None:
        """A chat with the tutor, with what the learner wrote and what the
        tutor answered in order, if there is such a chat."""
        with self._lock:
            row = self._db.execute(
                "SELECT language, started_at, updated_at, closed_at FROM tutor_chats"
                " WHERE id = ?",
                (chat_id,),
            ).fetchone()
            if row is None:
                return None
            messages = self._db.execute(
                "SELECT role, content, written_at, turn FROM tutor_messages"
                " WHERE chat_id = ? ORDER BY position",
                (chat_id,),
            ).fetchall()
        return {
            "id": chat_id,
            "language": row[0],
            "startedAt": row[1],
            "updatedAt": row[2],
            "closedAt": row[3],
            "messages": [
                {
                    "role": role,
                    "content": content,
                    "writtenAt": written_at,
                    "turn": json.loads(turn),
                }
                for role, content, written_at, turn in messages
            ],
        }

    def add_tutor_messages(
        self, chat_id: str, language: str, messages: list[dict[str, Any]]
    ) -> None:
        """Add to a chat with the tutor, which is started if there is none,
        what the learner wrote and what the tutor answered, each a `{"role":
        "user" | "assistant", "content": ..., "turn": {...}}`, `turn` being
        what else it holds, as _TUTOR_TURNS says, if anything. Raises
        ValueError, and keeps none, if one is not such a message."""
        if not is_id(chat_id):
            raise ValueError("a chat needs an id")
        for message in messages:
            if message.get("role") not in ROLES or not isinstance(
                message.get("content"), str
            ):
                raise ValueError("a message of the tutor is the learner's or its own")
            if not isinstance(message.get("turn", {}), dict):
                raise ValueError("what else a message of the tutor holds is an object")
        now = self._now()
        with self._lock, self._db:
            closed = self._db.execute(
                "SELECT closed_at FROM tutor_chats WHERE id = ?", (chat_id,)
            ).fetchone()
            if closed and closed[0] is not None:
                raise ValueError("the chat with the tutor is closed")
            self._db.execute(
                "INSERT INTO tutor_chats (id, language, started_at, updated_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET"
                " updated_at = excluded.updated_at",
                (chat_id, language, now, now),
            )
            (start,) = self._db.execute(
                "SELECT COUNT(*) FROM tutor_messages WHERE chat_id = ?", (chat_id,)
            ).fetchone()
            self._db.executemany(
                "INSERT INTO tutor_messages (chat_id, position, role, content,"
                " written_at, turn) VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        chat_id,
                        start + place,
                        message["role"],
                        message["content"],
                        now,
                        json.dumps(message.get("turn", {}), ensure_ascii=False),
                    )
                    for place, message in enumerate(messages)
                ],
            )

    def set_tutor_offer(
        self, chat_id: str, position: int, place: int, session: str, status: str
    ) -> None:
        """Note that the exercise the tutor offered at `place` among those of
        its answer at `position` in a chat was started as `session`, and got
        as far as `status`, one of OFFER_STATUSES. Raises ValueError if there
        is no such exercise, or no such status."""
        if status not in OFFER_STATUSES:
            raise ValueError(
                f"an exercise offered is one of {', '.join(OFFER_STATUSES)}"
            )
        if not is_id(session):
            raise ValueError("an exercise offered is started as a session")
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT turn FROM tutor_messages WHERE chat_id = ? AND position = ?"
                " AND role = 'assistant'",
                (chat_id, position),
            ).fetchone()
            turn = json.loads(row[0]) if row else {}
            offers = turn.get("offers")
            if not isinstance(offers, list) or not 0 <= place < len(offers):
                raise ValueError("the tutor offered no such exercise")
            offers[place] = {**offers[place], "session": session, "status": status}
            self._db.execute(
                "UPDATE tutor_messages SET turn = ? WHERE chat_id = ? AND position = ?",
                (json.dumps(turn, ensure_ascii=False), chat_id, position),
            )

    def close_tutor_chat(self, chat_id: str) -> bool:
        """Close a chat with the tutor, after which nothing more is said in
        it, and return whether it was open."""
        with self._lock, self._db:
            closed = self._db.execute(
                "UPDATE tutor_chats SET closed_at = ? WHERE id = ? AND closed_at IS NULL",
                (self._now(), chat_id),
            )
        return closed.rowcount > 0

    def memories(
        self, removed: bool = False, kind: str | None = None
    ) -> list[dict[str, Any]]:
        """The memories of the tutor, the oldest first: those it has, or
        those that were removed; of one of MEMORY_KINDS, or of every kind.
        An entry of the calendar has the `day` it is for, the others None."""
        with self._lock:
            rows = self._db.execute(
                "SELECT id, content, created_at, chat_id, removed_at, removed_why,"
                " removed_by, kind, day FROM tutor_memories"
                " WHERE (removed_at IS NULL) = ? AND kind = coalesce(?, kind)"
                " ORDER BY id",
                (not removed, kind),
            ).fetchall()
        return [
            {
                "id": memory_id,
                "content": content,
                "createdAt": created_at,
                "chat": chat_id,
                "removedAt": removed_at,
                "removedWhy": removed_why,
                "removedBy": removed_by,
                "kind": kind,
                "day": day,
            }
            for (
                memory_id,
                content,
                created_at,
                chat_id,
                removed_at,
                removed_why,
                removed_by,
                kind,
                day,
            ) in rows
        ]

    def add_memory(
        self,
        content: str,
        chat_id: str | None = None,
        kind: str = "fact",
        day: str | None = None,
    ) -> int:
        """Keep a memory of the tutor of one of MEMORY_KINDS, one of the
        calendar for its `day`, and return its id. Raises ValueError for one
        that says nothing, of another kind, or of the calendar without a day
        as YYYY-MM-DD."""
        if kind not in MEMORY_KINDS:
            raise ValueError(f"a memory is one of {', '.join(MEMORY_KINDS)}")
        if kind == "calendar":
            day = read_day(day)
        else:
            day = None
        lines = [" ".join(line.split()) for line in content.splitlines()]
        content = "\n".join(line for line in lines if line)
        if kind != "recap":
            content = " ".join(content.split())
        if not content:
            raise ValueError("a memory says something")
        with self._lock, self._db:
            cursor = self._db.execute(
                "INSERT INTO tutor_memories (content, created_at, chat_id, kind, day)"
                " VALUES (?, ?, ?, ?, ?)",
                (content, self._now(), chat_id, kind, day),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def remove_memory(self, memory_id: int, why: str, by: str) -> bool:
        """Remove a memory the tutor has, `by` the tutor or the learner, and
        return whether there was one. Raises ValueError for anyone else."""
        if by not in REMOVERS:
            raise ValueError(f"a memory is removed by one of {', '.join(REMOVERS)}")
        with self._lock, self._db:
            removed = self._db.execute(
                "UPDATE tutor_memories SET removed_at = ?, removed_why = ?,"
                " removed_by = ? WHERE id = ? AND removed_at IS NULL",
                (self._now(), why, by, memory_id),
            )
        return removed.rowcount > 0

    # texts

    def texts(self) -> list[dict[str, Any]]:
        """Every text and correction, the one changed last first, without
        what it says but with how many words it has."""
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_TEXT_COLUMNS} FROM learner_texts ORDER BY updated_at DESC"
            ).fetchall()
        return [
            {**_text(*row), "content": None, "words": len(row[2].split())}
            for row in rows
        ]

    def text(self, text_id: str) -> dict[str, Any] | None:
        """A text or a correction, with what it says, if there is one."""
        with self._lock:
            row = self._db.execute(
                f"SELECT {_TEXT_COLUMNS} FROM learner_texts WHERE id = ?", (text_id,)
            ).fetchone()
        return None if row is None else _text(*row)

    def save_text(self, text_id: str, title: str, content: str, language: str) -> None:
        """Keep a text the learner writes as it is now, starting it if there
        is none. Raises ValueError for one that is too long, or that cannot
        be changed: a text that was corrected, or a correction."""
        if not is_id(text_id):
            raise ValueError("a text needs an id")
        if len(title) > MAX_TEXT_TITLE or len(content) > MAX_TEXT:
            raise ValueError("the text is too long")
        now = self._now()
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT kind, locked_at FROM learner_texts WHERE id = ?", (text_id,)
            ).fetchone()
            if row and (row[0] != "text" or row[1] is not None):
                raise ValueError("a text that was corrected is not changed")
            self._db.execute(
                "INSERT INTO learner_texts (id, title, content, language, kind, created_at,"
                " updated_at) VALUES (?, ?, ?, ?, 'text', ?, ?) ON CONFLICT (id)"
                " DO UPDATE SET title = excluded.title, content = excluded.content,"
                " updated_at = excluded.updated_at",
                (text_id, title, content, language, now, now),
            )

    def correct_text(
        self,
        text_id: str,
        content: str,
        correction_id: str,
        correction: str,
        session_id: str,
    ) -> None:
        """Keep a text as it was when it was corrected in a session, lock it,
        and keep its correction, a text of its own. Raises ValueError for a
        text there is not, or that was corrected already."""
        now = self._now()
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT title, language, kind, locked_at FROM learner_texts WHERE id = ?",
                (text_id,),
            ).fetchone()
            if row is None or row[2] != "text" or row[3] is not None:
                raise ValueError("there is no text to correct")
            title, language = row[0], row[1]
            self._db.execute(
                "UPDATE learner_texts SET content = ?, updated_at = ?, locked_at = ?"
                " WHERE id = ?",
                (content, now, now, text_id),
            )
            self._db.execute(
                "INSERT INTO learner_texts (id, title, content, language, kind, corrects,"
                " session_id, created_at, updated_at, locked_at)"
                " VALUES (?, ?, ?, ?, 'correction', ?, ?, ?, ?, ?)",
                (
                    correction_id,
                    f"{title} (corrected)",
                    correction,
                    language,
                    text_id,
                    session_id,
                    now,
                    now,
                    now,
                ),
            )

    def delete_text(self, text_id: str) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM learner_texts WHERE id = ?", (text_id,))

    def delete_tutor_chat(self, chat_id: str) -> None:
        """Remove a chat with the tutor, the audio of what was read aloud
        of it, which is kept as that of a chat is, and its last request to
        the model, if it is the one kept."""
        with self._lock, self._db:
            self._db.execute("DELETE FROM tutor_chats WHERE id = ?", (chat_id,))
            self._db.execute("DELETE FROM book_speech WHERE book_id = ?", (chat_id,))
            if self._last_request_of(chat_id) is not None:
                self._last_request.unlink(missing_ok=True)
        if is_id(chat_id):
            shutil.rmtree(self._speech / chat_id, ignore_errors=True)

    def save_last_tutor_request(self, chat_id: str, record: dict[str, Any]) -> None:
        """Keep `record`, the last request the tutor made to its model in
        the chat `chat_id`, as the inspector shows it, in place of the one
        kept before: one is kept for the user, of whatever chat."""
        written = self._last_request.with_suffix(".tmp")
        with self._lock:
            written.write_text(
                json.dumps({**record, "chat": chat_id}, ensure_ascii=False),
                encoding="utf-8",
            )
            written.replace(self._last_request)

    def last_tutor_request(self, chat_id: str) -> dict[str, Any] | None:
        """The last request the tutor made to its model, if it was made in
        the chat `chat_id`."""
        with self._lock:
            return self._last_request_of(chat_id)

    def _last_request_of(self, chat_id: str) -> dict[str, Any] | None:
        try:
            record = json.loads(self._last_request.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return (
            record
            if isinstance(record, dict) and record.get("chat") == chat_id
            else None
        )

    # books

    def books(self) -> list[dict[str, Any]]:
        """Every book, without what it says, each with its versions, the
        one made first first. The versions are not listed as books."""
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_LISTED} FROM books WHERE parent_id IS NULL"
            ).fetchall()
            versions = self._db.execute(
                "SELECT id, parent_id, added_at, version FROM books"
                " WHERE parent_id IS NOT NULL ORDER BY added_at, rowid"
            ).fetchall()
        under: dict[str, list[dict[str, Any]]] = {}
        for version_id, parent_id, added_at, version in versions:
            under.setdefault(parent_id, []).append(
                _listed_version(version_id, added_at, version)
            )
        return [{**_listed(*row), "versions": under.get(row[0], [])} for row in rows]

    def book(self, book_id: str) -> dict[str, Any] | None:
        """A book with its paragraphs, its table of contents and its
        landmarks, if there is such a book."""
        with self._lock:
            row = self._db.execute(
                f"SELECT {_LISTED}, blocks, navigation, parent_id, version"
                " FROM books WHERE id = ?",
                (book_id,),
            ).fetchone()
        if not row:
            return None
        navigation = json.loads(row[7]) if row[7] else {}
        book = {
            **_listed(*row[:6]),
            "blocks": json.loads(row[6]),
            "contents": navigation.get("contents", []),
            "landmarks": navigation.get("landmarks", []),
        }
        if row[8]:
            book["parent"] = row[8]
            book["version"] = _listed_version(row[0], row[4], row[9])
        return book

    def add_version(
        self,
        version_id: str,
        source_id: str,
        kind: str,
        name: str,
        blocks: list[dict[str, Any]],
        contents: list[dict[str, Any]],
        landmarks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Keep a version of a book, made from the book or from another of
        its versions, `source_id`, and return it as it is listed. It is
        called what the book is, has its cover, and is kept under the book
        whichever it was made from. Raises ValueError for a source that is
        not kept, or an id that is not one."""
        if not is_id(version_id):
            raise ValueError("a version needs an id")
        with self._lock, self._db:
            source = self._db.execute(
                "SELECT title, author, language, cover_type, parent_id FROM books"
                " WHERE id = ?",
                (source_id,),
            ).fetchone()
            if not source:
                raise ValueError("no such book")
            title, author, language, cover_type, parent_id = source
            # the versions are all under the book, whichever they are made from
            parent_id = parent_id or source_id
            cover = self._covers / source_id
            if cover_type and cover.exists():
                shutil.copyfile(cover, self._covers / version_id)
            else:
                cover_type = None
            version = {"kind": kind, "name": name}
            added_at = int(self._now() * 1000)
            self._db.execute(
                "INSERT INTO books (id, title, author, language, added_at, blocks,"
                " cover_type, navigation, parent_id, version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    title,
                    author,
                    language,
                    added_at,
                    json.dumps(blocks, ensure_ascii=False),
                    cover_type,
                    json.dumps(
                        {"contents": contents, "landmarks": landmarks},
                        ensure_ascii=False,
                    ),
                    parent_id,
                    json.dumps(version, ensure_ascii=False),
                ),
            )
        return _listed_version(version_id, added_at, json.dumps(version))

    def add_book(
        self,
        book_id: str,
        title: str,
        author: str,
        language: str,
        blocks: list[dict[str, Any]],
        cover: tuple[bytes, str] | None = None,
        original: bytes | None = None,
        contents: list[dict[str, Any]] | None = None,
        landmarks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Keep a book, and return it as it is listed. `cover` is the
        picture on its cover with the kind of file it is, `original` the
        EPUB file it was read from, and `contents` and `landmarks` what it
        lists of itself. A book that was kept before stays as long ago added as it
        was. Raises ValueError for an id that is not one."""
        if not is_id(book_id):
            raise ValueError("a book needs an id")
        with self._lock, self._db:
            if cover:
                self._covers.mkdir(exist_ok=True)
                (self._covers / book_id).write_bytes(cover[0])
            else:
                (self._covers / book_id).unlink(missing_ok=True)
            if original is not None:
                self._originals.mkdir(exist_ok=True)
                (self._originals / f"{book_id}.epub").write_bytes(original)
            else:
                (self._originals / f"{book_id}.epub").unlink(missing_ok=True)
            self._db.execute(
                "INSERT INTO books (id, title, author, language, added_at, blocks,"
                " cover_type, navigation)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO UPDATE SET"
                " title = excluded.title, author = excluded.author,"
                " language = excluded.language, blocks = excluded.blocks,"
                " cover_type = excluded.cover_type,"
                " navigation = excluded.navigation",
                (
                    book_id,
                    title,
                    author,
                    language,
                    int(self._now() * 1000),
                    json.dumps(blocks, ensure_ascii=False),
                    cover[1] if cover else None,
                    json.dumps(
                        {"contents": contents or [], "landmarks": landmarks or []},
                        ensure_ascii=False,
                    ),
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

    def original(self, book_id: str) -> bytes | None:
        """The EPUB file a book was read from, if it was kept: those added
        before the files were kept have none."""
        with self._lock:
            row = self._db.execute(
                "SELECT 1 FROM books WHERE id = ?", (book_id,)
            ).fetchone()
            file = self._originals / f"{book_id}.epub"
            if not row or not is_id(book_id) or not file.exists():
                return None
            return file.read_bytes()

    def delete_book(self, book_id: str) -> None:
        """Remove a book, the file it was read from, the picture on its cover
        and the audio of its sentences, and its versions with theirs. A
        version is removed alone."""
        with self._lock, self._db:
            removed = [book_id] + [
                version_id
                for (version_id,) in self._db.execute(
                    "SELECT id FROM books WHERE parent_id = ?", (book_id,)
                )
            ]
            for each in removed:
                self._db.execute("DELETE FROM books WHERE id = ?", (each,))
                self._db.execute("DELETE FROM book_speech WHERE book_id = ?", (each,))
        for each in filter(is_id, removed):
            (self._covers / each).unlink(missing_ok=True)
            (self._originals / f"{each}.epub").unlink(missing_ok=True)
            shutil.rmtree(self._speech / each, ignore_errors=True)

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

    # processing

    def unprocessed(self, before: float) -> list[Unprocessed]:
        """The messages that are not processed, and were last changed
        before `before`, of the chats and of those with the tutor, with what
        was written in the exercises that are over, the oldest first. An
        exercise is over once it is finished or its session has ended. What
        the app wrote to start a chat with, the "system" messages, is never
        processed."""
        with self._lock:
            messages = self._db.execute(
                "SELECT 'message', chat_id, position, role, content, language,"
                " changed_at FROM messages JOIN chats ON chats.id = chat_id"
                " WHERE processed_at IS NULL AND changed_at < ?"
                " AND role IN ('user', 'assistant')",
                (before,),
            ).fetchall()
            tutor = self._db.execute(
                "SELECT 'tutor', chat_id, position, role, content, language,"
                " written_at FROM tutor_messages"
                " JOIN tutor_chats ON tutor_chats.id = chat_id"
                " WHERE processed_at IS NULL AND written_at < ?",
                (before,),
            ).fetchall()
            written = self._db.execute(
                "SELECT 'exercise', written.session_id || '/' || written.exercise,"
                " written.id, role, content, sessions.language, written_at"
                " FROM written JOIN sessions ON sessions.id = written.session_id"
                " JOIN session_exercises ON"
                " session_exercises.session_id = written.session_id"
                " AND session_exercises.exercise = written.exercise"
                # what is written in an exam is not taken in, as in a real one
                " WHERE written.processed_at IS NULL AND written_at < ?"
                " AND sessions.kind = 'practice'"
                " AND (session_exercises.finished_at IS NOT NULL"
                " OR sessions.status != 'running')",
                (before,),
            ).fetchall()
        waiting = [Unprocessed(*row) for row in messages + tutor + written]
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
            elif item.kind == "tutor":
                cursor = self._db.execute(
                    "UPDATE tutor_messages SET processed_at = ? WHERE chat_id = ?"
                    " AND position = ?",
                    (at, item.source_id, item.position),
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
        minutes: dict[str, int] | None = None,
        exams: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Start a session of practice with the exercises given, each with
        how many instances of it there are to be, the `words` they are to
        use, if any, and the `guidance` each is given, the `options` it was
        chosen with, how many `minutes` it may take, none for no limit, and
        what an exam tells it of the part it is, by exercise, which makes it
        a part of an evaluation. A review has no `lesson`, and goes over
        `lessons`. A session of the same kind that is still running is
        abandoned: there is one at a time of each. Raises ValueError."""
        guidance = guidance or {}
        options = options or {}
        minutes = minutes or {}
        exams = exams or {}
        if not is_id(session_id):
            raise ValueError("a session needs an id")
        if not exercises:
            raise ValueError("a session needs an exercise")
        kind = "evaluation" if exams else "practice"
        now = self._now()
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET status = 'abandoned', finished_at = ?"
                " WHERE status = 'running' AND kind = ?",
                (now, kind),
            )
            self._db.execute(
                "INSERT INTO sessions (id, language, lesson, topics, started_at,"
                " status, words, mix_topics, lessons, kind)"
                " VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?)",
                (
                    session_id,
                    language,
                    lesson,
                    json.dumps(topics),
                    now,
                    None if words is None else json.dumps(words, ensure_ascii=False),
                    int(mix_topics),
                    json.dumps(lessons or []),
                    kind,
                ),
            )
            self._db.executemany(
                "INSERT INTO session_exercises (session_id, exercise, position,"
                " instances, guidance, options, minutes, exam)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        session_id,
                        exercise,
                        position,
                        instances,
                        guidance.get(exercise, ""),
                        json.dumps(options.get(exercise, {}), ensure_ascii=False),
                        minutes.get(exercise, 0),
                        exams.get(exercise, ""),
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
                "kind": kind,
                # left before anything was done in it, and kept only for what
                # its exercises made
                "hidden": bool(hidden),
                "exercises": {},
                # what each exercise was told to heed, by exercise
                "guidance": {},
                # the options each exercise was chosen with, by exercise
                "options": {},
                # how many minutes each exercise may take, 0 for no limit
                "minutes": {},
                # what an exam told each exercise of the part it is
                "exams": {},
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
                kind,
                hidden,
            ) in (
                self._db.execute(
                    "SELECT id, language, lesson, topics, started_at, finished_at,"
                    " status, words, mix_topics, lessons, kind, hidden FROM sessions"
                    f" {where} ORDER BY started_at DESC",
                    values,
                )
            )
        }
        # how many instances each exercise made
        made: dict[tuple[str, str], int] = {
            (session_id, exercise): count
            for session_id, exercise, count in self._db.execute(
                "SELECT session_id, exercise, COUNT(*) FROM instances GROUP BY 1, 2"
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
            minutes,
            exam,
            started_at,
            scores,
            replay,
        ) in self._db.execute(
            "SELECT session_id, exercise, instances, state IS NOT NULL,"
            " finished_at IS NOT NULL, guidance, options, minutes, exam,"
            " started_at, scores, replay FROM session_exercises ORDER BY position"
        ):
            if session_id not in sessions:
                continue
            sessions[session_id]["exercises"][exercise] = instances
            sessions[session_id]["guidance"][exercise] = guidance
            sessions[session_id]["options"][exercise] = json.loads(options)
            sessions[session_id]["minutes"][exercise] = minutes
            sessions[session_id]["exams"][exercise] = exam
            sessions[session_id]["progress"][exercise] = {
                "status": "finished"
                if finished
                else "started"
                if started
                else "pending",
                "answered": sum(graded.get((session_id, exercise), {}).values()),
                # when it was first shown, in seconds since the epoch
                "started_at": started_at,
                # what it scored, as it reported when it finished
                "scores": None if scores is None else json.loads(scores),
                # how many of its instances are kept, which it can be done
                # again with: those it replays, or those it made
                "kept": len(json.loads(replay))
                if replay is not None
                else made.get((session_id, exercise), 0),
                # whether it does again what one of another session did
                "replays": replay is not None,
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

    def sessions(self, kind: str = "practice") -> list[dict[str, Any]]:
        """Every session of `kind`, the latest first."""
        with self._lock:
            return self._sessions("WHERE kind = ?", (kind,))

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

    def delete_session(self, session_id: str) -> None:
        """Forget a session, with what was done in it and the audio made for
        its exercises."""
        with self._lock, self._db:
            made = self._db.execute(
                "SELECT exercise, id FROM instances WHERE session_id = ?", (session_id,)
            ).fetchall()
            self._db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            for spoken in self._speech.glob(f"{session_id}-*"):
                shutil.rmtree(spoken, ignore_errors=True)
            for exercise, instance_id in made:
                folder = self._instances / exercise
                (folder / f"{instance_id}.json").unlink(missing_ok=True)
                for picture in folder.glob(f"{instance_id}-*"):
                    picture.unlink(missing_ok=True)

    def hide_session(self, session_id: str) -> None:
        """Hide a session left before anything was done in it, keeping it
        only for what its exercises made."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE sessions SET hidden = 1 WHERE id = ?", (session_id,)
            )

    def add_instances(
        self, session_id: str, exercise: str, made: list[Any]
    ) -> list[str]:
        """Keep the instances an exercise of a session made, after those it
        made before, each as a file of its own, and return their ids."""
        if not made:
            return []
        if not is_id(exercise):
            raise ValueError("an exercise has an id")
        with self._lock, self._db:
            (before,) = self._db.execute(
                "SELECT COUNT(*) FROM instances WHERE session_id = ? AND exercise = ?",
                (session_id, exercise),
            ).fetchone()
            ids = [uuid.uuid4().hex for _ in made]
            folder = self._instances / exercise
            folder.mkdir(parents=True, exist_ok=True)
            for instance_id, instance in zip(ids, made):
                files: list[tuple[str, bytes]] = []
                kept = _pictures_out(instance, instance_id, files)
                for name, data in files:
                    (folder / name).write_bytes(data)
                (folder / f"{instance_id}.json").write_text(
                    json.dumps(kept, ensure_ascii=False, indent=1),
                    encoding="utf-8",
                )
            self._db.executemany(
                "INSERT INTO instances (id, session_id, exercise, position, made_at)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (instance_id, session_id, exercise, before + number, self._now())
                    for number, instance_id in enumerate(ids)
                ],
            )
        return ids

    def set_replay(self, session_id: str, exercise: str, ids: list[str]) -> None:
        """Have an exercise of a session that has not started do again the
        instances of `ids`, in order, in place of making new ones."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE session_exercises SET replay = ?"
                " WHERE session_id = ? AND exercise = ? AND state IS NULL",
                (json.dumps(ids), session_id, exercise),
            )

    def instance_ids(self, session_id: str, exercise: str) -> list[str]:
        """The ids of the instances an exercise of a session is made of, in
        order: those it replays, or else those it made."""
        with self._lock:
            row = self._db.execute(
                "SELECT replay FROM session_exercises"
                " WHERE session_id = ? AND exercise = ?",
                (session_id, exercise),
            ).fetchone()
            if row and row[0] is not None:
                replayed: list[str] = json.loads(row[0])
                return replayed
            return [
                instance_id
                for (instance_id,) in self._db.execute(
                    "SELECT id FROM instances WHERE session_id = ? AND exercise = ?"
                    " ORDER BY position",
                    (session_id, exercise),
                )
            ]

    def instances(self, exercise: str, ids: list[str]) -> list[Any]:
        """The instances of an exercise by their ids, in order. Raises
        ValueError for one that is not kept."""
        found = []
        for instance_id in ids:
            file = self._instances / exercise / f"{instance_id}.json"
            if not (is_id(exercise) and is_id(instance_id) and file.is_file()):
                raise ValueError(f"the instance {instance_id} of {exercise} is gone")
            try:
                found.append(
                    _pictures_in(
                        json.loads(file.read_text(encoding="utf-8")),
                        self._instances / exercise,
                    )
                )
            except OSError:
                raise ValueError(
                    f"a picture of the instance {instance_id} of {exercise} is gone"
                ) from None
        return found

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
        it shows, which also has it started, at the time of the first."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE session_exercises SET state = ?, shown = ?,"
                " started_at = COALESCE(started_at, ?)"
                " WHERE session_id = ? AND exercise = ?",
                (
                    json.dumps(state, ensure_ascii=False),
                    json.dumps(shown, ensure_ascii=False),
                    self._now(),
                    session_id,
                    exercise,
                ),
            )

    def finish_exercise(
        self,
        session_id: str,
        exercise: str,
        results: Any,
        scores: dict[str, float] | None = None,
    ) -> None:
        """Keep what an exercise reported when it finished, with the scores
        it came to, if it reported any."""
        with self._lock, self._db:
            self._db.execute(
                "UPDATE session_exercises SET results = ?, scores = ?,"
                " finished_at = ? WHERE session_id = ? AND exercise = ?",
                (
                    json.dumps(results, ensure_ascii=False),
                    None if scores is None else json.dumps(scores),
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
        self, session_id: str, exercise: str, grades: list[dict[str, Any]]
    ) -> None:
        """Keep the grades an exercise reported, each a `{"result": ...,
        "task": ..., "answer": ..., "correction": ..., "note": ...}`, with
        the `parts` it is made of, each graded as a grade is, if any, and
        what the learner had to go on, `about`, such as a text. Raises
        ValueError, and keeps none, if one is not a grade."""
        rows = []
        for grade in grades:
            parts = grade.get("parts") or []
            if not isinstance(parts, list):
                raise ValueError("the parts of a grade are a list of grades")
            for each in [grade, *parts]:
                _check_grade(each)
            about = grade.get("about", "")
            if not isinstance(about, str):
                raise ValueError("what a grade is about is text")
            rows.append(
                (
                    session_id,
                    exercise,
                    grade["result"],
                    *(grade.get(name, "") for name in _GRADE_TEXTS),
                    json.dumps(
                        [
                            {
                                "result": each["result"],
                                **{name: each.get(name, "") for name in _GRADE_TEXTS},
                            }
                            for each in parts
                        ],
                        ensure_ascii=False,
                    ),
                    about,
                )
            )
        with self._lock, self._db:
            self._db.executemany(
                "INSERT INTO grades (session_id, exercise, result, task, answer,"
                " correction, note, parts, about) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
    ) -> list[dict[str, Any]]:
        """The grades of a session, or of one exercise of it, in the order
        they were kept, each with the `parts` it is made of."""
        with self._lock:
            rows = self._db.execute(
                "SELECT session_id, exercise, result, task, answer, correction, note,"
                " parts, about FROM grades"
                " WHERE session_id = ? AND exercise = COALESCE(?, exercise)"
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
        return [
            {
                **dict(zip(names, row[:-2])),
                "parts": json.loads(row[-2]),
                "about": row[-1],
            }
            for row in rows
        ]

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

    # evaluations

    def start_evaluation(
        self,
        evaluation_id: str,
        language: str,
        level: str,
        size: int,
        timed: bool,
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        """Start an evaluation of `level` made of the parts of `plan`. One
        that is still running is abandoned: there is one at a time. Raises
        ValueError."""
        if not is_id(evaluation_id):
            raise ValueError("an evaluation needs an id")
        if not plan.get("parts"):
            raise ValueError("an evaluation needs a part")
        now = self._now()
        with self._lock, self._db:
            self._db.execute(
                "UPDATE evaluations SET status = 'abandoned', finished_at = ?"
                " WHERE status = 'running'",
                (now,),
            )
            self._db.execute(
                "INSERT INTO evaluations (id, language, level, size, timed, plan,"
                " status, started_at) VALUES (?, ?, ?, ?, ?, ?, 'running', ?)",
                (
                    evaluation_id,
                    language,
                    level,
                    size,
                    int(timed),
                    json.dumps(plan, ensure_ascii=False),
                    now,
                ),
            )
        evaluation = self.evaluation(evaluation_id)
        assert evaluation
        return evaluation

    def _evaluations(self, where: str, values: tuple[Any, ...]) -> list[dict[str, Any]]:
        evaluations = {
            evaluation_id: {
                "id": evaluation_id,
                "language": language,
                "level": level,
                "size": size,
                "timed": bool(timed),
                "plan": json.loads(plan),
                "status": status,
                "started_at": started_at,
                "finished_at": finished_at,
                "result": None if result is None else json.loads(result),
                # the session of each part that was started, by its place
                "sessions": {},
            }
            for (
                evaluation_id,
                language,
                level,
                size,
                timed,
                plan,
                status,
                started_at,
                finished_at,
                result,
            ) in self._db.execute(
                "SELECT id, language, level, size, timed, plan, status,"
                f" started_at, finished_at, result FROM evaluations {where}"
                " ORDER BY started_at DESC",
                values,
            )
        }
        for evaluation_id, position, session_id in self._db.execute(
            "SELECT evaluation_id, position, session_id FROM evaluation_parts"
        ):
            if evaluation_id in evaluations:
                evaluations[evaluation_id]["sessions"][str(position)] = session_id
        return list(evaluations.values())

    def evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        """An evaluation, with the sessions of the parts that were started."""
        with self._lock:
            found = self._evaluations("WHERE id = ?", (evaluation_id,))
        return found[0] if found else None

    def evaluations(self) -> list[dict[str, Any]]:
        """Every evaluation, the latest first."""
        with self._lock:
            return self._evaluations("", ())

    def add_part(self, evaluation_id: str, position: int, session_id: str) -> None:
        """Note the session a part of an evaluation is done in, in place of
        any it was in before."""
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO evaluation_parts"
                " (evaluation_id, position, session_id) VALUES (?, ?, ?)",
                (evaluation_id, position, session_id),
            )

    def end_evaluation(self, evaluation_id: str, status: str, result: Any) -> None:
        """Bring a running evaluation to an end, as "finished" or
        "abandoned", with what it came to."""
        if status not in ("finished", "abandoned"):
            raise ValueError("an evaluation ends finished or abandoned")
        with self._lock, self._db:
            self._db.execute(
                "UPDATE evaluations SET status = ?, finished_at = ?, result = ?"
                " WHERE id = ? AND status = 'running'",
                (
                    status,
                    self._now(),
                    json.dumps(result, ensure_ascii=False),
                    evaluation_id,
                ),
            )

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

    def add_starter_topics(
        self,
        topics: list[tuple[str, str]],
        icon_of: Callable[[str], bytes | None] = lambda _: None,
    ) -> int:
        """Keep `topics`, each a title and what it is about, with the PNG
        icon `icon_of` gives by its title, if any, the first of them listed
        first, unless they were added before: they are added once, so that
        one deleted stays deleted. A topic of the same title as one there is
        is left out. Returns how many were added."""
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
        for topic_id, title, _, _ in rows:
            icon = icon_of(title)
            if icon is not None:
                self.save_icon(topic_id, icon, "image/png")
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

    def usage_series(
        self, since: int, bin_ms: int, offset_ms: int
    ) -> list[dict[str, Any]]:
        """The usage from `since` on, in milliseconds since the epoch, added
        up for each category and model in bins of `bin_ms`, such as an hour
        or a day, where the learner is `offset_ms` ahead of UTC, so that a
        day is theirs. Each bin is told by when it starts, the earliest
        first."""
        with self._lock:
            rows = self._db.execute(
                f"SELECT ((at + ?) / ?) * ? - ?, category, model, {_TOTALS}"
                " FROM usage WHERE at >= ?"
                " GROUP BY 1, category, model ORDER BY 1, category, model",
                (offset_ms, bin_ms, bin_ms, offset_ms, since),
            ).fetchall()
        return [
            {"at": at, "category": category, "model": model, **_totals(rest)}
            for at, category, model, *rest in rows
        ]

    # settings

    def settings(self) -> dict[str, Any] | None:
        """The settings, if any were ever kept."""
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM kept WHERE name = 'settings'"
            ).fetchone()
        return json.loads(row[0]) if row else None

    def skipped_anki_decks(self) -> list[int]:
        """The ids of the Anki decks whose words are left out. Every other
        deck's are had, those made later too."""
        with self._lock:
            row = self._db.execute(
                "SELECT body FROM kept WHERE name = 'skipped_anki_decks'"
            ).fetchone()
        return [int(deck_id) for deck_id in json.loads(row[0])] if row else []

    def save_skipped_anki_decks(self, decks: list[int]) -> None:
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO kept (name, body)"
                " VALUES ('skipped_anki_decks', ?)",
                (json.dumps(decks),),
            )

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
