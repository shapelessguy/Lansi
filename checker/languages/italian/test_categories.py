# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

from categories import Category, categories_of
from intake import mismatch
from vocabulary import Described, Form

from languages.italian import LANGUAGE
from languages.italian.categories import (
    ADJECTIVE,
    ADVERB,
    CATEGORIES,
    CONJUNCTION,
    NOUN,
    PREPOSITION,
    PRONOUN,
    VERB,
)

PERSONS = ("io", "tu", "lui", "noi", "voi", "loro")


def read(
    category: Category, reply: dict[str, Any]
) -> tuple[dict[str, Any], list[str], list[Form]]:
    """What is known of the one variant of a word, its translations and its forms."""
    (variant,) = category.read(reply)
    return variant.details, variant.translations, variant.forms


def table(*forms: str) -> dict[str, str]:
    return dict(zip(PERSONS, forms))


def verb(**changed: Any) -> dict[str, Any]:
    """A description of andare, as a model would fill it in."""
    description = {
        "meanings": ["to go"],
        "auxiliary": "essere",
        "reflexive": "never",
        "gerundio": "andando",
        "participio_passato": "andato",
        "presente": table("vado / vo", "vai", "va", "andiamo", "andate", "vanno"),
        "imperfetto": table(
            "andavo", "andavi", "andava", "andavamo", "andavate", "andavano"
        ),
        "passato_remoto": table(
            "andai", "andasti", "andò", "andammo", "andaste", "andarono"
        ),
        "futuro": table("andrò", "andrai", "andrà", "andremo", "andrete", "andranno"),
        "congiuntivo_presente": table(
            "vada", "vada", "vada", "andiamo", "andiate", "vadano"
        ),
        "congiuntivo_imperfetto": table(
            "andassi", "andassi", "andasse", "andassimo", "andaste", "andassero"
        ),
        "condizionale": table(
            "andrei", "andresti", "andrebbe", "andremmo", "andreste", "andrebbero"
        ),
        "imperativo": {"tu": "va' / vai", "noi": "andiamo", "voi": "andate"},
    }
    return {**description, **changed}


def spellings(forms: list[Form]) -> set[str]:
    return {form.form for form in forms}


def test_a_verb_is_stored_with_each_person_of_each_tense_and_its_participle() -> None:
    details, meanings, forms = read(VERB, verb())

    assert details == {"auxiliary": "essere", "reflexive": "never"}
    assert meanings == ["to go"]
    assert Form("vado", "presente io") in forms
    assert Form("vo", "presente io") in forms
    assert Form("andò", "passato remoto lui") in forms
    assert Form("vadano", "congiuntivo presente loro") in forms
    assert Form("andrebbero", "condizionale loro") in forms
    assert Form("va'", "imperativo tu") in forms
    assert Form("andando", "gerundio") in forms
    assert {
        form.form for form in forms if form.tags.startswith("participio passato")
    } == {"andato", "andata", "andati", "andate"}
    assert Form("andate", "participio passato femminile plurale") in forms


def test_a_noun_has_a_variant_for_each_gender_and_plural() -> None:
    variants = NOUN.read(
        {
            "variants": [
                {
                    "gender": "maschile",
                    "meanings": ["arm"],
                    "singular": "braccio",
                    "plural": "braccia",
                    "plural_gender": "femminile",
                },
                {
                    "gender": "maschile",
                    "meanings": ["branch", "arm of a lamp"],
                    "singular": "braccio",
                    "plural": "bracci",
                    "plural_gender": "maschile",
                },
            ]
        }
    )

    assert [variant.forms for variant in variants] == [
        [Form("braccio", "maschile singolare"), Form("braccia", "femminile plurale")],
        [Form("braccio", "maschile singolare"), Form("bracci", "maschile plurale")],
    ]


def test_an_adjective_is_stored_in_each_gender_and_number_and_degree() -> None:
    _, _, forms = read(
        ADJECTIVE,
        {
            "meanings": ["good"],
            "maschile_singolare": "buono",
            "maschile_plurale": "buoni",
            "femminile_singolare": "buona",
            "femminile_plurale": "buone",
            "comparativo": "migliore",
            "superlativo": "buonissimo / ottimo",
        },
    )

    assert Form("buone", "femminile plurale") in forms
    assert Form("migliori", "comparativo plurale") in forms
    assert Form("ottime", "superlativo femminile plurale") in forms
    assert Form("buonissima", "superlativo femminile singolare") in forms


def test_an_adjective_that_does_not_change_is_stored_once_for_each_use() -> None:
    _, _, forms = read(
        ADJECTIVE,
        {
            "meanings": ["blue"],
            **dict.fromkeys(
                (
                    "maschile_singolare",
                    "maschile_plurale",
                    "femminile_singolare",
                    "femminile_plurale",
                ),
                "blu",
            ),
            "comparativo": "",
            "superlativo": "",
        },
    )

    assert spellings(forms) == {"blu"} and len(forms) == 4


def test_the_degrees_of_an_adverb_are_stored_if_it_has_them() -> None:
    _, _, forms = read(
        ADVERB,
        {"meanings": ["well"], "comparativo": "meglio", "superlativo": "benissimo"},
    )

    assert forms == [Form("meglio", "comparativo"), Form("benissimo", "superlativo")]


def test_a_pronoun_is_stored_with_the_forms_that_were_listed_for_it() -> None:
    _, _, forms = read(
        PRONOUN,
        {
            "meanings": ["he"],
            "forms": [
                {"form": "lo", "tags": "oggetto diretto"},
                {"form": "gli", "tags": " oggetto indiretto "},
            ],
        },
    )

    assert forms == [Form("lo", "oggetto diretto"), Form("gli", "oggetto indiretto")]


def test_a_preposition_is_stored_fused_with_the_articles() -> None:
    _, _, forms = read(
        PREPOSITION, {"meanings": ["of"], "contractions": ["del", "dell'"]}
    )

    assert forms == [Form("del", "articolata"), Form("dell'", "articolata")]


def test_a_word_with_one_form_is_stored_with_its_meanings_only() -> None:
    assert CONJUNCTION.read({"meanings": ["because"]}) == [
        Described({}, ["because"], [])
    ]


def test_a_description_that_is_not_of_the_shape_is_told_from_one_that_is() -> None:
    assert mismatch(verb(), VERB.schema) is None
    assert mismatch(verb(auxiliary="haben"), VERB.schema) == (
        "answer.auxiliary is not one of avere, essere, avere o essere"
    )
    assert mismatch(verb(presente={"io": "vado"}), VERB.schema) == (
        "answer.presente has no tu"
    )


def test_what_is_stored_of_an_italian_word_is_known_to_the_language() -> None:
    known = LANGUAGE.details()
    details, _, _ = read(VERB, verb(auxiliary="avere o essere", reflexive="always"))

    assert all(value in known[name] for name, value in details.items())


def test_italian_has_categories_of_its_own() -> None:
    assert categories_of("Italian") is CATEGORIES
    assert categories_of(" italian ") is CATEGORIES


def test_what_italian_is_told_of_its_words_has_its_examples() -> None:
    assert "uomini" in NOUN.criterion
    assert "le braccia" in NOUN.judging
    assert "devo / debbo" in NOUN.describing
    assert "short translations into the language" in VERB.describing
