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

The rules written out there are those of German. A word of any other
language is stored by rules that fit every language: under the form a
dictionary lists it by, with whatever forms the model lists for it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


def _told(name: str) -> str:
    """A prompt of prompts/categories/, with the rules it uses."""
    return PROMPTS(
        f"categories.{name}",
        meanings_rule=PROMPTS("categories.rules.meanings"),
        empty_rule=PROMPTS("categories.rules.empty"),
        listing=PROMPTS("categories.rules.listing"),
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
    return {"genders": genders}, _present(forms)


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
            for form in _spellings(reply[name][person]):
                forms.append(Form(form, f"{tag} {person}"))
                parts = form.split()
                if reply["separable"] and len(parts) == 2:  # noqa: PLR2004
                    # "rufe an" is "anrufe" at the end of a subordinate clause
                    forms.append(Form(parts[1] + parts[0], f"{tag} {person} nebensatz"))
    for person in ("du", "ihr"):
        forms.append(Form(reply["imperativ"][person], f"imperativ {person}"))
    return details, _present(forms)


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
        for inflected in _spellings(reply[f"{degree}_inflected"]):
            if inflected.endswith("e"):
                # the other endings are put where the -e is: hohe, hoher...
                forms += [
                    Form(inflected[:-1] + end, f"{tag} -{end}") for end in ENDINGS
                ]
            else:
                forms.append(Form(inflected, tag))
    return {"meanings": reply["meanings"]}, _present(forms)


ADJECTIVE = _german("adjective", ADJECTIVE_SCHEMA, read_adjective)

# adverbs

ADVERB_SCHEMA = shape(meanings=MEANINGS, comparative=TEXT, superlative=TEXT)


def read_adverb(reply: dict[str, Any]) -> Description:
    forms = [Form(reply["comparative"], "komparativ")]
    for superlative in _spellings(reply["superlative"]):
        forms.append(Form(superlative, "superlativ"))
        # "am liebsten" is met as "liebsten" when words are taken one by one
        forms.append(Form(superlative.removeprefix("am "), "superlativ"))
    return {"meanings": reply["meanings"]}, _present(forms)


ADVERB = _german("adverb", ADVERB_SCHEMA, read_adverb)

# words that are declined: pronouns and articles

DECLINED_SCHEMA = shape(
    meanings=MEANINGS,
    forms=several(shape(form=TEXT, tags=TEXT)),
)


def read_listed(reply: dict[str, Any]) -> Description:
    forms = [Form(form["form"], form["tags"].strip()) for form in reply["forms"]]
    return {"meanings": reply["meanings"]}, _present(forms)


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
    return details, _present([Form(c, "contraction") for c in reply["contractions"]])


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

# The categories of a language that has no rules of its own here: the same
# ones, told apart without examples, and with a description of one shape.
GENERIC_SCHEMA = shape(
    meanings=MEANINGS,
    forms=several(shape(form=TEXT, tags=TEXT)),
)


def read_generic(reply: dict[str, Any]) -> Description:
    forms = [Form(form["form"], form["tags"].strip()) for form in reply["forms"]]
    return {"meanings": reply["meanings"]}, _present(forms)


GENERIC: dict[str, Category] = {
    name: Category(
        name,
        _told(f"generic_criteria.{name}"),
        _told("judging.generic"),
        _told("describing.generic"),
        GENERIC_SCHEMA,
        read_generic,
    )
    for name in CATEGORIES
}

# the languages that have rules of their own, by their names in small letters
_BY_LANGUAGE = {"german": CATEGORIES}


def categories_of(language: str) -> dict[str, Category]:
    """The categories the words of a language are divided into, with the
    rules of that language if it has any here. The names of the categories
    are the same for every language."""
    return _BY_LANGUAGE.get(language.strip().lower(), GENERIC)


def writes_nouns_with_capitals(language: str) -> bool:
    return language.strip().lower() == "german"


def dictionary_form(lemma: str, category: str, language: str) -> str:
    """`lemma` written as a dictionary of `language` has it, whatever the
    model that gave it wrote: a noun begins with a capital letter in a
    language that writes nouns so."""
    if category == "noun" and writes_nouns_with_capitals(language):
        return lemma[:1].upper() + lemma[1:]
    return lemma


# What a word can be found to be that is not stored, as the decision model is
# told to recognise it.
NOT_STORED = {name: _told(f"not_stored.{name}") for name in ("name", "other")}


def _spellings(text: str) -> list[str]:
    """The ways a form is written, where a model gave more than one."""
    return [spelling.strip() for spelling in text.split("/") if spelling.strip()]


def _present(forms: list[Form]) -> list[Form]:
    """The forms that were filled in, each once, and each spelling of a form
    that has several as a form of its own."""
    seen = set()
    present = []
    for form in forms:
        for spelling in _spellings(form.form):
            if (spelling, form.tags) not in seen:
                seen.add((spelling, form.tags))
                present.append(Form(spelling, form.tags))
    return present
