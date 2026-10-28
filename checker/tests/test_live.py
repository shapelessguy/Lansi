# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import replace

import pytest
from live import LiveChecker
from models import Model
from profiling import (
    QUESTIONS,
    Answer,
    Profile,
    ProfileError,
    Profiler,
    Questions,
    WordRating,
)
from sentences import Sentence
from spelling import Speller
from translating import Corrected, TranslationError

WORDS = ["ich", "habe", "einen", "hund", "er", "ist", "gut", "sehr"]
KEY = "test-key"
# the usual model, on OpenRouter
KEYED = Model(key=KEY)
TWO = "Ich habe einen Hund. Er ist gut."


def question(about: str) -> dict[str, object]:
    return {
        "type": "choice",
        "instructions": f"Is the sentence {about}?",
        "criteria": {"yes": f"It is {about}.", "no": f"It is not {about}."},
    }


POLITE: Questions = {"polite": question("polite")}
THREE_QUESTIONS: Questions = {
    "polite": question("polite"),
    "formal": question("formal"),
    "short": question("short"),
}
YES = Answer("choice", choice="yes")


class FakeProfiler(Profiler):
    """Records what it is asked instead of asking Jev, and says yes to it."""

    def __init__(self) -> None:
        super().__init__()
        self.asked: list[str] = []
        self.keys: list[str] = []
        self.models: list[str | None] = []
        self.questions: list[Questions | None] = []
        # the sentences whose words were rated, each with what it was rated by
        self.rated: list[tuple[str, list[dict[str, str]]]] = []
        # the correction each sentence's words were rated with, if any
        self.corrections: list[str | None] = []
        self.failing = False

    def profile(
        self,
        sentence: str,
        model: Model,
        questions: Questions | None = None,
    ) -> Profile:
        self.asked.append(sentence)
        self.keys.append(model.key)
        self.models.append(model.name)
        self.questions.append(questions)

        if self.failing:
            raise ProfileError("no credit left")
        return Profile(
            {name: YES for name in questions or {}},
            cost=0.001,
            id=f"request-{len(self.asked)}",
            model=model.name,
            input_tokens=100,
        )

    def rate_words(
        self,
        sentence: str,
        assessment: list[dict[str, str]],
        model: Model,
        correction: str | None = None,
    ) -> tuple[list[WordRating], Profile]:
        self.rated.append((sentence, assessment))
        self.corrections.append(correction)
        if self.failing:
            raise ProfileError("no credit left")
        return ratings_of(sentence), Profile(
            {}, cost=0.002, id=f"rating-{len(self.rated)}", input_tokens=300
        )


def ratings_of(sentence: str) -> list[WordRating]:
    """What the fake makes of a sentence: its first word is half right."""
    word = sentence.split(maxsplit=1)[0]
    return [WordRating(word, 0, len(word), 0.5)]


@pytest.fixture
def profiler() -> FakeProfiler:
    return FakeProfiler()


@pytest.fixture
def checker(profiler: FakeProfiler) -> LiveChecker:
    """A checker whose questions are answered at once rather than on a thread."""
    return LiveChecker(
        Speller(language=None, words=WORDS), profiler, background=lambda job: job()
    )


def ask(
    checker: LiveChecker,
    text: str,
    caret: int | None = None,
    questions: Questions = POLITE,
) -> list[Sentence]:
    """Check a text with a key and, unless others are given, one question."""
    return checker.check(text, caret, KEYED, questions=questions)


def misspelled(checker: LiveChecker, text: str) -> list[list[str]]:
    """The misspelled words of each sentence."""
    return [[issue.word for issue in s.spelling] for s in checker.check(text)]


def processed(checker: LiveChecker, text: str, caret: int | None = None) -> list[bool]:
    return [sentence.processed for sentence in ask(checker, text, caret)]


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


