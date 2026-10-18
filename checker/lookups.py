# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The logs of what the learner had translated, and of what they asked
about it afterwards.

Every translation is logged as it is given, without asking a model: what was
selected, the sentence it was in and what it was translated as. Once a chat
about a translation is over, a model reads it and writes a log of each
matter that was discussed in it, such as what a word means there or why it
stands where it does, in a point or two, and those are kept beside the log of
the translation, which they name. Like the logs of the exercises,
they are for the models that profile the learner later, not for the
learner, so they state what happened plainly.
"""

from __future__ import annotations

import re
from typing import Any

from logs import Asker, LogError, read_json
from prompts import PROMPTS
from translating import Passage

# how long the subject of a log is at most, in characters
MAX_SUBJECT = 120
# how much of the sentence a translation was in is kept, in characters
MAX_SENTENCE = 400
# how many matters a chat is written up as at most, and in how many points each
MAX_MATTERS = 6
MAX_POINTS = 2
# how much of the chat the model is shown, in characters
MAX_CHAT = 20_000
# what ends a sentence, with the space after it
_SENTENCE_END = re.compile(r"[.!?…]['\")\]»”’]*(\s+|$)")


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _cut(text: str, most: int) -> str:
    return text if len(text) <= most else text[: most - 1].rstrip() + "…"


def sentence_of(passage: Passage) -> str:
    """The sentence the selection of `passage` is in, as far as the passage
    has it, with the selection between [[ and ]]."""
    before = passage.before
    # The passage starts at a sentence and goes on to the end of the one the
    # selection is in: what is before it in its sentence is what is after
    # the last end of a sentence before it.
    ends = [found.end() for found in _SENTENCE_END.finditer(before)]
    start = ends[-1] if ends else 0
    lines = before[start:].rsplit("\n", 1)
    return _text(f"{lines[-1]}[[{passage.selection}]]{passage.after}")


def translation_log(passage: Passage, translation: str) -> tuple[str, str]:
    """The subject and the content of the log of a translation."""
    selection = _text(passage.selection)
    sentence = _cut(sentence_of(passage), MAX_SENTENCE)
    content = PROMPTS(
        "lookups.translation.asked", selection=selection, sentence=sentence
    )
    content += "\n" + PROMPTS(
        "lookups.translation.translated", translation=_text(translation)
    )
    return _cut(selection, MAX_SUBJECT), content


def describe_chat(messages: list[dict[str, str]]) -> str:
    """The chat as the model is shown it."""
    names = PROMPTS.table("lookups.names")
    chat = "\n\n".join(
        f"{names.get(message['role'], message['role'])}: {message['content'].strip()}"
        for message in messages
    )
    if len(chat) > MAX_CHAT:
        chat = chat[:MAX_CHAT] + "\n" + PROMPTS("cut")
    return chat


def asked_anything(messages: list[dict[str, str]]) -> bool:
    """Whether the learner asked anything there is to write logs of."""
    return any(
        message["role"] == "user" and message["content"].strip() for message in messages
    )


def write_question_logs(
    ask: Asker,
    passage: Passage,
    translation: str,
    messages: list[dict[str, str]],
    language: str,
    into: str,
) -> tuple[list[tuple[str, str]], Any]:
    """The subject and the content of the log of each matter discussed in a
    chat about a translation, with what asking for them used. Raises
    LogError and TranslationError."""
    prompt = PROMPTS(
        "lookups.writing",
        language=language,
        into=into,
        passage=passage.marked(),
        translation=translation,
        chat=describe_chat(messages),
        matters=MAX_MATTERS,
    )
    said, used = ask([{"role": "user", "content": prompt}])
    return read_question_logs(said), used


def read_question_logs(said: str) -> list[tuple[str, str]]:
    """The logs as the model wrote them, in JSON. Raises LogError."""
    found = read_json(said)
    listed = found.get("logs") if isinstance(found, dict) else None
    if not isinstance(listed, list):
        raise LogError("the model did not write the logs as it was asked")
    logs = []
    for each in listed[:MAX_MATTERS]:
        if not isinstance(each, dict):
            continue
        points = each.get("points")
        lines = [
            _text(point)
            for point in (points if isinstance(points, list) else [points])
            if _text(point)
        ][:MAX_POINTS]
        subject = _cut(_text(each.get("subject")), MAX_SUBJECT)
        if subject and lines:
            logs.append((subject, "\n".join(lines)))
    return logs
