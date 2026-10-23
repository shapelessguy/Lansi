# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from anki_import import vocabulary_words

from languages import language_of
from languages.italian import LANGUAGE as ITALIAN


def test_italian_is_the_language_of_its_directory() -> None:
    assert language_of("Italian") is ITALIAN
    assert ITALIAN.directory is not None
    assert (ITALIAN.directory / "tables.json").is_file()


def test_italian_writes_its_nouns_small_and_its_accents_otherwise() -> None:
    assert not ITALIAN.nouns_have_capitals
    assert ITALIAN.dictionary_form("cane", "noun") == "cane"
    assert ITALIAN.equivalents["è"] == "e'"
    assert ITALIAN.marks == "accents"


def test_a_statement_in_italian_is_answered_vero_or_falso_and_si_or_no() -> None:
    assert ITALIAN.answer_words["truefalse"] == ("Vero", "Falso")
    assert ITALIAN.answer_words["yesno"] == ("Sì", "No")


def test_an_anki_note_of_italian_gives_its_word_without_an_article() -> None:
    assert vocabulary_words("il cane", "Italian") == ["cane"]
    assert vocabulary_words("Lo zaino", "Italian") == ["zaino"]
    assert vocabulary_words("l'amico", "Italian") == ["amico"]
    assert vocabulary_words("un’amica", "Italian") == ["amica"]
    assert vocabulary_words("la", "Italian") == ["la"]


def test_the_forms_of_italian_are_laid_out_in_tables_of_their_tags() -> None:
    tables = ITALIAN.form_tables()

    assert [table["title"] for table in tables["verb"]] == [
        "Indicativo",
        "Congiuntivo e condizionale",
        "Participio passato",
    ]
    assert tables["noun"][0]["tags"] == "{row} {column}"
    assert tables["adjective"][1]["tags"] == "superlativo {row} {column}"
