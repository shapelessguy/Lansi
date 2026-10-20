# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What the backend of an exercise is written with.

An exercise is a directory of its own here, with:

    manifest.json   {"title": ..., "description": ..., "options": ...}
    backend.py      what makes the exercise and checks what is answered
    prompts.toml    what the backend tells the models, as `Prompts` reads
                    it and checker/prompts.py describes, which
                    `prompts_beside` gives the backend
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

An option may also be `{"label": "Text", "texts": true}`: one of the
learner's own texts that are not corrected yet, such as their homework, by
its id, which the app fills in as its choices. The exercise is told the
text it chose under `texts` in the context, by the name of the option, and
may say what came of it in its `results` under `texts`, by the same name:
`{"content": ..., "correction": ...}`, the text as it was when it was
corrected, which the app keeps and locks, and a copy of it with the
corrections and their comments worked in, in Markdown, which the app shows
in place of the text from then on.

The app remembers what the learner chose of each, for the next time.

An exercise whose manifest has `"once": true` is done once, with no time
limit, such as one that corrects a text: how many instances it has, and how
long it may take, are not for the learner to choose.

An exercise whose manifest has `"lesson": false` practises no lesson, such
as one that corrects a text: a session of such exercises alone has none,
and its `lesson` in the context is empty.

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
`results` the exercise keeps for itself, with the `scores` it came to.

The context is the same for every call:

    {"language": "German", "into": "English", "level": "A1",
     "letters": {"ß": "ss", ...}, "marks": "umlauts",
     "lesson": {"id": ..., "title": ..., "level": ..., "more_info": ...,
                "points": [{"id": ..., "role": "new", "title": ...,
                            "statement": ..., "when": ..., ...}]},
     "topics": [{"title": ..., "description": ...}],
     "mix_topics": False,
     "words": {"mode": "only" | "prefer", "lemmas": [...]} or None,
     "instances": 10,
     "options": {"then": "questions"},
     "guidance": "...",
     "minutes": 0,
     "exam": "",
     "texts": {"text": {"id": ..., "title": ..., "content": ...}}}

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

`minutes` is how long the learner has for the exercise, or 0 for as long as
they like. The app keeps the time: once it is up, the exercise is finished,
and nothing the learner sends after is taken. It is told so that it can
say so, and is best not made shorter or longer by the exercise.

`exam` is, when the exercise is a part of an evaluation, a mock exam of a
level, what the exam says that part is: its instructions to the learner,
what its texts and tasks are like, and an example of one, which the
exercise is to follow, as `describe_exam` tells a model, in place of the
lesson. The `lesson` is then made of the points of the level of the exam.
It is empty in practice.

`scores`, which `finish` may return, say what the learner can do as far
as the exercise shows it, each a number from 0 to 100, by the names of
`SCORES`, those it does not show left out. The app keeps them, and an
evaluation counts the scores of its parts by them, as an exam is marked.
`score_of` makes the share of the grades that were right into a score, and
`criteria_scores` the ratings of what was written by `CRITERIA`.

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

`letters` and `marks` are what the language does its own way with its
letters, as checker/languages/ says it: the letters that may be written
otherwise by someone who cannot type them, each with how, and what the
marks on its letters are called. `loose` compares answers by them, so that
one that differs only in capitals, marks or such letters is almost right
rather than wrong, and an exercise names the marks so where it says why.

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
from pathlib import Path
from string import Template
from typing import Any, Protocol, TextIO

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

RESULTS = ("right", "wrong", "partial")
# What an exercise may score, from 0 to 100, as an exam marks it: the
# skills, by how much of what was asked of each was done right, and the
# ratings of what the learner wrote or said, by `CRITERIA`.
SCORES = {
    "reading": "how many of the questions on texts read were answered right",
    "listening": "how many of the questions on texts heard were answered right",
    "writing": "how well the writing tasks were done",
    "speaking": "how well the speaking tasks were done",
    "task": "every point dealt with, as long as asked",
    "coherence": "one text joined up, for its reader and its register",
    "vocabulary": "the words of the level, used rightly and with range",
    "structures": "the grammar of the level, used rightly",
    "pronunciation": "what was said can be understood",
}
# How what the learner writes or says is rated, from 0 to 4, as the
# examiners of a language exam rate it, by the level of the exam. What a
# model is told of each is `kit.criteria` of the prompts.
CRITERIA = ("task", "coherence", "vocabulary", "structures", "pronunciation")
# how much of a reply that could not be read is told with why
MAX_SHOWN_REPLY = 160


class PromptError(Exception):
    """A prompt is not in its file, or cannot be filled in."""


