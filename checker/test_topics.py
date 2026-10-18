# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

import pytest
import topics
from models import Model
from PIL import Image, ImageDraw
from profiling import ProfileError
from storage import UserStore
from topics import (
    ICON_SIZE,
    Embeddings,
    as_picture,
    choose_words,
    clear_background,
    make_icon,
    rank,
    topic_text,
)

KEY = "sk-test"
IMAGE_MODEL = Model("some/image-model", key=KEY)
EMBEDDING_MODEL = Model("m", key=KEY)
# Where each text is, as the fake embedding model sees it: the doctor's
# words point one way, the football words another.
VECTORS = {
    "Beim Arzt: symptoms": [1.0, 0.0, 0.0],
    "Fußball": [0.0, 1.0, 0.0],
    "der Arzt": [0.9, 0.1, 0.0],
    "krank": [0.8, 0.0, 0.2],
    "das Tor": [0.1, 0.95, 0.0],
    "der Ball": [0.0, 0.9, 0.3],
    "gehen": [0.3, 0.3, 0.9],
}


def symbol(size: int = 400) -> bytes:
    """A PNG of a symbol as an image model draws it: a teal ring, white
    within, small in the middle of a white page."""
    page = Image.new("RGB", (size, size), "white")
    draw = ImageDraw.Draw(page)
    quarter = size // 4
    draw.ellipse(
        (quarter, quarter, size - quarter, size - quarter), fill=(20, 150, 140)
    )
    draw.ellipse(
        (size // 2 - 20, size // 2 - 20, size // 2 + 20, size // 2 + 20), fill="white"
    )
    out = io.BytesIO()
    page.save(out, "PNG")
    return out.getvalue()


SYMBOL = symbol()


class FakeOpenRouter:
    """Answers the requests for images and embeddings in place of
    OpenRouter, and keeps what it was asked."""

    def __init__(self, image: object = SYMBOL) -> None:
        self.image = image
        self.asked: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, path: str, body: dict[str, Any], model: Model) -> dict[str, Any]:
        assert model.key == KEY
        self.asked.append((path, body))
        if path == "images":
            if not isinstance(self.image, bytes):
                return {"data": []}
            encoded = base64.b64encode(self.image).decode()
            return {
                "data": [{"b64_json": encoded, "media_type": "image/webp"}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 0, "cost": 0.004},
            }
        assert path == "embeddings"
        # sent back the wrong way round, as only the index tells them apart
        data = [
            {"index": index, "embedding": VECTORS.get(text, [0.0, 0.0, 1.0])}
            for index, text in enumerate(body["input"])
        ]
        return {"id": "gen-e", "data": data[::-1], "usage": {"prompt_tokens": 9}}

    def embedded(self) -> list[list[str]]:
        return [body["input"] for path, body in self.asked if path == "embeddings"]


DOCTOR = {"title": "Beim Arzt", "description": "symptoms"}


def test_a_topic_is_embedded_and_described_by_its_title_and_what_it_is_about() -> None:
    assert topic_text(DOCTOR) == "Beim Arzt: symptoms"
    assert topic_text({"title": "Fußball", "description": ""}) == "Fußball"


def test_an_icon_is_made_by_the_image_model_for_the_topic() -> None:
    send = FakeOpenRouter()

    icon, kind, used = make_icon(DOCTOR, IMAGE_MODEL, send)

    assert icon.startswith(b"\x89PNG")
    assert (kind, used.cost, used.model) == ("image/png", 0.004, "some/image-model")
    ((path, body),) = send.asked
    assert body["model"] == "some/image-model"
    assert body["aspect_ratio"] == "1:1"
    assert "Beim Arzt: symptoms" in body["prompt"]


def test_an_icon_is_the_symbol_alone_filling_it() -> None:
    icon = Image.open(io.BytesIO(clear_background(SYMBOL)))

    middle = ICON_SIZE // 2
    corner, within, edge = (
        icon.getpixel(where) for where in ((0, 0), (middle, middle), (middle, 16))
    )
    assert icon.size == (ICON_SIZE, ICON_SIZE) and icon.mode == "RGBA"
    # the white around the symbol is gone, the white within it is not
    assert isinstance(corner, tuple) and corner[3] == 0
    assert within == (255, 255, 255, 255)
    # the symbol reaches nearly to the edges
    assert edge == (20, 150, 140, 255)


def test_what_is_not_an_image_makes_no_icon() -> None:
    with pytest.raises(ProfileError, match="not an image"):
        clear_background(b"PNG")


