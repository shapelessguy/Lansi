# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Runs the exercises of a session of practice.

An exercise is a directory in `exercises/`, written as `exercises/kit.py`
describes. Its backend is run for each step in a Python process of its own,
which is given the step on its input and replies on its output. It is given
no key, and the environment of the server is not passed on to it: when it
wants a language model asked, a picture looked at or a picture drawn, it
asks the server, which asks the model for it. This keeps an exercise from mixing with the server and from spending
what it was not given, but is no sandbox against an exercise written to do
harm: the exercises are trusted to be the user's own.

What a step returns is kept at once: the state for the next step, what the
interface is to show, the grades of what the learner answered, and what the
learner and the models wrote, whose words are taken into the vocabulary
once the exercise is over. Then a model writes the log of the exercise from
them, as logs.py describes, in the background, so that the learner can go on
meanwhile.

An exercise may study the user's Anki collection, as the reviewer of Anki
does: it asks the server for the next card of a deck, and answers it, and
the answers are reviews of the collection, synced to the user's other
devices. The deck-status server is reached only through the server here.

An exercise may have a time limit, in minutes, from when it is first shown.
The app keeps the time and finishes the exercise once it is up; what the
learner sends after that, and a little more for the way there, is refused.
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from anki_import import AnkiLink, AnkiUnavailable
from grammar import Grammar
from instances import instance_problem, schema_problem
from intake import read_usage
from languages import language_of
from logs import LogError, Task, has_anything, write_again, write_log
from models import Model
from profiling import Profile, ProfileError, spent, spent_by
from storage import UserStore
from topics import (
    DEFAULT_EMBEDDING_MODEL,
    MAX_WORDS,
    Embeddings,
    Send,
    as_picture,
    choose_words,
    draw,
    make_icon,
    rank,
    send_to_model,
    topic_text,
)
from translating import TranslationError, read_text

EXERCISES_DIRECTORY = Path(__file__).parent / "exercises"
# how long one step may take, with the models it asks
STEP_TIMEOUT_SECS = 300.0
# how often a step may ask a model, and have a picture drawn, which costs most
MAX_ASKS = 10
MAX_DRAWS = 1
# how often a step may ask of the Anki collection
MAX_ANKI_REQUESTS = 10
# what an exercise may ask of the Anki collection, as kit.py describes
ANKI_OPS = ("sync", "next", "answer")
# far more than an exercise needs to say
MAX_REPLY_BYTES = 2_000_000
# no exercise is done more often than this in a session
MAX_INSTANCES = 50
# How many words that were never embedded are embedded when a session
# starts. With more, the session waits for the vocabulary to be embedded in
# the background.
MAX_EMBEDDED_AT_START = 1000
# How many of the sessions an exercise was in before are looked at for what
# it was answered with, and how long what it is told of them may be.
GUIDANCE_SESSIONS = 20
MAX_GUIDANCE = 3000
# the most an exercise is told of what to make when a session starts, as
# the tutor briefs it
MAX_STEERING = 4000
# how many of the words nearest the topics are printed when a session starts
SHOWN_WORDS = 15
# how many of the lessons practised last a session without a lesson reviews
REVIEWED_LESSONS = 10
# what an exercise may score, as `SCORES` of exercises/kit.py names them
SCORES = (
    "reading",
    "listening",
    "writing",
    "speaking",
    "task",
    "coherence",
    "vocabulary",
    "structures",
    "pronunciation",
)
# the longest time limit an exercise may have, in minutes
MAX_MINUTES = 240
# how long after its time is up what an exercise is sent is still taken, for
# the way it takes there, in seconds
GRACE_SECS = 30
# The interface of an exercise is a module the app loads into its own page,
# where it runs as the app does: it is trusted, as the backend is, to be the
# user's own. The files it may be made of, by their endings, with what each
# is.
UI_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}
_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
# Runs the backend that is named, with the kit to be imported, and nothing
# else of the server's. It is run with -I, which leaves out the directory it
# is started in and whatever the environment says about Python.
_LAUNCH = (
    "import runpy, sys; sys.path[:0] = [sys.argv[1]];"
    " runpy.run_path(sys.argv[2], run_name='__main__')"
)

# Asks a language model the messages given, and replies with what it said and
# what asking used. Raises TranslationError.
Asker = Callable[[list[dict[str, Any]]], tuple[str, Profile]]
# Has an image model draw a prompt in an aspect ratio, and replies with the
# picture, as a data URL, and what drawing it used. Raises TranslationError.
Drawer = Callable[[str, str], tuple[str, Profile]]
# Has a job done in the background, named in a few words. The job returns
# what the models it asked used, and raises ExerciseError if it fails.
Later = Callable[[str, Callable[[], list[Profile]]], None]
# Answers what an exercise asks of the user's Anki collection, as kit.py
# describes. Raises ValueError for what cannot be asked, and AnkiUnavailable.
AnkiAsker = Callable[[dict[str, Any]], Any]
# the aspect ratios a picture may be drawn in
ASPECT_RATIOS = ("1:1", "4:3", "3:4", "16:9", "9:16", "3:2", "2:3", "21:9")


class ExerciseError(Exception):
    """A step of an exercise could not be made. The message says why."""


@dataclass
class Choosing:
    """How the topics and the words of a session are chosen."""

    # Whether the exercises bring all the topics chosen together. Otherwise
    # one of them is drawn for the whole session.
    mix_topics: bool = False
    # The words the exercises are given: "none", the whole vocabulary
    # ("all"), or the `words` that are sent, such as those of a set ("set").
    vocabulary: str = "none"
    words: list[str] = field(default_factory=list)
    # Whether the words are those nearest the topics, rather than those
    # used last.
    topic_words: bool = True
    embedding_model: Model = Model(DEFAULT_EMBEDDING_MODEL)


