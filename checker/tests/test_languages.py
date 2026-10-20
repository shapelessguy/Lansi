# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from pathlib import Path

from anki_import import vocabulary_words
from categories import GENERIC
from languages import Language, directory_of, language_of, languages_of_their_own
from sentences import split_sentences


def test_a_language_without_a_directory_has_the_rules_that_fit_every_language() -> None:
    italian = language_of("Italian")

    assert type(italian) is Language
    assert italian.name == "Italian"
    assert italian.directory is None
    assert italian.categories() is GENERIC
    assert not italian.nouns_have_capitals
    assert italian.dictionary_form("casa", "noun") == "casa"
    assert dict(italian.equivalents) == {}
    assert italian.marks == "accents"
    assert italian.form_tables() == {}


def test_a_language_is_found_by_its_name_whatever_its_case() -> None:
    assert language_of(" german ") is language_of("German")
    assert language_of("German").name == "German"


def test_a_directory_is_found_only_among_those_of_the_languages(tmp_path: Path) -> None:
    (tmp_path / "German").mkdir()

    assert directory_of("german", tmp_path) == tmp_path / "German"
    assert directory_of("../German", tmp_path) is None
    assert directory_of("", tmp_path) is None
    assert directory_of("Klingon", tmp_path) is None


def test_every_language_of_its_own_is_named_after_its_directory() -> None:
    for language in languages_of_their_own():
        assert language.directory is not None
        assert language.directory.name == language.name.lower()


def test_an_anki_note_of_a_language_without_prefixes_keeps_its_first_word() -> None:
    assert vocabulary_words("der Hund", "Italian") == []
    assert vocabulary_words("casa, case", "Italian") == ["casa", "case"]


def test_the_abbreviations_of_every_language_keep_a_sentence_whole() -> None:
    assert [
        each.text for each in split_sentences("Das ist z.B. gut. Mr. Smith came.")
    ] == [
        "Das ist z.B. gut.",
        "Mr. Smith came.",
    ]
