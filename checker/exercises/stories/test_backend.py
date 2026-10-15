# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any

import pytest
from kit import ModelError

from stories.backend import act, finish, start

CONTEXT: dict[str, Any] = {
    "language": "German",
    "into": "English",
    "level": "A2",
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
    "topics": [{"title": "Beim Arzt", "description": "symptoms and appointments"}],
    "instances": 2,
    "options": {"then": "questions"},
}
STORY = {
    "title": "Ein langer Morgen",
    "text": "Anna steht um sechs auf.\n\nSie ruft den Arzt an.",
    "questions": [
        {"question": "Wann steht Anna auf?", "answer": "Um sechs."},
        {"question": "Wen ruft sie an?", "answer": "Den Arzt."},
    ],
}
RIGHT = {"result": "right", "correction": "", "note": ""}


def with_mode(mode: str) -> dict[str, Any]:
    return {**CONTEXT, "options": {"then": mode}}


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


def test_a_story_with_questions_is_written_for_the_lesson_the_topic_and_the_level() -> (
    None
):
    model = FakeModel(STORY)

    step = start(CONTEXT, model)

    (prompt,) = model.asked
    assert "about 120 words" in prompt
    assert "The prefix goes to the end." in prompt
    assert "Beim Arzt" in prompt
    assert "questions" in prompt
    assert step.show["story"] == {"title": STORY["title"], "text": STORY["text"]}
    assert step.show["questions"] == ["Wann steht Anna auf?", "Wen ruft sie an?"]
    assert (step.show["at"], step.show["total"], step.show["mode"]) == (
        0,
        2,
        "questions",
    )


def test_the_story_and_its_questions_are_written_by_the_model_when_shown() -> None:
    step = start(CONTEXT, FakeModel(STORY))

    assert step.written == {
        "user": [],
        "assistant": [STORY["text"], "Wann steht Anna auf?", "Wen ruft sie an?"],
    }


def test_a_story_to_retell_or_to_read_is_written_without_questions() -> None:
    model = FakeModel({"title": "T", "text": "Anna steht auf."})

    step = start(with_mode("retell"), model)

    assert "questions" not in model.asked[0]
    assert "questions" not in step.show


def test_a_story_with_no_question_where_there_are_to_be_some_is_a_failure() -> None:
    with pytest.raises(ModelError, match="no question"):
        start(CONTEXT, FakeModel({"title": "T", "text": "Anna steht auf."}))


def test_the_answers_are_judged_together_and_logged_once_with_what_was_written() -> (
    None
):
    wrong = {"result": "wrong", "correction": "Um sechs.", "note": "Read again."}
    model = FakeModel(STORY, {"verdicts": [wrong]})
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": ["Um  sieben.", ""]}, model)

    assert step.logs == [
        {
            "result": "wrong",
            "answer": "Um sieben. / ",
            "correction": "Um sechs. / Den Arzt.",
            "note": "1. Read again.",
        }
    ]
    # what was left empty is wrong, and is not sent to be judged
    assert "Wen ruft sie an?" not in model.asked[1]
    assert "Learner: Um sieben." in model.asked[1]
    assert step.written == {
        "user": ["Um sieben."],
        "assistant": ["Um sechs.", "Den Arzt."],
    }
    assert [each["result"] for each in step.show["feedback"]] == ["wrong", "wrong"]
    assert (step.show["more"], step.show["prepared"]) == (True, False)


def test_a_story_with_nothing_answered_is_not_judged() -> None:
    model = FakeModel(STORY)
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": ["", " "]}, model)

    assert step.logs == [] and "feedback" not in step.show
    assert len(model.asked) == 1


def test_a_retelling_is_judged_and_logged_with_its_correction() -> None:
    context = with_mode("retell")
    verdict = {"result": "partial", "correction": "Anna steht auf.", "note": "n"}
    model = FakeModel({"title": "T", "text": "Anna steht auf."}, verdict)
    state = start(context, model).state

    step = act(context, state, {"retelling": " Anna aufsteht. "}, model)

    assert step.logs == [
        {
            "result": "partial",
            "answer": "Anna aufsteht.",
            "correction": "Anna steht auf.",
            "note": "n",
        }
    ]
    assert step.written == {
        "user": ["Anna aufsteht."],
        "assistant": ["Anna steht auf."],
    }


def test_a_story_that_is_only_read_logs_nothing() -> None:
    context = with_mode("read")
    model = FakeModel({"title": "T", "text": "Anna steht auf."})
    state = start(context, model).state

    step = act(context, state, {"read": True}, model)

    assert step.logs == []
    assert step.show["feedback"] == [] and step.show["more"] is True


def test_the_next_story_is_written_once_other_than_those_before_and_told_once() -> None:
    second = {**STORY, "title": "Beim Zahnarzt", "text": "Ben kommt mit."}
    model = FakeModel(STORY, {"verdicts": [RIGHT, RIGHT]}, second)
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"answers": ["Um sechs.", "Den Arzt."]}, model).state

    prepared = act(CONTEXT, state, {"prepare": True}, model)
    shown = act(CONTEXT, prepared.state, {"next": True}, model)
    again = act(CONTEXT, shown.state, {"answers": []}, model)

    assert len(model.asked) == 3
    assert "Ein langer Morgen" in model.asked[2]
    assert prepared.written == {}
    assert shown.written["assistant"][0] == "Ben kommt mit."
    assert shown.show["story"]["title"] == "Beim Zahnarzt"
    assert again.written == {}


def test_what_was_done_is_in_the_results_however_far_it_got() -> None:
    model = FakeModel(STORY, {"verdicts": [RIGHT, RIGHT]})
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"answers": ["Um sechs.", "Den Arzt."]}, model).state

    results = finish(CONTEXT, state, model).results

    assert results["mode"] == "questions" and results["total"] == 2
    (done,) = results["stories"]
    assert done["story"]["title"] == "Ein langer Morgen"
    assert done["result"] == "right"
