# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""
Client for endpoints speaking the OpenAI chat-completions schema (OpenAI, Groq,
OpenRouter, a local Ollama/LM Studio server, etc).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from anki.httpclient import HttpClient

# replies from larger models can take a while to arrive
REQUEST_TIMEOUT_SECS = 120


class LlmError(Exception):
    pass


@dataclass
class LlmMessage:
    # "system", "user" or "assistant"
    role: str
    content: str


@dataclass
class LlmReply:
    text: str
    prompt_tokens: int
    completion_tokens: int


def complete(
    api_endpoint: str,
    api_token: str,
    model_name: str,
    messages: list[LlmMessage],
    temperature: float | None = None,
    client: HttpClient | None = None,
) -> LlmReply:
    "Send the conversation to the endpoint, and return the assistant's reply."
    payload: dict[str, object] = {
        "model": model_name,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
    }
    if temperature is not None:
        payload["temperature"] = temperature

    owns_client = client is None
    if client is None:
        client = HttpClient()
        client.timeout = REQUEST_TIMEOUT_SECS
    try:
        resp = client.post(
            api_endpoint,
            json.dumps(payload).encode("utf8"),
            {
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
        )
        status, reason, body = resp.status_code, resp.reason, resp.text
    finally:
        if owns_client:
            client.close()

    if not 200 <= status < 300:
        raise LlmError(f"HTTP {status}: {_error_detail(body) or reason}")
    return _parse_reply(body)


def _error_detail(body: str) -> str | None:
    try:
        message = json.loads(body)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return None
    return message if isinstance(message, str) else None


def _parse_reply(body: str) -> LlmReply:
    try:
        parsed = json.loads(body)
        text = parsed["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LlmError("LLM response had no choices") from None
    if not isinstance(text, str):
        raise LlmError("LLM response had no choices")
    usage = parsed.get("usage") or {}
    return LlmReply(
        text=text,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )
