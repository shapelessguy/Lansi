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
from spelling import Speller

# Runs a job without making the caller wait for it.
Background = Callable[[Callable[[], None]], None]
# Told when a question about a sentence has come back: the sentence, the
# answer or else why there is none, and whether the answer was dropped
# because the sentence was changed or gone back to in the meantime.
OnProfiled = Callable[[str, "Profile | None", "str | None", bool], None]
# Told when the words of a sentence have been rated: the sentence, the
# ratings or else why there are none, and whether they were dropped.
OnRated = Callable[[str, "list[WordRating] | None", "str | None", bool], None]
# A sentence's wording, the model asked, and a question's name and content.
_Key = tuple[str, str, str, str]
# The name, in a key, of the rating of a sentence's words. No question can
# have it, as it is not a name that can be sent.
_WORDS = "\0words"


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
    error: str | None = None
    # The sentence was changed or gone back to while the question was out.
    # Its answer is not kept when it comes back.
    dropped: bool = False


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
    waiting for them. A model on this machine is asked all the questions
    about a sentence in one request instead, as it answers one request at a
    time, and it needs no key. Going back into a sentence that has been profiled and
    leaving it unchanged does not profile it again, while changing it does.

    If a sentence is changed, or the caret goes back onto it, while questions
    about it are out, their answers are dropped when they arrive: the threads
    end by themselves and leave nothing behind but what the requests cost.

    Once every question about a sentence is answered, its words can be rated
    as well: the model is asked again, with the answers it gave to go by, how
    right each word is where it stands. That is one more request, which is
    dropped in the same way if the sentence does not stay as it is. A word is
    taken as wrong only as far as the answers found the sentence wrong.

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
    ) -> None:
        self._speller = speller
        self._profiler = profiler
        self._on_profiled = on_profiled
        self._on_rated = on_rated
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
        api_key: str | None = None,
        model: str | None = None,
        questions: Questions | None = None,
        rate_words: bool = False,
    ) -> list[Sentence]:
        """Split `text` into sentences and fill in what is known about each.

        `caret` is where the writer's caret is in `text`, if known; the
        sentence it is on is treated as still being written. `api_key` is the
        OpenRouter key to profile sentences with; without one, none are,
        unless there is a model on this machine to ask.
        `model` and `questions` are the model to profile them with and the
        questions to ask it, if not the usual ones; with no questions at all,
        nothing is profiled. With `rate_words`, the words of each sentence
        are rated once it has been profiled."""
        sentences = split_sentences(text, caret)
        if questions is None:
            questions = QUESTIONS
        # a model on this machine is asked in place of the one named
        local = self._profiler.local_model() if self._profiler else None
        asked_model = f"local:{local}" if local else model or ""
        can_ask = bool(self._profiler and (local or api_key))
        # what to ask in each request
        to_ask: list[tuple[str, dict[str, _Question]]] = []
        # the sentences to rate the words of, each with what is known of it
        to_rate: list[tuple[str, list[dict[str, str]], float, _Key, _Asked]] = []
        asked_questions = json.dumps(questions, sort_keys=True)
        with self._lock:
            # the questions the text, as it is now, wants answered
            wanted: set[_Key] = set()
            for sentence in sentences:
                sentence.spelling = self._speller.check(sentence.text)
                keys = {
                    name: (
                        sentence.text,
                        asked_model,
                        name,
                        json.dumps(question, sort_keys=True),
                    )
                    for name, question in questions.items()
                }
                # the words are rated by what the questions said, so their
                # rating belongs to the questions as well
                words_key = (sentence.text, asked_model, _WORDS, asked_questions)
                if not sentence.complete:
                    self._being_written(sentence, keys, words_key)
                    continue
                new: dict[str, _Question] = {}
                for name, key in keys.items():
                    wanted.add(key)
                    if key in self._asked:
                        self._asked.move_to_end(key)
                    elif can_ask:
                        asked = self._asked[key] = self._asking[key] = _Asked()
                        new[name] = (questions[name], key, asked)
                if local and new:
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
                elif can_ask and sentence.profile and has_words(sentence.text):
                    rated = self._asked[words_key] = self._asking[words_key] = _Asked()
                    answers = sentence.profile.answers
                    to_rate.append(
                        (
                            sentence.text,
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
            self._drop_unwanted(wanted)
            self._forget_the_oldest()
            self._in_flight += len(to_ask) + len(to_rate)
        for sentence_text, new in to_ask:
            self._background(
                partial(self._ask, sentence_text, new, api_key or "", model)
            )
        for sentence_text, assessment, doubt, words_key, rated in to_rate:
            self._background(
                partial(
                    self._rate,
                    sentence_text,
                    assessment,
                    doubt,
                    words_key,
                    rated,
                    api_key or "",
                    model,
                )
            )
        return sentences

    def local_model(self) -> str | None:
        """The model on this machine that sentences are profiled by at
        present, if they are."""
        return self._profiler.local_model() if self._profiler else None

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

    def _drop_unwanted(self, wanted: set[_Key]) -> None:
        """Give up on the questions that are out about sentences which have
        since been changed or gone back to."""
        for key in [key for key in self._asking if key not in wanted]:
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
        api_key: str,
        model: str | None,
    ) -> None:
        """Ask questions about a sentence in one request and keep the
        answers, unless the sentence was changed or gone back to while
        waiting for them."""
        assert self._profiler
        profile, error = None, None
        try:
            profile = self._profiler.profile(
                sentence_text,
                api_key,
                model,
                {name: question for name, (question, _, _) in new.items()},
            )
        except ProfileError as failure:
            error = str(failure)
        finally:
            with self._lock:
                self._in_flight -= 1
                # the model on this machine is not paid for
                if profile and not profile.local:
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
        assessment: list[dict[str, str]],
        doubt: float,
        key: _Key,
        rated: _Asked,
        api_key: str,
        model: str | None,
    ) -> None:
        """Have the words of a sentence rated and keep the ratings, unless
        the sentence was changed or gone back to while waiting for them.
        `doubt` is how much there is to doubt in the sentence as a whole."""
        assert self._profiler
        ratings, profile, error = None, None, None
        try:
            ratings, profile = self._profiler.rate_words(
                sentence_text, assessment, api_key, model
            )
            ratings = weigh_ratings(ratings, doubt)
        except ProfileError as failure:
            error = str(failure)
        finally:
            with self._lock:
                self._in_flight -= 1
                if profile and not profile.local:
                    self._unbilled.append(profile)
                if self._asking.get(key) is rated:
                    del self._asking[key]
                if not rated.dropped:
                    rated.state = "answered" if ratings else "failed"
                    rated.words = ratings
                    rated.error = error
        if self._on_rated:
            self._on_rated(sentence_text, ratings, error, rated.dropped)
