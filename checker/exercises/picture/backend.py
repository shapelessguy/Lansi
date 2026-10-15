# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""A picture of a scene of the topic, with points on the things in it, each
of which the learner labels, and a model that sees the picture judges the
labels once the learner is done with them.

A picture is made in three asks: a model plans the scene and the things in
it, leaning on the words of the learner's vocabulary; an image model draws
it; and a model that sees pictures finds where each thing is in it. A thing
it cannot find is left out, so that no point is on nothing, and the picture
is never drawn again: if nothing is found, it is kept to be looked at again.

What a thing is called is never decided ahead: what was planned only shapes
the picture. The learner labels the points, changing them as they like, and
when they ask for the labels to be checked, the model that sees pictures is
shown the picture with each point marked by its number, and judges every
label by what is under it. Each point is logged then, a point left blank as
wrong. Each instance is a picture, drawn once the one before it is checked.
"""

from __future__ import annotations

import base64
import io
import json
import random
from typing import Any

from kit import (
    RESULTS,
    Model,
    ModelError,
    Step,
    ask_json,
    describe_guidance,
    describe_topics,
    log,
    loose,
    serve,
    written,
)
from PIL import Image, ImageDraw, ImageFont

# How many things are planned for a picture. Some may not be found in it,
# so that a few less are on it: pictures cost too much to be drawn again.
PLANNED = 14
# how far apart two points must be, out of 1000 across and down
MIN_APART = 40
# the most words of the learner's that the planning is told
SHOWN_WORDS = 60
ASPECT_RATIO = "4:3"
# how much of a reply that could not be read is told with why
MAX_SHOWN = 300
# the longest label that is kept
MAX_LABEL = 80
# how big a marker is drawn for the judge, as a part of the width
MARKER_SIZE = 0.024

PLANNING = """\
You plan a picture for someone learning {language} at level {level}: a \
drawing of one scene with things in it that the learner will label in \
{language}.

{topics}
{words}{guidance}
Choose a scene that fits the topics and has room for many things: a \
particular place and moment, rather than the first that comes to mind for \
the topic. Then choose \
{count} different things in it that are concrete objects, clearly visible, \
of a fair size and apart from one another, and whose names a learner at \
level {level} knows or should learn.{avoid}

For each thing, say in English what it is, for the illustrator, such as "a \
wooden kitchen table". For the scene, say in English what the picture shows, \
in one sentence that leaves the things out.

Reply with JSON alone: {{"scene": "A sunny kitchen seen from the door.", \
"things": ["a wooden kitchen table", "a red kettle"]}}"""

DRAWING = """\
{scene} In it, each clearly visible, once, and apart from the others: \
{things}. A clear, colourful illustration. No text, letters, labels or \
numbers."""

# The boxes are asked for as Gemini models are taught to give them, which
# they do far better than points.
LOCATING = """\
These are things that should be in the picture, numbered:
{things}

Detect each of them that is in the picture, and give its bounding box, tight \
around the thing itself, as "box_2d": [ymin, xmin, ymax, xmax], each from 0 \
to 1000 of the height or the width of the picture. Leave out a thing that is \
not in the picture, or that cannot be told apart from the others.

Reply with JSON alone: {{"boxes": [{{"n": 1, "box_2d": [520, 380, 700, 610]}}]}}"""

JUDGING = """\
Someone learning {language} at level {level} labelled the things in this \
picture. Each thing is marked with a numbered circle, and this is what they \
wrote for each, with what the illustrator meant to draw there:
{labels}

For each number, look at the thing under its circle, and judge what was \
written as its name in {language}:
- "right": a correct name of that thing, with the right article if \
{language} has articles. A capital first letter does not matter.
- "partial": the right word with a small mistake, such as in its article, a \
missing article, its spelling, umlauts or capitals; or a word so near in \
meaning that it is not quite the name of the thing.
- "wrong": not a name of that thing, or nothing written.

For each, give also "correct": the everyday name of the thing in {language}, \
in the singular, with its article if {language} has articles, or what was \
written if that is right; "translation": its name in {into}; and "note": in \
{into}, in a few words, what was not right, or "" if it was.

