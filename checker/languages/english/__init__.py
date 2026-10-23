# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What English does its own way, as languages/ describes: its categories,
in categories.py, with what the models are told of them in prompts/; and
how the forms of its words are laid out, in tables.json."""

from __future__ import annotations

from typing import TYPE_CHECKING

from languages import Language

if TYPE_CHECKING:
    from categories import Category


class English(Language):
    answer_words = {"truefalse": ("True", "False"), "yesno": ("Yes", "No")}
    # "the dog", "a cat", "to go"
    note_prefixes = frozenset({"the", "a", "an", "to"})
    abbreviations = frozenset(
        {"dr", "e.g", "i.e", "mr", "mrs", "ms", "prof", "st", "vs"}
    )

    def categories(self) -> dict[str, Category]:
        from languages.english.categories import CATEGORIES

        return CATEGORIES


LANGUAGE = English("English")
