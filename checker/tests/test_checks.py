# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from checks import EXERCISES, REST, CheckCache, Key


def key(sentence: str, name: str = "polite") -> Key:
    return (sentence, "model German", name, "{}")


@pytest.fixture
def cache(tmp_path: Path) -> CheckCache:
    return CheckCache(tmp_path / "checks.db", {EXERCISES: 3, REST: 2})


def test_a_check_is_given_back_under_the_key_it_was_kept_under(
    cache: CheckCache,
) -> None:
    cache.put(key("Ich bin."), REST, {"choice": "yes"})
    assert cache.get(key("Ich bin.")) == {"choice": "yes"}


def test_nothing_is_given_back_for_a_key_never_kept(cache: CheckCache) -> None:
    cache.put(key("Ich bin."), REST, 1)
    assert cache.get(key("Ich bin.", "formal")) is None
    assert cache.get(("Ich bin.", "other model", "polite", "{}")) is None


def test_checks_are_kept_between_runs(tmp_path: Path) -> None:
    CheckCache(tmp_path / "checks.db").put(key("Ich bin."), EXERCISES, [1, 2])
    assert CheckCache(tmp_path / "checks.db").get(key("Ich bin.")) == [1, 2]


def test_a_source_forgets_the_sentence_used_longest_ago_when_beyond_its_limit(
    cache: CheckCache,
) -> None:
    for sentence in ["Eins.", "Zwei.", "Drei."]:
        cache.put(key(sentence), REST, sentence)
    assert cache.count(REST) == 2
    assert cache.get(key("Eins.")) is None
    assert cache.get(key("Drei.")) == "Drei."


def test_a_sentence_given_back_counts_as_used_lately(cache: CheckCache) -> None:
    cache.put(key("Eins."), REST, 1)
    cache.put(key("Zwei."), REST, 2)
    cache.get(key("Eins."))
    cache.put(key("Drei."), REST, 3)
    assert cache.get(key("Eins.")) == 1
    assert cache.get(key("Zwei.")) is None


def test_every_check_of_a_sentence_is_forgotten_with_it(cache: CheckCache) -> None:
    cache.put(key("Eins.", "polite"), REST, 1)
    cache.put(key("Eins.", "formal"), REST, 1)
    cache.put(key("Zwei."), REST, 2)
    cache.put(key("Drei."), REST, 3)
    assert cache.get(key("Eins.", "polite")) is None
    assert cache.get(key("Eins.", "formal")) is None


def test_the_checks_of_one_sentence_count_as_one_towards_the_limit(
    cache: CheckCache,
) -> None:
    for name in ["polite", "formal", "short"]:
        cache.put(key("Eins.", name), REST, name)
    cache.put(key("Zwei."), REST, 2)
    assert cache.count(REST) == 2
    assert cache.get(key("Eins.", "polite")) == "polite"


def test_each_source_keeps_its_own_number_of_sentences(cache: CheckCache) -> None:
    for sentence in ["Eins.", "Zwei.", "Drei.", "Vier."]:
        cache.put(key(sentence), EXERCISES, sentence)
    cache.put(key("Fünf."), REST, 5)
    assert cache.count(EXERCISES) == 3
    assert cache.count(REST) == 1
    assert cache.get(key("Zwei.")) == "Zwei."


def test_a_source_without_a_limit_is_kept_as_the_rest(cache: CheckCache) -> None:
    cache.put(key("Eins."), "books", 1)
    assert cache.count(REST) == 1


def test_checks_can_be_kept_from_several_threads_at_once(cache: CheckCache) -> None:
    threads = [
        threading.Thread(target=cache.put, args=(key("Eins.", str(n)), EXERCISES, n))
        for n in range(20)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert [cache.get(key("Eins.", str(n))) for n in range(20)] == list(range(20))
