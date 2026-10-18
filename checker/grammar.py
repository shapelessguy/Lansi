# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The grammar of each language: the grammar points, and the lessons made of
them.

A grammar point is one decision the learner makes, such as which ending a
verb takes. A lesson is a selection of points, each with the
role it has there: taught as `new`, practised again as `review`, or only
shown ahead of time as `preview`. A lesson holds no grammar of its own but
what the book says that fits no point, in `more_info`.

They are kept by hand, for each language in `grammar/` of its directory in
languages/: the points in `points.json`, each lesson in a file of
its own in `lessons/`, and the order the lessons are taught in, as a list
of their ids, in `order.json`. They are read again whenever they are asked for, so
that a change to them is seen without starting the server again.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from languages import LANGUAGES_DIRECTORY, directory_of

# where the directories of the languages are, each with its grammar/
GRAMMAR_DIRECTORY = LANGUAGES_DIRECTORY
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
ROLES = ("new", "review", "preview")


class GrammarError(Exception):
    """The grammar of a language is not as it should be. The message says
    what is wrong, and where."""


@dataclass
class Point:
    id: str
    level: str
    title: str
    # the rule, in a sentence or two
    statement: str
    # when the rule applies, which is when a mistake can break it
    when: str
    # the points learners mix this one up with
    confused_with: list[str]
    # the points to be known before this one
    requires: list[str]


@dataclass
class LessonPoint:
    id: str
    # "new", "review" or "preview"
    role: str


@dataclass
class Lesson:
    id: str
    level: str
    title: str
    # in the order they are taught in
    points: list[LessonPoint]
    # what the book says that fits no point
    more_info: str

    def described(self, points: dict[str, Point]) -> dict[str, Any]:
        """The lesson with what each of its points says, as an exercise is
        given it."""
        return {
            **asdict(self),
            "points": [
                {**asdict(points[point.id]), "role": point.role}
                for point in self.points
            ],
        }


