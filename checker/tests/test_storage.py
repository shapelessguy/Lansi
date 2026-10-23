# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from starter_topics import STARTER_TOPICS, starter_icon
from storage import UserStore

# What came with versions 24 to 31, taken out of a store to make it as one
# was before: the instances the exercises made, what each replays, whether
# a session is hidden, the parts of a grade and what it is about, the size
# of an evaluation, which was a length, when a message of the tutor was
# processed, what a book lists of itself, and the versions of books.
BEFORE_INSTANCES = """
ALTER TABLE books DROP COLUMN version;
ALTER TABLE books DROP COLUMN parent_id;
ALTER TABLE books DROP COLUMN navigation;
ALTER TABLE tutor_messages DROP COLUMN processed_at;
ALTER TABLE evaluations RENAME COLUMN size TO length;
ALTER TABLE grades DROP COLUMN about;
ALTER TABLE grades DROP COLUMN parts;
ALTER TABLE sessions DROP COLUMN hidden;
DROP TABLE instances;
ALTER TABLE session_exercises DROP COLUMN replay;
"""
# What came with version 23, taken out of a store to make it as one was
# before: the day of an entry of the calendar of the tutor.
BEFORE_DAYS = " ALTER TABLE tutor_memories DROP COLUMN day;"
# What came with version 22, taken out of a store to make it as one was
# before, along with what came before it: what else a tutor message holds.
BEFORE_TURNS = " ALTER TABLE tutor_messages DROP COLUMN turn;"
# What came with version 18, taken out of a store to make it as one was
# before: the chats with the tutor.
BEFORE_TUTOR = """
DROP TABLE learner_texts;
DROP TABLE tutor_memories;
DROP TABLE tutor_messages;
DROP TABLE tutor_chats;
"""
# What came with version 16 and after it, taken out of a store to make it as
# one was before.
BEFORE_EVALUATIONS = (
    BEFORE_TUTOR
    + """
DROP TABLE evaluation_parts;
DROP TABLE evaluations;
ALTER TABLE sessions DROP COLUMN kind;
ALTER TABLE session_exercises DROP COLUMN minutes;
ALTER TABLE session_exercises DROP COLUMN started_at;
ALTER TABLE session_exercises DROP COLUMN scores;
ALTER TABLE session_exercises DROP COLUMN exam;
"""
)


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


def test_what_an_exercise_wrote_comes_back_by_who_wrote_it_in_order(
    store: UserStore,
) -> None:
    store.start_session("s1", "German", "lesson", [], {"cloze": 3})

    store.add_written(
        "s1", "cloze", {"assistant": ["Ich gehe.", " "], "user": ["Ich ging."]}
    )
    store.add_written("s1", "cloze", {"assistant": ["Er geht."]})

    assert store.written("s1", "cloze") == {
        "user": ["Ich ging."],
        "assistant": ["Ich gehe.", "Er geht."],
    }


@pytest.mark.parametrize(
    "not_written",
    [{"nobody": ["Ja."]}, {"user": "Ja."}, {"user": [1]}],
)
def test_what_is_not_written_by_the_learner_or_a_model_is_not_kept(
    store: UserStore, not_written: dict[str, Any]
) -> None:
    store.start_session("s1", "German", "lesson", [], {"cloze": 3})

    with pytest.raises(ValueError):
        store.add_written("s1", "cloze", not_written)
    assert store.written("s1", "cloze") == {"user": [], "assistant": []}


def test_what_an_exercise_wrote_is_processed_once_the_exercise_is_over(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path / "ada", now=lambda: 10.0)
    store.start_session("s1", "German", "lesson", [], {"cloze": 3, "picture": 1})
    store.add_written("s1", "cloze", {"user": ["Ich ging."]})
    store.add_written("s1", "picture", {"assistant": ["Der Hund."]})

    while_running = store.unprocessed(before=20.0)
    store.finish_exercise("s1", "cloze", None)
    once_finished = store.unprocessed(before=20.0)
    store.end_session("s1", "abandoned")
    once_ended = store.unprocessed(before=20.0)

    assert while_running == []
    assert [(item.source_id, item.role, item.content) for item in once_finished] == [
        ("s1/cloze", "user", "Ich ging.")
    ]
    assert [item.content for item in once_ended] == ["Ich ging.", "Der Hund."]
    assert {item.language for item in once_ended} == {"German"}


def test_what_an_exercise_wrote_is_processed_once(store: UserStore) -> None:
    store.start_session("s1", "German", "lesson", [], {"cloze": 3})
    store.add_written("s1", "cloze", {"user": ["Ich ging."]})
    store.end_session("s1", "finished")
    (item,) = store.unprocessed(before=float("inf"))

    noted = store.mark_processed(item, 99.0)

    assert noted is True
    assert store.unprocessed(before=float("inf")) == []


def test_the_settings_come_back_as_they_were_kept(store: UserStore) -> None:
    nothing_yet = store.settings()

    store.save_settings({"language": "German", "level": "B1"})
    store.save_settings({"language": "Italian", "level": "A2"})

    assert nothing_yet is None
    assert store.settings() == {"language": "Italian", "level": "A2"}


def used(**more: Any) -> dict[str, Any]:
    """What a request to a model used, as the app reports it."""
    return {
        "at": 1_000,
        "category": "chat",
        "chatId": "chat-1",
        "model": "openai/gpt-5",
        "promptTokens": 100,
        "completionTokens": 20,
        "cost": 0.5,
        **more,
    }


