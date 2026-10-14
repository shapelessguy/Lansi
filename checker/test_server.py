# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from anki_import import AnkiImporter
from book_sync import BookSync
from intake import Intake
from live import LiveChecker
from profiling import Answer, Profile, Profiler, Questions, WordRating
from sentences import Sentence
from server import Account, Accounts, describe, make_server
from speaking import Speaker
from spelling import Speller, SpellingIssue
from storage import UserStore
from tasks import Tasks
from test_books import epub, page
from test_intake import FakeChat, FakeProfiler
from test_speaking import FakeVoice
from test_translating import FakeModel
from translating import Translator
from users import Users, user_directory
from vocabulary import Form, Vocabularies, Vocabulary

# the importer of each server that is running, by the server's address
IMPORTERS: dict[str, AnkiImporter] = {}
INTAKES: dict[str, Intake] = {}


@pytest.fixture
def url() -> Iterator[str]:
    """A checker server on a free port, stopped after the test."""
    words = ["schön", "wie", "geht", "hund"]
    checker = LiveChecker(
        Speller(language=None, words=words),
        KeyEchoingProfiler(),
        background=lambda job: job(),
    )
    vocabulary = Vocabulary()
    vocabulary.save("noun", "Hund", {"genders": []}, [Form("Hunde", "plural")])
    chat = FakeChat()
    chat.judged("Katzze", "reject", reason="misspelt")
    intake = Intake(vocabulary, FakeProfiler({"Claudio": "name"}), chat)
    importer = AnkiImporter(intake, lambda: ["der Hund", "Claudio"])
    server = make_server(0, checker, intake, importer)
    IMPORTERS[f"http://127.0.0.1:{server.server_port}"] = importer
    INTAKES[f"http://127.0.0.1:{server.server_port}"] = intake
    # checking often for the request to stop keeps the tests quick
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


class KeyEchoingProfiler(Profiler):
    """Answers every question with the key it was given, in place of asking
    Jev, and says which model it was asked for."""

    def __init__(self) -> None:
        super().__init__()

    def profile(
        self,
        sentence: str,
        api_key: str,
        model: str | None = None,
        questions: Questions | None = None,
    ) -> Profile:
        answers = {name: Answer("choice", choice=api_key) for name in questions or {}}
        return Profile(
            answers,
            cost=0.002,
            id=f"request-{sentence}-{'-'.join(questions or {})}",
            model=model or "usual",
            input_tokens=50,
        )

    def rate_words(
        self,
        sentence: str,
        assessment: list[dict[str, str]],
        api_key: str,
        model: str | None = None,
    ) -> tuple[list[WordRating], Profile]:
        return [WordRating("Wie", 0, 3, 0.25)], Profile({}, id="rating")


def post(
    url: str, body: bytes, key: str | None = None, token: str | None = None
) -> tuple[int, object]:
    headers = {"X-OpenRouter-Key": key} if key else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def check(url: str, body: bytes, key: str | None = None) -> list[Any]:
    """The sentences the server makes of a text."""
    _, reply = post(url, body, key)
    assert isinstance(reply, dict)
    sentences: list[Any] = reply["sentences"]
    return sentences


def test_describe_numbers_the_sentences_and_marks_the_one_being_typed() -> None:
    sentences = [
        Sentence("Hallo!", 0, 6, complete=True),
        Sentence("Wie geht", 7, 15, complete=False),
    ]

    assert describe(sentences) == "  1. [done] Hallo!\n  2. [typing] Wie geht"


def test_describe_lists_spelling_issues_under_their_sentence() -> None:
    sentence = Sentence("Ein Hundd xq.", 0, 13, complete=True)
    sentence.spelling = [
        SpellingIssue("Hundd", 4, 9, ["Hund", "Hunde"]),
        SpellingIssue("xq", 10, 12, []),
    ]

    assert describe([sentence]) == (
        "  1. [done] Ein Hundd xq.\n"
        "       spelling: Hundd -> Hund, Hunde\n"
        "       spelling: xq -> no suggestions"
    )


def test_describe_shows_the_profile_of_a_processed_sentence() -> None:
    profile = Profile(
        {
            "grammar_errors": Answer("choice", choice="one", confidence=0.87),
            "clarity": Answer("score", score=2.6, max_score=3),
        }
    )
    sentence = Sentence("Hallo!", 0, 6, complete=True, processed=True, profile=profile)

    assert describe([sentence]) == (
        "  1. [done, processed] Hallo!\n"
        "       profile: grammar_errors=one (87%), clarity=2.6/3"
    )


