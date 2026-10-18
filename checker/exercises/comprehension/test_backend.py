# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any

import pytest
from kit import ModelError

from comprehension.backend import act, finish, start

CONTEXT: dict[str, Any] = {
    "language": "German",
    "into": "English",
    "level": "A1",
    "lesson": {
        "id": "trennbare-verben",
        "level": "A1",
        "title": "Trennbare Verben",
        "more_info": "",
        "points": [
            {
                "id": "trennbar-hauptsatz",
                "role": "new",
                "title": "Separable verbs in a main clause",
                "statement": "The prefix goes to the end.",
                "when": "main clause",
            }
        ],
    },
    "topics": [],
    "instances": 2,
    "options": {"by": "reading", "answers": "choice", "questions": 2},
}
TEXT = {
    "title": "E-Mail",
    "shown": "",
    "text": "Liebe Maria, am Samstag mache ich eine Party um 19 Uhr.",
    "questions": [
        {
            "prompt": "Wann ist die Party?",
            "options": ["Freitag", "Samstag", "Sonntag"],
            "answer": 1,
        },
        {
            "prompt": "Um wie viel Uhr?",
            "options": ["18 Uhr", "19 Uhr", "20 Uhr"],
            "answer": 1,
        },
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


def with_options(**options: Any) -> dict[str, Any]:
    return {**CONTEXT, "options": {**CONTEXT["options"], **options}}


def test_a_text_to_read_is_shown_with_its_questions_but_not_their_answers() -> None:
    model = FakeModel(TEXT)

    step = start(CONTEXT, model)

    assert "The prefix goes to the end." in model.asked[0]
    assert step.show["text"]["text"] == TEXT["text"]
    assert step.show["questions"] == [
        {"prompt": "Wann ist die Party?", "options": ["Freitag", "Samstag", "Sonntag"]},
        {"prompt": "Um wie viel Uhr?", "options": ["18 Uhr", "19 Uhr", "20 Uhr"]},
    ]
    assert "answer" not in json.dumps(step.show["questions"])


def test_the_answers_chosen_are_checked_without_asking_a_model_and_graded_once() -> (
    None
):
    model = FakeModel(TEXT)
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": [1, 0]}, model)

    assert len(model.asked) == 1
    assert [each["result"] for each in step.show["feedback"]] == ["right", "wrong"]
    (one,) = step.graded
    assert one["result"] == "partial"
    assert one["answer"] == "1. Samstag\n2. 18 Uhr"


def test_reading_scores_the_share_of_the_questions_answered_right() -> None:
    model = FakeModel(TEXT)
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"answers": [1, None]}, model).state

    step = finish(CONTEXT, state, model)

    assert step.scores == {"reading": 50.0}


def test_listening_scores_as_hearing_and_says_how_often_the_text_may_be_heard() -> None:
    context = with_options(by="listening", plays="1")
    model = FakeModel(TEXT)

    started = start(context, model)
    state = act(context, started.state, {"answers": [1, 1]}, model).state

    assert "read aloud" in model.asked[0]
    assert (started.show["by"], started.show["plays"]) == ("listening", 1)
    assert finish(context, state, model).scores == {"listening": 100.0}


def test_statements_are_answered_richtig_or_falsch_whatever_options_the_model_gave() -> (
    None
):
    statements = {
        **TEXT,
        "questions": [
            {"prompt": "Die Party ist am Samstag.", "options": ["x"], "answer": 0}
        ],
    }

    step = start(with_options(answers="truefalse"), FakeModel(statements))

    assert step.show["questions"][0]["options"] == ["Richtig", "Falsch"]


def test_a_text_whose_questions_cannot_be_answered_is_a_failure() -> None:
    broken = {
        **TEXT,
        "questions": [{"prompt": "Wann?", "options": ["a", "b"], "answer": 5}],
    }

    with pytest.raises(ModelError, match="no question"):
        start(CONTEXT, FakeModel(broken))


def test_in_an_exam_the_part_it_is_is_followed_in_place_of_the_lesson() -> None:
    model = FakeModel(TEXT)

    start({**CONTEXT, "exam": "Exam: Goethe A1, Lesen, Teil 1."}, model)

    assert "Goethe A1, Lesen, Teil 1" in model.asked[0]
    assert "The prefix goes to the end." not in model.asked[0]
