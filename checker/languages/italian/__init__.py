# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What Italian does its own way, as languages/ describes: its categories,
in categories.py, with what the models are told of them in prompts/; how
the forms of its words are laid out, in tables.json; its lessons, in
grammar/; and its mock exams, those of the CELI of the Università per
Stranieri di Perugia, in evaluations/."""

from __future__ import annotations

from typing import TYPE_CHECKING

from languages import Language

if TYPE_CHECKING:
    from categories import Category


class Italian(Language):
    # a vowel with an accent is written with an apostrophe without one
    equivalents = {
        "à": "a'",
        "è": "e'",
        "é": "e'",
        "ì": "i'",
        "ò": "o'",
        "ù": "u'",
    }
    marks = "accents"
    hunspell = "it_IT"
    handwriting_hint = "it-t-i0-handwrit"
    answer_words = {"truefalse": ("Vero", "Falso"), "yesno": ("Sì", "No")}
    # "il cane", "lo zaino", "l'amico", "un'amica"
    note_prefixes = frozenset(
        {"il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "l'", "un'"}
    )
    # Not those that end a sentence as often, such as "ecc.", nor any that
    # is a word of another language, such as "es", as every language's are
    # told apart from the end of a sentence in every text.
    abbreviations = frozenset(
        {
            "avv",
            "ca",
            "cfr",
            "dott",
            "ing",
            "n",
            "p.es",
            "pag",
            "prof",
            "sig",
            "sigg",
            "tel",
        }
    )

    def categories(self) -> dict[str, Category]:
        from languages.italian.categories import CATEGORIES

        return CATEGORIES


LANGUAGE = Italian("Italian")
