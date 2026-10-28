# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Translates what was selected in a text, and answers what is asked about
it afterwards. It also corrects the sentences the learner writes.

A language model is given the selection with the sentences it is in and the
few before them, so that it translates the words as they are meant there. It
is told to write the translation and nothing else. What is asked afterwards
goes to it with the same passage and the translation it gave.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from intake import Chat, read_usage, send_chat
from models import Model
from profiling import Profile, ProfileError
from prompts import PROMPTS
from sentences import split_sentences

# How many sentences before those the selection is in are given with it.
SENTENCES_BEFORE = 5
# more than anyone selects to have translated
MAX_SELECTION_LENGTH = 5000
# How much of the text before and after the selection is looked at for the
# sentences around it. What is further away is dropped.
MAX_BEFORE_LENGTH = 4000
MAX_AFTER_LENGTH = 2000
# a chat about a few words does not go on for longer
MAX_MESSAGES = 100
MAX_MESSAGE_LENGTH = 10_000
# A translation of a few words takes no thinking over, and a model that
# thinks first keeps the reader waiting, and is paid for what it thought.
# what the selection is put between in the passage the model is given
MARKS = ("[[", "]]")


class TranslationError(Exception):
    """A translation or an answer could not be had. The message says why."""


@dataclass
class Corrected:
    """A sentence as it should be, and what it means in the language the
    learner reads, empty if the model did not say."""

    sentence: str
    translation: str = ""


def read_corrected(said: str) -> Corrected:
    """What a model wrote of a sentence it corrected: the JSON of its
    correction and translation, which it may have put in a fenced block or
    among words of its own, or written with its values not in quotes; or,
    where there is none to read, all it wrote, as the correction alone."""
    start, end = said.find("{"), said.rfind("}")
    if 0 <= start < end:
        try:
            read = json.loads(said[start : end + 1])
        except ValueError:
            read = None
        if isinstance(read, dict) and isinstance(read.get("correction"), str):
            translation = read.get("translation")
            return Corrected(
                read["correction"].strip(),
                translation.strip() if isinstance(translation, str) else "",
            )
        # such as {"correction": Er ist gut., "translation": He is good.}
        loose = _LOOSE_CORRECTED.search(said[start : end + 1])
        if loose:
            return Corrected(
                _unquoted(loose.group("correction")),
                _unquoted(loose.group("translation") or ""),
            )
    return Corrected(said.strip())


# what a model wrote as JSON with the values not in quotes, or not all of them
_LOOSE_CORRECTED = re.compile(
    r'\{\s*"?correction"?\s*:\s*(?P<correction>.*?)\s*'
    r'(?:,\s*"?translation"?\s*:\s*(?P<translation>.*?))?\s*\}\s*$',
    re.DOTALL,
)


