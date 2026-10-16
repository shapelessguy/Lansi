# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Translates what was selected in a text, and answers what is asked about
it afterwards.

A language model is given the selection with the sentences it is in and the
few before them, so that it translates the words as they are meant there. It
is told to write the translation and nothing else. What is asked afterwards
goes to it with the same passage and the translation it gave.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from intake import Chat, read_usage, send_chat
from profiling import Profile, ProfileError
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
# The language a selection is translated into when the request names none.
DEFAULT_INTO = "English"
# A translation of a few words takes no thinking over, and a model that
# thinks first keeps the reader waiting, and is paid for what it thought.
NO_THINKING = {"reasoning": {"enabled": False}}
# what the selection is put between in the passage the model is given
MARKS = ("[[", "]]")

TRANSLATING = """\
You translate for someone who is learning {language}. You are given a passage \
in which a selection is marked with [[ and ]]. Translate the selection, and \
only the selection, into {into}, as it is meant in the passage. If the \
selection is in {into} already, translate it into {language} instead.

Reply with the translation alone: no quotation marks, no brackets, no notes, \
no alternatives, and nothing of the rest of the passage."""

CHATTING = """\
You help someone who is learning {language} with something they are reading. \
They selected part of a passage and were given a translation of it into \
{into}. Answer what they ask about it. Be brief, and write in {into} unless \
they write to you in another language.

The passage, with the selection marked with [[ and ]]:
{passage}

The selection:
{selection}

The translation they were given:
{translation}"""


class TranslationError(Exception):
    """A translation or an answer could not be had. The message says why."""


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
        api_key: str,
        model: str | None = None,
    ) -> tuple[str, Profile]:
        """The selection of `passage` in the language `into`, for someone
        learning `language`, with what asking for it used. Raises
        TranslationError."""
        return self._ask(
            TRANSLATING.format(language=language, into=into),
            [{"role": "user", "content": passage.marked()}],
            api_key,
            model,
            NO_THINKING,
        )

    def answer(
        self,
        passage: Passage,
        translation: str,
        messages: list[dict[str, str]],
        language: str,
        into: str,
        api_key: str,
        model: str | None = None,
    ) -> tuple[str, Profile]:
        """What the model says to the last of `messages`, which are what was
        asked and answered so far about the selection of `passage` and the
        `translation` given of it. Raises TranslationError."""
        instructions = CHATTING.format(
            language=language,
            into=into,
            passage=passage.marked(),
            selection=passage.selection,
            translation=translation,
        )
        return self._ask(instructions, messages, api_key, model)

    def asker(
        self, api_key: str, model: str | None = None
    ) -> Callable[[list[dict[str, Any]]], tuple[str, Profile]]:
        """What asks the model the messages it is given, as they are, such
        as for the logs of what was asked. It raises TranslationError."""
        return lambda messages: self._send(messages, api_key, model)

    def _ask(
        self,
        instructions: str,
        messages: list[dict[str, str]],
        api_key: str,
        model: str | None,
        more: dict[str, Any] | None = None,
    ) -> tuple[str, Profile]:
        system = {"role": "system", "content": instructions}
        return self._send([system, *messages], api_key, model, more)

    def _send(
        self,
        messages: list[dict[str, Any]],
        api_key: str,
        model: str | None,
        more: dict[str, Any] | None = None,
    ) -> tuple[str, Profile]:
        model = model or self._model
        if not api_key:
            raise TranslationError("an OpenRouter key is needed")
        if not model:
            raise TranslationError("no model was named")
        body = {
            "model": model,
            "messages": messages,
            "usage": {"include": True},
            **(more or {}),
        }
        try:
            try:
                response = self._chat(body, api_key)
            except ProfileError as error:
                if not more or "(400)" not in str(error):
                    raise
                # A model that cannot do as the extras say, such as one that
                # cannot but think, is asked without them.
                response = self._chat(
                    {name: value for name, value in body.items() if name not in more},
                    api_key,
                )
        except ProfileError as error:
            # whatever kept the model from answering is what there is to say
            raise TranslationError(str(error)) from None
        return read_text(response), read_usage(response, model)