class Prompts:
    """The prompts an exercise keeps in the `prompts.toml` of its directory,
    which `prompts_beside` reads, filled in by name: a prompt is a string of
    the file, found by its dotted name, and a table of strings is the
    variants of one. A prompt is filled in as checker/prompts.py describes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._table: dict[str, Any] | None = None

    def table(self, name: str = "") -> dict[str, Any]:
        """The table of that name, of prompts or of tables of them; the whole
        file without a name."""
        found = self._find(name) if name else self._read()
        if not isinstance(found, dict):
            raise PromptError(f"{name} of {self.path} is not a table")
        return found

    def text(self, name: str) -> str:
        """The prompt of that name as it is written, not filled in."""
        found = self._find(name)
        if not isinstance(found, str):
            raise PromptError(f"{name} of {self.path} is not a prompt")
        return found

    def __call__(self, name: str, /, **values: object) -> str:
        """The prompt of that name filled in with `values`: one it uses that
        is not given is an error, one it does not use is left out."""
        return _fill(self.text(name), f"{name} of {self.path}", values)

    def _read(self) -> dict[str, Any]:
        if self._table is None:
            with self.path.open("rb") as file:
                self._table = tomllib.load(file)
        return self._table

    def _find(self, name: str) -> Any:
        found: Any = self._read()
        for part in name.split("."):
            if not isinstance(found, dict) or part not in found:
                raise PromptError(f"{self.path} has no prompt {name}")
            found = found[part]
        return found


class SharedPrompts:
    """The prompts every exercise uses, kept in checker/prompts/kit/ and
    read as checker/prompts.py reads them: an exercise is run with nothing
    of the server's, so the kit reads them itself. `kit.topics.one` is the
    variant `one` of checker/prompts/kit/topics.md."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._files: dict[Path, dict[str, str]] = {}

    def table(self, name: str) -> dict[str, str]:
        """The variants of the prompt of that name, by their names."""
        variants = self._file(self.directory.joinpath(*name.split(".")))
        if variants is None or "" in variants:
            raise PromptError(f"there are no variants of a prompt {name}")
        return variants

    def text(self, name: str) -> str:
        """The prompt of that name as it is written, not filled in."""
        parts = name.split(".")
        whole = self._file(self.directory.joinpath(*parts))
        if whole is not None and "" in whole:
            return whole[""]
        variants = self._file(self.directory.joinpath(*parts[:-1]))
        if variants is not None and parts[-1] in variants:
            return variants[parts[-1]]
        raise PromptError(f"there is no prompt {name} in {self.directory}")

    def __call__(self, name: str, /, **values: object) -> str:
        """The prompt of that name filled in with `values`."""
        return _fill(self.text(name), name, values)

    def _file(self, path: Path) -> dict[str, str] | None:
        path = path.with_name(path.name + ".md")
        if path not in self._files:
            if not path.is_file():
                return None
            text = path.read_text(encoding="utf-8")
            headings = list(_HEADING.finditer(text))
            self._files[path] = {
                heading.group(1) or "": text[
                    heading.end() : headings[number + 1].start()
                    if number + 1 < len(headings)
                    else len(text)
                ].strip("\r\n")
                for number, heading in enumerate(headings)
            }
        return self._files[path]


# the heading a shared prompt, or a variant of one, starts under
_HEADING = re.compile(r"^## Prompt(?:: (\S+))?[ \t]*$", re.MULTILINE)


def _fill(text: str, name: str, values: dict[str, object]) -> str:
    """`text` with each of its variables replaced by its value: one it uses
    that is not given is an error, one it does not use is left out."""
    missing = variables_of(text) - set(values)
    if missing:
        listed = ", ".join(f"${each}" for each in sorted(missing))
        raise PromptError(f"{name} uses {listed}, which the code does not give")
    try:
        return Template(text).substitute(values)
    except ValueError as error:
        raise PromptError(f"{name}: {error}") from None


def variables_of(text: str) -> set[str]:
    """The names of the variables a prompt uses. Raises PromptError if it
    has a $ that is neither a variable nor $$."""
    names = set()
    for match in Template.pattern.finditer(text):
        if match.group("invalid") is not None:
            raise PromptError(
                f"a $ that starts no variable, at {text[match.start() : match.start() + 20]!r}"
            )
        name = match.group("named") or match.group("braced")
        if name:
            names.add(name)
    return names


def prompts_beside(file: str) -> Prompts:
    """The prompts of the exercise whose backend is `file`."""
    return Prompts(Path(file).resolve().with_name("prompts.toml"))


# the prompts every exercise uses, those of kit/ in the server's
PROMPTS = SharedPrompts(Path(__file__).resolve().parent.parent / "prompts")


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
    scores: dict[str, float] | None = None


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


def score_of(results: list[str]) -> float | None:
    """The score of a number of answers by their results, an answer that
    was partly right counting half, or None if there were none."""
    if not results:
        return None
    right = sum(
        1.0 if each == "right" else 0.5 if each == "partial" else 0.0
        for each in results
    )
    return round(100 * right / len(results), 1)


