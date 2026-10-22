# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import time

import pytest
from intake import Intake
from models import Model
from test_intake import CHAT, FakeChat, FakeProfiler
from vocabulary import Vocabulary
from word_translations import MAX_FAILURES_IN_A_ROW, TranslationStatus, WordTranslator


@pytest.fixture
def vocabulary() -> Vocabulary:
    return Vocabulary()


@pytest.fixture
def chat() -> FakeChat:
    return FakeChat()


@pytest.fixture
def translator(vocabulary: Vocabulary, chat: FakeChat) -> WordTranslator:
    return WordTranslator(Intake(vocabulary, FakeProfiler(), chat), workers=2)


def finished(translator: WordTranslator, into: str) -> TranslationStatus:
    """What the translating says once it is no longer at it."""
    for _ in range(200):
        status, _ = translator.status("German", into)
        if status.state != "translating":
            return status
        time.sleep(0.01)
    raise AssertionError("the translating did not finish")


def test_every_word_without_translations_in_a_language_is_translated_into_it(
    translator: WordTranslator, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    for lemma in ("Hund", "Katze", "Maus"):
        vocabulary.save("noun", lemma, {}, [], [lemma.lower()], "English")
        chat.translations[lemma] = [[f"{lemma.lower()} in italiano"]]
    vocabulary.save("noun", "Pferd", {}, [], ["cavallo"], "Italian")

    translator.start("German", "Italian", CHAT)
    status = finished(translator, "Italian")

    assert (status.state, status.remaining, status.translated) == ("idle", 0, 3)
    hund = vocabulary.entry("noun", "Hund")
    assert hund is not None
    # those it had in English stay as they were
    assert hund.variants[0].translations == {
        "English": ["hund"],
        "Italian": ["hund in italiano"],
    }


def test_the_translating_stops_when_words_fail_one_after_another(
    translator: WordTranslator, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    for number in range(MAX_FAILURES_IN_A_ROW + 2):
        vocabulary.save("noun", f"Wort{number}", {}, [], ["word"], "English")
        # an answer that leaves the one variant out
        chat.translations[f"Wort{number}"] = []

    translator.start("German", "Italian", CHAT)
    status = finished(translator, "Italian")

    assert status.state == "unavailable"
    assert status.failed >= MAX_FAILURES_IN_A_ROW
    assert "not as asked" in status.message
    assert status.remaining == MAX_FAILURES_IN_A_ROW + 2


def test_nothing_is_translated_without_a_key(
    translator: WordTranslator, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    vocabulary.save("noun", "Hund", {}, [], ["dog"], "English")

    translator.start("German", "Italian", Model("some/model"))
    status, _ = translator.status("German", "Italian")

    assert (status.state, status.remaining) == ("no-key", 1)
    assert chat.bodies == []
