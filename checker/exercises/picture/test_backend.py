# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import base64
import io
import json
from typing import Any

import pytest
from kit import ModelError
from PIL import Image

from picture.backend import (
    CLOSE_UP_PIXELS,
    GUTTER,
    MAX_POINTS,
    SHOWN_WORDS,
    act,
    close_up,
    describe_words,
    finish,
    marked,
    read_judgements,
    read_marks,
    read_plan,
    start,
    tightened,
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


def opened(url: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")


def plan(*things: str, scenes: tuple[str, ...] = ("A kitchen.",)) -> dict[str, Any]:
    return {"scenes": list(scenes), "things": list(things)}


def verdict(
    n: int, result: str, correct: str = "", note: str = "", alternatives: Any = ()
) -> dict[str, Any]:
    return {
        "n": n,
        "result": result,
        "correct": correct,
        "alternatives": list(alternatives),
        "note": note,
        "translation": "",
    }


def mark(x: int, y: int, label: str) -> dict[str, Any]:
    return {"x": x, "y": y, "label": label}


class FakeModel:
    """Plans, draws and judges as it is told to, one reply after another,
    and keeps what it was asked."""

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


def test_a_picture_is_planned_with_the_learners_words_drawn_and_shown_bare() -> None:
    model = FakeModel(plan("a table", "a chair", "a stove"))

    step = start(CONTEXT, model)

    assert step.show["image"] == IMAGE and step.show["points"] == []
    assert (step.show["picture"], step.show["pictures"]) == (1, 2)
    planning = model.asked[0][0]["content"]
    assert "Zu Hause" in planning and "Tisch, Lampe" in planning
    ((prompt, aspect_ratio),) = model.drawn
    assert prompt.startswith("A kitchen. Things such as these could be in it")
    assert "a table, a chair, a stove" in prompt and aspect_ratio == "4:3"
    # nothing is looked for on it
    assert len(model.asked) == 1 and model.looked == []


@pytest.mark.parametrize(
    ("panels", "layout", "aspect_ratio"),
    [
        (2, "side by side in one row", "16:9"),
        (3, "side by side in one row", "21:9"),
        (4, "in two rows of 2", "4:3"),
        (5, "in two rows, 3 in the top row and 2 in the bottom row", "16:9"),
        (8, "in two rows of 4", "16:9"),
    ],
)
def test_a_picture_is_drawn_in_as_many_panels_as_the_learner_chose(
    panels: int, layout: str, aspect_ratio: str
) -> None:
    scenes = tuple(f"Scene {number}." for number in range(1, 10))
    model = FakeModel(plan("a bus", "an apple", scenes=scenes))

    start({**CONTEXT, "options": {"panels": panels}}, model)

    planning = model.asked[0][0]["content"]
    assert f"Then choose {panels} scenes" in planning
    ((prompt, drawn_in),) = model.drawn
    assert f"divided into {panels} panels {layout}," in prompt
    assert f"{panels}. Scene {panels}." in prompt
    assert f"Scene {panels + 1}." not in prompt
    assert drawn_in == aspect_ratio


def test_more_things_are_planned_for_more_panels() -> None:
    told = []
    for panels in (1, 4, 8):
        model = FakeModel(plan("a bus"))
        start({**CONTEXT, "options": {"panels": panels}}, model)
        told.append(model.asked[0][0]["content"])

    assert ["Choose 8 different" in told[0], "Choose 12 different" in told[1]] == [
        True,
        True,
    ]
    assert "Choose 16 different" in told[2]


def test_a_plan_of_fewer_scenes_is_drawn_in_as_many_panels() -> None:
    scenes, _ = read_plan(plan("a bus", scenes=("A.", "B.", "C.")), 4)

    assert scenes == ["A.", "B.", "C."]
    assert read_plan(plan("a bus", scenes=("A.", "B.", "C.")), 2)[0] == ["A.", "B."]


def panelled(rows: list[int], border: int, gutter: int) -> str:
    """A picture of `rows` of coloured panels on white, `border` from its
    edges and `gutter` apart, as an image model draws them."""
    size = 200
    width = border * 2 + max(rows) * size + gutter * (max(rows) - 1)
    height = border * 2 + len(rows) * size + gutter * (len(rows) - 1)
    image = Image.new("RGB", (width, height), "white")
    for row, count in enumerate(rows):
        for column in range(count):
            x = border + column * (size + gutter)
            y = border + row * (size + gutter)
            image.paste(
                (60, 120 + 30 * column, 200 - 40 * row), (x, y, x + size, y + size)
            )
    out = io.BytesIO()
    image.save(out, "JPEG", quality=95)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def light_runs(line: list[Any]) -> list[tuple[int, int]]:
    runs, start = [], None
    for index, pixel in enumerate([*line, (0, 0, 0)]):
        if min(pixel) >= 225 and start is None:
            start = index
        elif min(pixel) < 225 and start is not None:
            runs.append((start, index))
            start = None
    return runs


def test_the_border_is_trimmed_and_the_gutters_made_thin() -> None:
    picture = opened(tightened(panelled([3, 2], border=50, gutter=70), [3, 2]))

    top_row = [picture.getpixel((x, 100)) for x in range(picture.width)]
    middle = [picture.getpixel((5, y)) for y in range(picture.height)]
    # no border, and a gutter of GUTTER between each two panels, but for
    # what the JPEG blurs at their edges
    widths = [end - start for start, end in light_runs(top_row)]
    heights = [end - start for start, end in light_runs(middle)]
    assert len(widths) == 2 and len(heights) == 1
    assert all(GUTTER <= each <= GUTTER + 2 for each in widths + heights)
    for corner in ((0, 0), (picture.width - 1, picture.height - 1)):
        pixel = picture.getpixel(corner)
        assert isinstance(pixel, tuple) and min(pixel) < 225


def test_panels_without_gutters_where_they_should_be_are_left_as_they_are() -> None:
    drawn = panelled([1], border=0, gutter=0)

    assert tightened(drawn, [2, 2]) == drawn


def test_a_plan_with_no_thing_is_a_failure() -> None:
    with pytest.raises(ModelError, match="no thing"):
        read_plan({"scenes": ["A kitchen."], "things": []})


def test_a_picture_is_reported_as_made_as_soon_as_it_is_drawn() -> None:
    model = FakeModel(plan("a table"))

    step = start(CONTEXT, model)

    assert step.made == [
        {"image": IMAGE, "scene": "A kitchen.", "planned": [{"thing": "a table"}]}
    ]


def test_the_marks_are_those_named_and_within_the_picture() -> None:
    given = [
        mark(100, 200, "  der   Tisch "),
        mark(300, 300, "   "),
        mark(1200, 300, "die Lampe"),
        {"x": True, "y": 3, "label": "der Stuhl"},
        "der Herd",
        {"x": 10.4, "y": 999.6, "label": "der Herd"},
    ]

    assert read_marks(given) == [
        mark(100, 200, "der Tisch"),
        mark(10, 1000, "der Herd"),
    ]
    assert len(read_marks([mark(1, 1, "x")] * (MAX_POINTS + 5))) == MAX_POINTS


def started(*things: str) -> tuple[FakeModel, Any]:
    """A picture of `things`, and the model, which is to be told what it
    replies next."""
    model = FakeModel(plan(*things))
    return model, start(CONTEXT, model).state


def test_the_marks_are_judged_in_one_look_at_the_ringed_picture_and_close_ups() -> None:
    model, state = started("a table", "a silver trophy")
    model.replies.append(
        {
            "labels": [
                verdict(1, "right", "der Tisch", alternatives=["der Esstisch"]),
                verdict(
                    2,
                    "wrong",
                    "der Pokal",
                    "Preis is a prize.",
                    ["die Trophäe", "der Pokal", "der Cup", "der Becher"],
                ),
            ]
        }
    )

    checked = act(
        CONTEXT,
        state,
        {
            "check": True,
            "points": [mark(200, 300, "Der Tisch"), mark(700, 600, "der Preis")],
        },
        model,
    )

    task = "Name what is marked at point {} of a picture of A kitchen.".format
    assert checked.graded == [
        {
            "result": "right",
            "task": task(1),
            "answer": "Der Tisch",
            "correction": "",
            "note": "",
        },
        {
            "result": "wrong",
            "task": task(2),
            "answer": "der Preis",
            "correction": "der Pokal",
            "note": "Preis is a prize.",
        },
    ]
    ((message,),) = model.asked[1:]
    assert model.looked == [1]
    text, *pictures = message["content"]
    assert '1. "Der Tisch"\n2. "der Preis"' in text["text"]
    assert "(the illustrator meant" not in text["text"]
    # the picture with its rings, then a close-up of each mark
    assert [part["type"] for part in pictures] == [
        "image_url",
        "text",
        "image_url",
        "text",
        "image_url",
    ]
    assert pictures[0]["image_url"]["url"] != IMAGE
    assert pictures[3]["text"] == "Close-up of mark 2:"
    shown = checked.show["points"]
    assert [(point["x"], point["label"]) for point in shown] == [
        (200, "Der Tisch"),
        (700, "der Preis"),
    ]
    # what is right is what was written; others are given only where it is not
    assert shown[0]["feedback"]["correct"] == "Der Tisch"
    assert shown[0]["feedback"]["alternatives"] == []
    assert shown[1]["feedback"]["alternatives"] == [
        "die Trophäe",
        "der Cup",
        "der Becher",
    ]
    assert checked.show["judged"] is True and checked.show["more"] is True


def test_once_the_marks_are_judged_they_and_what_was_not_right_are_written() -> None:
    model, state = started("a table", "a plant")
    model.replies.append(
        {
            "labels": [
                verdict(1, "right", "der Tisch"),
                verdict(2, "partial", "die Pflanze"),
            ]
        }
    )

    checked = act(
        CONTEXT,
        state,
        {
            "check": True,
            "points": [mark(1, 1, "Der Tisch"), mark(500, 500, "die Planze")],
        },
        model,
    )

    assert checked.written == {
        "user": ["Der Tisch", "die Planze"],
        "assistant": ["die Pflanze"],
    }


def test_nothing_is_judged_without_a_named_mark_or_a_second_time() -> None:
    model, state = started("a table")
    model.replies.append({"labels": [verdict(1, "right", "der Tisch")]})

    blank = act(CONTEXT, state, {"check": True, "points": [mark(1, 1, " ")]}, model)
    checked = act(
        CONTEXT, state, {"check": True, "points": [mark(1, 1, "der Tisch")]}, model
    )
    again = act(
        CONTEXT, checked.state, {"check": True, "points": [mark(2, 2, "x")]}, model
    )

    assert blank.graded == [] and again.graded == []
    assert len(model.asked) == 2
    assert again.show["points"] == checked.show["points"]


def test_a_judge_that_leaves_a_label_out_is_a_failure() -> None:
    with pytest.raises(ModelError, match="every label"):
        read_judgements({"labels": [verdict(1, "right")]}, 2)


def test_judgements_are_read_in_whatever_shape_the_model_gives_them() -> None:
    reply = [{"marker": "2", "result": "wrong"}, {"number": 1, "result": "right"}]

    judged = read_judgements(reply, 2)

    assert [each["result"] for each in judged] == ["right", "wrong"]


def test_the_judge_is_shown_a_ring_on_each_point_leaving_it_to_be_seen() -> None:
    picture = opened(marked(IMAGE, [{"x": 500, "y": 500}]))

    middle = picture.getpixel((200, 150))
    on_ring = [picture.getpixel((200 + offset, 150)) for offset in range(6, 14)]
    assert isinstance(middle, tuple) and middle[0] < 230 and middle[2] > 200
    assert any(
        isinstance(pixel, tuple) and pixel[0] > 150 and pixel[1] < 100
        for pixel in on_ring
    )


def test_a_close_up_is_of_what_is_around_the_point_even_by_the_edge() -> None:
    image = Image.new("RGB", (400, 300), (200, 220, 240))
    # a black square in the top left corner
    image.paste((0, 0, 0), (0, 0, 30, 30))
    out = io.BytesIO()
    image.save(out, "JPEG")
    url = "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()

    near = opened(close_up(url, {"x": 10, "y": 10}))

    assert near.size == (CLOSE_UP_PIXELS, CLOSE_UP_PIXELS)
    corner = near.getpixel((5, 5))
    assert isinstance(corner, tuple) and max(corner) < 40


def test_the_next_picture_is_of_other_scenes_without_what_was_planned_before() -> None:
    model, state = started("a table", "a chair")
    model.replies += [
        {"labels": [verdict(1, "right")]},
        plan("a stove", scenes=("A garden.",)),
    ]
    state = act(
        CONTEXT, state, {"check": True, "points": [mark(1, 1, "der Tisch")]}, model
    ).state

    following = act(CONTEXT, state, {"next": True}, model)

    planning = model.asked[2][0]["content"]
    assert "clearly different from all of them: A kitchen." in planning
    assert "a table; a chair" in planning
    assert following.show["points"] == [] and following.show["judged"] is False
    assert (following.show["picture"], following.show["more"]) == (2, False)
    assert following.made[0]["scene"] == "A garden."


def test_what_was_judged_is_scored_when_the_exercise_is_left() -> None:
    model, state = started("a table", "a chair")
    model.replies.append(
        {"labels": [verdict(1, "right", "der Tisch"), verdict(2, "wrong", "der Stuhl")]}
    )
    state = act(
        CONTEXT,
        state,
        {"check": True, "points": [mark(1, 1, "der Tisch"), mark(9, 9, "der Hund")]},
        model,
    ).state

    step = finish(CONTEXT, state, model)

    assert step.graded == [] and len(model.asked) == 2
    results: Any = step.results
    assert [item["label"] for item in results["items"]] == ["der Tisch", "der Hund"]
    assert step.scores == {"vocabulary": 50.0}
    assert IMAGE not in json.dumps(results)


def test_a_picture_left_unchecked_is_neither_judged_nor_scored() -> None:
    model, state = started("a table")

    step = finish(CONTEXT, state, model)

    assert step.graded == [] and step.scores is None and len(model.asked) == 1


def test_each_picture_is_planned_from_some_of_the_words_drawn_afresh() -> None:
    lemmas = [f"Wort{number}" for number in range(200)]
    context = {**CONTEXT, "words": {"mode": "only", "lemmas": lemmas}}

    told = [describe_words(context).splitlines()[1].split(", ") for _ in range(3)]

    for words in told:
        assert len(words) == SHOWN_WORDS
        assert words == sorted(words, key=lemmas.index)
    assert told[0] != told[1] or told[1] != told[2]


def test_a_picture_done_again_is_taken_from_those_drawn_before_and_only_judged() -> (
    None
):
    made = start(CONTEXT, FakeModel(plan("a table"))).made
    # one kept before the learner marked the things themselves
    kept = [{**made[0], "items": [{"thing": "a table", "x": 1, "y": 2}]}]
    again = {**CONTEXT, "instances": 1, "replay": kept}
    model = FakeModel({"labels": [verdict(1, "right")]})

    started = start(again, model)
    checked = act(
        again,
        started.state,
        {"check": True, "points": [mark(5, 5, "der Tisch")]},
        model,
    )

    assert (started.made, model.drawn) == ([], [])
    assert started.show["image"] == IMAGE and started.show["points"] == []
    # the only request is the one that judges the labels
    assert len(model.asked) == 1 and checked.graded


def test_a_label_that_is_what_the_judge_says_it_should_be_is_right() -> None:
    model, state = started("a desk", "a book")
    model.replies.append(
        {
            "labels": [
                verdict(
                    1,
                    "partial",
                    "der Schreibtisch",
                    "The mark is on the side of the desk.",
                    ["der Tisch"],
                ),
                verdict(2, "partial", "das buch", "Capitals."),
            ]
        }
    )

    checked = act(
        CONTEXT,
        state,
        {
            "check": True,
            "points": [mark(1, 1, "Der Schreibtisch"), mark(9, 9, "das buch")],
        },
        model,
    )

    assert [each["result"] for each in checked.graded] == ["right", "right"]
    feedback = checked.show["points"][0]["feedback"]
    assert (feedback["correct"], feedback["alternatives"], feedback["note"]) == (
        "Der Schreibtisch",
        [],
        "",
    )


def test_the_next_picture_is_drawn_ahead_and_shown_without_waiting() -> None:
    model, state = started("a table", "a chair")
    model.replies.append(plan("a stove", scenes=("A garden.",)))

    prepared = act(CONTEXT, state, {"prepare": True}, model)
    model.replies.append({"labels": [verdict(1, "right")]})
    state = act(
        CONTEXT,
        prepared.state,
        {"check": True, "points": [mark(1, 1, "der Tisch")]},
        model,
    ).state
    asked = len(model.asked)
    following = act(CONTEXT, state, {"next": True}, model)

    # what is shown does not change until the learner asks for the next one
    assert prepared.show["image"] == IMAGE and prepared.made == []
    planning = model.asked[1][0]["content"]
    assert "A kitchen." in planning and "a table; a chair" in planning
    # it is shown without a model being asked, and reported as made then
    assert len(model.asked) == asked and len(model.drawn) == 2
    assert (following.show["picture"], following.show["points"]) == (2, [])
    assert [made["scene"] for made in following.made] == ["A garden."]
    assert "upcoming" not in following.state


def test_nothing_is_drawn_ahead_of_the_last_picture_or_twice() -> None:
    model, state = started("a table")
    model.replies.append(plan("a stove"))

    once = act(CONTEXT, state, {"prepare": True}, model)
    twice = act(CONTEXT, once.state, {"prepare": True}, model)
    one = {**CONTEXT, "instances": 1}
    alone = start(one, FakeModel(plan("a lamp"))).state
    last = act(one, alone, {"prepare": True}, model)

    assert len(model.drawn) == 2
    assert twice.state["upcoming"] == once.state["upcoming"]
    assert "upcoming" not in last.state


def test_what_the_ring_is_on_is_given_as_a_hint_that_does_not_count() -> None:
    model, state = started("a person")
    model.replies.append(
        {
            "labels": [
                {
                    "n": 1,
                    "meant": "a person",
                    "result": "right",
                    "correct": "die Person",
                    "translation": "person",
                    "note": "",
                    "hint": "The ring is on her arm:  der Arm.",
                }
            ]
        }
    )

    checked = act(
        CONTEXT, state, {"check": True, "points": [mark(5, 5, "die Person")]}, model
    )

    assert [each["result"] for each in checked.graded] == ["right"]
    feedback = checked.show["points"][0]["feedback"]
    assert (feedback["meant"], feedback["hint"]) == (
        "a person",
        "The ring is on her arm: der Arm.",
    )
    judging = model.asked[1][0]["content"][0]["text"]
    assert "never where the ring is" in judging
