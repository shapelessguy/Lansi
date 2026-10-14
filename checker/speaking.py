# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Has the sentences of a book read aloud by a speech model, and keeps the
audio, so that a sentence is paid for once.

A message of a chat is read the same way, and its audio kept under the id
of the chat, with the place of the message among the messages where a book
has the place of a paragraph.

Every sentence of a book has an id: the place of its paragraph among the
paragraphs of the book, and its own place among the sentences of that
paragraph, such as `12.3`. The audio of a sentence is kept under the id of
the book and the id of the sentence. Each sentence is asked for by itself,
a few at a time, so that the first can be played while the others are still
being made. The next to be made is always the one that will be listened to
soonest: the first that is missing from where the listener is, who may skip
ahead or go back.
"""

from __future__ import annotations

import io
import json
import re
import threading
import urllib.error
import urllib.request
import uuid
import wave
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from sentences import split_sentences
from storage import UserStore

ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"
TIMEOUT_SECS = 60
# what Gemini's speech models produce when the reply does not say otherwise
DEFAULT_SAMPLE_RATE = 24_000
# how many sentences are being read at the same time
WORKERS = 3
# more than anyone listens to in one go
MAX_SENTENCES = 300


class SpeechError(Exception):
    """A sentence could not be read aloud. The message says why."""


@dataclass
class BookSentence:
    """A sentence of a book."""

    # the place of its paragraph, and its own place in it, such as "12.3"
    id: str
    # the place of its paragraph among the paragraphs of the book
    block: int
    # where it is in the text of its paragraph
    start: int
    end: int
    text: str


def sentences_between(
    blocks: list[dict[str, Any]], start_block: int, start: int, end_block: int, end: int
) -> list[BookSentence]:
    """The sentences of a book that a selection has all or part of. The
    selection goes from `start` in the text of the paragraph `start_block`
    to `end` in the text of the paragraph `end_block`."""
    found = []
    for number in range(max(0, start_block), min(len(blocks), end_block + 1)):
        text = blocks[number].get("text")
        if not isinstance(text, str):
            continue
        from_ = start if number == start_block else 0
        to = end if number == end_block else len(text)
        for place, sentence in enumerate(split_sentences(text)):
            if sentence.end > from_ and sentence.start < to:
                found.append(
                    BookSentence(
                        f"{number}.{place}",
                        number,
                        sentence.start,
                        sentence.end,
                        sentence.text,
                    )
                )
    return found


# the marks of Markdown, which a reply in a chat is written in and which are not read out
_MARKUP = re.compile(r"[#*_`>~]+")


# Emoticons and other little pictures, with what joins and colours them. A
# speech model reads them out by their names, or stumbles over them.
_PICTURES = re.compile(
    "[\U0001f000-\U0001faff\u2190-\u21ff\u2300-\u23ff\u2600-\u27bf"
    "\u2b00-\u2bff\u200d\ufe0f\u20e3\U000e0020-\U000e007f]+"
)


def sentences_of_message(text: str, place: int) -> list[BookSentence]:
    """The sentences of a message of a chat, which is the one at `place`
    among the messages. They have ids as those of a book have, with the
    place of the message for that of a paragraph, and are where they are in
    the message once the marks of Markdown and the emoticons are taken out
    of it. What is left without a letter or a digit is no sentence to
    read."""
    spoken = _PICTURES.sub("", _MARKUP.sub("", text))
    sentences = [
        sentence
        for sentence in split_sentences(spoken)
        if any(character.isalnum() for character in sentence.text)
    ]
    return [
        BookSentence(
            f"{place}.{number}", place, sentence.start, sentence.end, sentence.text
        )
        for number, sentence in enumerate(sentences)
    ]


# Sends a request body with an API key, and returns the audio, the kind of
# file it is as the reply names it, and the id the request goes by.
SendSpeech = Callable[[dict[str, Any], str], tuple[bytes, str, str]]


def send_speech(body: dict[str, Any], api_key: str) -> tuple[bytes, str, str]:
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECS) as response:
            return (
                response.read(),
                response.headers.get("Content-Type") or "",
                response.headers.get("X-Generation-Id") or "",
            )
    except urllib.error.HTTPError as error:
        try:
            message = json.load(error)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            message = error.reason
        raise SpeechError(
            f"OpenRouter refused the request ({error.code}): {message}"
        ) from None
    except OSError as error:
        raise SpeechError(f"could not reach OpenRouter: {error}") from None


def playable(data: bytes, content_type: str) -> tuple[bytes, str]:
    """What a speech model returned as a file players can open, with the
    kind of file it is. Samples that come bare are given the header of a WAV
    file."""
    kind = content_type.lower()
    if "mpeg" in kind or "mp3" in kind:
        return data, "audio/mpeg"
    if "wav" in kind:
        return data, "audio/wav"
    rate = DEFAULT_SAMPLE_RATE
    if "rate=" in kind:
        digits = kind.split("rate=")[1].split(";")[0].strip()
        rate = int(digits) if digits.isdigit() else rate
    file = io.BytesIO()
    with wave.open(file, "wb") as audio:
        # one channel of 16-bit samples
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(data)
    return file.getvalue(), "audio/wav"


class Speaker:
    """Reads the sentences of the books of one user aloud."""

    def __init__(
        self, store: UserStore, send: SendSpeech = send_speech, workers: int = WORKERS
    ) -> None:
        self._store = store
        self._send = send
        self._workers = workers
        # set once the audio of a sentence that is being made is there, or
        # is given up on, by the id of the book and of the sentence
        self._pending: dict[tuple[str, str], threading.Event] = {}
        # why the audio of a sentence could not be made, the last time
        self._failures: dict[tuple[str, str], str] = {}
        # One for each sentence whose audio is being made, so that two
        # readings that want the same sentence do not both pay for it.
        self._making: dict[tuple[str, str], threading.Lock] = {}
        # the readings that were told to stop
        self._stopped: set[str] = set()
        # where the listener of each reading is, among its sentences
        self._places: dict[str, int] = {}
        self._lock = threading.Lock()

    def kept(
        self, book_id: str, sentences: list[BookSentence], model: str, voice: str
    ) -> list[bool]:
        """Whether the audio of each sentence is kept, as it is now written
        and as that model reads it in that voice."""
        spoken = self._store.spoken(book_id)
        return [
            spoken.get(sentence.id) == (sentence.text, model, voice)
            for sentence in sentences
        ]

    def start(self, book_id: str, sentences: list[BookSentence]) -> str:
        """Say that the audio of these sentences is about to be made, so
        that whoever asks for it waits. Returns what the reading goes by,
        to stop it with."""
        with self._lock:
            for sentence in sentences:
                self._pending.setdefault((book_id, sentence.id), threading.Event())
                self._failures.pop((book_id, sentence.id), None)
        return uuid.uuid4().hex

    def make(
        self,
        reading: str,
        book_id: str,
        sentences: list[BookSentence],
        api_key: str,
        model: str,
        voice: str,
        instructions: str = "",
        step: Callable[[], None] | None = None,
        places: list[int] | None = None,
    ) -> list[dict[str, str]]:
        """Have the audio of each sentence made and kept, a few at a time,
        and return what became of each: its text as `word`, a `status` of
        "made", "failed" or "stopped", the `reason` it failed for, and the
        id the request to the model goes by as `generation`.

        `places` says where each sentence is among all that are listened
        to, some of which may need no making. The next sentence to be made
        is the first from where the listener is, as `listen_at` says, and
        once all of those are made, the nearest before."""
        where = places if places is not None else list(range(len(sentences)))
        waiting = set(range(len(sentences)))
        outcomes: list[dict[str, str]] = [{} for _ in sentences]

        def next_one() -> int | None:
            with self._lock:
                if not waiting:
                    return None
                at = self._places.get(reading, 0)
                ahead = [number for number in waiting if where[number] >= at]
                number = min(ahead) if ahead else max(waiting)
                waiting.remove(number)
                return number

        def work() -> None:
            while (number := next_one()) is not None:
                outcomes[number] = one(sentences[number])

        def one(sentence: BookSentence) -> dict[str, str]:
            outcome = {"word": sentence.text, "status": "made", "reason": ""}
            key = (book_id, sentence.id)
            try:
                with self._lock:
                    stopped = reading in self._stopped
                if stopped:
                    outcome["status"] = "stopped"
                    return outcome
                with self._lock:
                    making = self._making.setdefault(key, threading.Lock())
                with making:
                    if self.kept(book_id, [sentence], model, voice) == [True]:
                        # another reading has made it in the meantime
                        return outcome
                    body = {
                        "model": model,
                        "input": sentence.text,
                        "voice": voice,
                        "response_format": "pcm",
                    }
                    if instructions.strip():
                        body["instructions"] = instructions.strip()
                    data, content_type, generation = self._send(body, api_key)
                    if not data:
                        raise SpeechError("the speech model returned no audio")
                    audio, kind = playable(data, content_type)
                    self._store.save_speech(
                        book_id, sentence.id, sentence.text, model, voice, audio, kind
                    )
                    outcome["generation"] = generation
            except (SpeechError, ValueError) as error:
                outcome["status"], outcome["reason"] = "failed", str(error)
                with self._lock:
                    self._failures[key] = str(error)
            finally:
                with self._lock:
                    done = self._pending.pop(key, None)
                    self._making.pop(key, None)
                if done:
                    done.set()
                if step:
                    step()
            return outcome

        try:
            with ThreadPoolExecutor(max_workers=self._workers) as pool:
                for _ in range(self._workers):
                    pool.submit(work)
            return outcomes
        finally:
            with self._lock:
                self._stopped.discard(reading)
                self._places.pop(reading, None)

    def listen_at(self, reading: str, place: int) -> None:
        """Say which of the sentences of a reading is being listened to, so
        that those from there on are made next."""
        with self._lock:
            self._places[reading] = place

    def stop(self, reading: str) -> None:
        """Have the sentences of a reading that are not being read yet left
        unread."""
        with self._lock:
            self._stopped.add(reading)

    def audio(
        self, book_id: str, sentence_id: str, wait_secs: float = 0.0
    ) -> tuple[bytes, str]:
        """The audio of a sentence with the kind of file it is. If it is
        being made, it is waited for, for as long as `wait_secs`. Raises
        SpeechError if there is none."""
        key = (book_id, sentence_id)
        with self._lock:
            pending = self._pending.get(key)
        if pending and not pending.wait(wait_secs):
            raise SpeechError("the audio is not made yet")
        with self._lock:
            failure = self._failures.get(key)
        if failure:
            raise SpeechError(failure)
        kept = self._store.speech(book_id, sentence_id)
        if kept is None:
            raise SpeechError("there is no audio of this sentence")
        return kept
