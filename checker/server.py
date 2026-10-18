# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""A small local server the chat sends what is being typed to.

It splits the text into sentences, spell-checks each one, has each finished
sentence profiled, prints what it finds, and returns the sentences.

It also takes lists of words into the vocabulary, and shows what is in it.
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from anki_import import DECK_STATUS_URL, AnkiImporter, fetch_anki_notes
from book_sync import BookSync
from books import BookError, read_epub
from categories import CATEGORIES
from evaluating import EvaluationError, Evaluations
from exercising import (
    Asker,
    Choosing,
    Drawer,
    ExerciseError,
    Practice,
    model_asker,
    model_drawer,
    ui_file,
)
from grammar import GrammarError
from intake import (
    DEFAULT_LANGUAGE,
    MAX_WORDS,
    Intake,
    Outcome,
    Word,
    read_words,
    send_chat,
)
from live import LiveChecker
from logs import LogError
from lookups import asked_anything, translation_log, write_question_logs
from models import Model, read_model
from processing import Processor, words_in
from profiling import (
    DEFAULT_MODEL,
    Profile,
    ProfileError,
    Profiler,
    Questions,
    WordRating,
    read_questions,
)
from sentences import Sentence
from speaking import (
    MAX_SENTENCES,
    BookSentence,
    Speaker,
    SpeechError,
    sentences_between,
    sentences_of_message,
)
from spelling import StudySpeller
from starter_topics import STARTER_TOPICS
from storage import UserStore
from tasks import Tasks
from topics import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_IMAGE_MODEL,
    EMBED_BATCH,
)
from translating import (
    DEFAULT_INTO,
    MAX_SELECTION_LENGTH,
    Passage,
    TranslationError,
    Translator,
    passage_of,
    read_messages,
)
from users import Users, take_vocabulary, user_directory
from vocabulary import Vocabularies, Vocabulary

HOST = "127.0.0.1"
# The request header the chat sends its OpenRouter key in.
KEY_HEADER = "X-OpenRouter-Key"
# how long a model at an address the chat passes a request on to may take
RELAY_TIMEOUT_SECS = 120
# how long a server is given to list its models
LIST_TIMEOUT_SECS = 10
DEFAULT_PORT = 8092
# far more than anyone types into a chat box
MAX_BODY_BYTES = 1_000_000
# a book with many pictures in it, which are not kept
MAX_BOOK_BYTES = 200_000_000
# the request header the name of the file of a book comes in, encoded as in a URL
FILE_NAME_HEADER = "X-File-Name"
# no folder is named in more
MAX_PATH_LENGTH = 1000
# How much of the text on either side of a selection is looked at for the
# sentences its words are in.
MAX_AROUND_LENGTH = 2000
# how much of a selection a task that is about it is told by
MAX_TITLE_LENGTH = 80
# How long the audio of a sentence that is being made is waited for before
# whoever asked for it is told to ask again.
SPEECH_WAIT_SECS = 50.0
# a language is named in a word or two
MAX_LANGUAGE_LENGTH = 40
# a topic is told by a title and a sentence or two
MAX_TOPIC_LENGTH = 500
# more words than any set of them has
MAX_SET_WORDS = 20_000
# where something was done is told in a few names and ids, in JSON
MAX_WHERE_LENGTH = 2000
# how many logs are sent at a time
LOGS_AT_A_TIME = 100
# The directory everything is kept in, unless CHECKER_DATA names another:
# who may log in, and for each user a directory with the vocabularies, one
# file for each language.
DATA_DIRECTORY = Path(__file__).parent / "data"
# The file that says who may log in, unless CHECKER_USERS names another. It
# is edited by hand, and read every time someone logs in.
USERS_FILE = Path(__file__).parent.parent / "users.json"
# The user whose collection the deck-status server keeps, unless
# CHECKER_ANKI_USER names another. The Anki words are imported for nobody else.
ANKI_USER = "cian_cl"


def describe(sentences: list[Sentence]) -> str:
    """The lines printed for one text that was received."""
    if not sentences:
        return "(no sentences)"
    lines = []
    for number, sentence in enumerate(sentences, start=1):
        state = "done" if sentence.complete else "typing"
        if sentence.processed:
            state += ", processed"
        elif sentence.profiling:
            state += ", profiling"
        lines.append(f"  {number}. [{state}] {sentence.text}")
        for issue in sentence.spelling:
            suggestions = ", ".join(issue.suggestions) or "no suggestions"
            lines.append(f"       spelling: {issue.word} -> {suggestions}")
        if sentence.profile:
            lines.append(f"       profile: {describe_profile(sentence.profile)}")
        if sentence.profile_error:
            lines.append(f"       profile failed: {sentence.profile_error}")
    return "\n".join(lines)


def describe_profile(profile: Profile) -> str:
    """A profile on one line, such as `grammar_errors=one (87%), clarity=2.6/3`."""
    parts = []
    for name, answer in profile.answers.items():
        if answer.kind == "choice":
            part = f"{name}={answer.choice}"
        elif answer.kind == "noul":
            part = f"{name}={answer.yes:.2f}"
        else:
            part = f"{name}={answer.score:.1f}/{answer.max_score}"
        if answer.confidence is not None:
            part += f" ({answer.confidence:.0%})"
        parts.append(part)
    return ", ".join(parts)


def print_profile(
    sentence: str, profile: Profile | None, error: str | None, dropped: bool
) -> None:
    """Announces the answer to a question that has just come back."""
    result = describe_profile(profile) if profile else f"failed: {error}"
    if dropped:
        result += " (dropped: the sentence was changed or gone back to)"
    log(f"{datetime.now():%H:%M:%S} answered: {sentence}\n       {result}")


def print_ratings(
    sentence: str, ratings: list[WordRating] | None, error: str | None, dropped: bool
) -> None:
    """Announces how right the words of a sentence were found to be."""
    if ratings:
        result = ", ".join(f"{rating.word} {rating.value:.2f}" for rating in ratings)
    else:
        result = f"failed: {error}"
    if dropped:
        result += " (dropped: the sentence was changed or gone back to)"
    log(f"{datetime.now():%H:%M:%S} words: {sentence}\n       {result}")


def in_background(
    tasks: Tasks, kind: str
) -> Callable[[str, Callable[[], list[Profile]]], None]:
    """What does a job of practice as a task of `kind`, such as writing the
    log of an exercise."""

    def start(title: str, job: Callable[[], list[Profile]]) -> None:
        tasks.start(
            kind,
            title,
            1,
            lambda step: ([], [describe_usage(profile) for profile in job()]),
        )

    return start


def describe_usage(profile: Profile) -> dict[str, object]:
    """What one request to the model used, for whoever keeps count."""
    return {
        "id": profile.id,
        "model": profile.model,
        "input_tokens": profile.input_tokens,
        "output_tokens": profile.output_tokens,
        "cost": profile.cost,
    }


def describe_outcomes(outcomes: list[Outcome]) -> str:
    """The lines printed for a list of words that was taken in."""
    lines = []
    for outcome in outcomes:
        line = f"  {outcome.word}: {outcome.status}"
        if outcome.category:
            line += f" ({outcome.category})"
        if outcome.entry:
            line += f" -> {outcome.entry.lemma}, {len(outcome.entry.forms)} forms"
        if outcome.reason:
            line += f": {outcome.reason}"
        lines.append(line)
    return "\n".join(lines)


_log_lock = threading.Lock()


def log(entry: str) -> None:
    """Prints one entry at a time, as requests and profiles finish on
    different threads and their lines would otherwise run into each other."""
    with _log_lock:
        print(entry, flush=True)


