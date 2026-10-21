# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import ANY

import pytest
from anki_import import AnkiImporter, AnkiLink, AnkiRefused, AnkiUnavailable
from evaluating import Evaluations
from exercising import Practice, Runner
from intake import Intake
from live import LiveChecker
from models import Model
from profiling import Answer, Profile, Profiler, Questions, WordRating
from sentences import Sentence
from server import Account, Accounts, describe, in_background, make_server
from speaking import Speaker
from spelling import Speller, SpellingIssue
from storage import UserStore
from tasks import Tasks
from test_books import epub, page
from test_intake import FakeChat, FakeProfiler
from test_speaking import FakeVoice
from test_topics import FakeOpenRouter
from test_translating import FakeModel
from translating import Translator
from users import Users, user_directory
from vocabulary import Form, Vocabularies, Vocabulary

# the importer of each server that is running, by the server's address
IMPORTERS: dict[str, AnkiImporter] = {}
INTAKES: dict[str, Intake] = {}


@pytest.fixture(autouse=True)
def no_lookups_of_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    """What audio used is looked up on OpenRouter, which the tests do not
    reach: it is told as costing nothing."""
    monkeypatch.setattr(
        "server.generation_usages",
        lambda generations, model: [
            Profile({}, id=each, model=model.name) for each in generations if each
        ],
    )


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
    # the import goes by the words above, and only needs there to be Anki
    server = make_server(0, checker, intake, importer, anki=AnkiLink("ada"))
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
        super().__init__("usual")

    def profile(
        self,
        sentence: str,
        model: Model,
        questions: Questions | None = None,
    ) -> Profile:
        answers = {name: Answer("choice", choice=model.key) for name in questions or {}}
        return Profile(
            answers,
            cost=0.002,
            id=f"request-{sentence}-{'-'.join(questions or {})}",
            model=model.name,
            input_tokens=50,
        )

    def rate_words(
        self,
        sentence: str,
        assessment: list[dict[str, str]],
        model: Model,
        correction: str | None = None,
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
            "correction": None,
            "correcting": False,
            "correction_error": None,
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
            "correction": None,
            "correcting": False,
            "correction_error": None,
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


def test_sentences_request_checks_only_the_spelling_when_not_to_profile(
    url: str,
) -> None:
    body = json.dumps({"text": "Wie geht Hundd.", "profile": False}).encode()

    _, reply = post(f"{url}/sentences", body, key="a-key")

    assert isinstance(reply, dict)
    assert (reply["usage"], reply["pending"]) == ([], False)
    (sentence,) = reply["sentences"]
    assert [issue["word"] for issue in sentence["spelling"]] == ["Hundd"]
    assert (sentence["processed"], sentence["profiling"]) == (False, False)


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
    # The requests that were paid for: three to sort the words, one to judge.
    # The words are worked on together, so they come in no set order.
    assert sorted(used["id"] for used in reply["usage"]) == [
        "chat-1",
        "decision-1",
        "decision-2",
        "decision-3",
    ]


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
        "last_used_by_user": None,
        "last_used_by_assistant": None,
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


def test_the_words_of_a_language_come_with_how_its_forms_are_laid_out(
    url: str,
) -> None:
    _, german = get(f"{url}/vocabulary/words?language=German")
    _, italian = get(f"{url}/vocabulary/words?language=Italian")

    assert [table["title"] for table in german["tables"]["noun"]] == [
        "der",
        "die",
        "das",
    ]
    assert italian["tables"] == {}


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


def test_the_import_stays_off_for_a_user_without_anki() -> None:
    intake = Intake(Vocabulary(), FakeProfiler(), FakeChat())
    importer = AnkiImporter(intake, lambda: ["der Hund"])
    account = Account(LiveChecker(Speller(language=None)), intake, importer, anki=None)
    with server_of(account) as url:
        post(f"{url}/vocabulary/import", b'{"enabled": true}', key="the-key")
        importer.look()
        _, after = post(f"{url}/vocabulary/import", b'{"enabled": true}')

    assert isinstance(after, dict)
    assert (after["state"], after["taken"]) == ("off", 0)


@contextmanager
def server_of(account: Account) -> Iterator[str]:
    """The address of a server of `account` alone, stopped afterwards."""
    server = make_server(0, accounts=Accounts(lambda user: account))
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def ask(url: str, method: str, body: object | None = None) -> tuple[int, Any]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


ANKI_WORDS = {
    "rows": [[1, 2, "Hund", "Hund\x1fdog", 10, 30]],
    "timing": {},
    "field_names": {},
}


class FakeAnki(AnkiLink):
    """An Anki account linked with the password "right", in place of the
    deck-status server."""

    def __init__(self) -> None:
        super().__init__("ada", "http://127.0.0.1:1")
        self.linked = False
        self.there = True

    def state(self) -> dict[str, Any]:
        return {"linked": self.linked, "last_sync": None, "error": None}

    def link(self, username: str, password: str) -> dict[str, Any]:
        if password != "right":
            raise AnkiRefused("AnkiWeb ID or password was incorrect")
        self.linked = True
        return self.state()

    def unlink(self) -> dict[str, Any]:
        self.linked = False
        return self.state()

    def decks(self) -> list[dict[str, Any]]:
        return [{"id": 1, "name": "Deutsch"}, {"id": 2, "name": "Englisch"}]

    def known_words(self, decks: list[int] | None = None) -> dict[str, Any]:
        self.asked_decks = decks
        if not self.there:
            raise AnkiUnavailable("the deck-status server cannot be reached")
        if not self.linked:
            raise AnkiRefused("no Anki account is linked")
        return ANKI_WORDS

    def media(self, name: str) -> tuple[bytes, str]:
        if name != "hund bild.png":
            raise AnkiRefused(f"there is no file {name} in Anki (404)")
        return b"PNG", "image/png"


def test_an_anki_account_is_linked_and_its_words_given_to_its_user() -> None:
    anki = FakeAnki()
    account = Account(LiveChecker(Speller(language=None)), anki=anki)
    login = {"username": "ada@example.com", "password": "right"}

    with server_of(account) as url:
        before = ask(f"{url}/anki", "GET")
        linked = ask(f"{url}/anki/link", "POST", login)
        words = ask(f"{url}/anki/words", "GET")

    assert before == (200, {"linked": False, "last_sync": None, "error": None})
    assert linked == (200, {"linked": True, "last_sync": None, "error": None})
    assert words == (200, ANKI_WORDS)


def test_a_wrong_anki_password_is_refused_with_the_reason() -> None:
    account = Account(LiveChecker(Speller(language=None)), anki=FakeAnki())
    login = {"username": "ada@example.com", "password": "wrong"}

    with server_of(account) as url:
        refused = ask(f"{url}/anki/link", "POST", login)
        unsent = ask(f"{url}/anki/link", "POST", {"username": "ada@example.com"})

    assert refused == (400, {"error": "AnkiWeb ID or password was incorrect"})
    assert unsent[0] == 400


def test_the_anki_words_are_refused_once_the_account_is_unlinked() -> None:
    anki = FakeAnki()
    anki.linked = True
    account = Account(LiveChecker(Speller(language=None)), anki=anki)

    with server_of(account) as url:
        unlinked = ask(f"{url}/anki/link", "DELETE")
        words = ask(f"{url}/anki/words", "GET")

    assert unlinked == (200, {"linked": False, "last_sync": None, "error": None})
    assert words == (400, {"error": "no Anki account is linked"})


def test_the_anki_words_say_why_when_the_deck_status_server_is_not_there() -> None:
    anki = FakeAnki()
    anki.there = False
    account = Account(LiveChecker(Speller(language=None)), anki=anki)

    with server_of(account) as url:
        words = ask(f"{url}/anki/words", "GET")

    assert words == (502, {"error": "the deck-status server cannot be reached"})


def test_the_anki_decks_unticked_are_left_out_and_all_others_kept_in(
    tmp_path: Path,
) -> None:
    anki = FakeAnki()
    anki.linked = True
    store = UserStore(tmp_path / "ada")
    account = Account(LiveChecker(Speller(language=None)), store=store, anki=anki)

    with server_of(account) as url:
        before = ask(f"{url}/anki/decks", "GET")
        chosen = ask(f"{url}/anki/decks", "PUT", {"decks": [2]})
        ask(f"{url}/anki/words", "GET")
        left_out = anki.asked_decks
        ask(f"{url}/anki/decks", "PUT", {"decks": []})
        ask(f"{url}/anki/words", "GET")
        refused = ask(f"{url}/anki/decks", "PUT", {"decks": ["Englisch"]})

    assert [deck["chosen"] for deck in before[1]["decks"]] == [True, True]
    assert [deck["chosen"] for deck in chosen[1]["decks"]] == [False, True]
    assert (left_out, anki.asked_decks) == ([1], [1, 2])
    assert refused[0] == 400


def test_a_file_of_the_anki_media_is_sent_as_it_is_or_refused() -> None:
    account = Account(LiveChecker(Speller(language=None)), anki=FakeAnki())

    with server_of(account) as url:
        with urllib.request.urlopen(f"{url}/anki/media/hund%20bild.png") as response:
            sent = (response.status, response.headers["Content-Type"], response.read())
        missing = ask(f"{url}/anki/media/katze.png", "GET")

    assert sent == (200, "image/png", b"PNG")
    assert missing[0] == 404


def test_there_is_no_anki_for_an_account_without_it() -> None:
    account = Account(LiveChecker(Speller(language=None)))

    with server_of(account) as url:
        state = ask(f"{url}/anki", "GET")

    assert state == (404, {"error": "there is no Anki here"})


# the language model of each server with users, by its address
MODELS: dict[str, FakeModel] = {}


@pytest.fixture
def with_users(tmp_path: Path) -> Iterator[str]:
    """A server that two users can log in to, each with a vocabulary of
    their own, stopped after the test."""
    (tmp_path / "users.json").write_text(
        json.dumps({"ada": "a password", "ben": "another one"}), encoding="utf-8"
    )
    users = Users(tmp_path / "users.json", tmp_path)
    # what is asked of the language model, by every user
    model = FakeModel()

    def make_account(user: str) -> Account:
        vocabularies = Vocabularies(user_directory(tmp_path, user))
        intake = Intake(vocabularies, FakeProfiler(), FakeChat())
        store = UserStore(user_directory(tmp_path, user))
        # what is started is done before the request is answered
        tasks = Tasks(background=lambda job: job())
        practice = Practice(
            store,
            runner=FakeRunner(),
            lemmas_of=lambda language: ["der Arzt", "krank", "gehen"],
            send=FakeOpenRouter(),
            later=in_background(tasks, "log"),
        )
        return Account(
            LiveChecker(Speller(language=None)),
            intake,
            store=store,
            translator=Translator(model),
            speaker=Speaker(store, FakeVoice()),
            tasks=tasks,
            practice=practice,
            evaluations=Evaluations(store, practice, later=in_background(tasks, "log")),
        )

    server = make_server(0, users=users, accounts=Accounts(make_account))
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    MODELS[url] = model
    yield url
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


def test_the_usage_of_a_user_is_kept_and_added_up_for_them_alone(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    entry = {
        "at": 2_000,
        "category": "chat",
        "chatId": "chat-1",
        "model": "openai/gpt-5",
        "promptTokens": 100,
        "completionTokens": 20,
        "cost": 0.5,
    }

    kept, reply, _ = send(
        f"{with_users}/usage", "POST", ada, json.dumps({"entries": [entry]}).encode()
    )
    _, of_ada, _ = send(f"{with_users}/usage?chat=chat-1&since=1000", "GET", ada)
    _, of_ben, _ = send(f"{with_users}/usage?chat=chat-1&since=1000", "GET", ben)
    refused, _, _ = send(
        f"{with_users}/usage", "POST", ada, json.dumps({"entries": [{}]}).encode()
    )

    assert (kept, json.loads(reply)) == (200, {"kept": 1})
    assert json.loads(of_ada)["chat"]["cost"] == 0.5
    assert json.loads(of_ada)["since"]["requests"] == 1
    assert json.loads(of_ada)["byModel"][0]["model"] == "openai/gpt-5"
    assert json.loads(of_ben)["everything"]["requests"] == 0
    assert refused == 400


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


def test_what_a_translation_used_is_counted_without_the_app_telling_it(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {"selection": "Hund", "language": "German", "model": "some/model"}

    post(f"{with_users}/translate", json.dumps(body).encode(), key="sk-test", token=ada)
    told_again = {
        "id": "gen-1",
        "at": 2_000,
        "category": "translation",
        "chatId": "translate",
        "model": "some/model",
        "promptTokens": 40,
        "completionTokens": 3,
        "cost": 0.001,
    }
    _, again, _ = send(
        f"{with_users}/usage",
        "POST",
        ada,
        json.dumps({"entries": [told_again]}).encode(),
    )
    _, usage, _ = send(f"{with_users}/usage?chat=translate&since=0", "GET", ada)

    # what the app tells again is counted once
    assert json.loads(again) == {"kept": 0}
    assert json.loads(usage)["chat"]["requests"] == 1
    assert json.loads(usage)["byModel"][0]["category"] == "translation"


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


def test_a_translation_is_logged_with_where_the_selection_was_made(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    where = {"kind": "book", "id": "b1", "title": "Der Hund", "page": 2}
    body = {
        "selection": "Hund",
        "before": "Der ",
        "after": " schläft.",
        "language": "German",
        "model": "some/model",
        "where": where,
    }

    _, reply = post(
        f"{with_users}/translate", json.dumps(body).encode(), key="sk-test", token=ada
    )
    refused, _ = post(
        f"{with_users}/translate",
        json.dumps({**body, "where": "a book"}).encode(),
        key="sk-test",
        token=ada,
    )
    _, of_ada, _ = send(f"{with_users}/logs", "GET", ada)
    _, of_ben, _ = send(f"{with_users}/logs", "GET", ben)

    assert isinstance(reply, dict) and reply["log"]["kind"] == "translation"
    [log] = json.loads(of_ada)["logs"]
    assert (log["subject"], log["language"], log["source"]) == ("Hund", "German", where)
    assert log["content"] == (
        'Asked for "Hund" to be translated, in: "Der [[Hund]] schläft.".\n'
        'Translated as: "the dog".'
    )
    assert json.loads(of_ben) == {"logs": []}
    assert refused == 400


def test_each_matter_asked_about_a_translation_is_logged_when_the_chat_is_over(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {
        "passage": {"before": "Ich bin ", "selection": "gerade", "after": " da."},
        "translation": "just",
        "messages": [
            {"role": "user", "content": "Does it mean straight?"},
            {"role": "assistant", "content": "Here it means just now."},
        ],
        "language": "German",
        "model": "some/model",
        "where": {"kind": "chat", "id": "chat-1"},
    }
    translated = {"selection": "gerade", "before": "Ich bin ", "after": " da."}
    _, reply = post(
        f"{with_users}/translate",
        json.dumps({**translated, "model": "some/model"}).encode(),
        key="sk-test",
        token=ada,
    )
    assert isinstance(reply, dict)
    body["log"] = reply["log"]["id"]
    MODELS[with_users].says = json.dumps(
        {
            "logs": [
                {"subject": "gerade", "points": ["Asked if it means straight."]},
                {"subject": "da", "points": ["Asked what it is."]},
            ]
        }
    )

    status, reply = post(
        f"{with_users}/translate/chat/end",
        json.dumps(body).encode(),
        key="sk-test",
        token=ada,
    )
    _, nothing_asked = post(
        f"{with_users}/translate/chat/end",
        json.dumps({**body, "messages": []}).encode(),
        key="sk-test",
        token=ada,
    )
    _, listed, _ = send(f"{with_users}/logs", "GET", ada)

    assert status == 200 and isinstance(reply, dict)
    assert reply["task"]["kind"] == "questions"
    assert nothing_asked == {"task": None}
    logs = json.loads(listed)["logs"]
    assert [(log["kind"], log["subject"], log["content"]) for log in logs] == [
        ("question", "da", "Asked what it is."),
        ("question", "gerade", "Asked if it means straight."),
        ("translation", "gerade", logs[2]["content"]),
    ]
    assert logs[0]["source"] == {
        "kind": "chat",
        "id": "chat-1",
        "translation": body["log"],
    }


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


class FakeRunner(Runner):
    """Runs every exercise as one that logs each message it is sent, in
    place of starting its backend."""

    def run(
        self,
        exercise: str,
        request: dict[str, Any],
        ask: Any,
        draw: Any = None,
        look: Any = None,
        anki: Any = None,
    ) -> tuple[dict[str, Any], list[Profile]]:
        state = request["state"] or {"done": 0}
        logs = []
        if request["op"] == "act":
            state["done"] += 1
            logs = [
                {"result": "wrong", "answer": request["message"], "correction": "Ja."}
            ]
        show = {"done": state["done"], "level": request["context"]["level"]}
        return {"state": state, "show": show, "graded": logs, "results": state}, []


def test_a_session_of_practice_keeps_the_logs_of_its_exercises(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    _, listed, _ = send(f"{with_users}/lessons?language=German", "GET", ada)
    lesson = json.loads(listed)["lessons"][0]["id"]
    _, made, _ = send(
        f"{with_users}/sessions",
        "POST",
        ada,
        json.dumps(
            {"language": "German", "lesson": lesson, "exercises": {"cloze": 2}}
        ).encode(),
    )
    session = json.loads(made)
    steps = f"{with_users}/sessions/{session['id']}/exercises/cloze"
    learner = {"into": "English", "level": "A2", "model": "some/model"}

    send(f"{steps}/start", "POST", ada, json.dumps(learner).encode())
    _, acted, _ = send(
        f"{steps}/act",
        "POST",
        ada,
        json.dumps({**learner, "message": "Nein."}).encode(),
    )
    _, ended, _ = send(
        f"{with_users}/sessions/{session['id']}/end",
        "POST",
        ada,
        json.dumps(learner).encode(),
    )
    _, kept, _ = send(f"{with_users}/sessions/{session['id']}", "GET", ada)

    assert session["exercises"] == {"cloze": 2}
    assert json.loads(acted) == {
        "show": {"done": 1, "level": "A2"},
        "usage": [],
        "tasks": [],
    }
    assert json.loads(ended)["session"]["status"] == "finished"
    # the log of the exercise is written in the background
    # with no key here, it fails, as the learner is told
    assert [(task["kind"], task["state"]) for task in json.loads(ended)["tasks"]] == [
        ("log", "failed")
    ]
    found = json.loads(kept)
    assert found["progress"]["cloze"] == {
        "status": "finished",
        "answered": 1,
        "started_at": ANY,
        "scores": None,
        "kept": 0,
        "replays": False,
        "results": {"right": 0, "partial": 0, "wrong": 1},
    }
    assert [(log["answer"], log["correction"]) for log in found["grades"]] == [
        ("Nein.", "Ja.")
    ]


def test_the_sessions_of_one_user_are_not_those_of_another(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    ben = log_in(with_users, "ben", "another one")
    body = {
        "language": "German",
        "lesson": "trennbare-verben",
        "exercises": {"cloze": 1},
    }
    _, made, _ = send(f"{with_users}/sessions", "POST", ada, json.dumps(body).encode())
    session_id = json.loads(made)["id"]

    _, of_ben, _ = send(f"{with_users}/sessions", "GET", ben)
    status, _, _ = send(f"{with_users}/sessions/{session_id}", "GET", ben)

    assert json.loads(of_ben) == {"sessions": []}
    assert status == 404


def test_a_session_of_a_lesson_there_is_not_is_refused(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {"language": "German", "lesson": "nothing", "exercises": {"cloze": 1}}

    status, reply, _ = send(
        f"{with_users}/sessions", "POST", ada, json.dumps(body).encode()
    )

    assert status == 400
    assert "no lesson" in json.loads(reply)["error"]


def test_the_interface_of_an_exercise_is_given_without_logging_in(
    with_users: str,
) -> None:
    with urllib.request.urlopen(f"{with_users}/exercises/cloze/ui/index.js") as page:
        kind = page.headers["Content-Type"]
        script = page.read()
    with urllib.request.urlopen(f"{with_users}/exercises/kit.css") as kit:
        style = kit.headers["Content-Type"]
    backend, _ = get(f"{with_users}/exercises/cloze/backend.py")
    listing, _ = get(f"{with_users}/exercises")

    assert kind.startswith("text/javascript") and style.startswith("text/css")
    assert b"export function mount" in script
    # what is not part of an interface is not given, nor is the list to anyone
    assert (backend, listing) == (404, 401)


def test_a_topic_is_made_with_an_icon_and_removed(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {"title": "Beim Arzt", "description": "symptoms", "image_model": "m/image"}
    request = urllib.request.Request(
        f"{with_users}/topics",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {ada}", "X-OpenRouter-Key": "sk-test"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        made = json.load(response)

    topic_id = made["topic"]["id"]
    _, listed, _ = send(f"{with_users}/topics", "GET", ada)
    status, icon, kind = send(f"{with_users}/topics/{topic_id}/icon", "GET", ada)
    send(f"{with_users}/topics/{topic_id}", "DELETE", ada)
    _, after, _ = send(f"{with_users}/topics", "GET", ada)

    assert made["topic"]["title"] == "Beim Arzt"
    assert made["task"]["kind"] == "icon"
    assert json.loads(listed)["topics"][0]["icon"] is True
    assert (status, icon[:4], kind) == (200, b"\x89PNG", "image/png")
    assert json.loads(after) == {"topics": []}


def test_a_topic_made_without_a_key_has_no_icon_yet(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")

    _, made, _ = send(
        f"{with_users}/topics", "POST", ada, json.dumps({"title": "Fußball"}).encode()
    )

    topic = json.loads(made)
    assert (topic["task"], topic["topic"]["icon"]) == (None, False)


def test_the_vocabulary_is_embedded_in_the_background(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = json.dumps({"language": "German", "model": "m/embed"}).encode()
    request = urllib.request.Request(
        f"{with_users}/embeddings",
        data=body,
        headers={"Authorization": f"Bearer {ada}", "X-OpenRouter-Key": "sk-test"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        first = json.load(response)
    _, again, _ = send(f"{with_users}/embeddings", "POST", ada, body)

    assert (first["missing"], first["task"]["kind"]) == (3, "embeddings")
    assert json.loads(again) == {"missing": 0, "task": None}


def test_a_session_is_started_with_the_words_its_topic_needs(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    _, made, _ = send(
        f"{with_users}/topics",
        "POST",
        ada,
        json.dumps({"title": "Beim Arzt", "description": "symptoms"}).encode(),
    )
    topic_id = json.loads(made)["topic"]["id"]
    body = {
        "language": "German",
        "lesson": "trennbare-verben",
        "exercises": {"cloze": 2},
        "topics": [topic_id],
        "vocabulary": "all",
    }
    request = urllib.request.Request(
        f"{with_users}/sessions",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {ada}", "X-OpenRouter-Key": "sk-test"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        session = json.load(response)

    assert session["topics"] == [topic_id]
    # three words are too few to make sentences of alone
    assert session["words"] == {
        "mode": "prefer",
        "lemmas": ["der Arzt", "krank", "gehen"],
    }
    assert session["usage"]


def test_an_exercise_that_kept_nothing_is_not_done_again(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {
        "language": "German",
        "lesson": "trennbare-verben",
        "exercises": {"cloze": 1},
    }
    _, started, _ = send(
        f"{with_users}/sessions", "POST", ada, json.dumps(body).encode()
    )
    session = json.loads(started)["id"]

    refused, said, _ = send(
        f"{with_users}/sessions/{session}/exercises/cloze/replay", "POST", ada, b"{}"
    )

    assert refused == 400
    assert "nothing" in json.loads(said)["error"]


def test_a_session_with_words_chosen_in_a_way_there_is_not_is_refused(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {
        "language": "German",
        "lesson": "trennbare-verben",
        "exercises": {"cloze": 2},
        "vocabulary": "everything",
    }

    status, reply, _ = send(
        f"{with_users}/sessions", "POST", ada, json.dumps(body).encode()
    )

    assert status == 400
    assert "words are chosen" in json.loads(reply)["error"]


def test_the_exams_there_are_of_a_language_are_listed_by_level(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")

    _, listed, _ = send(f"{with_users}/evaluations/levels?language=German", "GET", ada)

    levels = json.loads(listed)["levels"]
    assert [level["level"] for level in levels][:2] == ["A1", "A2"]
    assert [module["id"] for module in levels[0]["modules"]] == [
        "listening",
        "reading",
        "writing",
        "speaking",
    ]


def test_an_evaluation_is_started_and_its_first_part_in_a_session_of_its_own(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {"language": "German", "level": "A1", "length": 2, "timed": True}

    _, made, _ = send(
        f"{with_users}/evaluations", "POST", ada, json.dumps(body).encode()
    )
    evaluation = json.loads(made)
    _, started, _ = send(
        f"{with_users}/evaluations/{evaluation['id']}/parts/0/start", "POST", ada, b"{}"
    )
    _, listed, _ = send(f"{with_users}/evaluations", "GET", ada)
    _, sessions, _ = send(f"{with_users}/sessions", "GET", ada)

    part = json.loads(started)["evaluation"]["parts"][0]
    assert (part["module"], part["exercise"], part["status"]) == (
        "listening",
        "comprehension",
        "running",
    )
    assert json.loads(started)["session"]["kind"] == "evaluation"
    assert [each["id"] for each in json.loads(listed)["evaluations"]] == [
        evaluation["id"]
    ]
    assert json.loads(sessions)["sessions"] == []


def test_an_evaluation_of_a_level_with_no_exam_is_refused(with_users: str) -> None:
    ada = log_in(with_users, "ada", "a password")
    body = {"language": "German", "level": "C2", "length": 2, "timed": True}

    status, said, _ = send(
        f"{with_users}/evaluations", "POST", ada, json.dumps(body).encode()
    )

    assert status == 400
    assert "no exam of German at C2" in json.loads(said)["error"]


# a server of the learner's own, which the chat passes requests on to


class OwnServer(BaseHTTPRequestHandler):
    """Answers as a server that takes OpenAI's requests does, and keeps
    what it was sent."""

    received: list[tuple[str, str, object]] = []

    def do_GET(self) -> None:
        self.received.append((self.path, self.headers.get("Authorization", ""), None))
        self._send("application/json", b'{"data": [{"id": "local/clef"}]}')

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.received.append((self.path, self.headers.get("Authorization", ""), body))
        self._send("text/event-stream", b'data: {"choices": []}\n\ndata: [DONE]\n\n')

    def _send(self, kind: str, data: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def own_server() -> Iterator[str]:
    OwnServer.received = []
    server = HTTPServer(("127.0.0.1", 0), OwnServer)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1"
    server.shutdown()
    server.server_close()


def relay(url: str, body: object) -> tuple[int, str, bytes]:
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers["Content-Type"], response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers["Content-Type"], error.read()


def test_the_models_a_server_of_ones_own_has_are_listed(
    url: str, own_server: str
) -> None:
    status, _, listed = relay(f"{url}/models", {"url": own_server, "key": "own-key"})

    assert (status, json.loads(listed)) == (200, {"models": ["local/clef"]})
    assert OwnServer.received == [("/v1/models", "Bearer own-key", None)]


def test_a_chat_request_is_passed_on_to_the_model_at_its_address(
    url: str, own_server: str
) -> None:
    model = {"model": "local/clef", "url": own_server}

    status, kind, reply = relay(
        f"{url}/models/chat", {"model": model, "messages": [], "stream": True}
    )

    assert (status, kind) == (200, "text/event-stream")
    assert reply.endswith(b"data: [DONE]\n\n")
    assert OwnServer.received == [
        (
            "/v1/chat/completions",
            "",
            {"messages": [], "stream": True, "model": "local/clef"},
        )
    ]


def test_a_model_on_openrouter_is_not_passed_on(url: str) -> None:
    status, _, _ = relay(f"{url}/models/chat", {"model": "some/model"})

    assert status == 400


def test_the_tutor_streams_what_it_does_a_line_at_a_time_and_ends_with_what_was_added(
    with_users: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[list[dict[str, Any]]] = [
        [
            {"choices": [{"delta": {"reasoning": "Which lessons are there?"}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "function": {"name": "lessons", "arguments": "{}"},
                                }
                            ]
                        }
                    }
                ]
            },
        ],
        [{"choices": [{"delta": {"content": "Read the first lesson."}}]}],
    ]
    asked: list[dict[str, Any]] = []

    def stream(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        asked.append(body)
        yield from replies.pop(0)

    monkeypatch.setattr("tutor.stream_chat", stream)
    ada = log_in(with_users, "ada", "a password")
    body = {
        "messages": [{"role": "user", "content": "Hallo"}],
        # one at an address of its own, which needs no key
        "model": {"model": "thinker", "url": "http://127.0.0.1:1"},
        "language": "German",
        "into": "English",
        "level": "A1",
    }

    status, sent, kind = send(
        f"{with_users}/tutor/chat", "POST", ada, json.dumps(body).encode()
    )

    every = [json.loads(line) for line in sent.decode().splitlines()]
    events = [each for each in every if each["type"] not in ("call", "call_done")]
    assert (status, kind) == (200, "application/x-ndjson; charset=utf-8")
    assert [event["type"] for event in events] == [
        "thinking",
        "tool",
        "tool_done",
        "text",
        "done",
    ]
    assert events[1]["doing"] == "Looking at the lessons"
    assert [message["role"] for message in events[-1]["messages"]] == [
        "assistant",
        "tool",
        "assistant",
    ]
    assert "exercise" in [tool["function"]["name"] for tool in asked[0]["tools"]]
    assert "They are at level A1" in asked[0]["messages"][0]["content"]


def test_the_tutor_is_told_how_an_exercise_went_before_it_goes_on(
    with_users: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[dict[str, Any]] = []

    def stream(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        asked.append(body)
        yield {"choices": [{"delta": {"content": "Well done."}}]}

    monkeypatch.setattr("tutor.stream_chat", stream)
    ada = log_in(with_users, "ada", "a password")
    _, listed, _ = send(f"{with_users}/lessons?language=German", "GET", ada)
    lesson = json.loads(listed)["lessons"][0]["id"]
    _, made, _ = send(
        f"{with_users}/sessions",
        "POST",
        ada,
        json.dumps(
            {"language": "German", "lesson": lesson, "exercises": {"cloze": 1}}
        ).encode(),
    )
    session = json.loads(made)
    body = {
        "messages": [
            {"role": "user", "content": "What next?"},
            {"role": "assistant", "content": "Fill the gaps."},
        ],
        "model": {"model": "thinker", "url": "http://127.0.0.1:1"},
        "practised": {"session": session["id"], "exercise": "cloze", "tasks": []},
    }

    _, sent, _ = send(
        f"{with_users}/tutor/chat", "POST", ada, json.dumps(body).encode()
    )

    events = [json.loads(line) for line in sent.decode().splitlines()]
    told = events[-1]["messages"][0]
    assert told["role"] == "user"
    assert "Fill the gaps" in told["content"]
    assert asked[0]["messages"][-1] == told
    assert events[-1]["messages"][-1] == {"role": "assistant", "content": "Well done."}


def test_the_tutor_keeps_its_answers_with_all_the_model_was_told_and_was_shown(
    with_users: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    replies: list[list[dict[str, Any]]] = [
        [
            {"choices": [{"delta": {"content": "Let me look. "}}]},
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "function": {"name": "lessons", "arguments": "{}"},
                                }
                            ]
                        }
                    }
                ]
            },
        ],
        [{"choices": [{"delta": {"content": "Read the first lesson."}}]}],
    ]

    def stream(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        yield from replies.pop(0)

    monkeypatch.setattr("tutor.stream_chat", stream)
    ada = log_in(with_users, "ada", "a password")
    body = {
        "chat": "chat-1",
        "messages": [{"role": "user", "content": "Hallo"}],
        "model": {"model": "thinker", "url": "http://127.0.0.1:1"},
        "language": "German",
    }

    send(f"{with_users}/tutor/chat", "POST", ada, json.dumps(body).encode())
    _, listed, _ = send(f"{with_users}/tutor/chats", "GET", ada)
    _, kept, _ = send(f"{with_users}/tutor/chats/chat-1", "GET", ada)
    deleted, _, _ = send(f"{with_users}/tutor/chats/chat-1", "DELETE", ada)
    gone, _, _ = send(f"{with_users}/tutor/chats/chat-1", "GET", ada)

    assert [chat["first"] for chat in json.loads(listed)["chats"]] == ["Hallo"]
    learner, answer = json.loads(kept)["messages"]
    assert (learner["role"], learner["content"]) == ("user", "Hallo")
    assert (answer["role"], answer["content"]) == (
        "assistant",
        "Let me look. \n\nRead the first lesson.",
    )
    # the tool it called, and what it came to, for the chat to be taken up again
    assert [each["role"] for each in answer["turn"]["messages"]] == [
        "assistant",
        "tool",
        "assistant",
    ]
    assert answer["turn"]["messages"][0]["tool_calls"][0]["id"] == "call-1"
    assert [(step["doing"], step["status"]) for step in answer["turn"]["steps"]] == [
        ("Looking at the lessons", "done")
    ]
    assert (answer["turn"]["offers"], answer["turn"]["exams"]) == ([], [])
    assert (deleted, gone) == (200, 404)


RECAP = "Talked about the exam.\nAgreed to practise the dative."


def recapping(body: dict[str, Any]) -> dict[str, Any] | None:
    """What a model answers when it is asked for the recap of a chat, and
    None when it is asked something else."""
    if "Write a recap" not in body["messages"][0]["content"]:
        return None
    return {"choices": [{"message": {"content": RECAP}}]}


def test_a_closed_chat_with_the_tutor_takes_nothing_more_and_leaves_memories(
    with_users: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stream(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        yield {"choices": [{"delta": {"content": "Good luck in the exam!"}}]}

    asked: list[dict[str, Any]] = []

    def chat(body: dict[str, Any], model: Model) -> dict[str, Any]:
        if recapped := recapping(body):
            return recapped
        asked.append(body)
        said = {"add": ["Has the B1 exam on 2026-12-05."], "remove": [{"id": 99}]}
        return {"choices": [{"message": {"content": json.dumps(said)}}]}

    monkeypatch.setattr("tutor.stream_chat", stream)
    monkeypatch.setattr("server.send_chat", chat)
    ada = log_in(with_users, "ada", "a password")
    model = {"model": "thinker", "url": "http://127.0.0.1:1"}
    body = {
        "chat": "chat-1",
        "messages": [{"role": "user", "content": "My exam is on 5 December."}],
        "model": model,
    }
    send(f"{with_users}/tutor/chat", "POST", ada, json.dumps(body).encode())

    _, closed, _ = send(
        f"{with_users}/tutor/chats/chat-1/close",
        "POST",
        ada,
        json.dumps({"model": model}).encode(),
    )
    refused, _, _ = send(
        f"{with_users}/tutor/chat", "POST", ada, json.dumps(body).encode()
    )
    _, memories, _ = send(f"{with_users}/tutor/memories", "GET", ada)

    assert [task["title"] for task in json.loads(closed)["tasks"]] == [
        "Memories of the chat",
        "Recap of the chat",
    ]
    assert refused == 400
    assert "Learner: My exam is on 5 December." in asked[0]["messages"][0]["content"]
    assert sorted(
        (each["kind"], each["content"]) for each in json.loads(memories)["memories"]
    ) == [("fact", "Has the B1 exam on 2026-12-05."), ("recap", RECAP)]


def test_the_tutor_is_told_its_memories_and_forgets_one_the_learner_deletes(
    with_users: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[dict[str, Any]] = []

    def stream(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        asked.append(body)
        yield {"choices": [{"delta": {"content": "Hi."}}]}

    def chat(body: dict[str, Any], model: Model) -> dict[str, Any]:
        if recapped := recapping(body):
            return recapped
        said = {"add": ["Likes football."], "remove": []}
        return {"choices": [{"message": {"content": json.dumps(said)}}]}

    monkeypatch.setattr("tutor.stream_chat", stream)
    monkeypatch.setattr("server.send_chat", chat)
    ada = log_in(with_users, "ada", "a password")
    model = {"model": "thinker", "url": "http://127.0.0.1:1"}

    def talk(chat_id: str) -> None:
        body = {
            "chat": chat_id,
            "messages": [{"role": "user", "content": "Hallo"}],
            "model": model,
        }
        send(f"{with_users}/tutor/chat", "POST", ada, json.dumps(body).encode())

    talk("chat-1")
    send(
        f"{with_users}/tutor/chats/chat-1/close",
        "POST",
        ada,
        json.dumps({"model": model}).encode(),
    )
    talk("chat-2")
    _, listed, _ = send(f"{with_users}/tutor/memories", "GET", ada)
    [memory] = [
        each for each in json.loads(listed)["memories"] if each["kind"] == "fact"
    ]
    deleted, _, _ = send(f"{with_users}/tutor/memories/{memory['id']}", "DELETE", ada)
    _, after, _ = send(f"{with_users}/tutor/memories", "GET", ada)

    assert "do not remember anything" in asked[0]["messages"][0]["content"]
    assert "Likes football." in asked[1]["messages"][0]["content"]
    # the recap is looked up, not told
    assert "Agreed to practise the dative." not in asked[1]["messages"][0]["content"]
    assert "1 in all" in asked[1]["messages"][0]["content"]
    assert {"recaps", "strategy", "calendar", "plan"} <= {
        tool["function"]["name"] for tool in asked[1]["tools"]
    }
    assert deleted == 200
    assert [each["kind"] for each in json.loads(after)["memories"]] == ["recap"]
    assert [each["removedBy"] for each in json.loads(after)["removed"]] == ["learner"]


def test_chats_closed_one_after_another_do_not_leave_the_same_memory_twice(
    with_users: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stream(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        yield {"choices": [{"delta": {"content": "Hi."}}]}

    def chat(body: dict[str, Any], model: Model) -> dict[str, Any]:
        if recapped := recapping(body):
            return recapped
        said = {"add": ["Likes football."], "remove": []}
        return {"choices": [{"message": {"content": json.dumps(said)}}]}

    monkeypatch.setattr("tutor.stream_chat", stream)
    monkeypatch.setattr("server.send_chat", chat)
    ada = log_in(with_users, "ada", "a password")
    model = {"model": "thinker", "url": "http://127.0.0.1:1"}
    for chat_id in ("chat-1", "chat-2"):
        body = {
            "chat": chat_id,
            "messages": [{"role": "user", "content": "I play football."}],
            "model": model,
        }
        send(f"{with_users}/tutor/chat", "POST", ada, json.dumps(body).encode())
    for chat_id in ("chat-1", "chat-2"):
        send(
            f"{with_users}/tutor/chats/{chat_id}/close",
            "POST",
            ada,
            json.dumps({"model": model}).encode(),
        )

    _, listed, _ = send(f"{with_users}/tutor/memories", "GET", ada)

    assert [each["content"] for each in json.loads(listed)["memories"]] == [
        "Likes football.",
        RECAP,
        RECAP,
    ]


def test_a_text_is_kept_listed_and_deleted_and_one_corrected_is_not_changed(
    with_users: str,
) -> None:
    ada = log_in(with_users, "ada", "a password")
    text = {"title": "Wochenende", "content": "Ich bin gegeht.", "language": "German"}

    kept, _, _ = send(f"{with_users}/texts/t1", "PUT", ada, json.dumps(text).encode())
    _, listed, _ = send(f"{with_users}/texts", "GET", ada)
    _, one, _ = send(f"{with_users}/texts/t1", "GET", ada)
    deleted, _, _ = send(f"{with_users}/texts/t1", "DELETE", ada)
    gone, _, _ = send(f"{with_users}/texts/t1", "GET", ada)

    assert kept == 200
    assert [(each["title"], each["words"]) for each in json.loads(listed)["texts"]] == [
        ("Wochenende", 3)
    ]
    assert json.loads(one)["content"] == "Ich bin gegeht."
    assert (deleted, gone) == (200, 404)


class NotesAnki(FakeAnki):
    """An Anki account whose decks hold the notes given."""

    def __init__(self, notes: list[str]) -> None:
        super().__init__()
        self.held = notes

    def notes(self, skipped: list[int] | None = None) -> list[str]:
        return self.held


def known_words_account(anki: AnkiLink | None = None) -> Account:
    """An account whose vocabulary has a noun used by the learner, a noun
    seen in a reply, a verb never used, and a set of the nouns."""
    vocabulary = Vocabulary()
    hund, _ = vocabulary.save("noun", "Hund", {}, [Form("Hunde")])
    katze, _ = vocabulary.save("noun", "Katze", {}, [])
    vocabulary.save("verb", "gehen", {}, [])
    vocabulary.record_uses("message", "c", 0, "user", 10.0, [(hund.id, "hund")])
    vocabulary.record_uses("message", "c", 1, "assistant", 20.0, [(katze.id, "katze")])
    vocabulary.save_set(
        "nouns",
        {"id": "nouns", "name": "Nouns", "rules": {"verb": {"included": False}}},
    )
    intake = Intake(vocabulary, FakeProfiler(), FakeChat())
    importer = AnkiImporter(intake, lambda: [])
    return Account(LiveChecker(Speller(language=None)), intake, importer, anki=anki)


def known(url: str, query: str = "") -> tuple[int, Any]:
    return ask(f"{url}/vocabulary/known?{query}", "GET")


def test_the_known_words_are_given_most_recently_used_first_by_default() -> None:
    with server_of(known_words_account()) as url:
        status, reply = known(url)

    assert status == 200
    assert [word["lemma"] for word in reply["words"]] == ["Katze", "Hund", "gehen"]
    assert reply["total"] == 3


def test_the_known_words_are_picked_by_category_order_and_limit() -> None:
    with server_of(known_words_account()) as url:
        _, by_user = known(
            url, "category=noun,verb&sorted_by=last_used_by_user&limit=2"
        )
        _, verbs = known(url, "category=verb")
        _, both = known(url, "category=verb&category=noun&sorted_by=alphabetical")

    assert [word["lemma"] for word in by_user["words"]] == ["Hund", "gehen"]
    assert by_user["total"] == 3
    assert [word["lemma"] for word in verbs["words"]] == ["gehen"]
    assert [word["lemma"] for word in both["words"]] == ["gehen", "Hund", "Katze"]


def test_the_known_words_of_a_set_are_those_its_rules_let_in() -> None:
    with server_of(known_words_account()) as url:
        _, nouns = known(url, "set=nouns&sorted_by=alphabetical")
        missing = known(url, "set=elsewhere")

    assert [word["lemma"] for word in nouns["words"]] == ["Hund", "Katze"]
    assert missing == (404, {"error": "no such set"})


def test_the_known_words_from_anki_are_those_a_note_holds_a_form_of() -> None:
    account = known_words_account(NotesAnki(["die Hunde", "gehen, laufen"]))

    with server_of(account) as url:
        _, reply = known(url, "anki_only=true&sorted_by=alphabetical")

    assert [word["lemma"] for word in reply["words"]] == ["gehen", "Hund"]


def test_the_known_words_from_anki_are_none_when_anki_is_of_another_language() -> None:
    account = known_words_account(NotesAnki(["Hund"]))

    with server_of(account) as url:
        _, reply = known(url, "anki_only=true&language=English")

    assert reply == {"words": [], "total": 0}


def test_the_known_words_from_anki_are_refused_without_anki() -> None:
    with server_of(known_words_account()) as url:
        status, _ = known(url, "anki_only=true")

    assert status == 404


def test_a_request_for_known_words_that_asks_what_there_is_not_is_refused() -> None:
    with server_of(known_words_account()) as url:
        category = known(url, "category=noun,colour")
        order = known(url, "sorted_by=loudest")
        limit = known(url, "limit=-1")
        flag = known(url, "reverse=perhaps")

    assert category == (400, {"error": "there is no category colour"})
    assert order[0] == limit[0] == flag[0] == 400