def test_a_picture_for_an_exercise_is_a_jpeg_no_bigger_than_it_need_be() -> None:
    picture = as_picture(symbol(2000))

    assert picture.startswith("data:image/jpeg;base64,")
    image = Image.open(io.BytesIO(base64.b64decode(picture.split(",", 1)[1])))
    assert image.size == (1024, 1024)


def test_an_image_model_that_sends_no_image_is_a_failure() -> None:
    with pytest.raises(ProfileError, match="no image"):
        make_icon(DOCTOR, IMAGE_MODEL, FakeOpenRouter(image=None))


def test_no_icon_is_made_without_a_key() -> None:
    with pytest.raises(ProfileError, match="key"):
        make_icon(DOCTOR, Model("some/image-model"), FakeOpenRouter())


def test_each_text_is_embedded_once_in_batches_and_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(topics, "EMBED_BATCH", 2)
    send = FakeOpenRouter()
    store = UserStore(tmp_path / "ada")
    steps: list[None] = []

    used = Embeddings(store, send).embed(
        ["der Arzt", "krank", "das Tor", "krank"],
        EMBEDDING_MODEL,
        lambda: steps.append(None),
    )
    again = Embeddings(UserStore(tmp_path / "ada"), send)

    assert send.embedded() == [["der Arzt", "krank"], ["das Tor"]]
    assert (len(used), len(steps)) == (2, 2)
    assert again.missing(["der Arzt", "der Ball"], "m") == ["der Ball"]
    assert again.missing(["der Arzt"], "another/model") == ["der Arzt"]
    assert again.embed(["krank"], EMBEDDING_MODEL) == []


def test_texts_that_are_embedded_already_need_no_key(tmp_path: Path) -> None:
    embeddings = Embeddings(UserStore(tmp_path / "ada"), FakeOpenRouter())
    embeddings.embed(["krank"], EMBEDDING_MODEL)

    assert embeddings.embed(["krank"], Model("m")) == []
    with pytest.raises(ProfileError, match="key"):
        embeddings.embed(["gehen"], Model("m"))


def test_an_embedding_model_that_leaves_a_text_out_is_a_failure(tmp_path: Path) -> None:
    def short(path: str, body: dict[str, Any], model: Model) -> dict[str, Any]:
        return {"data": [{"embedding": [1.0]}]}

    with pytest.raises(ProfileError, match="every text"):
        Embeddings(UserStore(tmp_path / "ada"), short).embed(
            ["a", "b"], EMBEDDING_MODEL
        )


def embedded(tmp_path: Path, texts: list[str]) -> Embeddings:
    embeddings = Embeddings(UserStore(tmp_path / "ada"), FakeOpenRouter())
    embeddings.embed(texts, EMBEDDING_MODEL)
    return embeddings


WORDS = ["gehen", "das Tor", "krank", "der Ball", "der Arzt"]


def test_words_are_ranked_by_how_near_they_are_to_the_topic(tmp_path: Path) -> None:
    embeddings = embedded(tmp_path, [*WORDS, "Beim Arzt: symptoms"])

    ranked = rank(embeddings, ["Beim Arzt: symptoms"], WORDS, "m")

    assert [word for word, _ in ranked] == [
        "der Arzt",
        "krank",
        "gehen",
        "das Tor",
        "der Ball",
    ]
    assert ranked[0][1] == pytest.approx(0.9 / (0.81 + 0.01) ** 0.5, abs=1e-3)


def test_the_words_of_several_topics_take_turns(tmp_path: Path) -> None:
    embeddings = embedded(tmp_path, [*WORDS, "Beim Arzt: symptoms", "Fußball"])

    ranked = rank(embeddings, ["Beim Arzt: symptoms", "Fußball"], WORDS, "m")

    assert [word for word, _ in ranked][:4] == [
        "der Arzt",
        "das Tor",
        "krank",
        "der Ball",
    ]
    assert len(ranked) == len(WORDS)


def test_without_a_topic_or_a_word_nothing_is_ranked(tmp_path: Path) -> None:
    embeddings = embedded(tmp_path, WORDS)

    assert rank(embeddings, [], WORDS, "m") == []
    assert rank(embeddings, ["Fußball"], [], "m") == []


RANKED = [("der Arzt", 0.9), ("krank", 0.7), ("gehen", 0.4), ("das Tor", 0.1)]


def test_the_first_words_are_used_alone_when_there_are_enough() -> None:
    assert choose_words(RANKED, limit=2, minimum=2) == {
        "mode": "only",
        "lemmas": ["der Arzt", "krank"],
    }


def test_the_words_are_preferred_when_there_are_too_few_to_use_them_alone() -> None:
    assert choose_words(RANKED, minimum=5) == {
        "mode": "prefer",
        "lemmas": ["der Arzt", "krank", "gehen", "das Tor"],
    }
