# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import io
import threading
import wave
from pathlib import Path
from typing import Any

import pytest
from speaking import (
    BookSentence,
    Speaker,
    SpeechError,
    playable,
    sentences_between,
    sentences_of_message,
)
from storage import UserStore

KEY = "sk-test"
BOOK = "book-1"
BLOCKS = [
    {"text": "Kapitel 1", "size": 2},
    {"text": "Der Hund schläft. Die Katze nicht. Danach?", "size": 1},
    {"text": "Ende.", "size": 1},
]


class FakeVoice:
    """Answers in place of a speech model, with samples that say which
    sentence they are of."""

    def __init__(self, fails_on: str = "") -> None:
        self.fails_on = fails_on
        self.bodies: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def __call__(self, body: dict[str, Any], api_key: str) -> tuple[bytes, str, str]:
        assert api_key == KEY
        with self._lock:
            self.bodies.append(body)
            number = len(self.bodies)
        if self.fails_on and self.fails_on in body["input"]:
            raise SpeechError("no credit")
        return body["input"].encode(), "audio/pcm;rate=16000", f"gen-{number}"

    def read(self) -> list[str]:
        return [body["input"] for body in self.bodies]


@pytest.fixture
def store(tmp_path: Path) -> UserStore:
    return UserStore(tmp_path)


def sentences(*places: int) -> list[BookSentence]:
    return sentences_between(BLOCKS, *places)


def test_the_sentences_of_a_selection_are_those_it_has_all_or_part_of() -> None:
    # from the middle of "schläft" to the middle of "Katze"
    found = sentences(1, 10, 1, 24)

    assert found == [
        BookSentence("1.0", 1, 0, 17, "Der Hund schläft."),
        BookSentence("1.1", 1, 18, 34, "Die Katze nicht."),
    ]


def test_the_sentences_of_a_selection_over_paragraphs_are_from_each_of_them() -> None:
    found = sentences(0, 0, 2, 3)

    assert [sentence.id for sentence in found] == ["0.0", "1.0", "1.1", "1.2", "2.0"]


def test_a_selection_that_ends_where_a_sentence_starts_has_none_of_it() -> None:
    assert [sentence.id for sentence in sentences(1, 0, 1, 18)] == ["1.0"]
    assert sentences(7, 0, 9, 3) == []


def test_bare_samples_are_made_a_file_players_can_open() -> None:
    audio, kind = playable(b"\x01\x00\x02\x00", "audio/pcm;rate=16000")

    with wave.open(io.BytesIO(audio)) as opened:
        assert (opened.getframerate(), opened.getnframes()) == (16000, 2)
    assert kind == "audio/wav"
    assert playable(b"ID3", "audio/mpeg") == (b"ID3", "audio/mpeg")


def test_the_audio_of_each_sentence_is_made_once_and_kept(store: UserStore) -> None:
    voice = FakeVoice()
    speaker = Speaker(store, voice, workers=1)
    wanted = sentences(1, 0, 1, 24)

    reading = speaker.start(BOOK, wanted)
    made = speaker.make(reading, BOOK, wanted, KEY, "some/tts", "Kore", "Slowly.")

    assert [(one["status"], one["generation"]) for one in made] == [
        ("made", "gen-1"),
        ("made", "gen-2"),
    ]
    assert voice.bodies[0] == {
        "model": "some/tts",
        "input": "Der Hund schläft.",
        "voice": "Kore",
        "response_format": "pcm",
        "instructions": "Slowly.",
    }
    assert speaker.kept(BOOK, sentences(1, 0, 1, 99), "some/tts", "Kore") == [
        True,
        True,
        False,
    ]
    audio, kind = speaker.audio(BOOK, "1.1")
    assert kind == "audio/wav" and "Die Katze nicht.".encode() in audio


def test_audio_is_not_taken_as_kept_for_another_voice_or_another_wording(
    store: UserStore,
) -> None:
    speaker = Speaker(store, FakeVoice(), workers=1)
    wanted = sentences(2, 0, 2, 5)
    speaker.make(speaker.start(BOOK, wanted), BOOK, wanted, KEY, "some/tts", "Kore")
    reworded = [BookSentence("2.0", 2, 0, 6, "Schluss.")]

    assert speaker.kept(BOOK, wanted, "some/tts", "Kore") == [True]
    assert speaker.kept(BOOK, wanted, "some/tts", "Puck") == [False]
    assert speaker.kept(BOOK, wanted, "other/tts", "Kore") == [False]
    assert speaker.kept(BOOK, reworded, "some/tts", "Kore") == [False]


