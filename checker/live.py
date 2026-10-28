# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Checks a text that is sent again and again while it is being typed."""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any, Literal

from models import Model
from profiling import (
    QUESTIONS,
    Answer,
    Profile,
    ProfileError,
    Profiler,
    Questions,
    WordRating,
    describe_assessment,
    doubt_about,
    has_words,
    weigh_ratings,
)
from sentences import Sentence, split_sentences
from spelling import Speller, StudySpeller
from translating import Corrected, TranslationError

# Runs a job without making the caller wait for it.
Background = Callable[[Callable[[], None]], None]
# Told when a question about a sentence has come back: the sentence, the
# answer or else why there is none, and whether the answer was dropped
# because the sentence was changed or gone back to in the meantime.
OnProfiled = Callable[[str, "Profile | None", "str | None", bool], None]
# Told when the words of a sentence have been rated: the sentence, the
# ratings or else why there are none, and whether they were dropped.
OnRated = Callable[[str, "list[WordRating] | None", "str | None", bool], None]
# Writes a sentence, by someone learning a language, as it should be, with
# what it means and what asking for it used: the sentence, the language, the
# model to ask and the language it is translated into. Raises
# TranslationError.
Corrector = Callable[[str, str, Model, str], tuple[Corrected, Profile]]
# Told when a sentence has been corrected: the sentence, the correction or
# else why there is none, and whether it was dropped.
OnCorrected = Callable[[str, "str | None", "str | None", bool], None]
# A sentence's wording, the model asked with the language the sentence is
# judged by, and a question's name and content.
_Key = tuple[str, str, str, str]
# The name, in a key, of the rating of a sentence's words. No question can
# have it, as it is not a name that can be sent.
_WORDS = "\0words"
# The name, in a key, of the correction of a sentence.
_CORRECTION = "\0correction"


def in_a_thread(job: Callable[[], None]) -> None:
    """Runs the job on a thread of its own, which ends when the job does."""
    threading.Thread(target=job, name="profile", daemon=True).start()


@dataclass
class _Asked:
    """One question about one wording of a sentence."""

    state: Literal["asking", "answered", "failed"] = "asking"
    answer: Answer | None = None
    # The ratings, when what was asked is how right each word is.
    words: list[WordRating] | None = None
    # The sentence as it should be, when that is what was asked, and what it
    # means in the language the learner reads.
    correction: str | None = None
    translation: str | None = None
    error: str | None = None
    # The sentence was changed or gone back to while the question was out.
    # Its answer is not kept when it comes back.
    dropped: bool = False
    # The text box whose sentence it was asked about, which alone gives it up.
    box: str = ""


# A question that is to be asked, where its answer is kept, and the answer.
_Question = tuple[dict[str, Any], _Key, _Asked]