def _text(data: dict[str, Any], name: str, where: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise GrammarError(f"{where}: {name} must be text")
    return value.strip()


def _ids(data: dict[str, Any], name: str, where: str) -> list[str]:
    value = data.get(name, [])
    if not isinstance(value, list) or not all(isinstance(each, str) for each in value):
        raise GrammarError(f"{where}: {name} must be a list of ids")
    return value


def _level(data: dict[str, Any], where: str) -> str:
    level = _text(data, "level", where)
    if level not in LEVELS:
        raise GrammarError(f"{where}: the level must be one of {', '.join(LEVELS)}")
    return level


def read_point(data: object, where: str) -> Point:
    """A point as it is written down. Raises GrammarError."""
    if not isinstance(data, dict):
        raise GrammarError(f"{where}: a point must be an object")
    return Point(
        id=_text(data, "id", where),
        level=_level(data, where),
        title=_text(data, "title", where),
        statement=_text(data, "statement", where),
        when=_text(data, "when", where),
        confused_with=_ids(data, "confused_with", where),
        requires=_ids(data, "requires", where),
    )


def read_lesson(data: object, where: str) -> Lesson:
    """A lesson as it is written down. Raises GrammarError."""
    if not isinstance(data, dict):
        raise GrammarError(f"{where}: a lesson must be an object")
    listed = data.get("points")
    if not isinstance(listed, list) or not listed:
        raise GrammarError(f"{where}: a lesson needs its points")
    points = []
    for point in listed:
        if not isinstance(point, dict) or not isinstance(point.get("id"), str):
            raise GrammarError(f"{where}: each point needs an id")
        if point.get("role") not in ROLES:
            raise GrammarError(f"{where}: the role must be one of {', '.join(ROLES)}")
        points.append(LessonPoint(point["id"], point["role"]))
    more_info = data.get("more_info", "")
    if not isinstance(more_info, str):
        raise GrammarError(f"{where}: more_info must be text")
    return Lesson(
        id=_text(data, "id", where),
        level=_level(data, where),
        title=_text(data, "title", where),
        points=points,
        more_info=more_info.strip(),
    )


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise GrammarError(f"{path.name}: {error}") from None


class Grammar:
    def __init__(self, directory: str | Path = GRAMMAR_DIRECTORY) -> None:
        self._directory = Path(directory)

    def _language_directory(self, language: str) -> Path | None:
        """Where the grammar of `language` is, whatever its case, if anywhere."""
        directory = directory_of(language, self._directory)
        return directory / "grammar" if directory else None

    def points(self, language: str) -> dict[str, Point]:
        """The points of `language`, by their ids. Raises GrammarError."""
        directory = self._language_directory(language)
        if directory is None or not (directory / "points.json").exists():
            return {}
        listed = _read_json(directory / "points.json")
        if not isinstance(listed, list):
            raise GrammarError("points.json: must be a list of points")
        points: dict[str, Point] = {}
        for number, data in enumerate(listed, start=1):
            point = read_point(data, f"points.json, point {number}")
            if point.id in points:
                raise GrammarError(f"points.json: {point.id} is there twice")
            points[point.id] = point
        for point in points.values():
            for other in point.confused_with + point.requires:
                if other not in points:
                    raise GrammarError(f"points.json, {point.id}: no point {other}")
        return points

    def _order(self, directory: Path, lessons: list[Lesson]) -> list[str]:
        """The ids of the lessons in the order they are taught in, as
        `order.json` lists them, if there is one."""
        if not (directory / "order.json").exists():
            return []
        listed = _read_json(directory / "order.json")
        if not isinstance(listed, list) or not all(
            isinstance(each, str) for each in listed
        ):
            raise GrammarError("order.json: must be a list of lesson ids")
        known = {lesson.id for lesson in lessons}
        for number, lesson_id in enumerate(listed):
            if lesson_id not in known:
                raise GrammarError(f"order.json: no lesson {lesson_id}")
            if lesson_id in listed[:number]:
                raise GrammarError(f"order.json: {lesson_id} is there twice")
        return listed

    def lessons(self, language: str) -> list[Lesson]:
        """The lessons of `language` in the order `order.json` gives, and
        those it does not list after them, by their level and then their
        titles. Raises GrammarError for one that names a point there is not."""
        directory = self._language_directory(language)
        if directory is None or not (directory / "lessons").is_dir():
            return []
        points = self.points(language)
        lessons = []
        for path in sorted((directory / "lessons").glob("*.json")):
            lesson = read_lesson(_read_json(path), path.name)
            if lesson.id != path.stem:
                raise GrammarError(f"{path.name}: the id must be {path.stem}")
            for point in lesson.points:
                if point.id not in points:
                    raise GrammarError(f"{path.name}: no point {point.id}")
            lessons.append(lesson)
        order = self._order(directory, lessons)
        unlisted = len(order)
        return sorted(
            lessons,
            key=lambda lesson: (
                order.index(lesson.id) if lesson.id in order else unlisted,
                lesson.level,
                lesson.title,
            ),
        )

    def review(self, language: str, lesson_ids: list[str]) -> dict[str, Any] | None:
        """A lesson that goes over the lessons of `language` by
        `lesson_ids`, in the order they are taught in: every point of them
        once, each to be reviewed, at the highest of their levels. Lessons
        there are not are left out, and there is no review without any.
        Raises GrammarError."""
        wanted = set(lesson_ids)
        lessons = [lesson for lesson in self.lessons(language) if lesson.id in wanted]
        if not lessons:
            return None
        points = self.points(language)
        # each point, with the title of the first lesson it is in
        reviewed: dict[str, str] = {}
        for lesson in lessons:
            for point in lesson.points:
                reviewed.setdefault(point.id, lesson.title)
        return {
            "id": "",
            "level": max(lesson.level for lesson in lessons),
            "title": "Review of " + "; ".join(lesson.title for lesson in lessons),
            "points": [
                {**asdict(points[point]), "role": "review", "lesson": title}
                for point, title in reviewed.items()
            ],
            "more_info": "",
        }

    def lesson(self, language: str, lesson_id: str) -> dict[str, Any] | None:
        """The lesson of `language` with what each of its points says, if
        there is one by `lesson_id`. Raises GrammarError."""
        for lesson in self.lessons(language):
            if lesson.id == lesson_id:
                return lesson.described(self.points(language))
        return None
