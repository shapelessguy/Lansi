# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from profiling import QUESTIONS, Answer, Profile, ProfileError, Profiler, read_profile


def response(**changes: Any) -> dict[str, Any]:
    """What the Decisions API returns for the two questions, with changes."""
    answers: dict[str, Any] = {
        "grammar_errors": {
            "type": "choice",
            "choice": "one",
            "confidence": 0.87,
            "probabilities": {"none": 0.05, "one": 0.9, "several": 0.05},
        },
        "clarity": {
            "type": "score",
            "score": 2.6,
            "confidence": 0.7,
            "probabilities": {"0": 0, "1": 0.05, "2": 0.3, "3": 0.65},
        },
    }
    answers.update(changes)
    return {
        "id": "gen-dec-1",
        "model": "typesafe/jev-1.13",
        "answers": answers,
        "usage": {"input_tokens": 180, "output_tokens": 0, "cost": 0.0000076},
    }


def test_read_profile_gives_the_answer_to_each_question_and_what_it_used() -> None:
    assert read_profile(response()) == Profile(
        {
            "grammar_errors": Answer("choice", choice="one", confidence=0.87),
            "clarity": Answer("score", score=2.6, max_score=3, confidence=0.7),
        },
        cost=0.0000076,
        id="gen-dec-1",
        model="typesafe/jev-1.13",
        input_tokens=180,
        output_tokens=0,
    )


def test_read_profile_accepts_a_response_without_confidence_or_usage() -> None:
    reply = response(grammar_errors={"type": "choice", "choice": "none"})
    del reply["usage"]

    profile = read_profile(reply)

    assert profile.answers["grammar_errors"] == Answer("choice", choice="none")
    assert (profile.cost, profile.input_tokens, profile.output_tokens) == (None, 0, 0)


def test_read_profile_gives_each_request_its_own_id_when_none_is_sent() -> None:
    reply = response()
    del reply["id"]

    first, second = read_profile(reply), read_profile(reply)

    assert first.id and second.id
    assert first.id != second.id


@pytest.mark.parametrize(
    "broken",
    [
        {"answers": None},
        {},
        response(grammar_errors=None),
        response(grammar_errors={"type": "choice", "choice": "dozens"}),
        response(clarity={"type": "score", "score": "high"}),
        response(clarity={"type": "score"}),
    ],
)
def test_read_profile_refuses_a_response_that_does_not_answer_the_questions(
    broken: dict[str, Any],
) -> None:
    with pytest.raises(ProfileError):
        read_profile(broken)


def test_profile_sends_the_sentence_and_every_question_with_the_key() -> None:
    sent: list[tuple[dict[str, Any], str]] = []

    def send(body: dict[str, Any], api_key: str) -> dict[str, Any]:
        sent.append((body, api_key))
        return response()

    profile = Profiler("some/model", send).profile("Er ist gut.", "the-key")

    assert sent == [
        (
            {
                "model": "some/model",
                "state": {"sentence": "Er ist gut."},
                "questions": QUESTIONS,
            },
            "the-key",
        )
    ]
    assert profile.answers["grammar_errors"].choice == "one"


def test_profile_asks_the_model_it_is_given_instead_of_the_usual_one() -> None:
    asked: list[str] = []

    def send(body: dict[str, Any], api_key: str) -> dict[str, Any]:
        asked.append(body["model"])
        return response()

    profiler = Profiler("usual/model", send)
    profiler.profile("Er ist gut.", "the-key", "other/model")
    profiler.profile("Er ist gut.", "the-key", None)

    assert asked == ["other/model", "usual/model"]


def test_the_questions_offer_none_one_or_several_errors_and_a_clarity_scale() -> None:
    assert QUESTIONS["grammar_errors"]["type"] == "choice"
    assert list(QUESTIONS["grammar_errors"]["criteria"]) == ["none", "one", "several"]
    assert QUESTIONS["clarity"]["type"] == "score"
    assert len(QUESTIONS["clarity"]["criteria"]) == 4
