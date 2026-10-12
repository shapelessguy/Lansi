# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tests for the chat-completions client."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from anki.httpclient import HttpClient
from aqt.llm import LlmError, LlmMessage, LlmReply, complete


class FakeResponse:
    def __init__(self, status_code: int, text: str, reason: str = "") -> None:
        self.status_code = status_code
        self.text = text
        self.reason = reason


class FakeClient:
    "Records the request and returns a canned response in place of the network."

    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.url = ""
        self.payload: dict[str, Any] = {}
        self.headers: dict[str, str] = {}

    def post(self, url: str, data: bytes, headers: dict[str, str]) -> FakeResponse:
        self.url = url
        self.payload = json.loads(data)
        self.headers = headers
        return self.response


def ask(client: FakeClient, temperature: float | None = None) -> LlmReply:
    return complete(
        api_endpoint="https://example.test/v1/chat/completions",
        api_token="secret",
        model_name="test-model",
        messages=[LlmMessage("system", "Be brief."), LlmMessage("user", "ping")],
        temperature=temperature,
        client=cast(HttpClient, client),
    )


def ok_response(body: dict[str, Any]) -> FakeClient:
    return FakeClient(FakeResponse(200, json.dumps(body)))


def test_complete_returns_reply_text_and_token_usage() -> None:
    client = ok_response(
        {
            "choices": [{"message": {"role": "assistant", "content": "pong"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        }
    )

    assert ask(client) == LlmReply(text="pong", prompt_tokens=12, completion_tokens=3)


def test_complete_sends_model_messages_and_bearer_token() -> None:
    client = ok_response({"choices": [{"message": {"content": "pong"}}]})

    ask(client)

    assert client.url == "https://example.test/v1/chat/completions"
    assert client.headers["Authorization"] == "Bearer secret"
    assert client.payload == {
        "model": "test-model",
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": "ping"},
        ],
    }


def test_complete_sends_temperature_only_when_given() -> None:
    client = ok_response({"choices": [{"message": {"content": "pong"}}]})

    ask(client, temperature=0.7)

    assert client.payload["temperature"] == 0.7


def test_complete_reports_zero_usage_when_provider_omits_it() -> None:
    client = ok_response({"choices": [{"message": {"content": "pong"}}]})

    reply = ask(client)

    assert (reply.prompt_tokens, reply.completion_tokens) == (0, 0)


def test_complete_raises_provider_error_message_on_http_error() -> None:
    body = json.dumps({"error": {"message": "Incorrect API key provided"}})
    client = FakeClient(FakeResponse(401, body, reason="Unauthorized"))

    with pytest.raises(LlmError, match="HTTP 401: Incorrect API key provided"):
        ask(client)


def test_complete_falls_back_to_http_reason_when_error_body_is_not_json() -> None:
    client = FakeClient(FakeResponse(502, "<html>oops</html>", reason="Bad Gateway"))

    with pytest.raises(LlmError, match="HTTP 502: Bad Gateway"):
        ask(client)


@pytest.mark.parametrize("body", ['{"choices": []}', "{}", "not json"])
def test_complete_raises_when_response_has_no_reply(body: str) -> None:
    client = FakeClient(FakeResponse(200, body))

    with pytest.raises(LlmError, match="no choices"):
        ask(client)
