# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What German does its own way, as languages/ describes: its categories,
in categories.py, with what the models are told of them in prompts/; how
the forms of its words are laid out, in tables.json; its lessons, in
grammar/; and its mock exams, those of the Goethe-Institut, in
evaluations/."""

from __future__ import annotations

from typing import TYPE_CHECKING

from languages import Language

if TYPE_CHECKING:
    from categories import Category


class German(Language):
    nouns_have_capitals = True
    equivalents = {"ß": "ss", "ä": "ae", "ö": "oe", "ü": "ue"}
    marks = "umlauts"
    # as the Goethe-Institut asks them
    answer_words = {"truefalse": ("Richtig", "Falsch"), "yesno": ("Ja", "Nein")}
    # "der Hund", "sich freuen"
    note_prefixes = frozenset({"der", "die", "das", "sich"})
    abbreviations = frozenset(
        {
            "bzw",
            "ca",
            "d.h",
            "dr",
            "evtl",
            "ggf",
            "inkl",
            "nr",
            "prof",
            "s.o",
            "s.u",
            "st",
            "u.a",
            "vgl",
            "z.b",
        }
    )

    def categories(self) -> dict[str, Category]:
        from languages.german.categories import CATEGORIES

        return CATEGORIES


LANGUAGE = German("German")
