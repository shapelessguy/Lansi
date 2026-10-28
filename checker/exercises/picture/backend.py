# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""A picture of the topic, on which the learner marks the things they can
name and names them, and a model that sees the picture judges the names.

A picture is made in two asks: a model plans the things that could be in
it, leaning on the words of the learner's vocabulary, and one to four
scenes they could be seen in; and an image model draws it, as one scene or
as panels of a grid. It is shown with nothing on it.

Nothing is decided ahead of what is on it: what was planned only shapes the
picture. The learner clicks on the picture where there is something they
can name, as many times as they like, and names each thing, all in the
interface. When they ask for the names to be checked, the points come with
the message, and the model that sees pictures is shown the picture with a
numbered ring on each point and a close-up of each, all in one ask, and
judges each name by what is under its ring, giving others that would be
right for one that is not. Each point is graded then. Each instance is a
picture. The interface asks for the next to be drawn as soon as one is
shown, and it is kept until the learner is done with this one, so that
they never wait for it.

A picture is reported as made once it is shown: its image, its scene and
what was planned. When the exercise is done again, the pictures are
taken in order from `replay` in place of being drawn, and those it
had not made yet when it was left are made as before.
"""

from __future__ import annotations

import base64
import io
import json
import random
from typing import Any

import numpy as np
from kit import (
    RESULTS,
    Model,
    ModelError,
    Step,
    ask_json,
    describe_guidance,
    describe_topics,
    grade,
    loose,
    option,
    prompts_beside,
    score_of,
    serve,
    written,
)
from PIL import Image, ImageDraw, ImageFont

# how many panels a picture is drawn in, if the learner chose none
PANELS = 4
# How a picture of each number of panels is laid out: how many panels are
# in each row, from the top, and the shape it is drawn in.
LAYOUTS = {
    1: ([1], "4:3"),
    2: ([2], "16:9"),
    3: ([3], "21:9"),
    4: ([2, 2], "4:3"),
    5: ([3, 2], "16:9"),
    6: ([3, 3], "3:2"),
    7: ([4, 3], "16:9"),
    8: ([4, 4], "16:9"),
}
# how many things are planned for each panel, and the fewest and the most
# for a picture
THINGS_PER_PANEL = 3
MIN_THINGS = 8
MAX_THINGS = 16
# how wide the gutters between the panels are made, in pixels
GUTTER = 10
# What is taken for the white of a gutter or a border: a line of pixels
# nearly all of whose channels are at least this light.
LIGHT = 225
LIGHT_SHARE = 0.96
# the most of each side of a picture that is trimmed as its border, and of
# a row of panels, which may have fewer than the others and room to spare
MAX_BORDER = 0.15
MAX_ROW_BORDER = 0.4
# the most words of the learner's that the planning is told
SHOWN_WORDS = 60
# how much of a reply that could not be read is told with why
MAX_SHOWN = 300
# the most points the learner may mark on a picture
MAX_POINTS = 20
# the longest label that is kept
MAX_LABEL = 80
# the most other names given for one that was not right
MAX_ALTERNATIVES = 3
# how big a ring is drawn for the judge, as a part of the shorter side
RING_SIZE = 0.035
# how much of the shorter side of the picture a close-up shows, and how big
# it is sent, in pixels
CLOSE_UP_SIZE = 0.25
CLOSE_UP_PIXELS = 256
RING_COLOUR = (220, 30, 60)

# what the exercise tells the models, by name
PROMPTS = prompts_beside(__file__)


def _level(context: dict[str, Any]) -> str:
    return str(context["level"] or context["lesson"]["level"])


def describe_words(context: dict[str, Any]) -> str:
    """The words of the learner's that the things are best chosen by, if
    any."""
    words = context.get("words")
    if not words or not words.get("lemmas"):
        return ""
    # Some of them, drawn afresh for each picture, as the first of them are
    # the same in every session about a topic, and would make the same
    # picture each time. They keep the order they came in.
    given = words["lemmas"]
    chosen = sorted(random.sample(range(len(given)), min(SHOWN_WORDS, len(given))))
    lemmas = ", ".join(given[index] for index in chosen)
    return f"{PROMPTS('words', lemmas=lemmas)}\n"


def _texts(listed: Any, key: str) -> list[str]:
    """The texts of a list of a reply, each once, with their spaces made
    single; an entry that is an object is read for what is under `key`."""
    texts: list[str] = []
    for each in listed if isinstance(listed, list) else []:
        if isinstance(each, dict):
            each = each.get(key)
        if not isinstance(each, str) or not each.strip():
            continue
        each = " ".join(each.split())
        if all(loose(each) != loose(other) for other in texts):
            texts.append(each)
    return texts


def read_plan(reply: Any, panels: int = 1) -> tuple[list[str], list[dict[str, Any]]]:
    """The scenes the model planned, one for each of at most `panels`
    panels, and the things that could be drawn in them. Raises ModelError
    if there are no things."""
    if not isinstance(reply, dict):
        raise ModelError("the model planned no picture")
    things = [{"thing": thing} for thing in _texts(reply.get("things"), "thing")]
    if not things:
        raise ModelError("the model planned no thing to draw")
    scenes = _texts(reply.get("scenes"), "scene")
    if not scenes and isinstance(reply.get("scene"), str):
        scenes = _texts([reply["scene"]], "scene")
    return scenes[: max(1, panels)], things


def drawing_prompt(scenes: list[str], things: list[dict[str, Any]]) -> str:
    """What the image model is asked to draw: the `scenes`, each in a panel
    of its own if there are several, laid out as `LAYOUTS` says, with room
    for the `things`."""
    listed = ", ".join(thing["thing"] for thing in things)
    if len(scenes) <= 1:
        return PROMPTS("drawing.one", scene=scenes[0] if scenes else "", things=listed)
    rows = LAYOUTS[len(scenes)][0]
    if len(rows) == 1:
        layout = PROMPTS("drawing.rows.one")
    elif rows[0] == rows[1]:
        layout = PROMPTS("drawing.rows.even", each=rows[0])
    else:
        layout = PROMPTS("drawing.rows.uneven", top=rows[0], bottom=rows[1])
    panels = "; ".join(f"{number}. {scene}" for number, scene in enumerate(scenes, 1))
    return PROMPTS(
        "drawing.panels",
        count=len(scenes),
        layout=layout,
        panels=panels,
        things=listed,
    )


def _panels(context: dict[str, Any]) -> int:
    return min(max(int(option(context, "panels", PANELS)), 1), max(LAYOUTS))


def make_picture(
    context: dict[str, Any],
    model: Model,
    planned: list[str],
    scenes: list[str] | None = None,
    at: int = 0,
) -> dict[str, Any]:
    """A picture of none of the `scenes` there were before and with none of
    the things `planned` for them; or, when the exercise is done again, the
    one of those `at` that place. Raises ModelError."""
    replay = context.get("replay")
    if replay and at < len(replay):
        again = replay[at]
        return {
            "image": again["image"],
            "scene": again.get("scene", ""),
            "planned": json.loads(json.dumps(again.get("planned", []))),
            "points": [],
            "judged": None,
            # it was kept, and is not reported as made again
            "reported": True,
        }
    avoid = ""
    if scenes:
        avoid += " " + PROMPTS("avoid.scenes", scenes="; ".join(scenes))
    if planned:
        avoid += " " + PROMPTS("avoid.planned", planned="; ".join(planned))
    plan = PROMPTS(
        "planning",
        language=context["language"],
        level=_level(context),
        topics=describe_topics(context),
        words=describe_words(context),
        guidance=describe_guidance(context, at + 1),
        count=min(max(THINGS_PER_PANEL * _panels(context), MIN_THINGS), MAX_THINGS),
        panels=_panels(context),
        avoid=avoid,
    )
    try:
        drawn_in, things = read_plan(
            ask_json(model, [{"role": "user", "content": plan}]), _panels(context)
        )
    except ModelError as error:
        raise ModelError(f"planning the picture: {error}") from None
    rows, aspect_ratio = LAYOUTS[max(1, len(drawn_in))]
    image = tightened(model.draw(drawing_prompt(drawn_in, things), aspect_ratio), rows)
    return {
        "image": image,
        "scene": " ".join(drawn_in),
        "planned": things,
        "points": [],
        "judged": None,
        "reported": False,
    }


def _gutters(light: Any) -> list[tuple[int, int]]:
    """Where the lines of a picture that are a gutter are, as runs of them,
    from the first to past the last, given whether each line is light."""
    runs: list[tuple[int, int]] = []
    start = None
    for index, is_light in enumerate([*light, False]):
        if is_light and start is None:
            start = index
        elif not is_light and start is not None:
            runs.append((start, index))
            start = None
    return runs


def _cut(light: Any, parts: int) -> list[tuple[int, int]] | None:
    """Where the `parts` panels side by side along lines of a picture are,
    as from and past each, given whether each line is light: split at the
    gutter nearest to where each split should be. None if a gutter is
    missing, so that what is not a gutter is never taken for one."""
    length = len(light)
    if parts == 1:
        return [(0, length)]
    inner = [run for run in _gutters(light) if run[0] > 0 and run[1] < length]
    splits: list[tuple[int, int]] = []
    for part in range(1, parts):
        expected = length * part / parts
        near = [
            run
            for run in inner
            if abs((run[0] + run[1]) / 2 - expected) < length / parts / 3
            and (not splits or run[0] >= splits[-1][1])
        ]
        if not near:
            return None
        splits.append(min(near, key=lambda run: abs((run[0] + run[1]) / 2 - expected)))
    edges = [0] + [edge for split in splits for edge in split] + [length]
    return list(zip(edges[::2], edges[1::2]))


def _is_light(pixels: Any, axis: int) -> Any:
    """Whether each line of `pixels` across `axis` is light enough to be a
    gutter or a border."""
    return (pixels.min(axis=2) >= LIGHT).mean(axis=axis) >= LIGHT_SHARE


def _trimmed(picture: Image.Image, most_of: float = MAX_BORDER) -> Image.Image:
    """The picture without the light border around it, of at most `most_of`
    each side."""
    pixels = np.asarray(picture)
    box = []
    for axis, size in ((0, picture.width), (1, picture.height)):
        light = list(_is_light(pixels, axis))
        most = int(size * most_of)
        start = next((i for i, each in enumerate(light[:most]) if not each), most)
        end = next((i for i, each in enumerate(light[::-1][:most]) if not each), most)
        box.append((start, size - end))
    (left, right), (top, bottom) = box
    return picture.crop((left, top, right, bottom))


def tightened(image: str, rows: list[int]) -> str:
    """A picture drawn in panels, laid out in `rows` of them, with no
    border around it and gutters of `GUTTER` pixels between them, as image
    models draw them far wider than they are told. Where the gutters are
    not where they should be, the panels are left as they are. Raises
    ModelError."""
    drawn = _open(image)
    picture = _trimmed(drawn)
    pixels = np.asarray(picture)
    bands = _cut(list(_is_light(pixels, 1)), len(rows)) if len(rows) > 1 else None
    if bands is None:
        bands = [(0, picture.height)]
        rows = [rows[0]] if len(rows) == 1 else [1]
    pieces: list[Image.Image] = []
    for (top, bottom), count in zip(bands, rows):
        band = picture.crop((0, top, picture.width, bottom))
        if len(bands) > 1:
            band = _trimmed(band, MAX_ROW_BORDER)
        columns = _cut(list(_is_light(np.asarray(band), 0)), count)
        if columns is None or len(columns) == 1:
            pieces.append(band)
            continue
        panels = [band.crop((left, 0, right, band.height)) for left, right in columns]
        joined = Image.new(
            "RGB",
            (
                sum(panel.width for panel in panels) + GUTTER * (len(panels) - 1),
                band.height,
            ),
            "white",
        )
        x = 0
        for panel in panels:
            joined.paste(panel, (x, 0))
            x += panel.width + GUTTER
        pieces.append(joined)
    if picture.size == drawn.size and [piece.size for piece in pieces] == [
        picture.size
    ]:
        # nothing to tighten, and the picture is kept as it was drawn
        return image
    # each band as wide as the widest, so that their edges meet
    width = max(piece.width for piece in pieces)
    pieces = [
        piece
        if piece.width == width
        else piece.resize(
            (width, round(piece.height * width / piece.width)), Image.Resampling.LANCZOS
        )
        for piece in pieces
    ]
    whole = Image.new(
        "RGB",
        (width, sum(piece.height for piece in pieces) + GUTTER * (len(pieces) - 1)),
        "white",
    )
    y = 0
    for piece in pieces:
        whole.paste(piece, (0, y))
        y += piece.height + GUTTER
    return _as_url(whole)


# what of a picture is the instance it is, which is kept to do it again
INSTANCE = ("image", "scene", "planned")


def made_of(picture: dict[str, Any]) -> list[dict[str, Any]]:
    """The picture as the instance to report as made, if it was not
    reported before; nothing otherwise."""
    if picture.get("reported", True):
        return []
    picture["reported"] = True
    return [{key: picture[key] for key in INSTANCE}]


def read_marks(given: Any) -> list[dict[str, Any]]:
    """The points the learner marked and named, as the interface sends
    them: each where it is, out of 1000 across and down, with its label.
    Those named with nothing are left out, and those past the most there
    may be."""
    points: list[dict[str, Any]] = []
    for point in given if isinstance(given, list) else []:
        if not isinstance(point, dict):
            continue
        x, y, label = point.get("x"), point.get("y"), point.get("label")
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in (x, y)
        ) or not isinstance(label, str):
            continue
        label = " ".join(label.split())[:MAX_LABEL]
        if not label or not (0 <= x <= 1000 and 0 <= y <= 1000):  # type: ignore[operator]
            continue
        points.append({"x": round(x), "y": round(y), "label": label})  # type: ignore[arg-type]
    return points[:MAX_POINTS]


def _with_pictures(text: str, *parts: tuple[str, str]) -> dict[str, Any]:
    """A message of `text`, then of each part: its words, if any, and its
    picture."""
    content: list[dict[str, Any]] = [{"type": "text", "text": text}]
    for words, image in parts:
        if words:
            content.append({"type": "text", "text": words})
        content.append({"type": "image_url", "image_url": {"url": image}})
    return {"role": "user", "content": content}


def _open(image: str) -> Image.Image:
    """A picture given as a data URL, in RGB. Raises ModelError."""
    try:
        encoded = image.split(",", 1)[1]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as opened:
            return opened.convert("RGB")
    except (IndexError, ValueError, OSError):
        raise ModelError("the picture cannot be read") from None


def _as_url(picture: Image.Image) -> str:
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def _ring(draw: ImageDraw.ImageDraw, x: float, y: float, radius: float) -> None:
    """A ring around a point, red within white, which leaves what it is on
    to be seen."""
    box = (x - radius, y - radius, x + radius, y + radius)
    width = max(2, round(radius / 6))
    draw.ellipse(box, outline="white", width=width * 2)
    draw.ellipse(
        (box[0] + width, box[1] + width, box[2] - width, box[3] - width),
        outline=RING_COLOUR,
        width=width,
    )


def _point_on(picture: Image.Image, point: dict[str, Any]) -> tuple[float, float]:
    return point["x"] * picture.width / 1000, point["y"] * picture.height / 1000


def marked(image: str, points: list[dict[str, Any]]) -> str:
    """The picture with a ring on each point and its number beside it, as a
    data URL, for the judge to see what each label is of. Raises
    ModelError."""
    picture = _open(image)
    draw = ImageDraw.Draw(picture)
    radius = max(10, round(min(picture.size) * RING_SIZE))
    tag = round(radius * 0.7)
    font = ImageFont.load_default(size=round(tag * 1.4))
    for number, point in enumerate(points, 1):
        x, y = _point_on(picture, point)
        _ring(draw, x, y, radius)
        # the number up and to the right of the ring, kept within the picture
        tag_x = min(max(x + radius + tag * 0.4, tag), picture.width - tag)
        tag_y = min(max(y - radius - tag * 0.4, tag), picture.height - tag)
        draw.ellipse(
            (tag_x - tag, tag_y - tag, tag_x + tag, tag_y + tag),
            fill=RING_COLOUR,
            outline="white",
            width=2,
        )
        draw.text((tag_x, tag_y), str(number), fill="white", font=font, anchor="mm")
    return _as_url(picture)


def close_up(image: str, point: dict[str, Any]) -> str:
    """What is around a point of the picture, made bigger, with a ring on
    the point, as a data URL. Raises ModelError."""
    picture = _open(image)
    x, y = _point_on(picture, point)
    half = min(picture.size) * CLOSE_UP_SIZE / 2
    # kept within the picture, so that the point may be off its middle
    left = min(max(x - half, 0), picture.width - 2 * half)
    top = min(max(y - half, 0), picture.height - 2 * half)
    crop = picture.crop(
        (round(left), round(top), round(left + 2 * half), round(top + 2 * half))
    )
    crop = crop.resize((CLOSE_UP_PIXELS, CLOSE_UP_PIXELS), Image.Resampling.LANCZOS)
    scale = CLOSE_UP_PIXELS / (2 * half)
    _ring(
        ImageDraw.Draw(crop),
        (x - left) * scale,
        (y - top) * scale,
        CLOSE_UP_PIXELS * 0.12,
    )
    return _as_url(crop)


def _shown(reply: Any) -> str:
    said = json.dumps(reply, ensure_ascii=False)
    return said[:MAX_SHOWN] + ("…" if len(said) > MAX_SHOWN else "")


def _entries(reply: Any, key: str) -> list[Any]:
    """The list a reply holds: the reply, what is under `key`, or the first
    list in it."""
    if isinstance(reply, list):
        return reply
    if isinstance(reply, dict):
        if isinstance(reply.get(key), list):
            return list(reply[key])
        return next((value for value in reply.values() if isinstance(value, list)), [])
    return []


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def read_judgements(reply: Any, count: int) -> list[dict[str, Any]]:
    """What the judge said of each of `count` labels, in order. Raises
    ModelError unless it judged every one."""
    judged: dict[int, dict[str, Any]] = {}
    for entry in _entries(reply, "labels"):
        if not isinstance(entry, dict):
            continue
        number = next(
            (
                found
                for key in ("n", "number", "marker", "index", "id")
                if (found := _number(entry.get(key))) is not None
            ),
            None,
        )
        result = entry.get("result")
        if number is None or not 1 <= number <= count or result not in RESULTS:
            continue
        correct = " ".join(str(entry.get("correct") or "").split())
        alternatives = [
            each
            for each in _texts(entry.get("alternatives"), "name")
            if loose(each) != loose(correct)
        ][:MAX_ALTERNATIVES]
        judged.setdefault(
            number - 1,
            {
                "result": result,
                "correct": correct,
                "alternatives": [] if result == "right" else alternatives,
                "translation": str(entry.get("translation") or ""),
                "note": str(entry.get("note") or ""),
                # what the learner meant, as the judge saw it, and what the
                # ring is on if it is mostly on something else, which is
                # never held against them
                "meant": " ".join(str(entry.get("meant") or "").split()),
                "hint": " ".join(str(entry.get("hint") or "").split()),
            },
        )
    if len(judged) < count:
        raise ModelError(f"the model did not judge every label: {_shown(reply)}")
    return [judged[index] for index in range(count)]


def _as_written(label: str) -> str:
    """A label as it is compared: its spaces made single, and its first
    letter small."""
    label = " ".join(label.split())
    return label[:1].lower() + label[1:]


def judge(
    context: dict[str, Any], model: Model, picture: dict[str, Any]
) -> list[dict[str, str]]:
    """Have the labels of the points of a picture judged, keep the
    judgements on it, and return their grades: one for each point. Raises
    ModelError."""
    points = picture["points"]
    labels = "\n".join(
        PROMPTS(
            "label",
            number=number,
            given=json.dumps(point["label"], ensure_ascii=False),
        )
        for number, point in enumerate(points, 1)
    )
    prompt = PROMPTS(
        "judging",
        language=context["language"],
        level=_level(context),
        labels=labels,
        into=context["into"],
    )
    message = _with_pictures(
        prompt,
        ("", marked(picture["image"], points)),
        *(
            (PROMPTS("close_up", number=number), close_up(picture["image"], point))
            for number, point in enumerate(points, 1)
        ),
    )
    judged = read_judgements(ask_json(model, [message], look=True), len(points))
    for judgement, point in zip(judged, points):
        # What was written is right where it is what the judge says it
        # should be, but for a capital first letter, which does not matter,
        # however it judged it: it marks down where the point is, at times.
        if _as_written(judgement["correct"]) == _as_written(point["label"]):
            judgement.update(result="right", alternatives=[], note="")
        # what is right is what was written, whatever the judge copied
        if judgement["result"] == "right":
            judgement["correct"] = point["label"]
    picture["judged"] = judged
    return [
        grade(
            judgement["result"],
            point["label"],
            "" if judgement["result"] == "right" else judgement["correct"],
            judgement["note"],
            f"Name what is marked at point {number} of a picture of {picture['scene']}",
        )
        for number, (judgement, point) in enumerate(zip(judged, points), start=1)
    ]


def written_on(picture: dict[str, Any]) -> dict[str, list[str]]:
    """What was written on a picture that was judged: the labels, by the
    learner, and what each that was not right should have been, by the
    model."""
    judged = picture.get("judged") or []
    return written(
        [point["label"] for point in picture["points"]],
        [
            judgement["correct"]
            for judgement in judged
            if judgement["result"] != "right" and judgement["correct"]
        ],
    )


def _show(state: dict[str, Any]) -> dict[str, Any]:
    picture = state["picture"]
    judged = picture.get("judged")
    return {
        "image": picture["image"],
        # the points as they were checked; none until then, as the
        # interface keeps them
        "points": [
            {**point, "feedback": judgement}
            for point, judgement in zip(picture["points"], judged or [])
        ],
        "judged": bool(judged),
        "most": MAX_POINTS,
        # which picture this is, from 1, of how many there are to be
        "picture": state["drawn"],
        "pictures": state["pictures"],
        # whether another picture follows once this one is checked
        "more": bool(judged) and state["drawn"] < state["pictures"],
    }


def _done(picture: dict[str, Any]) -> list[dict[str, Any]]:
    """What was named on a picture, and how it was judged, without the
    picture, which is large."""
    return [
        {**point, "judged": judgement}
        for point, judgement in zip(picture["points"], picture.get("judged") or [])
    ]


def start(context: dict[str, Any], model: Model) -> Step:
    picture = make_picture(context, model, [])
    state = {
        "pictures": context["instances"],
        "drawn": 1,
        "done": [],
        "scenes": [],
        "planned": [],
        "picture": picture,
    }
    return Step(state=state, show=_show(state), made=made_of(picture))


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    picture = state["picture"]
    if not isinstance(message, dict):
        return Step(state=state, show=_show(state))
    if message.get("check"):
        points = read_marks(message.get("points"))
        if picture.get("judged") or not points:
            return Step(state=state, show=_show(state))
        picture["points"] = points
        graded = judge(context, model, picture)
        return Step(
            state=state, show=_show(state), graded=graded, written=written_on(picture)
        )
    if message.get("prepare"):
        # the next picture drawn while this one is labelled, if there is one
        if state.get("upcoming") is None and state["drawn"] < state["pictures"]:
            state["upcoming"] = _following(context, model, state)
        return Step(state=state, show=_show(state))
    if message.get("next"):
        if not _show(state)["more"]:
            return Step(state=state, show=_show(state))
        following = state.pop("upcoming", None) or _following(context, model, state)
        state.update(
            scenes=_scenes_before(state),
            planned=_planned_before(state),
            done=state["done"] + _done(picture),
            picture=following,
            drawn=state["drawn"] + 1,
        )
        return Step(state=state, show=_show(state), made=made_of(following))
    return Step(state=state, show=_show(state))


def _scenes_before(state: dict[str, Any]) -> list[str]:
    """The scenes of every picture so far, this one with them."""
    scene = state["picture"]["scene"]
    return state["scenes"] + [scene] if scene else list(state["scenes"])


def _planned_before(state: dict[str, Any]) -> list[str]:
    """What was planned for every picture so far, this one with them."""
    planned: list[str] = state["planned"]
    return planned + [thing["thing"] for thing in state["picture"]["planned"]]


def _following(
    context: dict[str, Any], model: Model, state: dict[str, Any]
) -> dict[str, Any]:
    """The picture that follows this one. Raises ModelError."""
    return make_picture(
        context, model, _planned_before(state), _scenes_before(state), state["drawn"]
    )


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    # what was marked and not checked stayed in the interface, and is not graded
    done = state["done"] + _done(state["picture"])
    score = score_of([item["judged"]["result"] for item in done])
    return Step(
        state=state,
        results={"items": done, "pictures": state["drawn"]},
        scores=None if score is None else {"vocabulary": score},
    )


if __name__ == "__main__":
    serve(start, act, finish)
