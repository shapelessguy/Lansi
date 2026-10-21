# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from pathlib import Path

import pytest
from exercising import EXERCISES_DIRECTORY, exercises
from instances import instance_problem, schema_problem

SET = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "gaps": {"type": "integer"},
                    "level": {"type": "string", "enum": ["A1", "A2"]},
                },
                "required": ["text"],
            },
        }
    },
    "required": ["items"],
}


def test_an_instance_of_the_shape_declared_has_nothing_wrong_with_it() -> None:
    made = {"items": [{"text": "Ich [stehe] auf.", "gaps": 1}, {"text": "Hallo."}]}

    assert schema_problem(SET) is None
    assert instance_problem(made, SET) is None


@pytest.mark.parametrize(
    "made, problem",
    [
        ([], "instance is not an object"),
        ({}, "instance has no items"),
        ({"items": [{"text": 3}]}, "instance.items[0].text is not text"),
        ({"items": [{"text": "a", "gaps": True}]}, "is not a whole number"),
        ({"items": [{"text": "a", "gaps": None}]}, "is not a whole number"),
        ({"items": [{"text": "a", "level": "C2"}]}, "is not one of A1, A2"),
        ({"items": [], "answers": ["a"]}, "has what its shape does not: answers"),
    ],
)
def test_an_instance_unlike_the_shape_declared_says_what_is_wrong(
    made: object, problem: str
) -> None:
    found = instance_problem(made, SET)

    assert found is not None and problem in found


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "date"},
        {"type": "object", "properties": {}},
        {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["b"]},
        {"type": "array"},
        {"type": "string", "pattern": "x"},
        {"type": "integer", "enum": ["one"]},
    ],
)
def test_a_shape_an_instance_cannot_be_declared_with_is_refused(schema: object) -> None:
    assert schema_problem(schema) is not None


def test_every_exercise_there_is_is_offered_with_the_instance_it_declares() -> None:
    there = [
        path.name
        for path in EXERCISES_DIRECTORY.iterdir()
        if (path / "manifest.json").is_file()
    ]
    found = {manifest.id: manifest for manifest in exercises()}

    # one whose shape could not be read would be left out
    assert sorted(found) == sorted(there)
    for name in there:
        declared = json.loads(
            (EXERCISES_DIRECTORY / name / "manifest.json").read_text(encoding="utf-8")
        ).get("instance")
        assert found[name].instance == declared


def test_an_exercise_whose_instance_is_unlike_any_shape_is_not_offered(
    tmp_path: Path,
) -> None:
    exercise = tmp_path / "odd"
    (exercise / "ui").mkdir(parents=True)
    (exercise / "backend.py").write_text("", encoding="utf-8")
    (exercise / "ui" / "index.js").write_text("", encoding="utf-8")
    (exercise / "manifest.json").write_text(
        json.dumps({"title": "Odd", "instance": {"type": "date"}}), encoding="utf-8"
    )

    assert exercises(tmp_path) == []
