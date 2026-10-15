# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from kit import (
    ModelError,
    ask_json,
    describe_guidance,
    describe_lesson,
    describe_level,
    describe_made,
    describe_plan,
    describe_topics,
    describe_words,
    focuses,
    grade,
    grade_of,
)

DOCTOR = {"title": "Beim Arzt", "description": "symptoms"}
FOOTBALL = {"title": "Fußball", "description": ""}


def context(**more: Any) -> dict[str, Any]:
    return {"language": "German", "topics": [], "words": None, **more}


def test_a_session_without_topics_is_about_everyday_life() -> None:
    assert describe_topics(context()) == "Topic: everyday life."


def test_one_topic_is_described_with_what_it_is_about() -> None:
    assert describe_topics(context(topics=[DOCTOR])) == "Topic: Beim Arzt (symptoms)."
    assert describe_topics(context(topics=[FOOTBALL])) == "Topic: Fußball."


def test_topics_that_are_mixed_are_to_be_brought_together() -> None:
    mixed = describe_topics(context(topics=[DOCTOR, FOOTBALL], mix_topics=True))
    listed = describe_topics(context(topics=[DOCTOR, FOOTBALL]))

    assert mixed.startswith("Topics: Beim Arzt (symptoms); Fußball. Mix them")
    assert listed == "Topics: Beim Arzt (symptoms); Fußball."


def test_the_words_are_to_be_used_alone_or_preferred_as_the_session_says() -> None:
    only = describe_words(
        context(words={"mode": "only", "lemmas": ["der Arzt", "krank"]})
    )
    prefer = describe_words(context(words={"mode": "prefer", "lemmas": ["krank"]}))

    assert "with these words alone" in only
    assert only.endswith("\nder Arzt, krank")
    assert "wherever they fit" in prefer
    assert prefer.endswith("\nkrank")


def test_without_words_nothing_is_said_of_them() -> None:
    assert describe_words(context()) == ""
    assert describe_words(context(words={"mode": "only", "lemmas": []})) == ""


class Saying:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def ask(self, messages: list[dict[str, Any]]) -> str:
        return self.reply

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        raise ModelError("draws nothing")

    def look(self, messages: list[dict[str, Any]]) -> str:
        return self.ask(messages)


@pytest.mark.parametrize(
    "reply",
    [
        '{"items": [1]}',
        'Sure:\n```json\n{"items": [1]}\n```',
        'Here are the points: {"items": [1]} I hope they help.',
        'I found {these} things: {"items": [1]}',
    ],
)
def test_json_is_read_however_the_model_wraps_it(reply: str) -> None:
    assert ask_json(Saying(reply), []) == {"items": [1]}


def test_a_reply_without_json_says_what_the_model_said() -> None:
    with pytest.raises(ModelError, match="did not reply with JSON: I cannot see"):
        ask_json(Saying("I cannot see images."), [])


def test_what_the_app_says_to_heed_is_told_on_lines_of_its_own() -> None:
    assert describe_guidance(context(guidance=" Do not use: Tisch ")) == (
        "\nDo not use: Tisch\n"
    )
    assert describe_guidance(context()) == ""


def test_a_lesson_is_described_by_its_points_without_its_pages_of_theory() -> None:
    lesson = {
        "title": "Trennbare Verben",
        "level": "A1",
        "more_info": "# Trennbare Verben\n\nViele Verben haben ein Präfix.",
        "points": [
            {"role": "new", "title": "Prefix", "statement": "Last.", "when": "always"},
            {
                "role": "preview",
                "title": "Later",
                "statement": "Not yet.",
                "when": "never",
            },
        ],
    }

    described = describe_lesson(context(lesson=lesson))

    assert described == (
        "Lesson: Trennbare Verben (level A1)\n"
        "- Prefix (new): Last. Applies when: always."
    )


def test_the_sentences_are_as_long_as_the_level_of_the_learner_reads() -> None:
    lesson = {"level": "A1"}

    told = describe_level(context(level="B2", lesson=lesson))
    lesson_level = describe_level(context(level="", lesson=lesson))
    unknown = describe_level(context(level="Z9", lesson=lesson))

    assert "level B2" in told and "10 to 20 words" in told
    # with no level of their own, the learner is at that of the lesson
    assert "level A1" in lesson_level and "4 to 8 words" in lesson_level
    assert "level Z9" in unknown and "words" not in unknown.split("knows")[1]
    assert "the rules come first" in told


def test_the_sentences_made_before_are_told_so_that_others_are_made() -> None:
    assert describe_made([]) == ""
    assert describe_made(["Ich stehe auf.", "Er ruft an."]).endswith(
        "\n- Ich stehe auf.\n- Er ruft an.\n"
    )


@pytest.mark.parametrize(
    "results, overall",
    [
        (["right", "right"], "right"),
        (["wrong", "wrong"], "wrong"),
        (["right", "wrong"], "partial"),
        (["partial", "partial"], "partial"),
    ],
)
def test_an_instance_of_several_answers_is_graded_once(
    results: list[str], overall: str
) -> None:
    graded = [
        grade(result, f"answer {number}", f"fixed {number}", "")
        for number, result in enumerate(results, start=1)
    ]

    assert grade_of(graded)["result"] == overall
    assert grade_of(graded)["answer"] == "1. answer 1\n2. answer 2"


def test_the_grade_of_an_instance_keeps_its_tasks_apart_from_the_answers() -> None:
    graded = grade_of(
        [
            grade("right", "stehe; auf", task="Ich ___ um 6 Uhr ___."),
            grade("wrong", "", "ruft; an", "Left empty.", "Er ___ dich ___."),
        ]
    )

    assert graded == {
        "result": "partial",
        "task": "1. Ich ___ um 6 Uhr ___.\n2. Er ___ dich ___.",
        "answer": "1. stehe; auf\n2. (nothing)",
        "correction": "1. (right)\n2. ruft; an",
        "note": "2. Left empty.",
    }


def point(title: str, role: str = "new", **more: Any) -> dict[str, Any]:
    return {"title": title, "role": role, "statement": "", "when": "", **more}


def test_what_is_made_is_centred_on_each_point_taught_or_reviewed_in_turn() -> None:
    lesson = {
        "title": "L",
        "level": "A1",
        "points": [point("a"), point("b", "review"), point("c", "preview")],
    }

    plan = describe_plan({"lesson": lesson}, 3, start=1)

    assert focuses({"lesson": lesson}) == ["a", "b"]
    assert plan.endswith("\n1. b\n2. a\n3. b\n")
    assert "another side of it" in plan


def test_a_review_centres_what_is_made_on_each_of_its_lessons() -> None:
    lesson = {
        "title": "Review",
        "level": "A2",
        "points": [
            point("a", "review", lesson="One"),
            point("b", "review", lesson="Two"),
            point("c", "review", lesson="One"),
        ],
    }

    assert focuses({"lesson": lesson}) == ["One (a; c)", "Two (b)"]
    assert "another side" not in describe_plan({"lesson": lesson}, 2)


def test_a_lesson_without_points_to_practise_leaves_the_model_free() -> None:
    lesson = {"title": "L", "level": "A1", "points": [point("c", "preview")]}

    assert describe_plan({"lesson": lesson}, 5) == ""
