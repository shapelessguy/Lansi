# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import pytest
from spelling import Speller, SpellingIssue

# "hund" is listed twice so that it counts as the more common word
DICTIONARY = ["ich", "habe", "einen", "hund", "hund", "hunde", "geht", "wie", "es"]


@pytest.fixture
def speller() -> Speller:
    """A speller that knows only the words above, so results don't depend on
    a real dictionary."""
    return Speller(language=None, words=DICTIONARY)


def test_check_finds_nothing_in_correctly_spelled_text(speller: Speller) -> None:
    assert speller.check("Ich habe einen Hund.") == []


def test_check_reports_a_misspelled_word_with_its_place_and_suggestions(
    speller: Speller,
) -> None:
    text = "Ich habe einen Hundd."

    issues = speller.check(text)

    assert issues == [SpellingIssue("Hundd", 15, 20, ["Hund", "Hunde"])]
    assert text[issues[0].start : issues[0].end] == "Hundd"


def test_check_reports_every_misspelled_word_in_order(speller: Speller) -> None:
    issues = speller.check("Ihc habe einn Hund")

    assert [issue.word for issue in issues] == ["Ihc", "einn"]


def test_check_suggests_in_the_case_the_word_was_written_in(speller: Speller) -> None:
    lower, capitalised = speller.check("hundd Hundd")

    assert lower.suggestions == ["hund", "hunde"]
    assert capitalised.suggestions == ["Hund", "Hunde"]


def test_check_reports_a_word_nothing_is_close_to_without_suggestions(
    speller: Speller,
) -> None:
    assert speller.check("Xylophonkonzert") == [
        SpellingIssue("Xylophonkonzert", 0, 15, [])
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Wie geht's?",
        "Wie geht’s?",
        "ICH HABE USA",
        "a b c",
        "3 Hunde, 12.5 Hunde",
        "",
    ],
)
def test_check_accepts_contractions_capitals_single_letters_and_numbers(
    speller: Speller, text: str
) -> None:
    assert speller.check(text) == []


def test_check_gives_the_same_answer_when_a_word_is_checked_again(
    speller: Speller,
) -> None:
    first = speller.check("Hundd")

    assert speller.check("Hundd") == first


def test_speller_for_german_knows_common_words_and_corrects_typos() -> None:
    german = Speller("de")

    issues = german.check("Ich fahre mit dem Fahrad zum Krankenhaus.")

    assert [(issue.word, issue.suggestions[:1]) for issue in issues] == [
        ("Fahrad", ["Fahrrad"])
    ]
