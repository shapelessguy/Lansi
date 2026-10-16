# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from logs import LogError
from lookups import (
    MAX_POINTS,
    asked_anything,
    read_question_logs,
    sentence_of,
    translation_log,
    write_question_logs,
)
from profiling import Profile
from translating import Passage

PASSAGE = Passage("Es regnet. Ich bin ", "gerade", " nach Hause gekommen.")


def test_the_sentence_of_a_translation_starts_after_the_one_before_it() -> None:
    assert sentence_of(PASSAGE) == "Ich bin [[gerade]] nach Hause gekommen."


def test_the_sentence_of_a_translation_is_the_whole_passage_when_it_is_the_first() -> (
    None
):
    passage = Passage("Ich bin ", "gerade", " da.")

    assert sentence_of(passage) == "Ich bin [[gerade]] da."


def test_a_translation_is_logged_with_its_sentence_and_what_it_was_translated_as() -> (
    None
):
    subject, content = translation_log(PASSAGE, " just ")

    assert subject == "gerade"
    assert content == (
        'Asked for "gerade" to be translated, in:'
        ' "Ich bin [[gerade]] nach Hause gekommen.".\n'
        'Translated as: "just".'
    )


def test_a_chat_is_logged_only_when_the_learner_asked_something() -> None:
    assert not asked_anything([])
    assert not asked_anything([{"role": "user", "content": "  "}])
    assert asked_anything([{"role": "user", "content": "Why here?"}])


def test_each_matter_of_a_chat_is_logged_in_at_most_two_points() -> None:
    said = (
        '```json\n{"logs": ['
        '{"subject": "gerade", "points": ["Asked if it means straight.",'
        ' "Told it means just now here.", "A third point."]},'
        '{"subject": "", "points": ["no subject"]},'
        '{"subject": "nach Hause", "points": []},'
        '{"subject": "nach Hause", "points": "Asked why not zu Hause."}'
        "]}\n```"
    )

    logs = read_question_logs(said)

    assert logs == [
        ("gerade", "Asked if it means straight.\nTold it means just now here."),
        ("nach Hause", "Asked why not zu Hause."),
    ]
    assert all(len(content.split("\n")) <= MAX_POINTS for _, content in logs)


def test_logs_of_a_chat_that_are_not_written_as_asked_are_refused() -> None:
    with pytest.raises(LogError):
        read_question_logs("gerade means just")
    with pytest.raises(LogError):
        read_question_logs('{"summary": []}')


def test_the_model_is_shown_the_passage_the_translation_and_the_chat() -> None:
    asked: list[list[dict[str, Any]]] = []

    def ask(messages: list[dict[str, Any]]) -> tuple[str, Profile]:
        asked.append(messages)
        return '{"logs": [{"subject": "gerade", "points": ["x"]}]}', Profile({})

    messages = [
        {"role": "user", "content": "Does it mean straight?"},
        {"role": "assistant", "content": "Here it means just now."},
    ]

    logs, _ = write_question_logs(ask, PASSAGE, "just", messages, "German", "English")

    prompt = asked[0][0]["content"]
    assert logs == [("gerade", "x")]
    assert "Ich bin [[gerade]] nach Hause gekommen." in prompt
    assert "Learner: Does it mean straight?" in prompt
    assert "Helper: Here it means just now." in prompt
    assert "The translation they were given:\njust" in prompt
