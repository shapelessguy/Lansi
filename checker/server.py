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
from profiling import DEFAULT_MODEL, Profile, Profiler
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
        else:
            part = f"{name}={answer.score:.1f}/{answer.max_score}"
        if answer.confidence is not None:
            part += f" ({answer.confidence:.0%})"
        parts.append(part)
    return ", ".join(parts)


def print_profile(sentence: str, profile: Profile | None, error: str | None) -> None:
    """Announces a profile that has just come back."""
    result = describe_profile(profile) if profile else f"failed: {error}"
    log(f"{datetime.now():%H:%M:%S} profiled: {sentence}\n       {result}")


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
            text, caret, model = self._read_request()
        except ValueError as error:
            self._reply(HTTPStatus.BAD_REQUEST, {"error": str(error)})
            return
        # The chat sends the key from its settings; one set where the server
        # runs is used otherwise. Without either, sentences are not profiled.
        api_key = self.headers.get(KEY_HEADER) or os.environ.get("OPENROUTER_API_KEY")
        sentences = self.server.checker.check(text, caret, api_key or None, model)
        log(f"{datetime.now():%H:%M:%S}\n{describe(sentences)}")
        self._reply(HTTPStatus.OK, [asdict(sentence) for sentence in sentences])

    def _read_request(self) -> tuple[str, int | None, str | None]:
        """The parts of a `{"text": ..., "caret": ..., "model": ...}` request
        body. The caret may be left out or null, for when the text box is not
        in use, and so may the model, for the one the server was started with."""
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
        return text, caret, model or None

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
    server = make_server(
        int(os.environ.get("CHECKER_PORT", DEFAULT_PORT)),
        LiveChecker(Speller(language), Profiler(model), on_profiled=print_profile),
    )
    print(
        f"Checker listening on http://{HOST}:{server.server_port}"
        f" (spelling: {language}, profiles: {model})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
