# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import io
from typing import Any

import pytest
from ink import PAGE_HEIGHT, PAGE_WIDTH, checked, picture, width
from PIL import Image


def stroke(pen: str = "pen", **changed: Any) -> dict[str, Any]:
    return {
        "pen": pen,
        "color": "#3366ff",
        "size": 6,
        "points": [[100, 100, 0.5], [300, 100, 0.5]],
        **changed,
    }


def test_a_point_off_the_page_is_kept_on_its_edge() -> None:
    kept = checked([stroke(points=[[-5, PAGE_HEIGHT + 9, 2]])])

    assert kept[0]["points"] == [[0, PAGE_HEIGHT, 1]]


@pytest.mark.parametrize(
    "wrong",
    [
        {"pen": "crayon"},
        {"color": "blue"},
        {"size": 0},
        {"points": []},
        {"points": [[1, 2]]},
    ],
)
def test_a_stroke_that_is_not_one_is_refused(wrong: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        checked([stroke(**wrong)])


def test_a_fountain_pen_is_wider_the_harder_it_is_pressed_and_a_highlighter_is_not() -> (
    None
):
    assert width("fountain", 4, 1) > 2 * width("fountain", 4, 0.2)
    assert width("highlighter", 4, 1) == width("highlighter", 4, 0)


def test_a_page_is_read_from_its_ink_in_black_but_what_is_highlighted() -> None:
    drawn = Image.open(
        io.BytesIO(
            picture(
                checked(
                    [
                        stroke(),
                        stroke(
                            "highlighter", points=[[100, 400, 0.5], [300, 400, 0.5]]
                        ),
                    ]
                )
            )
        )
    )

    assert drawn.size == (PAGE_WIDTH, PAGE_HEIGHT)
    assert drawn.getpixel((200, 100)) == 0
    assert drawn.getpixel((200, 400)) == 255
