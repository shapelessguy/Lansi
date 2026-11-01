# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Finds misspelled words with a dictionary-based spell checker.

Whether a word is right is decided by the Hunspell dictionary of the
language (`Language.hunspell`) where the system has it and the Hunspell
library, as a Linux system has them from its packages, such as
hunspell-de-de: it knows how the words are inflected and put together, as
German puts nouns into compounds. Otherwise it is decided by
pyspellchecker's list of words. The words a wrong one may have been meant
as come from that list, the most common first, as Hunspell does not rank
its own suggestions by how common they are."""

from __future__ import annotations

import ctypes
import ctypes.util
import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from languages import language_of
from spellchecker import SpellChecker

# Letters of any alphabet, with apostrophes allowed inside: "geht's".
_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
MAX_SUGGESTIONS = 3
# where a Linux system keeps its Hunspell dictionaries
HUNSPELL_DIRECTORIES = (
    Path("/usr/share/hunspell"),
    Path("/usr/share/myspell"),
    Path("/usr/share/myspell/dicts"),
)


class Hunspell:
    """A Hunspell dictionary, asked through the system's Hunspell library."""

    def __init__(self, path: Path, library: ctypes.CDLL) -> None:
        """`path` is that of the .aff and .dic files, without the suffix."""
        library.Hunspell_create.restype = ctypes.c_void_p
        library.Hunspell_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        library.Hunspell_spell.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        library.Hunspell_get_dic_encoding.restype = ctypes.c_char_p
        library.Hunspell_get_dic_encoding.argtypes = [ctypes.c_void_p]
        library.Hunspell_destroy.argtypes = [ctypes.c_void_p]
        self._library = library
        self._handle = library.Hunspell_create(
            bytes(path.with_suffix(".aff")), bytes(path.with_suffix(".dic"))
        )
        named = library.Hunspell_get_dic_encoding(self._handle) or b"UTF-8"
        self._encoding = named.decode("ascii")
        # a Hunspell is not to be asked by two threads at once
        self._lock = threading.Lock()

    def __del__(self) -> None:
        if getattr(self, "_handle", None):
            self._library.Hunspell_destroy(self._handle)

    def lookup(self, word: str) -> bool:
        """Whether the word is right as it is written."""
        try:
            encoded = word.encode(self._encoding)
        except (UnicodeEncodeError, LookupError):
            # letters the dictionary cannot even write make no word of it
            return False
        with self._lock:
            return bool(self._library.Hunspell_spell(self._handle, encoded))


def hunspell_of(name: str | None) -> Hunspell | None:
    """The Hunspell dictionary of that name, such as "de_DE", if the system
    has it and the library to ask it with."""
    library = _hunspell_library()
    if not name or library is None:
        return None
    for directory in HUNSPELL_DIRECTORIES:
        path = directory / name
        if path.with_suffix(".aff").is_file() and path.with_suffix(".dic").is_file():
            return Hunspell(path, library)
    return None


