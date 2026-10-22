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

from anki_import import (
    DECK_STATUS_URL,
    AnkiImporter,
    AnkiLink,
    AnkiRefused,
    AnkiUnavailable,
    vocabulary_words,
)
from books import BookError, read_epub
from categories import CATEGORIES, practised_categories
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
    MAX_WORDS,
    Intake,
    Outcome,
    Word,
    read_words,
    send_chat,
)
from known import Asked, known_words
from languages import DEFAULT_INTO, DEFAULT_LANGUAGE, check_labels, language_of
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
    describe_usage,
    read_questions,
    spent_by,
)
from relaying import Listing, Watched
from sentences import Sentence
from speaking import (
    MAX_SENTENCES,
    BookSentence,
    Speaker,
    SpeechError,
    generation_usages,
    sentences_between,
    sentences_of_message,
)
from spelling import StudySpeller
from starter_topics import STARTER_TOPICS, starter_icon
from storage import UserStore, is_id
from tasks import Tasks
from topics import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_IMAGE_MODEL,
    EMBED_BATCH,
)
from translating import (
    MAX_SELECTION_LENGTH,
    Passage,
    TranslationError,
    Translator,
    passage_of,
    read_messages,
)
from tutor import (
    LastCall,
    TutorError,
    converse,
    data_tools,
    evaluation_tool,
    exercise_tool,
    instructions,
    memory_tools,
    practised,
    recap,
    remember,
    wait_for,
    words_tool,
)
from tutor import read_messages as read_tutor_messages
from users import Users, take_vocabulary, user_directory
from vocabulary import Vocabularies, Vocabulary
from word_translations import WordTranslator

HOST = "127.0.0.1"
# The request header the chat sends its OpenRouter key in.
KEY_HEADER = "X-OpenRouter-Key"
# how long a model at an address the chat passes a request on to may take
RELAY_TIMEOUT_SECS = 120
# the models OpenRouter has, as the chat is told them, shared by every user
OPENROUTER_MODELS = Listing()
# how long a server is given to list its models
LIST_TIMEOUT_SECS = 10
DEFAULT_PORT = 8092
# far more than anyone types into a chat box
MAX_BODY_BYTES = 1_000_000
# a book with many pictures in it, which are not kept
MAX_BOOK_BYTES = 200_000_000
# the request header the name of the file of a book comes in, encoded as in a URL
FILE_NAME_HEADER = "X-File-Name"
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
# the longest the tone of the tutor the learner sets may be, in characters
MAX_TONE_LENGTH = 2000
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
# no AnkiWeb name or password is longer
MAX_ANKI_LOGIN_LENGTH = 500
# no collection has more decks to choose
MAX_ANKI_DECKS = 5000


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


def print_correction(
    sentence: str, correction: str | None, error: str | None, dropped: bool
) -> None:
    """Announces what a sentence was corrected to."""
    result = correction if correction is not None else f"failed: {error}"
    if dropped:
        result += " (dropped: the sentence was changed or gone back to)"
    log(f"{datetime.now():%H:%M:%S} corrected: {sentence}\n       {result}")


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


# The kinds of work the usage is added up by, as the app names them, by the
# kind of each task; a task is counted under its kind, as the app adds up
# apart what is counted under each id, such as that of a chat. What reading
# aloud used is counted apart, once it is looked up.
TASK_CATEGORIES = {
    "words": "vocabulary",
    "embeddings": "vocabulary",
    "icon": "practice",
    "log": "practice",
    "questions": "translation",
    "memories": "tutor",
}
# the bins the usage over time is added up in, in milliseconds
USAGE_BINS = {"hour": 3_600_000, "day": 86_400_000}
# the longest id usage may be counted under, in characters
MAX_USAGE_ID = 200


def count_usage(
    store: UserStore | None, category: str, usage_id: str, used: list[Any]
) -> None:
    """Count what requests to the models used, each as describe_usage says
    it, under `category` and `usage_id`, as soon as they come back, so that
    it is counted whether or not the app is there to be told; the app may
    tell it again, and it is counted once."""
    if store is None or not used:
        return
    at = int(time.time() * 1000)
    store.add_usage(
        [
            {
                "id": each["id"],
                "at": at,
                "category": category,
                "chatId": usage_id,
                "model": each["model"] or "unknown",
                "promptTokens": each["input_tokens"],
                "completionTokens": each["output_tokens"],
                "cost": each["cost"],
            }
            for each in used
        ]
    )


def count_task_usage(store: UserStore, kind: str, used: list[Any]) -> None:
    """Count what a task of `kind` used, once it is done."""
    count_usage(
        store,
        TASK_CATEGORIES.get(kind, "vocabulary"),
        f"task:{kind}",
        used,
    )


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


