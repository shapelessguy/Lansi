# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The people who use the app, and who each have data of their own.

Who may log in is written in a file that is edited by hand: an object with a
password for each name, such as `{"ada": "her password"}`. The file is read
every time someone logs in, so a change to it needs no restart. It holds the
passwords as they are, and so is not to be shared.

A user who logs in is given a token, which comes back with every request and
says who is asking. A token is the name and the time it runs out, signed
with a secret that is made the first time and kept with the data, so that
tokens stay good when the server is started again.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from collections.abc import Callable
from pathlib import Path

# how long a token is good for
TOKEN_SECS = 30 * 24 * 60 * 60
# A name is also the name of the directory the user's data is kept in.
_NAME = re.compile(r"[a-z0-9_]{1,40}")


def is_name(name: str) -> bool:
    return bool(_NAME.fullmatch(name))


def user_directory(data: Path, name: str) -> Path:
    """Where everything a user has is kept."""
    return data / "users" / name


def take_vocabulary(data: Path, name: str) -> list[str]:
    """Move the vocabularies kept before there were users to a user, and
    return the names of the files that were moved. One the user has already
    is left where it is."""
    target = user_directory(data, name)
    target.mkdir(parents=True, exist_ok=True)
    moved = []
    for file in sorted(data.glob("vocabulary*.db")):
        if not (target / file.name).exists():
            file.rename(target / file.name)
            moved.append(file.name)
    return moved


class Users:
    def __init__(
        self,
        file: str | Path,
        secret_directory: str | Path,
        now: Callable[[], float] = time.time,
    ) -> None:
        # the file that says who may log in, and with which password
        self.file = Path(file)
        self._secret_file = Path(secret_directory) / "secret.key"
        self._now = now
        self._lock = threading.Lock()

    def names(self) -> list[str]:
        return sorted(self._read())

    def check(self, name: str, password: str) -> bool:
        """Whether there is such a user with this password."""
        expected = self._read().get(name)
        if expected is None:
            return False
        return hmac.compare_digest(password.encode(), expected.encode())

    def token(self, name: str) -> str:
        """A token that says the request it comes with is from `name`."""
        expires = int(self._now()) + TOKEN_SECS
        return f"{name}.{expires}.{self._sign(name, expires)}"

    def user_of(self, token: str) -> str | None:
        """The user a token was given to, if it is a token of this server,
        has not run out, and the user is still in the file."""
        name, _, rest = token.partition(".")
        expires, _, signature = rest.partition(".")
        if not expires.isdigit() or int(expires) < self._now():
            return None
        if not hmac.compare_digest(signature, self._sign(name, int(expires))):
            return None
        return name if name in self._read() else None

    def _sign(self, name: str, expires: int) -> str:
        message = f"{name}.{expires}".encode()
        return hmac.new(self._secret(), message, hashlib.sha256).hexdigest()

    def _secret(self) -> bytes:
        with self._lock:
            if not self._secret_file.exists():
                self._secret_file.parent.mkdir(parents=True, exist_ok=True)
                self._secret_file.write_bytes(secrets.token_bytes(32))
            return self._secret_file.read_bytes()

    def _read(self) -> dict[str, str]:
        """The password of each user. A name that could not be a directory,
        or a password that is empty or not text, is passed over."""
        try:
            users = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(users, dict):
            return {}
        return {
            name: password
            for name, password in users.items()
            if is_name(name) and isinstance(password, str) and password
        }
