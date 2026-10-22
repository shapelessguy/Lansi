# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The stored words translated into the language the learner reads
translations in, when they have no translations there yet: a word is
stored with its translations in the language of the time, and a learner
who then reads translations in another has them translated, word by word,
on a thread of its own, as `Intake.translate` does it, once asked to."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass

from intake import WORKERS, Intake, IntakeError
from models import Model
from profiling import Profile, ProfileError

# Words that fail one after another before the translating stops, as then
# the model or the key is at fault rather than the words.
MAX_FAILURES_IN_A_ROW = 3
# the requests to the models that are kept for whoever asks next, at most
MAX_UNBILLED = 200


@dataclass
class TranslationStatus:
    # What the translating is doing:
    #   "idle": nothing is being translated
    #   "translating": words are being translated
    #   "no-key": it was asked to, but there is no key to ask a model with
    #   "unavailable": a model could not be asked; `message` says why
    state: str = "idle"
    # how many words have no translations in the language asked after
    remaining: int = 0
    # how many words have been translated, and given up on, since it started
    translated: int = 0
    failed: int = 0
    message: str = ""


class WordTranslator:
    """Translates the words of one vocabulary into one language at a time,
    those that have no translations there, until none is left."""

    def __init__(self, intake: Intake, workers: int = WORKERS) -> None:
        self._intake = intake
        self._workers = workers
        # what is being translated: the vocabulary's language and the one
        # the meanings are put into, and with which model
        self._running: tuple[str, str] | None = None
        self._model = Model()
        self._status = TranslationStatus()
        self._unbilled: list[Profile] = []
        self._lock = threading.Lock()

    def start(self, language: str, into: str, model: Model) -> None:
        """Translate into `into` every word of the vocabulary of `language`
        that has no translations there. Translating into another language
        than before stops that once the words at hand are done."""
        with self._lock:
            self._model = model.or_keyed(self._model.key)
            if not self._model.has_key:
                self._status = TranslationStatus(state="no-key")
                return
            if self._running == (language, into):
                return
            first = self._running is None
            self._running = (language, into)
            self._status = TranslationStatus(state="translating")
        if first:
            threading.Thread(
                target=self._translate, name="word-translations", daemon=True
            ).start()

    def keyed(self, model: Model) -> None:
        """Ask the models with the key of `model` from now on, if it has one."""
        with self._lock:
            if model.has_key:
                self._model = model.or_keyed(self._model.key)

    def status(
        self, language: str, into: str
    ) -> tuple[TranslationStatus, list[Profile]]:
        """What the translating of the words of `language` into `into` is
        doing, and the requests to the models it has made since this was
        last asked."""
        remaining = len(self._intake.vocabulary_of(language).lacking_translations(into))
        with self._lock:
            used, self._unbilled = self._unbilled, []
            status = TranslationStatus(**asdict(self._status))
            if self._running not in (None, (language, into)):
                # what is said of another language is not of this one
                status = TranslationStatus()
        status.remaining = remaining
        return status, used

    def _translate(self) -> None:
        failures_in_a_row = 0
        given_up: set[int] = set()
        with ThreadPoolExecutor(self._workers) as pool:
            while True:
                with self._lock:
                    assert self._running is not None
                    language, into = self._running
                    model = self._model
                vocabulary = self._intake.vocabulary_of(language)
                batch = [
                    entry_id
                    for entry_id in vocabulary.lacking_translations(into)
                    if entry_id not in given_up
                ][: self._workers]
                if not batch and self._finish(language, into, "idle", ""):
                    return
                if not batch:
                    # another language was asked for as this one was done
                    given_up.clear()
                    continue
                results = list(
                    pool.map(
                        lambda entry_id: self._one(language, entry_id, into, model),
                        batch,
                    )
                )
                for entry_id, problem in zip(batch, results, strict=True):
                    if problem is None:
                        failures_in_a_row = 0
                        continue
                    given_up.add(entry_id)
                    failures_in_a_row += 1
                    with self._lock:
                        self._status.failed += 1
                        self._status.message = problem
                if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
                    with self._lock:
                        message = self._status.message
                    if self._finish(language, into, "unavailable", message):
                        return
                    failures_in_a_row = 0

    def _one(self, language: str, entry_id: int, into: str, model: Model) -> str | None:
        """Translate one word, and say what went wrong, if
        anything did."""
        vocabulary = self._intake.vocabulary_of(language)
        entry = vocabulary.get(entry_id)
        if entry is None:
            return None
        used: list[Profile] = []
        try:
            self._intake.translate(language, entry, into, model, used)
        except (IntakeError, ProfileError) as error:
            return f"{entry.lemma}: {error}"
        finally:
            with self._lock:
                # kept short, should nobody be asking
                self._unbilled = (self._unbilled + used)[-MAX_UNBILLED:]
        with self._lock:
            self._status.translated += 1
        return None

    def _finish(self, language: str, into: str, state: str, message: str) -> bool:
        """Stop translating into `into`, unless another language was asked
        for in the meantime, and say whether it stopped."""
        with self._lock:
            if self._running != (language, into):
                return False
            self._running = None
            self._status.state = state
            self._status.message = message
            return True
