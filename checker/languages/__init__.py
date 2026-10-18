# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The languages that can be learned, and what is particular to each.

Whatever works on a language, such as the vocabulary, the exercises and the
evaluations, is written for every language, and asks the `Language` it is
of whatever a language does in a way of its own. What `Language` says
itself fits every language. A language that has rules of its own has a
directory here, named after it by its English name in small letters, which
holds everything that is of that language and nothing else has:

    __init__.py     its `LANGUAGE`, a Language that says what it does its
                    own way
    prompts/        what the models are told of it, as checker/prompts.py
                    describes
    tables.json     how the forms of its words are laid out, as
                    `Language.form_tables` describes
    grammar/        its lessons, as grammar.py reads them
    evaluations/    its mock exams, as evaluating.py reads them

A language that has no directory here is learned all the same, by the
rules that fit every language.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from categories import Category

LANGUAGES_DIRECTORY = Path(__file__).resolve().parent
# The language that is learned unless another is said.
DEFAULT_LANGUAGE = "German"


class Language:
    """A language that can be learned, by its English name, with what it does
    its own way. A language of its own overrides what it does otherwise."""

    # whether its nouns are written with a capital letter, as its names are
    nouns_have_capitals = False
    # Letters that may be written otherwise by someone who cannot type them,
    # each with how, such as "ß" as "ss": an answer written so is almost
    # right rather than wrong, as one without the marks on its letters is.
    # The exercises are told them, as exercises/kit.py describes.
    equivalents: Mapping[str, str] = {}
    # what the marks on its letters are called, in English
    marks = "accents"
    # The words an Anki note may put before the word it is of, such as an
    # article, in small letters.
    note_prefixes: frozenset[str] = frozenset()
    # Words that are written with a full stop but do not end a sentence,
    # without the final full stop, in small letters.
    abbreviations: frozenset[str] = frozenset()

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.name!r})"

    @property
    def directory(self) -> Path | None:
        """The directory of what is of this language alone, if it has one."""
        return directory_of(self.name)

    def categories(self) -> dict[str, Category]:
        """The categories its words are divided into, as categories.py
        describes them. Their names are the same for every language."""
        from categories import GENERIC

        return GENERIC

    def dictionary_form(self, lemma: str, category: str) -> str:
        """`lemma` written as a dictionary of the language has it, whatever
        the model that gave it wrote."""
        if category == "noun" and self.nouns_have_capitals:
            return lemma[:1].upper() + lemma[1:]
        return lemma

    def form_tables(self) -> dict[str, list[dict[str, Any]]]:
        """How the app lays out the forms of a word in tables, for each
        category that has any: `tables.json` of the directory of the
        language. A table is

            {"title": ..., "columns": [...], "rows": [...],
             "tags": "{column} {row}",
             "also": {"tags": "{column} {row} ...", "title": ...}}

        where `tags` are those of the form that goes where a column and a
        row meet, and `also`, if there is one, those of another form shown
        beside it, with what that form is. A form that fits no table is
        listed with its tags."""
        directory = self.directory
        path = directory / "tables.json" if directory else None
        if path is None or not path.is_file():
            return {}
        tables: dict[str, list[dict[str, Any]]] = json.loads(
            path.read_text(encoding="utf-8")
        )
        return tables


def directory_of(name: str, root: Path = LANGUAGES_DIRECTORY) -> Path | None:
    """The directory of `root` that is of the language named, whatever its
    case, if there is one."""
    wanted = name.strip().lower()
    if not wanted or not root.is_dir():
        return None
    for directory in root.iterdir():
        if directory.is_dir() and directory.name.lower() == wanted:
            return directory
    return None


@lru_cache
def language_of(name: str) -> Language:
    """The language of that English name, whatever its case, with the rules
    of its own if it has any here."""
    directory = directory_of(name)
    if directory is None or not (directory / "__init__.py").is_file():
        return Language(name.strip())
    language: Language = importlib.import_module(
        f"{__name__}.{directory.name}"
    ).LANGUAGE
    return language


def languages_of_their_own() -> list[Language]:
    """Every language that has rules of its own here."""
    return [
        language_of(directory.name)
        for directory in sorted(LANGUAGES_DIRECTORY.iterdir())
        if (directory / "__init__.py").is_file()
    ]
