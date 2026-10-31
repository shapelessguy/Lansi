# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from pathlib import Path

import pytest
from exercising import EXERCISES_DIRECTORY, exercises
from instances import (
    GAP,
    instance_problem,
    preview_of,
    read_preview,
    schema_problem,
)

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


def test_the_preview_of_an_instance_is_what_it_asks_with_its_answers_blanked() -> None:
    preview = read_preview(
        ["title", {"path": "items.*.text", "blank": r"\[[^\]]*\]"}, "missing.*"]
    )
    instance = {
        "title": "Morning",
        "items": [{"text": "Ich [stehe] um sechs [auf]."}, {"text": " "}],
    }

    assert preview_of(instance, preview) == [
        "Morning",
        f"Ich {GAP} um sechs {GAP}.",
    ]


def test_a_preview_that_is_not_as_described_is_left_out() -> None:
    assert read_preview(["", 3, {"path": "text", "blank": "["}, {"blank": "x"}]) == []
    assert read_preview("text") == []


def _paths(schema: dict[str, object], at: str = "") -> set[str]:
    """The paths of the texts an instance of `schema` may have."""
    if schema["type"] == "string":
        return {at}
    if schema["type"] == "array":
        items = schema["items"]
        assert isinstance(items, dict)
        return _paths(items, f"{at}.*" if at else "*")
    if schema["type"] == "object":
        properties = schema["properties"]
        assert isinstance(properties, dict)
        return {
            path
            for name, each in properties.items()
            for path in _paths(each, f"{at}.{name}" if at else name)
        }
    return set()


def test_every_exercise_previews_only_texts_its_instances_have() -> None:
    for manifest in exercises():
        if manifest.preview:
            assert manifest.instance is not None
            paths = _paths(manifest.instance)
            assert {path for path, _ in manifest.preview} <= paths, manifest.id
