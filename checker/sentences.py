# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Splits text into the sentences it is made of."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field

from languages import languages_of_their_own
from profiling import Profile, WordRating
from spelling import SpellingIssue

_LINE = re.compile(r"[^\r\n]+")

# One or more sentence-ending marks, so that "?!" and "..." stay in one piece,
# followed by any quotes or brackets that close what was just said.
_SENTENCE_END = re.compile(r"[.!?…]+[\"'“”‘’«»)\]]*")

# Words that are written with a full stop but do not end a sentence, those
# of every language that has rules of its own. Compared without the final
# full stop, in lower case.
ABBREVIATIONS = frozenset(
    word for language in languages_of_their_own() for word in language.abbreviations
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
    # How right each word is where it stands, once the words have been rated,
    # which is done after the sentence has been profiled.
    words: list[WordRating] = field(default_factory=list)
    # True while the words are being rated.
    rating_words: bool = False
    # The sentence as it should be, once a model has written it, which is
    # asked alongside the profile when correcting is asked for.
    correction: str | None = None
    # The correction in the language the learner reads, if the model said.
    correction_translation: str | None = None
    # True while the correction is being written.
    correcting: bool = False
    # Why the correction could not be had, if it could not.
    correction_error: str | None = None


def split_sentences(text: str, caret: int | None = None) -> list[Sentence]:
    """Return the sentences in `text`, in order.

    A sentence ends at `.`, `!`, `?`, `…`, a run of them such as `...` or
    `?!`, or at the end of a line.

    `caret` is where in `text` the writer's caret is, or None if the writer
    is not in the text. A sentence is complete unless the caret is on it,
    which includes the caret being right at its start. A sentence without an
    ending mark also has the caret on it right after its last character, and
    after the spaces that follow; one with an ending mark is left as soon as
    the caret is behind the mark. Without a caret, every sentence is complete.
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
    # An ending mark closes the sentence, so a caret right behind the mark has
    # left it. To be back on it, the caret has to be before the mark.
    reach = stripped_end - 1 if ended else end
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