def test_the_sentences_from_where_the_listener_is_are_made_first(
    store: UserStore,
) -> None:
    voice = FakeVoice()
    speaker = Speaker(store, voice, workers=1)
    wanted = sentences(0, 0, 2, 5)
    reading = speaker.start(BOOK, wanted)

    # the listener has skipped to the fourth of the five sentences
    speaker.listen_at(reading, 3)
    speaker.make(reading, BOOK, wanted, KEY, "some/tts", "Kore")

    assert voice.read() == [
        "Danach?",
        "Ende.",
        "Die Katze nicht.",
        "Der Hund schläft.",
        "Kapitel 1",
    ]


def test_a_sentence_that_cannot_be_read_fails_by_itself_with_the_reason(
    store: UserStore,
) -> None:
    speaker = Speaker(store, FakeVoice(fails_on="Katze"), workers=1)
    wanted = sentences(1, 0, 1, 24)

    made = speaker.make(speaker.start(BOOK, wanted), BOOK, wanted, KEY, "m", "v")

    assert [(one["status"], one["reason"]) for one in made] == [
        ("made", ""),
        ("failed", "no credit"),
    ]
    with pytest.raises(SpeechError, match="no credit"):
        speaker.audio(BOOK, "1.1")


def test_a_reading_that_is_stopped_leaves_the_rest_unread(store: UserStore) -> None:
    voice = FakeVoice()
    speaker = Speaker(store, voice, workers=1)
    wanted = sentences(1, 0, 1, 24)
    reading = speaker.start(BOOK, wanted)

    speaker.stop(reading)
    made = speaker.make(reading, BOOK, wanted, KEY, "m", "v")

    assert [one["status"] for one in made] == ["stopped", "stopped"]
    assert voice.bodies == []
    with pytest.raises(SpeechError, match="no audio"):
        speaker.audio(BOOK, "1.0")


def test_audio_that_is_being_made_is_waited_for(store: UserStore) -> None:
    speaker = Speaker(store, FakeVoice(), workers=1)
    wanted = sentences(2, 0, 2, 5)
    reading = speaker.start(BOOK, wanted)

    with pytest.raises(SpeechError, match="not made yet"):
        speaker.audio(BOOK, "2.0", wait_secs=0.01)

    threading.Timer(
        0.05, lambda: speaker.make(reading, BOOK, wanted, KEY, "m", "v")
    ).start()

    assert speaker.audio(BOOK, "2.0", wait_secs=5)[1] == "audio/wav"


def test_the_audio_of_a_book_is_removed_with_the_book(store: UserStore) -> None:
    store.add_book(BOOK, "Der Hund", "", "", BLOCKS)
    store.save_speech(BOOK, "1.0", "Der Hund schläft.", "m", "v", b"RIFF", "audio/wav")

    assert store.speech(BOOK, "1.0") == (b"RIFF", "audio/wav")
    assert store.spoken(BOOK) == {"1.0": ("Der Hund schläft.", "m", "v")}

    store.delete_book(BOOK)

    assert (store.speech(BOOK, "1.0"), store.spoken(BOOK)) == (None, {})


def test_audio_is_not_kept_under_what_is_not_the_id_of_a_sentence(
    store: UserStore,
) -> None:
    with pytest.raises(ValueError):
        store.save_speech(BOOK, "../1.0", "Der Hund.", "m", "v", b"RIFF", "audio/wav")


def test_a_sentence_two_readings_want_is_read_once(store: UserStore) -> None:
    voice = FakeVoice()
    speaker = Speaker(store, voice, workers=1)
    wanted = sentences(2, 0, 2, 5)
    first, second = speaker.start(BOOK, wanted), speaker.start(BOOK, wanted)

    speaker.make(first, BOOK, wanted, KEY, "m", "v")
    again = speaker.make(second, BOOK, wanted, KEY, "m", "v")

    assert voice.read() == ["Ende."]
    assert [one["status"] for one in again] == ["made"]
    assert "generation" not in again[0]


def test_the_sentences_of_a_message_are_read_without_its_markdown() -> None:
    found = sentences_of_message("## Gut!\nDas ist **richtig**. Weiter so!", 4)

    assert [(sentence.id, sentence.text) for sentence in found] == [
        ("4.0", "Gut!"),
        ("4.1", "Das ist richtig."),
        ("4.2", "Weiter so!"),
    ]


def test_the_emoticons_of_a_message_are_not_read_out() -> None:
    found = sentences_of_message(
        "Hallo! \U0001f60a Wie geht\u2019s? \U0001f44d\U0001f3fd \u2764\ufe0f ...", 1
    )

    assert [sentence.text for sentence in found] == ["Hallo!", "Wie geht\u2019s?"]