def _unquoted(value: str) -> str:
    """A value of loose JSON without the quotes it may have."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value.strip()


@dataclass
class Passage:
    """A selection with what is around it, which read one after another are
    the sentences the selection is in and those before them."""

    before: str
    selection: str
    after: str

    def marked(self) -> str:
        """The whole of it, with the selection between the marks."""
        return f"{self.before}{MARKS[0]}{self.selection}{MARKS[1]}{self.after}"


def passage_of(before: str, selection: str, after: str) -> Passage:
    """The sentences `selection` is in, and the SENTENCES_BEFORE before
    them, cut out of the text it was selected in: `before` is the text up to
    the selection, and `after` the text from its end. Space at the ends of
    the selection is not part of it. Raises ValueError if nothing is left."""
    kept = selection.strip()
    if not kept:
        raise ValueError("nothing is selected")
    before += selection[: len(selection) - len(selection.lstrip())]
    after = selection[len(selection.rstrip()) :] + after
    before = before[-MAX_BEFORE_LENGTH:]
    after = after[:MAX_AFTER_LENGTH]
    text = before + kept + after
    start, end = len(before), len(before) + len(kept)
    sentences = split_sentences(text)
    touched = [
        number
        for number, sentence in enumerate(sentences)
        if sentence.end > start and sentence.start < end
    ]
    first = max(0, touched[0] - SENTENCES_BEFORE)
    # a selection reaches as far as it does, whatever the sentences are
    from_ = min(start, sentences[first].start)
    to = max(end, sentences[touched[-1]].end)
    return Passage(text[from_:start], kept, text[end:to])


def read_text(response: dict[str, Any]) -> str:
    """What a chat response says. Raises TranslationError if it says nothing."""
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = None
    if not isinstance(content, str) or not content.strip():
        raise TranslationError("the model gave no answer")
    return content.strip()


def read_messages(value: object, to_answer: bool = True) -> list[dict[str, str]]:
    """Check the messages of a chat that came in from outside: what the user
    wrote and what was answered, in turn. A chat `to_answer` ends with what
    the user wrote; one that is over may end with anything, or be empty.
    Raises ValueError."""
    least = 1 if to_answer else 0
    if not isinstance(value, list) or not least <= len(value) <= MAX_MESSAGES:
        raise ValueError(f"messages must be a list of {least} to {MAX_MESSAGES}")
    messages = []
    for message in value:
        role = message.get("role") if isinstance(message, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if role not in ("user", "assistant") or not isinstance(content, str):
            raise ValueError("every message needs a role and a content")
        if len(content) > MAX_MESSAGE_LENGTH:
            raise ValueError("a message is too long")
        messages.append({"role": role, "content": content})
    if to_answer and messages[-1]["role"] != "user":
        raise ValueError("the last message must be the user's")
    return messages


class Translator:
    def __init__(self, chat: Chat = send_chat, model: str = "") -> None:
        self._chat = chat
        # the language model asked when a request names none
        self._model = model

    def translate(
        self,
        passage: Passage,
        language: str,
        into: str,
        model: Model,
    ) -> tuple[str, Profile]:
        """The selection of `passage` in the language `into`, for someone
        learning `language`, with what asking for it used. Raises
        TranslationError."""
        return self._ask(
            PROMPTS("translating.translating", language=language, into=into),
            [{"role": "user", "content": passage.marked()}],
            model,
        )

    def correct(
        self, sentence: str, language: str, model: Model, into: str = "English"
    ) -> tuple[Corrected, Profile]:
        """`sentence`, written by someone learning `language`, as it should
        be, or as it is if nothing in it is wrong, translated into `into`,
        with what asking for it used. Raises TranslationError."""
        said, used = self._ask(
            PROMPTS("correcting", language=language, into=into),
            [{"role": "user", "content": sentence}],
            model,
        )
        return read_corrected(said), used

    def answer(
        self,
        passage: Passage,
        translation: str,
        messages: list[dict[str, str]],
        language: str,
        into: str,
        model: Model,
    ) -> tuple[str, Profile]:
        """What the model says to the last of `messages`, which are what was
        asked and answered so far about the selection of `passage` and the
        `translation` given of it. Raises TranslationError."""
        instructions = PROMPTS(
            "translating.chatting",
            language=language,
            into=into,
            passage=passage.marked(),
            selection=passage.selection,
            translation=translation,
        )
        return self._ask(instructions, messages, model)

    def asker(
        self, model: Model
    ) -> Callable[[list[dict[str, Any]]], tuple[str, Profile]]:
        """What asks the model the messages it is given, as they are, such
        as for the logs of what was asked. It raises TranslationError."""
        return lambda messages: self._send(messages, model)

    def _ask(
        self,
        instructions: str,
        messages: list[dict[str, str]],
        model: Model,
    ) -> tuple[str, Profile]:
        system = {"role": "system", "content": instructions}
        return self._send([system, *messages], model)

    def _send(
        self,
        messages: list[dict[str, Any]],
        model: Model,
    ) -> tuple[str, Profile]:
        model = model.or_named(self._model)
        problem = model.problem()
        if problem:
            raise TranslationError(problem)
        body = {
            "model": model.name,
            "messages": messages,
            "usage": {"include": True},
        }
        try:
            response = self._chat(body, model)
        except ProfileError as error:
            # whatever kept the model from answering is what there is to say
            raise TranslationError(str(error)) from None
        return read_text(response), read_usage(response, model.name)
