# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The categories the words of the vocabulary are divided into, and what is
stored of a word in each.

Everything a model is told about a category is here, to be tuned in one
place: how the decision model is to recognise it, what makes two words the
same entry, and the shape of the description a language model has to fill in
for a new word. The shapes are given to the model as JSON schemas, so it has
no say in how its answer is laid out, and the forms of a word are worked out
from the filled-in shape here rather than left to it to list.

The rules written out here are those of German. A word of any other
language is stored by rules that fit every language: under the form a
dictionary lists it by, with whatever forms the model lists for it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
_MEANINGS_RULE = (
    "`meanings` are short English translations, one for each distinct meaning"
    " of the word, the most common first."
)
# A form that is written in two ways is to be found by either, so both are
# asked for, in the one place the form has.
_EMPTY_RULE = (
    "Leave a text empty where the word has no such form. Where a form has two"
    " accepted spellings, give both, separated by a slash: `Produkts /"
    " Produktes`, `geh / gehe`, `gern / gerne`."
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


NOUN = Category(
    "noun",
    "A noun, in any case or number: Hund, Hundes, Häuser, Kindern, Freiheit."
    " German nouns are written with a capital letter.",
    "The dictionary form is the nominative singular, without an article, or"
    " the nominative plural for a noun that has no singular. The same word:"
    " its cases and its plural, and the same spelling with another gender or"
    " meaning (der, das and die Band are one word). Words of their own:"
    " compounds (Haustür is not Haus), diminutives (Häuschen), and verbs and"
    " adjectives used as nouns (das Essen, der Alte).",
    "List every gender the noun is used with as one of `genders`: der Band,"
    " das Band and die Band are three. For each give the article, the"
    " meanings it has with that gender, and the noun, without the article,"
    f" in the four cases of the singular and of the plural. {_EMPTY_RULE}"
    f" {_MEANINGS_RULE}",
    NOUN_SCHEMA,
    read_noun,
)

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


VERB = Category(
    "verb",
    "A verb, in any form: infinitive (gehen), conjugated (gehe, gehst, ging,"
    " kam, war, ist, bin, hat, wird, wäre), participle (gegangen, gewesen).",
    "The dictionary form is the infinitive, without `sich`. The same word:"
    " every person, tense and mood of the verb and its participles, and the"
    " same infinitive with another meaning or used reflexively. Words of"
    " their own: verbs with a prefix, separable or not (anrufen, berufen and"
    " rufen are three words).",
    "Give the forms that are one word: no tenses made with an auxiliary."
    " In each table give the form for each person without the pronoun and"
    " without `sich`, as it stands in a main clause, so that a separable"
    " verb is split: `rufe an`. `er` stands for er, sie and es, and `sie`"
    " for the plural sie and for Sie. `zu_infinitive` is the infinitive with"
    " zu, such as `zu gehen` or `anzurufen`. `auxiliary` is the verb the"
    f" perfect is made with. {_EMPTY_RULE} {_MEANINGS_RULE}",
    VERB_SCHEMA,
    read_verb,
)

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


ADJECTIVE = Category(
    "adjective",
    "An adjective, with or without an ending, in any degree: schön, schöne,"
    " altes, kleinen, größer, besten, müde, schnell.",
    "The dictionary form is the positive without an ending (schön, not"
    " schöne). The same word: every ending, and the comparative and the"
    " superlative. Words of their own: adjectives made with a prefix or a"
    " suffix (unschön, kindlich), and participles that have become"
    " adjectives with a meaning of their own (bekannt, spannend).",
    "`comparative` is the comparative without an ending (schöner, höher)."
    " `positive_inflected`, `comparative_inflected` and"
    " `superlative_inflected` are the three degrees with the ending -e, as"
    " after `die` (schöne, schönere, schönste; hohe, höhere, höchste). For"
    " an adjective that takes no endings (lila, prima) give it unchanged as"
    f" `positive_inflected`. {_EMPTY_RULE} {_MEANINGS_RULE}",
    ADJECTIVE_SCHEMA,
    read_adjective,
)

# adverbs

ADVERB_SCHEMA = shape(meanings=MEANINGS, comparative=TEXT, superlative=TEXT)


def read_adverb(reply: dict[str, Any]) -> Description:
    forms = [Form(reply["comparative"], "komparativ")]
    for superlative in _spellings(reply["superlative"]):
        forms.append(Form(superlative, "superlativ"))
        # "am liebsten" is met as "liebsten" when words are taken one by one
        forms.append(Form(superlative.removeprefix("am "), "superlativ"))
    return {"meanings": reply["meanings"]}, _present(forms)


ADVERB = Category(
    "adverb",
    "An adverb, which never changes: heute, morgen, jetzt, bald, immer, oft,"
    " selten, hier, dort, sehr, gern, vielleicht.",
    "The dictionary form is the word itself. The same word: its comparative"
    " and superlative, for the few adverbs that have them (gern, lieber, am"
    " liebsten). Every other adverb is a word of its own.",
    "`comparative` and `superlative` are for the few adverbs that have them"
    f" (lieber, am liebsten). {_EMPTY_RULE} {_MEANINGS_RULE}",
    ADVERB_SCHEMA,
    read_adverb,
)

# words that are declined: pronouns and articles

DECLINED_SCHEMA = shape(
    meanings=MEANINGS,
    forms=several(shape(form=TEXT, tags=TEXT)),
)


def read_listed(reply: dict[str, Any]) -> Description:
    forms = [Form(form["form"], form["tags"].strip()) for form in reply["forms"]]
    return {"meanings": reply["meanings"]}, _present(forms)


_LISTING = (
    "List every form the word is declined into as one of `forms`, each with"
    " `tags` that say which it is, in small letters, as case, then gender or"
    " `plural`: `dativ maskulin`, `akkusativ plural`. Give a spelling once"
    " for every case and gender it serves."
)

PRONOUN = Category(
    "pronoun",
    "A pronoun, in any case: ich, mich, mir, du, dich, dir, er, ihn, ihm, sie,"
    " ihr, es, wir, uns, euch, ihnen, man, jemand, etwas, sich, wer, was.",
    "The dictionary form is the nominative, masculine singular where there"
    " are genders (ich, dieser, jemand). The same word: its cases, genders"
    " and plural (mich and mir are ich; diese and diesem are dieser). Words"
    " of their own: each person (ich, du, er, sie, es, wir, ihr), and each"
    " possessive (mein, dein).",
    f"{_LISTING} {_MEANINGS_RULE}",
    DECLINED_SCHEMA,
    read_listed,
)

ARTICLE = Category(
    "article",
    "An article or determiner, in any case: der, die, das, den, dem, des,"
    " ein, eine, einen, einem, kein, mein, dein, dieser, jeder.",
    "The dictionary form is the nominative masculine singular (der, ein,"
    " kein, mein). The same word: its cases, genders and plural (die, das,"
    " dem and den are der).",
    f"{_LISTING} {_MEANINGS_RULE}",
    DECLINED_SCHEMA,
    read_listed,
)

# prepositions

PREPOSITION_SCHEMA = shape(
    meanings=MEANINGS,
    cases=several(one_of("akkusativ", "dativ", "genitiv")),
    contractions=several(TEXT),
)


def read_preposition(reply: dict[str, Any]) -> Description:
    details = {"meanings": reply["meanings"], "cases": reply["cases"]}
    return details, _present([Form(c, "contraction") for c in reply["contractions"]])


PREPOSITION = Category(
    "preposition",
    "A preposition, also fused with an article: in, im, an, am, auf, mit,"
    " nach, zu, zum, zur, von, vom, bei, für, um, ohne, wegen.",
    "The dictionary form is the preposition itself. The same word: the"
    " preposition fused with an article (zum and zur are zu, im is in).",
    "`cases` are the cases the preposition can be followed by."
    " `contractions` are the forms it has fused with an article (zum, zur),"
    f" if any. {_MEANINGS_RULE}",
    PREPOSITION_SCHEMA,
    read_preposition,
)

# words that have one form only

PLAIN_SCHEMA = shape(meanings=MEANINGS)


def read_plain(reply: dict[str, Any]) -> Description:
    return {"meanings": reply["meanings"]}, []


def _plain(name: str, criterion: str) -> Category:
    return Category(
        name,
        criterion,
        "The dictionary form is the word itself, which has no other forms."
        " Every other word is a word of its own.",
        _MEANINGS_RULE,
        PLAIN_SCHEMA,
        read_plain,
    )


CONJUNCTION = _plain(
    "conjunction",
    "A conjunction: und, oder, aber, denn, weil, dass, ob, wenn, als, obwohl.",
)
PARTICLE = _plain(
    "particle",
    "A particle: nicht, doch, mal, ja, nein, eben, halt, schon.",
)
INTERJECTION = _plain(
    "interjection",
    "A greeting or exclamation: hallo, hi, tschüss, danke, bitte, ach, oh.",
)
NUMERAL = Category(
    "numeral",
    "A number written as a word: eins, zwei, drei, acht, zwanzig, hundert,"
    " erste, dritte.",
    "The dictionary form of a cardinal is the word itself (drei), and of an"
    " ordinal the form with -e (dritte). The same word: the endings of an"
    " ordinal (dritten, dritter), and of eins (ein, eine, einen). A cardinal"
    " and its ordinal are two words.",
    f"{_LISTING} For a numeral that is not declined list no forms. {_MEANINGS_RULE}",
    DECLINED_SCHEMA,
    read_listed,
)

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


_GENERIC_CRITERIA = {
    "noun": "A noun, in any of its forms.",
    "verb": "A verb, in any of its forms: infinitive, conjugated or participle.",
    "adjective": "An adjective, in any of its forms.",
    "adverb": "An adverb.",
    "pronoun": "A pronoun, in any of its forms.",
    "article": "An article or determiner, in any of its forms.",
    "preposition": "A preposition, also when it is fused with an article.",
    "conjunction": "A conjunction.",
    "particle": "A particle: a small word that never changes its form.",
    "numeral": "A number written as a word.",
    "interjection": "A greeting or exclamation.",
}

GENERIC: dict[str, Category] = {
    name: Category(
        name,
        criterion,
        "The dictionary form is the one a dictionary of the language lists the"
        " word under. The same word: every inflected form of it, and the same"
        " spelling with another meaning. Words of their own: words made from"
        " it with a prefix or a suffix, and compounds.",
        "List every inflected form of the word as one of `forms`, each with"
        " `tags` that say which form it is, in English grammatical terms in"
        " small letters: `present 2nd singular`, `plural`, `feminine"
        " singular`. Give a spelling once for every form it serves. List no"
        f" forms for a word that never changes. {_MEANINGS_RULE}",
        GENERIC_SCHEMA,
        read_generic,
    )
    for name, criterion in _GENERIC_CRITERIA.items()
}
assert list(GENERIC) == list(CATEGORIES)

# the languages that have rules of their own, by their names in small letters
_BY_LANGUAGE = {"german": CATEGORIES}


def categories_of(language: str) -> dict[str, Category]:
    """The categories the words of a language are divided into, with the
    rules of that language if it has any here. The names of the categories
    are the same for every language."""
    return _BY_LANGUAGE.get(language.strip().lower(), GENERIC)


def writes_nouns_with_capitals(language: str) -> bool:
    return language.strip().lower() == "german"


# What a word can be found to be that is not stored, as the decision model is
# told to recognise it.
NOT_STORED = {
    "name": "A proper name of a person, place or brand: Maria, Berlin, Deutschland.",
    "other": "Not a word of that language at all: random letters, or a word of"
    " another language.",
}


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
