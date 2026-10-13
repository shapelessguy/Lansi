# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Builds a profile of a sentence by asking a decision model a series of
questions about it.

A decision model, such as Jev, is given a text and typed questions, and
answers each with one of the options it was offered rather than with text of
its own. One is called through OpenRouter's Decisions API, unless one that
takes the same requests is running on this machine, which is then used
instead: it answers sooner and costs nothing.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
TIMEOUT_SECS = 30
# Where a decision model run on this machine takes its requests.
LOCAL_ENDPOINT = "http://127.0.0.1:10000/clef/v1/systemone"
# how often to look whether it is running
LOCAL_POLL_SECS = 5.0
# it is on this machine, so it either answers at once or is not there
LOCAL_PROBE_TIMEOUT_SECS = 2

# Questions by name. A "choice" question is answered with one of the named
# options, and a "score" question with a place on the scale, counted from 0
# for the first level. Options and levels are listed from the worst to the
# best, so the last one is what a sentence with nothing wrong is given.
Questions = dict[str, dict[str, Any]]
# more than anyone would want to ask about one sentence
MAX_QUESTIONS = 20
# A sentence with more words than this does not have its words rated.
MAX_RATED_WORDS = 80
# a word, which may have an apostrophe or a hyphen inside it
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")

# The questions asked about a sentence when the request names none.
QUESTIONS: Questions = {
    "grammar_errors": {
        "type": "choice",
        "instructions": (
            "How many grammar errors does the sentence have? Judge it by the"
            " rules of the language it is written in. Count mistakes in"
            " grammar only, such as word order, agreement, case, tense and"
            " missing or extra words. Do not count spelling or punctuation."
        ),
        # from the worst to the best, as the options of every question are
        "criteria": {
            "several": "The sentence has two or more grammar errors.",
            "one": "The sentence has exactly one grammar error.",
            "none": "The sentence has no grammar errors.",
        },
    },
    "clarity": {
        "type": "score",
        "instructions": (
            "How clear is the sentence? Consider only whether a reader can tell"
            " what the writer means, not whether it is correct."
        ),
        "criteria": [
            "Unclear: it is not possible to tell what is meant.",
            "Hard to follow: the meaning can only be guessed.",
            "Mostly clear: the meaning comes across with some effort.",
            "Clear: the meaning is plain on first reading.",
        ],
    },
}


@dataclass
class Answer:
    """Jev's answer to one question."""

    # "choice", "score", or "noul" for a yes-or-no question
    kind: str
    # The option picked, for a choice question.
    choice: str | None = None
    # The place on the scale, for a score question. It can fall between two
    # levels: 2.5 is halfway between the third and the fourth.
    score: float | None = None
    # The highest place on the scale, for a score question.
    max_score: int | None = None
    # How much the answer is yes, from 0 to 1, for a yes-or-no question.
    yes: float | None = None
    # How near the answer is to the best there is, from 0 to 1: how likely
    # the best option is, for a choice, and how far up the scale, for a score.
    best: float | None = None
    # How sure Jev is, from 0 to 1.
    confidence: float | None = None


@dataclass
class Profile:
    """What was found out about a sentence, by the name of each question."""

    answers: dict[str, Answer]
    # What asking cost, in US dollars, if that was reported.
    cost: float | None = None
    # Tells this request from any other, so that whoever keeps count of
    # usage can count it exactly once.
    id: str = ""
    # The model that answered, and the tokens it was billed for.
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    # Whether the model on this machine answered, which is not paid for.
    local: bool = False


@dataclass
class WordRating:
    """How right a word of a sentence is where it stands."""

    word: str
    # Where the word is in its sentence.
    start: int
    end: int
    # From 0, for a word that is wrong, to 1, for one that is right.
    value: float


class ProfileError(Exception):
    """A profile could not be made. The message says why."""


# Sends a request body with an API key and returns the decoded response.
Transport = Callable[[dict[str, Any], str], dict[str, Any]]


