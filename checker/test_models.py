# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import pytest
from models import Model, read_model


def test_a_model_named_by_its_id_is_asked_on_openrouter_with_the_key() -> None:
    model = read_model("some/model", "the-key")

    assert model == Model("some/model", "", "the-key")
    assert model.endpoint("chat/completions") == (
        "https://openrouter.ai/api/v1/chat/completions"
    )
    assert model.headers() == {"Authorization": "Bearer the-key"}


def test_a_decision_model_on_openrouter_is_asked_where_openrouter_asks_them() -> None:
    assert Model("typesafe/jev").endpoint("decisions") == (
        "https://openrouter.ai/api/alpha/decisions"
    )


def test_a_model_at_an_address_is_asked_under_it_with_its_own_key_or_none() -> None:
    model = read_model(
        {"model": "jev", "url": "http://127.0.0.1:10000/v1/"}, "openrouter-key"
    )

    assert model == Model("jev", "http://127.0.0.1:10000/v1", "")
    assert model.endpoint("decisions") == "http://127.0.0.1:10000/v1/decisions"
    assert model.endpoint("audio/speech") == "http://127.0.0.1:10000/v1/audio/speech"
    assert model.headers() == {}
    assert model.problem() is None
    assert read_model({"model": "m", "url": "http://host/v1", "key": "k"}).key == "k"


def test_a_model_named_with_no_address_is_on_openrouter() -> None:
    assert read_model({"model": "some/model", "url": ""}, "the-key") == Model(
        "some/model", "", "the-key"
    )


def test_nothing_named_is_a_model_for_the_usual_one_to_be_used() -> None:
    model = read_model(None, "the-key")

    assert model.problem() == "no model was named"
    assert model.or_named("usual/model") == Model("usual/model", "", "the-key")
    assert read_model("", "the-key") == model


def test_a_model_on_openrouter_cannot_be_asked_without_a_key() -> None:
    assert Model("some/model").problem() == "an OpenRouter key is needed"
    assert not Model("some/model").has_key
    assert Model("some/model").or_keyed("kept") == Model("some/model", "", "kept")
    assert Model("m", "http://host/v1").or_keyed("kept").key == ""


@pytest.mark.parametrize(
    "named",
    [
        3,
        {"model": 3},
        {"model": "m", "url": "ftp://host"},
        {"model": "m", "url": "host:8000"},
    ],
)
def test_read_model_refuses_what_names_no_model(named: object) -> None:
    with pytest.raises(ValueError):
        read_model(named)