Reply with JSON alone: {{"labels": [{{"n": 1, "result": "partial", \
"correct": "der Pokal", "translation": "trophy", "note": "Preis is a prize, \
the cup is der Pokal."}}]}}"""


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
    return (
        "Some words the learner knows. Choose things that are named by these"
        f" words where they fit the scene:\n{lemmas}\n"
    )


def read_plan(reply: Any) -> tuple[str, list[dict[str, Any]]]:
    """The scene the model planned, and the things to be drawn in it, each
    once. Raises ModelError if there are none."""
    if not isinstance(reply, dict):
        raise ModelError("the model planned no picture")
    listed = reply.get("things")
    things: list[dict[str, Any]] = []
    for thing in listed if isinstance(listed, list) else []:
        if isinstance(thing, dict):
            thing = thing.get("thing")
        if not isinstance(thing, str) or not thing.strip():
            continue
        thing = " ".join(thing.split())
        if all(loose(thing) != loose(other["thing"]) for other in things):
            things.append({"thing": thing})
    if not things:
        raise ModelError("the model planned no thing to draw")
    scene = reply.get("scene")
    return scene.strip() if isinstance(scene, str) else "", things


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


def _shown(reply: Any) -> str:
    said = json.dumps(reply, ensure_ascii=False)
    return said[:MAX_SHOWN] + ("…" if len(said) > MAX_SHOWN else "")


def read_points(reply: Any, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The things that were found in the picture, each with where it is: the
    middle of its box. Those too near one found before them are left out.

    Models give them in more shapes than they are asked for: as a list or
    under any key, numbered or labelled by what the thing is, with a box or
    a point, out of 1000 or out of 1. All of these are read. Raises
    ModelError if none was found."""
    where: dict[int, tuple[int, int]] = {}
    for entry in _entries(reply, "boxes"):
        if not isinstance(entry, dict):
            continue
        index = _index_of(entry, items)
        middle = _middle_of(entry)
        if index is not None and middle is not None:
            where.setdefault(index, middle)
    found: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if index not in where:
            continue
        x, y = where[index]
        if any(
            abs(x - other["x"]) < MIN_APART and abs(y - other["y"]) < MIN_APART
            for other in found
        ):
            continue
        found.append({**item, "x": x, "y": y})
    if not found:
        raise ModelError(
            f"none of the things could be found in the picture: {_shown(reply)}"
        )
    return found


def _number(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _bare_thing(text: str) -> str:
    return loose(text.strip()).removeprefix("a ").removeprefix("an ")


def _index_of(entry: dict[str, Any], items: list[dict[str, Any]]) -> int | None:
    """Which of the `items` an entry of the reply is about, by its number
    or by what it is called, or None."""
    for key in ("n", "number", "index", "id", "label", "name", "thing"):
        number = _number(entry.get(key))
        if number is not None:
            return number - 1 if 1 <= number <= len(items) else None
    for key in ("label", "name", "thing"):
        label = entry.get(key)
        if not isinstance(label, str) or not label.strip():
            continue
        label = _bare_thing(label)
        for index, item in enumerate(items):
            if label == _bare_thing(item["thing"]):
                return index
        for index, item in enumerate(items):
            thing = _bare_thing(item["thing"])
            if label in thing or thing in label:
                return index
    return None


def _middle_of(entry: dict[str, Any]) -> tuple[int, int] | None:
    """The middle of the box or the point of an entry of the reply, as x
    and y out of 1000, or None."""
    box = next((entry[key] for key in ("box_2d", "box", "bbox") if key in entry), None)
    point = entry.get("point")
    if isinstance(box, list) and len(box) == 4:
        values = box
    elif isinstance(point, list) and len(point) == 2:
        # as Gemini models give a point, y first
        values = [point[0], point[1], point[0], point[1]]
    elif "x" in entry and "y" in entry:
        values = [entry["y"], entry["x"], entry["y"], entry["x"]]
    else:
        return None
    if not all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in values
    ):
        return None
    # out of 1, rather than out of 1000
    if all(0 <= value <= 1 for value in values) and any(
        isinstance(value, float) and 0 < value < 1 for value in values
    ):
        values = [value * 1000 for value in values]
    if not all(0 <= value <= 1000 for value in values):
        return None
    top, left, bottom, right = values
    if top > bottom or left > right:
        return None
    return round((left + right) / 2), round((top + bottom) / 2)