def _post(
    url: str, body: dict[str, Any], headers: dict[str, str], where: str
) -> dict[str, Any]:
    """Send a request and return the decoded response. `where` names the
    place it goes to, for the message of the ProfileError raised if it fails."""
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECS) as response:
            decoded: dict[str, Any] = json.load(response)
            return decoded
    except urllib.error.HTTPError as error:
        raise ProfileError(_error_message(error, where)) from None
    except (OSError, ValueError) as error:
        raise ProfileError(f"could not reach {where}: {error}") from None


def send_to_openrouter(body: dict[str, Any], api_key: str) -> dict[str, Any]:
    return _post(ENDPOINT, body, {"Authorization": f"Bearer {api_key}"}, "OpenRouter")


def _error_message(error: urllib.error.HTTPError, where: str) -> str:
    """The reason that was given for refusing, or the status if none was."""
    try:
        message = json.load(error)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = error.reason
    return f"{where} refused the request ({error.code}): {message}"


def probe_models(endpoint: str) -> str | None:
    """The name of the model a local server at `endpoint` has loaded, or None
    if no such server answers. The models are listed next to the endpoint."""
    url = endpoint.rsplit("/", 1)[0] + "/models"
    try:
        with urllib.request.urlopen(url, timeout=LOCAL_PROBE_TIMEOUT_SECS) as response:
            models = json.load(response)["data"]
        name = models[0]["id"]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    return name if isinstance(name, str) and name else None


class LocalModel:
    """A decision model run on this machine, which may come and go.

    Whether it is there is looked up every few seconds rather than before
    each request, so that asking it, or passing it by, takes no extra time.
    """

    def __init__(
        self,
        endpoint: str = LOCAL_ENDPOINT,
        probe: Callable[[str], str | None] = probe_models,
        send: Transport | None = None,
        on_change: Callable[[str | None], None] | None = None,
    ) -> None:
        self.endpoint = endpoint
        self._probe = probe
        self._send = send or self._post
        self._on_change = on_change
        # the name of the model that is loaded, or None while there is none
        self._model: str | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> str | None:
        """The model that was there when last looked, if any."""
        return self._model

    def look(self) -> str | None:
        """Look whether the model is there right now, and remember it."""
        self._found(self._probe(self.endpoint))
        return self._model

    def watch(self, every_secs: float = LOCAL_POLL_SECS) -> None:
        """Look now, and then again and again on a thread of its own."""
        self.look()

        def keep_looking() -> None:
            # never set, so this only waits; a thread that sleeps would do too
            pause = threading.Event()
            while not pause.wait(every_secs):
                self.look()

        threading.Thread(target=keep_looking, name="local-model", daemon=True).start()

    def send(self, body: dict[str, Any]) -> dict[str, Any]:
        """Ask the model. Raises ProfileError, and takes the model as gone,
        if it does not answer."""
        try:
            return self._send(body, "")
        except ProfileError:
            self._found(None)
            raise

    def _post(self, body: dict[str, Any], _api_key: str) -> dict[str, Any]:
        return _post(self.endpoint, body, {}, "the local model")

    def _found(self, model: str | None) -> None:
        with self._lock:
            changed = model != self._model
            self._model = model
        if changed and self._on_change:
            self._on_change(model)


