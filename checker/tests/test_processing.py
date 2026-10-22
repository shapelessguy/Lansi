# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from intake import Intake, Word
from processing import MAX_TRIES, Processor, words_in, words_of
from storage import UserStore
from test_intake import CHAT, DECIDER, FakeChat, FakeProfiler, noun, savable
from vocabulary import Form, Vocabularies


class Clock:
    """The time, which stands still until it is moved on."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> UserStore:
    return UserStore(tmp_path / "ada", now=clock)


@pytest.fixture
def vocabularies(tmp_path: Path) -> Vocabularies:
    vocabularies = Vocabularies(tmp_path / "ada")
    german = vocabularies.of("German")
    german.save("noun", "Hund", {}, [Form("Hunde")])
    german.save("verb", "gehen", {}, [Form("geht")])
    return vocabularies


@pytest.fixture
def chat() -> FakeChat:
    chat = FakeChat()
    for word in ("Der", "Hunde", "schnell", "Wie"):
        chat.judged(word, "reject", reason="for the test")
    return chat


@pytest.fixture
def processor(
    store: UserStore, vocabularies: Vocabularies, chat: FakeChat, clock: Clock
) -> Processor:
    profiler = FakeProfiler({"geht": "verb", "gehen": "verb", "Ada": "name"})
    processor = Processor(
        store, Intake(vocabularies, profiler, chat), now=clock, settle_secs=5
    )
    processor.configure(CHAT, DECIDER)
    return processor


def keep_chat(store: UserStore, *contents: str, **more: Any) -> None:
    """Keep a chat in which the user and the model take turns."""
    messages = [
        {"role": ("user", "assistant")[number % 2], "content": content}
        for number, content in enumerate(contents)
    ]
    store.save_chat(
        {"id": "chat-1", "language": "German", "messages": messages, **more}
    )


def processed(store: UserStore) -> list[bool]:
    return [message["processed"] for message in store.chats()[0]["messages"]]


def test_the_words_of_a_text_come_each_with_their_sentence_and_without_markup() -> None:
    words = words_of("# Der Hund\n\nEr **geht** schnell. Wie geht's?")

    assert words == [
        Word("Der", "Der Hund"),
        Word("Hund", "Der Hund"),
        Word("Er", "Er geht schnell."),
        Word("geht", "Er geht schnell."),
        Word("schnell", "Er geht schnell."),
        Word("Wie", "Wie geht's?"),
        Word("geht's", "Wie geht's?"),
    ]


def test_a_message_is_not_processed_until_it_has_been_left_alone_for_a_while(
    processor: Processor, store: UserStore, clock: Clock
) -> None:
    keep_chat(store, "Hund")

    too_soon = processor.look()
    clock.now += 6
    later = processor.look()

    assert (too_soon, later) == (0, 1)
    assert processed(store) == [True]


def test_every_use_of_a_stored_word_is_recorded_with_who_used_it_and_when(
    processor: Processor, store: UserStore, vocabularies: Vocabularies, clock: Clock
) -> None:
    keep_chat(store, "Hund, Hund!", "Der Hund geht.")
    written_at = clock.now
    clock.now += 6

    processor.look()

    german = vocabularies.of("German")
    hund = german.find("noun", "Hund")
    gehen = german.find("verb", "gehen")
    assert hund is not None and gehen is not None
    assert german.uses_of(hund.id) == [
        ("hund", "user", written_at),
        ("hund", "user", written_at),
        ("hund", "assistant", written_at),
    ]
    assert german.uses_of(gehen.id) == [("geht", "assistant", written_at)]
    assert processed(store) == [True, True]


def test_the_listing_says_how_often_a_word_was_used_and_seen_and_when(
    processor: Processor, store: UserStore, vocabularies: Vocabularies, clock: Clock
) -> None:
    keep_chat(store, "Hund, Hund!", "Der Hund geht.")
    written_at = clock.now
    clock.now += 6
    processor.look()

    listed = {word.lemma: word for word in vocabularies.of("German").listing()}

    assert (listed["Hund"].used, listed["Hund"].seen) == (2, 1)
    assert (listed["gehen"].used, listed["gehen"].seen) == (0, 1)
    assert (listed["Hund"].first_used, listed["Hund"].last_used) == (
        written_at,
        written_at,
    )


def test_a_new_word_of_a_message_is_taken_into_the_vocabulary_and_counted(
    processor: Processor,
    store: UserStore,
    vocabularies: Vocabularies,
    chat: FakeChat,
    clock: Clock,
) -> None:
    chat.judged("Katze", "new", "Katze")
    chat.descriptions["Katze"] = noun("die", "Katze", "Katzen", "cat")
    keep_chat(store, "Katze")
    clock.now += 6

    processor.look()

    katze = vocabularies.of("German").find("noun", "Katze")
    assert katze is not None
    assert len(vocabularies.of("German").uses_of(katze.id)) == 1


def test_a_word_that_is_not_stored_is_not_counted_but_its_message_is_processed(
    processor: Processor, store: UserStore, vocabularies: Vocabularies, clock: Clock
) -> None:
    keep_chat(store, "Ada schnell")
    clock.now += 6

    processor.look()

    assert processed(store) == [True]
    assert all(
        word.used == 0 and word.seen == 0
        for word in vocabularies.of("German").listing()
    )


def test_a_message_that_is_processed_again_is_not_counted_twice(
    processor: Processor, store: UserStore, vocabularies: Vocabularies, clock: Clock
) -> None:
    keep_chat(store, "Hund")
    clock.now += 6
    processor.look()

    keep_chat(store, "Hund geht")
    clock.now += 6
    processor.look()

    listed = {word.lemma: word for word in vocabularies.of("German").listing()}
    assert (listed["Hund"].used, listed["gehen"].used) == (1, 1)


def test_a_message_changed_while_it_was_processed_is_processed_again(
    store: UserStore, vocabularies: Vocabularies, clock: Clock
) -> None:
    class Changing(FakeProfiler):
        """Has the message changed while its words are looked into."""

        def ask(self, *args: Any, **kwargs: Any) -> Any:
            if store.chats()[0]["messages"][0]["content"] == "Hund":
                keep_chat(store, "Hund geht")
            return super().ask(*args, **kwargs)

    profiler = Changing({"geht": "verb"})
    processor = Processor(
        store, Intake(vocabularies, profiler, FakeChat()), now=clock, settle_secs=5
    )
    processor.configure(CHAT, DECIDER)
    keep_chat(store, "Hund")
    clock.now += 6

    done = processor.look()
    still_waiting = processed(store)
    clock.now += 6
    processor.look()

    assert (done, still_waiting) == (0, [False])
    assert processed(store) == [True]


def test_what_an_exercise_wrote_is_processed_once_it_is_over_by_who_wrote_it(
    processor: Processor, store: UserStore, vocabularies: Vocabularies, clock: Clock
) -> None:
    store.start_session("s1", "German", "lesson", [], {"cloze": 3})
    store.add_written(
        "s1", "cloze", {"assistant": ["Der Hund geht."], "user": ["Hunde."]}
    )
    clock.now += 6

    while_running = processor.look()
    store.finish_exercise("s1", "cloze", None)
    once_over = processor.look()

    listed = {word.lemma: word for word in vocabularies.of("German").listing()}
    assert (while_running, once_over) == (0, 2)
    assert (listed["Hund"].used, listed["Hund"].seen) == (1, 1)
    assert (listed["gehen"].used, listed["gehen"].seen) == (0, 1)


def test_a_message_goes_into_the_vocabulary_of_the_language_of_its_chat(
    processor: Processor,
    store: UserStore,
    vocabularies: Vocabularies,
    chat: FakeChat,
    clock: Clock,
) -> None:
    chat.judged("cane", "new", "cane")
    chat.descriptions["cane"] = {"meanings": ["dog"], "forms": []}
    keep_chat(store, "cane", language="Italian")
    clock.now += 6

    processor.look()

    assert vocabularies.of("Italian").find("noun", "cane") is not None
    assert vocabularies.of("German").find("noun", "cane") is None


def test_nothing_is_processed_without_a_key(
    store: UserStore, vocabularies: Vocabularies, clock: Clock
) -> None:
    processor = Processor(
        store, Intake(vocabularies, FakeProfiler(), FakeChat()), now=clock
    )
    keep_chat(store, "Hund")
    clock.now += 60

    assert processor.look() == 0
    assert processed(store) == [False]


def test_a_message_with_a_word_that_fails_is_tried_again_and_then_processed_without_it(
    processor: Processor,
    store: UserStore,
    vocabularies: Vocabularies,
    chat: FakeChat,
    clock: Clock,
) -> None:
    chat.judged("Katze", "form", "Katz")
    chat.rescues["Katze"] = savable("", "")
    keep_chat(store, "Hund Katze")
    clock.now += 6

    looks = [processor.look() for _ in range(MAX_TRIES)]

    listed = {word.lemma: word for word in vocabularies.of("German").listing()}
    assert looks == [0] * (MAX_TRIES - 1) + [1]
    assert processed(store) == [True]
    assert listed["Hund"].used == 1


def test_the_words_of_a_selection_come_with_the_whole_sentence_each_is_in() -> None:
    words = words_in("Der Hund ", "schläft. Die Katze", " nicht. Danach.")

    assert words == [
        Word("schläft", "Der Hund schläft."),
        Word("Die", "Die Katze nicht."),
        Word("Katze", "Die Katze nicht."),
    ]


def test_a_word_a_selection_has_part_of_is_one_of_its_words() -> None:
    assert words_in("Der Hu", "nd schl", "äft.") == [
        Word("Hund", "Der Hund schläft."),
        Word("schläft", "Der Hund schläft."),
    ]


def test_a_selection_without_letters_has_no_words() -> None:
    assert words_in("Um 7", ".05 ", "Uhr.") == []
