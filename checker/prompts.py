# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The prompts the models are told, kept in TOML files, where they can be
read and corrected without reading the code that sends them.

What the server tells the models is in `prompts.toml` here: the
vocabulary, the translations, the logs, the categories of words, and the
pieces of the prompts of the exercises that every exercise uses. What an
exercise tells them is in the `prompts.toml` of its own directory, read by
exercises/kit.py in the same way, as an exercise is run with nothing of the
server's.

A prompt is a string of a file, found by its dotted name, such as
`intake.judging`. A table of strings is the variants of one, of which the
code picks one, such as `kit.topics.one` and `kit.topics.several`. A
prompt is filled in with the values the code gives it, each written in it
as `$name`, or `${name}` where a letter follows; `$$` is a dollar sign. A
value the prompt does not use is left out, so that a sentence can be taken
out of a prompt together with its variable; one the prompt uses that the
code does not give is an error.

A file is read when it is first used: the server is to be started again
after `prompts.toml` is changed. An exercise reads its own each time it is
run.
"""

from __future__ import annotations

import sys
from pathlib import Path
from string import Template
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class PromptError(Exception):
    """A prompt is not in its file, or cannot be filled in."""


class Prompts:
    """The prompts of a file, filled in by name."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._table: dict[str, Any] | None = None

    def table(self, name: str = "") -> dict[str, Any]:
        """The table of that name, of prompts or of tables of them; the whole
        file without a name."""
        found = self._find(name) if name else self._read()
        if not isinstance(found, dict):
            raise PromptError(f"{name} of {self.path} is not a table")
        return found

    def text(self, name: str) -> str:
        """The prompt of that name as it is written, not filled in."""
        found = self._find(name)
        if not isinstance(found, str):
            raise PromptError(f"{name} of {self.path} is not a prompt")
        return found

    def __call__(self, name: str, /, **values: object) -> str:
        """The prompt of that name filled in with `values`."""
        return fill(self.text(name), f"{name} of {self.path}", values)

    def _read(self) -> dict[str, Any]:
        if self._table is None:
            with self.path.open("rb") as file:
                self._table = tomllib.load(file)
        return self._table

    def _find(self, name: str) -> Any:
        found: Any = self._read()
        for part in name.split("."):
            if not isinstance(found, dict) or part not in found:
                raise PromptError(f"{self.path} has no prompt {name}")
            found = found[part]
        return found


# the prompts of the server
PROMPTS = Prompts(Path(__file__).resolve().with_name("prompts.toml"))


def fill(text: str, where: str, values: dict[str, object]) -> str:
    """`text` with each of its variables replaced by its value. `where`
    names the prompt in an error."""
    missing = variables_of(text) - set(values)
    if missing:
        listed = ", ".join(f"${name}" for name in sorted(missing))
        raise PromptError(f"{where} uses {listed}, which the code does not give")
    try:
        return Template(text).substitute(values)
    except ValueError as error:
        raise PromptError(f"{where}: {error}") from None


def variables_of(text: str) -> set[str]:
    """The names of the variables a prompt uses. Raises PromptError if it
    has a $ that is neither a variable nor $$."""
    names = set()
    for match in Template.pattern.finditer(text):
        if match.group("invalid") is not None:
            raise PromptError(
                f"a $ that starts no variable, at {text[match.start() : match.start() + 20]!r}"
            )
        name = match.group("named") or match.group("braced")
        if name:
            names.add(name)
    return names


def every_prompt(table: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Every prompt of a table and of the tables in it, by its dotted name."""
    found = {}
    for key, value in table.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            found.update(every_prompt(value, f"{name}."))
        elif isinstance(value, str):
            found[name] = value
    return found
