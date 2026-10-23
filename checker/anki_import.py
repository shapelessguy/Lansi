# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Brings the words of a user's Anki collection into the vocabulary of the
language they are of.

Each user may link an Anki account of their own, whose collection the
deck-status server keeps a copy of; the checker alone reaches that server.
Every few seconds it is asked for the words that have a card in review, and
those the vocabulary was never given are taken into it, a few at a time. The
key and the model this needs are those of the chat, which hands them over
and can switch the import off.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from intake import Intake, Outcome, Word
from languages import DEFAULT_LANGUAGE, language_of
from models import Model
from profiling import Profile

DECK_STATUS_URL = "http://127.0.0.1:8090"
# how often the Anki words are looked through
LOOK_EVERY_SECS = 10.0
# How many words are taken into the vocabulary in one go. They are worked on
# several at a time, and with this many a slow one holds up few of the others.
BATCH = 40
TIMEOUT_SECS = 10
# how many requests to the models are remembered for whoever keeps count
MAX_UNBILLED = 2000
# How often a word that could not be taken in is tried, in all, before it is
# left alone until the server is started again.
MAX_TRIES = 3

# One row per note that has a card in review or being relearned, with the
# field the note is sorted by, which is the word.
WORDS_SQL = (
    "select n.sfld from cards c join notes n on n.id = c.nid"
    " where c.type in (2, 3){decks} group by n.id order by n.id"
)

_MARKUP = re.compile(r"\[sound:[^\]]*\]|<[^>]*>")
_IN_BRACKETS = re.compile(r"\([^)]*\)")
# a single word, which may have an apostrophe or a hyphen inside it
_SINGLE_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


# One row per note that has a card in review or being relearned, with the
# earliest day one of those cards is due and the longest interval, for the
# words the chat lists.
KNOWN_WORDS_SQL = (
    "select n.id, n.mid, n.sfld, n.flds,"
    " min(case when c.odue > 0 then c.odue else c.due end), max(c.ivl)"
    " from cards c join notes n on n.id = c.nid"
    " where c.type in (2, 3){decks} group by n.id"
)


class AnkiUnavailable(Exception):
    """The Anki words could not be fetched. The message says why."""


class AnkiRefused(AnkiUnavailable):
    """The deck-status server refused what was asked, such as a login to an
    Anki account with the wrong password. The message says why."""


# how long logging in to an Anki account may take, and a sync asked for
LINK_TIMEOUT_SECS = 60
SYNC_TIMEOUT_SECS = 130
# no more of what the deck-status server says of a refusal is passed on
MAX_REASON_LENGTH = 300
# far more than a picture or a sound of a card needs
MAX_MEDIA_BYTES = 50_000_000


