# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import pytest
from languages import language_of
from spelling import Speller, SpellingIssue, StudySpeller, hunspell_of

# "hund" is listed twice so that it counts as the more common word
DICTIONARY = [
    "ich",
    "habe",
    "ein",
    "einen",
    "hund",
    "hund",
    "hunde",
    "geht",
    "wie",
    "es",
]


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


def test_check_leaves_a_grammar_error_of_correctly_spelled_words_to_the_profile(
    speller: Speller,
) -> None:
    # "einen" is right: the profile's grammar question is what finds this
    assert speller.check("Ich habe ein Hund.") == []
    assert [issue.word for issue in speller.check("Ich habe ein Hnud.")] == ["Hnud"]


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


def test_the_speller_of_the_language_being_studied_goes_by_that_language() -> None:
    speller = StudySpeller("German")

    in_german = speller.check("Der Hund und the dog.")
    speller.language = "English"
    in_english = speller.check("Der Hund und the dog.")

    assert [issue.word for issue in in_german] == ["the", "dog"]
    assert "Hund" in [issue.word for issue in in_english]
    assert "dog" not in [issue.word for issue in in_english]
    assert speller.knows("dog") and not speller.knows("Hund")


def test_a_sentence_is_spelled_by_the_language_most_of_it_is_written_in() -> None:
    speller = StudySpeller("German")

    german, in_german = speller.check_written("Ich habe einen dog.", ["English"])
    english, in_english = speller.check_written("I have a big Hund.", ["English"])

    assert (german, [issue.word for issue in in_german]) == ("German", ["dog"])
    assert (english, [issue.word for issue in in_english]) == ("English", ["Hund"])


def test_a_sentence_both_dictionaries_know_is_of_the_language_studied() -> None:
    speller = StudySpeller("German")

    assert speller.check_written("Hand", ["English"]) == ("German", [])
    assert speller.check_written("Hand", ["Klingon"]) == ("German", [])


def test_a_language_without_a_dictionary_has_no_word_found_wrong_or_known() -> None:
    speller = StudySpeller("Klingon")

    assert speller.check("nuqneH qqqq") == []
    assert speller.knows("nuqneH") is False


@pytest.fixture(scope="module")
def hunspell_german() -> Speller:
    """The speller of German with the system's Hunspell dictionary, if it
    has one."""
    hunspell = hunspell_of(language_of("German").hunspell)
    if hunspell is None:
        pytest.skip("the system has no Hunspell dictionary of German")
    return Speller("de", hunspell=hunspell)


def test_a_dictionary_the_system_has_not_is_none() -> None:
    assert hunspell_of("xx_NOPE") is None
    assert hunspell_of(None) is None


def test_hunspell_tells_a_word_from_one_misspelled() -> None:
    english = hunspell_of(language_of("English").hunspell)
    if english is None:
        pytest.skip("the system has no Hunspell dictionary of English")

    assert english.lookup("dogs") and english.lookup("unbelievably")
    assert not english.lookup("dgos")


@pytest.mark.parametrize(
    "text",
    [
        "Wir setzen uns für den Tierschutz ein.",
        "Das Hundefutter liegt neben der Bahnhofsuhr.",
        "Der Tierschutzverein hilft.",
    ],
)
def test_hunspell_accepts_compounds_that_are_listed_nowhere(
    hunspell_german: Speller, text: str
) -> None:
    assert hunspell_german.check(text) == []


def test_hunspell_finds_a_compound_misspelled(hunspell_german: Speller) -> None:
    assert [issue.word for issue in hunspell_german.check("Der Tierschuts")] == [
        "Tierschuts"
    ]


def test_hunspell_knows_no_word_with_letters_its_dictionary_cannot_write(
    hunspell_german: Speller,
) -> None:
    # the German dictionary is written in Latin-1, which has no "ő"
    assert not hunspell_german.knows("Hőnd")


def test_hunspell_suggests_a_noun_written_small_with_its_capital(
    hunspell_german: Speller,
) -> None:
    [issue] = hunspell_german.check("Ich habe einen hund.")

    assert issue.word == "hund"
    assert issue.suggestions[0] == "Hund"


def test_hunspell_suggests_only_words_it_has(hunspell_german: Speller) -> None:
    [issue] = hunspell_german.check("Meine Grosmutter")

    assert issue.suggestions[0] == "Großmutter"
    assert all(hunspell_german.knows(word) for word in issue.suggestions)
