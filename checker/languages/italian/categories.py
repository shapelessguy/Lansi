# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The categories of the words of Italian, as categories.py describes them:
what is stored of a word of each, and how a model is told about it, which
is in prompts/categories/ here."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from categories import (
    MEANINGS,
    PRACTISED,
    TEXT,
    Category,
    Description,
    Schema,
    one_of,
    present,
    several,
    shape,
    spellings,
)
from prompts import PROMPTS, Prompts
from vocabulary import Described, Form

from languages.italian import LANGUAGE

# The names of what is stored of a word, with the values each can have, as
# tables.json has them: nothing else is stored.
DETAILS = LANGUAGE.details()

# what the models are told of Italian
ITALIAN_PROMPTS = Prompts(Path(__file__).resolve().with_name("prompts"))


def _told(name: str) -> str:
    """A prompt of prompts/categories/, with the rules it uses."""
    return ITALIAN_PROMPTS(
        f"categories.{name}",
        meanings_rule=PROMPTS("categories.rules.meanings"),
        empty_rule=ITALIAN_PROMPTS("categories.rules.empty"),
        listing=ITALIAN_PROMPTS("categories.rules.listing"),
    )


def _italian(
    name: str,
    schema: Schema,
    read: Callable[[dict[str, Any]], Description],
    rules: str = "",
) -> Category:
    """A category of Italian, as the prompts of prompts/categories/ tell it,
    judged and described by the rules of `rules` if it has none of its own."""
    told = rules or name
    return Category(
        name,
        _told(f"criteria.{name}"),
        _told(f"judging.{told}"),
        _told(f"describing.{told}"),
        schema,
        read,
        practised=name in PRACTISED,
    )


GENDERS = ("maschile", "femminile")
NUMBERS = ("singolare", "plurale")


def _in_every_gender(word: str, tag: str) -> list[Form]:
    """A word that ends as a masculine singular in -o in its four genders
    and numbers, each tagged with `tag` and which it is; the word alone,
    tagged with `tag`, if it does not."""
    if not word.endswith("o"):
        return [Form(word, tag)]
    stem = word[:-1]
    return [
        Form(stem + end, f"{tag} {gender} {number}")
        for (gender, number), end in (
            (("maschile", "singolare"), "o"),
            (("femminile", "singolare"), "a"),
            (("maschile", "plurale"), "i"),
            (("femminile", "plurale"), "e"),
        )
    ]


# nouns

NOUN_SCHEMA = shape(
    variants=several(
        shape(
            gender=one_of(*GENDERS),
            meanings=MEANINGS,
            singular=TEXT,
            plural=TEXT,
            plural_gender=one_of(*GENDERS),
        )
    )
)


def read_noun(reply: dict[str, Any]) -> Description:
    """A noun has a variant for each gender and plural it is used with,
    which its forms say: il fine and la fine are two, and so are il braccio
    with the plural le braccia and il braccio with i bracci."""
    return [
        Described(
            {},
            variant["meanings"],
            present(
                [
                    Form(variant["singular"], f"{variant['gender']} singolare"),
                    Form(variant["plural"], f"{variant['plural_gender']} plurale"),
                ]
            ),
        )
        for variant in reply["variants"]
    ]


NOUN = _italian("noun", NOUN_SCHEMA, read_noun)

# verbs

PERSONS = ("io", "tu", "lui", "noi", "voi", "loro")
_CONJUGATION = shape(**dict.fromkeys(PERSONS, TEXT))
# the tables of a verb, each by the tag its forms are stored with
TENSES = {
    "presente": "presente",
    "imperfetto": "imperfetto",
    "passato_remoto": "passato remoto",
    "futuro": "futuro",
    "congiuntivo_presente": "congiuntivo presente",
    "congiuntivo_imperfetto": "congiuntivo imperfetto",
    "condizionale": "condizionale",
}

VERB_SCHEMA = shape(
    meanings=MEANINGS,
    auxiliary=one_of(*DETAILS["auxiliary"]),
    reflexive=one_of(*DETAILS["reflexive"]),
    gerundio=TEXT,
    participio_passato=TEXT,
    **dict.fromkeys(TENSES, _CONJUGATION),
    imperativo=shape(tu=TEXT, noi=TEXT, voi=TEXT),
)


