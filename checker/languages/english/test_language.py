# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from anki_import import vocabulary_words
from sentences import ABBREVIATIONS

from languages import language_of
from languages.english import LANGUAGE as ENGLISH


def test_english_is_the_language_of_its_directory() -> None:
    assert language_of("English") is ENGLISH
    assert ENGLISH.directory is not None
    assert (ENGLISH.directory / "tables.json").is_file()


def test_english_writes_its_nouns_small_and_has_no_letters_of_its_own() -> None:
    assert not ENGLISH.nouns_have_capitals
    assert ENGLISH.dictionary_form("dog", "noun") == "dog"
    assert ENGLISH.equivalents == {}


def test_a_statement_in_english_is_answered_true_or_false_and_yes_or_no() -> None:
    assert ENGLISH.answer_words["truefalse"] == ("True", "False")
    assert ENGLISH.answer_words["yesno"] == ("Yes", "No")


def test_an_anki_note_of_english_gives_its_word_without_an_article_or_to() -> None:
    assert vocabulary_words("the dog", "English") == ["dog"]
    assert vocabulary_words("an apple", "English") == ["apple"]
    assert vocabulary_words("to go", "English") == ["go"]
    assert vocabulary_words("a", "English") == ["a"]


def test_no_abbreviation_is_a_word_that_ends_a_sentence() -> None:
    assert {"mr", "e.g"} <= ABBREVIATIONS
    assert not {"no", "etc", "es", "ecc"} & ABBREVIATIONS


def test_the_forms_of_english_are_laid_out_in_tables_of_their_tags() -> None:
    tables = ENGLISH.form_tables()

    assert tables["verb"][0]["rows"][2:] == ["past", "past participle", "-ing"]
    assert tables["noun"][0]["tags"] == "{row}"