def test_spell_checks_the_spelling_of_each_sentence_without_profiling_it(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    sentences = checker.spell("Ich habe einen Hundd. Er ist gut.")

    assert [[issue.word for issue in s.spelling] for s in sentences] == [["Hundd"], []]
    assert not any(sentence.processed or sentence.profiling for sentence in sentences)


def test_spelling_another_text_leaves_the_questions_out_about_the_checked_one(
    profiler: FakeProfiler,
) -> None:
    jobs: list[Callable[[], None]] = []
    checker = LiveChecker(
        Speller(language=None, words=WORDS), profiler, background=jobs.append
    )
    ask(checker, "Er ist gut.")

    checker.spell("Ein anderer Text.")
    for job in jobs:
        job()

    assert [sentence.processed for sentence in ask(checker, "Er ist gut.")] == [True]


# when a sentence is profiled


def test_a_sentence_is_profiled_when_the_caret_leaves_it(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask(checker, "Er ist gut.", caret=5)
    asked_while_typing = list(profiler.asked)

    ask(checker, "Er ist gut. ", caret=12)

    assert asked_while_typing == []
    assert profiler.asked == ["Er ist gut."]
    assert profiler.keys == [KEY]


def test_every_finished_sentence_is_profiled_but_not_the_one_being_typed(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask(checker, f"{TWO} Er ist se", caret=len(TWO) + 10)

    assert profiler.asked == ["Ich habe einen Hund.", "Er ist gut."]


def test_a_sentence_is_profiled_only_once_while_it_stays_the_same(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    for extra in ["", " Er", " Er ist", " Er ist sehr gut."]:
        ask(checker, TWO + extra, caret=len(TWO + extra))
    ask(checker, TWO)

    assert profiler.asked.count("Ich habe einen Hund.") == 1
    assert profiler.asked.count("Er ist gut.") == 1


def test_going_back_into_a_sentence_without_changing_it_does_not_profile_it_again(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask(checker, TWO)

    ask(checker, TWO, caret=5)
    ask(checker, TWO, caret=None)

    assert profiler.asked == ["Ich habe einen Hund.", "Er ist gut."]


def test_changing_a_sentence_profiles_the_new_wording_once_the_caret_leaves(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask(checker, TWO)
    changed = "Ich habe einen guten Hund. Er ist gut."

    ask(checker, changed, caret=20)
    asked_while_changing = list(profiler.asked)
    ask(checker, changed, caret=None)

    assert asked_while_changing == ["Ich habe einen Hund.", "Er ist gut."]
    assert profiler.asked[2:] == ["Ich habe einen guten Hund."]


def test_undoing_a_change_does_not_profile_the_earlier_wording_again(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask(checker, "Ich habe einen Hund.")
    ask(checker, "Ich habe einen Hundd.")

    ask(checker, "Ich habe einen Hund.")

    assert profiler.asked == ["Ich habe einen Hund.", "Ich habe einen Hundd."]


def test_nothing_is_profiled_without_a_key_until_one_is_given(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check("Er ist gut.", model=Model(), questions=POLITE)
    asked_without_key = list(profiler.asked)

    ask(checker, "Er ist gut.")

    assert asked_without_key == []
    assert profiler.asked == ["Er ist gut."]


def test_nothing_is_profiled_without_a_profiler() -> None:
    checker = LiveChecker(Speller(language=None, words=WORDS))

    (sentence,) = ask(checker, "Er ist gut.")

    assert (sentence.profiling, sentence.processed) == (False, False)


def test_a_sentence_is_profiled_with_the_model_asked_for(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check(TWO, model=Model("some/model", key=KEY), questions=POLITE)

    assert profiler.models == ["some/model", "some/model"]


def test_a_sentence_is_profiled_again_when_the_model_changes(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check("Er ist gut.", model=Model("one/model", key=KEY), questions=POLITE)
    checker.check("Er ist gut.", model=Model("other/model", key=KEY), questions=POLITE)

    assert profiler.models == ["one/model", "other/model"]


def test_a_sentence_is_profiled_again_when_the_language_studied_changes(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.study("German")
    ask(checker, "Er ist gut.")
    checker.study("English")
    ask(checker, "Er ist gut.")
    checker.study("German")
    ask(checker, "Er ist gut.")

    # what was answered in German before is still known
    assert profiler.asked.count("Er ist gut.") == 2


# the questions


def test_each_question_about_a_sentence_is_a_request_of_its_own(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask(checker, "Er ist gut.", questions=THREE_QUESTIONS)

    assert profiler.questions == [
        {name: asked} for name, asked in THREE_QUESTIONS.items()
    ]


def test_the_usual_questions_are_asked_when_none_are_given(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check("Er ist gut.", model=KEYED)

    assert profiler.questions == [{name: asked} for name, asked in QUESTIONS.items()]


def test_adding_a_question_asks_only_the_new_one(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask(checker, "Er ist gut.", questions=POLITE)

    ask(checker, "Er ist gut.", questions=THREE_QUESTIONS)

    assert [list(asked or {}) for asked in profiler.questions] == [
        ["polite"],
        ["formal"],
        ["short"],
    ]


def test_a_question_is_asked_again_when_it_is_reworded(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    reworded: Questions = {"polite": question("very polite")}
    ask(checker, "Er ist gut.", questions=POLITE)

    ask(checker, "Er ist gut.", questions=reworded)

    assert profiler.questions == [POLITE, reworded]


def test_going_back_to_earlier_questions_does_not_ask_them_again(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask(checker, "Er ist gut.", questions=POLITE)
    ask(checker, "Er ist gut.", questions={"formal": question("formal")})

    (sentence,) = ask(checker, "Er ist gut.", questions=POLITE)

    assert len(profiler.asked) == 2
    assert sentence.processed


def test_nothing_is_profiled_when_there_are_no_questions(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    sentences = ask(checker, TWO, questions={})

    assert profiler.asked == []
    assert [sentence.profiling for sentence in sentences] == [False, False]
    assert [sentence.processed for sentence in sentences] == [False, False]


# what a sentence says about its profile


def test_a_sentence_carries_the_answer_to_every_question_once_they_are_back(
    checker: LiveChecker,
) -> None:
    ask(checker, "Er ist gut.", questions=THREE_QUESTIONS)

    (sentence,) = ask(checker, "Er ist gut.", questions=THREE_QUESTIONS)

    assert sentence.profile == Profile({"polite": YES, "formal": YES, "short": YES})
    assert (sentence.processed, sentence.profiling) == (True, False)


def test_a_sentence_says_it_is_being_profiled_until_every_answer_is_back() -> None:
    waiting: list[Callable[[], None]] = []
    checker = LiveChecker(
        Speller(language=None, words=WORDS), FakeProfiler(), background=waiting.append
    )
    two: Questions = {"polite": question("polite"), "formal": question("formal")}

    (asked,) = ask(checker, "Er ist gut.", questions=two)
    waiting[0]()
    (half_answered,) = ask(checker, "Er ist gut.", questions=two)
    waiting[1]()
    (answered,) = ask(checker, "Er ist gut.", questions=two)

    assert (asked.profiling, asked.processed) == (True, False)
    assert (half_answered.profiling, half_answered.profile) == (True, None)
    assert (answered.profiling, answered.processed) == (False, True)
    assert len(waiting) == 2


def test_a_profiled_sentence_is_not_processed_while_the_caret_is_back_on_it(
    checker: LiveChecker,
) -> None:
    ask(checker, TWO)

    assert processed(checker, TWO, caret=5) == [False, True]
    assert processed(checker, TWO, caret=None) == [True, True]


def test_a_profiled_sentence_keeps_its_profile_while_the_caret_is_back_on_it(
    checker: LiveChecker,
) -> None:
    ask(checker, "Er ist gut.")

    (sentence,) = ask(checker, "Er ist gut.", caret=3)

    assert sentence.profile == Profile({"polite": YES})


def test_a_sentence_changed_under_the_caret_has_no_profile(
    checker: LiveChecker,
) -> None:
    ask(checker, "Er ist gut.")

    (sentence,) = ask(checker, "Er ist sehr gut.", caret=3)

    assert sentence.profile is None


def test_a_profiled_sentence_stays_processed_when_it_moves(
    checker: LiveChecker,
) -> None:
    ask(checker, "Er ist gut.")

    assert processed(checker, "Ich habe einen Hund.\nEr ist gut.") == [False, True]


def test_each_answer_is_announced_when_it_is_back(profiler: FakeProfiler) -> None:
    announced: list[tuple[str, Profile | None, str | None, bool]] = []
    checker = LiveChecker(
        Speller(language=None, words=WORDS),
        profiler,
        on_profiled=lambda *result: announced.append(result),
        background=lambda job: job(),
    )

    ask(checker, "Er ist gut.")

    ((sentence, profile, error, dropped),) = announced
    assert (sentence, error, dropped) == ("Er ist gut.", None, False)
    assert profile and profile.answers == {"polite": YES}


# what the requests cost


def test_every_request_is_billed_once(checker: LiveChecker) -> None:
    ask(checker, TWO, questions=THREE_QUESTIONS)

    used, pending = checker.billing()
    used_later, _ = checker.billing()

    assert [request.id for request in used] == [f"request-{n}" for n in range(1, 7)]
    assert sum(request.input_tokens for request in used) == 600
    assert pending is False
    assert used_later == []


def test_a_failed_request_is_not_billed(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    profiler.failing = True

    ask(checker, "Er ist gut.")

    assert checker.billing() == ([], False)


# when a question fails


def test_a_failed_question_leaves_the_sentence_unprocessed_with_the_reason(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    profiler.failing = True
    ask(checker, "Er ist gut.")

    (sentence,) = ask(checker, "Er ist gut.")

    assert sentence.profile is None
    assert sentence.profile_error == "no credit left"
    assert (sentence.processed, sentence.profiling) == (False, False)


def test_a_failed_question_is_not_asked_again_every_second(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    profiler.failing = True

    for _ in range(3):
        ask(checker, "Er ist gut.")

    assert profiler.asked == ["Er ist gut."]


def test_a_failed_question_is_asked_again_after_the_caret_returns_and_leaves(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    profiler.failing = True
    ask(checker, "Er ist gut.")
    profiler.failing = False

    ask(checker, "Er ist gut.", caret=3)
    (sentence,) = ask(checker, "Er ist gut.", caret=None)
    (later,) = ask(checker, "Er ist gut.")

    assert profiler.asked == ["Er ist gut.", "Er ist gut."]
    assert sentence.profile_error is None
    assert later.processed is True


def test_the_oldest_answers_are_forgotten_when_too_many_are_remembered(
    profiler: FakeProfiler,
) -> None:
    checker = LiveChecker(
        Speller(language=None, words=["eins", "zwei", "drei"]),
        profiler,
        background=lambda job: job(),
        max_remembered=2,
    )
    ask(checker, "Eins.")

    ask(checker, "Zwei. Drei.")
    ask(checker, "Eins.")

    assert profiler.asked == ["Eins.", "Zwei.", "Drei.", "Eins."]


# rating the words


def rate(checker: LiveChecker, text: str, caret: int | None = None) -> list[Sentence]:
    """Check a text with a key and one question, and have the words rated."""
    return checker.check(text, caret, KEYED, questions=POLITE, rate_words=True)


def test_the_words_of_a_sentence_are_rated_once_it_is_profiled_by_what_was_found(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    rate(checker, "Er ist gut.")
    rated_before_the_profile = list(profiler.rated)

    rate(checker, "Er ist gut.")

    assert rated_before_the_profile == []
    assert profiler.rated == [
        (
            "Er ist gut.",
            [{"question": "Is the sentence polite?", "answer": "yes: It is polite."}],
        )
    ]


def test_a_sentence_carries_the_ratings_of_its_words_once_they_are_back(
    checker: LiveChecker,
) -> None:
    for _ in range(2):
        rate(checker, "Er ist gut.")

    (sentence,) = rate(checker, "Er ist gut.")

    assert sentence.words == [WordRating("Er", 0, 2, 0.5)]
    assert (sentence.rating_words, sentence.processed) == (False, True)


def test_the_words_of_a_sentence_are_rated_only_once(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    for _ in range(4):
        rate(checker, "Er ist gut.")
    rate(checker, "Er ist gut.", caret=3)
    rate(checker, "Er ist gut.")

    assert len(profiler.rated) == 1


def test_words_are_not_rated_unless_it_is_asked_for(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    for _ in range(3):
        (sentence,) = ask(checker, "Er ist gut.")

    assert profiler.rated == []
    assert sentence.words == []


def test_the_ratings_of_words_are_weighed_by_how_wrong_the_sentence_was_found() -> None:
    class SureProfiler(FakeProfiler):
        """Finds every sentence nearly as good as can be."""

        def profile(
            self,
            sentence: str,
            model: Model,
            questions: Questions | None = None,
        ) -> Profile:
            profile = super().profile(sentence, model, questions)
            profile.answers = {
                name: replace(answer, best=0.9)
                for name, answer in profile.answers.items()
            }
            return profile

    checker = LiveChecker(
        Speller(language=None, words=WORDS),
        SureProfiler(),
        background=lambda job: job(),
    )
    for _ in range(2):
        rate(checker, "Er ist gut.")

    (sentence,) = rate(checker, "Er ist gut.")

    # the word was rated 0.5, in a sentence with a tenth to doubt
    assert [word.value for word in sentence.words] == pytest.approx([0.95])


def test_a_sentence_without_words_is_not_rated(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    for _ in range(3):
        rate(checker, "...")

    assert profiler.rated == []


def test_a_sentence_says_its_words_are_being_rated_until_the_ratings_are_back() -> None:
    waiting: list[Callable[[], None]] = []
    checker = LiveChecker(
        Speller(language=None, words=WORDS), FakeProfiler(), background=waiting.append
    )
    rate(checker, "Er ist gut.")
    waiting.pop()()

    (asked,) = rate(checker, "Er ist gut.")
    _, pending = checker.billing()
    waiting.pop()()
    (rated,) = rate(checker, "Er ist gut.")

    assert (asked.rating_words, asked.words) == (True, [])
    assert pending is True
    assert (rated.rating_words, len(rated.words)) == (False, 1)
    assert checker.billing()[1] is False


def test_a_sentence_keeps_the_ratings_of_its_words_while_the_caret_is_back_on_it(
    checker: LiveChecker,
) -> None:
    for _ in range(2):
        rate(checker, "Er ist gut.")

    (sentence,) = rate(checker, "Er ist gut.", caret=3)

    assert sentence.words == [WordRating("Er", 0, 2, 0.5)]


def test_a_sentence_changed_while_its_words_are_rated_drops_them_but_not_the_bill() -> (
    None
):
    waiting: list[Callable[[], None]] = []
    announced: list[tuple[str, bool]] = []
    checker = LiveChecker(
        Speller(language=None, words=WORDS),
        FakeProfiler(),
        background=waiting.append,
        on_rated=lambda sentence, _ratings, _error, dropped: announced.append(
            (sentence, dropped)
        ),
    )
    rate(checker, "Er ist gut.")
    waiting.pop()()
    rate(checker, "Er ist gut.")
    checker.billing()

    # the writer adds a word while the rating is out
    rate(checker, "Er ist sehr gut.", caret=10)
    waiting.pop()()
    used, pending = checker.billing()
    # without a key nothing new is asked, so this shows only what was kept
    (as_before,) = checker.check("Er ist gut.", questions=POLITE, rate_words=True)

    assert as_before.words == []
    assert [request.id for request in used] == ["rating-1"]
    assert pending is False
    assert announced == [("Er ist gut.", True)]


def test_rating_the_words_is_billed(checker: LiveChecker) -> None:
    for _ in range(2):
        rate(checker, "Er ist gut.")

    used, _ = checker.billing()

    assert [request.id for request in used] == ["request-1", "rating-1"]


def test_words_that_could_not_be_rated_leave_the_reason_and_are_not_tried_every_time(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    rate(checker, "Er ist gut.")
    profiler.failing = True

    for _ in range(3):
        (sentence,) = rate(checker, "Er ist gut.")

    assert len(profiler.rated) == 1
    assert (sentence.words, sentence.profile_error) == ([], "no credit left")


# a model at an address of the learner's own

AT_HOME = Model("local/clef", "http://127.0.0.1:10000/v1")


def ask_at_home(
    checker: LiveChecker, text: str, questions: Questions = POLITE
) -> list[Sentence]:
    return checker.check(text, None, AT_HOME, questions=questions)


def test_a_model_at_an_address_is_asked_all_the_questions_about_a_sentence_at_once(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask_at_home(checker, TWO, questions=THREE_QUESTIONS)
    sentences = ask_at_home(checker, TWO, questions=THREE_QUESTIONS)

    assert profiler.asked == ["Ich habe einen Hund.", "Er ist gut."]
    assert profiler.questions == [THREE_QUESTIONS, THREE_QUESTIONS]
    assert [sentence.processed for sentence in sentences] == [True, True]


def test_a_model_at_an_address_is_asked_without_an_openrouter_key(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask_at_home(checker, "Er ist gut.")

    assert (profiler.asked, profiler.keys) == (["Er ist gut."], [""])


def test_a_model_at_an_address_is_asked_only_the_questions_it_has_not_answered(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    ask_at_home(checker, "Er ist gut.", questions=POLITE)

    ask_at_home(checker, "Er ist gut.", questions=THREE_QUESTIONS)

    assert [list(asked or {}) for asked in profiler.questions] == [
        ["polite"],
        ["formal", "short"],
    ]


def test_a_sentence_is_profiled_again_by_a_model_of_the_same_id_elsewhere(
    checker: LiveChecker, profiler: FakeProfiler
) -> None:
    checker.check("Er ist gut.", model=Model("local/clef", key=KEY), questions=POLITE)
    ask_at_home(checker, "Er ist gut.")

    assert len(profiler.asked) == 2


# Profiling on threads. A request to Jev is stood in for by one that takes
# three seconds, which is longer than a real one should, so that there is
# time to change the text while requests are out.

REQUEST_SECS = 3.0
# how long a thread may take to notice that its request is back
SLACK_SECS = 1.0


class SlowProfiler(FakeProfiler):
    """Takes three seconds to answer, and notes how many requests it was
    answering at the same time."""

    def __init__(self) -> None:
        super().__init__()
        self._counting = threading.Lock()
        self._running = 0
        self.most_at_once = 0

    def profile(
        self,
        sentence: str,
        model: Model,
        questions: Questions | None = None,
    ) -> Profile:
        with self._counting:
            self._running += 1
            self.most_at_once = max(self.most_at_once, self._running)
            answer = super().profile(sentence, model, questions)
        time.sleep(REQUEST_SECS)
        with self._counting:
            self._running -= 1
        return answer


class Threads:
    """Starts each job on a thread of its own, as the checker does when left
    to itself, and keeps the threads so that they can be watched."""

    def __init__(self) -> None:
        self.started: list[threading.Thread] = []

    def __call__(self, job: Callable[[], None]) -> None:
        thread = threading.Thread(target=job, daemon=True)
        self.started.append(thread)
        thread.start()

    def alive(self) -> int:
        return sum(thread.is_alive() for thread in self.started)

    def wait_until_all_have_ended(self) -> float:
        """Wait for the threads to end by themselves, without asking them
        to, and return how long that took."""
        began = time.monotonic()
        while self.alive():
            assert time.monotonic() - began < REQUEST_SECS + SLACK_SECS
            time.sleep(0.05)
        return time.monotonic() - began


@pytest.fixture
def slow() -> SlowProfiler:
    return SlowProfiler()


@pytest.fixture
def threads() -> Threads:
    return Threads()


@pytest.fixture
def threaded(slow: SlowProfiler, threads: Threads) -> LiveChecker:
    return LiveChecker(Speller(language=None, words=WORDS), slow, background=threads)


def test_checking_a_text_does_not_wait_for_the_sentence_to_be_profiled(
    slow: SlowProfiler,
) -> None:
    # left to start its own threads
    checker = LiveChecker(Speller(language=None, words=WORDS), slow)
    began = time.monotonic()

    (at_once,) = ask(checker, "Er ist gut.")
    took = time.monotonic() - began
    (meanwhile,) = ask(checker, "Er ist gut.")
    time.sleep(REQUEST_SECS + SLACK_SECS)
    (afterwards,) = ask(checker, "Er ist gut.")

    assert took < 0.5
    assert (at_once.profiling, at_once.processed) == (True, False)
    assert (meanwhile.profiling, meanwhile.processed) == (True, False)
    assert (afterwards.profiling, afterwards.processed) == (False, True)
    assert slow.asked == ["Er ist gut."]


def test_every_question_about_every_finished_sentence_is_out_at_the_same_time(
    threaded: LiveChecker, slow: SlowProfiler, threads: Threads
) -> None:
    ask(threaded, TWO, questions=THREE_QUESTIONS)
    out_at_once = threads.alive()
    _, pending = threaded.billing()

    took = threads.wait_until_all_have_ended()
    sentences = ask(threaded, TWO, questions=THREE_QUESTIONS)

    # two sentences with three questions each
    assert out_at_once == 6
    assert slow.most_at_once == 6
    assert pending is True
    # one after the other, they would have taken eighteen seconds
    assert took < REQUEST_SECS + SLACK_SECS
    assert [sentence.processed for sentence in sentences] == [True, True]
    assert threaded.billing()[1] is False


def test_a_sentence_changed_while_it_is_profiled_drops_the_answers_but_not_the_bill(
    threaded: LiveChecker, slow: SlowProfiler, threads: Threads
) -> None:
    ask(threaded, "Er ist gut.", questions=THREE_QUESTIONS)
    time.sleep(0.5)

    # the writer goes back into the sentence and adds a word
    (changing,) = ask(threaded, "Er ist sehr gut.", caret=10, questions=THREE_QUESTIONS)
    still_out = threads.alive()
    threads.wait_until_all_have_ended()
    used, pending = threaded.billing()
    (changed,) = ask(threaded, "Er ist sehr gut.", caret=10, questions=THREE_QUESTIONS)
    # without a key nothing new is asked, so this shows only what was kept
    (as_before,) = threaded.check("Er ist gut.", questions=THREE_QUESTIONS)

    assert (changing.profiling, changing.profile) == (False, None)
    # the requests are not cut short: their threads run out by themselves
    assert still_out == 3
    assert (changed.profiling, changed.profile) == (False, None)
    assert (as_before.processed, as_before.profile) == (False, None)
    # nothing more was asked, and what was asked is billed
    assert slow.asked == ["Er ist gut."] * 3
    assert len(used) == 3
    assert pending is False


def test_going_back_onto_a_sentence_while_it_is_profiled_drops_the_answers_but_not_the_bill(
    threaded: LiveChecker, slow: SlowProfiler, threads: Threads
) -> None:
    ask(threaded, TWO)
    time.sleep(0.5)

    # the caret returns to the first sentence, which goes back to being typed
    first, second = ask(threaded, TWO, caret=5)
    threads.wait_until_all_have_ended()
    used, _ = threaded.billing()
    first_later, second_later = ask(threaded, TWO, caret=5)

    assert (first.complete, first.profiling) == (False, False)
    assert second.profiling is True
    # the answer about the first sentence is dropped, the other one is kept
    assert (first_later.profile, first_later.processed) == (None, False)
    assert second_later.processed is True
    assert len(used) == 2

    # leaving the sentence again starts over
    (again, _) = ask(threaded, TWO)
    assert again.profiling is True
    assert slow.asked.count("Ich habe einen Hund.") == 2


def test_announcing_an_answer_says_whether_it_was_dropped(
    slow: SlowProfiler, threads: Threads
) -> None:
    announced: list[tuple[str, bool]] = []
    checker = LiveChecker(
        Speller(language=None, words=WORDS),
        slow,
        on_profiled=lambda sentence, _profile, _error, dropped: announced.append(
            (sentence, dropped)
        ),
        background=threads,
    )
    ask(checker, TWO)

    ask(checker, "Er ist gut.")
    threads.wait_until_all_have_ended()

    assert sorted(announced) == [("Er ist gut.", False), ("Ich habe einen Hund.", True)]


# correcting


class FakeCorrector:
    """Writes "Correct: " before a sentence instead of asking a language
    model, and records what it was asked."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, str, Model, str]] = []
        self.failing = False

    def __call__(
        self, sentence: str, language: str, model: Model, into: str
    ) -> tuple[Corrected, Profile]:
        self.asked.append((sentence, language, model, into))
        if self.failing:
            raise TranslationError("no credit left")
        return Corrected(f"Correct: {sentence}", f"In {into}: {sentence}"), Profile(
            {}, cost=0.003, id=f"correction-{len(self.asked)}", input_tokens=50
        )


# the language model the sentences are corrected by
WRITER = Model("some/writer", key=KEY)


def correcting(
    corrector: FakeCorrector,
    background: Callable[[Callable[[], None]], None] = lambda job: job(),
    on_corrected: Callable[[str, str | None, str | None, bool], None] | None = None,
    profiler: FakeProfiler | None = None,
) -> LiveChecker:
    profiler = profiler or FakeProfiler()
    profiler.language = "German"
    return LiveChecker(
        Speller(language=None, words=WORDS),
        profiler,
        background=background,
        corrector=corrector,
        on_corrected=on_corrected,
    )


def correct(
    checker: LiveChecker, text: str, caret: int | None = None, rate_words: bool = False
) -> list[Sentence]:
    return checker.check(text, caret, KEYED, POLITE, rate_words, correct_with=WRITER)


def test_the_questions_and_the_correction_are_sent_at_the_same_time() -> None:
    waiting: list[Callable[[], None]] = []
    profiler, corrector = FakeProfiler(), FakeCorrector()
    checker = correcting(corrector, background=waiting.append, profiler=profiler)

    correct(checker, "Er ist gut.")
    for job in waiting:
        job()

    assert profiler.asked == ["Er ist gut."]
    assert [sentence for sentence, *_ in corrector.asked] == ["Er ist gut."]


def test_the_words_wait_for_the_correction_and_are_rated_with_it() -> None:
    waiting: list[Callable[[], None]] = []
    profiler = FakeProfiler()
    checker = correcting(FakeCorrector(), background=waiting.append, profiler=profiler)
    correct(checker, "Er ist gut.", rate_words=True)
    # the answers are back, and the correction is not
    waiting.pop(1)()

    (before,) = correct(checker, "Er ist gut.", rate_words=True)
    rated_before = list(profiler.rated)
    waiting.pop()()
    correct(checker, "Er ist gut.", rate_words=True)
    waiting.pop()()
    (after,) = correct(checker, "Er ist gut.", rate_words=True)

    assert (rated_before, before.rating_words) == ([], True)
    assert profiler.corrections == ["Correct: Er ist gut."]
    assert after.words == [WordRating("Er", 0, 2, 0.5)]


def test_the_words_are_rated_without_a_correction_that_could_not_be_had() -> None:
    profiler, corrector = FakeProfiler(), FakeCorrector()
    corrector.failing = True
    checker = correcting(corrector, profiler=profiler)

    for _ in range(2):
        correct(checker, "Er ist gut.", rate_words=True)

    assert profiler.corrections == [None]


def test_a_sentence_is_corrected_alongside_its_questions_when_the_caret_leaves_it() -> (
    None
):
    corrector = FakeCorrector()
    checker = correcting(corrector)

    correct(checker, "Ich habe ein Hund.", caret=5)
    assert corrector.asked == []

    correct(checker, "Ich habe ein Hund.")
    (sentence,) = correct(checker, "Ich habe ein Hund.")

    assert corrector.asked == [("Ich habe ein Hund.", "German", WRITER, "English")]
    assert sentence.correction == "Correct: Ich habe ein Hund."
    assert sentence.correction_translation == "In English: Ich habe ein Hund."
    assert sentence.profile is not None


def test_a_sentence_is_corrected_again_when_it_is_to_be_translated_into_another_language() -> (
    None
):
    corrector = FakeCorrector()
    checker = correcting(corrector)

    for into in ("Italian", "English"):
        checker.check(
            "Er ist gut.", None, KEYED, POLITE, correct_with=WRITER, into=into
        )
    # what was asked is read back the next time
    (sentence,) = checker.check(
        "Er ist gut.", None, KEYED, POLITE, correct_with=WRITER, into="English"
    )

    assert [into for *_, into in corrector.asked] == ["Italian", "English"]
    assert sentence.correction_translation == "In English: Er ist gut."


def test_a_sentence_is_not_corrected_unless_it_is_asked_for() -> None:
    corrector = FakeCorrector()
    checker = correcting(corrector)

    (sentence,) = checker.check("Ich habe ein Hund.", None, KEYED, POLITE)

    assert corrector.asked == []
    assert sentence.correction is None


def test_a_sentence_is_corrected_only_once_while_it_stays_the_same() -> None:
    corrector = FakeCorrector()
    checker = correcting(corrector)

    for caret in (None, None, 3, None):
        correct(checker, "Ich habe ein Hund.", caret)

    assert len(corrector.asked) == 1


def test_a_sentence_says_it_is_being_corrected_until_the_correction_is_back() -> None:
    waiting: list[Callable[[], None]] = []
    checker = correcting(FakeCorrector(), background=waiting.append)

    (asked,) = correct(checker, "Er ist gut.")
    for job in waiting:
        job()
    (corrected,) = correct(checker, "Er ist gut.")

    assert (asked.correcting, asked.correction) == (True, None)
    assert (corrected.correcting, corrected.correction) == (
        False,
        "Correct: Er ist gut.",
    )


def test_a_sentence_keeps_its_correction_while_the_caret_is_back_on_it() -> None:
    checker = correcting(FakeCorrector())
    correct(checker, "Er ist gut.")

    (sentence,) = correct(checker, "Er ist gut.", caret=3)

    assert sentence.correction == "Correct: Er ist gut."


def test_a_sentence_changed_while_it_is_corrected_drops_the_correction_but_not_the_bill() -> (
    None
):
    waiting: list[Callable[[], None]] = []
    announced: list[tuple[str, bool]] = []
    checker = correcting(
        FakeCorrector(),
        background=waiting.append,
        on_corrected=lambda sentence, _correction, _error, dropped: announced.append(
            (sentence, dropped)
        ),
    )
    correct(checker, "Er ist gut.")

    # the writer adds a word while the correction is out
    correct(checker, "Er ist sehr gut.", caret=10)
    for job in waiting:
        job()
    used, pending = checker.billing()

    assert "correction-1" in [request.id for request in used]
    assert pending is False
    assert announced == [("Er ist gut.", True)]


def test_a_failed_correction_leaves_the_reason_and_is_tried_again_after_the_caret_returns() -> (
    None
):
    corrector = FakeCorrector()
    corrector.failing = True
    checker = correcting(corrector)

    correct(checker, "Er ist gut.")
    (failed,) = correct(checker, "Er ist gut.")
    corrector.failing = False
    correct(checker, "Er ist gut.", caret=3)
    correct(checker, "Er ist gut.")
    (corrected,) = correct(checker, "Er ist gut.")

    assert (failed.correction, failed.correction_error) == (None, "no credit left")
    assert corrected.correction == "Correct: Er ist gut."
    assert len(corrector.asked) == 2


def test_a_correction_is_billed(checker: LiveChecker) -> None:
    checker = correcting(FakeCorrector())

    correct(checker, "Er ist gut.")
    used, _ = checker.billing()

    assert sorted(request.id for request in used) == ["correction-1", "request-1"]


def test_nothing_is_corrected_without_a_key() -> None:
    corrector = FakeCorrector()
    checker = correcting(corrector)

    checker.check("Er ist gut.", correct_with=Model("some/writer"))

    assert corrector.asked == []


def test_boxes_checked_in_turn_leave_alone_what_is_out_about_each_other() -> None:
    waiting: list[Callable[[], None]] = []
    profiler, corrector = FakeProfiler(), FakeCorrector()
    checker = correcting(corrector, background=waiting.append, profiler=profiler)

    # two boxes of an exercise, checked again and again while all is out
    for _ in range(5):
        for box, text in (("a", "Er ist gut."), ("b", "Sie ist klug.")):
            checker.check(text, None, KEYED, POLITE, correct_with=WRITER, box=box)
    for job in waiting:
        job()
    (first,) = checker.check(
        "Er ist gut.", None, KEYED, POLITE, correct_with=WRITER, box="a"
    )

    assert sorted(sentence for sentence, *_ in corrector.asked) == [
        "Er ist gut.",
        "Sie ist klug.",
    ]
    assert sorted(profiler.asked) == ["Er ist gut.", "Sie ist klug."]
    assert first.correction == "Correct: Er ist gut."


def test_a_box_gives_up_what_is_out_about_its_own_sentence_once_it_changed() -> None:
    waiting: list[Callable[[], None]] = []
    announced: list[tuple[str, bool]] = []
    checker = correcting(
        FakeCorrector(),
        background=waiting.append,
        on_corrected=lambda sentence, _correction, _error, dropped: announced.append(
            (sentence, dropped)
        ),
    )

    checker.check("Er ist gut.", None, KEYED, POLITE, correct_with=WRITER, box="a")
    checker.check("Sie ist klug.", None, KEYED, POLITE, correct_with=WRITER, box="b")
    checker.check("Er ist sehr gut.", None, KEYED, POLITE, correct_with=WRITER, box="a")
    for job in waiting:
        job()

    assert ("Er ist gut.", True) in announced
    assert ("Sie ist klug.", False) in announced
