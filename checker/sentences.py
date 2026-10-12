# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Splits text into the sentences it is made of."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from profiling import Profile
from spelling import SpellingIssue

_LINE = re.compile(r"[^\r\n]+")

# One or more sentence-ending marks, so that "?!" and "..." stay in one piece,
# followed by any quotes or brackets that close what was just said.
_SENTENCE_END = re.compile(r"[.!?…]+[\"'“”‘’«»)\]]*")

# Words that are written with a full stop but do not end a sentence. Compared
# without the final full stop, in lower case.
ABBREVIATIONS = frozenset(
    {
        # German
        "bzw",
        "ca",
        "d.h",
        "evtl",
        "ggf",
        "inkl",
        "nr",
        "s.o",
        "s.u",
        "u.a",
        "vgl",
        "z.b",
        # English
        "e.g",
        "i.e",
        "mr",
        "mrs",
        "ms",
        "vs",
        # both
        "dr",
        "prof",
        "st",
    }
)


@dataclass
class Sentence:
    """One sentence of a text."""

    # The sentence with its punctuation, without the space around it.
    text: str
    # Where it is in the text it came from: text[start:end] is the sentence.
    start: int
    end: int
    # False while the writer's caret is on the sentence, which is when it is
    # being written or changed.
    complete: bool
    # What the spell checker found in it.
    spelling: list[SpellingIssue] = field(default_factory=list)
    # Whether the sentence, as it is now, has been profiled.
    processed: bool = False
    # The answers to the questions asked about it, once it has been profiled.
    profile: Profile | None = None
    # True while the profile is being made.
    profiling: bool = False
    # Why the profile could not be made, if it could not.
    profile_error: str | None = None


def split_sentences(text: str, caret: int | None = None) -> list[Sentence]:
    """Return the sentences in `text`, in order.

    A sentence ends at `.`, `!`, `?`, `…`, a run of them such as `...` or
    `?!`, or at the end of a line.

    `caret` is where in `text` the writer's caret is, or None if the writer
    is not in the text. A sentence is complete unless the caret is on it,
    which includes the caret being right at its start or right after its last
    character. Without a caret, every sentence is complete.
    """
    sentences: list[Sentence] = []
    for line in _LINE.finditer(text):
        start = line.start()
        for marks in _SENTENCE_END.finditer(text, line.start(), line.end()):
            if _ends_sentence(text, line, marks):
                _add(sentences, text, start, marks.end(), caret, ended=True)
                start = marks.end()
        _add(sentences, text, start, line.end(), caret, ended=False)
    return sentences


def _add(
    sentences: list[Sentence],
    text: str,
    start: int,
    end: int,
    caret: int | None,
    ended: bool,
) -> None:
    """Add text[start:end] as a sentence, unless it is only space. `ended`
    says whether it closes with an ending mark."""
    piece = text[start:end]
    stripped = piece.strip()
    if not stripped:
        return
    start += len(piece) - len(piece.lstrip())
    stripped_end = start + len(stripped)
    # Spaces typed after a sentence that has no ending mark yet are part of
    # writing it: the next word is about to follow. After an ending mark they
    # belong to whatever comes next.
    reach = stripped_end if ended else end
    on_it = caret is not None and start <= caret <= reach
    sentences.append(Sentence(stripped, start, stripped_end, complete=not on_it))


def _ends_sentence(text: str, line: re.Match[str], marks: re.Match[str]) -> bool:
    """Whether the marks found really end a sentence, rather than being part
    of a number, an address or an abbreviation."""
    followed_by_space = marks.end() == line.end() or text[marks.end()].isspace()
    if not followed_by_space:
        # "3.5", "example.com", "z.B."
        return False
    if marks.group() != ".":
        return True
    before = text[line.start() : marks.start()].split()
    word = before[-1].lower() if before else ""
    is_single_letter = len(word) == 1 and word.isalpha()
    # "am 3. Oktober"
    is_ordinal = word.isdigit()
    return not (word in ABBREVIATIONS or is_single_letter or is_ordinal)


if __name__ == "__main__":
    # Try it: pass the text as arguments, or pipe it in.
    typed = " ".join(sys.argv[1:]) or sys.stdin.read()
    for sentence in split_sentences(typed):
        print(sentence)