def read_verb(reply: dict[str, Any]) -> Description:
    details = {name: reply[name] for name in ("auxiliary", "reflexive")}
    forms = [Form(reply["gerundio"], "gerundio")]
    for participle in spellings(reply["participio_passato"]):
        # andato, andata, andati, andate
        forms += _in_every_gender(participle, "participio passato")
    for name, tag in TENSES.items():
        for person in PERSONS:
            forms.append(Form(reply[name][person], f"{tag} {person}"))
    for person in ("tu", "noi", "voi"):
        forms.append(Form(reply["imperativo"][person], f"imperativo {person}"))
    return [Described(details, reply["meanings"], present(forms))]


VERB = _italian("verb", VERB_SCHEMA, read_verb)

# adjectives

ADJECTIVE_SCHEMA = shape(
    meanings=MEANINGS,
    **{f"{gender}_{number}": TEXT for gender in GENDERS for number in NUMBERS},
    comparativo=TEXT,
    superlativo=TEXT,
)


def read_adjective(reply: dict[str, Any]) -> Description:
    forms = [
        Form(reply[f"{gender}_{number}"], f"{gender} {number}")
        for gender in GENDERS
        for number in NUMBERS
    ]
    for comparative in spellings(reply["comparativo"]):
        # migliore, migliori
        forms.append(Form(comparative, "comparativo singolare"))
        if comparative.endswith("e"):
            forms.append(Form(comparative[:-1] + "i", "comparativo plurale"))
    for superlative in spellings(reply["superlativo"]):
        # bellissimo, bellissima, bellissimi, bellissime
        forms += _in_every_gender(superlative, "superlativo")
    return [Described({}, reply["meanings"], present(forms))]


ADJECTIVE = _italian("adjective", ADJECTIVE_SCHEMA, read_adjective)

# adverbs

ADVERB_SCHEMA = shape(meanings=MEANINGS, comparativo=TEXT, superlativo=TEXT)


def read_adverb(reply: dict[str, Any]) -> Description:
    forms = [
        Form(reply["comparativo"], "comparativo"),
        Form(reply["superlativo"], "superlativo"),
    ]
    return [Described({}, reply["meanings"], present(forms))]


ADVERB = _italian("adverb", ADVERB_SCHEMA, read_adverb)

# words whose forms are listed: pronouns, articles and numerals

LISTED_SCHEMA = shape(
    meanings=MEANINGS,
    forms=several(shape(form=TEXT, tags=TEXT)),
)


def read_listed(reply: dict[str, Any]) -> Description:
    forms = [Form(form["form"], form["tags"].strip()) for form in reply["forms"]]
    return [Described({}, reply["meanings"], present(forms))]


PRONOUN = _italian("pronoun", LISTED_SCHEMA, read_listed)

ARTICLE = _italian("article", LISTED_SCHEMA, read_listed)

NUMERAL = _italian("numeral", LISTED_SCHEMA, read_listed)

# prepositions

PREPOSITION_SCHEMA = shape(meanings=MEANINGS, contractions=several(TEXT))


def read_preposition(reply: dict[str, Any]) -> Description:
    contractions = [Form(c, "articolata") for c in reply["contractions"]]
    return [Described({}, reply["meanings"], present(contractions))]


PREPOSITION = _italian("preposition", PREPOSITION_SCHEMA, read_preposition)

# words that have one form only

PLAIN_SCHEMA = shape(meanings=MEANINGS)


def read_plain(reply: dict[str, Any]) -> Description:
    return [Described({}, reply["meanings"], [])]


CONJUNCTION = _italian("conjunction", PLAIN_SCHEMA, read_plain, "plain")
PARTICLE = _italian("particle", PLAIN_SCHEMA, read_plain, "plain")
INTERJECTION = _italian("interjection", PLAIN_SCHEMA, read_plain, "plain")

CATEGORIES: dict[str, Category] = {
    category.name: category
    for category in (
        NOUN,
        VERB,
        ADJECTIVE,
        ADVERB,
        PRONOUN,
        ARTICLE,
        PREPOSITION,
        CONJUNCTION,
        PARTICLE,
        NUMERAL,
        INTERJECTION,
    )
}
