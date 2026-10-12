# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Checks a text that is sent again and again while it is being typed."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import Literal

from profiling import Profile, ProfileError, Profiler
from sentences import Sentence, split_sentences
from spelling import Speller, SpellingIssue

# Runs a job without making the caller wait for it.
Background = Callable[[Callable[[], None]], None]
# Told when a sentence's profile is ready, or why it could not be made.
OnProfiled = Callable[[str, "Profile | None", "str | None"], None]


@dataclass
class _Checked:
    """What is known about a sentence, whatever its place in the text."""

    spelling: list[SpellingIssue]
    # Where the sentence's profile stands: not asked for yet, being made,
    # made, or failed.
    state: Literal["new", "profiling", "profiled", "failed"] = "new"
    profile: Profile | None = None
    profile_error: str | None = None


class LiveChecker:
    """Remembers what it found out about each sentence.

    The text arrives whole each time, and any sentence in it may have been
    edited since the last time, not only the last one. Sentences are therefore
    recognised by their wording: one that reads the same as before keeps its
    results, and one that was changed in any way starts again as a new,
    unprocessed sentence.

    A sentence is profiled when the writer's caret leaves it, which is when it
    goes from being typed to done. That happens once for each wording: going
    back into a sentence and leaving it unchanged does not profile it again,
    while changing it does.
    """

    def __init__(
        self,
        speller: Speller,
        profiler: Profiler | None = None,
        on_profiled: OnProfiled | None = None,
        background: Background | None = None,
        max_remembered: int = 2000,
    ) -> None:
        self._speller = speller
        self._profiler = profiler
        self._on_profiled = on_profiled
        self._background = background or ThreadPoolExecutor(max_workers=4).submit
        self._max_remembered = max_remembered
        self._remembered: OrderedDict[str, _Checked] = OrderedDict()
        # requests are handled on several threads, and so are profiles
        self._lock = threading.Lock()

    def check(
        self,
        text: str,
        caret: int | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> list[Sentence]:
        """Split `text` into sentences and fill in what is known about each.

        `caret` is where the writer's caret is in `text`, if known; the
        sentence it is on is treated as still being written. `api_key` is the
        OpenRouter key to profile sentences with; without one, none are.
        `model` is the model to profile them with, if not the usual one."""
        sentences = split_sentences(text, caret)
        to_profile = []
        with self._lock:
            for sentence in sentences:
                if not sentence.complete:
                    self._being_written(sentence)
                    continue
                checked = self._remember(sentence)
                if checked.state == "new" and self._profiler and api_key:
                    checked.state = "profiling"
                    to_profile.append((sentence.text, checked))
                sentence.spelling = checked.spelling
                sentence.profile = checked.profile
                sentence.profile_error = checked.profile_error
                sentence.profiling = checked.state == "profiling"
                sentence.processed = checked.state == "profiled"
        for sentence_text, checked in to_profile:
            self._background(
                partial(self._profile, sentence_text, checked, api_key or "", model)
            )
        return sentences

    def _being_written(self, sentence: Sentence) -> None:
        # it changes with every key press, so there is no point keeping it
        sentence.spelling = self._speller.check(sentence.text)
        # The writer is back on a sentence whose profile failed. Leaving it
        # again is a fresh chance to make one.
        checked = self._remembered.get(sentence.text)
        if checked and checked.state == "failed":
            checked.state = "new"
            checked.profile_error = None

    def _remember(self, sentence: Sentence) -> _Checked:
        checked = self._remembered.get(sentence.text)
        if checked is None:
            checked = _Checked(self._speller.check(sentence.text))
            self._remembered[sentence.text] = checked
            if len(self._remembered) > self._max_remembered:
                self._remembered.popitem(last=False)
        else:
            self._remembered.move_to_end(sentence.text)
        return checked

    def _profile(
        self,
        sentence_text: str,
        checked: _Checked,
        api_key: str,
        model: str | None,
    ) -> None:
        assert self._profiler
        profile, error = None, None
        try:
            profile = self._profiler.profile(sentence_text, api_key, model)
        except ProfileError as failure:
            error = str(failure)
        with self._lock:
            checked.profile = profile
            checked.profile_error = error
            checked.state = "profiled" if profile else "failed"
        if self._on_profiled:
            self._on_profiled(sentence_text, profile, error)
