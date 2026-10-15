# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

import pytest
from kit import ModelError
from PIL import Image

from picture.backend import (
    SHOWN_WORDS,
    act,
    describe_words,
    finish,
    marked,
    read_judgements,
    read_points,
    start,
)

CONTEXT = {
    "language": "German",
    "into": "English",
    "level": "A1",
    "lesson": {"id": "l", "level": "A1", "title": "L", "more_info": "", "points": []},
    "topics": [{"title": "Zu Hause", "description": ""}],
    "words": {"mode": "prefer", "lemmas": ["Tisch", "Lampe"]},
    "instances": 2,
}


def picture_of(width: int = 400, height: int = 300) -> str:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (200, 220, 240)).save(out, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


IMAGE = picture_of()


def plan(*things: str) -> dict[str, Any]:
    return {"scene": "A kitchen.", "things": list(things)}


def box(n: int, x: int, y: int) -> dict[str, Any]:
    return {"n": n, "box_2d": [y - 20, x - 20, y + 20, x + 20]}


def verdict(n: int, result: str, correct: str = "", note: str = "") -> dict[str, Any]:
    return {
        "n": n,
        "result": result,
        "correct": correct,
        "note": note,
        "translation": "",
    }


class FakeModel:
    """Plans, draws, finds and judges as it is told to, one reply after
    another, and keeps what it was asked."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.asked: list[list[dict[str, Any]]] = []
        self.drawn: list[tuple[str, str]] = []
        # which of the asks were looks, by where they are among them
        self.looked: list[int] = []

    def ask(self, messages: list[dict[str, Any]]) -> str:
        self.asked.append(messages)
        return json.dumps(self.replies.pop(0))

    def look(self, messages: list[dict[str, Any]]) -> str:
        self.looked.append(len(self.asked))
        return self.ask(messages)

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        self.drawn.append((prompt, aspect_ratio))
        return IMAGE


TABLE = {"thing": "a wooden table"}
LAMP = {"thing": "a tall lamp"}


def test_the_points_are_those_found_apart() -> None:
    items = [{"thing": str(number)} for number in range(5)]
    reply = {
        "boxes": [
            box(1, 100, 100),
            # too near the first
            box(2, 120, 110),
            {"n": 3, "box_2d": [80, 1180, 120, 1220]},
            box(4, 500, 500),
            box(5, 800, 800),
        ]
    }

    found = read_points(reply, items)

    assert [(item["thing"], item["x"], item["y"]) for item in found] == [
        ("0", 100, 100),
        ("3", 500, 500),
        ("4", 800, 800),
    ]


def test_a_picture_on_which_nothing_is_found_is_a_failure_that_says_what_was_said() -> (
    None
):
    with pytest.raises(ModelError, match=re.escape('"boxes": []')):
        read_points({"boxes": []}, [TABLE])


@pytest.mark.parametrize(
    "reply",
    [
        {"boxes": [{"n": 2, "box_2d": [100, 200, 300, 400]}]},
        [{"label": "a tall lamp", "box_2d": [100, 200, 300, 400]}],
        [{"label": "2", "box_2d": [100, 200, 300, 400]}],
        {"objects": [{"name": "lamp", "bbox": [100, 200, 300, 400]}]},
        [{"label": "lamp", "point": [200, 300]}],
        [{"n": "2", "box_2d": [0.1, 0.2, 0.3, 0.4]}],
        [{"n": 2, "x": 300, "y": 200}],
    ],
)
def test_the_things_are_read_in_whatever_shape_the_model_gives_them(
    reply: Any,
) -> None:
    found = read_points(reply, [TABLE, LAMP])

    assert [(item["thing"], item["x"], item["y"]) for item in found] == [
        ("a tall lamp", 300, 200)
    ]


def test_a_picture_is_planned_with_the_learners_words_drawn_and_its_things_found() -> (
    None
):
    model = FakeModel(
        plan("a table", "a chair", "a stove"),
        {"boxes": [box(1, 200, 300), box(3, 700, 600)]},
    )

    step = start(CONTEXT, model)

    assert step.show["image"] == IMAGE
    assert step.show["points"] == [
        {"x": 200, "y": 300, "label": "", "feedback": None},
        {"x": 700, "y": 600, "label": "", "feedback": None},
    ]
    assert (step.show["picture"], step.show["pictures"]) == (1, 2)
    planning = model.asked[0][0]["content"]
    assert "Zu Hause" in planning and "Tisch, Lampe" in planning
    ((prompt, aspect_ratio),) = model.drawn
    assert "a table, a chair, a stove" in prompt and aspect_ratio == "4:3"
    assert model.looked == [1]
    shown = model.asked[1][0]["content"]
    assert shown[1] == {"type": "image_url", "image_url": {"url": IMAGE}}
    assert "3. a stove" in shown[0]["text"]


def test_finding_the_things_is_asked_again_rather_than_drawing_again() -> None:
    model = FakeModel(
        plan("a table", "a chair"), {"no": "points"}, {"boxes": [box(2, 700, 600)]}
    )

    step = start(CONTEXT, model)

    assert len(model.drawn) == 1
    assert [(point["x"], point["y"]) for point in step.show["points"]] == [(700, 600)]


def test_a_picture_whose_things_are_not_found_is_kept_to_be_looked_at_again() -> None:
    model = FakeModel(
        plan("a table"),
        {"boxes": []},
        {"boxes": []},
        {"boxes": [{"n": 1, "box_2d": [100, 200, 300, 400]}]},
    )

    lost = start(CONTEXT, model)
    found = act(CONTEXT, lost.state, {"look": True}, model)

    assert lost.show["image"] == IMAGE and lost.show["points"] == []
    assert lost.show["lost"].startswith("finding the things in the picture")
    assert found.show["lost"] == ""
    assert [(point["x"], point["y"]) for point in found.show["points"]] == [(300, 200)]
    assert len(model.drawn) == 1


def started(*things: str) -> tuple[FakeModel, Any]:
    """A picture with a point on each of `things`, and the model, which is to
    be told what it replies next."""
    model = FakeModel(
        plan(*things),
        {"boxes": [box(n, 100 + 200 * n, 500) for n in range(1, len(things) + 1)]},
    )
    return model, start(CONTEXT, model).state


def test_labels_may_be_changed_and_nothing_is_logged_until_they_are_checked() -> None:
    model, state = started("a table", "a trophy")

    first = act(CONTEXT, state, {"point": 0, "label": " der  Tisch "}, model)
    changed = act(CONTEXT, first.state, {"point": 0, "label": "Tisch"}, model)

    assert first.logs == [] and changed.logs == []
    assert [point["label"] for point in changed.show["points"]] == ["Tisch", ""]
    assert changed.show["judged"] is False and model.looked == [1]


def test_the_labels_are_judged_on_the_marked_picture_and_each_point_is_logged() -> None:
    model, state = started("a table", "a silver trophy", "a plant")
    state = act(CONTEXT, state, {"point": 0, "label": "Der Tisch"}, model).state
    state = act(CONTEXT, state, {"point": 1, "label": "der Preis"}, model).state
    model.replies.append(
        {
            "labels": [
                verdict(1, "right", "der Tisch"),
                verdict(2, "wrong", "der Pokal", "Preis is a prize."),
                verdict(3, "partial", "die Pflanze"),
            ]
        }
    )

    checked = act(CONTEXT, state, {"check": True}, model)

    assert checked.logs == [
        {"result": "right", "answer": "Der Tisch", "correction": "", "note": ""},
        {
            "result": "wrong",
            "answer": "der Preis",
            "correction": "der Pokal",
            "note": "Preis is a prize.",
        },
        # a point left blank is not known, whatever the judge says
        {"result": "wrong", "answer": "", "correction": "die Pflanze", "note": ""},
    ]
    judging = model.asked[-1][0]["content"]
    assert (
        '2. "der Preis" (the illustrator meant: a silver trophy)' in judging[0]["text"]
    )
    assert "3. (nothing)" in judging[0]["text"]
    assert judging[1]["image_url"]["url"] != IMAGE
    assert model.looked[-1] == len(model.asked) - 1
    assert checked.show["judged"] is True and checked.show["more"] is True
    assert checked.show["points"][0]["feedback"]["correct"] == "Der Tisch"
    # once checked, the labels stay as they were judged
    again = act(CONTEXT, checked.state, {"point": 1, "label": "der Pokal"}, model)
    assert again.show["points"][1]["label"] == "der Preis"


def test_once_the_labels_are_judged_they_and_what_was_not_right_are_written() -> None:
    model, state = started("a table", "a silver trophy", "a plant")
    state = act(CONTEXT, state, {"point": 0, "label": "Der Tisch"}, model).state
    state = act(CONTEXT, state, {"point": 1, "label": "der Preis"}, model).state
    model.replies.append(
        {
            "labels": [
                verdict(1, "right", "der Tisch"),
                verdict(2, "wrong", "der Pokal"),
                verdict(3, "partial", "die Pflanze"),
            ]
        }
    )

    checked = act(CONTEXT, state, {"check": True}, model)

    assert checked.written == {
        "user": ["Der Tisch", "der Preis"],
        "assistant": ["der Pokal", "die Pflanze"],
    }


def test_a_judge_that_leaves_a_label_out_is_a_failure() -> None:
    with pytest.raises(ModelError, match="every label"):
        read_judgements({"labels": [verdict(1, "right")]}, 2)


def test_judgements_are_read_in_whatever_shape_the_model_gives_them() -> None:
    reply = [{"marker": "2", "result": "wrong"}, {"number": 1, "result": "right"}]

    judged = read_judgements(reply, 2)

    assert [each["result"] for each in judged] == ["right", "wrong"]


def test_the_judge_is_shown_a_numbered_mark_on_each_point() -> None:
    picture = marked(IMAGE, [{"x": 500, "y": 500}])

    image = Image.open(io.BytesIO(base64.b64decode(picture.split(",", 1)[1])))
    pixel = image.convert("RGB").getpixel((200 - 6, 150))
    assert isinstance(pixel, tuple)
    red, green, blue = pixel
    assert red > 150 and green < 100 and blue < 120


def test_the_next_picture_is_of_another_scene_without_what_was_drawn_before() -> None:
    model, state = started("a table", "a chair")
    state = act(CONTEXT, state, {"point": 0, "label": "der Tisch"}, model).state
    model.replies += [
        {"labels": [verdict(1, "right"), verdict(2, "wrong", "der Stuhl")]},
        plan("a stove"),
        {"boxes": [box(1, 500, 500)]},
    ]
    state = act(CONTEXT, state, {"check": True}, model).state

    following = act(CONTEXT, state, {"next": True}, model)

    planning = model.asked[3][0]["content"]
    assert "clearly different from all of them: A kitchen." in planning
    assert "a table; a chair" in planning
    assert following.show["points"] == [
        {"x": 500, "y": 500, "label": "", "feedback": None}
    ]
    assert (following.show["picture"], following.show["more"]) == (2, False)


def test_labels_not_checked_are_judged_when_the_exercise_is_left() -> None:
    model, state = started("a table", "a chair")
    state = act(CONTEXT, state, {"point": 1, "label": "der Hund"}, model).state
    model.replies.append(
        {"labels": [verdict(1, "wrong", "der Tisch"), verdict(2, "wrong", "der Stuhl")]}
    )

    step = finish(CONTEXT, state, model)

    assert [(each["result"], each["answer"]) for each in step.logs] == [
        ("wrong", ""),
        ("wrong", "der Hund"),
    ]
    results: Any = step.results
    assert [item["label"] for item in results["items"]] == ["", "der Hund"]
    assert IMAGE not in json.dumps(results)


def test_a_picture_with_no_label_is_left_without_asking_the_judge() -> None:
    model, state = started("a table")

    step = finish(CONTEXT, state, model)

    assert step.logs == [] and len(model.asked) == 2


def test_each_picture_is_planned_from_some_of_the_words_drawn_afresh() -> None:
    lemmas = [f"Wort{number}" for number in range(200)]
    context = {**CONTEXT, "words": {"mode": "only", "lemmas": lemmas}}

    told = [describe_words(context).splitlines()[1].split(", ") for _ in range(3)]

    for words in told:
        assert len(words) == SHOWN_WORDS
        assert words == sorted(words, key=lemmas.index)
    assert told[0] != told[1] or told[1] != told[2]