@lru_cache
def _hunspell_library() -> ctypes.CDLL | None:
    found = ctypes.util.find_library("hunspell-1.7") or ctypes.util.find_library(
        "hunspell"
    )
    try:
        return ctypes.CDLL(found) if found else None
    except OSError:
        return None


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

    def __init__(
        self,
        language: str | None = "de",
        words: Iterable[str] = (),
        hunspell: Hunspell | None = None,
    ) -> None:
        """`language` is one that pyspellchecker has a dictionary for, or None
        to start with an empty one. `words` are added to the dictionary.
        `hunspell`, if there is one, decides which words are right in place
        of pyspellchecker's."""
        self._spell = SpellChecker(language=language)
        self._spell.word_frequency.load_words(words)
        self._added = frozenset(word.lower() for word in words)
        self._hunspell = hunspell
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

    def knows(self, word: str) -> bool:
        """Whether the word is in the dictionary as it is."""
        if self._hunspell:
            return word.lower() in self._added or self._hunspell.lookup(word)
        return bool(self._spell.known([word]))

    def _look_up(self, word: str) -> tuple[str, ...] | None:
        """None if `word` is spelled correctly, otherwise the suggestions."""
        if self._is_accepted(word):
            return None
        # when nothing is close, or the word is in the list as it is, the
        # word itself comes back, which may yet be meant with a capital
        candidates = self._spell.candidates(word) or set()
        # most common first; the alphabet settles ties so the order is stable
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                -self._spell.word_usage_frequency(candidate),
                candidate,
            ),
        )
        suggestions: list[str] = []
        for candidate in ranked:
            written = self._as_written(word, candidate)
            if written and written != word and written not in suggestions:
                suggestions.append(written)
            if len(suggestions) == MAX_SUGGESTIONS:
                break
        return tuple(suggestions)

    def _as_written(self, word: str, candidate: str) -> str | None:
        """A candidate of the list, which is in small letters, as it is
        written in place of `word`: with the capital of `word`, or else,
        by the Hunspell dictionary, with the capital it needs, as the noun
        "Hund" does for "hund". None if the dictionary has it neither way."""
        written = _with_capital_of(word, candidate)
        if not self._hunspell or self._hunspell.lookup(written):
            return written
        capitalised = candidate.capitalize()
        return capitalised if self._hunspell.lookup(capitalised) else None

    def _is_accepted(self, word: str) -> bool:
        # single letters and abbreviations such as "USA" are left alone
        if len(word) == 1 or word.isupper():
            return True
        if self.knows(word):
            return True
        # "geht's" is fine if "geht" is
        head = re.split("['’]", word)[0]
        return head != word and self.knows(head)


def _with_capital_of(word: str, suggestion: str) -> str:
    """The dictionary is in lower case, so a suggestion for a capitalised word,
    such as a noun of a language that writes nouns so, is given its capital
    back."""
    return suggestion.capitalize() if word[0].isupper() else suggestion


# The languages there is a dictionary for, by their names in small letters.
DICTIONARIES = {
    "arabic": "ar",
    "basque": "eu",
    "dutch": "nl",
    "english": "en",
    "french": "fr",
    "german": "de",
    "italian": "it",
    "latvian": "lv",
    "persian": "fa",
    "portuguese": "pt",
    "russian": "ru",
    "spanish": "es",
}


class StudySpeller(Speller):
    """Checks words against the dictionary of the language being studied,
    which may be changed at any time, or of the language a text is written
    in, among others it is told of. A language there is no dictionary for
    has no word found wrong, and none known."""

    def __init__(self, language: str) -> None:
        # the language, by its English name
        self.language = language
        self._spellers: dict[str, Speller | None] = {}
        self._lock = threading.Lock()

    def _speller(self, language: str = "") -> Speller | None:
        name = (language or self.language).strip().lower()
        with self._lock:
            if name not in self._spellers:
                code = DICTIONARIES.get(name)
                hunspell = hunspell_of(language_of(name).hunspell)
                self._spellers[name] = (
                    Speller(code, hunspell=hunspell) if code or hunspell else None
                )
            return self._spellers[name]

    def check(self, text: str) -> list[SpellingIssue]:
        speller = self._speller()
        return speller.check(text) if speller else []

    def check_written(
        self, text: str, among: Iterable[str] = ()
    ) -> tuple[str, list[SpellingIssue]]:
        """The language `text` is written in, of the one studied and those
        `among`, with the words its dictionary finds wrong in it: the one
        whose dictionary finds the fewest wrong, the one studied where
        several find as few. A language there is no dictionary for is not
        one a text is found to be written in, unless none has one."""
        found: tuple[str, list[SpellingIssue]] | None = None
        for language in dict.fromkeys([self.language, *among]):
            speller = self._speller(language) if language.strip() else None
            if speller is None:
                continue
            issues = speller.check(text)
            if found is None or len(issues) < len(found[1]):
                found = (language, issues)
        return found or (self.language, [])

    def knows(self, word: str) -> bool:
        speller = self._speller()
        return speller.knows(word) if speller else False
