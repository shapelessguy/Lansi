# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

from categories import Category, categories_of
from intake import mismatch
from vocabulary import Described, Form

from languages.english.categories import (
    ADJECTIVE,
    CATEGORIES,
    NOUN,
    PREPOSITION,
    PRONOUN,
    VERB,
)


def read(
    category: Category, reply: dict[str, Any]
) -> tuple[dict[str, Any], list[str], list[Form]]:
    """What is known of the one variant of a word, its translations and its forms."""
    (variant,) = category.read(reply)
    return variant.details, variant.translations, variant.forms


def verb(**changed: Any) -> dict[str, Any]:
    """A description of be, as a model would fill it in."""
    description = {
        "meanings": ["sein"],
        "present": "am / are",
        "third_person": "is",
        "past": "was / were",
        "past_participle": "been",
        "ing": "being",
    }
    return {**description, **changed}


def test_a_verb_is_stored_with_its_forms_and_each_spelling_of_one() -> None:
    details, meanings, forms = read(VERB, verb())

    assert (details, meanings) == ({}, ["sein"])
    assert forms == [
        Form("am", "present"),
        Form("are", "present"),
        Form("is", "3rd person singular"),
        Form("was", "past"),
        Form("were", "past"),
        Form("been", "past participle"),
        Form("being", "-ing"),
    ]


def test_a_modal_verb_is_stored_with_its_past_alone() -> None:
    _, _, forms = read(
        VERB,
        verb(present="", third_person="", past="could", past_participle="", ing=""),
    )

    assert forms == [Form("could", "past")]


def test_a_noun_not_counted_is_stored_without_a_plural() -> None:
    assert read(NOUN, {"meanings": ["Auskunft"], "plural": ""})[2] == []
    assert read(NOUN, {"meanings": ["Kind"], "plural": "children"})[2] == [
        Form("children", "plural")
    ]


def test_an_adjective_is_stored_with_its_degrees_if_they_are_one_word() -> None:
    _, _, forms = read(
        ADJECTIVE,
        {"meanings": ["gut"], "comparative": "better", "superlative": "best"},
    )

    assert forms == [Form("better", "comparative"), Form("best", "superlative")]


def test_a_pronoun_is_stored_with_the_forms_that_were_listed_for_it() -> None:
    _, _, forms = read(
        PRONOUN,
        {
            "meanings": ["er"],
            "forms": [
                {"form": "him", "tags": "object"},
                {"form": "his", "tags": " possessive "},
            ],
        },
    )

    assert forms == [Form("him", "object"), Form("his", "possessive")]


def test_a_preposition_has_one_form_only() -> None:
    assert PREPOSITION.read({"meanings": ["mit"]}) == [Described({}, ["mit"], [])]


def test_a_description_that_is_not_of_the_shape_is_told_from_one_that_is() -> None:
    assert mismatch(verb(), VERB.schema) is None
    assert mismatch({"meanings": ["sein"]}, VERB.schema) == "answer has no present"


def test_english_has_categories_of_its_own() -> None:
    assert categories_of("English") is CATEGORIES


def test_what_english_is_told_of_its_words_has_its_examples() -> None:
    assert "children" in NOUN.criterion
    assert "scissors" in NOUN.judging
    assert "learned / learnt" in NOUN.describing
    assert "short translations into the language" in VERB.describing
