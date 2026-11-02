# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The ink of a handwritten page of a text, as the app writes it with a pen
or a finger, and the picture of it that is read.

A page is `PAGE_WIDTH` by `PAGE_HEIGHT`, the size of a sheet of A4 at 150
dots an inch, and everything on it is placed in those units, whatever size
it is shown at. Its ink is a list of strokes, the first written first:

    {"pen": "pen", "color": "#1a1a1a", "size": 4,
     "points": [[x, y, pressure], ...]}

where the pressure goes from 0 to 1, and is 0.5 for a mouse. The pens are
`PENS`; how wide each draws at a pressure is `width`, which the app draws
by too. A page is read from a picture of its ink in black on white, as
the colours a learner writes in are not what is written; what is
highlighted is not written, and is left out.
"""

from __future__ import annotations

import io
import re
from typing import Any

from PIL import Image, ImageDraw

PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
PENS = ("pen", "fountain", "pencil", "highlighter")
# the thinnest and the thickest a pen can be set to, in units of the page
MIN_SIZE = 1
MAX_SIZE = 40
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def width(pen: str, size: float, pressure: float) -> float:
    """How wide `pen`, set to `size`, draws at `pressure`: a pen a little
    wider the harder it is pressed, a fountain pen much wider, a pencil
    thinner, and a highlighter as wide whatever the pressure."""
    if pen == "fountain":
        return size * (0.3 + 1.4 * pressure)
    if pen == "pencil":
        return size * 0.6 * (0.8 + 0.4 * pressure)
    if pen == "highlighter":
        return size * 3
    return size * (0.75 + 0.5 * pressure)


def checked(ink: object) -> list[dict[str, Any]]:
    """`ink` as it is kept, if it is the ink of a page. Raises ValueError."""
    if not isinstance(ink, list):
        raise ValueError("the ink of a page is a list of strokes")
    strokes = []
    for stroke in ink:
        if not isinstance(stroke, dict):
            raise ValueError("a stroke is an object")
        pen, color, size = stroke.get("pen"), stroke.get("color"), stroke.get("size")
        points = stroke.get("points")
        if pen not in PENS:
            raise ValueError(f"a pen is one of {', '.join(PENS)}")
        if not isinstance(color, str) or not _COLOR.fullmatch(color):
            raise ValueError("a colour is written as #rrggbb")
        if not isinstance(size, int | float) or not MIN_SIZE <= size <= MAX_SIZE:
            raise ValueError(f"a size is from {MIN_SIZE} to {MAX_SIZE}")
        if not isinstance(points, list) or not points:
            raise ValueError("a stroke has points")
        kept = []
        for point in points:
            if (
                not isinstance(point, list)
                or len(point) != 3
                or not all(isinstance(each, int | float) for each in point)
            ):
                raise ValueError("a point is [x, y, pressure]")
            x, y, pressure = point
            kept.append(
                [
                    min(max(x, 0), PAGE_WIDTH),
                    min(max(y, 0), PAGE_HEIGHT),
                    min(max(pressure, 0), 1),
                ]
            )
        strokes.append({"pen": pen, "color": color, "size": size, "points": kept})
    return strokes


def picture(ink: list[dict[str, Any]]) -> bytes:
    """The ink of a page drawn in black on white, but what is highlighted,
    as a PNG of the size of the page."""
    image = Image.new("L", (PAGE_WIDTH, PAGE_HEIGHT), 255)
    draw = ImageDraw.Draw(image)
    for stroke in ink:
        if stroke["pen"] == "highlighter":
            continue
        points = stroke["points"]
        for at, (x, y, pressure) in enumerate(points):
            wide = width(stroke["pen"], stroke["size"], pressure)
            if at:
                before = points[at - 1]
                draw.line([(before[0], before[1]), (x, y)], fill=0, width=round(wide))
            # round ends and joins
            draw.ellipse(
                [x - wide / 2, y - wide / 2, x + wide / 2, y + wide / 2], fill=0
            )
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()
