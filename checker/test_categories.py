# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import pytest
from categories import (
    CATEGORIES,
    GENERIC,
    Schema,
    categories_of,
    dictionary_form,
)
from vocabulary import Form


def objects_of(schema: Schema) -> list[Schema]:
    """Every object a schema describes, however deep."""
    if schema["type"] == "array":
        return objects_of(schema["items"])
    if schema["type"] != "object":
        return []
    inner = [
        found
        for property_schema in schema["properties"].values()
        for found in objects_of(property_schema)
    ]
    return [schema, *inner]


@pytest.mark.parametrize("language", ["German", "Italian"])
def test_every_language_has_every_category_in_the_same_order(language: str) -> None:
    assert tuple(categories_of(language)) == CATEGORIES
    for name, category in categories_of(language).items():
        assert category.name == name
        # what a schema must be for a model to be held to it strictly
        for described in objects_of(category.schema):
            assert described["additionalProperties"] is False
            assert described["required"] == list(described["properties"])


def test_a_language_without_rules_of_its_own_has_the_general_ones() -> None:
    assert categories_of("Italian") is GENERIC
    assert dictionary_form("casa", "noun", "Italian") == "casa"


def test_a_word_of_a_language_without_rules_is_stored_with_the_forms_listed() -> None:
    details, forms = GENERIC["verb"].read(
        {
            "meanings": ["to speak"],
            "forms": [
                {"form": "parlo", "tags": "present 1st singular"},
                {"form": "parli", "tags": " present 2nd singular "},
                {"form": "", "tags": "nothing"},
            ],
        }
    )

    assert details == {"meanings": ["to speak"]}
    assert forms == [
        Form("parlo", "present 1st singular"),
        Form("parli", "present 2nd singular"),
    ]


def test_what_a_language_without_rules_is_told_names_no_language() -> None:
    for category in GENERIC.values():
        told = category.criterion + category.judging + category.describing
        assert "German" not in told
        assert not any(letter in told for letter in "äöüß")