@dataclass
class Manifest:
    id: str
    title: str
    description: str
    # Whether it teaches rather than asks: it comes first, is done once,
    # and is graded on nothing, so it has no log.
    theory: bool = False
    # What the learner chooses besides how many times it is done, by name:
    # each `{"label": ..., "choices": {value: label}}`, the first choice the
    # one taken unless another is; `{"label": ..., "texts": True}`, one of
    # the learner's texts that are not corrected yet, which are its choices
    # by their ids once they are filled in; `{"label": ..., "anki_decks":
    # True}`, a deck of the learner's Anki collection, which are its choices
    # by their ids, as text, once they are filled in; or `{"label": ...,
    # "min": ..., "max": ..., "default": ...}`, a whole number.
    options: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Whether it practises a lesson; one that does not, such as correcting
    # a text of the learner's, needs none, and a session of such exercises
    # alone has no lesson and reviews none.
    lesson: bool = True
    # Whether it is done once, with no time limit, such as correcting a
    # text: how many times it is done, and how long it may take, are not
    # for the learner to choose.
    once: bool = False
    # Whether it is about the topics of the session; one that is about
    # neither them nor a lesson, such as reviewing the learner's Anki cards,
    # is chosen only when neither is.
    topics: bool = True
    # Whether it is listed before every other, such as reviewing the
    # learner's Anki cards, which comes before what is made for them.
    first: bool = False
    # Whether the tutor offers it with a tool of its own, apart from the one
    # that offers the exercises made for the learner, such as reviewing
    # their Anki cards, which makes nothing.
    own_tool: bool = False
    # Whether its interface has an icon, ui/icon.svg, which the app shows it
    # with in place of its description
    icon: bool = False
    # The shape of one instance of what it makes, as instances.py says, so
    # that what it made is kept and can be done again; None for one that
    # makes nothing, such as reviewing the Anki cards.
    instance: dict[str, Any] | None = None
    # What it shows, its title, description and options and the texts of its
    # interface, in each language the app is shown in but English, by the
    # English name of the language and then by what it says in English.
    messages: dict[str, dict[str, str]] = field(default_factory=dict)
    # Whether the sentences written in its text boxes are checked by the
    # sentence check model, as those of the chat are: "always", "never", or
    # "optional", as the learner chooses with a checkbox in the bar of the
    # session, off at first.
    sentence_checks: str = "never"


# Whether the sentences written in an exercise may be checked.
SENTENCE_CHECKS = ("always", "optional", "never")


def exercises(directory: Path = EXERCISES_DIRECTORY) -> list[Manifest]:
    """The exercises there are, those listed first, then those of theory,
    then the others by their titles: each directory with a manifest, a
    backend and an interface."""
    found = []
    for path in sorted(directory.iterdir()) if directory.is_dir() else []:
        manifest = path / "manifest.json"
        if not _ID.fullmatch(path.name) or not manifest.exists():
            continue
        if (
            not (path / "backend.py").exists()
            or not (path / "ui" / "index.js").exists()
        ):
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except ValueError:
            continue
        instance = data.get("instance") if isinstance(data, dict) else None
        if instance is not None and schema_problem(instance):
            # an exercise whose instances could not be kept is not offered
            continue
        if isinstance(data, dict) and isinstance(data.get("title"), str):
            found.append(
                Manifest(
                    path.name,
                    data["title"],
                    str(data.get("description") or ""),
                    data.get("theory") is True,
                    _read_options(data.get("options")),
                    data.get("lesson") is not False,
                    data.get("once") is True,
                    data.get("topics") is not False,
                    data.get("first") is True,
                    data.get("own_tool") is True,
                    (path / "ui" / "icon.svg").is_file(),
                    instance,
                    _read_translations(data.get("messages")),
                    data["sentence_checks"]
                    if data.get("sentence_checks") in SENTENCE_CHECKS
                    else "never",
                )
            )
    return sorted(
        found,
        key=lambda manifest: (not manifest.first, not manifest.theory, manifest.title),
    )


# The options whose choices the app fills in, by what marks them, each with
# what is said when there is none to choose.
FILLED_OPTIONS = {
    "texts": "one of your texts that is not corrected yet",
    "anki_decks": "a deck of your Anki collection: link one first",
}


def _read_translations(value: object) -> dict[str, dict[str, str]]:
    """What a manifest shows in other languages, each text that is not
    text left out."""
    return {
        language: {
            english: said
            for english, said in texts.items()
            if isinstance(english, str) and isinstance(said, str)
        }
        for language, texts in (value.items() if isinstance(value, dict) else [])
        if isinstance(language, str) and isinstance(texts, dict)
    }


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _read_options(value: object) -> dict[str, dict[str, Any]]:
    """The options of a manifest, those that are not as kit.py describes
    left out."""
    options: dict[str, dict[str, Any]] = {}
    for name, option in value.items() if isinstance(value, dict) else []:
        if not (_ID.fullmatch(name) and isinstance(option, dict)):
            continue
        label = str(option.get("label") or name)
        filled = next(
            (kind for kind in FILLED_OPTIONS if option.get(kind) is True), None
        )
        if filled:
            options[name] = {"label": label, filled: True, "choices": {}}
            continue
        choices = option.get("choices")
        if (
            isinstance(choices, dict)
            and choices
            and all(isinstance(each, str) for each in choices.values())
        ):
            options[name] = {"label": label, "choices": choices}
            continue
        least, most, default = (option.get(each) for each in ("min", "max", "default"))
        if (
            _whole(least)
            and _whole(most)
            and _whole(default)
            and least <= default <= most  # type: ignore[operator]
        ):
            options[name] = {
                "label": label,
                "min": least,
                "max": most,
                "default": default,
            }
    return options


def _steering_of(steering: dict[str, str] | None, exercise: str) -> str:
    """The brief `steering` gives an exercise, with its lines kept, as it
    may list what each thing made is to be, cut to `MAX_STEERING` characters.
    Raises ValueError for one that is not text."""
    said = (steering or {}).get(exercise, "")
    if not isinstance(said, str):
        raise ValueError("what an exercise is steered with is text")
    return lines_of(said)[:MAX_STEERING]


def lines_of(text: str) -> str:
    """`text` with the spaces of each line made one, and without empty
    lines."""
    return "\n".join(
        " ".join(line.split()) for line in text.splitlines() if line.strip()
    )


def default_of(option: dict[str, Any]) -> Any:
    """The value of an option taken unless another is chosen: none, for
    one that has no choices, as a text where the learner has none."""
    if "choices" in option:
        return next(iter(option["choices"]), "")
    return option["default"]


