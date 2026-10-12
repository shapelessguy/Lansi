# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest
from live import LiveChecker
from profiling import Answer, Profile, Profiler
from sentences import Sentence
from server import describe, make_server
from spelling import Speller, SpellingIssue


@pytest.fixture
def url() -> Iterator[str]:
    """A checker server on a free port, stopped after the test."""
    words = ["schön", "wie", "geht", "hund"]
    checker = LiveChecker(
        Speller(language=None, words=words),
        KeyEchoingProfiler(),
        background=lambda job: job(),
    )
    server = make_server(0, checker)
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
    """Answers with the key and model it was given, in place of asking Jev."""

    def __init__(self) -> None:
        pass

    def profile(self, sentence: str, api_key: str, model: str | None = None) -> Profile:
        return Profile(
            {"key_used": Answer("choice", choice=api_key)}, model=model or "usual"
        )


def post(url: str, body: bytes, key: str | None = None) -> tuple[int, object]:
    headers = {"X-OpenRouter-Key": key} if key else {}
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


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

    status, sentences = post(f"{url}/sentences", body)

    assert status == 200
    assert sentences == [
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

    _, without_key = post(f"{url}/sentences", body)
    post(f"{url}/sentences", body, key="from-the-chat")
    _, after = post(f"{url}/sentences", body, key="from-the-chat")

    assert without_key[0]["profiling"] is False  # type: ignore[index]
    assert after[0]["processed"] is True  # type: ignore[index]
    assert after[0]["profile"]["answers"]["key_used"]["choice"] == "from-the-chat"  # type: ignore[index]


def test_sentences_request_profiles_with_the_model_it_names(url: str) -> None:
    body = json.dumps({"text": "Wie geht Hund.", "model": "some/model"}).encode()

    post(f"{url}/sentences", body, key="a-key")
    _, after = post(f"{url}/sentences", body, key="a-key")

    assert after[0]["profile"]["model"] == "some/model"  # type: ignore[index]


def test_sentences_request_without_a_model_profiles_with_the_usual_one(
    url: str,
) -> None:
    body = json.dumps({"text": "Wie geht Hund.", "model": ""}).encode()

    post(f"{url}/sentences", body, key="a-key")
    _, after = post(f"{url}/sentences", body, key="a-key")

    assert after[0]["profile"]["model"] == "usual"  # type: ignore[index]


def test_sentences_request_falls_back_to_the_key_set_where_the_server_runs(
    url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-the-environment")
    body = json.dumps({"text": "Wie geht Hund."}).encode()

    post(f"{url}/sentences", body)
    _, after = post(f"{url}/sentences", body)

    assert after[0]["profile"]["answers"]["key_used"]["choice"] == (  # type: ignore[index]
        "from-the-environment"
    )


def test_sentences_request_with_a_caret_reopens_the_sentence_it_is_in(
    url: str,
) -> None:
    text = "Wie geht Hund. Schön geht Hund."

    _, without = post(f"{url}/sentences", json.dumps({"text": text}).encode())
    _, with_null = post(
        f"{url}/sentences", json.dumps({"text": text, "caret": None}).encode()
    )
    _, inside = post(
        f"{url}/sentences", json.dumps({"text": text, "caret": 4}).encode()
    )

    assert [s["complete"] for s in without] == [True, True]  # type: ignore[attr-defined]
    assert with_null == without
    assert [s["complete"] for s in inside] == [False, True]  # type: ignore[attr-defined]


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
