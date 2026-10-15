# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What the backend of an exercise is written with.

An exercise is a directory of its own here, with:

    manifest.json   {"title": ..., "description": ..., "options": ...}
    backend.py      what makes the exercise and checks what is answered
    ui/index.js     what the learner sees, a module the app mounts, as
                    kit.js describes, with ui/style.css if it has one

The `options` of a manifest, if it has any, are the settings of the
exercise the learner may change, besides how many times it is done, by
their names, each with a label to show. One is a choice among a few, with
the choices by their values, the first of them the one taken unless another
is chosen; or a whole number between a `min` and a `max`, the `default`
taken unless another is chosen:

    "options": {"then": {"label": "Then",
                         "choices": {"questions": "Answer questions",
                                     "retell": "Retell it"}},
                "questions": {"label": "Questions", "min": 1, "max": 8,
                              "default": 3}}

The app remembers what the learner chose of each, for the next time.

An exercise whose manifest has `"theory": true` teaches rather than asks:
it is listed first and done first in a session, is not done a number of
times, and is graded on nothing.

The backend is three functions, given to `serve`:

    start(context, model)                  -> Step
    act(context, state, message, model)    -> Step
    finish(context, state, model)          -> Step

`start` makes the exercise, `act` takes what the interface sent, such as an
answer, and `finish` is called once the learner is done or leaves, however
far they got. Each returns a Step: the `state` to be handed back with the
next call, what the interface is to `show`, how what the learner answered
was `graded`, what was `written` in the step, and, from `finish`, the
`results` the exercise keeps for itself.

The context is the same for every call:

    {"language": "German", "into": "English", "level": "A1",
     "lesson": {"id": ..., "title": ..., "level": ..., "more_info": ...,
                "points": [{"id": ..., "role": "new", "title": ...,
                            "statement": ..., "when": ..., ...}]},
     "topics": [{"title": ..., "description": ...}],
     "mix_topics": False,
     "words": {"mode": "only" | "prefer", "lemmas": [...]} or None,
     "instances": 10,
     "options": {"then": "questions"},
     "guidance": "..."}

A session of no lesson reviews the lessons practised last, and its
`lesson` is made of them: its id is empty, it has every point of them once,
each with the role "review" and the title of the `lesson` it is from, and
it has no `more_info`.

What each sentence, or whatever an exercise makes, is centred on is best
not left to the model: `focuses` are the parts of the lesson to go through
in turn, and `describe_plan` tells a model which of them each thing it
makes is to practise.

`topics` are those the session is about: one, or several to be brought
together if `mix_topics`. `words` are words of the learner's vocabulary,
those nearest the topics first, which the sentences are to be made of
("only") or are to lean on ("prefer").

`guidance` is text the app gives the exercise when the session starts, for
the models it asks to heed besides the lesson, the topics and the words,
such as what the exercise was answered with in the sessions before. It may
come from anything in the app, and may be empty. Every exercise is to put
it into what it asks the models that make it, as `describe_guidance` does.

`options` has a value for each option of the manifest, as the learner
chose it, which `option` gives.

What is `written` is `{"user": [...], "assistant": [...]}`: the texts in the
language learned that the learner wrote in the step, such as their answers
as they gave them, and those the models wrote that the learner was shown,
such as the sentences of the exercise, its story or the corrections. Each
text is told once, in the step it was written or shown in, whole sentences
where there are any. Once the exercise is over, the words of all of them
are taken into the learner's vocabulary and counted as used by the learner
or seen, as the words of the chats are; a word that is no word, such as one
misspelt, is left out there.

`into` is the language the learner reads explanations in. A grade is a
`{"result": "right" | "wrong" | "partial", "task": ..., "answer": ...,
"correction": ..., "note": ...}`, one for each instance the learner did.
The `task` is what the exercise gave the learner, written by a model, such
as a sentence with its gaps, a sentence to translate or a question; the
`answer` is only what the learner wrote themselves, such as what they put
into the gaps, and never the task with it: the log is written from the
grades, and must not take what a model wrote for the learner's. An
instance made of several answers, such as a few sentences, is graded once,
as `grade_of` does. The grades are kept as soon as a step returns them, so an exercise
left halfway still counts. Once the exercise is over, the app has a model
write its log from them and from what was written: a short account, for
the app rather than the learner, of what worked and what did not.

