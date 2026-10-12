# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Finds misspelled words with a dictionary-based spell checker."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from spellchecker import SpellChecker

# Letters of any alphabet, with apostrophes allowed inside: "geht's".
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
MAX_SUGGESTIONS = 3


@dataclass
class SpellingIssue:
    """A word the spell checker does not know."""

    word: str
    # Where the word is in the sentence: sentence.text[start:end] is the word.
    start: int
    end: int
    # The most common words that are close to it, best first. May be empty.
    suggestions: list[str]


class Speller:
    """Checks words against the dictionary of one language."""

    def __init__(self, language: str | None = "de", words: Iterable[str] = ()) -> None:
        """`language` is one that pyspellchecker has a dictionary for, or None
        to start with an empty one. `words` are added to the dictionary."""
        self._spell = SpellChecker(language=language)
        self._spell.word_frequency.load_words(words)
        # The same words are checked again every second while a text is being
        # typed, and finding suggestions is the slow part.
        self._suggestions_for = lru_cache(maxsize=20_000)(self._look_up)

    def check(self, text: str) -> list[SpellingIssue]:
        """Return the misspelled words in `text`, in order."""
        issues = []
        for match in _WORD.finditer(text):
            suggestions = self._suggestions_for(match.group())
            if suggestions is not None:
                issues.append(
                    SpellingIssue(
                        match.group(), match.start(), match.end(), list(suggestions)
                    )
                )
        return issues

    def _look_up(self, word: str) -> tuple[str, ...] | None:
        """None if `word` is spelled correctly, otherwise the suggestions."""
        if self._is_accepted(word):
            return None
        # when nothing is close, the word itself comes back
        candidates = (self._spell.candidates(word) or set()) - {word, word.lower()}
        # most common first; the alphabet settles ties so the order is stable
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                -self._spell.word_usage_frequency(candidate),
                candidate,
            ),
        )
        return tuple(
            _with_capital_of(word, candidate) for candidate in ranked[:MAX_SUGGESTIONS]
        )

    def _is_accepted(self, word: str) -> bool:
        # single letters and abbreviations such as "USA" are left alone
        if len(word) == 1 or word.isupper():
            return True
        if self._spell.known([word]):
            return True
        # "geht's" is fine if "geht" is
        head = re.split("['’]", word)[0]
        return head != word and bool(self._spell.known([head]))


def _with_capital_of(word: str, suggestion: str) -> str:
    """The dictionary is in lower case, so a suggestion for a capitalised word,
    such as a German noun, is given its capital back."""
    return suggestion.capitalize() if word[0].isupper() else suggestion
