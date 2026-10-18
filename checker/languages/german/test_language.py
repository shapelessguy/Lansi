# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from anki_import import vocabulary_words

from languages import language_of
from languages.german import LANGUAGE as GERMAN


def test_german_is_the_language_of_its_directory() -> None:
    assert language_of("German") is GERMAN
    assert GERMAN.directory is not None
    assert (GERMAN.directory / "grammar" / "points.json").is_file()
    assert sorted(
        path.name for path in (GERMAN.directory / "evaluations").iterdir()
    ) == [
        "A1.json",
        "A2.json",
    ]


def test_german_writes_its_nouns_with_a_capital_and_its_umlauts_otherwise() -> None:
    assert GERMAN.nouns_have_capitals
    assert GERMAN.dictionary_form("hund", "noun") == "Hund"
    assert GERMAN.equivalents["ß"] == "ss"
    assert GERMAN.marks == "umlauts"


def test_an_anki_note_of_german_gives_its_word_without_an_article_or_sich() -> None:
    assert vocabulary_words("der Club", "German") == ["Club"]
    assert vocabulary_words("Die Mutter", "German") == ["Mutter"]
    assert vocabulary_words("sich freuen", "German") == ["freuen"]
    assert vocabulary_words("das", "German") == ["das"]


def test_the_forms_of_german_are_laid_out_in_tables_of_their_tags() -> None:
    tables = GERMAN.form_tables()

    assert [table["title"] for table in tables["noun"]] == ["der", "die", "das"]
    assert tables["noun"][0]["tags"] == "der {row} {column}"
    assert tables["verb"][0]["also"]["tags"] == "{column} {row} nebensatz"
