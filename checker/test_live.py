# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from collections.abc import Callable

import pytest
from live import LiveChecker
from profiling import Answer, Profile, ProfileError, Profiler
from spelling import Speller

WORDS = ["ich", "habe", "einen", "hund", "er", "ist", "gut", "sehr"]
KEY = "test-key"
TWO = "Ich habe einen Hund. Er ist gut."
PROFILE = Profile({"grammar_errors": Answer("choice", choice="none")})


class FakeProfiler(Profiler):
    """Records what it is asked instead of asking Jev."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self.keys: list[str] = []
        self.models: list[str | None] = []
        self.failing = False

    def profile(self, sentence: str, api_key: str, model: str | None = None) -> Profile:
        self.asked.append(sentence)
        self.keys.append(api_key)
        self.models.append(model)
        if self.failing:
            raise ProfileError("no credit left")
        return PROFILE


@pytest.fixture
def profiler() -> FakeProfiler:
    return FakeProfiler()


@pytest.fixture
def checker(profiler: FakeProfiler) -> LiveChecker:
    """A checker whose profiles are made at once rather than on another thread."""
    return LiveChecker(
        Speller(language=None, words=WORDS), profiler, background=lambda job: job()
    )


def misspelled(checker: LiveChecker, text: str) -> list[list[str]]:
    """The misspelled words of each sentence."""
    return [[issue.word for issue in s.spelling] for s in checker.check(text)]


def processed(checker: LiveChecker, text: str, caret: int | None = None) -> list[bool]:
    return [sentence.processed for sentence in checker.check(text, caret, KEY)]


# spelling


def test_check_gives_each_sentence_its_own_spelling_result(
    checker: LiveChecker,
) -> None:
    text = "Ich habe einen Hundd. Er ist gut. Er isst sehr gu"

    assert misspelled(checker, text) == [["Hundd"], [], ["isst", "gu"]]


def test_check_places_spelling_issues_within_their_sentence(
    checker: LiveChecker,
) -> None:
    _, second = checker.check("Er ist gut. Ich habe einen Hundd.")

    issue = second.spelling[0]
    assert second.text[issue.start : issue.end] == "Hundd"


def test_a_sentence_the_caret_is_on_is_still_spell_checked(
    checker: LiveChecker,
) -> None:
    first, _ = checker.check("Ich habe einen Hundd. Er ist gut.", caret=3)

    assert [issue.word for issue in first.spelling] == ["Hundd"]


# when a sentence is profiled


def test_a_sentence_is_profiled_when_the_caret_leaves_it(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check("Er ist gut.", caret=5, api_key=KEY)
    asked_while_typing = list(profiler.asked)

    checker.check("Er ist gut. ", caret=12, api_key=KEY)

    assert asked_while_typing == []
    assert profiler.asked == ["Er ist gut."]
    assert profiler.keys == [KEY]


def test_every_finished_sentence_is_profiled_but_not_the_one_being_typed(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check(f"{TWO} Er ist se", caret=len(TWO) + 10, api_key=KEY)

    assert profiler.asked == ["Ich habe einen Hund.", "Er ist gut."]


def test_a_sentence_is_profiled_only_once_while_it_stays_the_same(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    for extra in ["", " Er", " Er ist", " Er ist sehr gut."]:
        checker.check(TWO + extra, caret=len(TWO + extra), api_key=KEY)
    checker.check(TWO, api_key=KEY)

    assert profiler.asked.count("Ich habe einen Hund.") == 1
    assert profiler.asked.count("Er ist gut.") == 1


def test_going_back_into_a_sentence_without_changing_it_does_not_profile_it_again(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check(TWO, api_key=KEY)

    checker.check(TWO, caret=5, api_key=KEY)
    checker.check(TWO, caret=None, api_key=KEY)

    assert profiler.asked == ["Ich habe einen Hund.", "Er ist gut."]


def test_changing_a_sentence_profiles_the_new_wording_once_the_caret_leaves(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check(TWO, api_key=KEY)
    changed = "Ich habe einen guten Hund. Er ist gut."

    checker.check(changed, caret=20, api_key=KEY)
    asked_while_changing = list(profiler.asked)
    checker.check(changed, caret=None, api_key=KEY)

    assert asked_while_changing == ["Ich habe einen Hund.", "Er ist gut."]
    assert profiler.asked[2:] == ["Ich habe einen guten Hund."]


def test_undoing_a_change_does_not_profile_the_earlier_wording_again(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check("Ich habe einen Hund.", api_key=KEY)
    checker.check("Ich habe einen Hundd.", api_key=KEY)

    checker.check("Ich habe einen Hund.", api_key=KEY)

    assert profiler.asked == ["Ich habe einen Hund.", "Ich habe einen Hundd."]


def test_nothing_is_profiled_without_a_key_until_one_is_given(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check("Er ist gut.", api_key=None)
    asked_without_key = list(profiler.asked)

    checker.check("Er ist gut.", api_key=KEY)

    assert asked_without_key == []
    assert profiler.asked == ["Er ist gut."]


def test_a_sentence_is_profiled_with_the_model_asked_for(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check(TWO, api_key=KEY, model="some/model")

    assert profiler.models == ["some/model", "some/model"]


def test_nothing_is_profiled_without_a_profiler() -> None:
    checker = LiveChecker(Speller(language=None, words=WORDS))

    (sentence,) = checker.check("Er ist gut.", api_key=KEY)

    assert (sentence.profiling, sentence.processed) == (False, False)


# what a sentence says about its profile


def test_a_sentence_carries_its_profile_once_it_is_made(checker: LiveChecker) -> None:
    checker.check("Er ist gut.", api_key=KEY)

    (sentence,) = checker.check("Er ist gut.", api_key=KEY)

    assert sentence.profile == PROFILE
    assert (sentence.processed, sentence.profiling) == (True, False)


def test_a_sentence_says_it_is_being_profiled_until_the_answer_is_back(
    profiler: FakeProfiler,
) -> None:
    waiting: list[Callable[[], None]] = []
    checker = LiveChecker(
        Speller(language=None, words=WORDS), profiler, background=waiting.append
    )

    (asked,) = checker.check("Er ist gut.", api_key=KEY)
    (still_waiting,) = checker.check("Er ist gut.", api_key=KEY)
    waiting[0]()
    (answered,) = checker.check("Er ist gut.", api_key=KEY)

    assert (asked.profiling, asked.processed) == (True, False)
    assert (still_waiting.profiling, still_waiting.processed) == (True, False)
    assert (answered.profiling, answered.processed) == (False, True)
    assert len(waiting) == 1


def test_a_profiled_sentence_is_not_processed_while_the_caret_is_back_on_it(
    checker: LiveChecker,
) -> None:
    checker.check(TWO, api_key=KEY)

    assert processed(checker, TWO, caret=5) == [False, True]
    assert processed(checker, TWO, caret=None) == [True, True]


def test_a_profiled_sentence_stays_processed_when_it_moves(
    checker: LiveChecker,
) -> None:
    checker.check("Er ist gut.", api_key=KEY)

    assert processed(checker, "Ich habe einen Hund.\nEr ist gut.") == [False, True]


def test_the_profile_is_announced_when_it_is_made(profiler: FakeProfiler) -> None:
    announced: list[tuple[str, Profile | None, str | None]] = []
    checker = LiveChecker(
        Speller(language=None, words=WORDS),
        profiler,
        on_profiled=lambda *result: announced.append(result),
        background=lambda job: job(),
    )

    checker.check("Er ist gut.", api_key=KEY)

    assert announced == [("Er ist gut.", PROFILE, None)]


# when profiling fails


def test_a_failed_profile_leaves_the_sentence_unprocessed_with_the_reason(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    profiler.failing = True
    checker.check("Er ist gut.", api_key=KEY)

    (sentence,) = checker.check("Er ist gut.", api_key=KEY)

    assert sentence.profile is None
    assert sentence.profile_error == "no credit left"
    assert (sentence.processed, sentence.profiling) == (False, False)


def test_a_failed_profile_is_not_tried_again_every_second(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    profiler.failing = True

    for _ in range(3):
        checker.check("Er ist gut.", api_key=KEY)

    assert profiler.asked == ["Er ist gut."]


def test_a_failed_profile_is_tried_again_after_the_caret_returns_and_leaves(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    profiler.failing = True
    checker.check("Er ist gut.", api_key=KEY)
    profiler.failing = False

    checker.check("Er ist gut.", caret=3, api_key=KEY)
    (sentence,) = checker.check("Er ist gut.", caret=None, api_key=KEY)
    (later,) = checker.check("Er ist gut.", api_key=KEY)

    assert profiler.asked == ["Er ist gut.", "Er ist gut."]
    assert sentence.profile_error is None
    assert later.processed is True


def test_the_oldest_sentences_are_forgotten_when_too_many_are_remembered(
    profiler: FakeProfiler,
) -> None:
    checker = LiveChecker(
        Speller(language=None, words=["eins", "zwei", "drei"]),
        profiler,
        background=lambda job: job(),
        max_remembered=2,
    )
    checker.check("Eins.", api_key=KEY)

    checker.check("Zwei. Drei.", api_key=KEY)
    checker.check("Eins.", api_key=KEY)

    assert profiler.asked == ["Eins.", "Zwei.", "Drei.", "Eins."]
