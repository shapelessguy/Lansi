# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from categories import (
    ADJECTIVE,
    ADVERB,
    CATEGORIES,
    CONJUNCTION,
    GENERIC,
    NOUN,
    PREPOSITION,
    PRONOUN,
    VERB,
    Schema,
    categories_of,
    writes_nouns_with_capitals,
)
from intake import mismatch
from vocabulary import Form

PERSONS = ("ich", "du", "er", "wir", "ihr", "sie")


def table(*forms: str) -> dict[str, str]:
    return dict(zip(PERSONS, forms))


def verb(**changed: Any) -> dict[str, Any]:
    """A description of gehen, as a model would fill it in."""
    description = {
        "meanings": ["to go", "to walk"],
        "auxiliary": "sein",
        "separable": False,
        "reflexive": "never",
        "zu_infinitive": "zu gehen",
        "partizip_1": "gehend",
        "partizip_2": "gegangen",
        "praesens": table("gehe", "gehst", "geht", "gehen", "geht", "gehen"),
        "praeteritum": table("ging", "gingst", "ging", "gingen", "gingt", "gingen"),
        "konjunktiv_1": table("gehe", "gehest", "gehe", "gehen", "gehet", "gehen"),
        "konjunktiv_2": table("ginge", "gingest", "ginge", "gingen", "ginget", ""),
        "imperativ": {"du": "geh", "ihr": "geht"},
    }
    return {**description, **changed}


def spellings(forms: list[Form]) -> set[str]:
    return {form.form for form in forms}


def test_a_verb_is_stored_with_each_person_of_each_tense_and_its_participles() -> None:
    details, forms = VERB.read(verb())

    assert details == {
        "meanings": ["to go", "to walk"],
        "auxiliary": "sein",
        "separable": False,
        "reflexive": "never",
    }
    assert Form("gingst", "präteritum du") in forms
    assert Form("gegangen", "partizip II") in forms
    assert Form("geh", "imperativ du") in forms
    # one spelling is kept for each form it is
    assert [form.tags for form in forms if form.form == "ging"] == [
        "präteritum ich",
        "präteritum er",
    ]


def test_a_form_a_verb_does_not_have_is_left_out() -> None:
    _, forms = VERB.read(verb())

    assert "" not in spellings(forms)
    assert "konjunktiv II sie" not in {form.tags for form in forms}


def test_a_separable_verb_is_stored_split_and_as_it_is_at_the_end_of_a_clause() -> None:
    _, forms = VERB.read(
        verb(
            separable=True,
            praesens=table(
                "rufe an", "rufst an", "ruft an", "rufen an", "ruft an", "rufen an"
            ),
            imperativ={"du": "ruf an", "ihr": "ruft an"},
        )
    )

    assert Form("rufe an", "präsens ich") in forms
    assert Form("anrufe", "präsens ich nebensatz") in forms
    # there is no such form of the imperative
    assert "anruf" not in spellings(forms)


def test_a_noun_is_stored_with_every_gender_it_has_and_the_cases_of_each() -> None:
    def declined(singular: str, genitive: str, plural: str, dative: str) -> Any:
        return {
            "singular": {
                "nominativ": singular,
                "genitiv": genitive,
                "dativ": singular,
                "akkusativ": singular,
            },
            "plural": {
                "nominativ": plural,
                "genitiv": plural,
                "dativ": dative,
                "akkusativ": plural,
            },
        }

    details, forms = NOUN.read(
        {
            "genders": [
                {
                    "article": "der",
                    "meanings": ["volume"],
                    **declined("Band", "Bandes", "Bände", "Bänden"),
                },
                {
                    "article": "das",
                    "meanings": ["ribbon", "tape"],
                    **declined("Band", "Bandes", "Bänder", "Bändern"),
                },
                {
                    "article": "die",
                    "meanings": ["band"],
                    **declined("Band", "Band", "Bands", "Bands"),
                },
            ]
        }
    )

    assert details == {
        "genders": [
            {"article": "der", "meanings": ["volume"], "plural": "Bände"},
            {"article": "das", "meanings": ["ribbon", "tape"], "plural": "Bänder"},
            {"article": "die", "meanings": ["band"], "plural": "Bands"},
        ]
    }
    assert Form("Bändern", "das dativ plural") in forms
    assert Form("Bänden", "der dativ plural") in forms
    assert Form("Bands", "die nominativ plural") in forms


def test_an_adjective_is_stored_with_every_ending_of_each_degree() -> None:
    details, forms = ADJECTIVE.read(
        {
            "meanings": ["high", "tall"],
            "comparative": "höher",
            "positive_inflected": "hohe",
            "comparative_inflected": "höhere",
            "superlative_inflected": "höchste",
        }
    )

    assert details == {"meanings": ["high", "tall"]}
    assert spellings(forms) >= {
        "höher",
        *("hohe", "hoher", "hohes", "hohen", "hohem"),
        *("höhere", "höherer", "höheres", "höheren", "höherem"),
        *("höchste", "höchster", "höchstes", "höchsten", "höchstem"),
    }
    assert Form("höchsten", "superlativ -en") in forms


