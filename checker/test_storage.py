# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from storage import UserStore


@pytest.fixture
def store(tmp_path: Path) -> UserStore:
    return UserStore(tmp_path / "ada")


def chat(*contents: str, **more: Any) -> dict[str, Any]:
    """A chat in which the user and the model take turns."""
    messages = [
        {"role": ("user", "assistant")[number % 2], "content": content}
        for number, content in enumerate(contents)
    ]
    return {
        "id": "chat-1",
        "contextId": "tutor",
        "language": "German",
        "updatedAt": 5,
        "messages": messages,
        **more,
    }


def mark_processed(store: UserStore) -> None:
    store._db.execute("UPDATE messages SET processed_at = 1")  # noqa: SLF001
    store._db.execute("UPDATE texts SET processed_at = 1")  # noqa: SLF001
    store._db.commit()  # noqa: SLF001


def test_a_chat_comes_back_as_it_was_kept_with_nothing_processed(
    store: UserStore,
) -> None:
    store.save_chat(chat("Hallo!", "Hallo, wie geht es dir?"))

    (kept,) = store.chats()

    assert kept == {
        "id": "chat-1",
        "contextId": "tutor",
        "language": "German",
        "updatedAt": 5,
        "messages": [
            {"role": "user", "content": "Hallo!", "processed": False},
            {
                "role": "assistant",
                "content": "Hallo, wie geht es dir?",
                "processed": False,
            },
        ],
    }


def test_a_message_that_is_as_it_was_stays_processed_and_a_changed_one_does_not(
    store: UserStore,
) -> None:
    store.save_chat(chat("Hallo!", "Hallo, wie"))
    mark_processed(store)

    # the reply went on arriving, and the user wrote again
    store.save_chat(chat("Hallo!", "Hallo, wie geht es dir?", "Gut."))

    (kept,) = store.chats()
    assert [message["processed"] for message in kept["messages"]] == [
        True,
        False,
        False,
    ]


def test_messages_that_are_gone_from_a_chat_are_no_longer_kept(
    store: UserStore,
) -> None:
    store.save_chat(chat("Hallo!", "Hallo.", "Tschüss."))

    store.save_chat(chat("Hallo!"))

    (kept,) = store.chats()
    assert [message["content"] for message in kept["messages"]] == ["Hallo!"]


def test_a_chat_keeps_the_language_it_was_started_in(store: UserStore) -> None:
    store.save_chat(chat("Hallo!"))

    store.save_chat(chat("Hallo!", "Ciao.", language="Italian"))

    assert store.chats()[0]["language"] == "German"


def test_a_deleted_chat_is_gone_with_its_messages(store: UserStore) -> None:
    store.save_chat(chat("Hallo!"))
    store.save_chat(chat("Guten Tag!", id="chat-2"))

    store.delete_chat("chat-1")

    assert [kept["id"] for kept in store.chats()] == ["chat-2"]
    assert store._db.execute("SELECT count(*) FROM messages").fetchone() == (1,)  # noqa: SLF001


