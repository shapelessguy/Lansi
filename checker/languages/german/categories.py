# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The categories of the words of German, as categories.py describes them:
what is stored of a word of each, and how a model is told about it, which
is in prompts/categories/ here."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from categories import (
    FLAG,
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
from vocabulary import Form

# what the models are told of German
GERMAN_PROMPTS = Prompts(Path(__file__).resolve().with_name("prompts"))


def _told(name: str) -> str:
    """A prompt of prompts/categories/, with the rules it uses."""
    return GERMAN_PROMPTS(
        f"categories.{name}",
        meanings_rule=PROMPTS("categories.rules.meanings"),
        empty_rule=GERMAN_PROMPTS("categories.rules.empty"),
        listing=GERMAN_PROMPTS("categories.rules.listing"),
    )


def _german(
    name: str,
    schema: Schema,
    read: Callable[[dict[str, Any]], Description],
    rules: str = "",
) -> Category:
    """A category of German, as the prompts of prompts/categories/ tell it,
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


# nouns

CASES = ("nominativ", "genitiv", "dativ", "akkusativ")
_DECLENSION = shape(**dict.fromkeys(CASES, TEXT))

NOUN_SCHEMA = shape(
    genders=several(
        shape(
            article=one_of("der", "die", "das"),
            meanings=MEANINGS,
            singular=_DECLENSION,
            plural=_DECLENSION,
        )
    )
)


def read_noun(reply: dict[str, Any]) -> Description:
    genders = []
    forms = []
    for gender in reply["genders"]:
        article = gender["article"]
        genders.append(
            {
                "article": article,
                "meanings": gender["meanings"],
                "plural": gender["plural"]["nominativ"],
            }
        )
        for number in ("singular", "plural"):
            for case in CASES:
                forms.append(Form(gender[number][case], f"{article} {case} {number}"))
    return {"genders": genders}, present(forms)


NOUN = _german("noun", NOUN_SCHEMA, read_noun)

# verbs

PERSONS = ("ich", "du", "er", "wir", "ihr", "sie")
_CONJUGATION = shape(**dict.fromkeys(PERSONS, TEXT))
# the tables of a verb, each by the tag its forms are stored with
TENSES = {
    "praesens": "präsens",
    "praeteritum": "präteritum",
    "konjunktiv_1": "konjunktiv I",
    "konjunktiv_2": "konjunktiv II",
}

VERB_SCHEMA = shape(
    meanings=MEANINGS,
    auxiliary=one_of("haben", "sein", "haben or sein"),
    separable=FLAG,
    reflexive=one_of("never", "sometimes", "always"),
    zu_infinitive=TEXT,
    partizip_1=TEXT,
    partizip_2=TEXT,
    **dict.fromkeys(TENSES, _CONJUGATION),
    imperativ=shape(du=TEXT, ihr=TEXT),
)


def read_verb(reply: dict[str, Any]) -> Description:
    details = {
        name: reply[name]
        for name in ("meanings", "auxiliary", "separable", "reflexive")
    }
    forms = [
        Form(reply["zu_infinitive"], "zu-infinitiv"),
        Form(reply["partizip_1"], "partizip I"),
        Form(reply["partizip_2"], "partizip II"),
    ]
    for name, tag in TENSES.items():
        for person in PERSONS:
            for form in spellings(reply[name][person]):
                forms.append(Form(form, f"{tag} {person}"))
                parts = form.split()
                if reply["separable"] and len(parts) == 2:  # noqa: PLR2004
                    # "rufe an" is "anrufe" at the end of a subordinate clause
                    forms.append(Form(parts[1] + parts[0], f"{tag} {person} nebensatz"))
    for person in ("du", "ihr"):
        forms.append(Form(reply["imperativ"][person], f"imperativ {person}"))
    return details, present(forms)


VERB = _german("verb", VERB_SCHEMA, read_verb)

# adjectives

# the degrees of an adjective, each by the tag its forms are stored with
DEGREES = {
    "positive": "positiv",
    "comparative": "komparativ",
    "superlative": "superlativ",
}
ENDINGS = ("e", "er", "es", "en", "em")

ADJECTIVE_SCHEMA = shape(
    meanings=MEANINGS,
    comparative=TEXT,
    **{f"{degree}_inflected": TEXT for degree in DEGREES},
)


def read_adjective(reply: dict[str, Any]) -> Description:
    forms = [Form(reply["comparative"], "komparativ")]
    for degree, tag in DEGREES.items():
        for inflected in spellings(reply[f"{degree}_inflected"]):
            if inflected.endswith("e"):
                # the other endings are put where the -e is: hohe, hoher...
                forms += [
                    Form(inflected[:-1] + end, f"{tag} -{end}") for end in ENDINGS
                ]
            else:
                forms.append(Form(inflected, tag))
    return {"meanings": reply["meanings"]}, present(forms)


ADJECTIVE = _german("adjective", ADJECTIVE_SCHEMA, read_adjective)

# adverbs

ADVERB_SCHEMA = shape(meanings=MEANINGS, comparative=TEXT, superlative=TEXT)


def read_adverb(reply: dict[str, Any]) -> Description:
    forms = [Form(reply["comparative"], "komparativ")]
    for superlative in spellings(reply["superlative"]):
        forms.append(Form(superlative, "superlativ"))
        # "am liebsten" is met as "liebsten" when words are taken one by one
        forms.append(Form(superlative.removeprefix("am "), "superlativ"))
    return {"meanings": reply["meanings"]}, present(forms)


ADVERB = _german("adverb", ADVERB_SCHEMA, read_adverb)

# words that are declined: pronouns and articles

DECLINED_SCHEMA = shape(
    meanings=MEANINGS,
    forms=several(shape(form=TEXT, tags=TEXT)),
)


def read_listed(reply: dict[str, Any]) -> Description:
    forms = [Form(form["form"], form["tags"].strip()) for form in reply["forms"]]
    return {"meanings": reply["meanings"]}, present(forms)


PRONOUN = _german("pronoun", DECLINED_SCHEMA, read_listed)

ARTICLE = _german("article", DECLINED_SCHEMA, read_listed)

# prepositions

PREPOSITION_SCHEMA = shape(
    meanings=MEANINGS,
    cases=several(one_of("akkusativ", "dativ", "genitiv")),
    contractions=several(TEXT),
)


def read_preposition(reply: dict[str, Any]) -> Description:
    details = {"meanings": reply["meanings"], "cases": reply["cases"]}
    return details, present([Form(c, "contraction") for c in reply["contractions"]])


PREPOSITION = _german("preposition", PREPOSITION_SCHEMA, read_preposition)

# words that have one form only

PLAIN_SCHEMA = shape(meanings=MEANINGS)


def read_plain(reply: dict[str, Any]) -> Description:
    return {"meanings": reply["meanings"]}, []


CONJUNCTION = _german("conjunction", PLAIN_SCHEMA, read_plain, "plain")
PARTICLE = _german("particle", PLAIN_SCHEMA, read_plain, "plain")
INTERJECTION = _german("interjection", PLAIN_SCHEMA, read_plain, "plain")
NUMERAL = _german("numeral", DECLINED_SCHEMA, read_listed)

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