class LiveChecker:
    """Remembers what it found out about each sentence.

    The text arrives whole each time, and any sentence in it may have been
    edited since the last time, not only the last one. Sentences are therefore
    recognised by their wording: one that reads the same as before keeps its
    results, and one that was changed in any way starts again as a new,
    unprocessed sentence.

    A sentence is profiled when the writer's caret leaves it, which is when it
    goes from being typed to done. Each question about it is then sent on a
    thread of its own, all of them at once, and the text is answered without
    waiting for them. A model at an address of the learner's own is asked
    all the questions about a sentence in one request instead, as such a
    server may answer one request at a time. Going back into a sentence that has been profiled and
    leaving it unchanged does not profile it again, while changing it does.

    If a sentence is changed, or the caret goes back onto it, while questions
    about it are out, their answers are dropped when they arrive: the threads
    end by themselves and leave nothing behind but what the requests cost.
    Several text boxes may be checked in turn, each named by the `box` it
    is sent with: a box gives up only what was asked about its own
    sentences, and leaves what is out about those of the others alone.

    Once every question about a sentence is answered, its words can be rated
    as well: the model is asked again, with the answers it gave to go by, how
    right each word is where it stands. That is one more request, which is
    dropped in the same way if the sentence does not stay as it is. A word is
    taken as wrong only as far as the answers found the sentence wrong.

    A sentence can be corrected as well, if that is asked for, by a language
    model rather than the decision model: it is asked to write the sentence
    as it should be once the caret leaves it, alongside the questions, and
    its answer is kept and dropped as theirs are. The rating of the words
    then waits for the correction as well as for the answers, and the model
    rates them with it to go by; if it cannot be had, they are rated by the
    answers alone.

    An answer belongs to the question as it was asked and to the model that
    was asked. Other questions and another model are asked afresh, and going
    back to earlier ones brings back the answers they gave.
    """

    def __init__(
        self,
        speller: Speller,
        profiler: Profiler | None = None,
        on_profiled: OnProfiled | None = None,
        background: Background = in_a_thread,
        on_rated: OnRated | None = None,
        max_remembered: int = 10000,
        corrector: Corrector | None = None,
        on_corrected: OnCorrected | None = None,
    ) -> None:
        self._speller = speller
        self._profiler = profiler
        self._on_profiled = on_profiled
        self._on_rated = on_rated
        self._corrector = corrector
        self._on_corrected = on_corrected
        self._background = background
        self._max_remembered = max_remembered
        self._asked: OrderedDict[_Key, _Asked] = OrderedDict()
        # the questions that are out at the moment
        self._asking: dict[_Key, _Asked] = {}
        # how many requests have not come back yet, dropped ones included
        self._in_flight = 0
        # the requests that came back and have not been reported as usage yet
        self._unbilled: list[Profile] = []
        # requests are handled on several threads, and so are the questions
        self._lock = threading.Lock()

    def check(
        self,
        text: str,
        caret: int | None = None,
        model: Model | None = None,
        questions: Questions | None = None,
        rate_words: bool = False,
        correct_with: Model | None = None,
        into: str = "English",
        box: str = "",
    ) -> list[Sentence]:
        """Split `text` into sentences and fill in what is known about each.

        `caret` is where the writer's caret is in `text`, if known; the
        sentence it is on is treated as still being written. `model` is the
        model to profile them with; without one that can be asked, such as
        one on OpenRouter with no key, none are. `questions` are the
        questions to ask it, if not the usual ones; with no questions at
        all, nothing is profiled. With `rate_words`, the words of each sentence
        are rated once it has been profiled. With `correct_with`, the
        language model that writes each finished sentence as it should be,
        it is asked to alongside the questions, with what it wrote translated
        `into` the language the learner reads, and the words are rated with
        what it wrote. `box` names the text box the text is of: what is out
        about the sentences of another box is left to it, as the boxes of a
        page are checked in turn."""
        sentences = split_sentences(text, caret)
        if questions is None:
            questions = QUESTIONS
        if self._profiler and model:
            model = self._profiler.named(model)
        # A sentence is judged by the rules of the language studied, so what
        # was answered in one language is not taken to hold in another.
        language = (self._profiler.language if self._profiler else None) or ""
        asked_model = f"{model.url} {model.name} {language}" if model else ""
        can_ask = bool(self._profiler and model and model.problem() is None)
        # a model that names none is the corrector's usual one
        can_correct = bool(self._corrector and correct_with and correct_with.has_key)
        # what it is translated into is part of what is asked
        correcting_model = (
            f"{correct_with.url} {correct_with.name} {language} {into}"
            if correct_with
            else ""
        )
        # one at an address of the learner's own is asked all at once
        together = bool(model and not model.on_openrouter)
        # what to ask in each request
        to_ask: list[tuple[str, dict[str, _Question]]] = []
        # the sentences to rate the words of, each with what is known of it
        to_rate: list[
            tuple[str, str | None, list[dict[str, str]], float, _Key, _Asked]
        ] = []
        # the sentences to correct, each with where its correction is kept
        to_correct: list[tuple[str, _Key, _Asked]] = []
        asked_questions = json.dumps(questions, sort_keys=True)
        with self._lock:
            # the questions the text, as it is now, wants answered
            wanted: set[_Key] = set()
            for sentence in sentences:
                sentence.spelling = self._speller.check(sentence.text)
                correction_key = (sentence.text, correcting_model, _CORRECTION, "")
                corrected = self._asked.get(correction_key) if correct_with else None
                keys = {
                    name: (
                        sentence.text,
                        asked_model,
                        name,
                        json.dumps(question, sort_keys=True),
                    )
                    for name, question in questions.items()
                }
                # The words are rated by what the questions said, and by the
                # correction once there is one, so their rating belongs to
                # both: without one, they are rated by the questions alone.
                correction = corrected.correction if corrected else None
                rated_with = (
                    asked_questions
                    if correction is None
                    else f"{asked_questions}\0{correction}"
                )
                words_key = (sentence.text, asked_model, _WORDS, rated_with)
                if not sentence.complete:
                    self._being_written(sentence, keys, words_key)
                    if correct_with:
                        self._correction_being_written(sentence, correction_key)
                    continue
                if correct_with:
                    wanted.add(correction_key)
                    if corrected:
                        self._asked.move_to_end(correction_key)
                    elif can_correct and has_words(sentence.text):
                        corrected = self._asked[correction_key] = _Asked(box=box)
                        self._asking[correction_key] = corrected
                        to_correct.append((sentence.text, correction_key, corrected))
                    if corrected:
                        sentence.correction = corrected.correction
                        sentence.correction_translation = corrected.translation
                        sentence.correcting = corrected.state == "asking"
                        sentence.correction_error = corrected.error
                # the correction is out alongside the questions, and the words
                # wait for it as they wait for the answers
                waiting = bool(corrected and corrected.state == "asking")
                new: dict[str, _Question] = {}
                for name, key in keys.items():
                    wanted.add(key)
                    if key in self._asked:
                        self._asked.move_to_end(key)
                    elif can_ask:
                        asked = self._asked[key] = self._asking[key] = _Asked(box=box)
                        new[name] = (questions[name], key, asked)
                if together and new:
                    to_ask.append((sentence.text, new))
                else:
                    to_ask += [
                        (sentence.text, {name: one}) for name, one in new.items()
                    ]
                self._fill_in(sentence, keys)
                if not rate_words:
                    continue
                wanted.add(words_key)
                rated = self._asked.get(words_key)
                if rated:
                    self._asked.move_to_end(words_key)
                elif (
                    can_ask
                    and sentence.profile
                    and not waiting
                    and has_words(sentence.text)
                ):
                    rated = self._asked[words_key] = self._asking[words_key] = _Asked(
                        box=box
                    )
                    answers = sentence.profile.answers
                    to_rate.append(
                        (
                            sentence.text,
                            correction,
                            describe_assessment(questions, answers),
                            doubt_about(answers),
                            words_key,
                            rated,
                        )
                    )
                if rated:
                    sentence.words = rated.words or []
                    sentence.rating_words = rated.state == "asking"
                    sentence.profile_error = rated.error
                elif waiting and can_ask and sentence.profile:
                    sentence.rating_words = True
            self._drop_unwanted(wanted, box)
            self._forget_the_oldest()
            self._in_flight += len(to_ask) + len(to_rate) + len(to_correct)
        for sentence_text, correction_key, corrected in to_correct:
            assert correct_with
            self._background(
                partial(
                    self._correct,
                    sentence_text,
                    language,
                    correction_key,
                    corrected,
                    correct_with,
                    into,
                )
            )
        for sentence_text, new in to_ask:
            self._background(partial(self._ask, sentence_text, new, model or Model()))
        for sentence_text, correction, assessment, doubt, words_key, rated in to_rate:
            self._background(
                partial(
                    self._rate,
                    sentence_text,
                    correction,
                    assessment,
                    doubt,
                    words_key,
                    rated,
                    model or Model(),
                )
            )
        return sentences

    def spell(self, text: str, caret: int | None = None) -> list[Sentence]:
        """Split `text` into sentences and check their spelling alone. Nothing
        is profiled, and what is out or known about the text that `check` is
        given is left as it is, so that other text boxes can be checked
        alongside the one whose sentences are profiled."""
        sentences = split_sentences(text, caret)
        with self._lock:
            for sentence in sentences:
                sentence.spelling = self._speller.check(sentence.text)
        return sentences

    def study(self, language: str) -> None:
        """Go by `language`, given by its English name, from now on: it is
        the one whose spelling is checked, where the speller can be told,
        and the one sentences are judged by."""
        if isinstance(self._speller, StudySpeller):
            self._speller.language = language
        if self._profiler:
            self._profiler.language = language

    def billing(self) -> tuple[list[Profile], bool]:
        """The requests that have come back since this was last called, each
        with what it used, and whether any are still out. Requests whose
        answers were dropped are among them: they were paid for all the same."""
        with self._lock:
            unbilled, self._unbilled = self._unbilled, []
            return unbilled, self._in_flight > 0

    def _being_written(
        self, sentence: Sentence, keys: dict[str, _Key], words_key: _Key
    ) -> None:
        rated = self._asked.get(words_key)
        if rated and rated.state == "failed":
            del self._asked[words_key]
        elif rated and rated.words:
            sentence.words = rated.words
        answers = {}
        for name, key in keys.items():
            asked = self._asked.get(key)
            if asked is None:
                continue
            if asked.state == "failed":
                # The writer is back on a sentence a question failed for.
                # Leaving it again is a fresh chance to ask.
                del self._asked[key]
            elif asked.answer:
                answers[name] = asked.answer
        # The writer is back on a sentence that was profiled and has not
        # changed it so far, so what was found out about it still holds.
        if keys and len(answers) == len(keys):
            sentence.profile = Profile(answers)

    def _correction_being_written(self, sentence: Sentence, key: _Key) -> None:
        corrected = self._asked.get(key)
        if corrected and corrected.state == "failed":
            # leaving the sentence again is a fresh chance to ask
            del self._asked[key]
        elif corrected and corrected.correction:
            sentence.correction = corrected.correction
            sentence.correction_translation = corrected.translation

    def _fill_in(self, sentence: Sentence, keys: dict[str, _Key]) -> None:
        """Say where the profile of a finished sentence stands."""
        asked = {name: self._asked.get(key) for name, key in keys.items()}
        answers = {
            name: one.answer for name, one in asked.items() if one and one.answer
        }
        if keys and len(answers) == len(keys):
            sentence.profile = Profile(answers)
            sentence.processed = True
        elif any(one and one.state == "asking" for one in asked.values()):
            sentence.profiling = True
        else:
            errors = [one.error for one in asked.values() if one and one.error]
            sentence.profile_error = errors[0] if errors else None

    def _drop_unwanted(self, wanted: set[_Key], box: str) -> None:
        """Give up on the questions that are out about sentences of `box`
        which have since been changed or gone back to. Those about the
        sentences of other boxes are theirs to give up: each box is checked
        by itself, and a sentence it does not have is not one it changed."""
        for key in [
            key
            for key, asked in self._asking.items()
            if key not in wanted and asked.box == box
        ]:
            self._asking.pop(key).dropped = True
            del self._asked[key]

    def _forget_the_oldest(self) -> None:
        while len(self._asked) > self._max_remembered:
            key, asked = self._asked.popitem(last=False)
            if self._asking.pop(key, None):
                asked.dropped = True

    def _ask(
        self,
        sentence_text: str,
        new: dict[str, _Question],
        model: Model,
    ) -> None:
        """Ask questions about a sentence in one request and keep the
        answers, unless the sentence was changed or gone back to while
        waiting for them."""
        assert self._profiler
        profile, error = None, None
        try:
            profile = self._profiler.profile(
                sentence_text,
                model,
                {name: question for name, (question, _, _) in new.items()},
            )
        except ProfileError as failure:
            error = str(failure)
        finally:
            with self._lock:
                self._in_flight -= 1
                if profile:
                    self._unbilled.append(profile)
                for name, (_, key, asked) in new.items():
                    # the same question may have been asked afresh since
                    # this one was dropped
                    if self._asking.get(key) is asked:
                        del self._asking[key]
                    if not asked.dropped:
                        asked.state = "answered" if profile else "failed"
                        asked.answer = profile.answers.get(name) if profile else None
                        asked.error = error
                dropped = all(asked.dropped for _, _, asked in new.values())
        if self._on_profiled:
            self._on_profiled(sentence_text, profile, error, dropped)

    def _rate(
        self,
        sentence_text: str,
        correction: str | None,
        assessment: list[dict[str, str]],
        doubt: float,
        key: _Key,
        rated: _Asked,
        model: Model,
    ) -> None:
        """Have the words of a sentence rated and keep the ratings, unless
        the sentence was changed or gone back to while waiting for them.
        `doubt` is how much there is to doubt in the sentence as a whole."""
        assert self._profiler
        ratings, profile, error = None, None, None
        try:
            ratings, profile = self._profiler.rate_words(
                sentence_text, assessment, model, correction
            )
            ratings = weigh_ratings(ratings, doubt)
        except ProfileError as failure:
            error = str(failure)
        finally:
            with self._lock:
                self._in_flight -= 1
                if profile:
                    self._unbilled.append(profile)
                if self._asking.get(key) is rated:
                    del self._asking[key]
                if not rated.dropped:
                    rated.state = "answered" if ratings else "failed"
                    rated.words = ratings
                    rated.error = error
        if self._on_rated:
            self._on_rated(sentence_text, ratings, error, rated.dropped)

    def _correct(
        self,
        sentence_text: str,
        language: str,
        key: _Key,
        corrected: _Asked,
        model: Model,
        into: str,
    ) -> None:
        """Have a sentence written as it should be, and translated `into` the
        language the learner reads, and keep what was written, unless the
        sentence was changed or gone back to while waiting."""
        assert self._corrector
        correction, translation, used, error = None, None, None, None
        try:
            written, used = self._corrector(sentence_text, language, model, into)
            correction = written.sentence or None
            translation = written.translation or None
        except TranslationError as failure:
            error = str(failure)
        finally:
            with self._lock:
                self._in_flight -= 1
                if used:
                    self._unbilled.append(used)
                if self._asking.get(key) is corrected:
                    del self._asking[key]
                if not corrected.dropped:
                    corrected.state = "answered" if correction else "failed"
                    corrected.correction = correction
                    corrected.translation = translation
                    corrected.error = error
        if self._on_corrected:
            self._on_corrected(sentence_text, correction, error, corrected.dropped)