def test_the_usage_is_added_up_for_a_chat_from_a_time_on_and_in_all(
    store: UserStore,
) -> None:
    store.add_usage(
        [
            used(at=1_000),
            used(at=5_000, chatId="text:die-reise", category="text", cost=0.25),
            used(at=6_000, promptTokens=10, completionTokens=1),
        ]
    )

    usage = store.usage("chat-1", 5_000)

    assert usage["chat"] == {
        "requests": 2,
        "promptTokens": 110,
        "completionTokens": 21,
        "cost": 1.0,
        "costIncomplete": False,
    }
    assert usage["since"]["requests"] == 2
    assert usage["since"]["cost"] == 0.75
    assert usage["everything"]["requests"] == 3


def test_the_usage_is_added_up_for_each_category_and_model(store: UserStore) -> None:
    store.add_usage(
        [
            used(),
            used(cost=0.25),
            used(model="google/gemini-3-flash", cost=None),
            used(category="checking", cost=0.125),
        ]
    )

    by_model = store.usage("chat-1", 0)["byModel"]

    assert [(one["category"], one["model"]) for one in by_model] == [
        ("chat", "openai/gpt-5"),
        ("chat", "google/gemini-3-flash"),
        ("checking", "openai/gpt-5"),
    ]
    assert by_model[0]["requests"] == 2
    assert by_model[0]["cost"] == 0.75
    assert by_model[1]["costIncomplete"] is True


def test_a_request_reported_again_under_the_same_id_is_counted_once(
    store: UserStore,
) -> None:
    first = store.add_usage([used(id="gen-1"), used()])
    again = store.add_usage([used(id="gen-1"), used()])

    assert (first, again) == (2, 1)
    assert store.usage("chat-1", 0)["everything"]["requests"] == 3


def test_usage_that_is_not_an_entry_is_refused_and_none_of_it_kept(
    store: UserStore,
) -> None:
    for wrong in (
        used(category=""),
        used(promptTokens=-1),
        used(cost=True),
        used(id=7),
        "chat",
    ):
        with pytest.raises(ValueError):
            store.add_usage([used(), wrong])

    assert store.usage("chat-1", 0)["everything"]["requests"] == 0


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
        "cover": False,
    }
    assert store.books() == [{**listed, "versions": []}]
    assert store.book("book-1") == {
        **listed,
        "blocks": blocks,
        "contents": [],
        "landmarks": [],
    }


def test_a_book_is_given_with_what_it_lists_of_itself(store: UserStore) -> None:
    contents = [{"title": "Eins", "block": 0, "entries": [{"title": "A", "block": 1}]}]
    landmarks = [{"type": "bodymatter", "title": "Text", "block": 0}]
    store.add_book(
        "book-1", "Der Hund", "", "", [], contents=contents, landmarks=landmarks
    )

    book = store.book("book-1")

    assert book is not None
    assert (book["contents"], book["landmarks"]) == (contents, landmarks)


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
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_EVALUATIONS)  # noqa: SLF001
    before._db.execute("DROP TABLE books")  # noqa: SLF001
    before._db.execute("DROP TABLE book_speech")  # noqa: SLF001
    later = (
        "written",
        "grades",
        "logs",
        "session_exercises",
        "sessions",
        "topics",
        "embeddings",
        "usage",
    )
    for table in later:
        before._db.execute(f"DROP TABLE {table}")  # noqa: SLF001
    before._db.execute("PRAGMA user_version = 1")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")
    store.add_book("book-1", "Der Hund", "", "", [])

    assert [book["title"] for book in store.books()] == ["Der Hund"]
    assert store.settings() == {"level": "B1"}


def test_the_anki_decks_left_out_are_kept(store: UserStore) -> None:
    none = store.skipped_anki_decks()

    store.save_skipped_anki_decks([1781273623688, 2])

    assert (none, store.skipped_anki_decks()) == ([], [1781273623688, 2])


def test_a_book_kept_again_stays_as_long_ago_added(tmp_path: Path) -> None:
    times = iter([10.0, 20.0])
    store = UserStore(tmp_path / "ada", now=lambda: next(times))
    store.add_book("book-1", "Der Hund", "", "", [])

    read_again = store.add_book("book-1", "Der große Hund", "", "", [])

    assert (read_again["title"], read_again["addedAt"]) == ("Der große Hund", 10000)


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


def test_the_file_a_book_was_read_from_is_kept_with_it_and_removed_with_it(
    store: UserStore,
) -> None:
    store.add_book("book-1", "Der Hund", "", "", [], original=b"PK-and-so-on")
    store.add_book("book-2", "Die Katze", "", "", [])

    kept = store.original("book-1")
    store.delete_book("book-1")

    assert kept == b"PK-and-so-on"
    assert (store.original("book-2"), store.original("book-1")) == (None, None)


def test_a_book_that_is_read_again_without_a_cover_has_none_any_more(
    store: UserStore,
) -> None:
    store.add_book("book-1", "Der Hund", "", "", [], cover=(b"GIF89a", "image/gif"))

    again = store.add_book("book-1", "Der Hund", "", "", [])

    assert (again["cover"], store.cover("book-1")) == (False, None)


def test_sessions_can_be_kept_where_things_were_kept_before_there_were_sessions(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before.save_settings({"level": "B1"})
    later = (
        "written",
        "grades",
        "logs",
        "session_exercises",
        "sessions",
        "topics",
        "embeddings",
        "usage",
    )
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_EVALUATIONS)  # noqa: SLF001
    for table in later:
        before._db.execute(f"DROP TABLE {table}")  # noqa: SLF001
    before._db.execute("PRAGMA user_version = 5")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")
    store.start_session("s1", "German", "trennbare-verben", [], {"cloze": 3})
    store.add_grades("s1", "cloze", [{"result": "right", "answer": "Ja."}])

    assert [log["answer"] for log in store.grades("s1")] == ["Ja."]
    assert store.settings() == {"level": "B1"}


