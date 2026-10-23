# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The categories of the words of English, as categories.py describes them:
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
    present,
    several,
    shape,
)
from prompts import PROMPTS, Prompts
from vocabulary import Described, Form

# what the models are told of English
ENGLISH_PROMPTS = Prompts(Path(__file__).resolve().with_name("prompts"))


def _told(name: str) -> str:
    """A prompt of prompts/categories/, with the rules it uses."""
    return ENGLISH_PROMPTS(
        f"categories.{name}",
        meanings_rule=PROMPTS("categories.rules.meanings"),
        empty_rule=ENGLISH_PROMPTS("categories.rules.empty"),
        listing=ENGLISH_PROMPTS("categories.rules.listing"),
    )


def _english(
    name: str,
    schema: Schema,
    read: Callable[[dict[str, Any]], Description],
    rules: str = "",
) -> Category:
    """A category of English, as the prompts of prompts/categories/ tell it,
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


def _forms(reply: dict[str, Any], tags: dict[str, str]) -> Description:
    """A word of one variant, with the forms of the `tags`, each by the
    name the description gives it under."""
    forms = [Form(reply[name], tag) for name, tag in tags.items()]
    return [Described({}, reply["meanings"], present(forms))]


# nouns

NOUN_SCHEMA = shape(meanings=MEANINGS, plural=TEXT)


def read_noun(reply: dict[str, Any]) -> Description:
    return _forms(reply, {"plural": "plural"})


NOUN = _english("noun", NOUN_SCHEMA, read_noun)

# verbs

# the forms of a verb, each by the tag it is stored with
VERB_FORMS = {
    "present": "present",
    "third_person": "3rd person singular",
    "past": "past",
    "past_participle": "past participle",
    "ing": "-ing",
}

VERB_SCHEMA = shape(meanings=MEANINGS, **dict.fromkeys(VERB_FORMS, TEXT))


def read_verb(reply: dict[str, Any]) -> Description:
    return _forms(reply, VERB_FORMS)


VERB = _english("verb", VERB_SCHEMA, read_verb)

# adjectives and adverbs

DEGREES = {"comparative": "comparative", "superlative": "superlative"}
DEGREES_SCHEMA = shape(meanings=MEANINGS, **dict.fromkeys(DEGREES, TEXT))


def read_degrees(reply: dict[str, Any]) -> Description:
    return _forms(reply, DEGREES)


ADJECTIVE = _english("adjective", DEGREES_SCHEMA, read_degrees)
ADVERB = _english("adverb", DEGREES_SCHEMA, read_degrees)

# words whose forms are listed: pronouns, articles and numerals

LISTED_SCHEMA = shape(
    meanings=MEANINGS,
    forms=several(shape(form=TEXT, tags=TEXT)),
)


def read_listed(reply: dict[str, Any]) -> Description:
    forms = [Form(form["form"], form["tags"].strip()) for form in reply["forms"]]
    return [Described({}, reply["meanings"], present(forms))]


PRONOUN = _english("pronoun", LISTED_SCHEMA, read_listed)
ARTICLE = _english("article", LISTED_SCHEMA, read_listed)
NUMERAL = _english("numeral", LISTED_SCHEMA, read_listed)

# words that have one form only

PLAIN_SCHEMA = shape(meanings=MEANINGS)


def read_plain(reply: dict[str, Any]) -> Description:
    return [Described({}, reply["meanings"], [])]


PREPOSITION = _english("preposition", PLAIN_SCHEMA, read_plain, "plain")
CONJUNCTION = _english("conjunction", PLAIN_SCHEMA, read_plain, "plain")
PARTICLE = _english("particle", PLAIN_SCHEMA, read_plain, "plain")
INTERJECTION = _english("interjection", PLAIN_SCHEMA, read_plain, "plain")

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