def chosen_options(manifest: Manifest, given: object) -> dict[str, Any]:
    """A value for each option of `manifest`: the one `given`, or else the
    one taken unless another is. Raises ValueError for a value it cannot
    have."""
    given = given or {}
    if not isinstance(given, dict):
        raise ValueError("the options of an exercise are given by their names")
    values = {}
    for name, option in manifest.options.items():
        value = given.get(name, default_of(option))
        for kind, needed in FILLED_OPTIONS.items():
            if option.get(kind) and value not in option["choices"]:
                raise ValueError(f"{manifest.title} needs {needed}")
        if "choices" in option:
            if value not in option["choices"]:
                raise ValueError(
                    f"{value} is not a choice of {manifest.title}: {option['label']}"
                )
        elif not (_whole(value) and option["min"] <= value <= option["max"]):
            raise ValueError(
                f"{option['label']} of {manifest.title} is a whole number"
                f" from {option['min']} to {option['max']}"
            )
        values[name] = value
    return values


def ui_file(
    path: str, directory: Path = EXERCISES_DIRECTORY
) -> tuple[bytes, str] | None:
    """A file the interface of an exercise is made of, with what it is, as
    it is asked for by its path from `directory`: `kit.js` and `kit.css`,
    which every interface may use, or a file in the `ui` directory of an
    exercise. None for anything else."""
    parts = path.split("/")
    if parts in (["kit.js"], ["kit.css"]):
        file = directory / parts[0]
    elif len(parts) >= 3 and _ID.fullmatch(parts[0]) and parts[1] == "ui":
        ui = (directory / parts[0] / "ui").resolve()
        file = ui.joinpath(*parts[2:]).resolve()
        if ui not in file.parents:
            return None
    else:
        return None
    kind = UI_TYPES.get(file.suffix)
    if kind is None or not file.is_file():
        return None
    return file.read_bytes(), kind


def model_asker(
    chat: Callable[[dict[str, Any], Model], dict[str, Any]], model: Model
) -> Asker:
    """What asks `model`, as the exercises want it asked."""

    def ask(messages: list[dict[str, Any]]) -> tuple[str, Profile]:
        problem = model.problem()
        if problem:
            raise TranslationError(problem)
        try:
            response = chat(
                {"model": model.name, "messages": messages, "usage": {"include": True}},
                model,
            )
        except ProfileError as error:
            raise TranslationError(str(error)) from None
        return read_text(response), read_usage(response, model.name)

    return ask


def model_drawer(model: Model, send: Send = send_to_model) -> Drawer:
    """What has the image `model` draw, as the exercises want pictures
    drawn."""

    def draw_picture(prompt: str, aspect_ratio: str) -> tuple[str, Profile]:
        if not model.name:
            raise TranslationError("no image model was named")
        try:
            picture, _, used = draw(prompt, model, aspect_ratio, send)
            return as_picture(picture), used
        except ProfileError as error:
            raise TranslationError(str(error)) from None

    return draw_picture


def do_now(title: str, job: Callable[[], list[Profile]]) -> None:
    """Does a job that could be done in the background at once."""
    job()


def cannot_draw(prompt: str, aspect_ratio: str) -> tuple[str, Profile]:
    raise TranslationError("no image model was named")


class Runner:
    """Runs one step of the backend of an exercise in a process of its own."""

    def __init__(
        self,
        directory: Path = EXERCISES_DIRECTORY,
        python: str = sys.executable,
        timeout: float = STEP_TIMEOUT_SECS,
    ) -> None:
        self._directory = directory
        self._python = python
        self._timeout = timeout

    def run(
        self,
        exercise: str,
        request: dict[str, Any],
        ask: Asker,
        draw: Drawer = cannot_draw,
        look: Asker | None = None,
        anki: AnkiAsker | None = None,
        timed: list[str] | None = None,
    ) -> tuple[dict[str, Any], list[Profile]]:
        """What the backend of `exercise` replied to `request`, with what
        the models it had asked used, and `anki` what it asked of the Anki
        collection. How long each request to a model took is told to
        `timed`, a line each. Raises ExerciseError."""
        backend = self._directory / exercise / "backend.py"
        if not _ID.fullmatch(exercise) or not backend.exists():
            raise ExerciseError(f"there is no exercise {exercise}")
        process = subprocess.Popen(
            [
                self._python,
                "-I",
                "-X",
                "utf8",
                "-c",
                _LAUNCH,
                str(self._directory),
                str(backend),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=self._directory / exercise,
            env=_bare_environment(),
            encoding="utf-8",
        )
        assert process.stdin and process.stdout and process.stderr
        # what it writes to its error output, which is read as it comes so
        # that it never waits for room there
        errors: list[str] = []
        reader = threading.Thread(
            target=lambda: errors.extend(process.stderr or []), daemon=True
        )
        reader.start()
        timed_out = threading.Event()

        def stop() -> None:
            timed_out.set()
            process.kill()

        timer = threading.Timer(self._timeout, stop)
        timer.start()
        used: list[Profile] = []
        try:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            reply = self._converse(process, ask, draw, look or ask, anki, used, timed)
        except (OSError, ValueError) as error:
            raise spent(ExerciseError(f"the exercise failed: {error}"), used) from None
        except ExerciseError as error:
            raise spent(error, used) from None
        finally:
            timer.cancel()
            process.kill()
            process.wait()
            reader.join(timeout=1)
        # what the models it asked used is counted though the exercise failed
        try:
            if timed_out.is_set():
                raise ExerciseError(
                    f"the exercise took more than {self._timeout:.0f} s"
                )
            if reply is None:
                said = "".join(errors).strip().splitlines()
                raise ExerciseError(
                    "the exercise stopped without a reply"
                    f"{': ' + said[-1] if said else ''}"
                )
            if "error" in reply:
                raise ExerciseError(str(reply["error"]))
            return _read_reply(reply.get("reply")), used
        except ExerciseError as error:
            raise spent(error, used) from None

    def _converse(
        self,
        process: subprocess.Popen[str],
        ask: Asker,
        draw: Drawer,
        look: Asker,
        anki: AnkiAsker | None,
        used: list[Profile],
        timed: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Answers what the backend asks of the models and of the Anki
        collection until it replies. None if it stops first."""
        assert process.stdin and process.stdout
        asked = drawn = studied = 0
        while line := process.stdout.readline():
            if len(line) > MAX_REPLY_BYTES:
                raise ExerciseError("the exercise said too much")
            said = json.loads(line)
            if not isinstance(said, dict):
                raise ExerciseError("the exercise said what is not an object")
            if not {"ask", "look", "draw", "anki"} & said.keys():
                return said
            answer: dict[str, Any]
            try:
                if "anki" in said:
                    studied += 1
                    if studied > MAX_ANKI_REQUESTS:
                        raise ValueError(
                            f"an exercise asks of Anki at most {MAX_ANKI_REQUESTS} times"
                        )
                    if anki is None:
                        raise ValueError("there is no Anki collection here")
                    request = said["anki"] if isinstance(said["anki"], dict) else {}
                    answer = {"answer": anki(request)}
                elif "ask" in said or "look" in said:
                    asked += 1
                    if asked > MAX_ASKS:
                        raise TranslationError(
                            f"an exercise asks at most {MAX_ASKS} times"
                        )
                    # a look is asked of the model that sees pictures best
                    kind = "ask" if "ask" in said else "look"
                    request = said[kind] if isinstance(said[kind], dict) else {}
                    asker = ask if kind == "ask" else look
                    started = time.monotonic()
                    text, profile = asker(_read_messages(request.get("messages")))
                    _time(timed, kind, profile, started)
                    used.append(profile)
                    answer = {"answer": text}
                else:
                    drawn += 1
                    if drawn > MAX_DRAWS:
                        raise TranslationError(
                            f"an exercise has at most {MAX_DRAWS} pictures drawn"
                        )
                    request = said["draw"] if isinstance(said["draw"], dict) else {}
                    started = time.monotonic()
                    text, profile = draw(*_read_drawing(request))
                    _time(timed, "draw", profile, started)
                    used.append(profile)
                    answer = {"answer": text}
            except (TranslationError, ValueError, AnkiUnavailable) as error:
                answer = {"error": str(error)}
            process.stdin.write(json.dumps(answer) + "\n")
            process.stdin.flush()
        return None


def _time(timed: list[str] | None, kind: str, profile: Profile, started: float) -> None:
    if timed is not None:
        timed.append(
            f"{kind} {profile.model}: {time.monotonic() - started:.1f} s,"
            f" {profile.input_tokens} tokens in, {profile.output_tokens} out"
        )


def anki_asker(anki: AnkiLink) -> AnkiAsker:
    """What answers an exercise that asks of the Anki collection of `anki`:
    `{"op": "sync"}` to sync it, `{"op": "next", "deck": ID}` for the next
    card of a deck, or `{"op": "answer", "deck": ID, "card": ID, "rating":
    1 to 4, "millis": ...}` to answer the card at the top of its queue."""

    def ask(request: dict[str, Any]) -> Any:
        op = request.get("op")
        if op == "sync":
            anki.sync()
            return {"synced": True}
        if op not in ANKI_OPS:
            raise ValueError(f"Anki is asked one of {', '.join(ANKI_OPS)}")
        deck = request.get("deck")
        if not isinstance(deck, int) or isinstance(deck, bool):
            raise ValueError("a deck of Anki is asked for by its id")
        if op == "next":
            return anki.next_card(deck)
        card, rating, millis = (
            request.get(each) for each in ("card", "rating", "millis")
        )
        if not (_whole(card) and _whole(rating) and 1 <= rating <= 4):  # type: ignore[operator]
            raise ValueError("a card of Anki is answered by its id, with 1 to 4")
        millis = millis if _whole(millis) and millis >= 0 else 0  # type: ignore[operator]
        return anki.answer_card(deck, card, rating, millis)  # type: ignore[arg-type]

    return ask


def _bare_environment() -> dict[str, str]:
    """What a backend is given of the environment: only what Python needs
    to start, and nothing that holds a key."""
    kept = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH")
    return {name: os.environ[name] for name in kept if name in os.environ}


def _read_messages(value: object) -> list[dict[str, Any]]:
    """The messages an exercise asks with: each with a role and a content,
    which is text, or a list of parts that are text or pictures given as
    data URLs."""
    if not isinstance(value, list) or not value:
        raise ValueError("an exercise asks with messages")
    messages = []
    for message in value:
        if not isinstance(message, dict) or message.get("role") not in (
            "system",
            "user",
            "assistant",
        ):
            raise ValueError("every message needs a role and a content")
        messages.append(
            {"role": message["role"], "content": _read_content(message.get("content"))}
        )
    return messages


def _read_content(content: object) -> str | list[dict[str, Any]]:
    if isinstance(content, str):
        return content
    if not isinstance(content, list) or not content:
        raise ValueError("every message needs a role and a content")
    parts: list[dict[str, Any]] = []
    for part in content:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind == "text" and isinstance(part.get("text"), str):
            parts.append({"type": "text", "text": part["text"]})
            continue
        image = part.get("image_url") if kind == "image_url" else None
        url = image.get("url") if isinstance(image, dict) else None
        # a picture the exercise has, and no address for the model to fetch
        if not isinstance(url, str) or not url.startswith("data:image/"):
            raise ValueError("a part of a message is text, or a picture as a data URL")
        parts.append({"type": "image_url", "image_url": {"url": url}})
    return parts


def _read_drawing(request: dict[str, Any]) -> tuple[str, str]:
    prompt, aspect_ratio = request.get("prompt"), request.get("aspect_ratio", "1:1")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("a picture is drawn from a prompt")
    if aspect_ratio not in ASPECT_RATIOS:
        raise ValueError(f"a picture is drawn in one of {', '.join(ASPECT_RATIOS)}")
    return prompt, aspect_ratio


def _read_reply(reply: object) -> dict[str, Any]:
    if not isinstance(reply, dict):
        raise ExerciseError("the exercise replied with nothing")
    graded = reply.get("graded") or []
    if not isinstance(graded, list) or not all(
        isinstance(each, dict) for each in graded
    ):
        raise ExerciseError("the grades of an exercise must be a list of objects")
    written = reply.get("written") or {}
    if not isinstance(written, dict):
        raise ExerciseError("what an exercise wrote must be an object of lists")
    log = reply.get("log")
    if log is not None and not isinstance(log, str):
        raise ExerciseError("the log of an exercise must be text")
    made = reply.get("made") or []
    if not isinstance(made, list):
        raise ExerciseError("what an exercise made must be a list of instances")
    return {
        **reply,
        "graded": graded,
        "written": written,
        "scores": _read_scores(reply.get("scores")),
        "log": log.strip() if log else None,
        "made": made,
    }


def _read_scores(value: object) -> dict[str, float] | None:
    """The scores an exercise reported, each from 0 to 100 by a name of
    `SCORES`, or None if it reported none."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ExerciseError("the scores of an exercise must be an object")
    scores = {}
    for name, score in value.items():
        if name not in SCORES:
            raise ExerciseError(f"an exercise cannot score {name}")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ExerciseError(f"the score {name} must be a number")
        scores[name] = round(min(100.0, max(0.0, float(score))), 1)
    return scores


def describe_scores(scores: dict[str, float] | None) -> str:
    """The scores of an exercise as they are written into its log; nothing
    if it has none."""
    if not scores:
        return ""
    return "Scores: " + ", ".join(f"{name} {score:g}" for name, score in scores.items())


class Practice:
    """The sessions of practice of one user, and the exercises done in them."""

    def __init__(
        self,
        store: UserStore,
        grammar: Grammar | None = None,
        runner: Runner | None = None,
        directory: Path = EXERCISES_DIRECTORY,
        embeddings: Embeddings | None = None,
        lemmas_of: Callable[[str], list[str]] = lambda language: [],
        draw: Callable[[list[str]], str] = random.choice,
        tell: Callable[[str], None] = lambda line: None,
        send: Send = send_to_model,
        later: Later = do_now,
        now: Callable[[], float] = time.time,
        anki: AnkiLink | None = None,
    ) -> None:
        self._now = now
        # the user's Anki collection, which exercises may study
        self._anki = anki
        self._store = store
        self._grammar = grammar or Grammar()
        self._runner = runner or Runner(directory)
        self._directory = directory
        # what sends the requests for icons and embeddings to the models
        self._send = send
        self.embeddings = embeddings or Embeddings(store, send)
        # the words of the vocabulary of a language, those used last first
        self.lemmas_of = lemmas_of
        self._draw = draw
        # what is told to whoever runs the server: the words a session was
        # given, and how long each step took, and what in it
        self._tell = tell
        # what has the logs of the exercises written once they are over
        self._later = later
        # the embedding models that are embedding a vocabulary in the background
        self.embedding: set[str] = set()
        # one step at a time, so that two never start from the same state
        self._lock = threading.Lock()

    def exercises(self) -> list[dict[str, Any]]:
        return [asdict(manifest) for manifest in self._manifests()]

    def _manifests(self) -> list[Manifest]:
        """The exercises there are, with the learner's texts that are not
        corrected yet as the choices of an option of texts, by their ids,
        and the decks of their Anki collection as those of an option of
        decks."""
        filled = {
            "texts": {
                text["id"]: text["title"] or "Untitled"
                for text in self._store.texts()
                if text["kind"] == "text" and text["lockedAt"] is None
            },
            "anki_decks": self._anki_decks(),
        }
        return [
            replace(
                manifest,
                options={
                    name: {
                        **option,
                        "choices": next(
                            (
                                choices
                                for kind, choices in filled.items()
                                if option.get(kind)
                            ),
                            option.get("choices"),
                        ),
                    }
                    if "choices" in option
                    else option
                    for name, option in manifest.options.items()
                },
            )
            for manifest in exercises(self._directory)
        ]

    def _anki_decks(self) -> dict[str, str]:
        """The decks of the Anki collection by their ids, as text, with
        their full names; none if there is no collection, or it cannot be
        reached."""
        if self._anki is None:
            return {}
        try:
            decks = self._anki.decks()
        except AnkiUnavailable:
            return {}
        return {
            str(deck["id"]): str(deck.get("name") or deck["id"])
            for deck in decks
            if _whole(deck.get("id"))
        }

    def lessons(self, language: str) -> list[dict[str, Any]]:
        """The lessons of `language`. Raises GrammarError."""
        return [asdict(lesson) for lesson in self._grammar.lessons(language)]

    def start_session(
        self,
        language: str,
        lesson: str,
        topics: list[str],
        chosen: dict[str, int],
        choosing: Choosing | None = None,
        options: dict[str, Any] | None = None,
        minutes: dict[str, int] | None = None,
        exam: str = "",
        reviewing: list[str] | None = None,
        steering: dict[str, str] | None = None,
    ) -> tuple[dict[str, Any], list[Profile]]:
        """Start a session of `lesson`, with the exercises `chosen`, each
        with how many instances of it there are to be, the `options` it
        is chosen with and how many `minutes` it may take, by exercise,
        about `topics`, with the words `choosing` says. An exercise of
        theory comes first, with no instances and no time limit, as it is
        not answered. Without a lesson, the session reviews the lessons
        practised last, or those `reviewing` names, and has no theory.
        What `steering` says of an exercise is the brief the tutor gave it,
        what it is to make, which it follows before its lesson, topics and
        words.

        A session with an `exam` is a part of an evaluation: what the exam
        says the part is like is told to every exercise of it, and what is
        written in it is not taken into the vocabulary. Returns the session
        with what embedding the words used. Raises ValueError, and
        ProfileError if the words could not be embedded."""
        choosing = choosing or Choosing()
        minutes = minutes or {}
        known = {manifest.id: manifest for manifest in self._manifests()}
        reviewed: list[str] = []
        # exercises that practise no lesson need none, and review none
        lessonless = bool(chosen) and all(
            exercise in known and not known[exercise].lesson for exercise in chosen
        )
        if not lesson and lessonless:
            pass
        elif not lesson:
            if any(exercise in known and known[exercise].theory for exercise in chosen):
                raise ValueError("theory is that of a lesson: choose one")
            reviewed = self.practised(language) if reviewing is None else reviewing
            if not reviewed and not exam:
                raise ValueError(
                    "a review goes over the lessons practised last: practise one first"
                )
        elif self._grammar.lesson(language, lesson) is None:
            raise ValueError(f"there is no lesson {lesson} in {language}")
        if not chosen:
            raise ValueError("choose an exercise")
        options = options or {}
        if not isinstance(options, dict):
            raise ValueError("the options are given by exercise")
        for exercise, instances in chosen.items():
            if exercise not in known:
                raise ValueError(f"there is no exercise {exercise}")
            if known[exercise].theory or known[exercise].once:
                continue
            if not isinstance(instances, int) or not 0 < instances <= MAX_INSTANCES:
                raise ValueError(f"an exercise has 1 to {MAX_INSTANCES} instances")
            limit = minutes.get(exercise, 0)
            if not _whole(limit) or not 0 <= limit <= MAX_MINUTES:
                raise ValueError(f"an exercise takes 0 to {MAX_MINUTES} minutes")
        chosen = {
            exercise: 0
            if known[exercise].theory
            else 1
            if known[exercise].once
            else instances
            for exercise, instances in sorted(
                chosen.items(), key=lambda each: not known[each[0]].theory
            )
        }
        if all(known[exercise].theory for exercise in chosen):
            # theory is about the lesson alone, whatever was chosen besides
            topics, choosing = [], Choosing()
        about = [self._store.topic(topic) for topic in dict.fromkeys(topics)]
        if None in about:
            raise ValueError("there is no such topic")
        if len(topics) > 1 and not choosing.mix_topics:
            topics = [self._draw(topics)]
            about = [self._store.topic(topics[0])]
        values = {
            exercise: chosen_options(known[exercise], options.get(exercise))
            for exercise in chosen
        }
        words, used = self._words(
            language, [topic_text(each) for each in about if each], choosing
        )
        if not exam:
            # the session of practice left running, which this one ends, is
            # not kept if nothing was done in it
            self._hide_left_running()
        session = self._store.start_session(
            uuid.uuid4().hex,
            language,
            lesson,
            list(dict.fromkeys(topics)),
            chosen,
            words,
            choosing.mix_topics and len(topics) > 1,
            {exercise: self.guidance(exercise) for exercise in chosen},
            reviewed,
            values,
            {
                exercise: 0
                if known[exercise].theory or known[exercise].once
                else minutes.get(exercise, 0)
                for exercise in chosen
            },
            {exercise: exam for exercise in chosen} if exam else {},
            {exercise: _steering_of(steering, exercise) for exercise in chosen},
        )
        return session, used

    def practised(self, language: str) -> list[str]:
        """The ids of the lessons of `language` practised last, at most
        `REVIEWED_LESSONS` of them, in the order they are taught in. A
        lesson is practised in a session of it, and not in a review."""
        latest_first = dict.fromkeys(
            session["lesson"]
            for session in self._store.sessions()
            if session["language"] == language
            and session["lesson"]
            and not session["hidden"]
        )
        last = set(list(latest_first)[:REVIEWED_LESSONS])
        return [
            lesson.id for lesson in self._grammar.lessons(language) if lesson.id in last
        ]

    def guidance(self, exercise: str) -> str:
        """What an exercise is told to heed when a session starts, besides
        its lesson, topics and words: what it was answered with in the last
        sessions it was in, so that it chooses other things. Nothing if it
        was in none."""
        used = []
        length = 0
        for text in self._store.used_before(exercise, GUIDANCE_SESSIONS):
            length += len(text) + 2
            if length > MAX_GUIDANCE:
                break
            used.append(text)
        if not used:
            return ""
        return (
            "The learner had these in the last sessions of this exercise, the"
            " latest first. Do not use them again: choose other words, things and"
            f" sentences.\n{'; '.join(used)}"
        )

    def _words(
        self, language: str, topics: list[str], choosing: Choosing
    ) -> tuple[dict[str, Any] | None, list[Profile]]:
        """The words the exercises of a session about `topics` are to
        use, as `choosing` says, with what embedding them used."""
        if choosing.vocabulary == "all":
            candidates = self.lemmas_of(language)
        elif choosing.vocabulary == "set":
            candidates = list(dict.fromkeys(choosing.words))
        else:
            return None, []
        if not candidates:
            return None, []
        if not (choosing.topic_words and topics):
            return {"mode": "prefer", "lemmas": candidates[:MAX_WORDS]}, []
        model = choosing.embedding_model
        missing = self.embeddings.missing(candidates + topics, model.name)
        if len(missing) > MAX_EMBEDDED_AT_START:
            raise ValueError(
                f"{len(missing)} words of the vocabulary are not embedded yet:"
                " wait for them to be, and start again"
            )
        used = self.embeddings.embed(missing, model)
        ranked = rank(self.embeddings, topics, candidates, model.name)
        words = choose_words(ranked, MAX_WORDS)
        nearest = ", ".join(
            f"{word} {score:.2f}" for word, score in ranked[:SHOWN_WORDS]
        )
        self._tell(
            f"{datetime.now():%H:%M:%S} words for {'; '.join(topics)}:"
            f" {words['mode']} {len(words['lemmas'])} of {len(candidates)}"
            f"\n       nearest: {nearest}"
        )
        return words, used

    def make_icon(
        self, topic: dict[str, Any], model: Model
    ) -> tuple[bytes, str, Profile]:
        """An icon for `topic`, made by the image `model`. Raises ProfileError."""
        return make_icon(topic, model, self._send)

    def vocabulary_to_embed(self, language: str, model: str) -> list[str]:
        """The words of the vocabulary of `language` that `model` has not
        embedded yet."""
        return self.embeddings.missing(self.lemmas_of(language), model)

    def step(
        self,
        session_id: str,
        exercise: str,
        op: str,
        message: Any,
        context: dict[str, str],
        ask: Asker,
        draw: Drawer = cannot_draw,
        look: Asker | None = None,
    ) -> tuple[Any, list[Profile]]:
        """Make a step of an exercise of a session: `start` it, have it
        `act` on the `message` of its interface, or `finish` it. Returns
        what it is to show, with what the models it asked used. `context`
        is the language the learner reads in, as `into`, and their `level`.
        Raises ValueError for a step that cannot be made, and ExerciseError
        for one that failed."""
        asked_at = time.monotonic()
        with self._lock:
            began = time.monotonic()
            session = self._store.session(session_id)
            kept = self._store.exercise_state(session_id, exercise)
            if session is None or kept is None:
                raise ValueError("there is no such exercise in the session")
            if session["status"] != "running":
                raise ValueError("the session has ended")
            if session["progress"][exercise]["status"] == "finished":
                raise ValueError("the exercise is finished")
            started, state, shown = kept
            if op == "start" and started:
                # the interface was opened again, and is shown what it showed
                return shown, []
            if op == "finish" and not started:
                return None, []
            if op == "act" and not started:
                raise ValueError("the exercise has not started")
            if op == "act" and self._time_is_up(session, exercise):
                raise ValueError("the time for this exercise is up")
            if op not in ("start", "act", "finish"):
                raise ValueError(f"there is no step {op}")
            request = {
                "op": op,
                "context": self._context(session, exercise, context),
                "state": state,
                "message": message,
            }
            anki = anki_asker(self._anki) if self._anki else None
            timed: list[str] = []
            try:
                reply, used = self._runner.run(
                    exercise, request, ask, draw, look, anki, timed
                )
            finally:
                self._tell(
                    f"{datetime.now():%H:%M:%S} {exercise} {op}:"
                    f" {time.monotonic() - began:.1f} s,"
                    f" after waiting {began - asked_at:.1f} s"
                    + "".join(f"\n       {line}" for line in timed)
                )
            # what the models it asked used is counted though what came of it is refused
            try:
                # the grades are kept first, as they are what matters most
                try:
                    self._store.add_grades(session_id, exercise, reply["graded"])
                    self._store.add_written(
                        session_id, exercise, reply.get("written") or {}
                    )
                except ValueError as error:
                    raise ExerciseError(str(error)) from None
                self._keep_made(session, exercise, reply.get("made") or [])
                if op != "finish":
                    self._store.save_exercise_state(
                        session_id, exercise, reply.get("state"), reply.get("show")
                    )
                    return reply.get("show"), used
                self._store.finish_exercise(
                    session_id, exercise, reply.get("results"), reply.get("scores")
                )
                self._take_texts(session, exercise, reply.get("results"))
                if reply.get("log"):
                    # the exercise wrote its log itself
                    manifest = next(
                        (each for each in self._manifests() if each.id == exercise),
                        None,
                    )
                    self._store.set_log(
                        session_id,
                        exercise,
                        reply["log"],
                        manifest.title if manifest else exercise,
                    )
                    return None, used
            except ExerciseError as error:
                raise spent(error, used) from None
        self._log_later(session, exercise, request["context"], ask)
        return None, used

    def _keep_made(
        self, session: dict[str, Any], exercise: str, made: list[Any]
    ) -> None:
        """Keep what an exercise made in a step, each instance checked to be
        of the shape its manifest declares; one that does again what was
        made before makes nothing new. Raises ExerciseError."""
        if not made or session["progress"][exercise]["replays"]:
            return
        manifest = next(
            (each for each in exercises(self._directory) if each.id == exercise), None
        )
        if manifest is None or manifest.instance is None:
            raise ExerciseError(f"{exercise} made what its manifest has no instance of")
        for each in made:
            problem = instance_problem(each, manifest.instance)
            if problem:
                raise ExerciseError(
                    f"{exercise} made an instance unlike its own: {problem}"
                )
        try:
            self._store.add_instances(session["id"], exercise, made)
        except ValueError as error:
            raise ExerciseError(str(error)) from None

    def replay(
        self, session_id: str, exercise: str, fresh: bool = False
    ) -> dict[str, Any]:
        """Start a session that does again an exercise of a session exactly
        as it was: the same instances, in the same order, with the same
        lesson, topics, words, options and brief; or, if `fresh`, with all of
        those but instances made anew, as many as it had. Only an exercise
        that makes what it does, as its manifest says, is done again. Raises
        ValueError for any other, and for one that kept nothing to do again
        exactly."""
        session = self._store.session(session_id)
        if session is None or exercise not in session["exercises"]:
            raise ValueError("there is no such exercise in the session")
        manifest = next(
            (each for each in exercises(self._directory) if each.id == exercise), None
        )
        if manifest is None or manifest.instance is None:
            # one that makes nothing, such as reviewing the Anki cards or
            # correcting a text, goes one way only
            raise ValueError("this exercise is not one to do again")
        ids = [] if fresh else self._store.instance_ids(session_id, exercise)
        if not ids and not fresh:
            raise ValueError("nothing of that exercise was kept to do again")
        self._hide_left_running()
        again = self._store.start_session(
            uuid.uuid4().hex,
            session["language"],
            session["lesson"],
            session["topics"],
            {exercise: len(ids) or session["exercises"][exercise]},
            session["words"],
            session["mix_topics"],
            {exercise: session["guidance"].get(exercise, "")},
            session["lessons"],
            {exercise: session["options"].get(exercise, {})},
            {exercise: session["minutes"].get(exercise, 0)},
            briefs={exercise: session["briefs"].get(exercise, "")},
        )
        if ids:
            self._store.set_replay(again["id"], exercise, ids)
        replayed = self._store.session(again["id"])
        assert replayed
        return replayed

    def _take_texts(
        self, session: dict[str, Any], exercise: str, results: object
    ) -> None:
        """Keep what an exercise did with the texts of its options, as its
        `results` say under `texts`, by the name of each option: the text
        as it was corrected, which is then locked, and its correction."""
        done = results.get("texts") if isinstance(results, dict) else None
        chosen = session["options"].get(exercise, {})
        for name, text in done.items() if isinstance(done, dict) else []:
            if not (
                isinstance(text, dict)
                and isinstance(text.get("content"), str)
                and isinstance(text.get("correction"), str)
                and isinstance(chosen.get(name), str)
            ):
                continue
            try:
                self._store.correct_text(
                    chosen[name],
                    text["content"],
                    uuid.uuid4().hex,
                    text["correction"],
                    session["id"],
                )
            except ValueError as error:
                raise ExerciseError(str(error)) from None

    def _time_is_up(self, session: dict[str, Any], exercise: str) -> bool:
        """Whether the time an exercise had is up, with a little more for
        what is still on its way."""
        limit: int = session["minutes"].get(exercise, 0)
        started: float | None = session["progress"][exercise]["started_at"]
        if not limit or started is None:
            return False
        return self._now() > started + 60 * limit + GRACE_SECS

    def _log_later(
        self,
        session: dict[str, Any],
        exercise: str,
        context: dict[str, Any],
        ask: Asker,
    ) -> None:
        """Have the log of an exercise that is over written in the
        background, if the learner did anything in it. One that did again
        exactly what another did adds to the log of that one, which has
        then how each time went, and has no log of its own."""
        manifest = next(
            (each for each in self._manifests() if each.id == exercise), None
        )
        grades = self._store.grades(session["id"], exercise)
        written = self._store.written(session["id"], exercise)
        if manifest is None or manifest.theory or not has_anything(grades, written):
            return
        title = manifest.title
        chosen = session["options"].get(exercise, {})
        task = Task(
            manifest.title,
            manifest.description,
            context["language"],
            context["level"],
            context["lesson"],
            [topic["title"] for topic in context["topics"]],
            context["instances"],
            [
                f"{option['label']}:"
                f" {option.get('choices', {}).get(chosen[name], chosen[name])}"
                for name, option in manifest.options.items()
                if name in chosen
            ],
        )

        ended = self._store.session(session["id"])
        scores = ended["progress"][exercise]["scores"] if ended else None

        first = self._store.replayed_from(session["id"], exercise)
        lesson = context["lesson"].get("title", "")
        subject = f"{title}: {lesson}" if lesson else title

        def write() -> list[Profile]:
            before = (
                self._store.logs(first).get(exercise) if first is not None else None
            )
            try:
                if before:
                    added, used = write_again(ask, task, before, grades, written)
                    day = datetime.fromtimestamp(self._now()).strftime("%Y-%m-%d")
                    content = f"{before}\nDone again on {day}: {added}"
                else:
                    content, used = write_log(ask, task, grades, written)
            except (LogError, TranslationError) as error:
                raise spent(
                    ExerciseError(f"the log of {title} could not be written: {error}"),
                    spent_by(error),
                ) from None
            if scores:
                content += "\n" + describe_scores(scores)
            self._store.set_log(first or session["id"], exercise, content, subject)
            return [used]

        self._later(title, write)

    def end_session(
        self,
        session_id: str,
        status: str,
        context: dict[str, str],
        ask: Asker,
        draw: Drawer = cannot_draw,
        look: Asker | None = None,
    ) -> tuple[dict[str, Any], list[Profile]]:
        """End a session, after finishing every exercise of it that was
        started, so that what was done of them is kept. Raises ValueError."""
        session = self._store.session(session_id)
        if session is None:
            raise ValueError("there is no such session")
        used: list[Profile] = []
        if session["status"] == "running":
            for exercise, progress in session["progress"].items():
                if progress["status"] != "started":
                    continue
                try:
                    _, finishing = self.step(
                        session_id,
                        exercise,
                        "finish",
                        None,
                        context,
                        ask,
                        draw,
                        look,
                    )
                    used += finishing
                except ExerciseError as error:
                    # the grades it reported are kept all the same, and what
                    # the models it asked used is counted
                    used += spent_by(error)
            self._store.end_session(session_id, status)
        ended = self._store.session(session_id)
        assert ended
        if self._left_untouched(ended):
            # ended, or left, before anything was done in it, it is not kept
            self._drop(ended)
            ended = {**ended, "hidden": True}
        return ended, used

    def _hide_left_running(self) -> None:
        """Hide the session of practice left running, which one that starts
        ends, if nothing was done in it. It is not forgotten, as what shows
        it, such as an exercise the tutor offered, may still name it."""
        for left in self._store.sessions():
            if left["status"] == "running" and self._left_untouched(left):
                self._store.hide_session(left["id"])

    def _drop(self, session: dict[str, Any]) -> None:
        """Forget a session left before anything was done in it; or, if its
        exercises made something, which can be done again, hide it, so that
        it is kept for that alone."""
        if any(progress["kept"] for progress in session["progress"].values()):
            self._store.hide_session(session["id"])
        else:
            self._store.delete_session(session["id"])

    def _left_untouched(self, session: dict[str, Any]) -> bool:
        """Whether nothing was done in a session of practice: nothing graded,
        nothing written by the learner, and no theory read."""
        if (
            session.get("kind") != "practice"
            or session.get("hidden")
            or self._store.grades(session["id"])
        ):
            return False
        theory = {each.id for each in self._manifests() if each.theory}
        return not any(
            self._store.written(session["id"], exercise)["user"]
            or exercise in theory
            and session["progress"][exercise]["status"] != "pending"
            for exercise in session["exercises"]
        )

    def _context(
        self, session: dict[str, Any], exercise: str, context: dict[str, str]
    ) -> dict[str, Any]:
        """What an exercise is told about the session it is in. A review is
        told of a lesson made of the lessons it goes over."""
        exam = session["exams"].get(exercise, "")
        if session["lesson"]:
            lesson = self._grammar.lesson(session["language"], session["lesson"])
        else:
            lesson = self._grammar.review(session["language"], session["lessons"])
        if lesson is None and not session["lesson"] and not session["lessons"]:
            # a session of exercises that practise no lesson
            lesson = {"id": "", "level": "", "title": "", "points": [], "more_info": ""}
        if lesson is None and exam:
            # a level that has no lessons yet is examined all the same
            level = context.get("level") or ""
            lesson = {
                "id": "",
                "level": level,
                "title": f"Level {level}",
                "points": [],
                "more_info": "",
            }
        if lesson is None:
            raise ValueError(
                f"the lesson {session['lesson'] or 'of the review'} is gone"
            )
        topics = [self._store.topic(topic) for topic in session["topics"]]
        language = language_of(session["language"])
        manifest = next(
            (each for each in exercises(self._directory) if each.id == exercise), None
        )
        chosen = session["options"].get(exercise, {})
        options = manifest.options if manifest else {}
        texts = {
            name: self._store.text(chosen[name])
            for name, option in options.items()
            if option.get("texts") and isinstance(chosen.get(name), str)
        }
        deck_names = (
            self._anki_decks()
            if any(option.get("anki_decks") for option in options.values())
            else {}
        )
        return {
            "language": session["language"],
            "letters": dict(language.equivalents),
            "marks": language.marks,
            "answer_words": {
                kind: list(words) for kind, words in language.answer_words.items()
            },
            "into": context.get("into") or "English",
            "level": context.get("level") or "",
            "lesson": lesson,
            # those that have been deleted since are left out
            "topics": [
                {"title": topic["title"], "description": topic["description"]}
                for topic in topics
                if topic
            ],
            "mix_topics": session["mix_topics"],
            "words": session["words"],
            "instances": session["exercises"][exercise],
            "options": session["options"].get(exercise, {}),
            "guidance": session["guidance"].get(exercise, ""),
            "brief": session["briefs"].get(exercise, ""),
            "minutes": session["minutes"].get(exercise, 0),
            "exam": exam,
            # what it made before, which it does again, or None
            "replay": self._store.instances(
                exercise, self._store.instance_ids(session["id"], exercise)
            )
            if session["progress"][exercise]["replays"]
            else None,
            # the learner's texts the options chose, by the name of each
            "texts": {
                name: {
                    "id": text["id"],
                    "title": text["title"],
                    "content": text["content"],
                }
                for name, text in texts.items()
                if text
            },
            # the decks of Anki the options chose, by the name of each
            "anki_decks": {
                name: {
                    "id": int(chosen[name]),
                    "name": deck_names.get(chosen[name], ""),
                }
                for name, option in options.items()
                if option.get("anki_decks")
                and isinstance(chosen.get(name), str)
                and chosen[name].isdigit()
            },
        }