def test_usage_can_be_kept_where_things_were_kept_before_there_was_usage(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before.save_settings({"level": "B1"})
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_EVALUATIONS)  # noqa: SLF001
    before._db.execute("DROP TABLE written")  # noqa: SLF001
    before._db.execute("DROP TABLE grades")  # noqa: SLF001
    before._db.execute("DROP TABLE usage")  # noqa: SLF001
    before._db.execute("ALTER TABLE sessions DROP COLUMN lessons")  # noqa: SLF001
    before._db.execute(  # noqa: SLF001
        "ALTER TABLE session_exercises DROP COLUMN options"
    )
    before._db.execute("PRAGMA user_version = 8")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")
    store.add_usage([used()])

    assert store.usage("chat-1", 0)["everything"]["requests"] == 1
    assert store.settings() == {"level": "B1"}


def test_the_texts_kept_before_are_dropped_and_sessions_kept(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before.start_session("s1", "German", "lesson", [], {"cloze": 3})
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_EVALUATIONS)  # noqa: SLF001
    before._db.execute("DROP TABLE written")  # noqa: SLF001
    before._db.execute("DROP TABLE grades")  # noqa: SLF001
    before._db.execute(  # noqa: SLF001
        "ALTER TABLE session_exercises DROP COLUMN options"
    )
    before._db.execute(  # noqa: SLF001
        "CREATE TABLE texts (id TEXT PRIMARY KEY, body TEXT NOT NULL)"
    )
    before._db.execute("PRAGMA user_version = 10")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")
    store.add_written("s1", "cloze", {"user": ["Ich ging."]})

    tables = {
        name
        for (name,) in store._db.execute(  # noqa: SLF001
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "texts" not in tables
    session = store.session("s1")
    assert session is not None and session["options"] == {"cloze": {}}
    assert store.written("s1", "cloze")["user"] == ["Ich ging."]


def test_a_session_says_how_far_each_of_its_exercises_got(tmp_path: Path) -> None:
    times = iter([10.0, 20.0, 30.0])
    store = UserStore(tmp_path / "ada", now=lambda: next(times))
    store.start_session(
        "s1", "German", "lesson", ["t1"], {"cloze": 3, "translation": 2}
    )
    store.save_exercise_state("s1", "cloze", {"at": 1}, {"shown": True})
    store.add_grades("s1", "cloze", [{"result": "partial", "answer": "a", "note": "n"}])

    store.end_session("s1", "abandoned")

    session = store.session("s1")
    assert session == {
        "id": "s1",
        "language": "German",
        "lesson": "lesson",
        "lessons": [],
        "topics": ["t1"],
        "started_at": 10.0,
        "finished_at": 30.0,
        "status": "abandoned",
        "words": None,
        "mix_topics": False,
        "kind": "practice",
        "hidden": False,
        "exercises": {"cloze": 3, "translation": 2},
        "guidance": {"cloze": "", "translation": ""},
        "options": {"cloze": {}, "translation": {}},
        "minutes": {"cloze": 0, "translation": 0},
        "exams": {"cloze": "", "translation": ""},
        "progress": {
            "cloze": {
                "status": "started",
                "answered": 1,
                "started_at": 20.0,
                "scores": None,
                "kept": 0,
                "replays": False,
                "results": {"right": 0, "partial": 1, "wrong": 0},
            },
            "translation": {
                "status": "pending",
                "answered": 0,
                "started_at": None,
                "scores": None,
                "kept": 0,
                "replays": False,
                "results": {"right": 0, "partial": 0, "wrong": 0},
            },
        },
    }
    assert store.exercise_state("s1", "cloze") == (True, {"at": 1}, {"shown": True})
    assert store.exercise_state("s1", "translation") == (False, None, None)


def test_a_session_keeps_the_words_its_exercises_are_to_use(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "ada")
    words = {"mode": "only", "lemmas": ["der Arzt", "krank"]}

    store.start_session(
        "s1", "German", "lesson", ["t1", "t2"], {"cloze": 3}, words, True
    )

    session = store.session("s1")
    assert session and (session["words"], session["mix_topics"]) == (words, True)


def test_a_topic_is_kept_with_its_icon_and_removed_with_it(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "ada", now=lambda: 5.0)

    added = store.add_topic("t1", " Beim Arzt ", "symptoms, appointments ")
    without = store.icon("t1")
    kept = store.save_icon("t1", b"png", "image/png")
    listed = store.topics()
    icon = store.icon("t1")
    store.delete_topic("t1")

    assert added == {
        "id": "t1",
        "title": "Beim Arzt",
        "description": "symptoms, appointments",
        "created_at": 5.0,
        "icon": False,
    }
    assert (without, kept, icon) == (None, True, (b"png", "image/png"))
    assert listed[0]["icon"] is True
    assert (store.topics(), store.icon("t1")) == ([], None)
    assert not (tmp_path / "ada" / "topics" / "t1").exists()


def test_an_icon_is_not_kept_for_a_topic_there_is_not(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "ada")

    assert store.save_icon("gone", b"png", "image/png") is False
    assert store.save_icon("../escape", b"png", "image/png") is False


def test_a_topic_needs_a_title(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="title"):
        UserStore(tmp_path / "ada").add_topic("t1", "  ", "")


def test_embeddings_are_kept_by_the_model_that_made_them(tmp_path: Path) -> None:
    store = UserStore(tmp_path / "ada")

    store.save_embeddings("one/model", {"Hund": b"", "Katze": b""})
    store.save_embeddings("other/model", {"Hund": b""})
    store.save_embeddings("one/model", {"Hund": b""})

    assert store.embedded("one/model") == {"Hund": b"", "Katze": b""}
    assert store.embedded("other/model") == {"Hund": b""}


def test_a_session_keeps_what_each_of_its_exercises_was_told_to_heed(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path / "ada")

    store.start_session(
        "s1", "German", "l", [], {"cloze": 2, "picture": 1}, guidance={"cloze": "x"}
    )

    session = store.session("s1")
    assert session and session["guidance"] == {"cloze": "x", "picture": ""}


def test_what_an_exercise_was_answered_with_comes_from_its_last_sessions(
    tmp_path: Path,
) -> None:
    times = iter(range(100))
    store = UserStore(tmp_path / "ada", now=lambda: float(next(times)))
    for number, logs in enumerate(
        [
            [{"result": "right", "answer": "der Tisch"}],
            [
                {"result": "wrong", "answer": "der Preis", "correction": "der Pokal"},
                {"result": "right", "answer": "der Tisch"},
            ],
            [{"result": "right", "answer": "die Lampe"}],
        ]
    ):
        store.start_session(f"s{number}", "German", "l", [], {"picture": 1, "cloze": 1})
        store.add_grades(f"s{number}", "picture", logs)
    store.add_grades("s2", "cloze", [{"result": "right", "answer": "Ich stehe auf."}])

    assert store.used_before("picture", 2) == ["die Lampe", "der Pokal", "der Tisch"]
    assert store.used_before("picture", 1) == ["die Lampe"]
    assert store.used_before("translation", 20) == []


def test_the_starter_topics_are_added_once_without_icons_and_after_none_of_the_same_title(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path / "ada", now=lambda: 100.0)
    store.add_topic("t1", "family", "")
    starters = [("Family", "relatives"), ("Travel", "trips"), ("Work", "jobs")]

    added = store.add_starter_topics(starters)
    store.delete_topic("starter-1")
    again = store.add_starter_topics(starters)

    assert (added, again) == (2, 0)
    assert [(topic["title"], topic["icon"]) for topic in store.topics()] == [
        ("family", False),
        ("Work", False),
    ]


def test_the_starter_topics_come_with_the_icons_there_are_of_them(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path / "ada")
    icons = {"Travel": b"\x89PNG travel"}

    store.add_starter_topics([("Family", "relatives"), ("Travel", "trips")], icons.get)

    assert [(topic["title"], topic["icon"]) for topic in store.topics()] == [
        ("Family", False),
        ("Travel", True),
    ]
    assert store.icon("starter-1") == (b"\x89PNG travel", "image/png")


def test_the_instances_an_exercise_made_are_kept_as_files_and_go_with_it(
    store: UserStore, tmp_path: Path
) -> None:
    store.start_session("s1", "German", "dativ", [], {"cloze": 2})
    first = store.add_instances("s1", "cloze", [{"items": ["a"]}])
    second = store.add_instances("s1", "cloze", [{"items": ["b"]}])
    store.start_session("s2", "German", "dativ", [], {"cloze": 2})
    store.set_replay("s2", "cloze", second + first)

    ids = store.instance_ids("s1", "cloze")
    files = sorted((tmp_path / "ada" / "exercises" / "cloze").iterdir())
    assert ids == first + second
    assert store.instances("cloze", ids) == [{"items": ["a"]}, {"items": ["b"]}]
    assert store.instance_ids("s2", "cloze") == second + first
    assert len(files) == 2
    store.delete_session("s1")
    assert list((tmp_path / "ada" / "exercises" / "cloze").iterdir()) == []
    with pytest.raises(ValueError, match="gone"):
        store.instances("cloze", ids)


def test_a_picture_an_instance_holds_is_kept_as_a_file_beside_it(
    store: UserStore, tmp_path: Path
) -> None:
    store.start_session("s1", "German", "dativ", [], {"picture": 1})
    picture = (
        "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8 a picture").decode()
    )

    [made] = store.add_instances("s1", "picture", [{"image": picture, "scene": "x"}])

    folder = tmp_path / "ada" / "exercises" / "picture"
    assert (folder / f"{made}-0.jpg").read_bytes() == b"\xff\xd8 a picture"
    assert "base64" not in (folder / f"{made}.json").read_text(encoding="utf-8")
    assert store.instances("picture", [made]) == [{"image": picture, "scene": "x"}]
    store.delete_session("s1")
    assert list(folder.iterdir()) == []


def test_a_grade_of_several_answers_is_kept_with_each_as_it_was_graded(
    store: UserStore,
) -> None:
    store.start_session("s1", "German", "dativ", [], {"comprehension": 1})
    parts = [
        {"result": "right", "task": "Wann?", "answer": "Samstag", "correction": ""},
        {
            "result": "wrong",
            "task": "Wo?",
            "answer": "",
            "correction": "Im Park",
            "note": "",
        },
    ]

    store.add_grades(
        "s1", "comprehension", [{"result": "partial", "answer": "x", "parts": parts}]
    )

    [kept] = store.grades("s1")
    assert [(each["task"], each["result"], each["note"]) for each in kept["parts"]] == [
        ("Wann?", "right", ""),
        ("Wo?", "wrong", ""),
    ]
    with pytest.raises(ValueError):
        store.add_grades("s1", "comprehension", [{"result": "right", "parts": [{}]}])


def test_every_starter_topic_has_an_icon() -> None:
    assert all(starter_icon(title) for title, _ in STARTER_TOPICS)


def test_a_log_can_be_kept_where_findings_were_left_naming_the_logs_before(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_EVALUATIONS)  # noqa: SLF001
    before._db.executescript(  # noqa: SLF001
        "CREATE TABLE findings (id INTEGER PRIMARY KEY,"
        " log_id INTEGER NOT NULL REFERENCES logs (id) ON DELETE CASCADE);"
        " ALTER TABLE grades DROP COLUMN task;"
        " PRAGMA user_version = 12;"
    )
    before.close()

    store = UserStore(tmp_path / "ada")
    store.start_session("s1", "German", "trennbare-verben", [], {"cloze": 3})
    store.set_log("s1", "cloze", "1 of 3 done.")

    assert store.logs("s1") == {"cloze": "1 of 3 done."}


def test_the_logs_of_exercises_are_among_those_of_everything_once_logs_are_of_more(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before.start_session("s1", "German", "trennbare-verben", [], {"cloze": 3})
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_EVALUATIONS)  # noqa: SLF001
    before._db.executescript(  # noqa: SLF001
        "DROP TABLE logs;"
        " CREATE TABLE logs (session_id TEXT NOT NULL REFERENCES sessions (id)"
        " ON DELETE CASCADE, exercise TEXT NOT NULL, content TEXT NOT NULL,"
        " written_at REAL NOT NULL, PRIMARY KEY (session_id, exercise));"
        " INSERT INTO logs VALUES ('s1', 'cloze', '1 of 3 done.', 5.0);"
        " PRAGMA user_version = 14;"
    )
    before.close()

    store = UserStore(tmp_path / "ada")

    assert store.logs("s1") == {"cloze": "1 of 3 done."}
    assert store.all_logs() == [
        {
            "id": 1,
            "kind": "exercise",
            "language": "German",
            "subject": "cloze",
            "content": "1 of 3 done.",
            "writtenAt": 5.0,
            "session": "s1",
            "exercise": "cloze",
            "source": {},
        }
    ]


def test_a_log_of_an_exercise_is_kept_in_place_of_the_one_it_had(
    store: UserStore,
) -> None:
    store.start_session("s1", "German", "trennbare-verben", [], {"cloze": 3})

    store.set_log("s1", "cloze", "1 of 3 done.")
    store.set_log("s1", "cloze", "3 of 3 done.", "Cloze: Trennbare Verben")

    assert [(log["subject"], log["content"]) for log in store.all_logs()] == [
        ("Cloze: Trennbare Verben", "3 of 3 done.")
    ]


def test_a_log_of_a_translation_is_listed_with_where_it_was_made_the_latest_first(
    store: UserStore,
) -> None:
    store.start_session("s1", "German", "trennbare-verben", [], {"cloze": 3})
    store.set_log("s1", "cloze", "1 of 3 done.")
    where = {"kind": "book", "id": "b1", "title": "Der Hund", "page": 3}

    kept = store.add_log("translation", "German", "gerade", "Asked.", where)

    assert kept["source"] == where and kept["session"] is None
    assert [log["kind"] for log in store.all_logs()] == ["translation", "exercise"]


def test_the_logs_are_listed_a_few_at_a_time_from_one_on(store: UserStore) -> None:
    for number in range(5):
        store.add_log("question", "German", f"word {number}", "Asked.")

    first = store.all_logs(most=2)
    then = store.all_logs(first[-1]["id"], most=2)

    assert [log["subject"] for log in first + then] == [
        "word 4",
        "word 3",
        "word 2",
        "word 1",
    ]


def test_a_log_of_no_kind_there_is_is_refused(store: UserStore) -> None:
    with pytest.raises(ValueError):
        store.add_log("exercise", "German", "cloze", "Done.")
    with pytest.raises(ValueError):
        store.add_log("dream", "German", "cloze", "Done.")


def test_a_session_of_an_exam_runs_beside_one_of_practice_and_is_not_listed_with_them(
    store: UserStore,
) -> None:
    store.start_session("s1", "German", "lesson", [], {"cloze": 3})

    store.start_session(
        "s2", "German", "", [], {"comprehension": 2}, exams={"comprehension": "Teil 1"}
    )

    assert [session["id"] for session in store.sessions()] == ["s1"]
    assert [session["id"] for session in store.sessions("evaluation")] == ["s2"]
    found = store.session("s1")
    assert found and found["status"] == "running"


def test_what_is_written_in_an_exam_is_not_taken_into_the_vocabulary(
    store: UserStore,
) -> None:
    store.start_session("s1", "German", "", [], {"writing": 1}, exams={"writing": "x"})
    store.add_written("s1", "writing", {"user": ["Ich bin krank."]})
    store.end_session("s1", "finished")

    assert store.unprocessed(float("inf")) == []


def test_an_evaluation_keeps_its_plan_the_sessions_of_its_parts_and_what_it_came_to(
    tmp_path: Path,
) -> None:
    times = iter([10.0, 20.0, 30.0, 40.0])
    store = UserStore(tmp_path / "ada", now=lambda: next(times))
    plan = {
        "exam": "A1",
        "pass": {"total": 60},
        "modules": [],
        "parts": [{"module": "reading"}],
    }
    store.start_evaluation("e1", "German", "A1", 2, True, plan)
    store.start_session(
        "s1", "German", "", [], {"comprehension": 2}, exams={"comprehension": "x"}
    )

    store.add_part("e1", 0, "s1")
    store.end_evaluation("e1", "finished", {"scores": {"reading": 80}, "passed": None})

    assert store.evaluation("e1") == {
        "id": "e1",
        "language": "German",
        "level": "A1",
        "size": 2,
        "timed": True,
        "plan": plan,
        "status": "finished",
        "started_at": 10.0,
        "finished_at": 30.0,
        "result": {"scores": {"reading": 80}, "passed": None},
        "sessions": {"0": "s1"},
    }


def test_a_new_evaluation_abandons_the_one_that_was_running(store: UserStore) -> None:
    plan = {"parts": [{"module": "reading"}]}
    store.start_evaluation("e1", "German", "A1", 2, True, plan)

    store.start_evaluation("e2", "German", "A2", 1, False, plan)

    assert [(each["id"], each["status"]) for each in store.evaluations()] == [
        ("e2", "running"),
        ("e1", "abandoned"),
    ]


def test_the_scores_kept_before_are_named_in_english(tmp_path: Path) -> None:
    before = UserStore(tmp_path / "ada")
    before.start_session("s1", "German", "", [], {"writing": 1})
    before.finish_exercise("s1", "writing", {}, {"lesen": 80.0, "aufgabe": 50.0})
    plan = {
        "modules": [{"id": "lesen", "title": "Lesen"}],
        "parts": [{"module": "lesen"}],
    }
    before.start_evaluation("e1", "German", "A1", 2, True, plan)
    before.end_evaluation(
        "e1", "finished", {"scores": {"schreiben_aufgabe": 50}, "passed": None}
    )
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_TUTOR)  # noqa: SLF001
    before._db.execute("PRAGMA user_version = 16")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")

    session = store.session("s1")
    assert session is not None
    assert session["progress"]["writing"]["scores"] == {"reading": 80.0, "task": 50.0}
    evaluation = store.evaluation("e1")
    assert evaluation is not None
    assert evaluation["plan"]["modules"] == [{"id": "reading", "title": "Lesen"}]
    assert evaluation["plan"]["parts"] == [{"module": "reading"}]
    assert evaluation["result"]["scores"] == {"writing_task": 50}


