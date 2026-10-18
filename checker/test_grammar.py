# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from grammar import Grammar, GrammarError


def point(point_id: str, **more: Any) -> dict[str, Any]:
    return {
        "id": point_id,
        "level": "A1",
        "title": point_id.title(),
        "statement": f"The rule of {point_id}.",
        "when": "always",
        "confused_with": [],
        "requires": [],
        **more,
    }


def write(directory: Path, points: list[Any], lessons: dict[str, Any]) -> Grammar:
    german = directory / "German" / "grammar"
    (german / "lessons").mkdir(parents=True)
    (german / "points.json").write_text(json.dumps(points), encoding="utf-8")
    for name, lesson in lessons.items():
        (german / "lessons" / f"{name}.json").write_text(
            json.dumps(lesson), encoding="utf-8"
        )
    return Grammar(directory)


def lesson(
    lesson_id: str, *points: tuple[str, str], level: str = "A1"
) -> dict[str, Any]:
    return {
        "id": lesson_id,
        "level": level,
        "title": lesson_id.title(),
        "points": [{"id": each, "role": role} for each, role in points],
        "more_info": "A note.",
    }


def test_the_grammar_that_is_kept_is_whole() -> None:
    grammar = Grammar()

    lessons = grammar.lessons("German")

    assert lessons
    for each in lessons:
        described = grammar.lesson("German", each.id)
        assert described and all(point["statement"] for point in described["points"])


def test_a_lesson_is_given_with_what_each_of_its_points_says_in_the_order_taught(
    tmp_path: Path,
) -> None:
    grammar = write(
        tmp_path,
        [point("a"), point("b", requires=["a"])],
        {"one": lesson("one", ("b", "new"), ("a", "review"))},
    )

    described = grammar.lesson("german", "one")

    assert described is not None
    assert [(each["id"], each["role"]) for each in described["points"]] == [
        ("b", "new"),
        ("a", "review"),
    ]
    assert described["points"][0]["requires"] == ["a"]
    assert described["more_info"] == "A note."


def test_a_review_goes_over_every_point_of_its_lessons_once_at_their_highest_level(
    tmp_path: Path,
) -> None:
    grammar = write(
        tmp_path,
        [point("a"), point("b"), point("c")],
        {
            "one": lesson("one", ("a", "new"), ("b", "preview")),
            "two": lesson("two", ("b", "new"), ("c", "new"), level="A2"),
        },
    )

    review = grammar.review("German", ["two", "one", "gone"])

    assert review is not None
    assert review["title"] == "Review of One; Two"
    assert review["level"] == "A2"
    assert [
        (each["id"], each["role"], each["lesson"]) for each in review["points"]
    ] == [("a", "review", "One"), ("b", "review", "One"), ("c", "review", "Two")]
    assert grammar.review("German", ["gone"]) is None


def test_lessons_are_listed_by_their_level_and_then_their_title_with_no_order_kept(
    tmp_path: Path,
) -> None:
    grammar = write(
        tmp_path,
        [point("a")],
        {
            "zebra": lesson("zebra", ("a", "new")),
            "later": lesson("later", ("a", "new"), level="A2"),
            "apple": lesson("apple", ("a", "new")),
        },
    )

    assert [each.id for each in grammar.lessons("German")] == [
        "apple",
        "zebra",
        "later",
    ]


def test_lessons_are_listed_in_the_order_kept_and_the_others_after_them(
    tmp_path: Path,
) -> None:
    grammar = write(
        tmp_path,
        [point("a")],
        {
            "zebra": lesson("zebra", ("a", "new")),
            "later": lesson("later", ("a", "new"), level="A2"),
            "apple": lesson("apple", ("a", "new")),
            "mango": lesson("mango", ("a", "new")),
        },
    )
    (tmp_path / "German" / "grammar" / "order.json").write_text(
        json.dumps(["zebra", "later"]), encoding="utf-8"
    )

    assert [each.id for each in grammar.lessons("German")] == [
        "zebra",
        "later",
        "apple",
        "mango",
    ]


def test_the_order_kept_names_only_lessons_there_are_and_each_once(
    tmp_path: Path,
) -> None:
    grammar = write(tmp_path, [point("a")], {"one": lesson("one", ("a", "new"))})
    order = tmp_path / "German" / "grammar" / "order.json"

    order.write_text(json.dumps(["one", "gone"]), encoding="utf-8")
    with pytest.raises(GrammarError, match="no lesson gone"):
        grammar.lessons("German")

    order.write_text(json.dumps(["one", "one"]), encoding="utf-8")
    with pytest.raises(GrammarError, match="there twice"):
        grammar.lessons("German")


def test_a_language_without_a_grammar_has_no_lessons(tmp_path: Path) -> None:
    assert Grammar(tmp_path).lessons("Spanish") == []
    assert Grammar(tmp_path).lesson("Spanish", "anything") is None


@pytest.mark.parametrize(
    "points, lessons, wrong",
    [
        ([point("a", requires=["gone"])], {}, "no point gone"),
        ([point("a"), point("a")], {}, "there twice"),
        ([point("a", level="Z9")], {}, "the level"),
        ([point("a")], {"one": lesson("one", ("gone", "new"))}, "no point gone"),
        ([point("a")], {"one": lesson("one", ("a", "taught"))}, "the role"),
        ([point("a")], {"one": lesson("other", ("a", "new"))}, "the id must be one"),
    ],
)
def test_a_grammar_that_is_not_as_it_should_be_says_what_is_wrong(
    tmp_path: Path, points: list[Any], lessons: dict[str, Any], wrong: str
) -> None:
    grammar = write(tmp_path, points, lessons)

    with pytest.raises(GrammarError, match=wrong):
        grammar.lessons("German")
