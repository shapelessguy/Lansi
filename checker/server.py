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
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from anki_import import DECK_STATUS_URL, AnkiImporter, fetch_anki_notes
from categories import CATEGORIES
from intake import DEFAULT_LANGUAGE, Intake, Outcome, Word, read_words
from live import LiveChecker
from processing import Processor
from profiling import (
    DEFAULT_MODEL,
    LOCAL_ENDPOINT,
    LOCAL_POLL_SECS,
    LocalModel,
    Profile,
    Profiler,
    Questions,
    WordRating,
    read_questions,
)
from sentences import Sentence
from spelling import StudySpeller
from storage import UserStore
from users import Users, take_vocabulary, user_directory
from vocabulary import Vocabularies, Vocabulary

HOST = "127.0.0.1"
# The request header the chat sends its OpenRouter key in.
KEY_HEADER = "X-OpenRouter-Key"
DEFAULT_PORT = 8092
# far more than anyone types into a chat box
MAX_BODY_BYTES = 1_000_000
# the audio of a text of a few minutes, uncompressed, with room to spare
MAX_AUDIO_BYTES = 60_000_000
# a language is named in a word or two
MAX_LANGUAGE_LENGTH = 40
# The directory everything is kept in, unless CHECKER_DATA names another:
# who may log in, and for each user a directory with the vocabularies, one
# file for each language.
DATA_DIRECTORY = Path(__file__).parent / "data"
# The file that says who may log in, unless CHECKER_USERS names another. It
# is edited by hand, and read every time someone logs in.
USERS_FILE = Path(__file__).parent.parent / "users.json"


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