def test_an_adjective_without_endings_or_degrees_is_stored_as_it_is() -> None:
    _, forms = ADJECTIVE.read(
        {
            "meanings": ["purple"],
            "comparative": "",
            "positive_inflected": "lila",
            "comparative_inflected": "",
            "superlative_inflected": "",
        }
    )

    assert forms == [Form("lila", "positiv")]


def test_the_superlative_of_an_adverb_is_stored_with_and_without_am() -> None:
    _, forms = ADVERB.read(
        {"meanings": ["gladly"], "comparative": "lieber", "superlative": "am liebsten"}
    )

    assert spellings(forms) == {"lieber", "am liebsten", "liebsten"}


def test_a_pronoun_is_stored_with_the_forms_that_were_listed_for_it() -> None:
    details, forms = PRONOUN.read(
        {
            "meanings": ["I"],
            "forms": [
                {"form": "mich", "tags": "akkusativ"},
                {"form": " mir ", "tags": " dativ "},
                {"form": "", "tags": "genitiv"},
            ],
        }
    )

    assert details == {"meanings": ["I"]}
    assert forms == [Form("mich", "akkusativ"), Form("mir", "dativ")]


def test_a_preposition_is_stored_with_its_cases_and_fused_with_articles() -> None:
    details, forms = PREPOSITION.read(
        {"meanings": ["to"], "cases": ["dativ"], "contractions": ["zum", "zur"]}
    )

    assert details == {"meanings": ["to"], "cases": ["dativ"]}
    assert forms == [Form("zum", "contraction"), Form("zur", "contraction")]


def test_a_word_with_one_form_is_stored_with_its_meanings_only() -> None:
    assert CONJUNCTION.read({"meanings": ["because"]}) == (
        {"meanings": ["because"]},
        [],
    )


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


@pytest.mark.parametrize("name", CATEGORIES)
def test_the_shape_of_a_category_leaves_a_model_no_room(name: str) -> None:
    # what a schema must be for a model to be held to it strictly
    for described in objects_of(CATEGORIES[name].schema):
        assert described["additionalProperties"] is False
        assert described["required"] == list(described["properties"])


def test_a_description_that_is_not_of_the_shape_is_told_from_one_that_is() -> None:
    assert mismatch(verb(), VERB.schema) is None
    assert mismatch(verb(auxiliary="werden"), VERB.schema) == (
        "answer.auxiliary is not one of haben, sein, haben or sein"
    )
    assert mismatch(verb(praesens={"ich": "gehe"}), VERB.schema) == (
        "answer.praesens has no du"
    )
    assert mismatch(verb(meanings=["to go", 3]), VERB.schema) == (
        "answer.meanings[1] is not text"
    )
    assert mismatch(verb(separable="no"), VERB.schema) == (
        "answer.separable is not true or false"
    )
    assert mismatch([], VERB.schema) == "answer is not an object"


def test_a_form_given_in_two_spellings_is_stored_as_two_forms() -> None:
    _, noun_forms = NOUN.read(
        {
            "genders": [
                {
                    "article": "das",
                    "meanings": ["product"],
                    "singular": {
                        "nominativ": "Produkt",
                        "genitiv": "Produkts / Produktes",
                        "dativ": "Produkt",
                        "akkusativ": "Produkt",
                    },
                    "plural": dict.fromkeys(
                        ("nominativ", "genitiv", "dativ", "akkusativ"), ""
                    ),
                }
            ]
        }
    )
    _, verb_forms = VERB.read(
        verb(
            separable=True,
            praesens=table("fange an", "fängst an", "", "", "", ""),
            imperativ={"du": "fang an / fange an", "ihr": ""},
        )
    )
    _, adjective_forms = ADJECTIVE.read(
        {
            "meanings": ["dear"],
            "comparative": "teurer",
            "positive_inflected": "teure/teuere",
            "comparative_inflected": "",
            "superlative_inflected": "",
        }
    )
    _, adverb_forms = ADVERB.read(
        {"meanings": ["gladly"], "comparative": "", "superlative": "am liebsten"}
    )

    assert Form("Produkts", "das genitiv singular") in noun_forms
    assert Form("Produktes", "das genitiv singular") in noun_forms
    assert Form("fang an", "imperativ du") in verb_forms
    assert Form("fange an", "imperativ du") in verb_forms
    assert {"teuren", "teueren"} <= spellings(adjective_forms)
    assert spellings(adverb_forms) == {"am liebsten", "liebsten"}
    assert not any("/" in form.form for form in noun_forms + verb_forms)


def test_german_has_rules_of_its_own_and_any_other_language_the_general_ones() -> None:
    assert categories_of("German") is CATEGORIES
    assert categories_of(" german ") is CATEGORIES
    assert categories_of("Italian") is GENERIC
    assert list(GENERIC) == list(CATEGORIES)
    assert writes_nouns_with_capitals("German")
    assert not writes_nouns_with_capitals("Italian")


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
    assert "German" not in GENERIC["verb"].criterion + GENERIC["verb"].judging
