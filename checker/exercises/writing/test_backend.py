# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any

import pytest
from kit import ModelError

from writing.backend import act, finish, start

CONTEXT: dict[str, Any] = {
    "language": "German",
    "into": "English",
    "level": "A1",
    "lesson": {"id": "", "level": "A1", "title": "A1", "more_info": "", "points": []},
    "topics": [],
    "instances": 2,
    "options": {"kind": "email", "words": 30},
}
TASK = {
    "situation": "Sie können morgen nicht zum Kurs kommen. Schreiben Sie Frau Schmidt.",
    "points": [
        "Warum?",
        "Wann sind Sie wieder da?",
        "Fragen Sie nach den Hausaufgaben.",
    ],
}
RATED = {
    "ratings": {"task": 4, "coherence": 3, "vocabulary": 3, "structures": 2},
    "correction": "Liebe Frau Schmidt, ich bin krank.",
    "note": "The verb is second.",
}
FORM = {
    "text": "Herr Novak möchte für zwei Personen einen Kurs buchen.",
    "fields": [
        {"label": "Familienname:", "answer": "Novak"},
        {"label": "Personen:", "answer": "2"},
    ],
}


class FakeModel:
    """Replies with each of `replies` in turn, as JSON."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.asked: list[str] = []

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        raise ModelError("draws nothing")

    def look(self, messages: list[dict[str, Any]]) -> str:
        return self.ask(messages)

    def ask(self, messages: list[dict[str, Any]]) -> str:
        self.asked.append(messages[-1]["content"])
        return json.dumps(self.replies.pop(0))


def test_what_was_written_is_rated_by_the_criteria_and_graded_by_the_ratings() -> None:
    model = FakeModel(TASK, RATED)
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"text": "Liebe Frau Schmidt, ich krank bin."}, model)

    assert "About 30 words are asked for; the learner wrote 6 words" in model.asked[1]
    assert step.show["feedback"]["ratings"] == RATED["ratings"]
    (one,) = step.graded
    assert one["result"] == "right"
    assert one["answer"] == "Liebe Frau Schmidt, ich krank bin."
    assert one["correction"] == RATED["correction"]


def test_writing_scores_the_ratings_as_shares_of_the_most_by_each_criterion() -> None:
    model = FakeModel(TASK, RATED)
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"text": "Liebe Frau Schmidt"}, model).state

    step = finish(CONTEXT, state, model)

    assert step.scores == {
        "writing": 75.0,
        "task": 100.0,
        "coherence": 75.0,
        "vocabulary": 75.0,
        "structures": 50.0,
    }


def test_a_rating_without_every_criterion_is_a_failure() -> None:
    model = FakeModel(TASK, {"ratings": {"task": 4}})
    state = start(CONTEXT, model).state

    with pytest.raises(ModelError, match="did not rate"):
        act(CONTEXT, state, {"text": "Hallo"}, model)


def test_a_form_takes_what_the_text_says_as_it_is_without_asking_a_model() -> None:
    context = {**CONTEXT, "options": {"kind": "form"}}
    model = FakeModel(FORM)
    started = start(context, model)

    step = act(context, started.state, {"fields": ["novak", ""]}, model)

    assert started.show["task"]["fields"] == ["Familienname:", "Personen:"]
    assert "answer" not in json.dumps(started.show)
    assert [each["result"] for each in step.show["feedback"]["fields"]] == [
        "right",
        "wrong",
    ]
    assert len(model.asked) == 1
    assert finish(context, step.state, model).scores == {"writing": 50.0}