`level` is the learner's, and may be empty, when the level of the lesson is
taken: `describe_level` tells a model how hard what it writes is to be.

Each call is made in a process of its own, which is given no key and keeps
nothing: whatever is needed for the next call goes into the state. A
language model is asked through the server, with `model.ask`, a model that
sees pictures well with `model.look`, and a picture drawn by an image model
with `model.draw`. A message may show the model a picture, with a content of
parts:

    [{"type": "text", "text": ...},
     {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}]
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, TextIO

RESULTS = ("right", "wrong", "partial")
# how much of a reply that could not be read is told with why
MAX_SHOWN_REPLY = 160
# What the sentences a learner reads and writes are like at each level.
LEVEL_SENTENCES = {
    "A1": "very short, simple main clauses of about 4 to 8 words",
    "A2": "short sentences of about 6 to 12 words: main clauses, joined at most"
    " by simple conjunctions such as and, but or because",
    "B1": "sentences of about 8 to 15 words, with a subordinate clause where one fits",
    "B2": "sentences of about 10 to 20 words, with subordinate and relative clauses",
    "C1": "sentences of natural length, up to about 25 words, with complex structures",
    "C2": "sentences as a native speaker writes them, of any length and structure",
}


class ModelError(Exception):
    """The model could not be asked, or gave no answer that could be used."""


class Model(Protocol):
    def ask(self, messages: list[dict[str, Any]]) -> str:
        """What the model replies to `messages`, each a `{"role": ...,
        "content": ...}`. Raises ModelError."""
        ...

    def look(self, messages: list[dict[str, Any]]) -> str:
        """As `ask`, of the model the learner chose to look at pictures,
        which is the same one if they chose none. Raises ModelError."""
        ...

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        """The picture an image model draws for `prompt`, as a data URL of
        a JPEG. `aspect_ratio` is one such as "4:3". Raises ModelError."""
        ...


@dataclass
class Step:
    state: Any = None
    show: Any = None
    graded: list[dict[str, str]] = field(default_factory=list)
    results: Any = None
    written: dict[str, list[str]] = field(default_factory=dict)


def written(
    user: list[str] | None = None, assistant: list[str] | None = None
) -> dict[str, list[str]]:
    """What was written in a step: by the learner, and by the models."""
    return {"user": list(user or []), "assistant": list(assistant or [])}


def grade(
    result: str, answer: str, correction: str = "", note: str = "", task: str = ""
) -> dict[str, str]:
    """The grade of one instance the learner did: `answer` is what they
    wrote, and `task` what the exercise gave them to answer."""
    assert result in RESULTS
    return {
        "result": result,
        "task": task,
        "answer": answer,
        "correction": correction,
        "note": note,
    }


def numbered(texts: list[str]) -> str:
    """Texts one to a line, each with its number."""
    return "\n".join(f"{number}. {text}" for number, text in enumerate(texts, 1))


def overall(results: list[str]) -> str:
    """The result of an instance of several answers: right if every one is,
    wrong if every one is, and partial otherwise."""
    if all(result == "right" for result in results):
        return "right"
    if all(result == "wrong" for result in results):
        return "wrong"
    return "partial"


def grade_of(grades: list[dict[str, str]]) -> dict[str, str]:
    """The one grade of an instance of several answers, each graded as
    `grade` grades one: its result `overall`, and the tasks, the answers
    and the correction of each, one to a line by their numbers, where each
    that was right is said to be, and the notes by the number of the
    answer."""
    result = overall([each["result"] for each in grades])
    corrected = [
        "(right)" if each["result"] == "right" else each["correction"]
        for each in grades
    ]
    notes = [
        f"{number}. {each['note']}"
        for number, each in enumerate(grades, start=1)
        if each["note"]
    ]
    return grade(
        result,
        numbered([each["answer"] or "(nothing)" for each in grades]),
        "" if result == "right" else numbered(corrected),
        "; ".join(notes),
        numbered([each["task"] for each in grades])
        if any(each["task"] for each in grades)
        else "",
    )


