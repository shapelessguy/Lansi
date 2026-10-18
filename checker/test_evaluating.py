# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from evaluating import (
    EVALUATIONS_DIRECTORY,
    EvaluationError,
    Evaluations,
    exams,
    score,
)
from exercising import EXERCISES_DIRECTORY, Practice, Runner, exercises
from profiling import Profile
from storage import UserStore

# A backend that scores what its options say, and tells what it was given.
SCORED = """\
from kit import Step, grade, serve

def start(context, model):
    shown = {name: context[name] for name in ("exam", "minutes", "level", "instances")}
    return Step(state={}, show={**shown, "options": context["options"]})

def act(context, state, message, model):
    return Step(state=state, show="ok", graded=[grade("right", message)])

def finish(context, state, model):
    return Step(results={}, scores={context["options"]["skill"]: 80, "task": 50})

serve(start, act, finish)
"""
MANIFEST = {
    "title": "Scored",
    "description": "scores what it is told",
    "options": {
        "skill": {
            "label": "Skill",
            "choices": {"reading": "Lesen", "writing": "Schreiben"},
        },
        "count": {"label": "Count", "min": 1, "max": 10, "default": 4},
    },
}
TEMPLATE = {
    "level": "A1",
    "exam": "Test A1",
    "pass": {"total": 60},
    "themes": ["Wohnen"],
    "modules": [
        {
            "id": "reading",
            "title": "Lesen",
            "weight": 25,
            "parts": [
                {
                    "title": "Teil 1",
                    "exercise": "scored",
                    "options": {"skill": "reading", "count": 4},
                    "instances": 1,
                    "scale": "count",
                    "minutes": 20,
                    "points": 5,
                    "instructions": "Lesen Sie.",
                    "task": "A short email.",
                    "example": {"text": "Liebe Maria"},
                }
            ],
        },
        {
            "id": "writing",
            "title": "Schreiben",
            "weight": 25,
            "parts": [
                {
                    "title": "Teil 1",
                    "exercise": "scored",
                    "options": {"skill": "writing"},
                    "instances": 2,
                    "minutes": 40,
                    "points": 10,
                    "instructions": "Schreiben Sie.",
                    "task": "A message.",
                }
            ],
        },
    ],
}
LOG_REPLY = (
    '{"summary": ["Both parts done.", "Reading went well."],'
    ' "worked": [{"text": "Ja.", "why": "right"}], "failed": []}'
)
LEARNER = {"into": "English", "level": "B2"}


def answering(text: str = LOG_REPLY) -> Any:
    def ask(messages: list[dict[str, Any]]) -> tuple[str, Profile]:
        return text, Profile({}, id="gen-1", model="some/model")

    return ask


@pytest.fixture
def directory(tmp_path: Path) -> Path:
    """A directory of exercises with the kit and one exercise, `scored`."""
    exercises_directory = tmp_path / "exercises"
    (exercises_directory / "scored" / "ui").mkdir(parents=True)
    shutil.copy(EXERCISES_DIRECTORY / "kit.py", exercises_directory)
    scored = exercises_directory / "scored"
    (scored / "manifest.json").write_text(json.dumps(MANIFEST), encoding="utf-8")
    (scored / "backend.py").write_text(SCORED, encoding="utf-8")
    (scored / "ui" / "index.js").write_text(
        "export function mount() {}", encoding="utf-8"
    )
    return exercises_directory


@pytest.fixture
def templates(tmp_path: Path) -> Path:
    """A directory of languages, with the exam of A1 in German."""
    (tmp_path / "languages" / "German" / "evaluations").mkdir(parents=True)
    (tmp_path / "languages" / "German" / "evaluations" / "A1.json").write_text(
        json.dumps(TEMPLATE), encoding="utf-8"
    )
    return tmp_path / "languages"


@pytest.fixture
def evaluations(tmp_path: Path, directory: Path, templates: Path) -> Evaluations:
    store = UserStore(tmp_path / "ada")
    practice = Practice(store, runner=Runner(directory), directory=directory)
    return Evaluations(
        store,
        practice,
        templates,
        directory,
        sample=lambda themes, count: themes[:count],
    )


def test_the_exams_of_german_name_exercises_and_options_there_are() -> None:
    found = exams("German", EVALUATIONS_DIRECTORY)

    assert set(found) >= {"A1", "A2"}
    known = {manifest.id for manifest in exercises()}
    for exam in found.values():
        assert {part.module for part in exam.parts} == {
            "listening",
            "reading",
            "writing",
            "speaking",
        }
        assert {part.exercise for part in exam.parts} <= known
    assert found["A1"].minutes == 80


def test_a_template_with_an_exercise_there_is_not_is_refused(
    templates: Path, directory: Path
) -> None:
    broken = json.loads(json.dumps(TEMPLATE))
    broken["modules"][0]["parts"][0]["exercise"] = "dance"
    (templates / "German" / "evaluations" / "A1.json").write_text(
        json.dumps(broken), encoding="utf-8"
    )

    with pytest.raises(EvaluationError, match="no exercise 'dance'"):
        exams("German", templates, directory)


def test_a_template_with_an_option_its_exercise_does_not_have_is_refused(
    templates: Path, directory: Path
) -> None:
    broken = json.loads(json.dumps(TEMPLATE))
    broken["modules"][0]["parts"][0]["options"]["skill"] = "singen"
    (templates / "German" / "evaluations" / "A1.json").write_text(
        json.dumps(broken), encoding="utf-8"
    )

    with pytest.raises(EvaluationError, match="singen"):
        exams("German", templates, directory)


