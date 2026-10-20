# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any

import pytest
from kit import ModelError

from correcting.backend import act, finish, markdown_of, read_parts, start

TEXT = "Am Samstag bin ich ins Kino gegeht.\nDer Film war gut."
CONTEXT: dict[str, Any] = {
    "language": "German",
    "into": "English",
    "level": "A2",
    "lesson": {"id": "", "level": "A2", "title": "A2", "more_info": "", "points": []},
    "topics": [],
    "instances": 1,
    "options": {"text": "t1"},
    "texts": {"text": {"id": "t1", "title": "Wochenende", "content": TEXT}},
}
MARKED = {
    "parts": [
        {"text": "Am Samstag bin ich ins Kino "},
        {
            "wrong": "gegeht",
            "right": "gegangen",
            "why": "gehen has an irregular participle",
        },
        {"text": "."},
        {"text": "\nDer Film war gut."},
    ],
    "summary": "Learn the participles of irregular verbs.",
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


def test_the_text_chosen_is_corrected_as_the_exercise_starts() -> None:
    model = FakeModel(MARKED)

    step = start(CONTEXT, model)

    assert step.show["title"] == "Wochenende"
    assert step.show["parts"] == [
        {"text": "Am Samstag bin ich ins Kino "},
        {
            "wrong": "gegeht",
            "right": "gegangen",
            "why": "gehen has an irregular participle",
        },
        {"text": ".\nDer Film war gut."},
    ]
    [graded] = step.graded
    assert (graded["result"], graded["answer"]) == ("partial", TEXT)
    assert (
        graded["correction"]
        == "Am Samstag bin ich ins Kino gegangen.\nDer Film war gut."
    )
    assert graded["note"] == "gegeht → gegangen: gehen has an irregular participle"
    assert step.written == {
        "user": [TEXT],
        "assistant": ["Am Samstag bin ich ins Kino gegangen.\nDer Film war gut."],
    }
    assert "Wochenende" in model.asked[0] and TEXT in model.asked[0]


@pytest.mark.parametrize(
    "texts",
    [{}, {"text": {"id": "t1", "title": "Leer", "content": "  "}}],
)
def test_without_a_text_to_correct_the_exercise_cannot_start(
    texts: dict[str, Any],
) -> None:
    with pytest.raises(ModelError):
        start({**CONTEXT, "texts": texts}, FakeModel())


def test_there_is_nothing_to_act_on() -> None:
    state = start(CONTEXT, FakeModel(MARKED)).state

    step = act(CONTEXT, state, {"text": "Something else."}, FakeModel())

    assert (step.graded, step.show["parts"]) == ([], state["parts"])


def test_the_text_the_model_wrote_out_is_taken_though_it_differs_a_little() -> None:
    # the model wrote the line break as a space, and quoted the text otherwise
    written = {
        "parts": [
            {"text": "Am Samstag bin ich ins Kino "},
            {"wrong": "gegeht", "right": "gegangen", "why": "irregular"},
            {"text": ". Der Film war gut."},
        ]
    }

    step = start(CONTEXT, FakeModel(written))

    assert step.show["parts"][-1] == {"text": ". Der Film war gut."}
    # what the learner wrote is what is graded, as they wrote it
    assert step.graded[0]["answer"] == TEXT


def test_a_reply_with_no_text_is_asked_for_again_then_given_up() -> None:
    model = FakeModel({"parts": []}, MARKED)

    step = start(CONTEXT, model)

    assert len(model.asked) == 2 and step.graded[0]["result"] == "partial"
    with pytest.raises(ModelError):
        start(CONTEXT, FakeModel({"summary": "?"}, {"parts": [7]}))


def test_a_text_with_no_mistake_is_right() -> None:
    step = start(
        CONTEXT, FakeModel({"parts": [{"text": TEXT}], "summary": "All right."})
    )

    assert step.graded[0]["result"] == "right"
    assert step.written["assistant"] == []


def test_once_over_the_text_and_its_marked_copy_are_what_it_came_to() -> None:
    model = FakeModel(MARKED)

    step = finish(CONTEXT, start(CONTEXT, model).state, model)

    assert step.results["texts"]["text"]["content"] == TEXT
    # the text alone, with its corrections and their comments worked in
    assert step.results["texts"]["text"]["correction"] == (
        "Am Samstag bin ich ins Kino ~~gegeht~~ **gegangen**"
        " _(gehen has an irregular participle)_.\nDer Film war gut.\n"
    )


def test_a_word_to_add_or_to_leave_out_is_marked_with_its_comment() -> None:
    parts = read_parts(
        {
            "parts": [
                {"text": "Ich habe"},
                {"wrong": "", "right": " ein", "why": "an article is missing"},
                {"text": " Hund"},
                {"wrong": " sehr", "right": "", "why": "one word too many"},
                {"text": "."},
            ]
        }
    )

    assert parts is not None
    assert markdown_of(parts) == (
        "Ich habe **ein** _(an article is missing)_ Hund ~~sehr~~ _(one word too many)_.\n"
    )