def print_local_model(model: str | None) -> None:
    """Announces that a model on this machine has been found, or has gone."""
    if model:
        log(f"{datetime.now():%H:%M:%S} local model found: {model}. It is asked now.")
    else:
        log(f"{datetime.now():%H:%M:%S} local model gone. OpenRouter is asked now.")


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
    # the chats, texts and settings of the user
    store: UserStore | None = None
    # what takes the words of those chats and texts into the vocabulary
    processor: Processor | None = None

    def study(self, language: str) -> None:
        """Have every part go by `language`, given by its English name."""
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
        self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})

    def do_DELETE(self) -> None:
        if not self._find_account() or self._kept("DELETE") or self._sets("DELETE"):
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

    def _kept(self, method: str) -> bool:
        """Answers a request about what the user has kept: the chats, the
        texts with their audio, and the settings. Returns whether the
        request was one of those.

            GET /chats                the chats, each with its messages
            PUT, DELETE /chats/ID     keep a chat as it is sent, or remove it
            GET /texts                the texts
            PUT, DELETE /texts/ID     keep a text as it is sent, or remove it
            GET, PUT /texts/ID/audio  the audio of a text, as a file
            GET, PUT /settings        the settings
        """
        store = self.account.store
        path = urlsplit(self.path).path
        one = re.fullmatch(r"/(chats|texts)/([^/]+)(/audio)?", path)
        if store is None or not (one or path in ("/chats", "/texts", "/settings")):
            return False
        try:
            if method == "GET" and path == "/chats":
                self._reply(HTTPStatus.OK, {"chats": store.chats()})
            elif method == "GET" and path == "/texts":
                self._reply(HTTPStatus.OK, store.texts())
            elif method == "GET" and path == "/settings":
                self._reply(HTTPStatus.OK, {"settings": store.settings()})
            elif method == "PUT" and path == "/settings":
                store.save_settings(self._read_body())
                self._reply(HTTPStatus.OK, {})
            elif one and one.group(3):
                self._audio(method, store, one.group(2))
            elif one and method == "PUT" and one.group(1) == "chats":
                chat = self._read_body()
                if chat.get("id") != one.group(2):
                    raise ValueError("a chat is kept under its own id")
                store.save_chat(chat)
                self._reply(HTTPStatus.OK, {})
            elif one and method == "PUT":
                store.save_text(one.group(2), self._read_body())
                self._reply(HTTPStatus.OK, {})
            elif one and method == "DELETE" and one.group(1) == "chats":
                store.delete_chat(one.group(2))
                self._reply(HTTPStatus.OK, {})
            elif one and method == "DELETE":
                store.delete_text(one.group(2))
                self._reply(HTTPStatus.OK, {})
            else:
                return False
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        return True

    def _audio(self, method: str, store: UserStore, text_id: str) -> None:
        """Keeps the audio a PUT brings for a text, or sends the audio of a
        text back for a GET, as the file it is."""
        if method == "PUT":
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_AUDIO_BYTES:
                raise ValueError("the audio is too long")
            content_type = self.headers.get("Content-Type") or "audio/wav"
            if store.save_audio(text_id, self.rfile.read(length), content_type):
                self._reply(HTTPStatus.OK, {})
            else:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such text"})
            return
        audio = store.audio(text_id) if method == "GET" else None
        if audio is None:
            self._reply(HTTPStatus.NOT_FOUND, {"error": "no audio"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", audio[1])
        self.send_header("Content-Length", str(len(audio[0])))
        self.end_headers()
        self.wfile.write(audio[0])

    def do_GET(self) -> None:
        if not self._find_account() or self._kept("GET") or self._sets("GET"):
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
        # runs is used otherwise. Without either, only a model on this
        # machine can be asked.
        api_key = self.headers.get(KEY_HEADER) or os.environ.get("OPENROUTER_API_KEY")
        try:
            if self.path == "/login":
                self._log_in()
            elif not self._find_account():
                pass
            elif self.path == "/sentences":
                self._check_sentences(api_key)
            elif self.path == "/vocabulary/words" and self.account.intake:
                self._take_words(self.account.intake, api_key)
            elif self.path == "/vocabulary/import" and self.account.importer:
                self._import(self.account.importer, api_key)
            else:
                self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def _import(self, importer: AnkiImporter, api_key: str | None) -> None:
        """Takes the `{"enabled": ..., "model": ..., "decision_model": ...,
        "language": ..., "anki_language": ...}`
        of a request, and the key it came with, as what the import of the
        Anki words is to go by, and replies with what the import is doing
        and the requests to the models it has made since it was last asked."""
        body = self._read_body()
        models = []
        for name in ("model", "decision_model"):
            model = body.get(name)
            if model is not None and not isinstance(model, str):
                raise ValueError(f"{name} must be text or null")
            models.append(model or None)
        self._take_language(body)
        # the language the Anki words are of, which need not be the one studied
        anki_language = body.get("anki_language")
        if anki_language is not None and not isinstance(anki_language, str):
            raise ValueError("anki_language must be text or null")
        importer.configure(
            body.get("enabled") is not False,
            api_key or "",
            models[0],
            models[1],
            (anki_language or "").strip()[:MAX_LANGUAGE_LENGTH] or None,
        )
        if self.account.processor:
            # the messages and texts are processed with the same key and models
            self.account.processor.configure(api_key or "", models[0], models[1])
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
        models = []
        for name in ("model", "decision_model"):
            model = body.get(name)
            if model is not None and not isinstance(model, str):
                raise ValueError(f"{name} must be text or null")
            models.append(model or None)
        outcomes, used = intake.take(words, api_key or "", models[0], models[1])
        log(f"{datetime.now():%H:%M:%S} words taken in\n{describe_outcomes(outcomes)}")
        self._reply(
            HTTPStatus.OK,
            {
                "words": [asdict(outcome) for outcome in outcomes],
                "usage": [describe_usage(profile) for profile in used],
            },
        )

    def _check_sentences(self, api_key: str | None) -> None:
        text, caret, model, questions, rate_words = self._read_request()
        sentences = self.account.checker.check(
            text, caret, api_key or None, model, questions, rate_words
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
                # the model on this machine that answers the questions at
                # present, or null if OpenRouter does
                "local_model": self.account.checker.local_model(),
            },
        )

    def _read_request(
        self,
    ) -> tuple[str, int | None, str | None, Questions | None, bool]:
        """The parts of a `{"text": ..., "caret": ..., "model": ...,
        "questions": ...}` request body. The caret may be left out or null,
        for when the text box is not in use, and so may the model and the
        questions, for the model the server was started with and the usual
        questions."""
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
        model = body.get("model")
        if model is not None and not isinstance(model, str):
            raise ValueError("model must be text or null")
        questions = body.get("questions")
        if questions is not None:
            questions = read_questions(questions)
        # whether to rate the words of each sentence once it is profiled
        rate_words = body.get("words") is True
        return text, caret, model or None, questions, rate_words

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
    # set to nothing to leave a model on this machine alone
    local_endpoint = os.environ.get("CHECKER_LOCAL_URL", LOCAL_ENDPOINT)
    local = None
    if local_endpoint:
        local = LocalModel(local_endpoint, on_change=print_local_model)
    data_directory = Path(os.environ.get("CHECKER_DATA") or DATA_DIRECTORY)
    deck_status_url = os.environ.get("ANKI_STATUS_URL", DECK_STATUS_URL)

    def make_account(user: str) -> Account:
        """Everything a user has, with the vocabularies in a directory of
        the user's own."""
        profiler = Profiler(model, local=local)
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
        processor = Processor(
            kept,
            intake,
            on_processed=lambda item, outcomes: log(
                f"{datetime.now():%H:%M:%S} processed a {item.kind} of {user}"
                f" ({item.role}, {len(outcomes)} words)"
            ),
        )
        account = Account(
            LiveChecker(
                speller, profiler, on_profiled=print_profile, on_rated=print_ratings
            ),
            intake,
            importer,
            kept,
            processor,
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
    print(f"Anki words are imported from {deck_status_url}", flush=True)
    if local:
        print(f"Looking for a local model at {local.endpoint}", flush=True)
        local.watch(float(os.environ.get("CHECKER_LOCAL_POLL_SECS", LOCAL_POLL_SECS)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
