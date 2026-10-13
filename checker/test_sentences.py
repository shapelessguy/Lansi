# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import pytest
from sentences import Sentence, split_sentences


def texts(text: str) -> list[str]:
    return [sentence.text for sentence in split_sentences(text)]


def test_split_sentences_separates_at_full_stops_question_and_exclamation_marks() -> (
    None
):
    text = "Ich gehe nach Hause. Kommst du mit? Bitte komm! Danke."

    assert texts(text) == [
        "Ich gehe nach Hause.",
        "Kommst du mit?",
        "Bitte komm!",
        "Danke.",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Ich weiß nicht... Vielleicht morgen.",
            ["Ich weiß nicht...", "Vielleicht morgen."],
        ),
        (
            "Ich weiß nicht… Vielleicht morgen.",
            ["Ich weiß nicht…", "Vielleicht morgen."],
        ),
        ("Wirklich?! Das glaube ich nicht!!", ["Wirklich?!", "Das glaube ich nicht!!"]),
    ],
)
def test_split_sentences_keeps_a_run_of_marks_with_its_sentence(
    text: str, expected: list[str]
) -> None:
    assert texts(text) == expected


def test_split_sentences_separates_at_new_lines_without_punctuation() -> None:
    text = "Erste Zeile\nZweite Zeile.\r\n\n  Dritte Zeile  "

    assert texts(text) == ["Erste Zeile", "Zweite Zeile.", "Dritte Zeile"]


@pytest.mark.parametrize("text", ["", "   ", "\n\n", " \t\n "])
def test_split_sentences_is_empty_for_text_without_words(text: str) -> None:
    assert split_sentences(text) == []


def test_split_sentences_keeps_closing_quotes_and_brackets_with_the_sentence() -> None:
    text = 'Er sagte: "Komm her!" Dann ging er (schnell.) Ende.'

    assert texts(text) == ['Er sagte: "Komm her!"', "Dann ging er (schnell.)", "Ende."]


@pytest.mark.parametrize(
    "sentence",
    [
        "Das kostet 3.50 Euro.",
        "Schau auf www.example.com nach.",
        "Ich komme am 3. Oktober zurück.",
        "Das ist z. B. ein Hund.",
        "Das ist z.B. ein Hund.",
        "Frag Dr. Müller oder Prof. Schmidt.",
        "Es dauert ca. zwei Stunden.",
    ],
)
def test_split_sentences_does_not_split_at_numbers_addresses_and_abbreviations(
    sentence: str,
) -> None:
    assert texts(f"{sentence} Gut.") == [sentence, "Gut."]


def test_split_sentences_splits_after_a_lower_case_start() -> None:
    assert texts("hallo. wie geht es dir? gut") == ["hallo.", "wie geht es dir?", "gut"]


def test_split_sentences_records_where_each_sentence_is_in_the_text() -> None:
    text = "  Hallo!  Wie geht's?\n\tGut."

    sentences = split_sentences(text)

    assert [(s.start, s.end) for s in sentences] == [(2, 8), (10, 21), (23, 27)]
    assert [text[s.start : s.end] for s in sentences] == [s.text for s in sentences]


def test_split_sentences_gives_whole_sentence_objects() -> None:
    sentences = split_sentences("Das ist fertig. Eine Zeile ohne Punkt\nNoch ni")

    assert sentences == [
        Sentence("Das ist fertig.", 0, 15, complete=True),
        Sentence("Eine Zeile ohne Punkt", 16, 37, complete=True),
        Sentence("Noch ni", 38, 45, complete=True),
    ]


# "Eins ist da. Zwei ist da. Drei"
#  0          12 13        25 26  30
THREE = "Eins ist da. Zwei ist da. Drei"


def complete(text: str, caret: int | None) -> list[bool]:
    return [sentence.complete for sentence in split_sentences(text, caret)]


def test_split_sentences_treats_only_the_sentence_the_caret_is_in_as_not_complete() -> (
    None
):
    assert complete(THREE, 5) == [False, True, True]
    assert complete(THREE, 18) == [True, False, True]
    assert complete(THREE, 28) == [True, True, False]


@pytest.mark.parametrize(
    ("caret", "expected"),
    [
        (0, [False, True, True]),
        # right before the full stop of the first and of the second sentence
        (11, [False, True, True]),
        (24, [True, False, True]),
        # right before the first letter of the second and of the third
        (13, [True, False, True]),
        (26, [True, True, False]),
        # at the very end of the text, which has no ending mark
        (30, [True, True, False]),
    ],
)
def test_split_sentences_counts_the_caret_at_the_edges_of_a_sentence_as_on_it(
    caret: int, expected: list[bool]
) -> None:
    assert complete(THREE, caret) == expected


@pytest.mark.parametrize("text", ["Hi wie gehts?", "Er ist gut.", "Wirklich?!", "Und…"])
def test_split_sentences_takes_a_sentence_as_complete_once_the_caret_is_behind_its_ending_mark(
    text: str,
) -> None:
    assert complete(text, len(text)) == [True]
    assert complete(text, len(text) - 1) == [False]


def test_split_sentences_treats_the_last_sentence_like_any_other() -> None:
    # it has no full stop, but the caret is elsewhere
    assert complete(THREE, 5)[2] is True
    assert complete("Eins ist da", None) == [True]


def test_split_sentences_keeps_a_sentence_open_across_spaces_typed_after_it() -> None:
    # no ending mark yet, so the next word is about to follow
    assert complete("Eins ist ", 9) == [False]
    assert complete("Eins ist da. Zwei  ", 19) == [True, False]


def test_split_sentences_closes_a_sentence_once_a_space_follows_its_ending_mark() -> (
    None
):
    assert complete("Eins ist da. ", 13) == [True]


def test_split_sentences_closes_a_sentence_once_the_caret_is_on_a_new_line() -> None:
    assert complete("Eins ist da\n", 12) == [True]
    assert complete("Eins ist da\nZwei", 14) == [True, False]


def test_split_sentences_without_a_caret_has_every_sentence_complete() -> None:
    assert complete(THREE, None) == [True, True, True]


def test_split_sentences_ignores_a_caret_outside_the_text() -> None:
    assert complete(THREE, 500) == [True, True, True]
    assert complete(THREE, -1) == [True, True, True]
