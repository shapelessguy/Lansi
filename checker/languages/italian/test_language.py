# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json

from anki_import import vocabulary_words
from evaluating import EVALUATIONS_DIRECTORY, SIZES, exams
from exercising import exercises
from grammar import Grammar

from languages import language_of
from languages.italian import LANGUAGE as ITALIAN


def test_italian_is_the_language_of_its_directory() -> None:
    assert language_of("Italian") is ITALIAN
    assert ITALIAN.directory is not None
    assert (ITALIAN.directory / "tables.json").is_file()
    assert (ITALIAN.directory / "grammar" / "points.json").is_file()
    assert sorted(
        path.name for path in (ITALIAN.directory / "evaluations").iterdir()
    ) == [
        "A1.json",
        "A2.json",
        "B1.json",
        "B2.json",
        "C1.json",
        "C2.json",
    ]


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


def test_the_exams_of_italian_have_every_module_and_exercises_there_are() -> None:
    found = exams("Italian", EVALUATIONS_DIRECTORY)

    assert sorted(found) == ["A1", "A2", "B1", "B2", "C1", "C2"]
    known = {manifest.id for manifest in exercises()}
    for exam in found.values():
        assert {part.module for part in exam.parts} == {
            "listening",
            "reading",
            "writing",
            "speaking",
        }
        assert {part.exercise for part in exam.parts} <= known


def test_the_exams_of_italian_take_longer_at_each_size_up_to_the_exam_in_full() -> None:
    for exam in exams("Italian", EVALUATIONS_DIRECTORY).values():
        minutes = [exam.minutes_at(size) for size in SIZES]
        assert minutes == sorted(set(minutes))
        assert minutes[-1] == exam.minutes


def test_the_lessons_of_italian_are_whole_and_each_kept_in_the_order() -> None:
    grammar = Grammar()
    lessons = grammar.lessons("Italian")
    assert ITALIAN.directory is not None
    order = json.loads(
        (ITALIAN.directory / "grammar" / "order.json").read_text(encoding="utf-8")
    )

    assert sorted(lesson.id for lesson in lessons) == sorted(order)
    assert {lesson.level for lesson in lessons} == {"A1", "A2", "B1", "B2"}
    for each in lessons:
        assert each.id in order
        described = grammar.lesson("Italian", each.id)
        assert described and all(point["statement"] for point in described["points"])
