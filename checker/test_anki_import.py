# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from anki_import import AnkiImporter, AnkiUnavailable, vocabulary_words
from intake import Intake
from test_intake import KEY, MODEL, FakeChat, FakeProfiler, savable
from vocabulary import Vocabularies, Vocabulary

NOTES = ["der Hund", "von Anfang an", "gern, gerne", "Claudio", "die Katze"]


class Anki:
    """Stands in for the deck-status server."""

    def __init__(self) -> None:
        self.notes = list(NOTES)
        self.there = True

    def __call__(self) -> list[str]:
        if not self.there:
            raise AnkiUnavailable("the deck-status server cannot be reached")
        return self.notes


@pytest.fixture
def anki() -> Anki:
    return Anki()


@pytest.fixture
def vocabulary() -> Vocabulary:
    return Vocabulary()


@pytest.fixture
def chat() -> FakeChat:
    chat = FakeChat()
    for word in ("Hund", "gern", "gerne", "Katze"):
        chat.judged(word, "reject", reason="for the test")
    return chat


@pytest.fixture
def importer(vocabulary: Vocabulary, chat: FakeChat, anki: Anki) -> AnkiImporter:
    profiler = FakeProfiler({"Claudio": "name", "gern": "adverb", "gerne": "adverb"})
    importer = AnkiImporter(Intake(vocabulary, profiler, chat), anki, batch=3)
    importer.configure(True, KEY, MODEL, None)
    return importer


def test_a_note_gives_its_word_without_the_article_or_sich() -> None:
    assert vocabulary_words("selbstverständlich") == ["selbstverständlich"]
    assert vocabulary_words("der Club") == ["Club"]
    assert vocabulary_words("Die Mutter") == ["Mutter"]
    assert vocabulary_words("sich freuen") == ["freuen"]


def test_a_note_gives_each_of_its_spellings_once() -> None:
    assert vocabulary_words("gern, gerne") == ["gern", "gerne"]
    assert vocabulary_words("der Teil, das Teil") == ["Teil"]


def test_a_note_gives_nothing_of_its_markup_brackets_or_closing_mark() -> None:
    assert vocabulary_words("circa, zirka (ca.)") == ["circa", "zirka"]
    assert vocabulary_words("<b>Hallo!</b>[sound:hallo.mp3]") == ["Hallo"]
    assert vocabulary_words("der&nbsp;Hund") == ["Hund"]


def test_an_expression_of_several_words_gives_nothing() -> None:
    assert vocabulary_words("von Anfang an") == []
    assert vocabulary_words("je...desto") == []
    assert vocabulary_words("an der Universität, an der Uni") == []
    # the single words of a note that also has an expression are kept
    assert vocabulary_words("meiste, die meisten") == ["meiste", "meisten"]


def test_a_look_takes_in_a_few_of_the_anki_words_the_vocabulary_lacks(
    importer: AnkiImporter, vocabulary: Vocabulary
) -> None:
    importer.look()

    status, _ = importer.status()
    assert vocabulary.not_taken(["Hund", "gern", "gerne", "Claudio", "Katze"]) == [
        "Claudio",
        "Katze",
    ]
    assert (status.state, status.remaining, status.taken) == ("waiting", 2, 3)


def test_looking_again_takes_in_the_rest_and_then_nothing(
    importer: AnkiImporter, chat: FakeChat
) -> None:
    importer.look()
    importer.look()
    asked = len(chat.bodies)

    importer.look()

    status, _ = importer.status()
    assert (status.state, status.remaining, status.taken) == ("waiting", 0, 5)
    assert len(chat.bodies) == asked


def test_a_word_added_to_anki_is_taken_in_by_the_next_look(
    importer: AnkiImporter, anki: Anki, chat: FakeChat, vocabulary: Vocabulary
) -> None:
    importer.look()
    importer.look()
    chat.judged("Maus", "reject")

    anki.notes.append("die Maus")
    importer.look()

    assert vocabulary.not_taken(["Maus"]) == []


def test_nothing_is_taken_in_while_anki_is_not_there(
    importer: AnkiImporter, anki: Anki, chat: FakeChat
) -> None:
    anki.there = False

    importer.look()

    status, _ = importer.status()
    assert (status.state, status.message) == (
        "unavailable",
        "the deck-status server cannot be reached",
    )
    assert chat.bodies == []


def test_nothing_is_taken_in_while_the_import_is_off_or_has_no_key(
    vocabulary: Vocabulary, chat: FakeChat, anki: Anki
) -> None:
    importer = AnkiImporter(Intake(vocabulary, FakeProfiler(), chat), anki)

    importer.look()
    without_key, _ = importer.status()
    importer.configure(False, KEY, MODEL, None)
    importer.look()
    switched_off, _ = importer.status()

    assert (without_key.state, switched_off.state) == ("no-key", "off")
    assert vocabulary.not_taken(["Hund"]) == ["Hund"]


def test_a_key_that_was_handed_over_is_kept_when_none_comes_with_the_next_word(
    importer: AnkiImporter,
) -> None:
    importer.configure(True, "", MODEL, None)

    importer.look()

    assert importer.status()[0].state == "waiting"


