# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Builds a profile of a sentence by asking Jev a series of questions about it.

Jev is a decision model: it is given a text and typed questions, and answers
each with one of the options it was offered rather than with text of its own.
It is called through OpenRouter's Decisions API.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
TIMEOUT_SECS = 30

# The questions asked about every sentence. A "choice" question is answered
# with one of the named options, and a "score" question with a place on the
# scale, counted from 0 for the first level.
QUESTIONS: dict[str, dict[str, Any]] = {
    "grammar_errors": {
        "type": "choice",
        "instructions": (
            "How many grammar errors does the sentence have? Judge it by the"
            " rules of the language it is written in. Count mistakes in"
            " grammar only, such as word order, agreement, case, tense and"
            " missing or extra words. Do not count spelling or punctuation."
        ),
        "criteria": {
            "none": "The sentence has no grammar errors.",
            "one": "The sentence has exactly one grammar error.",
            "several": "The sentence has two or more grammar errors.",
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

    # "choice" or "score"
    kind: str
    # The option picked, for a choice question.
    choice: str | None = None
    # The place on the scale, for a score question. It can fall between two
    # levels: 2.5 is halfway between the third and the fourth.
    score: float | None = None
    # The highest place on the scale, for a score question.
    max_score: int | None = None
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


class ProfileError(Exception):
    """A profile could not be made. The message says why."""


# Sends a request body with an API key and returns the decoded response.
Transport = Callable[[dict[str, Any], str], dict[str, Any]]


def send_to_openrouter(body: dict[str, Any], api_key: str) -> dict[str, Any]:
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
            decoded: dict[str, Any] = json.load(response)
            return decoded
    except urllib.error.HTTPError as error:
        raise ProfileError(_error_message(error)) from None
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise ProfileError(f"could not reach OpenRouter: {error}") from None


def _error_message(error: urllib.error.HTTPError) -> str:
    """The reason OpenRouter gave for refusing, or the status if it gave none."""
    try:
        message = json.load(error)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = error.reason
    return f"OpenRouter refused the request ({error.code}): {message}"


class Profiler:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        send: Transport = send_to_openrouter,
    ) -> None:
        self._model = model
        self._send = send

    def profile(self, sentence: str, api_key: str, model: str | None = None) -> Profile:
        """Ask the questions about `sentence`, of `model` if one is given
        rather than the usual one. Raises ProfileError."""
        body = {
            "model": model or self._model,
            "state": {"sentence": sentence},
            "questions": QUESTIONS,
        }
        return read_profile(self._send(body, api_key))


def read_profile(response: dict[str, Any]) -> Profile:
    """Turn a Decisions API response into a profile. Raises ProfileError if an
    answer is missing or not of the kind that was asked for."""
    received = response.get("answers")
    if not isinstance(received, dict):
        raise ProfileError("the response has no answers")
    answers = {}
    for name, question in QUESTIONS.items():
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
    if kind == "choice":
        choice = answer.get("choice")
        if choice not in question["criteria"]:
            raise ProfileError(f"the answer for {name} is not one of the options")
        return Answer(kind, choice=choice, confidence=confidence)
    score = answer.get("score")
    if not isinstance(score, (int, float)):
        raise ProfileError(f"the answer for {name} is not a score")
    return Answer(
        kind,
        score=float(score),
        max_score=len(question["criteria"]) - 1,
        confidence=confidence,
    )
