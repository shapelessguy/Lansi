# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The prompts the server tells the models, kept in prompts/, where they
can be read and corrected without reading the code that sends them. Those
of an exercise are in the prompts.toml of its directory in exercises/,
read by exercises/kit.py.

Each kind of prompt is a Markdown file of prompts/: what it is for and what
its variables are first, then the prompt under a `## Prompt` heading,
exactly as the model is told it. A file of several variants of a prompt,
of which the code picks one, has each under a `## Prompt: name` heading.
A prompt is named by its path in prompts/, with dots for slashes, and the
name of its variant if it has one: `intake.judging` is
prompts/intake/judging.md, and `kit.topics.one` is the variant `one` of
prompts/kit/topics.md.

A prompt is filled in with the values the code gives it, each written in it
as `$name`, or `${name}` where a letter follows; `$$` is a dollar sign. A
value the prompt does not use is left out, so that a sentence can be taken
out of a prompt together with its variable; one the prompt uses that the
code does not give is an error.

A file is read when it is first used: the server is to be started again
after one is changed.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template

# the heading a prompt, or a variant of one, starts under
_HEADING = re.compile(r"^## Prompt(?:: (\S+))?[ \t]*$", re.MULTILINE)


class PromptError(Exception):
    """A prompt is not in its file, or cannot be filled in."""


def read_prompts(text: str) -> dict[str, str]:
    """The prompts of a file by their variants, "" for a file of one prompt,
    each without the blank lines around it."""
    headings = list(_HEADING.finditer(text))
    prompts = {}
    for number, heading in enumerate(headings):
        end = headings[number + 1].start() if number + 1 < len(headings) else len(text)
        prompts[heading.group(1) or ""] = text[heading.end() : end].strip("\r\n")
    return prompts


class Prompts:
    """The prompts of a directory, filled in by name."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._files: dict[Path, dict[str, str]] = {}

    def table(self, name: str) -> dict[str, str]:
        """The variants of the prompt of that name, by their names."""
        variants = self._file(self.directory.joinpath(*name.split(".")))
        if variants is None or "" in variants:
            raise PromptError(f"there are no variants of a prompt {name}")
        return variants

    def text(self, name: str) -> str:
        """The prompt of that name as it is written, not filled in."""
        parts = name.split(".")
        whole = self._file(self.directory.joinpath(*parts))
        if whole is not None and "" in whole:
            return whole[""]
        variants = self._file(self.directory.joinpath(*parts[:-1]))
        if variants is not None and parts[-1] in variants:
            return variants[parts[-1]]
        raise PromptError(f"there is no prompt {name} in {self.directory}")

    def __call__(self, name: str, /, **values: object) -> str:
        """The prompt of that name filled in with `values`."""
        return fill(self.text(name), name, values)

    def _file(self, path: Path) -> dict[str, str] | None:
        """The prompts of the file of that path, without its .md, or None if
        there is none."""
        path = path.with_name(path.name + ".md")
        if path not in self._files:
            if not path.is_file():
                return None
            self._files[path] = read_prompts(path.read_text(encoding="utf-8"))
        return self._files[path]


# the prompts of the server
PROMPTS = Prompts(Path(__file__).resolve().with_name("prompts"))


def fill(text: str, name: str, values: dict[str, object]) -> str:
    """`text` with each of its variables replaced by its value. `name` names
    the prompt in an error."""
    missing = variables_of(text) - set(values)
    if missing:
        listed = ", ".join(f"${each}" for each in sorted(missing))
        raise PromptError(f"{name} uses {listed}, which the code does not give")
    try:
        return Template(text).substitute(values)
    except ValueError as error:
        raise PromptError(f"{name}: {error}") from None


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