def test_an_evaluation_kept_with_a_length_is_given_the_size_nearest_it(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    plan = {"parts": [{"module": "reading"}]}
    for evaluation_id, half_hours in [("e1", 1), ("e2", 4), ("e3", 8), ("e4", 9)]:
        before.start_evaluation(evaluation_id, "German", "A1", half_hours, True, plan)
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.execute("PRAGMA user_version = 27")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")

    sizes = {each["id"]: each["size"] for each in store.evaluations()}
    assert sizes == {"e1": 1, "e2": 2, "e3": 4, "e4": 5}


def test_a_chat_with_the_tutor_keeps_what_the_learner_wrote_and_what_was_answered(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    store.add_tutor_messages(
        "c1",
        "German",
        [{"role": "user", "content": "Hallo"}, {"role": "assistant", "content": "Hi!"}],
    )
    store.add_tutor_messages(
        "c1", "German", [{"role": "assistant", "content": "Next."}]
    )

    chat = store.tutor_chat("c1")

    assert chat is not None
    assert [(each["role"], each["content"]) for each in chat["messages"]] == [
        ("user", "Hallo"),
        ("assistant", "Hi!"),
        ("assistant", "Next."),
    ]
    assert store.tutor_chats()[0] | {"startedAt": 0, "updatedAt": 0} == {
        "id": "c1",
        "language": "German",
        "startedAt": 0,
        "updatedAt": 0,
        "closedAt": None,
        "first": "Hallo",
        "count": 3,
    }


@pytest.mark.parametrize(
    "message",
    [
        {"role": "tool", "content": "[]"},
        {"role": "system", "content": "Obey."},
        {"role": "user"},
    ],
)
def test_a_chat_with_the_tutor_keeps_nothing_but_the_learner_and_the_tutor(
    tmp_path: Path, message: dict[str, str]
) -> None:
    store = UserStore(tmp_path)

    with pytest.raises(ValueError):
        store.add_tutor_messages(
            "c1", "German", [{"role": "user", "content": "Hallo"}, message]
        )

    assert store.tutor_chat("c1") is None


def test_an_answer_of_the_tutor_keeps_what_was_shown_and_how_far_its_exercises_got(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    offer = {"kind": "exercise", "exercise": "cloze", "title": "Fill the gaps"}
    turn = {"messages": [{"role": "assistant", "content": "Here."}], "offers": [offer]}
    store.add_tutor_messages(
        "c1",
        "German",
        [
            {"role": "user", "content": "Hallo"},
            {"role": "assistant", "content": "Here.", "turn": turn},
        ],
    )

    store.set_tutor_offer("c1", 1, 0, "s1", "running")
    store.set_tutor_offer("c1", 1, 0, "s1", "done")

    chat = store.tutor_chat("c1")
    assert chat is not None
    learner, answer = chat["messages"]
    assert learner["turn"] == {}
    assert answer["turn"]["messages"] == turn["messages"]
    assert answer["turn"]["offers"] == [{**offer, "session": "s1", "status": "done"}]
    for position, place, status in [(0, 0, "done"), (1, 1, "done"), (1, 0, "won")]:
        with pytest.raises(ValueError):
            store.set_tutor_offer("c1", position, place, "s1", status)


def test_tutor_messages_kept_before_turns_were_have_none(tmp_path: Path) -> None:
    before = UserStore(tmp_path / "ada")
    before.add_tutor_messages("c1", "German", [{"role": "user", "content": "Hallo"}])
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_DAYS + BEFORE_TURNS)  # noqa: SLF001
    before._db.execute("PRAGMA user_version = 21")  # noqa: SLF001
    before.close()

    chat = UserStore(tmp_path / "ada").tutor_chat("c1")

    assert chat is not None
    assert chat["messages"][0]["turn"] == {}


def test_a_chat_with_the_tutor_that_is_deleted_is_gone_with_its_messages(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    store.add_tutor_messages("c1", "German", [{"role": "user", "content": "Hallo"}])

    store.delete_tutor_chat("c1")

    assert (store.tutor_chat("c1"), store.tutor_chats()) == (None, [])


def test_nothing_more_is_said_in_a_chat_with_the_tutor_once_it_is_closed(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    store.add_tutor_messages("c1", "German", [{"role": "user", "content": "Hallo"}])

    closed, again = store.close_tutor_chat("c1"), store.close_tutor_chat("c1")

    assert (closed, again) == (True, False)
    with pytest.raises(ValueError, match="closed"):
        store.add_tutor_messages("c1", "German", [{"role": "user", "content": "Noch?"}])
    chat = store.tutor_chat("c1")
    assert chat is not None and chat["closedAt"] is not None


def test_a_memory_that_is_removed_is_kept_apart_with_why_and_by_whom(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    kept = store.add_memory("  Prefers   short answers. ", "c1")
    dropped = store.add_memory("Is going to Vienna in May.")

    removed = store.remove_memory(dropped, "the trip is over", "tutor")

    assert removed is True
    assert [
        (each["id"], each["content"], each["chat"]) for each in store.memories()
    ] == [(kept, "Prefers short answers.", "c1")]
    [gone] = store.memories(removed=True)
    assert (gone["id"], gone["removedWhy"], gone["removedBy"]) == (
        dropped,
        "the trip is over",
        "tutor",
    )
    assert store.remove_memory(dropped, "again", "tutor") is False
    with pytest.raises(ValueError):
        store.remove_memory(kept, "", "someone")


def test_memories_can_be_kept_where_there_were_tutor_chats_before_them(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before.add_tutor_messages("c1", "German", [{"role": "user", "content": "Hallo"}])
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(  # noqa: SLF001
        "DROP TABLE learner_texts; DROP TABLE tutor_memories;"
        " ALTER TABLE tutor_chats DROP COLUMN closed_at;" + BEFORE_TURNS
    )
    before._db.execute("PRAGMA user_version = 18")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")
    store.add_memory("Likes football.")

    assert [each["content"] for each in store.memories()] == ["Likes football."]
    assert store.close_tutor_chat("c1") is True


def test_a_recap_is_kept_line_by_line_apart_from_the_facts(tmp_path: Path) -> None:
    store = UserStore(tmp_path)
    fact = store.add_memory("Likes\nfootball.")
    recapped = store.add_memory(
        "  Talked   about Vienna.\n\nAgreed on more. ", "c1", "recap"
    )

    assert [each["id"] for each in store.memories(kind="fact")] == [fact]
    [kept] = store.memories(kind="recap")
    assert (kept["id"], kept["content"], kept["chat"]) == (
        recapped,
        "Talked about Vienna.\nAgreed on more.",
        "c1",
    )
    assert store.memories(kind="fact")[0]["content"] == "Likes football."
    with pytest.raises(ValueError):
        store.add_memory("Something.", kind="dream")


def test_a_strategy_is_kept_on_one_line_as_its_own_kind(tmp_path: Path) -> None:
    store = UserStore(tmp_path)

    store.add_memory("Anki first,\n  then a   chapter.", "c1", "strategy")

    assert [memory["content"] for memory in store.memories(kind="strategy")] == [
        "Anki first, then a chapter."
    ]
    assert store.memories(kind="fact") == []


def test_an_entry_of_the_calendar_is_kept_for_its_day(tmp_path: Path) -> None:
    store = UserStore(tmp_path)

    store.add_memory("A mock exam.", kind="calendar", day="2026-10-21")
    store.add_memory("Likes football.", day="2026-10-21")

    assert [(each["kind"], each["day"]) for each in store.memories()] == [
        ("calendar", "2026-10-21"),
        ("fact", None),
    ]
    for day in (None, "21.10.26", "2026-13-01"):
        with pytest.raises(ValueError):
            store.add_memory("A mock exam.", kind="calendar", day=day)


def test_memories_kept_before_there_was_a_calendar_have_no_day(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before.add_memory("Likes football.")
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(BEFORE_DAYS)  # noqa: SLF001
    before._db.execute("PRAGMA user_version = 22")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")
    store.add_memory("A mock exam.", kind="calendar", day="2026-10-21")

    assert [each["day"] for each in store.memories()] == [None, "2026-10-21"]


def test_memories_kept_before_there_were_recaps_are_facts(tmp_path: Path) -> None:
    before = UserStore(tmp_path / "ada")
    before.add_memory("Likes football.")
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(  # noqa: SLF001
        "ALTER TABLE tutor_memories DROP COLUMN kind;" + BEFORE_DAYS + BEFORE_TURNS
    )
    before._db.execute("PRAGMA user_version = 20")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")

    assert [each["kind"] for each in store.memories()] == ["fact"]


def test_a_text_is_kept_as_it_was_last_written_and_listed_without_what_it_says(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    store.save_text("t1", "Wochenende", "Am Samstag", "German")
    store.save_text(
        "t1", "Mein Wochenende", "Am Samstag bin ich geschwommen.", "German"
    )

    text = store.text("t1")

    assert text is not None
    assert (text["title"], text["content"], text["kind"]) == (
        "Mein Wochenende",
        "Am Samstag bin ich geschwommen.",
        "text",
    )
    assert [
        (each["title"], each["words"], each["content"]) for each in store.texts()
    ] == [("Mein Wochenende", 5, None)]


def test_a_text_that_was_corrected_is_locked_and_has_its_correction(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    store.save_text("t1", "Wochenende", "Ich bin gegeht.", "German")

    store.correct_text(
        "t1", "Ich bin gegangen.", "c1", "Ich bin ~~gegeht~~ **gegangen**.", "s1"
    )

    text, correction = store.text("t1"), store.text("c1")
    assert text is not None and correction is not None
    assert (text["content"], text["lockedAt"] is not None) == (
        "Ich bin gegangen.",
        True,
    )
    assert (correction["kind"], correction["corrects"], correction["title"]) == (
        "correction",
        "t1",
        "Wochenende (corrected)",
    )
    with pytest.raises(ValueError):
        store.save_text("t1", "Wochenende", "Changed", "German")
    with pytest.raises(ValueError):
        store.save_text("c1", "Changed", "Changed", "German")
    with pytest.raises(ValueError):
        store.correct_text("t1", "Again", "c2", "Again", "s2")


def test_texts_can_be_kept_where_there_were_memories_before_them(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
    before.add_memory("Likes football.")
    before._db.executescript(BEFORE_INSTANCES)  # noqa: SLF001
    before._db.executescript(  # noqa: SLF001
        "DROP TABLE learner_texts; ALTER TABLE tutor_memories DROP COLUMN kind;"
        + BEFORE_DAYS
        + BEFORE_TURNS
    )
    before._db.execute("PRAGMA user_version = 19")  # noqa: SLF001
    before.close()

    store = UserStore(tmp_path / "ada")
    store.save_text("t1", "Hallo", "Text", "German")

    assert [each["title"] for each in store.texts()] == ["Hallo"]
    assert [each["content"] for each in store.memories()] == ["Likes football."]


def test_one_last_tutor_request_is_kept_and_is_of_the_chat_it_was_made_in(
    store: UserStore,
) -> None:
    store.save_last_tutor_request("chat-1", {"label": "Hallo", "call": {"id": 1}})
    store.save_last_tutor_request("chat-2", {"label": "Tschüss", "call": {"id": 2}})

    assert store.last_tutor_request("chat-1") is None
    assert store.last_tutor_request("chat-2") == {
        "label": "Tschüss",
        "call": {"id": 2},
        "chat": "chat-2",
    }


def test_the_last_tutor_request_goes_with_its_chat_when_it_is_deleted(
    store: UserStore,
) -> None:
    store.save_last_tutor_request("chat-1", {"label": "Hallo", "call": {"id": 1}})

    store.delete_tutor_chat("chat-2")
    kept = store.last_tutor_request("chat-1")
    store.delete_tutor_chat("chat-1")

    assert kept is not None
    assert store.last_tutor_request("chat-1") is None


def test_the_usage_is_added_up_by_model_in_bins_of_the_learners_own_days(
    store: UserStore,
) -> None:
    hour, day = 3_600_000, 86_400_000
    store.add_usage(
        [
            # 23:30 UTC on the first day, which is the second day two hours ahead
            used(at=day - hour // 2, cost=0.25),
            used(at=day + hour, cost=0.5),
            used(at=day + 2 * hour, model="google/gemini", cost=None),
            used(at=0, cost=4.0),
        ]
    )

    series = store.usage_series(hour, day, 2 * hour)

    assert [(each["at"], each["model"], each["requests"]) for each in series] == [
        (day - 2 * hour, "google/gemini", 1),
        (day - 2 * hour, "openai/gpt-5", 2),
    ]
    assert series[0]["costIncomplete"] is True
    assert series[1]["cost"] == 0.75


def test_a_version_is_kept_under_its_book_whichever_it_is_made_from(
    tmp_path: Path,
) -> None:
    times = iter([1.0, 2.0, 3.0])
    store = UserStore(tmp_path / "ada", now=lambda: next(times))
    picture = (b"GIF89a", "image/gif")
    store.add_book(
        "book-1", "Der Hund", "Ada", "de", [{"text": "A", "size": 1}], cover=picture
    )
    blocks = [{"text": "A", "size": 1}]

    first = store.add_version("v-1", "book-1", "stripped", "Nur Text", blocks, [], [])
    second = store.add_version("v-2", "v-1", "stripped", "Weniger", blocks, [], [])

    assert first == {
        "id": "v-1",
        "name": "Nur Text",
        "kind": "stripped",
        "addedAt": 2000,
    }
    assert [book["id"] for book in store.books()] == ["book-1"]
    assert store.books()[0]["versions"] == [first, second]
    version = store.book("v-2")
    assert version is not None
    assert (version["title"], version["parent"], version["version"]) == (
        "Der Hund",
        "book-1",
        second,
    )
    assert store.cover("v-2") == picture


def test_a_book_is_removed_with_its_versions_and_a_version_alone(
    store: UserStore,
) -> None:
    store.add_book("book-1", "Der Hund", "", "", [])
    store.add_book("book-2", "Die Katze", "", "", [])
    store.add_version("v-1", "book-1", "stripped", "Eins", [], [], [])
    store.add_version("v-2", "book-2", "stripped", "Zwei", [], [], [])
    store.add_version("v-3", "book-2", "stripped", "Drei", [], [], [])

    store.delete_book("book-1")
    store.delete_book("v-2")

    assert (store.book("v-1"), store.book("v-2")) == (None, None)
    assert [
        (book["id"], [version["id"] for version in book["versions"]])
        for book in store.books()
    ] == [("book-2", ["v-3"])]