def translating_into(store: UserStore) -> str:
    """The language the user has what they read translated into, as their
    settings say, which new words are translated into."""
    into = (store.settings() or {}).get("translateInto")
    return (
        into.strip()[:MAX_LANGUAGE_LENGTH]
        if isinstance(into, str) and into.strip()
        else DEFAULT_INTO
    )


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
    # the Anki account the user may link, whose words are listed and
    # imported; the deck-status server is reached only through it
    anki: AnkiLink | None = None
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
    # what translates the stored words into another language
    words: WordTranslator | None = None
    # held while what the tutor is to remember of a chat is decided, so that
    # chats closed together are remembered one after another, each with the
    # memories that came of those before it
    remembering: threading.Lock = field(default_factory=threading.Lock)

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
            if self._anki("PUT"):
                return
            if self._books("PUT") or self._speech("PUT") or self._texts("PUT"):
                return
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})

    def do_DELETE(self) -> None:
        if not self._find_account() or self._kept("DELETE") or self._sets("DELETE"):
            return
        if self._tutor_chats("DELETE") or self._texts("DELETE"):
            return
        if self._books("DELETE") or self._speech("DELETE") or self._topics("DELETE"):
            return
        if self._anki("DELETE"):
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

    def _known(self) -> bool:
        """Answers a request for the words the learner knows, and returns
        whether the request was one.

            GET /vocabulary/known   the stored words picked by what is
                                    asked, those spelt alike as one word
                                    with all their `categories` and the
                                    `ids` of their entries

        What is asked is in the query, and all of it may be left out:

            language=L      the vocabulary of L, or of the language studied
            category=C      the words of C alone; named several times, or as
                            C1,C2, the words of any of them; all if none is
            set=S           the words of the set with that id or name alone
            anki_only=true  the words that have a card in review in the
                            chosen decks of Anki, if the Anki words are of L
            sorted_by=O     put in the order of ORDERS named, last_used if
                            none is
            reverse=true    in that order the other way round
            limit=N         the first N words only; all if 0 or left out

        The reply has the `words`, and how many there were before they
        were cut down to the limit, as `total`.
        """
        intake = self.account.intake
        url = urlsplit(self.path)
        if intake is None or url.path != "/vocabulary/known":
            return False
        query = parse_qs(url.query)

        def one(name: str, otherwise: str = "") -> str:
            return query.get(name, [otherwise])[-1].strip()

        def flag(name: str) -> bool:
            value = one(name, "false").lower()
            if value not in ("true", "false", "1", "0"):
                raise ValueError(f"{name} must be true or false")
            return value in ("true", "1")

        try:
            language = one("language")[:MAX_LANGUAGE_LENGTH] or intake.language
            limit = one("limit", "0")
            if not limit.isdigit():
                raise ValueError("limit must be a whole number")
            asked = Asked(
                categories=frozenset(
                    name.strip()
                    for given in query.get("category", [])
                    for name in given.split(",")
                    if name.strip()
                ),
                set=one("set"),
                anki_only=flag("anki_only"),
                order=one("sorted_by", "last_used"),
                reverse=flag("reverse"),
                limit=int(limit),
            )
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return True
        # asking after a language does not make a vocabulary of it
        vocabulary = (
            intake.vocabulary_of(language) if intake.has_vocabulary(language) else None
        )
        try:
            words, total = known_words(vocabulary, asked, self._anki_words(language))
        except LookupError as error:
            self._reply(HTTPStatus.NOT_FOUND, {"error": str(error)})
        except AnkiRefused as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except AnkiUnavailable as error:
            self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
        else:
            words_listed = [asdict(word) for word in words]
            self._reply(HTTPStatus.OK, {"words": words_listed, "total": total})
        return True

    def _anki_words(self, language: str) -> Callable[[], list[str]] | None:
        """What gives the words of the notes of the chosen decks of Anki
        that have a card in review, if they are of `language`, and none if
        they are of another; None if the user has no Anki."""
        anki, store = self.account.anki, self.account.store
        if anki is None:
            return None
        importer = self.account.importer
        anki_language = importer.language if importer else self.account.language

        def words() -> list[str]:
            if anki_language.strip().lower() != language.strip().lower():
                return []
            notes = anki.notes(store.skipped_anki_decks() if store else [])
            return [
                word for note in notes for word in vocabulary_words(note, anki_language)
            ]

        return words

    def _books(self, method: str) -> bool:
        """Answers a request about the books the user reads, and returns
        whether the request was one.

            GET /books         the books, without what they say
            POST /books        keep the EPUB file that is sent, as its text
                               and how large each part of it is written
            GET /books/ID      a book with its paragraphs
            GET /books/ID/cover  the picture on its cover, as a file
            DELETE /books/ID   remove a book
        """
        store = self.account.store
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
        if method == "GET" and not one:
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
                # audio comes without what it cost, which is looked up
                # apart, as it takes a while, and counted once it is
                generations = [str(each.get("generation") or "") for each in outcomes]
                threading.Thread(
                    target=lambda: count_usage(
                        store,
                        "speech",
                        "speech",
                        [
                            describe_usage(profile)
                            for profile in generation_usages(generations, model)
                        ],
                    ),
                    name="speech usage",
                    daemon=True,
                ).start()
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
                                      all of it, by category and model too;
                                      with `&bin=hour|day&offset=MINUTES`,
                                      the usage from that time on as a
                                      `series` too, by category and model in
                                      bins of an hour or a day, where the
                                      learner is MINUTES ahead of UTC
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
                summary = store.usage(chat_id, int(since))
                binned = query.get("bin", [""])[0]
                if binned:
                    if binned not in USAGE_BINS:
                        raise ValueError(f"bin is one of {', '.join(USAGE_BINS)}")
                    try:
                        offset = int(query.get("offset", ["0"])[0])
                    except ValueError:
                        raise ValueError("offset is a number of minutes") from None
                    if abs(offset) > 24 * 60:
                        raise ValueError("offset is a number of minutes")
                    summary["series"] = store.usage_series(
                        int(since), USAGE_BINS[binned], offset * 60_000
                    )
                self._reply(HTTPStatus.OK, summary)
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
            POST /sessions/S/exercises/ID/replay
                                         start a session that does that
                                         exercise again exactly as it was,
                                         with what it made, as it says
                                         under `kept` of its progress, or,
                                         with `{"fresh": true}`, with the
                                         same settings and what it does
                                         made anew; the reply is the session

        A POST that starts a session may bring `"guidance": {ID: ...}`, what
        each exercise is to aim at, such as the tutor steers it to, which it
        is told first among what it is to heed.

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
            elif method == "POST" and step and step.group(3) == "replay":
                fresh = self._read_body().get("fresh") is True
                self._reply(
                    HTTPStatus.OK,
                    practice.replay(step.group(1), step.group(2), fresh),
                )
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
                usage = self._count_practice(
                    end.group(1) if end else step.group(1) if step else "", used
                )
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
            # what the models were asked before it failed is counted all the same
            self._count_practice(
                end.group(1) if end else step.group(1) if step else "",
                spent_by(error),
            )
            self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
        except GrammarError as error:
            self._reply(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})
        return True

    def _count_practice(
        self, session_id: str, used: list[Profile]
    ) -> list[dict[str, object]]:
        """Count what the models asked in the session `session_id` used, as
        practice, or under the evaluations for a part of one, and return it
        as it is counted."""
        store = self.account.store
        usage = [describe_usage(profile) for profile in used]
        kept = store.session(session_id) if store and session_id else None
        evaluated = kept is not None and kept.get("kind") == "evaluation"
        count_usage(
            store, "practice", "evaluations" if evaluated else "practice", usage
        )
        return usage

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
                usage = [describe_usage(profile) for profile in used]
                count_usage(self.account.store, "practice", "evaluations", usage)
                self._reply(
                    HTTPStatus.OK,
                    {
                        "evaluation": evaluation,
                        "usage": usage,
                        "tasks": logging,
                    },
                )
            else:
                return False
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except ExerciseError as error:
            count_usage(
                self.account.store,
                "practice",
                "evaluations",
                [describe_usage(profile) for profile in spent_by(error)],
            )
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
        steering = body.get("guidance") or {}
        if not (
            isinstance(language, str)
            and isinstance(lesson, str)
            and isinstance(topics, list)
            and all(isinstance(topic, str) for topic in topics)
            and isinstance(chosen, dict)
            and isinstance(options, dict)
            and isinstance(minutes, dict)
            and isinstance(steering, dict)
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
            steering=steering,
        )
        usage = [describe_usage(profile) for profile in used]
        count_usage(self.account.store, "practice", "practice", usage)
        self._reply(HTTPStatus.OK, {**session, "usage": usage})

    def _anki(self, method: str) -> bool:
        """Answers a request about the Anki account of the user, and returns
        whether the request was one.

            GET /anki          whether an account is linked, when its
                               collection was last synced and why the last
                               sync failed, if it did
            POST /anki/link    link the account of the `{"username": ...,
                               "password": ...}` that is sent; the password
                               is not kept
            DELETE /anki/link  forget the account and its collection
            GET /anki/words    the words of the chosen decks that have a
                               card in review
            GET /anki/decks    the decks of the collection, each saying
                               whether it is chosen
            PUT /anki/decks    choose the `{"decks": [id, ...]}` that are
                               sent, and no other of the decks there are;
                               those made later are chosen
            GET /anki/media/NAME
                               a file of the media of the collection, such
                               as a picture of a card that is studied
        """
        path = urlsplit(self.path).path
        media = re.fullmatch(r"/anki/media/([^/]+)", path)
        if not media and path not in (
            "/anki",
            "/anki/link",
            "/anki/words",
            "/anki/decks",
        ):
            return False
        store = self.account.store
        anki = self.account.anki
        if anki is None:
            self._reply(HTTPStatus.NOT_FOUND, {"error": "there is no Anki here"})
            return True
        try:
            if method == "GET" and path == "/anki":
                self._reply(HTTPStatus.OK, anki.state())
            elif method == "POST" and path == "/anki/link":
                body = self._read_body()
                username, password = body.get("username"), body.get("password")
                if not (
                    isinstance(username, str)
                    and isinstance(password, str)
                    and username.strip()
                    and password
                    and len(username) + len(password) <= MAX_ANKI_LOGIN_LENGTH
                ):
                    raise ValueError('expected {"username": "...", "password": "..."}')
                self._reply(HTTPStatus.OK, anki.link(username.strip(), password))
            elif method == "DELETE" and path == "/anki/link":
                self._reply(HTTPStatus.OK, anki.unlink())
            elif method == "GET" and media:
                data, kind = anki.media(unquote(media.group(1)))
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "private, max-age=3600")
                self.end_headers()
                self.wfile.write(data)
            elif method == "GET" and path == "/anki/words":
                skipped = store.skipped_anki_decks() if store else []
                self._reply(HTTPStatus.OK, anki.known_words(skipped))
            elif method in ("GET", "PUT") and path == "/anki/decks" and store:
                if method == "PUT":
                    decks = self._read_body().get("decks")
                    if not (
                        isinstance(decks, list)
                        and len(decks) <= MAX_ANKI_DECKS
                        and all(type(deck) is int for deck in decks)
                    ):
                        raise ValueError('expected {"decks": [id, ...]}')
                    there = [deck.get("id") for deck in anki.decks()]
                    store.save_skipped_anki_decks(
                        [
                            deck
                            for deck in there
                            if isinstance(deck, int) and deck not in decks
                        ]
                    )
                skipped = store.skipped_anki_decks()
                listed = [
                    {**deck, "chosen": deck.get("id") not in skipped}
                    for deck in anki.decks()
                ]
                self._reply(HTTPStatus.OK, {"decks": listed})
            else:
                return False
        except AnkiRefused as error:
            status = HTTPStatus.NOT_FOUND if media else HTTPStatus.BAD_REQUEST
            self._reply(status, {"error": str(error)})
        except AnkiUnavailable as error:
            self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
        return True

    def do_GET(self) -> None:
        if self._exercise_ui():
            return
        if not self._find_account() or self._kept("GET") or self._sets("GET"):
            return
        if self._known() or self._openrouter_models():
            return
        if self._tutor_chats("GET") or self._texts("GET"):
            return
        if self._practice("GET") or self._topics("GET") or self._evaluating("GET"):
            return
        if self._books("GET") or self._speech("GET"):
            return
        if self._anki("GET"):
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
        studied = language_of(named or (intake.language if intake else ""))
        shown = {
            # in the order they are to be shown in
            "categories": list(CATEGORIES),
            # what is stored of a word, with the values that are names
            "details": studied.details(),
            # each of those names in the languages the app is shown in
            "labels": studied.labels(),
            # how the forms of a word of the language are laid out
            "tables": studied.form_tables(),
        }
        if intake and not vocabulary and url.path == "/vocabulary/words":
            self._reply(HTTPStatus.OK, {**shown, "words": []})
            return
        if vocabulary and url.path == "/vocabulary/words":
            # Every stored word, without what is known about it, which is
            # asked for one word at a time.
            self._reply(
                HTTPStatus.OK,
                {
                    **shown,
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
            elif not self._find_account() or self._kept("POST") or self._anki("POST"):
                pass
            elif self._books("POST") or self._speech("POST", api_key):
                pass
            elif self._practice("POST", api_key) or self._topics("POST", api_key):
                pass
            elif self._evaluating("POST", api_key) or self._relay(api_key):
                pass
            elif self.path == "/sentences":
                self._check_sentences(api_key)
            elif self.path == "/translate" and self.account.translator:
                self._translate(self.account.translator, api_key)
            elif self.path == "/translate/chat" and self.account.translator:
                self._answer(self.account.translator, api_key)
            elif self.path == "/translate/chat/end" and self.account.translator:
                self._log_questions(self.account.translator, api_key)
            elif self.path == "/tutor/chat" and self.account.practice:
                self._tutor(self.account.practice, api_key)
            elif self._tutor_chats("POST", api_key):
                pass
            elif self.path == "/vocabulary/words" and self.account.intake:
                self._take_words(self.account.intake, api_key)
            elif self.path == "/vocabulary/selection" and self.account.intake:
                self._take_selection(self.account.intake, api_key)
            elif self.path == "/vocabulary/import" and self.account.importer:
                self._import(self.account.importer, api_key)
            elif self.path == "/vocabulary/translations" and self.account.words:
                self._translate_words(self.account.words, api_key)
            else:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def _relay(self, api_key: str | None) -> bool:
        """Answers a request of the chat for a model, which the page never
        asks itself, and returns whether the request was one.

            POST /models            the ids of the models the server at
                                    `{"url": ..., "key": ...}` has
            POST /models/chat       a chat request, with the reply as it
                                    comes, streamed or not; `usage_id` is
                                    the chat its usage is counted under

        The model of a chat request is named as a request to the server
        names it, on OpenRouter with the key the request goes with, and the
        rest of the request goes on as it is. What it used is counted as the
        reply says; one that is cut off before it says is looked up on
        OpenRouter."""
        path = urlsplit(self.path).path
        if path not in ("/models", "/models/chat"):
            return False
        body = self._read_body()
        if path == "/models":
            model = read_model({"model": "", **body})
            if model.on_openrouter:
                raise ValueError("the models of OpenRouter are listed with a GET")
            try:
                self._reply(HTTPStatus.OK, {"models": list_models(model)})
            except ProfileError as error:
                self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
            return True
        model = read_model(body.pop("model", None), api_key or "")
        usage_id = body.pop("usage_id", None)
        usage_id = usage_id[:MAX_USAGE_ID] if isinstance(usage_id, str) else ""
        problem = model.problem()
        if problem:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": {"message": problem}})
            return True
        request = urllib.request.Request(
            model.endpoint("chat/completions"),
            data=json.dumps(
                {**body, "model": model.name, "usage": {"include": True}}
            ).encode(),
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
        streamed = body.get("stream") is True
        watched = Watched()
        whole = b""
        with response:
            self.send_response(response.status)
            kind = response.headers.get("Content-Type") or "application/octet-stream"
            self.send_header("Content-Type", kind)
            # for nginx, which would otherwise hold the reply back until its end
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            # passed on as it comes, for a reply that is streamed
            try:
                while piece := response.read1(65536):
                    if streamed:
                        watched.feed(piece)
                    else:
                        whole += piece
                    self.wfile.write(piece)
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                # the chat stopped the reply, which stops the model too
                pass
        if not streamed:
            watched.whole(whole)
        if response.status == HTTPStatus.OK:
            self._count_chat(model, watched, usage_id)
        return True

    def _count_chat(self, model: Model, watched: Watched, usage_id: str) -> None:
        """Count what a chat request used, as its reply said, or as
        OpenRouter keeps it, looked up in the background, if the reply was
        cut off before it said."""
        store = self.account.store
        used = watched.used(model)
        if used is not None:
            count_usage(store, "chat", usage_id, [describe_usage(used)])
        elif watched.generation and model.on_openrouter:
            threading.Thread(
                target=lambda: count_usage(
                    store,
                    "chat",
                    usage_id,
                    [
                        describe_usage(each)
                        for each in generation_usages([watched.generation], model)
                    ],
                ),
                daemon=True,
            ).start()

    def _openrouter_models(self) -> bool:
        """Answers `GET /models/openrouter?kind=...`, the models OpenRouter
        has of a kind, as relaying.py describes them, and returns whether
        the request was one."""
        url = urlsplit(self.path)
        if url.path != "/models/openrouter":
            return False
        kind = parse_qs(url.query).get("kind", ["all"])[0]
        try:
            self._reply(HTTPStatus.OK, {"models": OPENROUTER_MODELS.models(kind)})
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except ProfileError as error:
            self._reply(HTTPStatus.BAD_GATEWAY, {"error": str(error)})
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
        usage = [describe_usage(used)]
        count_usage(self.account.store, "translation", "translate", usage)
        self._reply(
            HTTPStatus.OK,
            {
                "translation": translation,
                "passage": asdict(passage),
                "log": kept,
                "usage": usage,
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
        usage = [describe_usage(used)]
        count_usage(self.account.store, "translation", "translate", usage)
        self._reply(HTTPStatus.OK, {"reply": reply, "usage": usage})

    def _tutor_chats(self, method: str, api_key: str | None = None) -> bool:
        """Answers a request about the chats with the tutor and its memories,
        and returns whether the request was one.

            GET /tutor/chats          the chats, the latest first, each with
                                      the first thing the learner wrote
            GET /tutor/chats/ID       a chat, with what the learner wrote and
                                      what the tutor answered
            DELETE /tutor/chats/ID    forget a chat
            POST /tutor/chats/ID/offers
                                      note how far an exercise the tutor
                                      offered got: `{"position": ..., "place":
                                      ..., "session": ..., "status": "running"
                                      | "done" | "abandoned"}`, the position
                                      of the answer in the chat and the place
                                      of the exercise among its offers
            POST /tutor/chats/ID/close
                                      close a chat, after which nothing more
                                      is said in it, with `{"model": ...}`,
                                      which then decides in the background
                                      what the tutor is to remember of it,
                                      and writes a recap of it, kept as a
                                      memory of the kind "recap"; the reply
                                      has the `tasks` it started
            GET /tutor/chats/ID/request
                                      the last request the tutor made to its
                                      model, `{"request": {"label": ...,
                                      "at": ..., "call": {...}}}`, as the
                                      inspector shows it, or null if it was
                                      made in another chat: one is kept
            GET /tutor/memories       the memories the tutor has, the oldest
                                      first, and those it `removed`
            DELETE /tutor/memories/N  have the tutor forget a memory, as the
                                      learner wants
        """
        store = self.account.store
        path = urlsplit(self.path).path
        one = re.fullmatch(r"/tutor/chats/([^/]+)", path)
        close = re.fullmatch(r"/tutor/chats/([^/]+)/close", path)
        offer = re.fullmatch(r"/tutor/chats/([^/]+)/offers", path)
        last = re.fullmatch(r"/tutor/chats/([^/]+)/request", path)
        memory = re.fullmatch(r"/tutor/memories/(\d+)", path)
        if store is None or not (
            one
            or close
            or offer
            or last
            or memory
            or path in ("/tutor/chats", "/tutor/memories")
        ):
            return False
        if method == "POST" and close:
            self._close_tutor_chat(store, close.group(1), api_key)
        elif method == "POST" and offer:
            body = self._read_body()
            position, place = body.get("position"), body.get("place")
            if type(position) is not int or type(place) is not int:
                raise ValueError(
                    "an exercise offered is told by its position and place"
                )
            store.set_tutor_offer(
                offer.group(1),
                position,
                place,
                str(body.get("session") or ""),
                str(body.get("status") or ""),
            )
            self._reply(HTTPStatus.OK, {})
        elif method == "GET" and last:
            self._reply(
                HTTPStatus.OK, {"request": store.last_tutor_request(last.group(1))}
            )
        elif method == "GET" and path == "/tutor/memories":
            self._reply(
                HTTPStatus.OK,
                {"memories": store.memories(), "removed": store.memories(removed=True)},
            )
        elif method == "DELETE" and memory:
            store.remove_memory(int(memory.group(1)), "", "learner")
            self._reply(HTTPStatus.OK, {})
        elif method == "GET" and path == "/tutor/chats":
            self._reply(HTTPStatus.OK, {"chats": store.tutor_chats()})
        elif method == "GET" and one:
            chat = store.tutor_chat(one.group(1))
            if chat is None:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such chat"})
            else:
                self._reply(HTTPStatus.OK, chat)
        elif method == "DELETE" and one:
            store.delete_tutor_chat(one.group(1))
            self._reply(HTTPStatus.OK, {})
        else:
            return False
        return True

    def _texts(self, method: str) -> bool:
        """Answers a request about the learner's texts, such as their
        homework, and the corrections of them, and returns whether the
        request was one.

            GET /texts            the texts and corrections, the one changed
                                  last first, without what they say
            GET /texts/ID         a text or a correction, with what it says
            PUT /texts/ID         keep a text as `{"title": ..., "content":
                                  ..., "language": ...}`, starting it if
                                  there is none; one that was corrected,
                                  or a correction, is not changed
            DELETE /texts/ID      delete a text or a correction
        """
        store = self.account.store
        path = urlsplit(self.path).path
        one = re.fullmatch(r"/texts/([^/]+)", path)
        if store is None or not (one or path == "/texts"):
            return False
        if method == "GET" and not one:
            self._reply(HTTPStatus.OK, {"texts": store.texts()})
        elif method == "GET" and one:
            text = store.text(one.group(1))
            if text is None:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such text"})
            else:
                self._reply(HTTPStatus.OK, text)
        elif method == "PUT" and one:
            body = self._read_body()
            title, content = body.get("title", ""), body.get("content", "")
            if not isinstance(title, str) or not isinstance(content, str):
                raise ValueError('a text is {"title": ..., "content": ...}')
            language = body.get("language")
            store.save_text(
                one.group(1),
                title,
                content,
                language if isinstance(language, str) else self.account.language,
            )
            self._reply(HTTPStatus.OK, {})
        elif method == "DELETE" and one:
            store.delete_text(one.group(1))
            self._reply(HTTPStatus.OK, {})
        else:
            return False
        return True

    def _close_tutor_chat(
        self, store: UserStore, chat_id: str, api_key: str | None
    ) -> None:
        """Close a chat with the tutor, and start what decides what the
        tutor is to remember of it, if it was open and anything was said."""
        model = read_model(self._read_body().get("model"), api_key or "")
        chat = store.tutor_chat(chat_id)
        if chat is None:
            self._reply(HTTPStatus.NOT_FOUND, {"error": "no such chat"})
            return
        started = []
        if store.close_tutor_chat(chat_id) and chat["messages"]:
            ask = model_asker(send_chat, model)

            remembering = self.account.remembering

            def job(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
                with remembering:
                    # the recaps are written apart, and the strategy and the
                    # calendar by the tutor as it agrees on them
                    remembered, used = remember(
                        chat["messages"],
                        store.memories(kind="fact"),
                        chat["language"],
                        ask,
                    )
                    for content in remembered.add:
                        store.add_memory(content, chat_id)
                    for memory_id, why in remembered.remove:
                        store.remove_memory(memory_id, why, "tutor")
                step()
                return [asdict(remembered)], [describe_usage(used)]

            def recap_job(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
                written, used = recap(chat["messages"], chat["language"], ask)
                store.add_memory(written, chat_id, kind="recap")
                step()
                return [written], [describe_usage(used)]

            # the two are asked of the model at the same time
            started.append(
                self.account.tasks.start("memories", "Memories of the chat", 1, job)
            )
            started.append(
                self.account.tasks.start("memories", "Recap of the chat", 1, recap_job)
            )
        self._reply(HTTPStatus.OK, {"tasks": started})

    def _tutor(self, practice: Practice, api_key: str | None) -> None:
        """Has the tutor answer the last of the `messages` of a `{"messages":
        [...], "model": ..., "language": ..., "level": ...,
        "tone": ...}` request, `tone` being how the tutor is to talk, as the
        learner set it: the chat so far as the tutor was told it, which the reply
        adds to. Nothing of the chat is kept here.

        The reply is streamed, an event of the tutor to a line, as tutor.py
        says, as they come; the last is `{"type": "done", "messages": [...],
        "usage": [...]}`, with the messages that were added, or `{"type":
        "error", "error": ...}`.

        With a `"chat": ID`, what the learner wrote and what the tutor
        answered are kept in that chat with the tutor, which is started if
        there is none: the answer with all the model was told and added on
        the way, and what was shown of it, so that the chat can be taken up
        again as it was.

        A request that has `"practised": {"session": ..., "exercise": ...,
        "tasks": [...]}` in place of something the learner wrote tells the
        tutor how an exercise it offered went, once the `tasks` that write
        its log are done: what it is told is the first of the messages
        added."""
        store = self.account.store
        assert store is not None
        body = self._read_body()
        chat_id = body.get("chat")
        if chat_id is not None and not is_id(chat_id):
            raise ValueError("chat is the id of a chat with the tutor")
        kept = store.tutor_chat(chat_id) if chat_id is not None else None
        if kept is not None and kept["closedAt"] is not None:
            raise ValueError("the chat with the tutor is closed")
        done = body.get("practised")
        if done is not None and not (
            isinstance(done, dict)
            and isinstance(done.get("session"), str)
            and isinstance(done.get("exercise"), str)
            and isinstance(done.get("tasks", []), list)
        ):
            raise ValueError(
                'practised is {"session": ..., "exercise": ..., "tasks": [...]}'
            )
        messages = read_tutor_messages(body.get("messages"), to_answer=done is None)
        language, _, model = self._read_translating(body, api_key)
        titles = {each["id"]: each["title"] for each in practice.exercises()}
        level = body.get("level")
        # how the tutor is to talk, as the learner set it
        tone = body.get("tone")
        tone = tone[:MAX_TONE_LENGTH] if isinstance(tone, str) else ""
        try:
            lessons = practice.lessons(language)
        except GrammarError:
            lessons = []
        evaluations = self.account.evaluations
        try:
            levels = evaluations.levels(language) if evaluations else []
        except EvaluationError:
            levels = []
        intake = self.account.intake
        # asking after a language does not make a vocabulary of it
        vocabulary = (
            intake.vocabulary_of(language)
            if intake and intake.has_vocabulary(language)
            else None
        )
        anki_words = self._anki_words(language)
        sets = [str(kept["name"]) for kept in vocabulary.sets()] if vocabulary else []
        tools = [
            *data_tools(store, lambda: lessons, language, evaluations),
            *memory_tools(store),
            words_tool(
                partial(known_words, vocabulary, anki_words=anki_words),
                sets,
                anki=anki_words is not None,
                practised=practised_categories(language),
            ),
            *exercise_tool(practice.exercises(), lessons, store.topics()),
            *evaluation_tool(levels),
        ]
        told = instructions(
            language,
            level if isinstance(level, str) else "",
            store.memories(),
            tone,
        )
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        # for nginx, which would otherwise hold the events back until the end
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        # what is shown of the turn, kept with the answer to be shown again
        turn: dict[str, Any] = {"thinking": "", "steps": [], "offers": [], "exams": []}
        # the last request to the model, kept for the inspector of the chat
        last = LastCall(
            str(messages[-1].get("content") or "")
            if done is None
            else f"How “{done['exercise']}” went"
        )

        def emit(event: dict[str, Any]) -> None:
            last.follow(event)
            kind = event.get("type")
            if kind == "thinking":
                turn["thinking"] += event["text"]
            elif kind == "tool":
                turn["steps"].append(
                    {"id": event["id"], "doing": event["doing"], "status": "running"}
                )
            elif kind == "tool_done":
                for step in turn["steps"]:
                    if step["id"] == event["id"]:
                        step["status"] = "failed" if event["failed"] else "done"
                shown = event.get("shown") or {}
                if shown.get("kind") == "exercise":
                    turn["offers"].append(shown)
                elif shown.get("kind") == "evaluation":
                    turn["exams"].append(shown)
            self.wfile.write(json.dumps(event, ensure_ascii=False).encode() + b"\n")
            self.wfile.flush()

        said: list[dict[str, Any]] = []
        if done is not None:
            emit({"type": "tool", "id": "log", "name": "", "doing": "Writing the log"})
            wait_for(self.account.tasks.listing, [str(each) for each in done["tasks"]])
            emit({"type": "tool_done", "id": "log", "failed": False, "shown": None})
            try:
                said = [
                    practised(
                        store,
                        done["session"],
                        done["exercise"],
                        titles.get(done["exercise"]) or str(done["exercise"]),
                    )
                ]
            except ValueError as error:
                emit({"type": "error", "error": str(error)})
                return
        try:
            added, used = converse([*messages, *said], tools, model, told, emit)
        except TutorError as error:
            # what the requests that were answered used is counted all the same
            count_usage(
                store,
                "tutor",
                "tutor",
                [describe_usage(profile) for profile in spent_by(error)],
            )
            emit({"type": "error", "error": str(error)})
            return
        finally:
            record = last.record()
            if chat_id is not None and record is not None:
                store.save_last_tutor_request(chat_id, record)
        added = [*said, *added]
        if chat_id is not None:
            answer = "\n\n".join(
                message["content"]
                for message in added
                if message["role"] == "assistant" and message.get("content")
            )
            # Everything the model was told and added on the way is kept with
            # the answer, so that a chat taken up again is told it whole.
            kept = {
                "role": "assistant",
                "content": answer,
                "turn": {**turn, "messages": added},
            }
            store.add_tutor_messages(
                chat_id,
                language,
                [*([messages[-1]] if done is None else []), kept],
            )
        usage = [describe_usage(profile) for profile in used]
        count_usage(store, "tutor", "tutor", usage)
        emit({"type": "done", "messages": added, "usage": usage})

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
            # without an Anki account, there is nothing to take in
            self.account.anki is not None and body.get("enabled") is not False,
            model,
            decision_model,
            (anki_language or "").strip()[:MAX_LANGUAGE_LENGTH] or None,
        )
        if self.account.processor:
            # the messages and the exercises are processed with the same models
            self.account.processor.configure(model, decision_model)
        status, used = importer.status()
        usage = [describe_usage(profile) for profile in used]
        count_usage(self.account.store, "vocabulary", "vocabulary", usage)
        self._reply(HTTPStatus.OK, {**asdict(status), "usage": usage})

    def _translate_words(self, translator: WordTranslator, api_key: str | None) -> None:
        """Replies to a `{"language": ..., "into": ..., "model": ...,
        "start": ...}` request with what the translating of the words of
        `language` into `into` is doing, and how many words have no
        translations there, and starts it if `start` is true."""
        body = self._read_body()
        language, into, model = self._read_translating(body, api_key)
        if body.get("start") is True:
            translator.start(language, into, model)
        else:
            translator.keyed(model)
        status, used = translator.status(language, into)
        usage = [describe_usage(profile) for profile in used]
        count_usage(self.account.store, "vocabulary", "vocabulary", usage)
        self._reply(HTTPStatus.OK, {**asdict(status), "usage": usage})

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
        usage = [describe_usage(profile) for profile in used]
        count_usage(self.account.store, "vocabulary", "vocabulary", usage)
        self._reply(
            HTTPStatus.OK,
            {"words": [asdict(outcome) for outcome in outcomes], "usage": usage},
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
        text, caret, model, questions, rate_words, profile, correct_with, usage_id = (
            self._read_request(api_key)
        )
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
            text, caret, model, questions, rate_words, correct_with
        )
        log(f"{datetime.now():%H:%M:%S}\n{describe(sentences)}")
        used, pending = self.account.checker.billing()
        usage = [describe_usage(profile) for profile in used]
        count_usage(self.account.store, "checking", usage_id, usage)
        self._reply(
            HTTPStatus.OK,
            {
                "sentences": [asdict(sentence) for sentence in sentences],
                # the requests to the model that have come back since the
                # last time, including those whose answers were dropped
                "usage": usage,
                # whether any are still out, and so worth asking again for
                "pending": pending,
            },
        )

    def _read_request(
        self, api_key: str | None
    ) -> tuple[str, int | None, Model, Questions | None, bool, bool, Model | None, str]:
        """The parts of a `{"text": ..., "caret": ..., "model": ...,
        "questions": ..., "words": ..., "profile": ..., "correct": ...}`
        request body. The caret may be left out or null, for when the text
        box is not in use, and so may the model and the questions, for the
        model the server was started with and the usual questions. With
        `"profile": false` only the spelling is checked. `correct` is the
        language model that writes each finished sentence as it should be,
        if that is wanted, and null or left out if not. `usage` is what what
        the requests to the models used is counted under, such as the chat
        the text box is of, "checking" if it is left out."""
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
        correct = body.get("correct")
        correct_with = None if correct is None else read_model(correct, api_key or "")
        usage_id = body.get("usage")
        if not isinstance(usage_id, str) or not usage_id:
            usage_id = "checking"
        return (
            text,
            caret,
            model,
            questions,
            rate_words,
            profile,
            correct_with,
            usage_id[:MAX_USAGE_ID],
        )

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
    anki: AnkiLink | None = None,
) -> CheckerServer:
    """A server with an account for each user, or, given a `checker`, with
    the one account made of it and what else is given, for whoever asks."""
    if accounts is None:
        assert checker is not None
        one = Account(checker, intake, importer, anki=anki)
        accounts = Accounts(lambda user: one)
    return CheckerServer(port, accounts, users)


if __name__ == "__main__":
    # a Windows console may not be able to show every character that is typed
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # every name a word is stored with can be shown in the app's languages
    check_labels()
    # the language being studied, by its English name, until the chat says
    language = os.environ.get("CHECKER_LANGUAGE", DEFAULT_LANGUAGE)
    model = os.environ.get("CHECKER_PROFILE_MODEL", DEFAULT_MODEL)
    data_directory = Path(os.environ.get("CHECKER_DATA") or DATA_DIRECTORY)
    deck_status_url = os.environ.get("ANKI_STATUS_URL", DECK_STATUS_URL)

    def make_account(user: str) -> Account:
        """Everything a user has, with the vocabularies in a directory of
        the user's own."""
        profiler = Profiler(model)
        speller = StudySpeller(language)
        kept = UserStore(user_directory(data_directory, user))
        intake = Intake(
            Vocabularies(user_directory(data_directory, user)),
            profiler,
            # the language model asked about new words when a request names none
            model=os.environ.get("CHECKER_CHAT_MODEL", ""),
            known=speller.knows,
            into=partial(translating_into, kept),
        )
        anki = AnkiLink(user, deck_status_url)
        importer = AnkiImporter(
            intake,
            # the words of the decks the user chose
            lambda: anki.notes(kept.skipped_anki_decks()),
            api_key=os.environ.get("OPENROUTER_API_KEY", ""),
            on_taken=lambda outcomes: log(
                f"{datetime.now():%H:%M:%S} Anki words taken in for {user}\n"
                f"{describe_outcomes(outcomes)}"
            ),
        )
        kept.add_starter_topics(STARTER_TOPICS, starter_icon)
        processor = Processor(
            kept,
            intake,
            on_processed=lambda item, outcomes: log(
                f"{datetime.now():%H:%M:%S} processed a {item.kind} of {user}"
                f" ({item.role}, {len(outcomes)} words)"
            ),
        )
        tasks = Tasks(on_used=partial(count_task_usage, kept))
        # the language model asked when a request names none
        translator = Translator(model=os.environ.get("CHECKER_CHAT_MODEL", ""))
        account = Account(
            LiveChecker(
                speller,
                profiler,
                on_profiled=print_profile,
                on_rated=print_ratings,
                corrector=translator.correct,
                on_corrected=print_correction,
            ),
            intake,
            importer,
            kept,
            processor,
            anki=anki,
            translator=translator,
            speaker=Speaker(kept),
            tasks=tasks,
            practice=Practice(
                kept,
                lemmas_of=partial(lemmas_of, intake),
                on_words=log,
                later=in_background(tasks, "log"),
                anki=anki,
            ),
        )
        assert account.practice
        account.words = WordTranslator(intake)
        account.evaluations = Evaluations(
            kept, account.practice, later=in_background(tasks, "log")
        )
        processor.watch()
        account.study(language)
        importer.watch()
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
    print(f"The Anki accounts of the users are kept by {deck_status_url}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