@dataclass
class Account:
    """What one user has: the checks of what they type, and the vocabulary
    with what brings words into it."""

    checker: LiveChecker
    intake: Intake | None = None
    importer: AnkiImporter | None = None
    # the chats, the practice and the settings of the user
    store: UserStore | None = None
    # what takes the words of the chats and the exercises into the vocabulary
    processor: Processor | None = None
    # whether the Anki words are this user's, and so are imported
    anki: bool = True
    # what takes the books of a folder into those the user reads
    book_sync: BookSync | None = None
    # what translates a selection, and answers what is asked about it
    translator: Translator | None = None
    # the language being studied, by its English name
    language: str = DEFAULT_LANGUAGE
    # what reads the sentences of the books aloud
    speaker: Speaker | None = None
    # what is done for the user in the background
    tasks: Tasks = field(default_factory=Tasks)
    # the sessions of practice, with the exercises done in them
    practice: Practice | None = None
    # the evaluations, mock exams made of the exercises of practice
    evaluations: Evaluations | None = None

    def study(self, language: str) -> None:
        """Have every part go by `language`, given by its English name."""
        self.language = language
        self.checker.study(language)
        if self.intake:
            self.intake.language = language


class Accounts:
    """The account of each user, made the first time the user asks for
    anything."""

    def __init__(self, make: Callable[[str], Account]) -> None:
        self._make = make
        self._accounts: dict[str, Account] = {}
        self._lock = threading.Lock()

    def of(self, user: str) -> Account:
        with self._lock:
            if user not in self._accounts:
                self._accounts[user] = self._make(user)
            return self._accounts[user]


class CheckerServer(ThreadingHTTPServer):
    def __init__(
        self, port: int, accounts: Accounts, users: Users | None = None
    ) -> None:
        super().__init__((HOST, port), CheckerHandler)
        self.accounts = accounts
        # Those who may log in. Without them there is no logging in, and one
        # account for whoever asks.
        self.users = users


