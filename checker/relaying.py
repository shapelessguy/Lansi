# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What the chat asks of the models by way of the server, which the page
never asks itself: a chat request, passed on as it is and its reply passed
back as it comes, with what it used read off it on the way, and the models
OpenRouter has, with what each costs and how much context it takes, and the
providers that serve each, with what they ask for its tokens, how quick
they are and what of a request they take.
"""

from __future__ import annotations

import json
import re
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
# the id of a model on OpenRouter, such as deepseek/deepseek-v4-flash
MODEL_ID = re.compile(r"[\w.-]+/[\w.:-]+")


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
        # the providers of each model, by its id and whether a key asked
        self._served: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    def providers(self, model: str, key: str = "") -> list[dict[str, Any]]:
        """The providers OpenRouter has serve `model`, as `served_by`
        describes them, asked with the learner's `key` if there is one.
        Raises ValueError for what is no id of a model, and ProfileError."""
        if not MODEL_ID.fullmatch(model):
            raise ValueError(f"{model!r} is not the id of a model on OpenRouter")
        # what is listed without a key has less in it
        kept = f"{model} {'keyed' if key else 'open'}"
        with self._lock:
            had = self._served.get(kept)
        if had and time.monotonic() - had[0] < LISTED_FOR_SECS:
            return had[1]
        served = served_by(model, key)
        with self._lock:
            self._served[kept] = (time.monotonic(), served)
        return served

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


def served_by(model: str, key: str = "") -> list[dict[str, Any]]:
    """The providers that serve `model` on OpenRouter, each as `endpoint`
    describes it. The listing needs no key, but is asked with `key` if there
    is one, as without one it leaves out how quick each provider is. Raises
    ProfileError."""
    asked = Model(key=key)
    request = urllib.request.Request(
        asked.endpoint(f"models/{model}/endpoints"), headers=asked.headers()
    )
    try:
        with urllib.request.urlopen(request, timeout=LIST_TIMEOUT_SECS) as response:
            endpoints = json.load(response)["data"]["endpoints"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ProfileError(
            f"could not list the providers of {model}: {error}"
        ) from None
    listed = endpoints if isinstance(endpoints, list) else []
    return [
        endpoint(each)
        for each in listed
        if isinstance(each, dict) and (each.get("tag") or each.get("provider_name"))
    ]


def endpoint(listed: dict[str, Any]) -> dict[str, Any]:
    """What the app is told of a provider that serves a model: its `slug`,
    which a request names it by, such as deepinfra/fp8/flex, its name, which
    several of its endpoints share, what it asks for each token in
    and out, in dollars, the seconds to the first token and the tokens a
    second it wrote lately, the share of requests it answered lately,
    whether it takes tools and reasoning, how much context it takes and how
    its weights are stored, with what is not known null."""
    pricing = listed.get("pricing")
    pricing = pricing if isinstance(pricing, dict) else {}
    taken = listed.get("supported_parameters")
    taken = taken if isinstance(taken, list) else []
    latency = _typical(listed.get("latency_last_30m"))
    uptime = listed.get("uptime_last_30m")
    quantization = listed.get("quantization")
    return {
        "slug": str(listed.get("tag") or listed.get("provider_name")),
        "name": str(listed.get("provider_name") or listed.get("tag")),
        "promptPrice": _price(pricing.get("prompt")),
        "completionPrice": _price(pricing.get("completion")),
        # OpenRouter has it in milliseconds
        "latency": None if latency is None else latency / 1000,
        "throughput": _typical(listed.get("throughput_last_30m")),
        "uptime": float(uptime)
        if isinstance(uptime, (int, float)) and not isinstance(uptime, bool)
        else None,
        "tools": "tools" in taken,
        "reasoning": "reasoning" in taken,
        "contextLength": _count(listed.get("context_length")),
        "quantization": quantization if isinstance(quantization, str) else None,
    }


def _typical(value: object) -> float | None:
    """A figure OpenRouter gives as it is or by its percentiles, as the
    median."""
    if isinstance(value, dict):
        value = value.get("p50")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


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
