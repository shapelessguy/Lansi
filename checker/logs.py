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

# Asks a language model the messages given, and replies with what it said and
# what asking used. Raises TranslationError.
Asker = Callable[[list[dict[str, Any]]], tuple[str, Profile]]

# How many lines the account may have, by how many words the learner wrote
# at most: the last is for any more.
LINES_BY_WORDS = ((80, 4), (400, 8), (None, 14))
# how many examples there may be of what worked, and of what did not
MAX_WORKED = 2
MAX_FAILED = 3
# how much of what was written the model is shown, in characters
MAX_WRITTEN = 20_000

PROMPT = """\
You write the log of an exercise that someone learning {language} has just \
done. The log is not for the learner: it is kept for the models that will \
later work out what the learner can and cannot do yet, so it must be exact \
and plain. Do not praise, encourage or soften anything, and do not excuse \
mistakes. State facts that what the learner wrote shows; draw no conclusion \
about the learner beyond them. Where several answers show the same mistake, \
say how many. If the learner wrote too little to judge something, say so \
rather than guess.

What the learner did is told in two parts that must never be mixed. \
"Given by the exercise" was written by a model, not by the learner: a \
sentence with gaps, a sentence to translate, a question. The learner gets no \
credit and no blame for any of it, and it is never quoted as theirs; it is \
there only so that you know what was asked. "Written by the learner" is the \
only thing the learner did, and the only thing you judge. In a sentence with \
gaps (___), the learner wrote only what went into the gaps, in the order of \
the gaps: a rule counts as used by the learner only if what they wrote into \
a gap shows it.

The grades below were given by another model while the exercise ran. Check \
each against what the learner wrote: where a grade or a correction is wrong, \
go by what the learner actually wrote, and say the grade was wrong.

The exercise:
{task}

What the learner did, in the order they did it:
{record}

Write, in English:
- "summary": at most {lines} short lines, in this order: how much of the \
exercise was done; what the learner got right, as the rules and forms they \
used correctly; what they got wrong, as the rules and forms they used \
wrongly, the words they did not know and the kinds of mistakes they made. \
Name the rules of the lesson where they apply. Leave out what was not \
tested.
- "worked": at most {worked} examples of what the learner wrote that was \
right, with the rule or form it shows. None if nothing was right.
- "failed": at most {failed} examples of what the learner wrote that was \
wrong, with the correction and what was wrong. None if nothing was wrong.
In each example, "text" is only the learner's own words, quoted exactly as \
they wrote them, such as what they put into a gap, and never words the \
exercise gave; "given" is, if it helps, the part of the exercise they \
answered, such as the sentence with its gaps.

Reply with JSON only:
{{"summary": ["...", "..."], \
"worked": [{{"text": "...", "given": "...", "why": "..."}}], \
"failed": [{{"text": "...", "given": "...", "correction": "...", \
"why": "..."}}]}}"""


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
        f"{task.title}: {task.description}",
        f"Level: {task.level or lesson.get('level', '')}",
        f"Instances to do: {task.instances}",
    ]
    lines += task.options
    if task.topics:
        lines.append(f"Topics: {'; '.join(task.topics)}")
    lines.append(f"Lesson: {lesson.get('title', '')}")
    for point in lesson.get("points", []):
        if point.get("role") in ("new", "review"):
            lines.append(
                f"- {point['title']} ({point['role']}): {point['statement']}"
                f" Applies when: {point['when']}."
            )
    return "\n".join(lines)


def describe_record(grades: list[dict[str, str]], written: dict[str, list[str]]) -> str:
    """What the model is told the learner did: each answer with its grade,
    and else what was written, by the learner and by the exercise."""
    lines = []
    for number, grade in enumerate(grades, start=1):
        lines.append(f"Instance {number}, graded {grade['result']}")
        parts = [
            ("Given by the exercise (not the learner's)", grade.get("task", "")),
            ("Written by the learner", grade["answer"] or "(nothing)"),
            ("Correct", grade["correction"]),
            ("Note", grade["note"]),
        ]
        for name, text in parts:
            if text:
                lines.append(f"  {name}:")
                lines += [f"    {line}" for line in text.splitlines()]
    if not grades:
        # such as a conversation, which is not graded answer by answer
        lines += [f"Exercise: {text}" for text in written.get("assistant", [])]
        lines += [f"Learner: {text}" for text in written.get("user", [])]
    record = "\n".join(lines)
    if len(record) > MAX_WRITTEN:
        record = record[:MAX_WRITTEN] + "\n(the rest is left out)"
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
    prompt = PROMPT.format(
        language=task.language,
        task=describe_task(task),
        record=describe_record(grades, written),
        lines=lines_for(grades, written),
        worked=MAX_WORKED,
        failed=MAX_FAILED,
    )
    said, used = ask([{"role": "user", "content": prompt}])
    return format_log(read_log(said)), used


def read_log(said: str) -> dict[str, Any]:
    """The log as the model wrote it, in JSON, which it may have put in a
    fenced block. Raises LogError."""
    fenced = re.search(r"```(?:json)?\s*(.*?)```", said, re.DOTALL)
    reply = (fenced.group(1) if fenced else said).strip()
    start, end = reply.find("{"), reply.rfind("}")
    try:
        found = json.loads(reply[start : end + 1]) if start != -1 else None
    except ValueError:
        found = None
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