def test_words_that_all_fail_are_tried_again_and_the_reason_is_given(
    vocabulary: Vocabulary, chat: FakeChat, anki: Anki
) -> None:
    importer = AnkiImporter(Intake(vocabulary, FakeProfiler(), chat), anki, batch=2)
    # no model is named, so no new word can be judged
    importer.configure(True, KEY, None, None)

    importer.look()
    importer.look()

    status, _ = importer.status()
    assert status.state == "unavailable"
    assert "no model was named" in status.message
    assert (status.taken, status.failed) == (0, 0)


def test_a_word_that_fails_is_sent_again_after_the_others_and_then_taken_in(
    vocabulary: Vocabulary, chat: FakeChat, anki: Anki
) -> None:
    del chat.verdicts["Hund"]
    chat.judged("Hund", "form", "Hundd")
    chat.rescues["Hund"] = savable("", "")
    profiler = FakeProfiler({"Claudio": "name"})
    importer = AnkiImporter(Intake(vocabulary, profiler, chat), anki, batch=2)
    importer.configure(True, KEY, MODEL, None)

    importer.look()
    after_failing = vocabulary.not_taken(["Hund", "gern"])
    # whatever was wrong is over
    chat.judged("Hund", "reject")
    importer.look()
    taken_before_hund = vocabulary.not_taken(["gerne", "Claudio", "Hund"])
    importer.look()

    status, _ = importer.status()
    assert after_failing == ["Hund"]
    assert taken_before_hund == ["Hund"]
    assert vocabulary.not_taken(["Hund", "Katze"]) == []
    assert (status.failed, status.remaining, status.taken) == (0, 0, 5)


def test_a_word_that_keeps_failing_is_given_up_on_after_a_few_tries(
    vocabulary: Vocabulary, chat: FakeChat, anki: Anki
) -> None:
    del chat.verdicts["Hund"]
    chat.judged("Hund", "form", "Hundd")
    chat.rescues["Hund"] = savable("", "")
    profiler = FakeProfiler({"Claudio": "name"})
    importer = AnkiImporter(Intake(vocabulary, profiler, chat), anki, batch=2)
    importer.configure(True, KEY, MODEL, None)

    for _ in range(8):
        importer.look()

    status, _ = importer.status()
    assert (
        len([given for given in chat.asked_for("verdict") if given["word"] == "Hund"])
        == 3
    )
    assert (status.failed, status.remaining) == (1, 1)
    assert status.message.startswith("Hund: it was judged a form of Hundd")


def test_the_requests_an_import_made_are_reported_once(
    importer: AnkiImporter,
) -> None:
    importer.look()

    _, used = importer.status()
    _, used_again = importer.status()

    # three words sorted by the decision model, and each judged
    assert len(used) == 6
    assert used_again == []


def test_each_word_is_counted_as_soon_as_it_is_taken_in(
    importer: AnkiImporter, chat: FakeChat
) -> None:
    seen = []

    class Watching(FakeChat):
        def __call__(self, body: dict[str, Any], api_key: str) -> dict[str, Any]:
            seen.append(importer.status()[0])
            return chat(body, api_key)

    importer._intake._chat = Watching()  # noqa: SLF001
    importer._intake._workers = 1  # noqa: SLF001

    importer.look()

    # while the second and the third word were judged, others were done
    assert [(status.state, status.taken) for status in seen] == [
        ("importing", 0),
        ("importing", 1),
        ("importing", 2),
    ]
    assert [status.remaining for status in seen] == [5, 4, 3]


def test_an_import_switched_on_again_no_longer_says_it_is_off(
    importer: AnkiImporter,
) -> None:
    importer.configure(False, KEY, MODEL, None)
    switched_off = importer.status()[0].state

    importer.configure(True, KEY, MODEL, None)

    assert (switched_off, importer.status()[0].state) == ("off", "waiting")


def test_a_look_says_whether_there_is_more_to_take_in_right_away(
    importer: AnkiImporter, anki: Anki
) -> None:
    first = importer.look()
    second = importer.look()
    with_nothing_left = importer.look()
    anki.there = False

    assert (first, second, with_nothing_left) == (True, False, False)
    assert importer.look() is False


def test_the_anki_words_go_into_the_vocabulary_of_their_own_language(
    tmp_path: Path, chat: FakeChat, anki: Anki
) -> None:
    vocabularies = Vocabularies(tmp_path)
    intake = Intake(vocabularies, FakeProfiler({"Claudio": "name"}), chat)
    importer = AnkiImporter(intake, anki, batch=5)
    importer.configure(True, KEY, MODEL, None, "German")
    # another language is being studied, and has been all along
    intake.language = "Arabic"

    importer.look()

    assert vocabularies.of("German").not_taken(["Hund", "Katze", "gern"]) == []
    assert "a vocabulary of German" in chat.bodies[0]["messages"][0]["content"]
    assert not vocabularies.has("Arabic")