def describe_criteria(names: list[str]) -> str:
    """How a model is told to rate by the `CRITERIA` named, one to a line."""
    return "\n".join(f'- "{name}": {PROMPTS(f"kit.criteria.{name}")}' for name in names)


def read_ratings(reply: Any, names: list[str]) -> dict[str, int]:
    """The rating of each criterion named that a model gave, from 0 to 4.
    Raises ModelError if one is missing."""
    found = reply if isinstance(reply, dict) else {}
    ratings = {}
    for name in names:
        value = found.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ModelError(f"the model did not rate {name}")
        ratings[name] = max(0, min(4, round(value)))
    return ratings


def result_of_ratings(ratings: dict[str, int]) -> str:
    """The result of a rated answer: right if it is rated 3 or more on
    average, partial if 1.5 or more, and else wrong."""
    mean = sum(ratings.values()) / len(ratings) if ratings else 0
    return "right" if mean >= 3 else "partial" if mean >= 1.5 else "wrong"


def criteria_scores(ratings: list[dict[str, int]]) -> dict[str, float]:
    """The score of each criterion that answers were rated by, from their
    ratings from 0 to 4, and that of them all as `all`."""
    scores: dict[str, float] = {}
    for name in CRITERIA:
        rated = [each[name] for each in ratings if name in each]
        if rated:
            scores[name] = round(100 * sum(rated) / (4 * len(rated)), 1)
    every = [value for each in ratings for value in each.values()]
    if every:
        scores["all"] = round(100 * sum(every) / (4 * len(every)), 1)
    return scores


def describe_exam(context: dict[str, Any]) -> str:
    """What an exam says the part the exercise is in is like, as a model
    is told to follow it, on lines of its own; nothing in practice."""
    exam = str(context.get("exam") or "").strip()
    if not exam:
        return ""
    return f"\n{PROMPTS('kit.exam', exam=exam)}\n"


def letters_of(context: dict[str, Any]) -> dict[str, str]:
    """The `letters` of the context: those of the language that may be
    written otherwise, each with how."""
    letters = context.get("letters")
    if not isinstance(letters, dict):
        return {}
    return {
        str(letter): str(written)
        for letter, written in letters.items()
        if str(letter) and isinstance(written, str)
    }


def marks_of(context: dict[str, Any]) -> str:
    """What the marks on the letters of the language are called."""
    return str(context.get("marks") or "accents")


def loose(text: str, letters: dict[str, str] | None = None) -> str:
    """Text as it is when capitals and the marks on letters are not told
    apart, nor the `letters` of the language, of `letters_of`, from how they
    are written otherwise."""
    text = text.casefold()
    for letter, written in (letters or {}).items():
        text = text.replace(letter.casefold(), written.casefold())
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
    lines = [
        PROMPTS("kit.lesson.heading", title=lesson["title"], level=lesson["level"])
    ]
    for point in lesson["points"]:
        if point["role"] in roles:
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
    told = PROMPTS("kit.plan.repeated" if len(parts) < count else "kit.plan.once")
    return f"{told}\n" + "\n".join(lines) + "\n"


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
    sentences = PROMPTS.table("kit.level_sentences").get(level.strip().upper())
    if sentences:
        return PROMPTS("kit.level.with_sentences", level=level, sentences=sentences)
    return PROMPTS("kit.level.plain", level=level)


def describe_made(sentences: list[str]) -> str:
    """The sentences made before in the exercise, as a model is told them
    so as to make others, on lines of their own; nothing if there are none."""
    if not sentences:
        return ""
    listed = "\n".join(f"- {sentence}" for sentence in sentences)
    return f"\n{PROMPTS('kit.made', listed=listed)}\n"


def _topic(topic: dict[str, Any]) -> str:
    if topic.get("description"):
        return PROMPTS(
            "kit.topics.described",
            title=topic["title"],
            description=topic["description"],
        )
    return str(topic["title"])


def describe_topics(context: dict[str, Any]) -> str:
    """The topics, as a model is told them, or that there are none."""
    topics = context.get("topics") or []
    if not topics:
        return PROMPTS("kit.topics.none")
    if len(topics) == 1:
        return PROMPTS("kit.topics.one", topic=_topic(topics[0]))
    listed = "; ".join(_topic(topic) for topic in topics)
    if context.get("mix_topics"):
        return PROMPTS("kit.topics.mixed", topics=listed)
    return PROMPTS("kit.topics.several", topics=listed)


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
    name = "kit.words.only" if words["mode"] == "only" else "kit.words.prefer"
    return PROMPTS(name, language=context["language"], lemmas=lemmas)


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
                "scores": step.scores,
            }
        }
    except ModelError as error:
        reply = {"error": str(error)}
    # in ASCII, which no pipe can garble
    out.write(json.dumps(reply) + "\n")
    out.flush()