def test_a_language_with_no_templates_has_no_exams(templates: Path) -> None:
    assert exams("Klingon", templates) == {}
    assert exams("../German", templates) == {}


def test_a_shorter_evaluation_has_fewer_instances_or_less_of_the_option_scaled(
    evaluations: Evaluations,
) -> None:
    # half of the hour of the exam, and twice as much
    evaluation = evaluations.start("German", "A1", 1, True)
    half = [
        (part["instances"], part["options"]["count"], part["minutes"])
        for part in evaluation["parts"]
    ]

    evaluation = evaluations.start("German", "A1", 4, True)
    twice = [
        (part["instances"], part["options"]["count"], part["minutes"])
        for part in evaluation["parts"]
    ]

    assert half == [(1, 2, 10), (1, 4, 20)]
    assert twice == [(2, 4, 40), (4, 4, 80)]


def test_an_evaluation_is_of_an_exam_there_is_and_of_a_length_it_can_have(
    evaluations: Evaluations,
) -> None:
    with pytest.raises(ValueError, match="no exam of German at B2"):
        evaluations.start("German", "B2", 2, True)
    with pytest.raises(ValueError, match="1 to 8 half hours"):
        evaluations.start("German", "A1", 9, True)


def test_a_part_is_a_session_of_its_exercise_told_of_the_exam_and_kept_from_practice(
    evaluations: Evaluations,
) -> None:
    evaluation = evaluations.start("German", "A1", 2, True)

    described, session = evaluations.start_part(evaluation["id"], 0)
    shown, _ = evaluations._practice.step(  # noqa: SLF001
        session["id"], "scored", "start", None, {**LEARNER, "level": "A1"}, answering()
    )

    assert described["parts"][0]["status"] == "running"
    assert session["kind"] == "evaluation"
    assert "Exam: Test A1, Lesen, Teil 1." in shown["exam"]
    assert "Draw on one of these themes: Wohnen." in shown["exam"]
    assert '"text": "Liebe Maria"' in shown["exam"]
    assert (shown["minutes"], shown["options"]["count"]) == (20, 4)
    assert evaluations._store.sessions() == []  # noqa: SLF001
    with pytest.raises(ValueError, match="finish the part that is running"):
        evaluations.start_part(evaluation["id"], 1)


def test_an_untimed_evaluation_gives_its_parts_no_time_limit(
    evaluations: Evaluations,
) -> None:
    evaluation = evaluations.start("German", "A1", 2, False)

    _, session = evaluations.start_part(evaluation["id"], 0)

    assert session["minutes"] == {"scored": 0}


def test_an_evaluation_done_to_the_end_is_scored_by_its_parts_and_logged(
    evaluations: Evaluations,
) -> None:
    evaluation = evaluations.start("German", "A1", 2, True)
    practice = evaluations._practice  # noqa: SLF001
    for position in (0, 1):
        _, session = evaluations.start_part(evaluation["id"], position)
        practice.step(session["id"], "scored", "start", None, LEARNER, answering())
        practice.step(session["id"], "scored", "act", "Ja.", LEARNER, answering())
        ended, _ = evaluations.finish_part(
            evaluation["id"], position, LEARNER, answering()
        )

    assert ended["status"] == "finished"
    assert ended["result"]["scores"]["reading"] == 80
    assert ended["result"]["scores"]["writing_task"] == 50
    assert ended["result"]["scores"]["total"] == 80
    assert ended["result"]["passed"] is True
    (log, *exercise_logs) = evaluations._store.all_logs()  # noqa: SLF001
    assert log["kind"] == "evaluation"
    assert log["content"].startswith("Both parts done.")
    assert "Scores: reading 80" in log["content"]
    assert log["source"]["scores"]["total"] == 80
    assert [each["kind"] for each in exercise_logs] == ["exercise", "exercise"]


def test_an_evaluation_ended_early_is_abandoned_and_not_passed(
    evaluations: Evaluations,
) -> None:
    evaluation = evaluations.start("German", "A1", 2, True)
    _, session = evaluations.start_part(evaluation["id"], 0)
    evaluations._practice.step(
        session["id"], "scored", "start", None, LEARNER, answering()
    )  # noqa: SLF001

    ended, _ = evaluations.end(evaluation["id"], LEARNER, answering())

    assert ended["status"] == "abandoned"
    assert ended["result"]["scores"]["reading"] == 80
    assert ended["result"]["scores"]["writing"] is None
    assert (ended["result"]["scores"]["total"], ended["result"]["passed"]) == (
        None,
        None,
    )


def test_a_module_counts_its_parts_by_their_points_and_a_part_not_done_as_none() -> (
    None
):
    plan = {
        "pass": {"module": 60},
        "modules": [{"id": "reading", "weight": 1}, {"id": "listening", "weight": 3}],
        "parts": [
            {"module": "reading", "points": 5},
            {"module": "reading", "points": 15},
            {"module": "listening", "points": 5},
        ],
    }

    result = score(plan, [{"reading": 100}, None, {"listening": 70}])

    assert result["scores"]["reading"] == 25
    assert result["scores"]["listening"] == 70
    # (25 + 3 * 70) / 4
    assert result["scores"]["total"] == 58.8
    # as every module must reach 60
    assert result["passed"] is False