class Profiler:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        send: Transport = send_to_openrouter,
        local: LocalModel | None = None,
    ) -> None:
        self._model = model
        self._send = send
        self._local = local

    def local_model(self) -> str | None:
        """The name of the model on this machine that questions go to at
        present, or None if they go to OpenRouter."""
        return self._local.model if self._local else None

    def profile(
        self,
        sentence: str,
        api_key: str,
        model: str | None = None,
        questions: Questions | None = None,
    ) -> Profile:
        """Ask `questions` about `sentence`. They go to the model on this
        machine if there is one, and else to `model` on OpenRouter, which
        needs `api_key`. The usual questions and model are used where none
        are given. Raises ProfileError."""
        if questions is None:
            questions = QUESTIONS
        return self._ask({"sentence": sentence}, questions, api_key, model)

    def rate_words(
        self,
        sentence: str,
        assessment: list[dict[str, str]],
        api_key: str,
        model: str | None = None,
    ) -> tuple[list[WordRating], Profile]:
        """Ask of every word of `sentence` whether it is right where it
        stands, in one request, and return how right each is with what the
        request used. `assessment` is what was found out about the sentence
        before, as questions and their answers, which the model is given to
        go by. Raises ProfileError."""
        words = list(_WORD.finditer(sentence))
        if not words or len(words) > MAX_RATED_WORDS:
            raise ProfileError("the sentence has no words, or too many, to rate")
        questions = {
            f"w{number}": word_question(number, word.group())
            for number, word in enumerate(words, start=1)
        }
        state = {"sentence": sentence, "assessment": assessment}
        profile = self._ask(state, questions, api_key, model)
        ratings = [
            WordRating(
                word.group(),
                word.start(),
                word.end(),
                profile.answers[f"w{number}"].yes or 0.0,
            )
            for number, word in enumerate(words, start=1)
        ]
        return ratings, profile

    def _ask(
        self,
        state: dict[str, Any],
        questions: Questions,
        api_key: str,
        model: str | None,
    ) -> Profile:
        body: dict[str, Any] = {"state": state, "questions": questions}
        if self._local and self._local.model:
            try:
                profile = read_profile(self._local.send(body), questions)
            except ProfileError:
                # it has gone since it was last looked for
                if not api_key:
                    raise
            else:
                profile.local = True
                return profile
        if not api_key:
            raise ProfileError("there is no local model and no OpenRouter key")
        body["model"] = model or self._model
        return read_profile(self._send(body, api_key), questions)


def has_words(sentence: str) -> bool:
    """Whether the sentence has words to rate, and not too many of them."""
    return 0 < len(_WORD.findall(sentence)) <= MAX_RATED_WORDS


def word_question(number: int, word: str) -> dict[str, Any]:
    """The yes-or-no question asked about the word that is the `number`th of
    its sentence. Yes means that the word is right."""
    return {
        "type": "noul",
        "instructions": (
            f'Given the `assessment` of the `sentence`, is the word "{word}"'
            f" (word {number} of the sentence) correct where it stands in the"
            " sentence? Answer yes if the word is right in spelling, form and"
            " place. Answer no if it is the word, or one of the words, that"
            " an error is in."
        ),
    }


def describe_assessment(
    questions: Questions, answers: dict[str, Answer]
) -> list[dict[str, str]]:
    """What was found out about a sentence, as each question with its answer
    in words, for a model to go by when it is asked about the sentence again."""
    assessment = []
    for name, question in questions.items():
        answer = answers.get(name)
        if answer is None:
            continue
        criteria = question["criteria"]
        if answer.choice is not None:
            # an answer may not be one the question, as it is now, offers
            meaning = (
                criteria.get(answer.choice) if isinstance(criteria, dict) else None
            )
            said = f"{answer.choice}: {meaning}" if meaning else answer.choice
        elif answer.score is not None and isinstance(criteria, list):
            level = criteria[min(len(criteria) - 1, max(0, round(answer.score)))]
            said = f"{level} ({answer.score:.1f} of {len(criteria) - 1})"
        else:
            continue
        assessment.append({"question": question["instructions"], "answer": said})
    return assessment


def read_questions(value: object) -> Questions:
    """Check questions that came in from outside. Raises ValueError saying
    what is wrong with them."""
    if not isinstance(value, dict) or len(value) > MAX_QUESTIONS:
        raise ValueError(f"questions must be an object of at most {MAX_QUESTIONS}")
    questions: Questions = {}
    for name, question in value.items():
        if not isinstance(name, str) or not name or not isinstance(question, dict):
            raise ValueError("every question needs a name and a description")
        instructions = question.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValueError(f"question {name} has no instructions")
        kind = question.get("type")
        criteria: Any = question.get("criteria")
        if kind == "choice":
            usable = isinstance(criteria, dict) and all(
                isinstance(option, str) and option and isinstance(meaning, str)
                for option, meaning in criteria.items()
            )
        elif kind == "score":
            usable = isinstance(criteria, list) and all(
                isinstance(level, str) for level in criteria
            )
        else:
            raise ValueError(f"question {name} must be a choice or a score")
        if not usable or len(criteria) < 2:
            raise ValueError(f"question {name} needs at least two options")
        questions[name] = {
            "type": kind,
            "instructions": instructions,
            "criteria": criteria,
        }
    return questions


