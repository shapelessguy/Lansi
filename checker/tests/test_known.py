# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from known import Known, members_of, pick
from vocabulary import Listed


def word(
    word_id: int,
    lemma: str,
    category: str = "noun",
    used: int = 0,
    seen: int = 0,
    by_user: float | None = None,
    by_assistant: float | None = None,
    created_at: str = "2026-10-01 10:00:00",
) -> Listed:
    times = [time for time in (by_user, by_assistant) if time is not None]
    return Listed(
        word_id,
        category,
        lemma,
        created_at,
        1,
        used,
        seen,
        min(times, default=None),
        max(times, default=None),
        by_user,
        by_assistant,
    )


def lemmas(words: Sequence[Listed | Known]) -> list[str]:
    return [each.lemma for each in words]


HUND = word(1, "Hund", used=3, by_user=30.0, by_assistant=10.0)
KATZE = word(2, "Katze", seen=5, by_assistant=40.0)
GEHEN = word(3, "gehen", "verb", used=1, seen=1, by_user=20.0, by_assistant=50.0)
APFEL = word(4, "Apfel", created_at="2026-10-05 10:00:00")
WORDS = [HUND, KATZE, GEHEN, APFEL]


def test_words_are_picked_most_recently_used_first_with_the_never_used_last() -> None:
    assert lemmas(pick(WORDS)) == ["gehen", "Katze", "Hund", "Apfel"]


def test_words_are_picked_least_recently_used_first_when_reversed() -> None:
    assert lemmas(pick(WORDS, reverse=True)) == ["Apfel", "Hund", "Katze", "gehen"]


def test_words_are_picked_by_when_the_learner_or_a_model_last_used_them() -> None:
    by_user = pick(WORDS, order="last_used_by_user")
    by_assistant = pick(WORDS, order="last_used_by_assistant")

    assert lemmas(by_user) == ["Hund", "gehen", "Apfel", "Katze"]
    assert lemmas(by_assistant) == ["gehen", "Katze", "Hund", "Apfel"]


def test_words_used_as_often_are_picked_in_the_order_of_the_alphabet() -> None:
    assert lemmas(pick(WORDS, order="most_used")) == ["Katze", "Hund", "gehen", "Apfel"]
    assert lemmas(pick(WORDS, order="most_used_by_user")) == [
        "Hund",
        "gehen",
        "Apfel",
        "Katze",
    ]


def test_words_are_picked_alphabetically_without_regard_to_capitals() -> None:
    assert lemmas(pick(WORDS, order="alphabetical")) == [
        "Apfel",
        "gehen",
        "Hund",
        "Katze",
    ]


def test_only_the_words_of_the_categories_named_are_picked() -> None:
    assert lemmas(pick(WORDS, categories={"verb"})) == ["gehen"]


def test_only_the_entries_named_are_picked_when_some_are() -> None:
    assert lemmas(pick(WORDS, only={1, 4})) == ["Hund", "Apfel"]


def test_no_more_words_are_picked_than_the_limit() -> None:
    assert lemmas(pick(WORDS, order="added", limit=2)) == ["Apfel", "gehen"]


def a_set(**parts: Any) -> dict[str, Any]:
    return {"id": "s", "name": "S", "rules": {}, "otherwise": {}, **parts}


def test_a_set_gives_the_words_each_rule_lets_in_with_those_put_in_by_hand() -> None:
    kept = a_set(
        rules={"verb": {"included": False}},
        otherwise={"minUsed": 1},
        added=[3],
        removed=[1],
    )

    assert lemmas(members_of(kept, WORDS)) == ["gehen"]


def test_a_set_cuts_each_category_down_to_its_limit_by_its_order() -> None:
    kept = a_set(otherwise={"limit": 1, "orderBy": "seen", "mostFirst": True})

    assert lemmas(members_of(kept, WORDS)) == ["Katze", "gehen"]


def test_a_set_kept_with_one_rule_gives_no_words_of_the_categories_it_did_not_name() -> (
    None
):
    kept = {"id": "s", "name": "S", "rule": {"categories": ["verb"]}}

    assert lemmas(members_of(kept, WORDS)) == ["gehen"]


def test_only_the_words_of_a_set_are_picked_when_one_is_given() -> None:
    kept = a_set(otherwise={"minSeen": 1})

    assert lemmas(pick(WORDS, word_set=kept, order="alphabetical")) == [
        "gehen",
        "Katze",
    ]


def test_words_spelt_alike_are_picked_as_one_word_with_all_their_categories() -> None:
    article = word(5, "der", "article", used=6, by_user=30.0)
    pronoun = word(6, "der", "pronoun", used=6, by_user=30.0)

    (picked,) = pick([article, pronoun], categories={"article"})

    # in the order the categories are shown in
    assert (picked.lemma, picked.categories, picked.ids) == (
        "der",
        ["pronoun", "article"],
        [6, 5],
    )
    assert (picked.used, picked.last_used_by_user) == (6, 30.0)


def test_words_spelt_alike_but_for_capitals_are_picked_as_one_word() -> None:
    noun = word(7, "Essen", "noun")
    verb = word(8, "essen", "verb")

    assert [each.categories for each in pick([verb, noun], only={8})] == [
        ["noun", "verb"]
    ]
