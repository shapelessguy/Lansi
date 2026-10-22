# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json

import pytest
from models import Model
from relaying import Listing, Watched, described

MODEL = Model("thinker", key="key")


def test_the_usage_of_a_streamed_reply_is_read_off_it_across_its_pieces() -> None:
    watched = Watched()
    stream = (
        b'data: {"id": "gen-1", "choices": [{"delta": {"content": "Hi"}}]}\n\n'
        b": OPENROUTER PROCESSING\n\n"
        b'data: {"id": "gen-1", "choices": [], "model": "thinker-v2",'
        b' "usage": {"prompt_tokens": 9, "completion_tokens": 3, "cost": 0.01}}\n\n'
        b"data: [DONE]\n\n"
    )

    for start in range(0, len(stream), 7):
        watched.feed(stream[start : start + 7])
    used = watched.used(MODEL)

    assert used is not None
    assert (used.id, used.model) == ("gen-1", "thinker-v2")
    assert (used.input_tokens, used.output_tokens, used.cost) == (9, 3, 0.01)


def test_a_reply_cut_off_before_its_usage_has_only_the_id_to_look_it_up_by() -> None:
    watched = Watched()

    watched.feed(b'data: {"id": "gen-2", "choices": [{"delta": {"content": "H')
    watched.feed(b'i"}}]}\n\ndata: {"id": "gen-2", "cho')

    assert watched.used(MODEL) is None
    assert watched.generation == "gen-2"


def test_the_usage_of_a_reply_that_was_not_streamed_is_read_off_it_whole() -> None:
    watched = Watched()

    watched.whole(
        json.dumps(
            {"id": "gen-3", "usage": {"prompt_tokens": 4, "completion_tokens": 1}}
        ).encode()
    )
    used = watched.used(MODEL)

    assert used is not None
    assert (used.id, used.model, used.input_tokens) == ("gen-3", "thinker", 4)


def test_a_model_of_openrouter_is_described_with_what_is_not_known_null() -> None:
    model = {
        "id": "openai/gpt-5",
        "context_length": 400000,
        "pricing": {"prompt": "0.00000125", "completion": ""},
        "supported_voices": ["alloy", 3],
    }

    assert described(model) == {
        "id": "openai/gpt-5",
        "voices": ["alloy"],
        "contextLength": 400000,
        "maxOutput": None,
        "promptPrice": 0.00000125,
        "completionPrice": None,
    }


def test_a_kind_of_model_there_is_not_is_refused() -> None:
    with pytest.raises(ValueError):
        Listing().models("smells")
