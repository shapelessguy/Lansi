# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What the chat asks of the models by way of the server, which the page
never asks itself: a chat request, passed on as it is and its reply passed
back as it comes, with what it used read off it on the way, and the models
OpenRouter has, with what each costs and how much context it takes.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import Any

from intake import read_usage
from models import Model
from profiling import Profile, ProfileError

# what OpenRouter lists the models of each kind by
KINDS = {
    "text": "output_modalities=text",
    "reasoning": "output_modalities=text&supported_parameters=reasoning",
    "vision": "input_modalities=image&output_modalities=text",
    "decisions": "output_modalities=decisions",
    "speech": "output_modalities=speech",
    "image": "output_modalities=image",
    "embeddings": "output_modalities=embeddings",
    # every model, for what is known of one
    "all": "",
}
# how long the models of a kind are listed again from what was had, in seconds
LISTED_FOR_SECS = 600
LIST_TIMEOUT_SECS = 10


class Watched:
    """What a reply of a chat model says it used, read off it as it is
    passed on: streamed, a piece at a time, or whole."""

    def __init__(self) -> None:
        self._rest = b""
        # the last piece that told the usage, and the id of the request,
        # which OpenRouter keeps what it used by
        self._told: dict[str, Any] | None = None
        self.generation = ""

    def feed(self, piece: bytes) -> None:
        """Take in a piece of a streamed reply, as events of the server."""
        *lines, self._rest = (self._rest + piece).split(b"\n")
        for line in lines:
            line = line.strip()
            if line.startswith(b"data:") and line[5:].strip() != b"[DONE]":
                self._take(line[5:])

    def whole(self, body: bytes) -> None:
        """Take in a reply that was not streamed."""
        self._take(body)

    def _take(self, data: bytes) -> None:
        try:
            told = json.loads(data)
        except ValueError:
            return
        if not isinstance(told, dict):
            return
        if isinstance(told.get("id"), str):
            self.generation = told["id"]
        if isinstance(told.get("usage"), dict):
            self._told = told

    def used(self, model: Model) -> Profile | None:
        """What the request used, or None if the reply has not said."""
        return read_usage(self._told, model.name) if self._told else None


class Listing:
    """The models OpenRouter has, by kind, each with what is known of it,
    listed again only once what was had is old. It can be used from several
    threads."""

    def __init__(self) -> None:
        self._listed: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    def models(self, kind: str) -> list[dict[str, Any]]:
        """The models of `kind`, one of KINDS, sorted by their ids. Raises
        ValueError for any other kind, and ProfileError."""
        if kind not in KINDS:
            raise ValueError(f"the kinds of model are {', '.join(KINDS)}")
        with self._lock:
            had = self._listed.get(kind)
        if had and time.monotonic() - had[0] < LISTED_FOR_SECS:
            return had[1]
        listed = list_openrouter(KINDS[kind])
        with self._lock:
            self._listed[kind] = (time.monotonic(), listed)
        return listed


def list_openrouter(query: str) -> list[dict[str, Any]]:
    """The models OpenRouter lists for `query`, which needs no key. Raises
    ProfileError."""
    path = f"models?{query}" if query else "models"
    try:
        with urllib.request.urlopen(
            Model().endpoint(path), timeout=LIST_TIMEOUT_SECS
        ) as response:
            data = json.load(response)["data"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ProfileError(
            f"could not list the models of OpenRouter: {error}"
        ) from None
    return sorted(
        (described(model) for model in data if isinstance(model, dict)),
        key=lambda model: model["id"],
    )


def described(model: dict[str, Any]) -> dict[str, Any]:
    """What the app is told of a model OpenRouter lists: its id, the voices
    it speaks in, how much context it takes, how much it writes at most, and
    what its tokens cost, in dollars each, with what is not known null."""
    pricing = model.get("pricing")
    pricing = pricing if isinstance(pricing, dict) else {}
    top = model.get("top_provider")
    top = top if isinstance(top, dict) else {}
    voices = model.get("supported_voices")
    return {
        "id": str(model.get("id") or ""),
        "voices": [each for each in voices if isinstance(each, str)]
        if isinstance(voices, list)
        else [],
        "contextLength": _count(model.get("context_length")),
        "maxOutput": _count(top.get("max_completion_tokens")),
        "promptPrice": _price(pricing.get("prompt")),
        "completionPrice": _price(pricing.get("completion")),
    }


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _price(value: object) -> float | None:
    try:
        return (
            float(value)
            if isinstance(value, (str, int, float)) and value != ""
            else None
        )
    except ValueError:
        return None
