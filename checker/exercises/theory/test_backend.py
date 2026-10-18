# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from kit import ModelError

from theory.backend import MAX_TURNS, act, finish, pages_of, start

PAGES = "# Eins\n\nDas Präfix.\n\n---\n\n# Zwei\n\n| a | b |\n|---|---|\n\n---\n"
LESSON = {
    "id": "trennbare-verben",
    "level": "A1",
    "title": "Trennbare Verben",
    "more_info": PAGES,
    "points": [
        {
            "id": "trennbar-hauptsatz",
            "role": "new",
            "title": "Separable verbs in a main clause",
            "statement": "The prefix goes to the end.",
            "when": "main clause",
        }
    ],
}
CONTEXT = {
    "language": "German",
    "into": "English",
    "level": "",
    "lesson": LESSON,
    "topics": [],
    "instances": 0,
}


class FakeModel:
    def __init__(self, reply: str = "Das Präfix geht ans **Ende**.") -> None:
        self.reply = reply
        self.asked: list[list[dict[str, Any]]] = []

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        raise ModelError("draws nothing")

    def look(self, messages: list[dict[str, Any]]) -> str:
        return self.ask(messages)

    def ask(self, messages: list[dict[str, Any]]) -> str:
        self.asked.append(messages)
        return self.reply


def test_the_pages_of_a_lesson_are_split_by_lines_of_dashes_and_empty_ones_left_out() -> (
    None
):
    assert pages_of(PAGES) == [
        "# Eins\n\nDas Präfix.",
        "# Zwei\n\n| a | b |\n|---|---|",
    ]


def test_the_theory_is_shown_from_its_first_page_without_asking_a_model() -> None:
    model = FakeModel()

    step = start(CONTEXT, model)

    assert step.show == {
        "title": "Trennbare Verben",
        "pages": pages_of(PAGES),
        "page": 0,
        "chat": [],
    }
    assert (model.asked, step.graded) == ([], [])


def test_a_lesson_without_theory_cannot_be_shown() -> None:
    context = {**CONTEXT, "lesson": {**LESSON, "more_info": " \n---\n "}}

    with pytest.raises(ModelError, match="no theory"):
        start(context, FakeModel())


def test_a_question_is_answered_with_the_lesson_and_the_page_it_is_asked_on() -> None:
    model = FakeModel()
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"question": " Warum am Ende? ", "page": 1}, model)

    system, asked = model.asked[0][0]["content"], model.asked[0][-1]["content"]
    assert "level A1" in system and "The prefix goes to the end." in system
    assert "own language is English" in system
    assert "# Eins" in system and "# Zwei" in system
    assert asked == "(I am on page 2 of 2.)\n\nWarum am Ende?"
    assert step.show["chat"] == [
        {
            "page": 1,
            "question": "Warum am Ende?",
            "answer": "Das Präfix geht ans **Ende**.",
        }
    ]
    assert step.show["page"] == 1
    assert step.graded == []


def test_a_question_is_asked_with_the_last_questions_before_it() -> None:
    model = FakeModel()
    state = start(CONTEXT, model).state
    for number in range(MAX_TURNS + 2):
        state = act(
            CONTEXT, state, {"question": f"Frage {number}", "page": 0}, model
        ).state

    last = model.asked[-1]

    assert len(last) == 1 + 2 * MAX_TURNS + 1
    assert last[1]["content"] == "Frage 1"
    assert last[-2]["role"] == "assistant"


def test_an_empty_question_asks_nothing() -> None:
    model = FakeModel()
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"question": "  ", "page": 0}, model)

    assert (model.asked, step.show["chat"]) == ([], [])


def test_finishing_keeps_how_many_questions_there_were_and_no_logs() -> None:
    model = FakeModel()
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"question": "Wieso?", "page": 0}, model).state

    step = finish(CONTEXT, state, model)

    assert (step.results, step.graded) == ({"questions": 1}, [])


def test_the_lessons_that_are_kept_have_theory_to_show() -> None:
    lessons = Path(__file__).parents[2] / "languages" / "german" / "grammar" / "lessons"
    for path in lessons.glob("*.json"):
        lesson = json.loads(path.read_text(encoding="utf-8"))
        step = start({**CONTEXT, "lesson": lesson}, FakeModel())
        assert len(step.show["pages"]) > 1, path.name
