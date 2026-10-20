# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The words the learner knows, picked out of a vocabulary as they are
asked for: those of some categories, of a set, or that have a card in
review in Anki, put in order by one of the ways in ORDERS and cut down to
as many as are wanted.

The vocabulary stores a word once for each category it is of, as its forms
and what is known of it differ by category; but whoever uses a word goes by
its spelling alone, so the entries spelt alike, whatever their capitals,
are given as one word with all their categories.

Which words are of a set is worked out here as the app works it out
(chat-ui/src/lib/sets.ts), from the rule of each category and the words
put in or taken out by hand, so that a set means the same words to both.

The checker gives them at /vocabulary/known, and the tutor has a tool that
asks for them; both ask with an `Asked`, and `known_words` answers it.
"""

from __future__ import annotations

import random
import unicodedata
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any

from categories import CATEGORIES
from vocabulary import Listed, Vocabulary, fold

# what the words of a category of a set are cut down to, if its rule says
# nothing, as the app has it
DEFAULT_SET_LIMIT = 100
_SET_ORDERS = ("lastUsed", "used", "seen", "total")


def _never_first(value: float | None) -> float:
    """A time to put words in order by, with never before all others."""
    return float("-inf") if value is None else value


@dataclass
class Known:
    """A word the learner knows: the stored entries spelt alike, as one."""

    # the dictionary form, as the entry of the first of the categories spells it
    lemma: str
    # the categories it is of, in the order they are shown in, and the
    # numbers of its entries in the same order
    categories: list[str]
    ids: list[int]
    # when it was first stored, in UTC
    created_at: str
    # what is known of its uses, as Listed has it
    used: int = 0
    seen: int = 0
    first_used: float | None = None
    last_used: float | None = None
    last_used_by_user: float | None = None
    last_used_by_assistant: float | None = None


def _as_one(entries: list[Listed]) -> Known:
    """Entries spelt alike, which share their uses, as one word."""
    ordered = sorted(entries, key=lambda entry: CATEGORIES.index(entry.category))
    first = ordered[0]
    return Known(
        first.lemma,
        [entry.category for entry in ordered],
        [entry.id for entry in ordered],
        min(entry.created_at for entry in ordered),
        first.used,
        first.seen,
        first.first_used,
        first.last_used,
        first.last_used_by_user,
        first.last_used_by_assistant,
    )


def _alphabetical(word: Listed | Known) -> str:
    """A dictionary form as words are put in the order of the alphabet by:
    without capitals or accents, so that "Ärger" comes with "arg"."""
    decomposed = unicodedata.normalize("NFKD", word.lemma.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


@dataclass(frozen=True)
class Order:
    # what a word is put in order by
    key: Callable[[Known], Any]
    # whether the words with the most of it come first, unless asked otherwise
    most_first: bool = True


# The ways words can be put in order, by the name a request gives them. A
# word never used was used before all others, so it comes last when the most
# recently used come first, and first when the least recently used do.
ORDERS: dict[str, Order] = {
    # by when it was last used, by either the learner or a model
    "last_used": Order(lambda word: _never_first(word.last_used)),
    "last_used_by_user": Order(lambda word: _never_first(word.last_used_by_user)),
    "last_used_by_assistant": Order(
        lambda word: _never_first(word.last_used_by_assistant)
    ),
    # by when it was first used, the words met most lately first
    "first_used": Order(lambda word: _never_first(word.first_used)),
    # by how often it was used, by either and by each
    "most_used": Order(lambda word: word.used + word.seen),
    "most_used_by_user": Order(lambda word: word.used),
    "most_used_by_assistant": Order(lambda word: word.seen),
    # by when it was stored, the newest first
    "added": Order(lambda word: word.created_at),
    # in the order of the alphabet, from A
    "alphabetical": Order(_alphabetical, most_first=False),
    # in no order at all, which is different every time
    "random": Order(lambda word: random.random()),
}


def _count(value: object, otherwise: int | None) -> int | None:
    """A whole number of a rule as it was kept, or `otherwise` for one that
    is none."""
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        return otherwise
    return int(value)


@dataclass(frozen=True)
class SetRule:
    """What picks the words of one category for a set, as the app keeps it."""

    included: bool = True
    min_used: int = 0
    max_used: int | None = None
    min_seen: int = 0
    max_seen: int | None = None
    # 0 for as many as there are
    limit: int = DEFAULT_SET_LIMIT
    order_by: str = "lastUsed"
    most_first: bool = True

    @classmethod
    def read(cls, kept: object, included: bool = True) -> SetRule:
        """The rule as the app kept it, with what is missing or wrong in it
        as it would be in a new one."""
        rule = kept if isinstance(kept, dict) else {}
        order_by = rule.get("orderBy")
        return cls(
            included=rule["included"]
            if isinstance(rule.get("included"), bool)
            else included,
            min_used=_count(rule.get("minUsed"), 0) or 0,
            max_used=_count(rule.get("maxUsed"), None),
            min_seen=_count(rule.get("minSeen"), 0) or 0,
            max_seen=_count(rule.get("maxSeen"), None),
            limit=_count(rule.get("limit"), DEFAULT_SET_LIMIT) or 0,
            order_by=order_by if order_by in _SET_ORDERS else "lastUsed",
            most_first=rule["mostFirst"]
            if isinstance(rule.get("mostFirst"), bool)
            else True,
        )

    def lets_in(self, word: Listed) -> bool:
        return (
            self.included
            and word.used >= self.min_used
            and (self.max_used is None or word.used <= self.max_used)
            and word.seen >= self.min_seen
            and (self.max_seen is None or word.seen <= self.max_seen)
        )

    def amount(self, word: Listed) -> float:
        """How much a word has of what this rule puts words in order by."""
        return {
            "lastUsed": word.last_used or 0,
            "used": word.used,
            "seen": word.seen,
            "total": word.used + word.seen,
        }[self.order_by]


def members_of(kept: dict[str, Any], words: list[Listed]) -> list[Listed]:
    """The `words` that are of the set the app `kept`, in the order they are
    given. Each category gives the words its rule lets in, without the ones
    taken out by hand, cut down to as many as it may give; the words put in
    by hand are of the set whatever the rules say. A set kept when it had a
    single rule for the categories it named has that rule for each of them,
    and gives no words of the others."""
    rules = kept.get("rules")
    one = kept.get("rule")
    if isinstance(rules, dict):
        by_category = {name: SetRule.read(rule) for name, rule in rules.items()}
        otherwise = SetRule.read(kept.get("otherwise"))
    elif isinstance(one, dict):
        named = one.get("categories")
        named = (
            [name for name in named if isinstance(name, str)]
            if isinstance(named, list)
            else []
        )
        # the one rule had no most unless it was given one
        rule = SetRule.read({"limit": 0, **one})
        by_category = dict.fromkeys(named, rule)
        otherwise = SetRule.read({"limit": 0, **one}, included=not named)
    else:
        by_category, otherwise = {}, SetRule.read(kept.get("otherwise"))

    def ids(key: str) -> set[int]:
        listed = kept.get(key)
        return (
            {each for each in listed if type(each) is int}
            if isinstance(listed, list)
            else set()
        )

    removed = ids("removed")
    picked: dict[str, list[Listed]] = {}
    for word in words:
        rule = by_category.get(word.category, otherwise)
        if rule.lets_in(word) and word.id not in removed:
            picked.setdefault(word.category, []).append(word)
    members = ids("added")
    for category, its in picked.items():
        rule = by_category.get(category, otherwise)
        if rule.limit and len(its) > rule.limit:
            sign = -1 if rule.most_first else 1
            its = sorted(
                its, key=lambda word: (sign * rule.amount(word), _alphabetical(word))
            )[: rule.limit]
        members.update(word.id for word in its)
    return [word for word in words if word.id in members]


def pick(
    words: list[Listed],
    categories: Collection[str] = (),
    word_set: dict[str, Any] | None = None,
    only: Collection[int] | None = None,
    order: str = "last_used",
    reverse: bool = False,
    limit: int = 0,
) -> list[Known]:
    """The `words`, with those spelt alike as one, of which an entry is of
    the `categories`, or of any if none are named, is of `word_set` if one
    is given and is among the entries `only` names if that is given; put in
    the `order` named, the other way round if `reverse`, and cut down to
    `limit` if that is not 0. Words that are alike by the order are put in
    the order of the alphabet."""
    members = members_of(word_set, words) if word_set is not None else words
    wanted = {
        fold(word.lemma)
        for word in members
        if (not categories or word.category in categories)
        and (only is None or word.id in only)
    }
    spelt: dict[str, list[Listed]] = {}
    for word in words:
        if fold(word.lemma) in wanted:
            spelt.setdefault(fold(word.lemma), []).append(word)
    picked = [_as_one(entries) for entries in spelt.values()]
    by = ORDERS[order]
    picked.sort(key=_alphabetical)
    # sorting is stable, so the alphabet decides between words that are alike
    picked.sort(key=by.key, reverse=by.most_first != reverse)
    return picked[:limit] if limit else picked


@dataclass(frozen=True)
class Asked:
    """Which of the words the learner knows are wanted. Raises ValueError
    for a category or an order there is not, or a limit below 0."""

    # the words of these categories, or of all if none are named
    categories: frozenset[str] = frozenset()
    # the words of the set with this id or name, whatever its case, if one is named
    set: str = ""
    # the words that have a card in review in the chosen decks of Anki alone
    anki_only: bool = False
    # put in the order of ORDERS of this name, the other way round if `reverse`
    order: str = "last_used"
    reverse: bool = False
    # as many as this at most; 0 for all
    limit: int = 0

    def __post_init__(self) -> None:
        unknown = sorted(self.categories - set(CATEGORIES))
        if unknown:
            raise ValueError(f"there is no category {', '.join(unknown)}")
        if self.order not in ORDERS:
            raise ValueError(f"sorted_by must be one of {', '.join(ORDERS)}")
        if self.limit < 0:
            raise ValueError("limit must be a whole number")


def known_words(
    vocabulary: Vocabulary | None,
    asked: Asked,
    anki_words: Callable[[], list[str]] | None = None,
) -> tuple[list[Known], int]:
    """The words of `vocabulary` that are `asked` for, with how many there
    were before they were cut down to the limit. `anki_words` gives the
    words of the notes with a card in review, in the language of the
    vocabulary, and is None where there is no Anki. Raises LookupError for
    a set there is not, or for the Anki words where there is no Anki; and
    whatever `anki_words` raises."""
    if asked.anki_only and anki_words is None:
        raise LookupError("there is no Anki here")
    if vocabulary is None:
        if asked.set:
            raise LookupError("no such set")
        return [], 0
    word_set = None
    if asked.set:
        wanted = asked.set.casefold()
        word_set = next(
            (
                kept
                for kept in vocabulary.sets()
                if asked.set == kept.get("id")
                or wanted == str(kept.get("name", "")).strip().casefold()
            ),
            None,
        )
        if word_set is None:
            raise LookupError("no such set")
    only = None
    if asked.anki_only and anki_words is not None:
        only = vocabulary.having_forms(anki_words())
    picked = pick(
        vocabulary.listing(),
        asked.categories,
        word_set,
        only,
        asked.order,
        asked.reverse,
    )
    return (picked[: asked.limit] if asked.limit else picked), len(picked)
