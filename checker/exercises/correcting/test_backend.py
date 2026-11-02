# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any

import pytest
from kit import ModelError

from correcting.backend import (
    CHANGES,
    act,
    applied,
    finish,
    read_corrections,
    start,
)

TEXT = "Am Samstag bin ich ins Kino gegeht.\nDer Film war gut."
WORDS = TEXT.split()
CONTEXT: dict[str, Any] = {
    "language": "German",
    "into": "English",
    "level": "A2",
    "lesson": {"id": "", "level": "A2", "title": "A2", "more_info": "", "points": []},
    "topics": [],
    "instances": 1,
    "options": {"text": "t1"},
    "texts": {
        "text": {
            "id": "t1",
            "title": "Wochenende",
            "content": TEXT,
            "handwritten": False,
            "words": WORDS,
        }
    },
}
PARTICIPLE = {
    "type": "replace",
    "from_id": 6,
    "to_id": 6,
    "text": "gegangen.",
    "category": "participle",
    "explanation": "gehen has an irregular participle",
}
CORRECTED = {
    "corrections": [PARTICIPLE],
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
    model = FakeModel(CORRECTED)

    step = start(CONTEXT, model)

    assert step.show["title"] == "Wochenende"
    assert step.show["words"] == WORDS
    assert step.show["corrections"] == [PARTICIPLE]
    [graded] = step.graded
    assert graded["result"] == "partial"
    assert graded["answer"] == " ".join(WORDS)
    assert (
        graded["correction"]
        == "Am Samstag bin ich ins Kino gegangen. Der Film war gut."
    )
    assert graded["note"] == "gegeht. → gegangen.: gehen has an irregular participle"
    assert step.written["assistant"] == [graded["correction"]]
    # the model is told each word by its id
    assert '"6": "gegeht."' in model.asked[0] and "Wochenende" in model.asked[0]


def test_a_typed_text_is_told_to_have_no_misreadings_and_a_handwritten_one_may() -> (
    None
):
    typed = FakeModel(CORRECTED)
    start(CONTEXT, typed)
    texts = {"text": {**CONTEXT["texts"]["text"], "handwritten": True}}
    handwritten = FakeModel(CORRECTED)
    start({**CONTEXT, "texts": texts}, handwritten)

    assert "do not use misread" in typed.asked[0]
    assert "read wrong" in handwritten.asked[0]
    assert "do not use misread" not in handwritten.asked[0]


@pytest.mark.parametrize(
    "texts",
    [{}, {"text": {"id": "t1", "title": "Leer", "content": "  ", "words": []}}],
)
def test_without_a_text_to_correct_the_exercise_cannot_start(
    texts: dict[str, Any],
) -> None:
    with pytest.raises(ModelError):
        start({**CONTEXT, "texts": texts}, FakeModel())


def test_there_is_nothing_to_act_on() -> None:
    state = start(CONTEXT, FakeModel(CORRECTED)).state

    step = act(CONTEXT, state, {"text": "Something else."}, FakeModel())

    assert (step.graded, step.show["corrections"]) == ([], state["corrections"])


def test_a_reply_with_no_corrections_is_asked_for_again_then_given_up() -> None:
    model = FakeModel({"summary": "?"}, CORRECTED)

    step = start(CONTEXT, model)

    assert len(model.asked) == 2 and step.graded[0]["result"] == "partial"
    with pytest.raises(ModelError):
        start(CONTEXT, FakeModel({"summary": "?"}, {"corrections": "none"}))


def test_a_text_with_no_mistake_is_right_though_it_is_praised() -> None:
    praised = {"type": "praise", "from_id": 0, "to_id": 1, "text": "Good."}

    step = start(CONTEXT, FakeModel({"corrections": [praised], "summary": "Right."}))

    assert step.graded[0]["result"] == "right"
    assert step.written["assistant"] == []


def test_corrections_that_are_not_what_a_function_takes_are_left_out() -> None:
    read = read_corrections(
        {
            "corrections": [
                {"type": "replace", "from_id": 2, "to_id": 1, "text": "x"},
                {"type": "replace", "from_id": 0, "to_id": 99, "text": "x"},
                {"type": "insert", "after_id": -2, "text": "x"},
                {"type": "split", "id": 3},
                {"type": "shout", "from_id": 0, "to_id": 0},
                {"type": "erase", "from_id": True, "to_id": 1},
                "erase",
                {"type": "insert", "after_id": -1, "text": " Heute "},
                {"type": "illegible", "from_id": 4, "to_id": 4, "explanation": "?"},
            ]
        },
        9,
    )

    assert read == [
        {"type": "insert", "after_id": -1, "text": "Heute"},
        {"type": "illegible", "from_id": 4, "to_id": 4},
    ]


def test_a_word_is_not_changed_twice() -> None:
    read = read_corrections(
        {
            "corrections": [
                {"type": "replace", "from_id": 1, "to_id": 2, "text": "a"},
                {"type": "erase", "from_id": 2, "to_id": 3},
                {"type": "comment", "from_id": 2, "to_id": 2, "text": "note"},
            ]
        },
        5,
    )

    assert [each["type"] for each in read or []] == ["replace", "comment"]


def test_a_correction_whose_ids_are_a_few_words_off_is_put_on_the_words_it_names() -> (
    None
):
    words = ["che", "il", "mio", "era", "il", "più", "buono"]
    read = read_corrections(
        {
            "corrections": [
                # one word late, as a model may miscount
                {
                    "type": "replace",
                    "from_id": 3,
                    "to_id": 3,
                    "was": "mio",
                    "text": "x",
                },
                {"type": "insert", "after_id": 5, "after": "il", "text": "y"},
                {"type": "split", "id": 6, "was": "più", "text": "p iù"},
                # nowhere near the words it names
                {"type": "erase", "from_id": 0, "to_id": 0, "was": "buono"},
            ]
        },
        len(words),
        words,
    )

    assert read == [
        {"type": "replace", "from_id": 2, "to_id": 2, "text": "x"},
        {"type": "insert", "after_id": 4, "text": "y"},
        {"type": "split", "id": 5, "text": "p iù"},
    ]


def test_a_replacement_that_only_parts_or_joins_words_is_a_split_or_a_join() -> None:
    words = ["Unabbraccio,", "In", "vece", "del"]
    read = read_corrections(
        {
            "corrections": [
                {"type": "replace", "from_id": 0, "to_id": 0, "text": "Un abbraccio,"},
                {"type": "replace", "from_id": 1, "to_id": 2, "text": "Invece"},
                {"type": "replace", "from_id": 3, "to_id": 3, "text": "dal"},
            ]
        },
        len(words),
        words,
    )

    assert read == [
        {"type": "split", "id": 0, "text": "Un abbraccio,"},
        {"type": "join", "from_id": 1, "to_id": 2, "text": "Invece"},
        {"type": "replace", "from_id": 3, "to_id": 3, "text": "dal"},
    ]


def test_a_replacement_that_only_adds_words_is_an_insertion() -> None:
    words = ["tornati", "casa", "perché"]
    read = read_corrections(
        {
            "corrections": [
                {"type": "replace", "from_id": 1, "to_id": 1, "text": "a casa"},
                {"type": "replace", "from_id": 2, "to_id": 2, "text": "perché non"},
            ]
        },
        len(words),
        words,
    )

    assert read == [
        {"type": "insert", "after_id": 0, "text": "a"},
        {"type": "insert", "after_id": 2, "text": "non"},
    ]


def test_the_corrections_are_done_to_the_words_the_moved_ones_last() -> None:
    words = ["Ich", "habe", "gestern", "Hund", "sehr", "gesehen", "ein"]
    corrections = [
        {"type": "erase", "from_id": 4, "to_id": 4},
        {"type": "move", "from_id": 6, "to_id": 6, "after_id": 2},
        {"type": "insert", "after_id": -1, "text": "Ja,"},
        {"type": "replace", "from_id": 5, "to_id": 5, "text": "gesehen."},
        {"type": "suggest", "from_id": 0, "to_id": 1, "text": "Wir haben"},
    ]

    assert (
        applied(words, corrections, CHANGES) == "Ja, Ich habe gestern ein Hund gesehen."
    )


def test_once_over_the_text_and_its_corrections_are_what_it_came_to() -> None:
    model = FakeModel(CORRECTED)

    step = finish(CONTEXT, start(CONTEXT, model).state, model)

    assert step.results["texts"]["text"]["content"] == TEXT
    assert json.loads(step.results["texts"]["text"]["correction"]) == {
        "words": WORDS,
        "corrections": [PARTICIPLE],
        "summary": "Learn the participles of irregular verbs.",
    }
    assert step.results["mistakes"] == 1