@pytest.mark.parametrize(
    "not_a_chat",
    [
        {},
        {"id": "../x", "messages": []},
        {"id": "chat-1"},
        {"id": "chat-1", "messages": [{"role": "user"}]},
        {"id": "chat-1", "messages": [{"role": "nobody", "content": "x"}]},
    ],
)
def test_what_is_not_a_chat_is_not_kept(
    store: UserStore, not_a_chat: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        store.save_chat(not_a_chat)


def text(content: str = "# Die Reise\n\nWir fahren.", **more: Any) -> dict[str, Any]:
    return {
        "id": "die-reise",
        "title": "Die Reise",
        "text": content,
        "language": "German",
        "audio": None,
        **more,
    }


def test_a_text_comes_back_as_it_was_kept_and_not_processed(store: UserStore) -> None:
    store.save_text("die-reise", text())

    assert store.texts() == [{**text(), "processed": False}]


def test_a_text_stays_processed_until_what_it_says_is_changed(
    store: UserStore,
) -> None:
    store.save_text("die-reise", text())
    mark_processed(store)

    store.save_text("die-reise", text(audio={"voice": "Kore"}))
    with_audio_noted = store.texts()[0]
    store.save_text("die-reise", text("# Die Reise\n\nWir fliegen."))

    assert (with_audio_noted["processed"], with_audio_noted["audio"]) == (
        True,
        {"voice": "Kore"},
    )
    assert store.texts()[0]["processed"] is False


def test_the_audio_of_a_text_is_kept_with_the_kind_of_file_it_is(
    store: UserStore,
) -> None:
    store.save_text("die-reise", text())

    kept = store.save_audio("die-reise", b"RIFF....", "audio/wav")
    store.save_text("die-reise", text(audio={"voice": "Kore"}))

    assert kept is True
    assert store.audio("die-reise") == (b"RIFF....", "audio/wav")


def test_there_is_no_audio_for_a_text_that_has_none_or_is_not_there(
    store: UserStore,
) -> None:
    store.save_text("die-reise", text())

    assert store.audio("die-reise") is None
    assert store.save_audio("another", b"x", "audio/wav") is False
    assert store.audio("another") is None


def test_a_deleted_text_is_gone_with_its_audio(
    store: UserStore, tmp_path: Path
) -> None:
    store.save_text("die-reise", text())
    store.save_audio("die-reise", b"RIFF....", "audio/wav")

    store.delete_text("die-reise")

    assert store.texts() == []
    assert not (tmp_path / "ada" / "audio" / "die-reise").exists()


def test_a_text_is_kept_only_under_its_own_id(store: UserStore) -> None:
    with pytest.raises(ValueError):
        store.save_text("another", text())
    with pytest.raises(ValueError):
        store.save_text("../die-reise", text(id="../die-reise"))


def test_the_settings_come_back_as_they_were_kept(store: UserStore) -> None:
    nothing_yet = store.settings()

    store.save_settings({"language": "German", "level": "B1"})
    store.save_settings({"language": "Italian", "level": "A2"})

    assert nothing_yet is None
    assert store.settings() == {"language": "Italian", "level": "A2"}


def test_what_a_user_has_is_still_there_when_it_is_opened_again(
    tmp_path: Path,
) -> None:
    first = UserStore(tmp_path / "ada")
    first.save_chat(chat("Hallo!"))
    first.save_settings({"level": "B1"})
    first.close()

    again = UserStore(tmp_path / "ada")

    assert [kept["id"] for kept in again.chats()] == ["chat-1"]
    assert again.settings() == {"level": "B1"}
    assert UserStore(tmp_path / "ben").chats() == []


def test_a_book_is_listed_without_what_it_says_and_given_whole_when_asked_for(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path / "ada", now=lambda: 12.5)
    blocks = [{"text": "Der Hund", "size": 2}, {"text": "Es war einmal.", "size": 1}]

    listed = store.add_book("book-1", "Der Hund", "Ada Autorin", "de", blocks)

    assert listed == {
        "id": "book-1",
        "title": "Der Hund",
        "author": "Ada Autorin",
        "language": "de",
        "addedAt": 12500,
        "source": None,
        "cover": False,
    }
    assert store.books() == [listed]
    assert store.book("book-1") == {**listed, "blocks": blocks}


def test_a_book_that_is_removed_is_gone(store: UserStore) -> None:
    store.add_book("book-1", "Der Hund", "", "", [{"text": "Text.", "size": 1}])

    store.delete_book("book-1")

    assert store.books() == []
    assert store.book("book-1") is None


def test_books_can_be_kept_where_things_were_kept_before_there_were_books(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before.save_settings({"level": "B1"})
    before._db.execute("DROP TABLE books")  # noqa: SLF001
    before._db.execute("DROP TABLE book_speech")  # noqa: SLF001
    before._db.execute("PRAGMA user_version = 1")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")
    store.add_book("book-1", "Der Hund", "", "", [])

    assert [book["title"] for book in store.books()] == ["Der Hund"]
    assert store.settings() == {"level": "B1"}


def test_a_book_from_the_folder_is_known_by_its_file_and_stays_as_long_ago_added(
    tmp_path: Path,
) -> None:
    times = iter([10.0, 20.0, 30.0])
    store = UserStore(tmp_path / "ada", now=lambda: next(times))
    store.add_book("book-1", "Der Hund", "", "", [], "tiere/hund.epub", "1:100")
    store.add_book("by-hand", "Die Katze", "", "", [])

    read_again = store.add_book(
        "book-1", "Der große Hund", "", "", [], "tiere/hund.epub", "2:120"
    )

    assert store.books_from_folder() == {"tiere/hund.epub": ("book-1", "2:120")}
    assert (read_again["title"], read_again["addedAt"]) == ("Der große Hund", 10000)
    assert read_again["source"] == "tiere/hund.epub"


def test_the_folder_of_books_is_kept(store: UserStore) -> None:
    nowhere = store.books_folder()

    store.save_books_folder(r"C:\Users\ada\OneDrive\Bücher")

    assert (nowhere, store.books_folder()) == ("", r"C:\Users\ada\OneDrive\Bücher")


def test_the_cover_of_a_book_is_kept_with_it_and_removed_with_it(
    store: UserStore,
) -> None:
    picture = (b"\x89PNG-and-so-on", "image/png")
    with_cover = store.add_book("book-1", "Der Hund", "", "", [], cover=picture)
    store.add_book("book-2", "Die Katze", "", "", [])

    kept = store.cover("book-1")
    store.delete_book("book-1")

    assert with_cover["cover"] is True
    assert kept == picture
    assert (store.cover("book-2"), store.cover("book-1")) == (None, None)


def test_a_book_that_is_read_again_without_a_cover_has_none_any_more(
    store: UserStore,
) -> None:
    store.add_book("book-1", "Der Hund", "", "", [], cover=(b"GIF89a", "image/gif"))

    again = store.add_book("book-1", "Der Hund", "", "", [])

    assert (again["cover"], store.cover("book-1")) == (False, None)