class CheckerHandler(BaseHTTPRequestHandler):
    server: CheckerServer
    # the account of whoever sent the request
    account: Account

    def _find_account(self) -> bool:
        """Find out whose request this is, by the token it came with. If it
        cannot be told, the request is refused, and False returned."""
        users = self.server.users
        if users is None:
            self.account = self.server.accounts.of("")
            return True
        scheme, _, token = (self.headers.get("Authorization") or "").partition(" ")
        user = users.user_of(token.strip()) if scheme == "Bearer" else None
        if user is None:
            self._reply(HTTPStatus.UNAUTHORIZED, {"error": "log in first"})
            return False
        self.account = self.server.accounts.of(user)
        return True

    def _log_in(self) -> None:
        """Answers a `{"user": ..., "password": ...}` with a token to send
        with every other request, if there is such a user."""
        users = self.server.users
        body = self._read_body()
        user, password = body.get("user"), body.get("password")
        if users is None or not isinstance(user, str) or not isinstance(password, str):
            raise ValueError('expected {"user": "...", "password": "..."}')
        if not users.check(user, password):
            self._reply(HTTPStatus.UNAUTHORIZED, {"error": "wrong name or password"})
            return
        self._reply(HTTPStatus.OK, {"user": user, "token": users.token(user)})

    def do_PUT(self) -> None:
        if not self._find_account() or self._kept("PUT") or self._sets("PUT"):
            return
        try:
            if self._books("PUT") or self._speech("PUT"):
                return
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})

    def do_DELETE(self) -> None:
        if not self._find_account() or self._kept("DELETE") or self._sets("DELETE"):
            return
        if self._books("DELETE") or self._speech("DELETE") or self._topics("DELETE"):
            return
        self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})

    def _sets(self, method: str) -> bool:
        """Answers a request about the sets of words picked out of a
        vocabulary, and returns whether the request was one. The vocabulary
        is that of the `language` the request names.

            GET /vocabulary/sets?language=L             the sets
            PUT, DELETE /vocabulary/sets/ID?language=L  keep or remove one
        """
        intake = self.account.intake
        url = urlsplit(self.path)
        one = re.fullmatch(r"/vocabulary/sets/([^/]+)", url.path)
        if intake is None or not (one or url.path == "/vocabulary/sets"):
            return False
        language = parse_qs(url.query).get("language", [""])[0].strip()
        language = language[:MAX_LANGUAGE_LENGTH] or intake.language
        try:
            if method == "GET" and not one:
                # asking after a language does not make a vocabulary of it
                kept = intake.has_vocabulary(language)
                sets = intake.vocabulary_of(language).sets() if kept else []
                self._reply(HTTPStatus.OK, {"sets": sets})
            elif method == "PUT" and one:
                intake.vocabulary_of(language).save_set(one.group(1), self._read_body())
                self._reply(HTTPStatus.OK, {})
            elif method == "DELETE" and one:
                if intake.has_vocabulary(language):
                    intake.vocabulary_of(language).delete_set(one.group(1))
                self._reply(HTTPStatus.OK, {})
            else:
                return False
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        return True

    def _books(self, method: str) -> bool:
        """Answers a request about the books the user reads, and returns
        whether the request was one.

            GET /books         the books, without what they say
            POST /books        keep the EPUB file that is sent, as its text
                               and how large each part of it is written
            GET /books/ID      a book with its paragraphs
            GET /books/ID/cover  the picture on its cover, as a file
            DELETE /books/ID   remove a book
            GET /books/folder  the folder the books are taken from, and
                               what the taking of them is doing
            PUT /books/folder  take the books from the `{"folder": ...}`
                               that is sent from now on, or from none
            POST /books/sync   look through the folder now
        """
        store = self.account.store
        sync = self.account.book_sync
        path = urlsplit(self.path).path
        one = re.fullmatch(r"/books/([^/]+)", path)
        cover = re.fullmatch(r"/books/([^/]+)/cover", path)
        if store is None or not (one or cover or path == "/books"):
            return False
        if cover:
            picture = store.cover(cover.group(1)) if method == "GET" else None
            if picture is None:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no cover"})
                return True
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", picture[1])
            self.send_header("Content-Length", str(len(picture[0])))
            self.end_headers()
            self.wfile.write(picture[0])
            return True
        if sync and path in ("/books/folder", "/books/sync"):
            if method == "PUT" and path == "/books/folder":
                folder = self._read_body().get("folder")
                if not isinstance(folder, str) or len(folder) > MAX_PATH_LENGTH:
                    raise ValueError('expected {"folder": "..."}')
                sync.choose(folder)
            elif method == "POST" and path == "/books/sync":
                sync.start()
            elif method != "GET" or path != "/books/folder":
                return False
            self._reply(HTTPStatus.OK, asdict(sync.status()))
        elif method == "GET" and not one:
            self._reply(HTTPStatus.OK, {"books": store.books()})
        elif method == "POST" and not one:
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BOOK_BYTES:
                raise ValueError("the book is too large")
            name = unquote(self.headers.get(FILE_NAME_HEADER) or "")
            try:
                book = read_epub(self.rfile.read(length), Path(name).stem[:200])
            except BookError as error:
                raise ValueError(str(error)) from None
            listed = store.add_book(
                uuid.uuid4().hex,
                book.title,
                book.author,
                book.language,
                [block.kept() for block in book.blocks],
                cover=book.cover,
            )
            log(
                f"{datetime.now():%H:%M:%S} book added: {book.title}"
                f" ({len(book.blocks)} paragraphs)"
            )
            self._reply(HTTPStatus.OK, listed)
        elif method == "GET" and one:
            found = store.book(one.group(1))
            if found:
                self._reply(HTTPStatus.OK, found)
            else:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such book"})
        elif method == "DELETE" and one:
            store.delete_book(one.group(1))
            self._reply(HTTPStatus.OK, {})
        else:
            return False
        return True

    def _speech(self, method: str, api_key: str | None = None) -> bool:
        """Answers a request about the reading aloud of a book, of a
        message of a chat, or of a text of an exercise of a session, and
        returns whether the request was one. For a chat the paths start with
        /chats/ID in place of /books/ID, and for an exercise of a session
        with /sessions/SESSION-EXERCISE.

            POST /books/ID/speech        have the sentences read that a
                                         selection has all or part of
            GET /books/ID/speech/S       the audio of the sentence S, as a
                                         file; one being made is waited for
            PUT /books/ID/speech/R       say where the listener of the
                                         reading R is, as `{"at": ...}`
            DELETE /books/ID/speech/R    leave the rest of the reading R
                                         unread

        A POST brings `{"start_block": ..., "start": ..., "end_block": ...,
        "end": ..., "model": ..., "voice": ..., "instructions": ...}`: the
        selection goes from `start` in the text of the paragraph
        `start_block` to `end` in that of `end_block`. The reply lists the
        `sentences`, each with its id, where it is, and whether its audio
        is `ready`. The audio that is not is made in the background, as the
        `task` of the reply, whose `reading` is what a PUT and a DELETE
        name; there is none if all of it is kept.

        A POST for a chat brings `{"message": ..., "text": ..., "model":
        ..., "voice": ..., "instructions": ...}` in place of a selection:
        the place of the message among the messages of the chat, and what
        it says, every sentence of which is read. A POST for a session
        brings the same, with the number an exercise gives the text in
        place of that of a message.
        """
        store, speaker = self.account.store, self.account.speaker
        path = urlsplit(self.path).path
        found = re.fullmatch(
            r"/(books|chats|sessions)/([^/]+)/speech(?:/([^/]+))?", path
        )
        if store is None or speaker is None or not found:
            return False
        kind, book_id, name = found.groups()
        if method == "POST" and name is None:
            self._read_aloud(speaker, store, kind, book_id, api_key or "")
        elif method == "GET" and name:
            try:
                audio, kind = speaker.audio(book_id, name, SPEECH_WAIT_SECS)
            except SpeechError as error:
                self._reply(HTTPStatus.NOT_FOUND, {"error": str(error)})
                return True
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(audio)))
            self.end_headers()
            self.wfile.write(audio)
        elif method == "PUT" and name:
            at = self._read_body().get("at")
            if not isinstance(at, int) or isinstance(at, bool):
                raise ValueError('expected {"at": a whole number}')
            speaker.listen_at(name, at)
            self._reply(HTTPStatus.OK, {})
        elif method == "DELETE" and name:
            speaker.stop(name)
            self._reply(HTTPStatus.OK, {})
        else:
            return False
        return True

    def _read_aloud(
        self, speaker: Speaker, store: UserStore, kind: str, book_id: str, api_key: str
    ) -> None:
        """Has what a POST names read aloud: the sentences of a selection
        of the book, or those of a message of the chat or of a text of the
        session, that goes by `book_id`. `kind` says which it is."""
        body = self._read_body()
        places: list[int] = [
            place
            for name in ("start_block", "start", "end_block", "end")
            if isinstance(place := body.get(name), int) and not isinstance(place, bool)
        ]
        message, text = body.get("message"), body.get("text")
        if kind == "books" and len(places) != 4:
            raise ValueError('expected {"start_block": ..., "start": ..., ...}')
        if kind != "books" and not (
            isinstance(message, int)
            and not isinstance(message, bool)
            and message >= 0
            and isinstance(text, str)
        ):
            raise ValueError('expected {"message": ..., "text": "..."}')
        model, voice = read_model(body.get("model"), api_key), body.get("voice")
        if not (model.name and isinstance(voice, str) and voice):
            raise ValueError("a model and a voice must be named")
        instructions = body.get("instructions")
        if not isinstance(instructions, str):
            instructions = ""
        sentences: list[BookSentence]
        if kind != "books":
            # what they are was looked into above
            assert isinstance(text, str) and isinstance(message, int)
            sentences = sentences_of_message(text, message)
        else:
            book = store.book(book_id)
            if book is None:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such book"})
                return
            sentences = sentences_between(book["blocks"], *places)
        if not sentences:
            raise ValueError("there is no sentence in the selection")
        if len(sentences) > MAX_SENTENCES:
            raise ValueError(f"more than {MAX_SENTENCES} sentences are selected")
        ready = speaker.kept(book_id, sentences, model.name, voice)
        missing = [number for number, kept in enumerate(ready) if not kept]
        task = None
        if missing and not model.has_key:
            self._reply(
                HTTPStatus.BAD_GATEWAY, {"error": "an OpenRouter key is needed"}
            )
            return
        if missing:
            to_make = [sentences[number] for number in missing]
            reading = speaker.start(book_id, to_make)

            def make(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
                outcomes = speaker.make(
                    reading,
                    book_id,
                    to_make,
                    model,
                    voice,
                    instructions,
                    step,
                    missing,
                )
                return outcomes, []

            title = " ".join(sentences[0].text.split())[:MAX_TITLE_LENGTH]
            task = self.account.tasks.start("speech", title, len(to_make), make)
            task["reading"] = reading
        self._reply(
            HTTPStatus.OK,
            {
                "sentences": [
                    {**asdict(sentence), "ready": kept}
                    for sentence, kept in zip(sentences, ready)
                ],
                "task": task,
            },
        )

    def _kept(self, method: str) -> bool:
        """Answers a request about what the user has kept: the chats and
        the settings. Returns whether the request was one of those.

            GET /chats                the chats, each with its messages
            PUT, DELETE /chats/ID     keep a chat as it is sent, or remove it
            GET, PUT /settings        the settings
            POST /usage               keep what requests to models used,
                                      sent as {"entries": [...]}
            GET /usage?chat=ID&since=MS
                                      the totals of the usage of a chat, of
                                      that from a time on, and of
                                      all of it, by category and model too
            GET /logs?before=ID       the logs of everything the user did,
                                      the latest first, a hundred at a time
        """
        store = self.account.store
        path = urlsplit(self.path).path
        one = re.fullmatch(r"/chats/([^/]+)", path)
        listed = ("/chats", "/settings", "/usage", "/logs")
        if store is None or not (one or path in listed):
            return False
        try:
            if method == "GET" and path == "/chats":
                self._reply(HTTPStatus.OK, {"chats": store.chats()})
            elif method == "GET" and path == "/settings":
                self._reply(HTTPStatus.OK, {"settings": store.settings()})
            elif method == "PUT" and path == "/settings":
                store.save_settings(self._read_body())
                self._reply(HTTPStatus.OK, {})
            elif method == "POST" and path == "/usage":
                entries = self._read_body().get("entries")
                if not isinstance(entries, list):
                    raise ValueError('expected {"entries": [...]}')
                self._reply(HTTPStatus.OK, {"kept": store.add_usage(entries)})
            elif method == "GET" and path == "/usage":
                query = parse_qs(urlsplit(self.path).query)
                since = query.get("since", ["0"])[0]
                if not since.isdigit():
                    raise ValueError("since is a time in milliseconds")
                chat_id = query.get("chat", [""])[0]
                self._reply(HTTPStatus.OK, store.usage(chat_id, int(since)))
            elif method == "GET" and path == "/logs":
                before = parse_qs(urlsplit(self.path).query).get("before", [""])[0]
                if before and not before.isdigit():
                    raise ValueError("before is the id of a log")
                logs = store.all_logs(int(before) if before else None, LOGS_AT_A_TIME)
                self._reply(HTTPStatus.OK, {"logs": logs})
            elif one and method == "PUT":
                chat = self._read_body()
                if chat.get("id") != one.group(1):
                    raise ValueError("a chat is kept under its own id")
                store.save_chat(chat)
                self._reply(HTTPStatus.OK, {})
            elif one and method == "DELETE":
                store.delete_chat(one.group(1))
                self._reply(HTTPStatus.OK, {})
            else:
                return False
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        return True

    def _exercise_ui(self) -> bool:
        """Sends a file the interface of an exercise is made of, and returns
        whether the request was for one. These are the same for everyone,
        and are loaded by the browser as modules and stylesheets, which
        cannot send the token, so whoever asks is not looked into.

            GET /exercises/kit.js, /exercises/kit.css
            GET /exercises/ID/ui/PATH
        """
        path = urlsplit(self.path).path
        if not path.startswith("/exercises/"):
            return False
        found = ui_file(unquote(path.removeprefix("/exercises/")))
        if found is None:
            self._reply(HTTPStatus.NOT_FOUND, {"error": "no such file"})
            return True
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", found[1])
        self.send_header("Content-Length", str(len(found[0])))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(found[0])
        return True

    def _practice(self, method: str, api_key: str | None = None) -> bool:
        """Answers a request about practice, and returns whether the request
        was one.

            GET /lessons?language=L      the lessons of a language
            GET /exercises               the exercises there are
            GET /sessions                the sessions, the latest first
            GET /sessions/S              a session, with its grades and the
                                         logs of its exercises, by exercise
            POST /sessions               start a session of `{"language": ...,
                                         "lesson": ..., "topics": [...],
                                         "exercises": {ID: instances},
                                         "options": {ID: {NAME: VALUE}}}`;
                                         with an empty lesson, it reviews
                                         the lessons practised last
            POST /sessions/S/end         end it, `{"status": "finished" |
                                         "abandoned"}`, after finishing the
                                         exercises that were started
            POST /sessions/S/exercises/ID/OP
                                         make a step of an exercise: `start`,
                                         `act` on `{"message": ...}`, or
                                         `finish`; the reply is what it is to
                                         `show`, and the `tasks` it started,
                                         such as writing the log of an
                                         exercise that is over

        A POST to a session brings the `model` an exercise asks, the
        `image_model` that draws its pictures, the `vision_model` that looks
        at them (the `model` if there is none), and the `into` and `level`
        of the learner. The reply has what the models that
        were asked used.
        """
        practice = self.account.practice
        url = urlsplit(self.path)
        one = re.fullmatch(r"/sessions/([^/]+)", url.path)
        end = re.fullmatch(r"/sessions/([^/]+)/end", url.path)
        step = re.fullmatch(r"/sessions/([^/]+)/exercises/([^/]+)/([a-z]+)", url.path)
        listed = url.path in ("/lessons", "/exercises", "/sessions")
        store = self.account.store
        if practice is None or store is None or not (listed or one or end or step):
            return False
        try:
            if method == "GET" and url.path == "/lessons":
                language = parse_qs(url.query).get("language", [""])[0].strip()
                lessons = practice.lessons(language or self.account.language)
                self._reply(HTTPStatus.OK, {"lessons": lessons})
            elif method == "GET" and url.path == "/exercises":
                self._reply(HTTPStatus.OK, {"exercises": practice.exercises()})
            elif method == "GET" and url.path == "/sessions":
                self._reply(HTTPStatus.OK, {"sessions": store.sessions()})
            elif method == "GET" and one:
                session = store.session(one.group(1))
                if session is None:
                    self._reply(HTTPStatus.NOT_FOUND, {"error": "no such session"})
                else:
                    grades, logs = (
                        store.grades(session["id"]),
                        store.logs(session["id"]),
                    )
                    self._reply(
                        HTTPStatus.OK, {**session, "grades": grades, "logs": logs}
                    )
            elif method == "POST" and url.path == "/sessions":
                self._start_session(practice, api_key)
            elif method == "POST" and (end or step):
                body = self._read_body()
                learner, ask, draw, look = self._models(body, api_key)
                reply: dict[str, Any]
                before = {task["id"] for task in self.account.tasks.listing()}
                if end:
                    status = str(body.get("status") or "finished")
                    session, used = practice.end_session(
                        end.group(1), status, learner, ask, draw, look
                    )
                    reply = {"session": session}
                else:
                    assert step
                    session_id, exercise, op = step.groups()
                    show, used = practice.step(
                        session_id,
                        exercise,
                        op,
                        body.get("message"),
                        learner,
                        ask,
                        draw,
                        look,
                    )
                    reply = {"show": show}
                usage = [describe_usage(profile) for profile in used]
                # the logs of the exercises it finished, being written
                started = [
                    task
                    for task in self.account.tasks.listing()
                    if task["id"] not in before and task["kind"] == "log"
                ]
                self._reply(HTTPStatus.OK, {**reply, "usage": usage, "tasks": started})
            else:
                return False
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except ExerciseError as error:
            self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
        except GrammarError as error:
            self._reply(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
        return True

    def _models(
        self, body: dict[str, Any], api_key: str | None
    ) -> tuple[dict[str, str], Asker, Drawer, Asker]:
        """What a request about an exercise says of the learner, their
        `into` and `level`, and what asks the models it names: the `model`,
        the `image_model` that draws and the `vision_model` that looks at
        pictures, which is the `model` if none is named."""
        learner = {
            name: value[:MAX_LANGUAGE_LENGTH]
            for name in ("into", "level")
            if isinstance(value := body.get(name), str)
        }
        ask = model_asker(send_chat, read_model(body.get("model"), api_key or ""))
        vision_model = read_model(body.get("vision_model"), api_key or "")
        look = model_asker(send_chat, vision_model) if vision_model.name else ask
        image_model = read_model(body.get("image_model"), api_key or "")
        draw = model_drawer(image_model.or_named(DEFAULT_IMAGE_MODEL))
        return learner, ask, draw, look

    def _evaluating(self, method: str, api_key: str | None = None) -> bool:
        """Answers a request about the evaluations, and returns whether the
        request was one.

            GET /evaluations/levels?language=L
                                         the exams there are of a language,
                                         by level
            GET /evaluations             the evaluations, the latest first
            GET /evaluations/E           an evaluation, with its parts
            POST /evaluations            start one, `{"language": ...,
                                         "level": ..., "length": half hours,
                                         "timed": ...}`
            POST /evaluations/E/parts/N/start
                                         start its part N in a session of its
                                         own, or take it up; the reply has the
                                         `evaluation` and the `session`
            POST /evaluations/E/parts/N/finish
                                         finish the part N, and the evaluation
                                         after the last
            POST /evaluations/E/end      end it, after finishing the part that
                                         is running

        A POST that finishes brings the models and the learner, as one to a
        session does; the level is that of the exam. The reply has the
        `evaluation`, what the models used and the `tasks` it started, such
        as writing the logs.
        """
        evaluations, store = self.account.evaluations, self.account.store
        url = urlsplit(self.path)
        one = re.fullmatch(r"/evaluations/([^/]+)", url.path)
        part = re.fullmatch(
            r"/evaluations/([^/]+)/parts/(\d+)/(start|finish)", url.path
        )
        end = re.fullmatch(r"/evaluations/([^/]+)/end", url.path)
        listed = url.path in ("/evaluations", "/evaluations/levels")
        if evaluations is None or store is None or not (listed or one or part or end):
            return False
        try:
            if method == "GET" and url.path == "/evaluations/levels":
                language = parse_qs(url.query).get("language", [""])[0].strip()
                levels = evaluations.levels(language or self.account.language)
                self._reply(HTTPStatus.OK, {"levels": levels})
            elif method == "GET" and url.path == "/evaluations":
                self._reply(HTTPStatus.OK, {"evaluations": evaluations.evaluations()})
            elif method == "GET" and one:
                found = evaluations.evaluation(one.group(1))
                if found is None:
                    self._reply(HTTPStatus.NOT_FOUND, {"error": "no such evaluation"})
                else:
                    self._reply(HTTPStatus.OK, found)
            elif method == "POST" and url.path == "/evaluations":
                body = self._read_body()
                named, level = body.get("language"), body.get("level")
                if not isinstance(named, str) or not isinstance(level, str):
                    raise ValueError("an evaluation names its language and its level")
                evaluation = evaluations.start(
                    named.strip() or self.account.language,
                    level,
                    body.get("length"),  # type: ignore[arg-type]
                    body.get("timed") is True,
                )
                self._reply(HTTPStatus.OK, evaluation)
            elif method == "POST" and part and part.group(3) == "start":
                evaluation, session = evaluations.start_part(
                    part.group(1), int(part.group(2))
                )
                self._reply(
                    HTTPStatus.OK, {"evaluation": evaluation, "session": session}
                )
            elif method == "POST" and (part or end):
                body = self._read_body()
                learner, ask, draw, _ = self._models(body, api_key)
                before = {task["id"] for task in self.account.tasks.listing()}
                if part:
                    evaluation, used = evaluations.finish_part(
                        part.group(1), int(part.group(2)), learner, ask, draw
                    )
                else:
                    assert end
                    evaluation, used = evaluations.end(end.group(1), learner, ask, draw)
                logging = [
                    task
                    for task in self.account.tasks.listing()
                    if task["id"] not in before and task["kind"] == "log"
                ]
                self._reply(
                    HTTPStatus.OK,
                    {
                        "evaluation": evaluation,
                        "usage": [describe_usage(profile) for profile in used],
                        "tasks": logging,
                    },
                )
            else:
                return False
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except ExerciseError as error:
            self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
        except (EvaluationError, GrammarError) as error:
            self._reply(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
        return True

    def _topics(self, method: str, api_key: str | None = None) -> bool:
        """Answers a request about the topics of practice, or about the
        embedding of the vocabulary that finds the words of a topic, and
        returns whether the request was one.

            GET /topics             the topics, the newest first
            POST /topics            make a topic of `{"title": ...,
                                    "description": ..., "image_model": ...}`;
                                    its icon is made in the background, as
                                    the `task` of the reply
            DELETE /topics/ID       remove a topic
            GET /topics/ID/icon     the icon of a topic, as a file
            POST /topics/ID/icon    make its icon again, `{"image_model": ...}`
            POST /embeddings        embed the words of the vocabulary of
                                    `{"language": ..., "model": ...}` that are
                                    not yet, in the background; the reply says
                                    how many are `missing`, and the `task`
        """
        practice, store = self.account.practice, self.account.store
        path = urlsplit(self.path).path
        one = re.fullmatch(r"/topics/([^/]+)", path)
        icon = re.fullmatch(r"/topics/([^/]+)/icon", path)
        if practice is None or store is None:
            return False
        if not (one or icon or path in ("/topics", "/embeddings")):
            return False
        try:
            if method == "GET" and path == "/topics":
                self._reply(HTTPStatus.OK, {"topics": store.topics()})
            elif method == "POST" and path == "/topics":
                body = self._read_body()
                title, description = body.get("title"), body.get("description", "")
                if not isinstance(title, str) or not isinstance(description, str):
                    raise ValueError('expected {"title": "...", "description": "..."}')
                topic = store.add_topic(
                    uuid.uuid4().hex,
                    title[:MAX_TOPIC_LENGTH],
                    description[:MAX_TOPIC_LENGTH],
                )
                task = self._make_icon(topic, body, api_key)
                self._reply(HTTPStatus.OK, {"topic": topic, "task": task})
            elif method == "DELETE" and one:
                store.delete_topic(one.group(1))
                self._reply(HTTPStatus.OK, {})
            elif method == "GET" and icon:
                found = store.icon(icon.group(1))
                if found is None:
                    self._reply(HTTPStatus.NOT_FOUND, {"error": "no icon"})
                    return True
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", found[1])
                self.send_header("Content-Length", str(len(found[0])))
                self.end_headers()
                self.wfile.write(found[0])
            elif method == "POST" and icon:
                again = store.topic(icon.group(1))
                if again is None:
                    self._reply(HTTPStatus.NOT_FOUND, {"error": "no such topic"})
                    return True
                task = self._make_icon(again, self._read_body(), api_key)
                self._reply(HTTPStatus.OK, {"task": task})
            elif method == "POST" and path == "/embeddings":
                self._embed_vocabulary(practice, api_key)
            else:
                return False
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        return True

    def _make_icon(
        self, topic: dict[str, Any], body: dict[str, Any], api_key: str | None
    ) -> dict[str, Any] | None:
        """Has the icon of `topic` made in the background by the
        `image_model` of the request, and returns the task, or None
        without a key to make it with."""
        store, practice = self.account.store, self.account.practice
        assert store and practice
        image_model = read_model(body.get("image_model"), api_key or "").or_named(
            DEFAULT_IMAGE_MODEL
        )
        if not image_model.has_key:
            return None

        def make(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
            picture, kind, used = practice.make_icon(topic, image_model)
            store.save_icon(topic["id"], picture, kind)
            step()
            return [{"topic": topic["id"]}], [describe_usage(used)]

        return self.account.tasks.start("icon", topic["title"], 1, make)

    def _embed_vocabulary(self, practice: Practice, api_key: str | None) -> None:
        """Has the words of a vocabulary that are not embedded yet embedded
        in the background, as a POST to /embeddings asks."""
        body = self._read_body()
        language = body.get("language")
        if not isinstance(language, str):
            raise ValueError('expected {"language": "...", "model": "..."}')
        model = read_model(body.get("model"), api_key or "")
        model = model.or_named(DEFAULT_EMBEDDING_MODEL)
        missing = practice.vocabulary_to_embed(language.strip(), model.name)
        if not missing or model.name in practice.embedding:
            self._reply(HTTPStatus.OK, {"missing": len(missing), "task": None})
            return
        if not model.has_key:
            raise ValueError("an OpenRouter key is needed")
        practice.embedding.add(model.name)

        def embed(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
            try:
                used = practice.embeddings.embed(missing, model, step)
            finally:
                practice.embedding.discard(model.name)
            log(
                f"{datetime.now():%H:%M:%S} embedded {len(missing)} words of"
                f" {language} with {model.name}"
            )
            return [], [describe_usage(profile) for profile in used]

        batches = -(-len(missing) // EMBED_BATCH)
        task = self.account.tasks.start(
            "embeddings", f"{len(missing)} words of {language}", batches, embed
        )
        self._reply(HTTPStatus.OK, {"missing": len(missing), "task": task})

    def _start_session(self, practice: Practice, api_key: str | None) -> None:
        """Starts the session of practice a POST describes, and replies with
        it and with what embedding its words used. Besides the lesson, the
        topics and the exercises, the POST says how the words are chosen:
        `{"mix_topics": ..., "vocabulary": "none" | "all" | "set", "words":
        [...], "topic_words": ...,
        "embedding_model": ...}`, and how many `minutes` each exercise may
        take, by exercise, none for no limit."""
        body = self._read_body()
        language, lesson = body.get("language"), body.get("lesson")
        topics, chosen = body.get("topics", []), body.get("exercises")
        options = body.get("options") or {}
        minutes = body.get("minutes") or {}
        if not (
            isinstance(language, str)
            and isinstance(lesson, str)
            and isinstance(topics, list)
            and all(isinstance(topic, str) for topic in topics)
            and isinstance(chosen, dict)
            and isinstance(options, dict)
            and isinstance(minutes, dict)
        ):
            raise ValueError(
                'expected {"language": ..., "lesson": ..., "exercises": {...}}'
            )
        session, used = practice.start_session(
            language,
            lesson,
            topics,
            chosen,
            read_choosing(body, api_key or ""),
            options,
            minutes,
        )
        usage = [describe_usage(profile) for profile in used]
        self._reply(HTTPStatus.OK, {**session, "usage": usage})

    def do_GET(self) -> None:
        if self._exercise_ui():
            return
        if not self._find_account() or self._kept("GET") or self._sets("GET"):
            return
        if self._practice("GET") or self._topics("GET") or self._evaluating("GET"):
            return
        if self._books("GET") or self._speech("GET"):
            return
        if urlsplit(self.path).path == "/tasks":
            # what is done in the background, and what came of it
            self._reply(HTTPStatus.OK, {"tasks": self.account.tasks.listing()})
            return
        intake = self.account.intake
        url = urlsplit(self.path)
        entry = re.fullmatch(r"/vocabulary/words/(\d+)", url.path)
        # the vocabulary of the language the request names, if it names one
        named = parse_qs(url.query).get("language", [""])[0].strip()
        vocabulary: Vocabulary | None = None
        if intake and not named:
            vocabulary = intake.vocabulary
        elif intake and intake.has_vocabulary(named):
            # asking after a language does not make a vocabulary of it
            vocabulary = intake.vocabulary_of(named)
        elif intake and url.path == "/vocabulary/words":
            self._reply(HTTPStatus.OK, {"categories": list(CATEGORIES), "words": []})
            return
        if vocabulary and url.path == "/vocabulary/words":
            # Every stored word, without what is known about it, which is
            # asked for one word at a time.
            self._reply(
                HTTPStatus.OK,
                {
                    # in the order they are to be shown in
                    "categories": list(CATEGORIES),
                    "words": [asdict(word) for word in vocabulary.listing()],
                },
            )
        elif vocabulary and entry:
            found = vocabulary.get(int(entry.group(1)))
            if found:
                self._reply(HTTPStatus.OK, asdict(found))
            else:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such word"})
        else:
            self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})

    def do_POST(self) -> None:
        # The chat sends the key from its settings; one set where the server
        # runs is used otherwise. Without either, only the models at
        # addresses of the learner's own can be asked.
        api_key = self.headers.get(KEY_HEADER) or os.environ.get("OPENROUTER_API_KEY")
        try:
            if self.path == "/login":
                self._log_in()
            elif not self._find_account() or self._kept("POST"):
                pass
            elif self._books("POST") or self._speech("POST", api_key):
                pass
            elif self._practice("POST", api_key) or self._topics("POST", api_key):
                pass
            elif self._evaluating("POST", api_key) or self._relay():
                pass
            elif self.path == "/sentences":
                self._check_sentences(api_key)
            elif self.path == "/translate" and self.account.translator:
                self._translate(self.account.translator, api_key)
            elif self.path == "/translate/chat" and self.account.translator:
                self._answer(self.account.translator, api_key)
            elif self.path == "/translate/chat/end" and self.account.translator:
                self._log_questions(self.account.translator, api_key)
            elif self.path == "/vocabulary/words" and self.account.intake:
                self._take_words(self.account.intake, api_key)
            elif self.path == "/vocabulary/selection" and self.account.intake:
                self._take_selection(self.account.intake, api_key)
            elif self.path == "/vocabulary/import" and self.account.importer:
                self._import(self.account.importer, api_key)
            else:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def _relay(self) -> bool:
        """Answers a request that the chat has passed on to a server of
        the learner's own, which a page may not be let to reach itself,
        and returns whether the request was one.

            POST /models            the ids of the models the server at
                                    `{"url": ..., "key": ...}` has
            POST /models/chat       a chat request, with the reply as it
                                    comes, streamed or not

        The model of a chat request is named with its address, as a
        request to the server names it, and the rest of the request goes
        on as it is. Only one at an address is asked here: OpenRouter is
        asked by the chat itself."""
        path = urlsplit(self.path).path
        if path not in ("/models", "/models/chat"):
            return False
        body = self._read_body()
        if path == "/models":
            body = {"model": {"model": "", **body}}
        model = read_model(body.pop("model", None))
        if model.on_openrouter:
            raise ValueError("only a model at an address is asked here")
        if path == "/models":
            try:
                self._reply(HTTPStatus.OK, {"models": list_models(model)})
            except ProfileError as error:
                self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            return True
        request = urllib.request.Request(
            model.endpoint("chat/completions"),
            data=json.dumps({**body, "model": model.name}).encode(),
            headers={**model.headers(), "Content-Type": "application/json"},
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=RELAY_TIMEOUT_SECS)
        except urllib.error.HTTPError as error:
            response = error
        except OSError as error:
            self._reply(
                HTTPStatus.BAD_GATEWAY,
                {"error": {"message": f"could not reach {model.where}: {error}"}},
            )
            return True
        with response:
            self.send_response(response.status)
            kind = response.headers.get("Content-Type") or "application/octet-stream"
            self.send_header("Content-Type", kind)
            self.end_headers()
            # passed on as it comes, for a reply that is streamed
            while piece := response.read1(65536):
                self.wfile.write(piece)
                self.wfile.flush()
        return True

    def _translate(self, translator: Translator, api_key: str | None) -> None:
        """Translates the `selection` of a `{"selection": ..., "before": ...,
        "after": ..., "language": ..., "into": ..., "model": ...}` request,
        where `before` and `after` are the text around it, as much of it as
        the sender likes. Replies with the translation, with the `passage`
        the model was given, which is the sentences the selection is in and
        a few before them, and with what the request to the model used.
        The translation is logged, with `where`, if the request has it,
        saying where the selection was made, such as a page of a book; the
        reply has the `log` too."""
        body = self._read_body()
        selection = body.get("selection")
        before, after = body.get("before", ""), body.get("after", "")
        if not (
            isinstance(selection, str)
            and isinstance(before, str)
            and isinstance(after, str)
        ):
            raise ValueError('expected {"selection": "...", "before": "..."}')
        if len(selection) > MAX_SELECTION_LENGTH:
            raise ValueError("the selection is too long")
        passage = passage_of(before, selection, after)
        language, into, model = self._read_translating(body, api_key)
        where = self._read_where(body)
        started = time.monotonic()
        try:
            translation, used = translator.translate(passage, language, into, model)
        except TranslationError as error:
            self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            return
        log(
            f"{datetime.now():%H:%M:%S} translated: {passage.selection}\n"
            f"       {translation}\n"
            f"       ({used.model}, {time.monotonic() - started:.1f} s,"
            f" {used.input_tokens} tokens in, {used.output_tokens} out)"
        )
        kept = None
        if self.account.store:
            subject, content = translation_log(passage, translation)
            kept = self.account.store.add_log(
                "translation", language, subject, content, where
            )
        self._reply(
            HTTPStatus.OK,
            {
                "translation": translation,
                "passage": asdict(passage),
                "log": kept,
                "usage": [describe_usage(used)],
            },
        )

    def _log_questions(self, translator: Translator, api_key: str | None) -> None:
        """Has a model write the logs of what was asked about a selection
        that was translated, once the chat about it is over: one for each
        matter that was discussed. The request is as for an answer, with
        `where` the translation was made and the `log` of the translation,
        if it has them, which the logs of the questions are kept beside.
        This is done in the background: the reply is the `task` that was
        started, or null if nothing was asked."""
        body = self._read_body()
        given = body.get("passage")
        parts = [
            part
            for name in ("before", "selection", "after")
            if isinstance(given, dict) and isinstance(part := given.get(name), str)
        ]
        translation = body.get("translation")
        if len(parts) != 3 or not isinstance(translation, str):
            raise ValueError('expected {"passage": {...}, "translation": "..."}')
        messages = read_messages(body.get("messages"), to_answer=False)
        language, into, model = self._read_translating(body, api_key)
        where = self._read_where(body)
        translated = body.get("log")
        if translated is not None and not isinstance(translated, int):
            raise ValueError("log must be the id of the log of the translation")
        store = self.account.store
        if store is None or not asked_anything(messages):
            self._reply(HTTPStatus.OK, {"task": None})
            return
        passage = Passage(*parts)
        source = {**where, "translation": translated} if translated else where
        ask = translator.asker(model)

        def write(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
            try:
                logs, used = write_question_logs(
                    ask, passage, translation, messages, language, into
                )
            except (LogError, TranslationError) as error:
                raise ValueError(
                    f"the questions could not be logged: {error}"
                ) from None
            for subject, content in logs:
                store.add_log("question", language, subject, content, source)
            step()
            return [{"subject": subject} for subject, _ in logs], [describe_usage(used)]

        title = " ".join(passage.selection.split())[:MAX_TITLE_LENGTH]
        task = self.account.tasks.start(
            "questions", f"Questions about {title}", 1, write
        )
        self._reply(HTTPStatus.OK, {"task": task})

    def _read_where(self, body: dict[str, Any]) -> dict[str, Any]:
        """Where a request says something was done, such as a page of a
        book, as a few names and ids, or nothing."""
        where = body.get("where")
        if where is None:
            return {}
        if not isinstance(where, dict) or len(json.dumps(where)) > MAX_WHERE_LENGTH:
            raise ValueError("where must be a small object")
        return where

    def _answer(self, translator: Translator, api_key: str | None) -> None:
        """Answers the last of the `messages` of a `{"passage": ...,
        "translation": ..., "messages": [...], "language": ..., "into": ...,
        "model": ...}` request: what was asked and answered so far about a
        selection that was translated, each a `{"role": ..., "content":
        ...}`. The passage and the translation are those the translating
        replied with. Nothing of the chat is kept here."""
        body = self._read_body()
        given = body.get("passage")
        parts = [
            part
            for name in ("before", "selection", "after")
            if isinstance(given, dict) and isinstance(part := given.get(name), str)
        ]
        translation = body.get("translation")
        if len(parts) != 3 or not isinstance(translation, str):
            raise ValueError('expected {"passage": {...}, "translation": "..."}')
        messages = read_messages(body.get("messages"))
        language, into, model = self._read_translating(body, api_key)
        try:
            reply, used = translator.answer(
                Passage(*parts),
                translation,
                messages,
                language,
                into,
                model,
            )
        except TranslationError as error:
            self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            return
        self._reply(HTTPStatus.OK, {"reply": reply, "usage": [describe_usage(used)]})

    def _read_translating(
        self, body: dict[str, Any], api_key: str | None
    ) -> tuple[str, str, Model]:
        """The language being learned, the one to translate into and the
        model to ask, as a request about a selection names them. The first
        is the one the account goes by if the request names none."""
        named = []
        for name in ("language", "into"):
            value = body.get(name)
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{name} must be text or null")
            named.append((value or "").strip())
        language = named[0][:MAX_LANGUAGE_LENGTH] or self.account.language
        into = named[1][:MAX_LANGUAGE_LENGTH] or DEFAULT_INTO
        return language, into, read_model(body.get("model"), api_key or "")

    def _import(self, importer: AnkiImporter, api_key: str | None) -> None:
        """Takes the `{"enabled": ..., "model": ..., "decision_model": ...,
        "language": ..., "anki_language": ...}`
        of a request, and the key it came with, as what the import of the
        Anki words is to go by, and replies with what the import is doing
        and the requests to the models it has made since it was last asked."""
        body = self._read_body()
        model = read_model(body.get("model"), api_key or "")
        decision_model = read_model(body.get("decision_model"), api_key or "")
        self._take_language(body)
        # the language the Anki words are of, which need not be the one studied
        anki_language = body.get("anki_language")
        if anki_language is not None and not isinstance(anki_language, str):
            raise ValueError("anki_language must be text or null")
        importer.configure(
            # the Anki words of one user are not taken in for another
            self.account.anki and body.get("enabled") is not False,
            model,
            decision_model,
            (anki_language or "").strip()[:MAX_LANGUAGE_LENGTH] or None,
        )
        if self.account.processor:
            # the messages and the exercises are processed with the same models
            self.account.processor.configure(model, decision_model)
        status, used = importer.status()
        self._reply(
            HTTPStatus.OK,
            {**asdict(status), "usage": [describe_usage(profile) for profile in used]},
        )

    def _take_language(self, body: dict[str, Any]) -> None:
        """Takes the `language` of a request, if it has one, as the language
        being studied from now on: the one that is spell-checked, that
        sentences are judged by, and that the vocabulary is of."""
        language = body.get("language")
        if language is not None and not isinstance(language, str):
            raise ValueError("language must be text or null")
        if language and language.strip():
            self.account.study(language.strip()[:MAX_LANGUAGE_LENGTH])

    def _take_words(self, intake: Intake, api_key: str | None) -> None:
        """Takes the words of a `{"words": [...], "model": ...,
        "decision_model": ...}` request into the vocabulary, and replies
        with what became of each once all are done. A word is text, or a
        `{"word": ..., "sentence": ...}` with the sentence it was used in.
        `model` is the language model that judges and describes new words."""
        body = self._read_body()
        words: list[Word] = read_words(body.get("words"))
        self._take_language(body)
        outcomes, used = intake.take(
            words,
            read_model(body.get("model"), api_key or ""),
            read_model(body.get("decision_model"), api_key or ""),
        )
        log(f"{datetime.now():%H:%M:%S} words taken in\n{describe_outcomes(outcomes)}")
        self._reply(
            HTTPStatus.OK,
            {
                "words": [asdict(outcome) for outcome in outcomes],
                "usage": [describe_usage(profile) for profile in used],
            },
        )

    def _take_selection(self, intake: Intake, api_key: str | None) -> None:
        """Takes the words of the `selection` of a `{"selection": ...,
        "before": ..., "after": ..., "language": ..., "model": ...,
        "decision_model": ...}` request into the vocabulary of the
        `language`, each with the sentence it is in, as the words of the
        chats and the exercises are taken. `before` and `after` are the text
        around the selection. This is done in the background: the reply is
        the `task` that was started, and `GET /tasks` says how far it is,
        and in the end what became of each word and what the requests to
        the models used."""
        body = self._read_body()
        selection = body.get("selection")
        before, after = body.get("before", ""), body.get("after", "")
        if not (
            isinstance(selection, str)
            and isinstance(before, str)
            and isinstance(after, str)
        ):
            raise ValueError('expected {"selection": "...", "before": "..."}')
        words = words_in(
            before[-MAX_AROUND_LENGTH:], selection, after[:MAX_AROUND_LENGTH]
        )
        if not words:
            raise ValueError("there are no words in the selection")
        if len(words) > MAX_WORDS:
            raise ValueError(f"more than {MAX_WORDS} words are selected")
        language, _, model = self._read_translating(body, api_key)
        decision_model = read_model(body.get("decision_model"), api_key or "")

        def take(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
            outcomes, used = intake.take(
                words,
                model,
                decision_model,
                on_outcome=lambda outcome: step(),
                language=language,
            )
            log(
                f"{datetime.now():%H:%M:%S} words of a selection taken in\n"
                f"{describe_outcomes(outcomes)}"
            )
            return (
                [
                    {
                        "word": outcome.word,
                        "status": outcome.status,
                        "reason": outcome.reason,
                    }
                    for outcome in outcomes
                ],
                [describe_usage(profile) for profile in used],
            )

        # a word that is there twice in a sentence is worked on once
        distinct = len({(word.word, word.sentence) for word in words})
        title = " ".join(selection.split())[:MAX_TITLE_LENGTH]
        task = self.account.tasks.start("words", title, distinct, take)
        self._reply(HTTPStatus.OK, {"task": task})

    def _check_sentences(self, api_key: str | None) -> None:
        text, caret, model, questions, rate_words, profile = self._read_request(api_key)
        if not profile:
            # the spelling of a text box whose sentences are not profiled;
            # the requests to the model are left to be reported to the one
            # that is
            sentences = self.account.checker.spell(text, caret)
            self._reply(
                HTTPStatus.OK,
                {
                    "sentences": [asdict(sentence) for sentence in sentences],
                    "usage": [],
                    "pending": False,
                },
            )
            return
        sentences = self.account.checker.check(
            text, caret, model, questions, rate_words
        )
        log(f"{datetime.now():%H:%M:%S}\n{describe(sentences)}")
        used, pending = self.account.checker.billing()
        self._reply(
            HTTPStatus.OK,
            {
                "sentences": [asdict(sentence) for sentence in sentences],
                # the requests to the model that have come back since the
                # last time, including those whose answers were dropped
                "usage": [describe_usage(profile) for profile in used],
                # whether any are still out, and so worth asking again for
                "pending": pending,
            },
        )

    def _read_request(
        self, api_key: str | None
    ) -> tuple[str, int | None, Model, Questions | None, bool, bool]:
        """The parts of a `{"text": ..., "caret": ..., "model": ...,
        "questions": ..., "words": ..., "profile": ...}` request body. The
        caret may be left out or null, for when the text box is not in use,
        and so may the model and the questions, for the model the server was
        started with and the usual questions. With `"profile": false` only
        the spelling is checked."""
        body = self._read_body()
        self._take_language(body)
        text = body.get("text")
        if not isinstance(text, str):
            raise ValueError('expected {"text": "..."}')
        caret = body.get("caret")
        # in JSON, true and false are not numbers, but in Python they are
        if caret is not None and (
            not isinstance(caret, int) or isinstance(caret, bool)
        ):
            raise ValueError("caret must be a whole number or null")
        model = read_model(body.get("model"), api_key or "")
        questions = body.get("questions")
        if questions is not None:
            questions = read_questions(questions)
        # whether to rate the words of each sentence once it is profiled
        rate_words = body.get("words") is True
        profile = body.get("profile") is not False
        return text, caret, model, questions, rate_words, profile

    def _read_body(self) -> dict[str, Any]:
        """The JSON object a request brought. Raises ValueError."""
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise ValueError("text is too long")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            raise ValueError("body is not JSON") from None
        if not isinstance(body, dict):
            raise ValueError('expected {"text": "..."}')
        return body

    def _reply(self, status: HTTPStatus, content: object) -> None:
        body = json.dumps(content, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        # only the sentences are printed, not a line per request
        pass


def list_models(model: Model) -> list[str]:
    """The ids of the models the server `model` is at has, as it lists
    them. Raises ProfileError."""
    request = urllib.request.Request(model.endpoint("models"), headers=model.headers())
    try:
        with urllib.request.urlopen(request, timeout=LIST_TIMEOUT_SECS) as response:
            listed = json.load(response)["data"]
        return [each["id"] for each in listed if isinstance(each.get("id"), str)]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ProfileError(
            f"could not list the models at {model.url}: {error}"
        ) from None


def read_choosing(body: dict[str, Any], api_key: str = "") -> Choosing:
    """How the topics and words of a session are to be chosen, as a request
    to start one says, `api_key` being the OpenRouter key the embedding
    model is asked with there. Raises ValueError."""
    mix, topic_words = body.get("mix_topics", False), body.get("topic_words", True)
    vocabulary, words = body.get("vocabulary", "none"), body.get("words", [])
    model = read_model(body.get("embedding_model"), api_key)
    if not (
        isinstance(mix, bool)
        and isinstance(topic_words, bool)
        and vocabulary in ("none", "all", "set")
        and isinstance(words, list)
        and all(isinstance(word, str) for word in words)
    ):
        raise ValueError("the way the words are chosen is not one there is")
    if len(words) > MAX_SET_WORDS:
        raise ValueError(f"a set gives at most {MAX_SET_WORDS} words")
    return Choosing(
        mix_topics=mix,
        vocabulary=vocabulary,
        words=[word.strip() for word in words if word.strip()],
        topic_words=topic_words,
        embedding_model=model.or_named(DEFAULT_EMBEDDING_MODEL),
    )


def lemmas_of(intake: Intake, language: str) -> list[str]:
    """The words of the vocabulary of `language`, each once, those used or
    stored last first. None for a language there is no vocabulary of."""
    if not intake.has_vocabulary(language):
        return []
    listed = intake.vocabulary_of(language).listing()
    latest = sorted(
        listed, key=lambda word: (word.last_used or 0, word.created_at), reverse=True
    )
    return list(dict.fromkeys(word.lemma for word in latest))


def make_server(
    port: int,
    checker: LiveChecker | None = None,
    intake: Intake | None = None,
    importer: AnkiImporter | None = None,
    users: Users | None = None,
    accounts: Accounts | None = None,
) -> CheckerServer:
    """A server with an account for each user, or, given a `checker`, with
    the one account made of it and what else is given, for whoever asks."""
    if accounts is None:
        assert checker is not None
        one = Account(checker, intake, importer)
        accounts = Accounts(lambda user: one)
    return CheckerServer(port, accounts, users)


if __name__ == "__main__":
    # a Windows console may not be able to show every character that is typed
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # the language being studied, by its English name, until the chat says
    language = os.environ.get("CHECKER_LANGUAGE", DEFAULT_LANGUAGE)
    model = os.environ.get("CHECKER_PROFILE_MODEL", DEFAULT_MODEL)
    data_directory = Path(os.environ.get("CHECKER_DATA") or DATA_DIRECTORY)
    deck_status_url = os.environ.get("ANKI_STATUS_URL", DECK_STATUS_URL)
    anki_user = os.environ.get("CHECKER_ANKI_USER") or ANKI_USER

    def make_account(user: str) -> Account:
        """Everything a user has, with the vocabularies in a directory of
        the user's own."""
        profiler = Profiler(model)
        speller = StudySpeller(language)
        intake = Intake(
            Vocabularies(user_directory(data_directory, user)),
            profiler,
            # the language model asked about new words when a request names none
            model=os.environ.get("CHECKER_CHAT_MODEL", ""),
            known=speller.knows,
        )
        importer = AnkiImporter(
            intake,
            partial(fetch_anki_notes, deck_status_url),
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            on_taken=lambda outcomes: log(
                f"{datetime.now():%H:%M:%S} Anki words taken in for {user}\n"
                f"{describe_outcomes(outcomes)}"
            ),
        )
        kept = UserStore(user_directory(data_directory, user))
        kept.add_starter_topics(STARTER_TOPICS)
        processor = Processor(
            kept,
            intake,
            on_processed=lambda item, outcomes: log(
                f"{datetime.now():%H:%M:%S} processed a {item.kind} of {user}"
                f" ({item.role}, {len(outcomes)} words)"
            ),
        )
        tasks = Tasks()
        account = Account(
            LiveChecker(
                speller, profiler, on_profiled=print_profile, on_rated=print_ratings
            ),
            intake,
            importer,
            kept,
            processor,
            anki=user == anki_user,
            book_sync=BookSync(
                kept,
                on_synced=lambda added, removed: log(
                    f"{datetime.now():%H:%M:%S} books of {user} synced with the"
                    f" folder: {added} added, {removed} removed"
                ),
            ),
            # the language model asked when a request names none
            translator=Translator(model=os.environ.get("CHECKER_CHAT_MODEL", "")),
            speaker=Speaker(kept),
            tasks=tasks,
            practice=Practice(
                kept,
                lemmas_of=partial(lemmas_of, intake),
                on_words=log,
                later=in_background(tasks, "log"),
            ),
        )
        assert account.book_sync and account.practice
        account.evaluations = Evaluations(
            kept, account.practice, later=in_background(tasks, "log")
        )
        account.book_sync.watch()
        processor.watch()
        account.study(language)
        if account.anki:
            importer.watch()
        else:
            importer.configure(False, Model(), Model())
        return account

    users = Users(os.environ.get("CHECKER_USERS") or USERS_FILE, data_directory)
    # The vocabularies kept before there were users go to the one user there
    # is.
    if len(users.names()) == 1 and list(data_directory.glob("vocabulary*.db")):
        handed_over = take_vocabulary(data_directory, users.names()[0])
        print(
            f"Handed over to {users.names()[0]}: {', '.join(handed_over)}", flush=True
        )
    server = make_server(
        int(os.environ.get("CHECKER_PORT", DEFAULT_PORT)),
        users=users,
        accounts=Accounts(make_account),
    )
    print(
        f"Checker listening on http://{HOST}:{server.server_port}"
        f" (language: {language}, profiles: {model})",
        flush=True,
    )
    print(f"Data of the users in {data_directory}", flush=True)
    if not users.names():
        print(
            f"Nobody can log in yet. Write who may in {users.file}, as"
            ' {"name": "password"}.',
            flush=True,
        )
    print(f"Anki words are imported from {deck_status_url} for {anki_user}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
