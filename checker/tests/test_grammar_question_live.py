# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Asks the real decision model the grammar question about sentences whose
errors are known, to see whether the question as it is worded catches them.
Each sentence is a request billed on OpenRouter, so these run only when
CHECKER_LIVE_TESTS is set, with a key in OPENROUTER_API_KEY: `just test-live`.
The model asked is the usual one, or the one CHECKER_LIVE_MODEL names, so
that models can be compared: `just test-live typesafe/jev-1.14`.
"""

from __future__ import annotations

import os

import pytest
from models import Model
from profiling import QUESTIONS, Profiler

KEY = os.environ.get("OPENROUTER_API_KEY", "")
# blank for the usual one
MODEL = os.environ.get("CHECKER_LIVE_MODEL", "")

pytestmark = pytest.mark.skipif(
    not (os.environ.get("CHECKER_LIVE_TESTS") and KEY),
    reason="asks a billed model: set CHECKER_LIVE_TESTS and OPENROUTER_API_KEY",
)

# sentences, the language they are judged by and how many grammar errors
# they have
CASES = [
    # right
    ("Ich habe einen Hund.", "German", "none"),
    ("Der Mann gibt dem Kind einen Apfel.", "German", "none"),
    # the case of an article
    ("Ich habe ein Hund.", "German", "one"),
    ("Ich sehe der Mann.", "German", "one"),
    ("Ich spiele mit den Kind.", "German", "one"),
    # the form of a verb, and the word order
    ("Du habe einen Hund.", "German", "one"),
    ("Gestern ich habe einen Hund gesehen.", "German", "one"),
    ("Gestern ich sehe der Mann mit den Kind.", "German", "several"),
    # misspelled words alone, which the question is not to count
    ("Ich habe einen Hnud.", "German", "none"),
    ("Ich wohne in einem grossen Hauss.", "German", "none"),
    ("Ich habe ein Hnud.", "German", "one"),
]


@pytest.mark.parametrize(("sentence", "language", "expected"), CASES)
def test_the_grammar_question_counts_the_errors_of_grammar_and_not_of_spelling(
    sentence: str, language: str, expected: str
) -> None:
    profiler = Profiler()
    profiler.language = language
    questions = {"grammar_errors": QUESTIONS["grammar_errors"]}

    profile = profiler.profile(sentence, Model(MODEL, key=KEY), questions)

    assert profile.answers["grammar_errors"].choice == expected
