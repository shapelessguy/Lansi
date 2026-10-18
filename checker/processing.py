# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Processes what a user has written and been written: the messages of the
chats, and what the learner and the models wrote in the exercises of
practice once each exercise is over.

Processing a message, or a text of an exercise, means two things. Every word of it is taken into the
vocabulary of the language the chat is in, so that new words are added to
it. And every word that is, or now is, in the vocabulary has a use recorded
against it, with who wrote it and when. A message is processed once, and
again if it is changed.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable

from intake import Intake, Outcome, Word
from models import Model
from sentences import split_sentences
from storage import Unprocessed, UserStore
from vocabulary import fold

# how often to look for something to process
LOOK_EVERY_SECS = 10.0
# How long a message has to have been left alone before it is processed. A
# reply is kept many times while it arrives, and is not to be processed
# until it is whole.
SETTLE_SECS = 8.0
# How often a message some of whose words could not be taken in is tried, in
# all, before it is processed without them.
MAX_TRIES = 3

# a word, which may have an apostrophe or a hyphen inside it
_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")
# the marks of Markdown, which a reply or a story is written in
_MARKUP = re.compile(r"[#*_`>~]+")


def words_of(text: str) -> list[Word]:
    """The words of a text, each with the sentence it is in."""
    words = []
    for sentence in split_sentences(_MARKUP.sub("", text)):
        for word in _WORD.findall(sentence.text):
            words.append(Word(word, sentence.text))
    return words


def words_in(before: str, selection: str, after: str) -> list[Word]:
    """The words of a `selection` out of a text, each with the sentence it
    is in. `before` is the text up to the selection and `after` the text
    from its end, so that a sentence the selection has only part of is
    given whole. A word the selection has only part of is one of its words."""
    text = before + selection + after
    start, end = len(before), len(before) + len(selection)
    words = []
    for sentence in split_sentences(text):
        if sentence.end <= start or sentence.start >= end:
            continue
        for word in _WORD.finditer(sentence.text):
            if (
                sentence.start + word.end() > start
                and sentence.start + word.start() < end
            ):
                words.append(Word(word.group(), sentence.text))
    return words


class Processor:
    def __init__(
        self,
        store: UserStore,
        intake: Intake,
        now: Callable[[], float] = time.time,
        settle_secs: float = SETTLE_SECS,
        on_processed: Callable[[Unprocessed, list[Outcome]], None] | None = None,
    ) -> None:
        self._store = store
        self._intake = intake
        self._now = now
        self._settle_secs = settle_secs
        self._on_processed = on_processed
        self._model = Model()
        self._decision_model = Model()
        # how often each thing that could not be processed whole was tried
        self._tries: dict[tuple[str, str, int, float], int] = {}
        self._lock = threading.Lock()

    def configure(self, model: Model, decision_model: Model) -> None:
        """Say which models new words are looked into with. One on
        OpenRouter without a key keeps the key there was."""
        with self._lock:
            self._model = model.or_keyed(self._model.key)
            self._decision_model = decision_model.or_keyed(self._decision_model.key)

    def watch(self, every_secs: float = LOOK_EVERY_SECS) -> None:
        """Look again and again, on a thread of its own."""

        def keep_looking() -> None:
            # never set, so this only waits
            pause = threading.Event()
            while not pause.wait(every_secs):
                self.look()

        threading.Thread(target=keep_looking, name="processing", daemon=True).start()

    def look(self) -> int:
        """Process what has been left alone long enough and is not processed
        yet, and return how many things were. Nothing is done while a model
        on OpenRouter has no key, as a new word cannot be looked into
        without one."""
        with self._lock:
            model, decision_model = self._model, self._decision_model
        if not (model.has_key and decision_model.has_key):
            return 0
        done = 0
        for item in self._store.unprocessed(self._now() - self._settle_secs):
            done += self._process(item, model, decision_model)
        return done

    def _process(
        self,
        item: Unprocessed,
        model: Model,
        decision_model: Model,
    ) -> bool:
        language = item.language or self._intake.language
        outcomes, _ = self._intake.take(
            words_of(item.content), model, decision_model, language=language
        )
        key = (item.kind, item.source_id, item.position, item.changed_at)
        if any(outcome.status == "failed" for outcome in outcomes):
            self._tries[key] = self._tries.get(key, 0) + 1
            if self._tries[key] < MAX_TRIES:
                # the words that failed are tried again with the next look
                return False
        self._tries.pop(key, None)
        self._intake.vocabulary_of(language).record_uses(
            item.kind,
            item.source_id,
            item.position,
            item.role,
            item.changed_at,
            [
                (outcome.entry.id, fold(outcome.word))
                for outcome in outcomes
                if outcome.entry is not None
            ],
        )
        processed = self._store.mark_processed(item, self._now())
        if processed and self._on_processed:
            self._on_processed(item, outcomes)
        return processed