def test_describe_marks_a_sentence_whose_profile_is_being_made_or_failed() -> None:
    waiting = Sentence("Hallo!", 0, 6, complete=True, profiling=True)
    failed = Sentence("Tschüss!", 7, 15, complete=True, profile_error="no credit")

    assert describe([waiting, failed]) == (
        "  1. [done, profiling] Hallo!\n"
        "  2. [done] Tschüss!\n"
        "       profile failed: no credit"
    )


def test_describe_says_so_when_there_are_no_sentences() -> None:
    assert describe([]) == "(no sentences)"


def test_sentences_request_returns_and_prints_the_checked_sentences(
    url: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # the caret is at the end, where the second sentence is being typed
    body = json.dumps({"text": "Schön! Wie geht Hundd", "caret": 21}).encode()

    status, reply = post(f"{url}/sentences", body)

    assert status == 200
    assert isinstance(reply, dict)
    assert (reply["usage"], reply["pending"]) == ([], False)
    assert reply["local_model"] is None
    assert reply["sentences"] == [
        {
            "text": "Schön!",
            "start": 0,
            "end": 6,
            "complete": True,
            "spelling": [],
            "processed": False,
            "profile": None,
            "profiling": False,
            "profile_error": None,
            "words": [],
            "rating_words": False,
        },
        {
            "text": "Wie geht Hundd",
            "start": 7,
            "end": 21,
            "complete": False,
            "spelling": [
                {"word": "Hundd", "start": 9, "end": 14, "suggestions": ["Hund"]}
            ],
            "processed": False,
            "profile": None,
            "profiling": False,
            "profile_error": None,
            "words": [],
            "rating_words": False,
        },
    ]
    printed = capsys.readouterr().out
    assert (
        "  1. [done] Schön!\n"
        "  2. [typing] Wie geht Hundd\n"
        "       spelling: Hundd -> Hund\n"
    ) in printed


def test_sentences_request_with_a_key_profiles_finished_sentences_with_it(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    body = json.dumps({"text": "Wie geht Hund."}).encode()

    without_key = check(f"{url}/sentences", body)
    post(f"{url}/sentences", body, key="from-the-chat")
    after = check(f"{url}/sentences", body, key="from-the-chat")

    assert without_key[0]["profiling"] is False
    assert after[0]["processed"] is True
    assert after[0]["profile"]["answers"]["grammar_errors"]["choice"] == "from-the-chat"


def test_sentences_request_profiles_with_the_model_it_names(url: str) -> None:
    body = json.dumps({"text": "Wie geht Hund.", "model": "some/model"}).encode()

    _, reply = post(f"{url}/sentences", body, key="a-key")

    assert isinstance(reply, dict)
    assert {request["model"] for request in reply["usage"]} == {"some/model"}


def test_sentences_request_without_a_model_profiles_with_the_usual_one(
    url: str,
) -> None:
    body = json.dumps({"text": "Wie geht Hund.", "model": ""}).encode()

    _, reply = post(f"{url}/sentences", body, key="a-key")

    assert isinstance(reply, dict)
    assert {request["model"] for request in reply["usage"]} == {"usual"}


def test_sentences_request_profiles_with_the_questions_it_sends(url: str) -> None:
    questions = {
        "polite": {
            "type": "choice",
            "instructions": "Is the sentence polite?",
            "criteria": {"yes": "It is polite.", "no": "It is not polite."},
        }
    }
    body = json.dumps({"text": "Wie geht Hund.", "questions": questions}).encode()

    post(f"{url}/sentences", body, key="a-key")
    after = check(f"{url}/sentences", body, key="a-key")

    assert after[0]["profile"]["answers"] == {
        "polite": {
            "kind": "choice",
            "choice": "a-key",
            "score": None,
            "max_score": None,
            "yes": None,
            "best": None,
            "confidence": None,
        }
    }


def test_sentences_request_with_a_question_that_has_no_options_is_refused(
    url: str,
) -> None:
    questions = {"polite": {"type": "choice", "instructions": "Is it polite?"}}
    body = json.dumps({"text": "Wie geht Hund.", "questions": questions}).encode()

    status, answer = post(f"{url}/sentences", body, key="a-key")

    assert status == 400
    assert answer == {"error": "question polite needs at least two options"}


def test_sentences_request_reports_each_request_to_the_model_once(url: str) -> None:
    questions = {
        "polite": {
            "type": "choice",
            "instructions": "Is the sentence polite?",
            "criteria": {"yes": "It is polite.", "no": "It is not polite."},
        }
    }
    body = json.dumps({"text": "Wie geht Hund.", "questions": questions}).encode()

    _, first = post(f"{url}/sentences", body, key="a-key")
    _, second = post(f"{url}/sentences", body, key="a-key")

    assert isinstance(first, dict) and isinstance(second, dict)
    assert first["usage"] == [
        {
            "id": "request-Wie geht Hund.-polite",
            "model": "usual",
            "input_tokens": 50,
            "output_tokens": 0,
            "cost": 0.002,
        }
    ]
    assert first["pending"] is False
    assert second["usage"] == []


def test_sentences_request_rates_the_words_when_it_asks_for_that(url: str) -> None:
    body = json.dumps({"text": "Wie geht Hund.", "words": True}).encode()
    without = json.dumps({"text": "Wie geht Hund."}).encode()

    for _ in range(2):
        post(f"{url}/sentences", body, key="a-key")
    (rated,) = check(f"{url}/sentences", body, key="a-key")
    (not_asked_for,) = check(f"{url}/sentences", without, key="a-key")

    assert rated["words"] == [{"word": "Wie", "start": 0, "end": 3, "value": 0.25}]
    assert not_asked_for["words"] == []


def test_sentences_request_falls_back_to_the_key_set_where_the_server_runs(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-the-environment")
    body = json.dumps({"text": "Wie geht Hund."}).encode()

    post(f"{url}/sentences", body)
    after = check(f"{url}/sentences", body)

    assert after[0]["profile"]["answers"]["grammar_errors"]["choice"] == (
        "from-the-environment"
    )


def test_sentences_request_with_a_caret_reopens_the_sentence_it_is_in(
    url: str,
) -> None:
    text = "Wie geht Hund. Schön geht Hund."

    without = check(f"{url}/sentences", json.dumps({"text": text}).encode())
    with_null = check(
        f"{url}/sentences", json.dumps({"text": text, "caret": None}).encode()
    )
    inside = check(f"{url}/sentences", json.dumps({"text": text, "caret": 4}).encode())

    assert [s["complete"] for s in without] == [True, True]
    assert with_null == without
    assert [s["complete"] for s in inside] == [False, True]


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[]",
        b'{"text": 5}',
        b'{"other": "x"}',
        b"",
        b'{"text": "Hund.", "caret": "3"}',
        b'{"text": "Hund.", "caret": 1.5}',
        b'{"text": "Hund.", "caret": true}',
    ],
)
def test_sentences_request_without_a_text_is_refused(url: str, body: bytes) -> None:
    status, reply = post(f"{url}/sentences", body)

    assert status == 400
    assert isinstance(reply, dict) and reply["error"]


def test_request_to_another_path_is_not_found(url: str) -> None:
    status, _ = post(f"{url}/elsewhere", b'{"text": "Hallo."}')

    assert status == 404


def test_words_request_takes_each_word_in_and_says_what_became_of_it(url: str) -> None:
    body = json.dumps(
        {"words": ["Hunde", "Claudio", "Katzze"], "model": "some/model"}
    ).encode()

    status, reply = post(f"{url}/vocabulary/words", body, key="the-key")

    assert status == 200
    assert isinstance(reply, dict)
    known, skipped, rejected = reply["words"]
    assert (known["status"], known["category"]) == ("known", "noun")
    assert known["entry"]["lemma"] == "Hund"
    assert [form["form"] for form in known["entry"]["forms"]] == ["Hunde", "Hund"]
    assert (skipped["status"], skipped["category"]) == ("skipped", "name")
    assert (rejected["status"], rejected["reason"]) == ("rejected", "misspelt")
    # the requests that were paid for: three to sort the words, one to judge
    assert [used["id"] for used in reply["usage"]][-1] == "chat-1"
    assert len(reply["usage"]) == 4


def test_words_request_without_a_key_fails_only_the_words_that_need_one(
    url: str,
) -> None:
    body = json.dumps({"words": ["Hunde", "Katze"], "model": "some/model"}).encode()

    _, reply = post(f"{url}/vocabulary/words", body)

    assert isinstance(reply, dict)
    assert [word["status"] for word in reply["words"]] == ["known", "failed"]


@pytest.mark.parametrize(
    "body",
    [b"{}", b'{"words": []}', b'{"words": [3]}', b'{"words": ["a"], "model": 3}'],
)
def test_words_request_that_is_not_a_list_of_words_is_refused(
    url: str, body: bytes
) -> None:
    status, _ = post(f"{url}/vocabulary/words", body, key="the-key")

    assert status == 400


def get(url: str) -> tuple[int, Any]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def test_the_vocabulary_is_listed_without_what_is_known_about_each_word(
    url: str,
) -> None:
    status, reply = get(f"{url}/vocabulary/words")

    assert status == 200
    assert reply["categories"][:2] == ["noun", "verb"]
    (word,) = reply["words"]
    assert word.pop("created_at")
    assert {**word, "id": 0} == {
        "id": 0,
        "category": "noun",
        "lemma": "Hund",
        "forms": 2,
        # nobody has used it yet
        "used": 0,
        "seen": 0,
        "first_used": None,
        "last_used": None,
    }


def test_a_word_of_the_vocabulary_is_given_with_everything_stored_of_it(
    url: str,
) -> None:
    _, listed = get(f"{url}/vocabulary/words")
    word_id = listed["words"][0]["id"]

    status, word = get(f"{url}/vocabulary/words/{word_id}")
    missing, _ = get(f"{url}/vocabulary/words/{word_id + 1}")

    assert status == 200
    assert (word["lemma"], word["category"]) == ("Hund", "noun")
    assert word["details"] == {"genders": []}
    assert [(form["form"], form["tags"]) for form in word["forms"]] == [
        ("Hunde", "plural"),
        ("Hund", ""),
    ]
    assert word["created_at"]
    assert missing == 404


def test_the_import_goes_by_what_a_request_hands_it_and_says_what_it_is_doing(
    url: str,
) -> None:
    settings = json.dumps({"enabled": True, "model": "some/model"}).encode()
    switched_off = json.dumps({"enabled": False}).encode()

    _, before = post(f"{url}/vocabulary/import", settings, key="the-key")
    # the server looks every ten seconds; here it is made to look at once
    IMPORTERS[url].look()
    _, after = post(f"{url}/vocabulary/import", settings)
    _, again = post(f"{url}/vocabulary/import", switched_off)
    IMPORTERS[url].look()
    _, off = post(f"{url}/vocabulary/import", switched_off)

    assert isinstance(before, dict) and isinstance(after, dict)
    assert isinstance(again, dict) and isinstance(off, dict)
    assert (before["state"], before["taken"], before["usage"]) == ("waiting", 0, [])
    assert (after["state"], after["taken"], after["remaining"]) == ("waiting", 2, 0)
    # the words were sorted by the decision model, which is paid for
    assert len(after["usage"]) == 2
    assert again["usage"] == []
    assert off["state"] == "off"


def test_the_language_a_request_names_is_the_one_everything_goes_by_from_then_on(
    url: str,
) -> None:
    settings = json.dumps({"enabled": True, "language": " Italian "}).encode()

    status, _ = post(f"{url}/vocabulary/import", settings)
    refused, _ = post(f"{url}/vocabulary/import", b'{"language": 3}')
    in_italian = INTAKES[url].language
    post(f"{url}/sentences", json.dumps({"text": "", "language": "French"}).encode())

    assert (status, refused) == (200, 400)
    assert (in_italian, INTAKES[url].language) == ("Italian", "French")


def test_asking_for_the_words_of_a_language_names_which_vocabulary_is_meant(
    url: str,
) -> None:
    _, named = get(f"{url}/vocabulary/words?language=German")
    _, entry = get(f"{url}/vocabulary/words/{named['words'][0]['id']}?language=German")

    assert [word["lemma"] for word in named["words"]] == ["Hund"]
    assert entry["lemma"] == "Hund"


def test_the_import_is_told_which_language_the_anki_words_are_of(url: str) -> None:
    settings = json.dumps(
        {"enabled": True, "language": "Arabic", "anki_language": "German"}
    ).encode()

    post(f"{url}/vocabulary/import", settings, key="the-key")
    IMPORTERS[url].look()

    assert INTAKES[url].language == "Arabic"
    # the words were looked up where the test put them: in the one vocabulary
    assert IMPORTERS[url].status()[0].taken == 2
    assert IMPORTERS[url]._language == "German"  # noqa: SLF001


def test_the_import_stays_off_for_a_user_the_anki_words_are_not_of() -> None:
    intake = Intake(Vocabulary(), FakeProfiler(), FakeChat())
    importer = AnkiImporter(intake, lambda: ["der Hund"])
    account = Account(LiveChecker(Speller(language=None)), intake, importer, anki=False)
    server = make_server(0, accounts=Accounts(lambda user: account))
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        post(f"{url}/vocabulary/import", b'{"enabled": true}', key="the-key")
        importer.look()
        _, after = post(f"{url}/vocabulary/import", b'{"enabled": true}')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert isinstance(after, dict)
    assert (after["state"], after["taken"]) == ("off", 0)


@pytest.fixture
def with_users(tmp_path: Path) -> Iterator[str]:
    """A server that two users can log in to, each with a vocabulary of
    their own, stopped after the test."""
    (tmp_path / "users.json").write_text(
        json.dumps({"ada": "a password", "ben": "another one"}), encoding="utf-8"
    )
    users = Users(tmp_path / "users.json", tmp_path)

    def make_account(user: str) -> Account:
        vocabularies = Vocabularies(user_directory(tmp_path, user))
        intake = Intake(vocabularies, FakeProfiler(), FakeChat())
        store = UserStore(user_directory(tmp_path, user))
        return Account(
            LiveChecker(Speller(language=None)),
            intake,
            store=store,
            # the folder is looked through before the request is answered
            book_sync=BookSync(store, background=lambda job: job()),
            translator=Translator(FakeModel()),
            speaker=Speaker(store, FakeVoice()),
            # what is started is done before the request is answered
            tasks=Tasks(background=lambda job: job()),
        )

    server = make_server(0, users=users, accounts=Accounts(make_account))
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def log_in(url: str, user: str, password: str) -> str:
    _, reply = post(
        f"{url}/login", json.dumps({"user": user, "password": password}).encode()
    )
    assert isinstance(reply, dict)
    token: str = reply["token"]
    return token


def test_nothing_is_answered_without_logging_in_where_there_are_users(
    with_users: str,
) -> None:
    words = json.dumps({"words": ["Hund"]}).encode()

    without, _ = post(f"{with_users}/vocabulary/words", words)
    with_a_made_up_token, _ = post(f"{with_users}/vocabulary/words", words, token="x")
    sentences, _ = post(f"{with_users}/sentences", b'{"text": "Hallo."}')

    assert (without, with_a_made_up_token, sentences) == (401, 401, 401)


def test_logging_in_takes_the_right_name_and_password(with_users: str) -> None:
    def try_with(body: dict[str, Any]) -> int:
        status, _ = post(f"{with_users}/login", json.dumps(body).encode())
        return status

    assert try_with({"user": "ada", "password": "a password"}) == 200
    assert try_with({"user": "ada", "password": "another one"}) == 401
    assert try_with({"user": "eve", "password": "a password"}) == 401
    assert try_with({"user": "ada"}) == 400


def test_each_user_has_a_vocabulary_of_their_own(
    with_users: str, tmp_path: Path
) -> None:
    Vocabularies(user_directory(tmp_path, "ada")).of("German").save(
        "noun", "Hund", {}, []
    )
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    words = json.dumps({"words": ["Hund"]}).encode()

    _, of_ada = post(f"{with_users}/vocabulary/words", words, token=ada)
    _, of_ben = post(f"{with_users}/vocabulary/words", words, token=ben)

    assert isinstance(of_ada, dict) and isinstance(of_ben, dict)
    assert of_ada["words"][0]["status"] == "known"
    # he has no such word, and no key to have it looked into
    assert of_ben["words"][0]["status"] == "failed"


def send(
    url: str, method: str, token: str, body: bytes | None = None, kind: str = ""
) -> tuple[int, bytes, str]:
    """Send a request as a user, and return the status, what came back and
    the kind of thing it is."""
    headers = {"Authorization": f"Bearer {token}"}
    if kind:
        headers["Content-Type"] = kind
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read(), response.headers["Content-Type"]
    except urllib.error.HTTPError as error:
        return error.code, error.read(), ""


def test_a_chat_that_is_kept_is_there_for_its_user_only(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    chat = {
        "id": "chat-1",
        "contextId": "tutor",
        "language": "German",
        "updatedAt": 7,
        "messages": [{"role": "user", "content": "Hallo!"}],
    }

    status, _, _ = send(
        f"{with_users}/chats/chat-1", "PUT", ada, json.dumps(chat).encode()
    )
    _, of_ada, _ = send(f"{with_users}/chats", "GET", ada)
    _, of_ben, _ = send(f"{with_users}/chats", "GET", ben)
    without_logging_in, _ = post(f"{with_users}/chats", b"{}")

    assert status == 200
    assert json.loads(of_ada)["chats"] == [
        {
            **chat,
            "messages": [{"role": "user", "content": "Hallo!", "processed": False}],
        }
    ]
    assert json.loads(of_ben) == {"chats": []}
    assert without_logging_in == 401


def test_a_chat_is_removed_and_one_under_another_id_is_refused(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    chat = json.dumps({"id": "chat-1", "messages": []}).encode()
    send(f"{with_users}/chats/chat-1", "PUT", ada, chat)

    under_another_id, _, _ = send(f"{with_users}/chats/chat-2", "PUT", ada, chat)
    removed, _, _ = send(f"{with_users}/chats/chat-1", "DELETE", ada)
    _, left, _ = send(f"{with_users}/chats", "GET", ada)

    assert (under_another_id, removed) == (400, 200)
    assert json.loads(left) == {"chats": []}


def test_a_text_is_kept_with_its_audio_and_removed_with_it(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    text = {
        "id": "die-reise",
        "title": "Die Reise",
        "text": "# Die Reise",
        "audio": None,
    }
    at = f"{with_users}/texts/die-reise"

    send(at, "PUT", ada, json.dumps(text).encode())
    no_audio_yet, _, _ = send(f"{at}/audio", "GET", ada)
    send(f"{at}/audio", "PUT", ada, b"RIFF-and-so-on", "audio/wav")
    _, audio, kind = send(f"{at}/audio", "GET", ada)
    _, texts, _ = send(f"{with_users}/texts", "GET", ada)
    send(at, "DELETE", ada)
    _, left, _ = send(f"{with_users}/texts", "GET", ada)
    gone, _, _ = send(f"{at}/audio", "GET", ada)

    assert no_audio_yet == 404
    assert (audio, kind) == (b"RIFF-and-so-on", "audio/wav")
    assert json.loads(texts) == [{**text, "processed": False}]
    assert (json.loads(left), gone) == ([], 404)


def test_the_settings_of_a_user_are_kept_and_given_back(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    at = f"{with_users}/settings"

    _, before, _ = send(at, "GET", ada)
    send(at, "PUT", ada, json.dumps({"language": "German", "level": "B2"}).encode())
    _, after, _ = send(at, "GET", ada)
    _, of_ben, _ = send(at, "GET", ben)

    assert json.loads(before) == {"settings": None}
    assert json.loads(after) == {"settings": {"language": "German", "level": "B2"}}
    assert json.loads(of_ben) == {"settings": None}


def test_the_sets_of_a_vocabulary_are_kept_for_its_user_and_language(
    with_users: str, tmp_path: Path
) -> None:
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    travel = {"id": "set-1", "name": "Travel", "rule": {"minUsed": 1}}
    at = f"{with_users}/vocabulary/sets"

    kept, _, _ = send(
        f"{at}/set-1?language=German", "PUT", ada, json.dumps(travel).encode()
    )
    without_a_name, _, _ = send(
        f"{at}/set-2?language=German", "PUT", ada, b'{"id": "set-2"}'
    )
    _, of_ada, _ = send(f"{at}?language=German", "GET", ada)
    _, in_italian, _ = send(f"{at}?language=Italian", "GET", ada)
    _, of_ben, _ = send(f"{at}?language=German", "GET", ben)
    send(f"{at}/set-1?language=German", "DELETE", ada)
    _, left, _ = send(f"{at}?language=German", "GET", ada)

    assert (kept, without_a_name) == (200, 400)
    assert json.loads(of_ada) == {"sets": [travel]}
    assert json.loads(in_italian) == json.loads(of_ben) == {"sets": []}
    assert json.loads(left) == {"sets": []}
    # asking after a language made no vocabulary of it
    assert not Vocabularies(user_directory(tmp_path, "ada")).has("Italian")


def test_a_book_is_kept_as_its_text_for_its_user_only_and_removed_when_asked(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    file = epub(page("<h1>Der Hund</h1><p>Es war einmal ein Hund, der gern las.</p>"))

    _, added, _ = send(f"{with_users}/books", "POST", ada, file)
    listed = json.loads(added)
    _, of_ada, _ = send(f"{with_users}/books", "GET", ada)
    _, of_ben, _ = send(f"{with_users}/books", "GET", ben)
    _, whole, _ = send(f"{with_users}/books/{listed['id']}", "GET", ada)
    not_bens, _, _ = send(f"{with_users}/books/{listed['id']}", "GET", ben)
    send(f"{with_users}/books/{listed['id']}", "DELETE", ada)
    gone, _, _ = send(f"{with_users}/books/{listed['id']}", "GET", ada)

    assert listed["title"] == "Der Hund"
    assert json.loads(of_ada) == {"books": [listed]}
    assert json.loads(of_ben) == {"books": []}
    assert json.loads(whole)["blocks"] == [
        {"text": "Der Hund", "size": 2},
        {"text": "Es war einmal ein Hund, der gern las.", "size": 1},
    ]
    assert (not_bens, gone) == (404, 404)


def test_a_file_that_is_not_a_book_is_refused_with_the_reason(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")

    status, reply, _ = send(f"{with_users}/books", "POST", ada, b"%PDF-1.7")
    _, books, _ = send(f"{with_users}/books", "GET", ada)

    assert (status, json.loads(reply)) == (
        400,
        {"error": "the file is not an EPUB book"},
    )
    assert json.loads(books) == {"books": []}


def test_the_books_of_a_folder_a_user_chooses_are_kept_for_that_user(
    with_users: str, tmp_path: Path
) -> None:
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    folder = tmp_path / "OneDrive" / "Books" / "German"
    folder.mkdir(parents=True)
    (folder / "hund.epub").write_bytes(epub(page("<p>Es war einmal.</p>")))
    chosen = json.dumps({"folder": str(folder.parent)}).encode()

    _, before, _ = send(f"{with_users}/books/folder", "GET", ada)
    _, after, _ = send(f"{with_users}/books/folder", "PUT", ada, chosen)
    (folder / "katze.epub").write_bytes(epub(page("<p>Text.</p>")))
    _, looked, _ = send(f"{with_users}/books/sync", "POST", ada)
    _, of_ada, _ = send(f"{with_users}/books", "GET", ada)
    _, of_ben, _ = send(f"{with_users}/books", "GET", ben)
    refused, _, _ = send(f"{with_users}/books/folder", "PUT", ada, b'{"folder": 3}')

    assert json.loads(before)["state"] == "off"
    assert (json.loads(after)["state"], json.loads(after)["found"]) == ("synced", 1)
    assert (json.loads(looked)["found"], json.loads(looked)["revision"]) == (2, 2)
    assert sorted(book["source"] for book in json.loads(of_ada)["books"]) == [
        "German/hund.epub",
        "German/katze.epub",
    ]
    assert json.loads(of_ben) == {"books": []}
    assert refused == 400


def test_the_cover_of_a_book_is_given_as_the_file_it_is(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    file = epub(
        page("<p>Es war einmal.</p>"),
        files={"OEBPS/cover.png": "PNG-and-so-on"},
        manifest='<item id="c" href="cover.png" media-type="image/png"'
        ' properties="cover-image"/>',
    )
    plain = epub(page("<p>Es war einmal.</p>"))

    _, added, _ = send(f"{with_users}/books", "POST", ada, file)
    _, without, _ = send(f"{with_users}/books", "POST", ada, plain)
    at = f"{with_users}/books/{json.loads(added)['id']}/cover"
    status, picture, kind = send(at, "GET", ada)
    none, _, _ = send(
        f"{with_users}/books/{json.loads(without)['id']}/cover", "GET", ada
    )

    assert (json.loads(added)["cover"], json.loads(without)["cover"]) == (True, False)
    assert (status, picture, kind) == (200, b"PNG-and-so-on", "image/png")
    assert none == 404


def test_a_selection_is_translated_with_the_sentences_around_it(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {
        "selection": "Hund",
        "before": "Null. Eins. Zwei. Drei. Vier. Fünf. Der ",
        "after": " schläft. Danach.",
        "language": "German",
        "into": "English",
        "model": "some/model",
    }

    status, reply = post(
        f"{with_users}/translate", json.dumps(body).encode(), key="sk-test", token=ada
    )

    assert status == 200 and isinstance(reply, dict)
    assert reply["translation"] == "the dog"
    assert reply["passage"] == {
        "before": "Eins. Zwei. Drei. Vier. Fünf. Der ",
        "selection": "Hund",
        "after": " schläft.",
    }
    assert reply["usage"] == [
        {
            "id": "gen-1",
            "model": "some/model",
            "input_tokens": 40,
            "output_tokens": 3,
            "cost": 0.001,
        }
    ]


def test_a_translation_that_cannot_be_had_is_answered_with_the_reason(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = json.dumps({"selection": "Hund", "model": "some/model"}).encode()

    without_a_key, reply = post(f"{with_users}/translate", body, token=ada)
    nothing_selected, _ = post(
        f"{with_users}/translate", b'{"selection": " "}', key="sk-test", token=ada
    )
    not_logged_in, _ = post(f"{with_users}/translate", body, key="sk-test")

    assert (without_a_key, nothing_selected, not_logged_in) == (502, 400, 401)
    assert reply == {"error": "an OpenRouter key is needed"}


def test_what_is_asked_about_a_translated_selection_is_answered(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {
        "passage": {"before": "Der ", "selection": "Hund", "after": " schläft."},
        "translation": "the dog",
        "messages": [{"role": "user", "content": "Which gender?"}],
        "model": "some/model",
    }

    status, reply = post(
        f"{with_users}/translate/chat",
        json.dumps(body).encode(),
        key="sk-test",
        token=ada,
    )
    without_messages, _ = post(
        f"{with_users}/translate/chat",
        json.dumps({**body, "messages": []}).encode(),
        key="sk-test",
        token=ada,
    )

    assert status == 200 and isinstance(reply, dict)
    assert reply["reply"] == "the dog"
    assert reply["usage"][0]["id"] == "gen-1"
    assert without_messages == 400


def test_the_words_of_a_selection_are_taken_into_the_vocabulary(url: str) -> None:
    body = {
        "selection": "Hunde Katzze",
        "before": "Zwei ",
        "after": " hier.",
        "model": "some/model",
    }

    status, reply = post(
        f"{url}/vocabulary/selection", json.dumps(body).encode(), key="the-key"
    )
    nothing, _ = post(f"{url}/vocabulary/selection", b'{"selection": "7.05"}')

    assert status == 200 and isinstance(reply, dict)
    assert reply["task"]["title"] == "Hunde Katzze"
    # it is done in the background, and asked after until it is done
    for _ in range(200):
        _, listed = get(f"{url}/tasks")
        (task,) = listed["tasks"]
        if task["state"] != "running":
            break
        time.sleep(0.01)
    assert (task["id"], task["state"]) == (reply["task"]["id"], "done")
    assert (task["done"], task["total"]) == (2, 2)
    assert task["result"] == [
        {"word": "Hunde", "status": "known", "reason": ""},
        {"word": "Katzze", "status": "rejected", "reason": "misspelt"},
    ]
    assert [used["id"] for used in task["usage"]][-1] == "chat-1"
    assert nothing == 400


def test_the_sentences_of_a_book_are_read_aloud_once_and_their_audio_kept(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    file = epub(page("<p>Der Hund schläft. Die Katze nicht. Danach?</p>"))
    _, added, _ = send(f"{with_users}/books", "POST", ada, file)
    book = f"{with_users}/books/{json.loads(added)['id']}"
    # from the middle of the first sentence to the middle of the second
    body = {"start_block": 0, "start": 4, "end_block": 0, "end": 24}
    voiced = json.dumps({**body, "model": "some/tts", "voice": "Kore"}).encode()

    status, first = post(f"{book}/speech", voiced, key="sk-test", token=ada)
    _, again = post(f"{book}/speech", voiced, token=ada)
    heard, audio, kind = send(f"{book}/speech/0.1", "GET", ada)
    unread, _, _ = send(f"{book}/speech/0.2", "GET", ada)
    unvoiced, _ = post(f"{book}/speech", json.dumps(body).encode(), token=ada)
    _, tasks, _ = send(f"{with_users}/tasks", "GET", ada)

    assert status == 200 and isinstance(first, dict) and isinstance(again, dict)
    assert [(one["id"], one["text"], one["ready"]) for one in first["sentences"]] == [
        ("0.0", "Der Hund schläft.", False),
        ("0.1", "Die Katze nicht.", False),
    ]
    assert first["task"]["kind"] == "speech" and first["task"]["reading"]
    # the second time there is nothing to make, and so no key is needed
    assert [one["ready"] for one in again["sentences"]] == [True, True]
    assert again["task"] is None
    assert (heard, kind, unread, unvoiced) == (200, "audio/wav", 404, 400)
    assert "Die Katze nicht.".encode() in audio
    (task,) = json.loads(tasks)["tasks"]
    assert (task["state"], task["done"], task["total"]) == ("done", 2, 2)
    assert [one["status"] for one in task["result"]] == ["made", "made"]


def test_a_reading_is_told_where_the_listener_is_and_to_stop(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    place = json.dumps({"at": 3}).encode()

    told, _, _ = send(f"{with_users}/books/b/speech/r", "PUT", ada, place)
    not_a_place, _, _ = send(f"{with_users}/books/b/speech/r", "PUT", ada, b"{}")
    stopped, _, _ = send(f"{with_users}/books/b/speech/r", "DELETE", ada)

    assert (told, not_a_place, stopped) == (200, 400, 200)


def test_a_message_of_a_chat_is_read_aloud_and_its_audio_removed_with_the_chat(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    chat = f"{with_users}/chats/chat-1"
    body = {"message": 1, "text": "**Gut!** Weiter so.", "model": "m", "voice": "v"}

    status, reply = post(
        f"{chat}/speech", json.dumps(body).encode(), key="sk-test", token=ada
    )
    heard, audio, _ = send(f"{chat}/speech/1.1", "GET", ada)
    without_text, _ = post(f"{chat}/speech", b'{"message": 1}', token=ada)
    send(chat, "DELETE", ada)
    gone, _, _ = send(f"{chat}/speech/1.1", "GET", ada)

    assert status == 200 and isinstance(reply, dict)
    assert [(one["id"], one["text"]) for one in reply["sentences"]] == [
        ("1.0", "Gut!"),
        ("1.1", "Weiter so."),
    ]
    assert (heard, without_text, gone) == (200, 400, 404)
    assert "Weiter so.".encode() in audio
