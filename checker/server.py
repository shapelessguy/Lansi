# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""A small local server the chat sends what is being typed to.

It splits the text into sentences, spell-checks each one, has each finished
sentence profiled, prints what it finds, and returns the sentences.
"""

from __future__ import annotations

import io
import json
import os
import sys
import threading
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from live import LiveChecker
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
from spelling import Speller

HOST = "127.0.0.1"
# The request header the chat sends its OpenRouter key in.
KEY_HEADER = "X-OpenRouter-Key"
DEFAULT_PORT = 8092
DEFAULT_LANGUAGE = "de"
# far more than anyone types into a chat box
MAX_BODY_BYTES = 1_000_000


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


_log_lock = threading.Lock()


def log(entry: str) -> None:
    """Prints one entry at a time, as requests and profiles finish on
    different threads and their lines would otherwise run into each other."""
    with _log_lock:
        print(entry, flush=True)


class CheckerServer(ThreadingHTTPServer):
    def __init__(self, port: int, checker: LiveChecker) -> None:
        super().__init__((HOST, port), CheckerHandler)
        self.checker = checker


class CheckerHandler(BaseHTTPRequestHandler):
    server: CheckerServer

    def do_POST(self) -> None:
        if self.path != "/sentences":
            self._reply(HTTPStatus.NOT_FOUND, {"error": "no such path"})
            return
        try:
            text, caret, model, questions, rate_words = self._read_request()
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        # The chat sends the key from its settings; one set where the server
        # runs is used otherwise. Without either, sentences are only
        # profiled while there is a model on this machine to ask.
        api_key = self.headers.get(KEY_HEADER) or os.environ.get("OPENROUTER_API_KEY")
        sentences = self.server.checker.check(
            text, caret, api_key or None, model, questions, rate_words
        )
        log(f"{datetime.now():%H:%M:%S}\n{describe(sentences)}")
        used, pending = self.server.checker.billing()
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
                "local_model": self.server.checker.local_model(),
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
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY_BYTES:
            raise ValueError("text is too long")
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError:
            raise ValueError("body is not JSON") from None
        text = body.get("text") if isinstance(body, dict) else None
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


def make_server(port: int, checker: LiveChecker) -> CheckerServer:
    return CheckerServer(port, checker)


if __name__ == "__main__":
    # a Windows console may not be able to show every character that is typed
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    language = os.environ.get("CHECKER_LANGUAGE", DEFAULT_LANGUAGE)
    model = os.environ.get("CHECKER_PROFILE_MODEL", DEFAULT_MODEL)
    # set to nothing to leave a model on this machine alone
    local_endpoint = os.environ.get("CHECKER_LOCAL_URL", LOCAL_ENDPOINT)
    local = None
    if local_endpoint:
        local = LocalModel(local_endpoint, on_change=print_local_model)
    server = make_server(
        int(os.environ.get("CHECKER_PORT", DEFAULT_PORT)),
        LiveChecker(
            Speller(language),
            Profiler(model, local=local),
            on_profiled=print_profile,
            on_rated=print_ratings,
        ),
    )
    print(
        f"Checker listening on http://{HOST}:{server.server_port}"
        f" (spelling: {language}, profiles: {model})",
        flush=True,
    )
    if local:
        print(f"Looking for a local model at {local.endpoint}", flush=True)
        local.watch(float(os.environ.get("CHECKER_LOCAL_POLL_SECS", LOCAL_POLL_SECS)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
