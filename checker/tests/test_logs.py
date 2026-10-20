# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from logs import (
    LogError,
    Task,
    describe_record,
    format_log,
    has_anything,
    lines_for,
    read_log,
    write_log,
)
from profiling import Profile

LESSON = {
    "title": "Trennbare Verben",
    "level": "A1",
    "points": [
        {
            "title": "Prefix last",
            "role": "new",
            "statement": "The prefix goes to the end.",
            "when": "in a main clause",
        },
        {"title": "Old", "role": "known", "statement": "-", "when": "-"},
    ],
}
TASK = Task("Cloze", "Fill the gaps.", "German", "A1", LESSON, ["Daily routine"], 5)


def grade(
    result: str, answer: str, correction: str = "", task: str = ""
) -> dict[str, str]:
    return {
        "result": result,
        "task": task,
        "answer": answer,
        "correction": correction,
        "note": "",
    }


def test_a_log_is_asked_with_the_task_the_grades_and_the_lines_it_may_have() -> None:
    asked: list[Any] = []

    def ask(messages: list[dict[str, Any]]) -> tuple[str, Profile]:
        asked.append(messages)
        return '{"summary": ["0 of 5 done right."]}', Profile({}, id="gen-1")

    log, used = write_log(
        ask, TASK, [grade("wrong", "aufstehe", "stehe; auf", "Ich ___ um 6 ___.")], {}
    )

    prompt = asked[0][0]["content"]
    assert "Cloze: Fill the gaps." in prompt and "Topics: Daily routine" in prompt
    assert "- Prefix last (new): The prefix goes to the end." in prompt
    assert "Old" not in prompt
    assert (
        "Instance 1, graded wrong\n"
        "  Given by the exercise (not the learner's):\n    Ich ___ um 6 ___.\n"
        "  Written by the learner:\n    aufstehe\n"
        "  Correct:\n    stehe; auf"
    ) in prompt
    assert "at most 7 lines" in prompt
    assert (log, used.id) == ("0 of 5 done right.", "gen-1")


def test_a_log_may_be_longer_the_more_the_learner_wrote() -> None:
    short = [grade("right", "Ich stehe auf.")]
    retelling = {"user": [" ".join(["Wort"] * 300)]}
    conversation = {"user": [" ".join(["Wort"] * 100)] * 10}

    found = [
        lines_for(short, {}),
        lines_for([], retelling),
        lines_for([], conversation),
    ]

    assert found == [7, 11, 16]


def test_without_grades_the_record_is_what_was_written() -> None:
    written = {"user": ["Ich gehe heim."], "assistant": ["Wohin gehst du?"]}

    record = describe_record([], written)

    assert record == "Exercise: Wohin gehst du?\nLearner: Ich gehe heim."


def test_there_is_a_log_only_of_what_the_learner_did() -> None:
    assert not has_anything([], {"user": [" "], "assistant": ["Hallo."]})
    assert has_anything([], {"user": ["Hallo."]})
    assert has_anything([grade("wrong", "")], {})


def test_a_log_is_kept_as_its_account_then_its_examples() -> None:
    found = {
        "summary": ["3 of 5 right.", " Prefix  left in place twice. "],
        "worked": [{"text": "Ich rufe an.", "why": "prefix last"}],
        "failed": [
            {
                "text": "aufstehe",
                "given": "Ich ___ um 6 ___.",
                "correction": "stehe; auf",
                "why": "split",
            },
            {"text": "Er einkauft."},
            {"text": ""},
        ],
    }

    assert format_log(found) == (
        "3 of 5 right.\nPrefix left in place twice.\n"
        'Worked:\n- "Ich rufe an.": prefix last\n'
        'Did not work:\n- "aufstehe" (in: "Ich ___ um 6 ___.") → "stehe; auf": split\n'
        '- "Er einkauft."'
    )


def test_a_log_may_come_in_a_fenced_block_among_other_words() -> None:
    said = 'Here it is:\n```json\n{"summary": ["Done."], "worked": []}\n```'

    assert read_log(said)["summary"] == ["Done."]


@pytest.mark.parametrize("said", ["no JSON", '{"worked": []}', '{"summary": []}'])
def test_a_log_that_is_not_as_asked_is_refused(said: str) -> None:
    with pytest.raises(LogError):
        format_log(read_log(said))