def loose(text: str) -> str:
    """Text as it is when capitals and umlauts are not told apart."""
    text = text.casefold().replace("ß", "ss")
    for umlaut, written in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        text = text.replace(umlaut, written)
    folded = unicodedata.normalize("NFKD", text)
    return "".join(char for char in folded if not unicodedata.combining(char))


def ask_json(model: Model, messages: list[dict[str, Any]], look: bool = False) -> Any:
    """What the model replies, read as JSON, which it may have put in a
    fenced block or among words of its own; asked with `model.look` if
    `look`. Raises ModelError."""
    said = (model.look if look else model.ask)(messages).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", said, re.DOTALL)
    reply = fenced.group(1).strip() if fenced else said
    try:
        return json.loads(reply)
    except ValueError:
        pass
    # the first object or list in what it said that reads as a whole
    decoder = json.JSONDecoder()
    for start, char in enumerate(reply):
        if char in "{[":
            try:
                return decoder.raw_decode(reply, start)[0]
            except ValueError:
                continue
    shown = " ".join(said.split())
    shown = shown[:MAX_SHOWN_REPLY] + ("…" if len(shown) > MAX_SHOWN_REPLY else "")
    raise ModelError(f"the model did not reply with JSON: {shown or 'nothing'}")


def describe_lesson(
    context: dict[str, Any], roles: tuple[str, ...] = ("new", "review")
) -> str:
    """The points of the lesson that have one of `roles`, as a model is told
    them: the rule, and when it applies. The pages of theory in `more_info`
    are left out: they are long, and the points say what is practised."""
    lesson = context["lesson"]
    lines = [f"Lesson: {lesson['title']} (level {lesson['level']})"]
    for point in lesson["points"]:
        if point["role"] in roles:
            lines.append(
                f"- {point['title']} ({point['role']}): {point['statement']}"
                f" Applies when: {point['when']}."
            )
    return "\n".join(lines)


def focuses(context: dict[str, Any]) -> list[str]:
    """The parts of the lesson to centre what is made on, in turn: each
    lesson of a review, with its points, or else each point that is taught
    or reviewed. Empty for a lesson without such points."""
    points = [
        point
        for point in context["lesson"]["points"]
        if point["role"] in ("new", "review")
    ]
    if any(point.get("lesson") for point in points):
        lessons: dict[str, list[str]] = {}
        for point in points:
            lessons.setdefault(point.get("lesson") or "", []).append(point["title"])
        return [
            f"{lesson} ({'; '.join(titles)})" if lesson else "; ".join(titles)
            for lesson, titles in lessons.items()
        ]
    return [point["title"] for point in points]


def describe_plan(context: dict[str, Any], count: int, start: int = 0) -> str:
    """What each of `count` things a model makes is to practise, as it is
    told: the `focuses` in turn, from the one `start` things made before
    reached, over again when there are fewer than `count`. Nothing when
    the lesson has none, which leaves the model free within the lesson."""
    parts = focuses(context)
    if not parts:
        return ""
    lines = [
        f"{number}. {parts[(start + number - 1) % len(parts)]}"
        for number in range(1, count + 1)
    ]
    again = (
        " Where the same comes more than once, practise another side of it."
        if len(parts) < count
        else ""
    )
    return (
        f"Make them in this order, each centred on the rule named for it.{again}\n"
        + "\n".join(lines)
        + "\n"
    )


def option(context: dict[str, Any], name: str, default: Any) -> Any:
    """The value the learner chose of an option of the manifest, or
    `default` if they were given none, as in a session started before it
    was there."""
    return (context.get("options") or {}).get(name, default)


def level_of(context: dict[str, Any]) -> str:
    """The learner's level, or that of the lesson if they gave none."""
    return str(context.get("level") or context["lesson"]["level"])


def describe_level(context: dict[str, Any]) -> str:
    """How hard what a model writes is to be, as it is told: words the
    learner knows, and sentences as long and as built as their level
    reads, unless the rules of the lesson need more."""
    level = level_of(context)
    told = f"The learner is at level {level}: use only words a learner at {level} knows"
    sentences = LEVEL_SENTENCES.get(level.strip().upper())
    if sentences:
        told += f", and write {sentences}"
    return f"{told}. Where the rules below need more than that, the rules come first."