def make_picture(
    context: dict[str, Any],
    model: Model,
    drawn: list[str],
    scenes: list[str] | None = None,
) -> dict[str, Any]:
    """A picture with many things on it, of none of the `scenes` there were
    before and with none of the things `drawn` in them. Raises ModelError."""
    avoid = ""
    if scenes:
        avoid += (
            " The learner has had pictures of these scenes already; choose one"
            f" clearly different from all of them: {'; '.join(scenes)}."
        )
    if drawn:
        avoid += (
            " None of these may be in the picture, under any name, as the learner"
            f" has labelled them already: {'; '.join(drawn)}."
        )
    plan = PLANNING.format(
        language=context["language"],
        level=_level(context),
        topics=describe_topics(context),
        words=describe_words(context),
        guidance=describe_guidance(context),
        count=PLANNED,
        avoid=avoid,
    )
    try:
        scene, things = read_plan(ask_json(model, [{"role": "user", "content": plan}]))
    except ModelError as error:
        raise ModelError(f"planning the picture: {error}") from None
    listed = ", ".join(thing["thing"] for thing in things)
    image = model.draw(DRAWING.format(scene=scene, things=listed), ASPECT_RATIO)
    picture: dict[str, Any] = {
        "image": image,
        "scene": scene,
        "planned": things,
        "items": [],
        "labels": [],
        "judged": None,
    }
    # The picture cost far more than asking where things are in it, so that
    # this is asked again rather than the picture being lost: once now, and
    # whenever the learner asks after.
    locate(model, picture)
    if picture["lost"]:
        locate(model, picture)
    return picture


def locate(model: Model, picture: dict[str, Any]) -> None:
    """Find the things planned for a picture in it, or say in `lost` why
    they could not be."""
    numbered = "\n".join(
        f"{number}. {thing['thing']}"
        for number, thing in enumerate(picture["planned"], 1)
    )
    try:
        reply = ask_json(
            model,
            [_with_picture(LOCATING.format(things=numbered), picture["image"])],
            look=True,
        )
        found = read_points(reply, picture["planned"])
    except ModelError as error:
        picture["lost"] = f"finding the things in the picture: {error}"
        return
    picture.update(items=found, labels=[""] * len(found), lost="")


def _with_picture(text: str, image: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": image}},
        ],
    }


