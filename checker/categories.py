# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The categories the words of the vocabulary are divided into, and what is
stored of a word in each.

What a model is told about a category is in prompts/categories/, to be
tuned in one place: how the decision model is to recognise it, what makes
two words the same entry, and what a language model is told when it
describes a new word. The shape of that description is here. The shapes
are given to the model as JSON schemas, so it has no say in how its answer
is laid out, and the forms of a word are worked out from the filled-in
shape here rather than left to it to list.

What is written out here fits every language: a word is stored under the
form a dictionary lists it by, with whatever forms the model lists for it.
A language that has rules of its own, as languages/ describes, has
categories of its own, with the same names, which store more of a word,
told by its own prompts.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from languages import language_of
from prompts import PROMPTS
from vocabulary import Form

Schema = dict[str, Any]
# What is known about a word beyond its forms, and its forms.
Description = tuple[dict[str, Any], list[Form]]

TEXT: Schema = {"type": "string"}
FLAG: Schema = {"type": "boolean"}


def shape(**properties: Schema) -> Schema:
    """An object that has exactly these properties, all of them."""
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def several(items: Schema) -> Schema:
    return {"type": "array", "items": items}


def one_of(*options: str) -> Schema:
    return {"type": "string", "enum": list(options)}


@dataclass(frozen=True)
class Category:
    name: str
    # How the decision model is told to recognise a word of this category.
    # It does best with examples, of every form the words come in.
    criterion: str
    # What a language model is told when it judges whether a word is new:
    # which is the dictionary form, and what is and is not the same word.
    judging: str
    # what it is told when it describes a new word
    describing: str
    # the shape of that description
    schema: Schema
    # turns a description of that shape into what is stored
    read: Callable[[dict[str, Any]], Description]


MEANINGS = several(TEXT)

# The names of the categories, which are the same for every language, in the
# order they are shown in.
CATEGORIES = (
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "article",
    "preposition",
    "conjunction",
    "particle",
    "numeral",
    "interjection",
)


def _told(name: str) -> str:
    """A prompt of prompts/categories/, with the rules it uses."""
    return PROMPTS(
        f"categories.{name}", meanings_rule=PROMPTS("categories.rules.meanings")
    )


# The categories of a language that has no rules of its own: told apart
# without examples, and with a description of one shape.
GENERIC_SCHEMA = shape(
    meanings=MEANINGS,
    forms=several(shape(form=TEXT, tags=TEXT)),
)


def read_generic(reply: dict[str, Any]) -> Description:
    forms = [Form(form["form"], form["tags"].strip()) for form in reply["forms"]]
    return {"meanings": reply["meanings"]}, present(forms)


GENERIC: dict[str, Category] = {
    name: Category(
        name,
        _told(f"criteria.{name}"),
        _told("judging"),
        _told("describing"),
        GENERIC_SCHEMA,
        read_generic,
    )
    for name in CATEGORIES
}


def categories_of(language: str) -> dict[str, Category]:
    """The categories the words of a language are divided into, with the
    rules of that language if it has any. The names of the categories are
    the same for every language."""
    return language_of(language).categories()


def dictionary_form(lemma: str, category: str, language: str) -> str:
    """`lemma` written as a dictionary of `language` has it, whatever the
    model that gave it wrote."""
    return language_of(language).dictionary_form(lemma, category)


# What a word can be found to be that is not stored, as the decision model is
# told to recognise it.
NOT_STORED = {name: _told(f"not_stored.{name}") for name in ("name", "other")}


def spellings(text: str) -> list[str]:
    """The ways a form is written, where a model gave more than one."""
    return [spelling.strip() for spelling in text.split("/") if spelling.strip()]


def present(forms: list[Form]) -> list[Form]:
    """The forms that were filled in, each once, and each spelling of a form
    that has several as a form of its own."""
    seen = set()
    kept = []
    for form in forms:
        for spelling in spellings(form.form):
            if (spelling, form.tags) not in seen:
                seen.add((spelling, form.tags))
                kept.append(Form(spelling, form.tags))
    return kept
