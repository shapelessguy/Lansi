# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The models the server asks, and where each is asked.

Every model is asked the same way: on OpenRouter, with the learner's key,
or at the address of a server of the learner's own that takes the requests
OpenAI's API takes, such as one running on this machine. Each kind of
request goes to a path of its own under the address: `chat/completions`,
`embeddings`, `images`, `audio/speech`, and `decisions` for a decision model.

A request names a model by its id on OpenRouter, or as `{"model": ...,
"url": ..., "key": ...}` for one at an address of its own, whose key may
be left out.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

OPENROUTER_URL = "https://openrouter.ai/api/v1"
# OpenRouter's decision models are asked apart from its others
OPENROUTER_DECISIONS = "https://openrouter.ai/api/alpha/decisions"
# more than an id or an address is ever long
MAX_LENGTH = 500


@dataclass(frozen=True)
class Model:
    """A model, and where it is asked."""

    # its id where it is asked; blank where the usual one is to be used
    name: str = ""
    # where the paths of the requests go, such as http://127.0.0.1:8000/v1;
    # blank for OpenRouter
    url: str = ""
    # the key the requests go with: the learner's OpenRouter key, or one of
    # the server at `url`, which may need none
    key: str = ""

    @property
    def on_openrouter(self) -> bool:
        return not self.url

    @property
    def where(self) -> str:
        """Where it is asked, as a message says it."""
        return "OpenRouter" if self.on_openrouter else self.url

    def endpoint(self, path: str) -> str:
        """Where a request of the kind `path` names goes."""
        if self.on_openrouter and path == "decisions":
            return OPENROUTER_DECISIONS
        return f"{(self.url or OPENROUTER_URL).rstrip('/')}/{path}"

    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}"} if self.key else {}

    def or_named(self, name: str) -> Model:
        """This, with `name` as its id if it has none."""
        return self if self.name else replace(self, name=name)

    def or_keyed(self, key: str) -> Model:
        """This, with `key` as its key if it is asked on OpenRouter and has
        none."""
        return replace(self, key=key) if self.on_openrouter and not self.key else self

    @property
    def has_key(self) -> bool:
        """Whether it has what it is asked with: a key, on OpenRouter."""
        return bool(self.key) or not self.on_openrouter

    def problem(self) -> str | None:
        """Why it cannot be asked, or None if it can."""
        if not self.name:
            return "no model was named"
        if not self.has_key:
            return "an OpenRouter key is needed"
        return None


def read_model(value: object, openrouter_key: str = "") -> Model:
    """A model as a request names it, `openrouter_key` being the key it is
    asked with on OpenRouter. Nothing named is a model with no id, for the
    usual one to be used. Raises ValueError."""
    if value is None or value == "":
        return Model(key=openrouter_key)
    if isinstance(value, str):
        return Model(value.strip()[:MAX_LENGTH], key=openrouter_key)
    if isinstance(value, dict):
        name, url, key = value.get("model"), value.get("url", ""), value.get("key", "")
        if not all(isinstance(each, str) for each in (name, url, key)):
            raise ValueError(
                'a model is named as {"model": ..., "url": ..., "key": ...}'
            )
        assert isinstance(name, str) and isinstance(url, str) and isinstance(key, str)
        url = url.strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            raise ValueError(f"{url} is not the address of a server")
        return Model(
            name.strip()[:MAX_LENGTH],
            url[:MAX_LENGTH],
            key.strip() if url else openrouter_key,
        )
    raise ValueError("a model is named by its id, or with its address")