def read_profile(
    response: dict[str, Any], questions: Questions | None = None
) -> Profile:
    """Turn a Decisions API response into a profile. `questions` are the ones
    that were asked, if not the usual ones. Raises ProfileError if an answer
    is missing or not of the kind that was asked for."""
    received = response.get("answers")
    if not isinstance(received, dict):
        raise ProfileError("the response has no answers")
    answers = {}
    for name, question in (QUESTIONS if questions is None else questions).items():
        answer = received.get(name)
        if not isinstance(answer, dict):
            raise ProfileError(f"the response has no answer for {name}")
        answers[name] = _read_answer(name, question, answer)
    usage = response.get("usage")
    if not isinstance(usage, dict):
        usage = {}
    cost = usage.get("cost")
    request_id = response.get("id")
    model = response.get("model")
    return Profile(
        answers,
        cost=cost if isinstance(cost, (int, float)) else None,
        id=request_id if isinstance(request_id, str) else str(uuid.uuid4()),
        model=model if isinstance(model, str) else "",
        input_tokens=_count(usage.get("input_tokens")),
        output_tokens=_count(usage.get("output_tokens")),
    )


def _count(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _read_answer(name: str, question: dict[str, Any], answer: dict[str, Any]) -> Answer:
    kind = question["type"]
    confidence = answer.get("confidence")
    if not isinstance(confidence, (int, float)):
        confidence = None
    if kind == "noul":
        yes = answer.get("noul")
        if not isinstance(yes, (int, float)) or isinstance(yes, bool):
            raise ProfileError(f"the answer for {name} is not a yes or a no")
        return Answer(kind, yes=min(1.0, max(0.0, float(yes))))
    if kind == "choice":
        choice = answer.get("choice")
        if choice not in question["criteria"]:
            raise ProfileError(f"the answer for {name} is not one of the options")
        best_option = list(question["criteria"])[-1]
        probabilities = answer.get("probabilities")
        best = (
            probabilities.get(best_option) if isinstance(probabilities, dict) else None
        )
        if not isinstance(best, (int, float)) or isinstance(best, bool):
            # all that is known is which option was picked
            best = 1.0 if choice == best_option else 0.0
        return Answer(
            kind, choice=choice, confidence=confidence, best=_fraction(float(best))
        )
    score = answer.get("score")
    if not isinstance(score, (int, float)):
        raise ProfileError(f"the answer for {name} is not a score")
    max_score = len(question["criteria"]) - 1
    return Answer(
        kind,
        score=float(score),
        max_score=max_score,
        confidence=confidence,
        best=_fraction(float(score) / max_score),
    )


def _fraction(value: float) -> float:
    return min(1.0, max(0.0, value))


def doubt_about(answers: dict[str, Answer]) -> float:
    """How much there is to doubt in a sentence that was given these answers,
    from 0, when every answer is the best there is, to 1. It is the answer
    furthest from the best that counts. Answers that cannot be placed leave
    everything in doubt."""
    placed = [answer.best for answer in answers.values() if answer.best is not None]
    return 1.0 - min(placed) if placed else 1.0


def weigh_ratings(ratings: list[WordRating], doubt: float) -> list[WordRating]:
    """The ratings of the words of a sentence, by how much there is to doubt
    in the sentence as a whole.

    Asked about one word at a time, the model finds fault with words of
    sentences it found nothing wrong with. So a word counts as wrong only as
    far as the sentence was found wrong: with nothing to doubt in the
    sentence, every word is right, whatever was said about it."""
    return [
        WordRating(
            rating.word, rating.start, rating.end, 1.0 - (1.0 - rating.value) * doubt
        )
        for rating in ratings
    ]
