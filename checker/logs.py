# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The log of an exercise of a session: what worked and what did not, with
a few examples of each, written by a model once the exercise is over from
what the learner was asked, how each answer was graded and what was
written. It is for the models that profile the learner later, not for the
learner, so it states what happened, plainly and without sparing them.

How long it may be follows how much the learner wrote: a few lines for an
exercise of gaps, more for one of answers or a retelling, and more again
for a conversation.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from profiling import Profile
from prompts import PROMPTS

# Asks a language model the messages given, and replies with what it said and
# what asking used. Raises TranslationError.
Asker = Callable[[list[dict[str, Any]]], tuple[str, Profile]]

# How many lines the account may have, by how many words the learner wrote
# at most: the last is for any more.
LINES_BY_WORDS = ((80, 7), (400, 11), (None, 16))
# how many examples there may be of what worked, and of what did not
MAX_WORKED = 3
MAX_FAILED = 5
# how much of what was written the model is shown, in characters
MAX_WRITTEN = 20_000


class LogError(Exception):
    """The log could not be written. The message says why."""


@dataclass
class Task:
    """What the learner was asked to do in an exercise."""

    # the exercise, as its manifest describes it
    title: str
    description: str
    language: str
    level: str
    lesson: dict[str, Any]
    topics: list[str]
    # how many instances there were to be
    instances: int
    # the label of each option and of the choice it was given, such as
    # "Then: Retell it"
    options: list[str] = field(default_factory=list)


def describe_task(task: Task) -> str:
    """What the model is told of the exercise."""
    lesson = task.lesson
    lines = [
        PROMPTS("logs.task.heading", title=task.title, description=task.description),
        PROMPTS("logs.task.level", level=task.level or lesson.get("level", "")),
        PROMPTS("logs.task.instances", count=task.instances),
    ]
    lines += task.options
    if task.topics:
        lines.append(PROMPTS("logs.task.topics", topics="; ".join(task.topics)))
    lines.append(PROMPTS("logs.task.lesson", title=lesson.get("title", "")))
    for point in lesson.get("points", []):
        if point.get("role") in ("new", "review"):
            lines.append(
                PROMPTS(
                    "kit.lesson.point",
                    title=point["title"],
                    role=point["role"],
                    statement=point["statement"],
                    when=point["when"],
                )
            )
    return "\n".join(lines)


def describe_record(grades: list[dict[str, str]], written: dict[str, list[str]]) -> str:
    """What the model is told the learner did: each answer with its grade,
    and else what was written, by the learner and by the exercise."""
    lines = []
    for number, grade in enumerate(grades, start=1):
        lines.append(
            PROMPTS("logs.record.instance", number=number, result=grade["result"])
        )
        parts = [
            (PROMPTS("logs.record.given"), grade.get("task", "")),
            (
                PROMPTS("logs.record.written"),
                grade["answer"] or PROMPTS("logs.record.nothing"),
            ),
            (PROMPTS("logs.record.correction"), grade["correction"]),
            (PROMPTS("logs.record.note"), grade["note"]),
        ]
        for name, text in parts:
            if text:
                lines.append(f"  {name}:")
                lines += [f"    {line}" for line in text.splitlines()]
    if not grades:
        # such as a conversation, which is not graded answer by answer
        lines += [
            PROMPTS("logs.record.exercise", text=text)
            for text in written.get("assistant", [])
        ]
        lines += [
            PROMPTS("logs.record.learner", text=text)
            for text in written.get("user", [])
        ]
    record = "\n".join(lines)
    if len(record) > MAX_WRITTEN:
        record = record[:MAX_WRITTEN] + "\n" + PROMPTS("cut")
    return record


def lines_for(grades: list[dict[str, str]], written: dict[str, list[str]]) -> int:
    """How many lines the account may have, for what the learner wrote."""
    texts = [grade["answer"] for grade in grades] or written.get("user", [])
    words = sum(len(text.split()) for text in texts)
    return next(
        lines for most, lines in LINES_BY_WORDS if most is None or words <= most
    )


def has_anything(grades: list[dict[str, str]], written: dict[str, list[str]]) -> bool:
    """Whether the learner did anything there is to write a log of."""
    return bool(grades) or any(text.strip() for text in written.get("user", []))


def write_log(
    ask: Asker,
    task: Task,
    grades: list[dict[str, str]],
    written: dict[str, list[str]],
) -> tuple[str, Profile]:
    """The log of an exercise, with what asking for it used. Raises LogError
    and TranslationError."""
    prompt = PROMPTS(
        "logs.writing",
        language=task.language,
        task=describe_task(task),
        record=describe_record(grades, written),
        lines=lines_for(grades, written),
        worked=MAX_WORKED,
        failed=MAX_FAILED,
    )
    said, used = ask([{"role": "user", "content": prompt}])
    return format_log(read_log(said)), used


def read_json(said: str) -> Any:
    """The object a model wrote in JSON, which it may have put in a fenced
    block, or None if it wrote none."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", said, re.DOTALL)
    reply = (fenced.group(1) if fenced else said).strip()
    start, end = reply.find("{"), reply.rfind("}")
    try:
        return json.loads(reply[start : end + 1]) if start != -1 else None
    except ValueError:
        return None


def read_log(said: str) -> dict[str, Any]:
    """The log as the model wrote it, in JSON. Raises LogError."""
    found = read_json(said)
    if not isinstance(found, dict) or not isinstance(found.get("summary"), list):
        raise LogError("the model did not write the log as it was asked")
    return found


def format_log(found: dict[str, Any]) -> str:
    """The log as it is kept: the account, then the examples."""

    def text(value: object) -> str:
        return " ".join(str(value or "").split())

    def listed(name: str, most: int) -> list[dict[str, Any]]:
        value = found.get(name)
        return [
            each
            for each in (value if isinstance(value, list) else [])
            if isinstance(each, dict) and text(each.get("text"))
        ][:most]

    def example(each: dict[str, Any]) -> str:
        line = f'- "{text(each["text"])}"'
        if text(each.get("given")):
            line += f' (in: "{text(each["given"])}")'
        if text(each.get("correction")):
            line += f' → "{text(each["correction"])}"'
        if text(each.get("why")):
            line += f": {text(each['why'])}"
        return line

    lines = [text(line) for line in found["summary"] if text(line)]
    worked, failed = listed("worked", MAX_WORKED), listed("failed", MAX_FAILED)
    if worked:
        lines += ["Worked:", *map(example, worked)]
    if failed:
        lines += ["Did not work:", *map(example, failed)]
    if not lines:
        raise LogError("the model wrote an empty log")
    return "\n".join(lines)