def marked(image: str, points: list[dict[str, Any]]) -> str:
    """The picture with a numbered circle on each point, as a data URL, for
    the judge to see what each label is of. Raises ModelError."""
    try:
        encoded = image.split(",", 1)[1]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as opened:
            picture = opened.convert("RGB")
    except (IndexError, ValueError, OSError):
        raise ModelError("the picture cannot be read") from None
    draw = ImageDraw.Draw(picture)
    radius = max(10, round(picture.width * MARKER_SIZE))
    font = ImageFont.load_default(size=round(radius * 1.2))
    for number, point in enumerate(points, 1):
        x = point["x"] * picture.width / 1000
        y = point["y"] * picture.height / 1000
        box = (x - radius, y - radius, x + radius, y + radius)
        draw.ellipse(box, fill=(220, 30, 60), outline="white", width=3)
        draw.text((x, y), str(number), fill="white", font=font, anchor="mm")
    out = io.BytesIO()
    picture.save(out, "JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def read_judgements(reply: Any, count: int) -> list[dict[str, str]]:
    """What the judge said of each of `count` labels, in order. Raises
    ModelError unless it judged every one."""
    judged: dict[int, dict[str, str]] = {}
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
        judged.setdefault(
            number - 1,
            {
                "result": result,
                "correct": " ".join(str(entry.get("correct") or "").split()),
                "translation": str(entry.get("translation") or ""),
                "note": str(entry.get("note") or ""),
            },
        )
    if len(judged) < count:
        raise ModelError(f"the model did not judge every label: {_shown(reply)}")
    return [judged[index] for index in range(count)]


def judge(
    context: dict[str, Any], model: Model, picture: dict[str, Any]
) -> list[dict[str, str]]:
    """Have the labels of a picture judged, keep the judgements on it, and
    return the logs of them: one for each point. Raises ModelError."""
    lines = []
    for number, (item, label) in enumerate(zip(picture["items"], picture["labels"]), 1):
        given = json.dumps(label, ensure_ascii=False) if label else "(nothing)"
        lines.append(f"{number}. {given} (the illustrator meant: {item['thing']})")
    prompt = JUDGING.format(
        language=context["language"],
        level=_level(context),
        labels="\n".join(lines),
        into=context["into"],
    )
    image = marked(picture["image"], picture["items"])
    reply = ask_json(model, [_with_picture(prompt, image)], look=True)
    judged = read_judgements(reply, len(picture["items"]))
    for judgement, label in zip(judged, picture["labels"]):
        # what is right is what was written, whatever the judge copied
        if judgement["result"] == "right" and label:
            judgement["correct"] = label
        if not label:
            judgement["result"] = "wrong"
    picture["judged"] = judged
    return [
        log(
            judgement["result"],
            label,
            "" if judgement["result"] == "right" else judgement["correct"],
            judgement["note"],
        )
        for judgement, label in zip(judged, picture["labels"])
    ]


def written_on(picture: dict[str, Any]) -> dict[str, list[str]]:
    """What was written on a picture that was judged: the labels, by the
    learner, and what each that was not right should have been, by the
    model."""
    judged = picture.get("judged") or []
    return written(
        [label for label in picture["labels"] if label],
        [
            judgement["correct"]
            for judgement in judged
            if judgement["result"] != "right" and judgement["correct"]
        ],
    )


def _show(state: dict[str, Any]) -> dict[str, Any]:
    picture = state["picture"]
    judged = picture.get("judged")
    points = []
    for index, (item, label) in enumerate(zip(picture["items"], picture["labels"])):
        points.append(
            {
                "x": item["x"],
                "y": item["y"],
                "label": label,
                "feedback": judged[index] if judged else None,
            }
        )
    lost = picture.get("lost") or ""
    return {
        "image": picture["image"],
        "points": points,
        # why no thing could be found on it, which may be looked for again
        "lost": lost,
        "judged": bool(judged),
        # which picture this is, from 1, of how many there are to be
        "picture": state["drawn"],
        "pictures": state["pictures"],
        # whether another picture follows once this one is checked
        "more": bool(judged) and state["drawn"] < state["pictures"],
    }


def _drawn(state: dict[str, Any]) -> list[str]:
    return [item["thing"] for item in state["done"]] + [
        item["thing"] for item in state["picture"]["items"]
    ]


def _done(picture: dict[str, Any]) -> list[dict[str, Any]]:
    """What was labelled on a picture, and how it was judged, without the
    picture, which is large."""
    judged = picture.get("judged") or [None] * len(picture["items"])
    return [
        {**item, "label": label, "judged": judgement}
        for item, label, judgement in zip(picture["items"], picture["labels"], judged)
    ]


def start(context: dict[str, Any], model: Model) -> Step:
    picture = make_picture(context, model, [])
    state = {
        "pictures": context["instances"],
        "drawn": 1,
        "done": [],
        "picture": picture,
    }
    return Step(state=state, show=_show(state))


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    picture = state["picture"]
    if not isinstance(message, dict):
        return Step(state=state, show=_show(state))
    if message.get("look"):
        if picture.get("lost"):
            locate(model, picture)
        return Step(state=state, show=_show(state))
    if message.get("check"):
        if picture.get("judged") or not any(picture["labels"]):
            return Step(state=state, show=_show(state))
        logs = judge(context, model, picture)
        return Step(
            state=state, show=_show(state), logs=logs, written=written_on(picture)
        )
    if message.get("next"):
        if not _show(state)["more"]:
            return Step(state=state, show=_show(state))
        scenes = state.get("scenes", []) + [picture.get("scene", "")]
        made = make_picture(context, model, _drawn(state), [s for s in scenes if s])
        state["scenes"] = scenes
        state["done"] += _done(picture)
        state["picture"] = made
        state["drawn"] += 1
        return Step(state=state, show=_show(state))
    point, text = message.get("point"), message.get("label")
    if (
        not isinstance(point, int)
        or not 0 <= point < len(picture["items"])
        or picture.get("judged")
        or not isinstance(text, str)
    ):
        return Step(state=state, show=_show(state))
    picture["labels"][point] = " ".join(text.split())[:MAX_LABEL]
    return Step(state=state, show=_show(state))


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    picture = state["picture"]
    logs: list[dict[str, str]] = []
    said: dict[str, list[str]] = {}
    # what was labelled and not checked is judged now, so that it is logged
    if not picture.get("judged") and any(picture["labels"]):
        try:
            logs = judge(context, model, picture)
            said = written_on(picture)
        except ModelError:
            pass
    done = state["done"] + _done(picture)
    return Step(
        state=state,
        logs=logs,
        results={"items": done, "pictures": state["drawn"]},
        written=said,
    )


if __name__ == "__main__":
    serve(start, act, finish)