class AnkiLink:
    """The Anki account a user may link, whose collection the deck-status
    server at `url` keeps a copy of."""

    def __init__(self, user: str, url: str = DECK_STATUS_URL) -> None:
        self._base = f"{url}/users/{urllib.parse.quote(user, safe='')}"

    def state(self) -> dict[str, Any]:
        """Whether an account is linked, with when its collection was last
        synced, in Unix seconds, and why the last sync failed, if it did."""
        reply = self._ask("")
        status = reply.get("status") or {}
        return {
            "linked": bool(reply.get("linked")),
            "last_sync": status.get("last_sync"),
            "error": status.get("last_sync_error"),
        }

    def link(self, username: str, password: str) -> dict[str, Any]:
        """Log in to the Anki account of `username`, whose collection is
        kept from now on, and return the state. The password is not kept.
        Raises AnkiRefused if the login is refused."""
        self._ask(
            "/link",
            {"username": username, "password": password},
            timeout=LINK_TIMEOUT_SECS,
        )
        return self.state()

    def unlink(self) -> dict[str, Any]:
        """Forget the Anki account, and the copy of its collection."""
        self._ask("/link", method="DELETE")
        return self.state()

    def decks(self) -> list[dict[str, Any]]:
        """The decks of the collection, parents before their children, each
        with its id, its full name ("Deutsch::Verben") and its counts.
        Raises AnkiUnavailable, or AnkiRefused before the first sync."""
        decks = self._ask("/decks").get("decks", [])
        return [deck for deck in decks if isinstance(deck, dict)]

    def next_card(self, deck_id: int) -> dict[str, Any]:
        """The next card to study of the deck `deck_id` and its subdecks,
        rendered, with what is left of them today, as the deck-status server
        shows it, and which makes it the current deck of the collection.
        Raises AnkiUnavailable, or AnkiRefused for a deck there is not."""
        reply = self._ask("/review/next", {"deck_id": deck_id})
        return reply if isinstance(reply, dict) else {}

    def answer_card(
        self, deck_id: int, card_id: int, rating: int, millis: int
    ) -> dict[str, Any]:
        """Answer the card `card_id` of the deck `deck_id`, 1 to 4 for
        Again, Hard, Good and Easy, after `millis` of looking at it, as a
        review in Anki that is synced soon, and return whether it was
        `answered` with the next card. Raises AnkiUnavailable."""
        body = {
            "deck_id": deck_id,
            "card_id": card_id,
            "rating": rating,
            "millis": millis,
        }
        reply = self._ask("/review/answer", body)
        return reply if isinstance(reply, dict) else {}

    def sync(self) -> None:
        """Sync the collection now, as before it is studied. Raises
        AnkiUnavailable, or AnkiRefused if the sync failed."""
        self._ask("/sync", {}, timeout=SYNC_TIMEOUT_SECS)

    def media(self, name: str) -> tuple[bytes, str]:
        """A file of the media folder of the collection, such as a picture
        or a sound of a card, with its type. Raises AnkiUnavailable, or
        AnkiRefused if there is no such file."""
        request = urllib.request.Request(
            f"{self._base}/media/{urllib.parse.quote(name, safe='')}"
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECS) as response:
                kind = response.headers.get_content_type()
                data = response.read(MAX_MEDIA_BYTES + 1)
        except urllib.error.HTTPError as error:
            raise AnkiRefused(
                f"there is no file {name} in Anki ({error.code})"
            ) from None
        except OSError:
            raise AnkiUnavailable("the deck-status server cannot be reached") from None
        if len(data) > MAX_MEDIA_BYTES:
            raise AnkiRefused(f"{name} is too large to be shown")
        return data, kind

    @staticmethod
    def _without_decks(skipped: list[int]) -> str:
        """What leaves the cards of the `skipped` decks out of a query."""
        if not skipped:
            return ""
        listed = ", ".join(str(int(deck_id)) for deck_id in skipped)
        # a card moved into a filtered deck still belongs to its own one
        return f" and not (c.did in ({listed}) or c.odid in ({listed}))"

    def notes(self, skipped: list[int] | None = None) -> list[str]:
        """What each note with a card in review holds as its word, leaving
        out the cards of the `skipped` decks. Raises AnkiUnavailable."""
        sql = WORDS_SQL.format(decks=self._without_decks(skipped or []))
        rows = self._ask("/sql", {"sql": sql})
        try:
            return [str(row[0]) for row in rows]
        except (IndexError, TypeError):
            raise AnkiUnavailable(
                "the deck-status server gave rows of another shape"
            ) from None

    def known_words(self, skipped: list[int] | None = None) -> dict[str, Any]:
        """The notes with a card in review, leaving out the cards of the
        `skipped` decks, as rows of KNOWN_WORDS_SQL, with the names of the
        fields of each of their notetypes and the timing of the day the due
        days count from. The chat makes its list of words of them. Raises
        AnkiUnavailable."""
        sql = KNOWN_WORDS_SQL.format(decks=self._without_decks(skipped or []))
        rows = self._ask("/sql", {"sql": sql})
        timing = self._ask("/api/schedTimingToday")
        try:
            notetypes = list(dict.fromkeys(int(row[1]) for row in rows))
        except (TypeError, ValueError, IndexError):
            raise AnkiUnavailable(
                "the deck-status server gave rows of another shape"
            ) from None
        field_names = {
            str(ntid): self._ask("/api/getFieldNames", {"ntid": ntid}).get("vals", [])
            for ntid in notetypes
        }
        return {"rows": rows, "timing": timing, "field_names": field_names}

    def _ask(
        self,
        path: str,
        body: object | None = None,
        method: str | None = None,
        timeout: float = TIMEOUT_SECS,
    ) -> Any:
        """What the deck-status server answers at `path` of the user's
        collection, posted `body` if there is one. Raises AnkiUnavailable,
        or AnkiRefused with the reason the server gives."""
        request = urllib.request.Request(
            f"{self._base}{path}",
            data=None if body is None else json.dumps(body).encode(),
            method=method or ("GET" if body is None else "POST"),
            headers={} if body is None else {"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            reason = error.read().decode(errors="replace").strip()
            raise AnkiRefused(
                reason[:MAX_REASON_LENGTH]
                or f"the deck-status server refused the request ({error.code})"
            ) from None
        except (OSError, ValueError):
            raise AnkiUnavailable("the deck-status server cannot be reached") from None


def vocabulary_words(note: str, language: str = DEFAULT_LANGUAGE) -> list[str]:
    """The words an Anki note of `language` gives the vocabulary. A note may
    hold several spellings, separated by commas, an abbreviation in brackets,
    and before a word one of the `note_prefixes` of the language, such as an
    article, or joined to it one of them that is elided, such as "l'".
    Expressions of several words give nothing: the vocabulary takes words
    one by one."""
    prefixes = language_of(language).note_prefixes
    text = _MARKUP.sub("", note).replace("&nbsp;", " ").replace("&amp;", "&")
    words: dict[str, None] = {}
    for part in _IN_BRACKETS.sub("", text).split(","):
        word = part.strip()
        first, _, rest = word.partition(" ")
        if rest and first.lower() in prefixes:
            word = rest.strip()
        # an article that is elided is written joined to the word: "l'amico"
        elided = next(
            (
                prefix
                for prefix in prefixes
                if prefix.endswith("'")
                and word.replace("’", "'").lower().startswith(prefix)
                and len(word) > len(prefix)
            ),
            None,
        )
        if elided:
            word = word[len(elided) :]
        word = word.rstrip(".!?")
        if _SINGLE_WORD.fullmatch(word):
            words[word] = None
    return list(words)


@dataclass
class ImportStatus:
    # What the import is doing:
    #   "off": it is switched off
    #   "no-key": it waits for an OpenRouter key
    #   "unavailable": Anki or a model could not be asked; `message` says why
    #   "importing": words are being taken in
    #   "waiting": it waits for the next look
    state: str = "waiting"
    # how many Anki words the vocabulary still lacks, once that is known
    remaining: int | None = None
    # how many words have been taken in since the server started
    taken: int = 0
    # how many were given up on, with what was said about the last that failed
    failed: int = 0
    message: str = ""


class AnkiImporter:
    def __init__(
        self,
        intake: Intake,
        fetch_notes: Callable[[], list[str]],
        api_key: str = "",
        batch: int = BATCH,
        on_taken: Callable[[list[Outcome]], None] | None = None,
    ) -> None:
        self._intake = intake
        self._fetch_notes = fetch_notes
        self._batch = batch
        self._on_taken = on_taken
        self._enabled = True
        # the language the Anki words are of
        self._language = DEFAULT_LANGUAGE
        self._model = Model(key=api_key)
        self._decision_model = Model(key=api_key)
        self._status = ImportStatus()
        # the requests to the models that nobody has been told of yet
        self._unbilled: list[Profile] = []
        # how often each word that could not be taken in has been tried
        self._tries: dict[str, int] = {}
        self._lock = threading.Lock()

    def configure(
        self,
        enabled: bool,
        model: Model,
        decision_model: Model,
        language: str | None = None,
    ) -> None:
        """Switch the import on or off, and say which models it is to use.
        One on OpenRouter without a key keeps the key there was.
        `language` is the one the Anki words are of, if it is not the one
        that was given before."""
        with self._lock:
            self._language = language or self._language
            self._enabled = enabled
            self._model = model.or_keyed(self._model.key)
            self._decision_model = decision_model.or_keyed(self._decision_model.key)
            if not enabled:
                self._status.state = "off"
            elif self._status.state == "off":
                # until the next look says more
                self._status.state = "waiting"

    @property
    def language(self) -> str:
        """The language the Anki words are of."""
        with self._lock:
            return self._language

    def status(self) -> tuple[ImportStatus, list[Profile]]:
        """What the import is doing, and the requests to the models it has
        made since this was last asked."""
        with self._lock:
            used, self._unbilled = self._unbilled, []
            return ImportStatus(**asdict(self._status)), used

    def watch(self, every_secs: float = LOOK_EVERY_SECS) -> None:
        """Look again and again, on a thread of its own. The first look
        waits as long as the others, for the chat to say whether the import
        is wanted at all."""

        def keep_looking() -> None:
            # never set, so this only waits
            pause = threading.Event()
            while not pause.wait(every_secs):
                # while there are words to take in, there is no waiting
                while self.look():
                    pass

        threading.Thread(target=keep_looking, name="anki-import", daemon=True).start()

    def look(self) -> bool:
        """Look through the Anki words once, and take in some of those the
        vocabulary lacks. Returns whether it is worth looking again at once,
        as there are more to take in."""
        return self._look()

    def _look(self) -> bool:
        with self._lock:
            enabled = self._enabled
            model, decision_model = self._model, self._decision_model
        if not enabled:
            self._update(state="off")
            return False
        if not (model.has_key and decision_model.has_key):
            self._update(state="no-key")
            return False
        try:
            notes = self._fetch_notes()
        except AnkiUnavailable as error:
            self._update(state="unavailable", message=str(error))
            return False
        # The Anki words are of a language of their own, whichever one is
        # being studied at present, and go into the vocabulary of that one.
        with self._lock:
            language = self._language
        words = [word for note in notes for word in vocabulary_words(note, language)]
        new = self._intake.vocabulary_of(language).not_taken(words)
        # A word that failed is sent again, after those that were not tried.
        to_try = [word for word in new if self._tries.get(word, 0) < MAX_TRIES]
        batch = sorted(to_try, key=lambda word: self._tries.get(word, 0))
        batch = batch[: self._batch]
        if not batch:
            self._update(state="waiting", remaining=len(new))
            return False
        self._update(state="importing", remaining=len(new))
        outcomes, used = self._intake.take(
            [Word(word) for word in batch],
            model,
            decision_model,
            on_outcome=self._count,
            language=language,
        )
        with self._lock:
            # kept short, should nobody be asking
            self._unbilled = (self._unbilled + used)[-MAX_UNBILLED:]
        failures = [outcome for outcome in outcomes if outcome.status == "failed"]
        if len(failures) == len(outcomes) > 1:
            # Nothing can be taken in as things are, with this key or model,
            # so the same words are tried the next time.
            self._update(state="unavailable", message=failures[0].reason)
            return False
        for failure in failures:
            self._tries[failure.word] = self._tries.get(failure.word, 0) + 1
        with self._lock:
            self._status.failed = sum(
                tries >= MAX_TRIES for tries in self._tries.values()
            )
            if failures:
                last = failures[-1]
                self._status.message = f"{last.word}: {last.reason}"
        self._update(state="waiting")
        if self._on_taken:
            self._on_taken(outcomes)
        # a word that failed is not sent again before the next pause
        return len(to_try) > len(batch)

    def _count(self, outcome: Outcome) -> None:
        """Count a word as taken in as soon as it is, for whoever follows
        the import to see it move."""
        if outcome.status == "failed":
            return
        with self._lock:
            self._status.taken += 1
            if self._status.remaining:
                self._status.remaining -= 1

    def _update(
        self, state: str, remaining: int | None = None, message: str | None = None
    ) -> None:
        with self._lock:
            self._status.state = state
            if remaining is not None:
                self._status.remaining = remaining
            if message is not None:
                self._status.message = message
