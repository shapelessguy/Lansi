# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from storage import UserStore

# What came with version 16, taken out of a store to make it as one was before.
BEFORE_EVALUATIONS = """
DROP TABLE evaluation_parts;
DROP TABLE evaluations;
ALTER TABLE sessions DROP COLUMN kind;
ALTER TABLE session_exercises DROP COLUMN minutes;
ALTER TABLE session_exercises DROP COLUMN started_at;
ALTER TABLE session_exercises DROP COLUMN scores;
ALTER TABLE session_exercises DROP COLUMN exam;
"""


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
                "results": {"right": 0, "partial": 1, "wrong": 0},
            },
            "translation": {
                "status": "pending",
                "answered": 0,
                "started_at": None,
                "scores": None,
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


def test_a_log_can_be_kept_where_findings_were_left_naming_the_logs_before(
    tmp_path: Path,
) -> None:
    before = UserStore(tmp_path / "ada")
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
        "length": 2,
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