def describe_made(sentences: list[str]) -> str:
    """The sentences made before in the exercise, as a model is told them
    so as to make others, on lines of their own; nothing if there are none."""
    if not sentences:
        return ""
    listed = "\n".join(f"- {sentence}" for sentence in sentences)
    return (
        "\nSentences made already in this exercise. Write other ones, with"
        f" other words, things and structures:\n{listed}\n"
    )


def _topic(topic: dict[str, Any]) -> str:
    if topic.get("description"):
        return f"{topic['title']} ({topic['description']})"
    return str(topic["title"])


def describe_topics(context: dict[str, Any]) -> str:
    """The topics, as a model is told them, or that there are none."""
    topics = context.get("topics") or []
    if not topics:
        return "Topic: everyday life."
    if len(topics) == 1:
        return f"Topic: {_topic(topics[0])}."
    listed = "; ".join(_topic(topic) for topic in topics)
    if context.get("mix_topics"):
        return (
            f"Topics: {listed}. Mix them: bring them together in the same"
            " sentences where it makes sense, so that every topic comes up."
        )
    return f"Topics: {listed}."


def describe_guidance(context: dict[str, Any]) -> str:
    """What the app said the models are to heed, as a model is told it, on
    lines of its own; nothing if it said nothing."""
    guidance = str(context.get("guidance") or "").strip()
    return f"\n{guidance}\n" if guidance else ""


def describe_words(context: dict[str, Any]) -> str:
    """The words of the learner's vocabulary the sentences are to be made
    of, or to lean on, as a model is told them; nothing if there are none."""
    words = context.get("words")
    if not words or not words.get("lemmas"):
        return ""
    lemmas = ", ".join(words["lemmas"])
    language = context["language"]
    if words["mode"] == "only":
        return (
            f"Words the learner knows, those that fit the topic first. Write the"
            f" {language} sentences with these words alone, in any of their forms,"
            " besides articles, pronouns, prepositions, conjunctions, numbers,"
            " auxiliary and modal verbs, and the words the rules above need:\n"
            f"{lemmas}"
        )
    return (
        f"Words the learner knows, those that fit the topic first. Use these in"
        f" the {language} sentences wherever they fit, in any of their forms;"
        " other words are fine where none of these does, as long as a learner"
        f" at the level knows them:\n{lemmas}"
    )


class _StdioModel:
    """Asks the server, which asks the model, over the pipes the process was
    started with."""

    def __init__(self, into: TextIO, out: TextIO) -> None:
        self._into = into
        self._out = out

    def ask(self, messages: list[dict[str, Any]]) -> str:
        return self._request({"ask": {"messages": messages}})

    def look(self, messages: list[dict[str, Any]]) -> str:
        return self._request({"look": {"messages": messages}})

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        return self._request({"draw": {"prompt": prompt, "aspect_ratio": aspect_ratio}})

    def _request(self, request: dict[str, Any]) -> str:
        self._out.write(json.dumps(request) + "\n")
        self._out.flush()
        answer = json.loads(self._into.readline() or "{}")
        if "answer" not in answer:
            raise ModelError(answer.get("error") or "the server gave no answer")
        return str(answer["answer"])


Start = Callable[[dict[str, Any], Model], Step]
Act = Callable[[dict[str, Any], Any, Any, Model], Step]
Finish = Callable[[dict[str, Any], Any, Model], Step]


def serve(start: Start, act: Act, finish: Finish) -> None:
    """Make the one call the server sent, and reply with what came of it."""
    out = sys.stdout
    # what the backend prints is not taken for a reply
    sys.stdout = sys.stderr
    model = _StdioModel(sys.stdin, out)
    try:
        request = json.loads(sys.stdin.readline())
        context = request["context"]
        if request["op"] == "start":
            step = start(context, model)
        elif request["op"] == "act":
            step = act(context, request["state"], request["message"], model)
        else:
            step = finish(context, request["state"], model)
        reply: dict[str, Any] = {
            "reply": {
                "state": step.state,
                "show": step.show,
                "graded": step.graded,
                "results": step.results,
                "written": step.written,
            }
        }
    except ModelError as error:
        reply = {"error": str(error)}
    # in ASCII, which no pipe can garble
    out.write(json.dumps(reply) + "\n")
    out.flush()
