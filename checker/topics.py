# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The topics a session of practice is about: the icon each is shown with,
and the words of the vocabulary that fit them.

The icon is made by an image model when the topic is made. The words are
found with embeddings: every word of the vocabulary is embedded once, the
topics as they are used, and the words are ranked by how near they are to
the topics. The embeddings are kept, so that a word is only ever embedded
once by each model.
"""

from __future__ import annotations

import base64
import io
import math
import re
import threading
import uuid
from collections.abc import Callable, Iterable
from typing import Any

import numpy as np
from models import Model
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter
from profiling import Profile, ProfileError, post
from prompts import PROMPTS
from storage import UserStore

DEFAULT_IMAGE_MODEL = "google/gemini-3.1-flash-lite-image"
# one that knows many languages, as the words are of the one being learned
DEFAULT_EMBEDDING_MODEL = "baai/bge-m3"
# how many texts go to the embedding model in one request
EMBED_BATCH = 500
# the most words the exercises of a session are given
MAX_WORDS = 200
# How many words there must be to choose from for the exercises to use
# those they are given alone. With fewer, they lean on them and use others.
MIN_WORDS = 20
# how long an image or a batch of embeddings may take
TIMEOUT_SECS = 60
WITHIN_SECS = 180

# how big an icon is kept, on each side, in pixels; it is shown far smaller
ICON_SIZE = 256
# How far from white a colour of the background may be and still be taken
# away, out of 255 on each channel. Edges nearer white than this fade out.
WHITE_TOLERANCE = 40
# how much room is left around the symbol, as a part of the side
ICON_MARGIN = 0.04
# the most a picture of an exercise is sent at, on its longer side
PICTURE_SIZE = 1024
PICTURE_QUALITY = 82

# Sends a request body of the kind a path names, such as "images", to a
# model, and returns the decoded response. Raises ProfileError.
Send = Callable[[str, dict[str, Any], Model], dict[str, Any]]


def send_to_model(path: str, body: dict[str, Any], model: Model) -> dict[str, Any]:
    return post(
        model.endpoint(path),
        body,
        model.headers(),
        model.where,
        TIMEOUT_SECS,
        WITHIN_SECS,
    )


def topic_text(topic: dict[str, Any]) -> str:
    """A topic as it is embedded and described: its title, and what it is about."""
    if topic.get("description"):
        return f"{topic['title']}: {topic['description']}"
    return str(topic["title"])


def _usage(response: dict[str, Any], model: str) -> Profile:
    """What a request used, for whoever keeps count."""
    usage = response.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    cost = usage.get("cost")
    request_id = response.get("id")
    return Profile(
        {},
        cost=cost if isinstance(cost, (int, float)) else None,
        id=request_id if isinstance(request_id, str) else str(uuid.uuid4()),
        model=model,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
    )


def draw(
    prompt: str,
    model: Model,
    aspect_ratio: str = "1:1",
    send: Send = send_to_model,
) -> tuple[bytes, str, Profile]:
    """What the image `model` drew for `prompt`, as the bytes of an image
    with the kind of file it is, and what drawing it used. Raises
    ProfileError."""
    problem = model.problem()
    if problem:
        raise ProfileError(problem)
    body = {"model": model.name, "prompt": prompt, "aspect_ratio": aspect_ratio, "n": 1}
    try:
        response = send("images", body, model)
    except ProfileError as error:
        # a model that draws only some shapes draws the nearest it can
        nearest = _nearest_ratio(str(error), aspect_ratio)
        if nearest is None:
            raise
        response = send("images", {**body, "aspect_ratio": nearest}, model)
    try:
        image = response["data"][0]
        picture = base64.b64decode(image["b64_json"], validate=True)
    except (KeyError, IndexError, TypeError, ValueError):
        raise ProfileError("the image model sent no image") from None
    kind = image.get("media_type")
    return (
        picture,
        kind if isinstance(kind, str) else "image/png",
        _usage(response, model.name),
    )


def _nearest_ratio(refused: str, aspect_ratio: str) -> str | None:
    """Of the aspect ratios a request to draw was `refused` for not being
    one of, as OpenRouter says them, the nearest to `aspect_ratio`; None
    when it was refused for something else."""
    accepted = re.search(r"aspect_ratio\b.*?Accepted: ([\d:, ]+)", refused, re.S)
    ratios = re.findall(r"(\d+):(\d+)", accepted.group(1)) if accepted else []
    wanted = _ratio(aspect_ratio)
    if not ratios or wanted is None:
        return None
    width, height = min(
        ratios, key=lambda each: abs(math.log(int(each[0]) / int(each[1]) / wanted))
    )
    return None if f"{width}:{height}" == aspect_ratio else f"{width}:{height}"


def _ratio(aspect_ratio: str) -> float | None:
    found = re.fullmatch(r"(\d+):(\d+)", aspect_ratio)
    return int(found.group(1)) / int(found.group(2)) if found else None


def _open(picture: bytes) -> Image.Image:
    """A picture as Pillow has it, in RGB. Raises ProfileError."""
    try:
        with Image.open(io.BytesIO(picture)) as opened:
            return opened.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        raise ProfileError("the image model sent what is not an image") from None


def clear_background(picture: bytes, size: int = ICON_SIZE) -> bytes:
    """A symbol drawn on white as a PNG of the symbol alone: the white
    around it, that reaches the edges, made clear, and the symbol made to
    fill a square of `size`. Raises ProfileError."""
    image = _open(picture)
    # worked on at about the size it is kept at, and not at full size, as
    # the flood fill goes pixel by pixel
    image.thumbnail((size * 2, size * 2))
    pixels = np.asarray(image, dtype=np.int16)
    # how far each pixel is from white, by its furthest channel
    distance = (255 - pixels).max(axis=2)
    # copied, as an image over an array cannot be filled in
    near_white = Image.fromarray(
        np.where(distance <= WHITE_TOLERANCE, 255, 0).astype(np.uint8)
    ).copy()
    # the white that is reached from the edges, leaving that within the symbol
    width, height = near_white.size
    for x, y in (
        [(x, 0) for x in range(width)]
        + [(x, height - 1) for x in range(width)]
        + [(0, y) for y in range(height)]
        + [(width - 1, y) for y in range(height)]
    ):
        if near_white.getpixel((x, y)) == 255:
            ImageDraw.floodfill(near_white, (x, y), 128)
    background = np.asarray(near_white) == 128
    # the edge of the symbol fades as it nears white, so that it is not ragged
    edge = np.asarray(near_white.filter(ImageFilter.MaxFilter(3))) == 128
    faded = np.clip(distance * 255 // (WHITE_TOLERANCE * 2), 0, 255)
    alpha = np.where(background, 0, np.where(edge, faded, 255)).astype(np.uint8)
    clear = image.convert("RGBA")
    clear.putalpha(Image.fromarray(alpha))
    box = clear.getbbox(alpha_only=True)
    if box:
        clear = clear.crop(box)
    # made as big as the room there is, or as small
    inner = size * (1 - 2 * ICON_MARGIN)
    scale = inner / max(clear.width, clear.height)
    clear = clear.resize(
        (max(1, round(clear.width * scale)), max(1, round(clear.height * scale))),
        Image.Resampling.LANCZOS,
    )
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon.paste(clear, ((size - clear.width) // 2, (size - clear.height) // 2))
    out = io.BytesIO()
    icon.save(out, "PNG", optimize=True)
    return out.getvalue()


def as_picture(picture: bytes) -> str:
    """A picture as an exercise is given it: a JPEG no bigger than it needs
    to be, as a data URL. Raises ProfileError."""
    image = _open(picture)
    image.thumbnail((PICTURE_SIZE, PICTURE_SIZE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=PICTURE_QUALITY)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def make_icon(
    topic: dict[str, Any], model: Model, send: Send = send_to_model
) -> tuple[bytes, str, Profile]:
    """An icon for `topic`, as the bytes of a PNG of the symbol alone with
    the kind of file it is, and what making it used. Raises ProfileError."""
    picture, _, used = draw(
        PROMPTS("topics.icon", topic=topic_text(topic)), model, "1:1", send
    )
    return clear_background(picture), "image/png", used


class Embeddings:
    """The embeddings of texts, as each model made them: kept in the store,
    and held in memory once they are asked for."""

    def __init__(self, store: UserStore, send: Send = send_to_model) -> None:
        self._store = store
        self._send = send
        # by model, the vector of each text, as it is kept
        self._held: dict[str, dict[str, bytes]] = {}
        self._lock = threading.Lock()

    def _of(self, model: str) -> dict[str, bytes]:
        with self._lock:
            if model not in self._held:
                self._held[model] = self._store.embedded(model)
            return self._held[model]

    def missing(self, texts: Iterable[str], model: str) -> list[str]:
        """Those of `texts` that `model` has not embedded, each once."""
        held = self._of(model)
        return list(dict.fromkeys(text for text in texts if text not in held))

    def embed(
        self,
        texts: Iterable[str],
        model: Model,
        step: Callable[[], None] = lambda: None,
    ) -> list[Profile]:
        """Have those of `texts` embedded by `model` that are not yet, in
        batches, keeping each batch as it comes. `step` is called after
        each. Returns what the requests used. Raises ProfileError."""
        missing = self.missing(texts, model.name)
        problem = model.problem()
        if missing and problem:
            raise ProfileError(problem)
        used = []
        for start in range(0, len(missing), EMBED_BATCH):
            batch = missing[start : start + EMBED_BATCH]
            response = self._send(
                "embeddings",
                {"model": model.name, "input": batch, "encoding_format": "float"},
                model,
            )
            vectors = _read_vectors(response, len(batch))
            kept = {
                text: np.asarray(vector, dtype=np.float16).tobytes()
                for text, vector in zip(batch, vectors)
            }
            self._store.save_embeddings(model.name, kept)
            with self._lock:
                self._held.setdefault(model.name, {}).update(kept)
            used.append(_usage(response, model.name))
            step()
        return used

    def matrix(self, texts: list[str], model: str) -> NDArray[np.float32]:
        """The vectors of `texts`, one to a row, each of length 1. Every one
        of them must have been embedded."""
        held = self._of(model)
        rows = np.stack([np.frombuffer(held[text], dtype=np.float16) for text in texts])
        vectors = rows.astype(np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        normal: NDArray[np.float32] = vectors / np.where(norms == 0, 1, norms)
        return normal


def _read_vectors(response: dict[str, Any], count: int) -> list[list[float]]:
    """The vectors of an embedding response, in the order the texts were
    sent. Raises ProfileError."""
    data = response.get("data")
    if not isinstance(data, list) or len(data) != count:
        raise ProfileError("the embedding model did not embed every text")
    if all(
        isinstance(item, dict) and isinstance(item.get("index"), int) for item in data
    ):
        data = sorted(data, key=lambda item: item["index"])
    vectors = []
    for item in data:
        vector = item.get("embedding") if isinstance(item, dict) else None
        if not isinstance(vector, list) or not vector:
            raise ProfileError("the embedding model sent no vector")
        vectors.append(vector)
    return vectors


def rank(
    embeddings: Embeddings, topics: list[str], words: list[str], model: str
) -> list[tuple[str, float]]:
    """The `words` by how near they are to the `topics`, each with how near
    it is to the nearest topic. With several topics, they take turns, so
    that the first words are of all of them. Everything must have been
    embedded."""
    words = list(dict.fromkeys(words))
    if not words or not topics:
        return []
    near = embeddings.matrix(words, model) @ embeddings.matrix(topics, model).T
    best = near.max(axis=1)
    orders = [
        np.argsort(-near[:, column], kind="stable") for column in range(len(topics))
    ]
    ranked: list[tuple[str, float]] = []
    taken: set[int] = set()
    for place in range(len(words)):
        for order in orders:
            index = int(order[place])
            if index not in taken:
                taken.add(index)
                ranked.append((words[index], float(best[index])))
    return ranked


def choose_words(
    ranked: list[tuple[str, float]],
    limit: int = MAX_WORDS,
    minimum: int = MIN_WORDS,
) -> dict[str, Any]:
    """The words the exercises are to use, out of those ranked by how near
    they are to the topics: the first `limit` of them, to be used alone if
    there are `minimum` at least, and else to be preferred."""
    lemmas = [word for word, _ in ranked[:limit]]
    return {"mode": "only" if len(lemmas) >= minimum else "prefer", "lemmas": lemmas}
