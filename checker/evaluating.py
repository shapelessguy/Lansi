# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Evaluations: mock exams of a level, as the Goethe-Institut sets them,
made of the exercises of practice.

The exam of each level is kept by hand in a template, for each language in
a directory named after it by its English name, such as
`evaluations/German/A1.json`. A template names the exam, how it is passed,
the themes its texts are drawn from, and its modules, Hören, Lesen,
Schreiben and Sprechen, each with how much it counts and its parts. A part
is an exercise of practice with the options it is set to, how many
instances it has, how many minutes it takes and how many points it is worth
in its module, as the real exam has it, with the instructions the learner
is given, what its texts and tasks are like and an example of one. These
three are told to the exercise as its `exam`, which it follows in place of
a lesson, as exercises/kit.py describes.

An evaluation takes the time the learner chooses, from half an hour to
four, in half hours: every part is made longer or shorter by as much, by
its number of instances, or, where it has one instance, by the option its
`scale` names, such as the questions on a text. With timing, each part
has its minutes, made longer or shorter likewise; without, it takes as long
as the learner likes.

Each part is done in a session of its own, of its one exercise, which is
given the points of the lessons of the level of the exam, and the level as
the learner's. What is written in it is not taken into the vocabulary.
Every exercise reports its scores once it is over; an evaluation counts
them up as the exam does: the score of each module is the mean of those of
its parts, by their points, for the skill of the module, a part not done
counting none; the score of a criterion of writing or speaking is the mean
of those its parts reported; and the total, once every module was done,
the mean of the modules, by how much each counts. Once the evaluation is
over, a model writes its log from what was answered in it, as logs.py does
for an exercise, with the scores.
"""

from __future__ import annotations

import json
import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from exercising import (
    Asker,
    Choosing,
    Drawer,
    ExerciseError,
    Later,
    Manifest,
    Practice,
    cannot_draw,
    chosen_options,
    do_now,
    exercises,
)
from logs import LogError, describe_record, format_log, read_log
from profiling import Profile
from prompts import PROMPTS
from storage import UserStore
from translating import TranslationError

EVALUATIONS_DIRECTORY = Path(__file__).parent / "evaluations"
LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2")
# how long an evaluation may take, in half hours
LENGTHS = range(1, 9)
# the modules of an exam, which are the skills the exercises score
MODULES = ("hoeren", "lesen", "schreiben", "sprechen")
# how what is written or said is rated, as the exercises score it
CRITERIA = ("aufgabe", "kohaerenz", "wortschatz", "strukturen", "aussprache")
# the modules that are rated by the criteria
RATED = ("schreiben", "sprechen")
# What an evaluation scores, each from 0 to 100, or None when it was not
# shown: each module, each criterion of the modules that are rated, such as
# "schreiben_aufgabe", and the total.
SCORES = (
    *MODULES,
    *(f"{module}_{criterion}" for module in RATED for criterion in CRITERIA),
    "total",
)
# how many of the themes of an exam a part is given to choose from
THEMES = 3
# how many lines the account of an evaluation may have
LOG_LINES = 16
MAX_WORKED = 3
MAX_FAILED = 4
# how much of what was answered the model that writes the log is shown, in
# characters
MAX_RECORD = 40_000


class EvaluationError(Exception):
    """A template of an exam is not as it should be. The message says what
    is wrong, and where."""


@dataclass
class Part:
    """A part of the exam of a level, as its template has it."""

    module: str
    title: str
    exercise: str
    options: dict[str, Any]
    instances: int
    minutes: int
    points: int
    instructions: str
    task: str
    example: Any
    # the option that is made larger or smaller where there is one instance
    scale: str = ""


@dataclass
class Exam:
    """The exam of a level, as its template has it."""

    level: str
    title: str
    # `{"total": 60}` to pass with that total and every module done, or
    # `{"module": 60}` to pass with that much in each module
    passing: dict[str, int]
    themes: list[str]
    # each module with its title and how much it counts, in order
    modules: list[dict[str, Any]]
    parts: list[Part]

    @property
    def minutes(self) -> int:
        return sum(part.minutes for part in self.parts)


def _whole(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def read_exam(data: Any, where: str, manifests: dict[str, Manifest]) -> Exam:
    """The exam a template describes. Raises EvaluationError."""

    def wrong(what: str) -> EvaluationError:
        return EvaluationError(f"{where}: {what}")

    if not isinstance(data, dict) or data.get("level") not in LEVELS:
        raise wrong("a template names its level, one of " + ", ".join(LEVELS))
    passing = data.get("pass")
    if not (
        isinstance(passing, dict)
        and len(passing) == 1
        and next(iter(passing)) in ("total", "module")
        and _whole(next(iter(passing.values())))
    ):
        raise wrong('"pass" is {"total": N} or {"module": N}')
    themes = data.get("themes") or []
    if not isinstance(themes, list) or not all(
        isinstance(each, str) for each in themes
    ):
        raise wrong('"themes" is a list of texts')
    modules, parts = [], []
    for module in data.get("modules") or []:
        if not isinstance(module, dict) or module.get("id") not in MODULES:
            raise wrong("each module is one of " + ", ".join(MODULES))
        if not _whole(module.get("weight")) or module["weight"] <= 0:
            raise wrong(f"the module {module['id']} needs a weight")
        modules.append(
            {
                "id": module["id"],
                "title": str(module.get("title") or module["id"]),
                "weight": module["weight"],
            }
        )
        for part in module.get("parts") or []:
            parts.append(_read_part(part, module["id"], manifests, wrong))
    if not parts:
        raise wrong("an exam needs a part")
    return Exam(
        data["level"],
        str(data.get("exam") or f"Exam {data['level']}"),
        passing,
        themes,
        modules,
        parts,
    )


def _read_part(
    part: Any,
    module: str,
    manifests: dict[str, Manifest],
    wrong: Callable[[str], EvaluationError],
) -> Part:
    if not isinstance(part, dict):
        raise wrong(f"a part of {module} is an object")
    title = f"{module} {part.get('title', '')}".strip()
    manifest = manifests.get(part.get("exercise", ""))
    if manifest is None or manifest.theory:
        raise wrong(f"{title}: there is no exercise {part.get('exercise')!r}")
    try:
        options = chosen_options(manifest, part.get("options"))
    except ValueError as error:
        raise wrong(f"{title}: {error}") from None
    for name in ("instances", "minutes", "points"):
        if not _whole(part.get(name)) or part[name] <= 0:
            raise wrong(f"{title}: {name} is a whole number above 0")
    scale = part.get("scale") or ""
    if scale and "min" not in manifest.options.get(scale, {}):
        raise wrong(f"{title}: {scale} is not an option of numbers")
    return Part(
        module,
        str(part.get("title") or ""),
        manifest.id,
        options,
        part["instances"],
        part["minutes"],
        part["points"],
        str(part.get("instructions") or ""),
        str(part.get("task") or ""),
        part.get("example"),
        scale,
    )


def exams(
    language: str,
    directory: Path = EVALUATIONS_DIRECTORY,
    exercise_directory: Path | None = None,
) -> dict[str, Exam]:
    """The exams there are of `language`, by level. They are read again
    each time, so that a change to a template is seen at once. Raises
    EvaluationError."""
    folder = directory / language
    if (
        not language
        or not folder.is_dir()
        or folder.resolve().parent != directory.resolve()
    ):
        return {}
    manifests = {
        manifest.id: manifest
        for manifest in (
            exercises(exercise_directory) if exercise_directory else exercises()
        )
    }
    found = {}
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise EvaluationError(f"{path.name}: {error}") from None
        exam = read_exam(data, f"{language}/{path.name}", manifests)
        found[exam.level] = exam
    return found


def scaled(
    exam: Exam, length: int, manifests: dict[str, Manifest]
) -> list[dict[str, Any]]:
    """The parts of `exam` made longer or shorter, for an evaluation of
    `length` half hours: each with its instances, its options and how many
    minutes it takes."""
    factor = 30 * length / exam.minutes
    planned = []
    for part in exam.parts:
        options = dict(part.options)
        wanted = part.instances * factor
        instances = max(1, round(wanted))
        done = instances / part.instances
        if wanted < 1 and part.scale:
            option = manifests[part.exercise].options[part.scale]
            usual = int(options[part.scale])
            fewer = min(option["max"], max(option["min"], round(usual * wanted)))
            options[part.scale] = fewer
            done = fewer / usual
        planned.append(
            {
                "module": part.module,
                "title": part.title,
                "exercise": part.exercise,
                "options": options,
                "instances": instances,
                "minutes": max(1, round(part.minutes * done)),
                "points": part.points,
                "instructions": part.instructions,
            }
        )
    return planned


def describe_part(exam: Exam, part: Part, themes: list[str]) -> str:
    """What an exercise is told of the part of the exam it is: the
    instructions, what the part is like, themes to draw on and an example,
    in the form the exercise has its model reply in."""
    module = next(each for each in exam.modules if each["id"] == part.module)
    lines = [
        f"Exam: {exam.title}, {module['title']}, {part.title}.",
        f"The instructions the learner reads: {part.instructions}",
        f"What the part is like: {part.task}",
    ]
    if themes:
        lines.append(f"Draw on one of these themes: {'; '.join(themes)}.")
    if part.example is not None:
        lines.append(
            "An example of one, in the form to reply in:\n"
            + json.dumps(part.example, ensure_ascii=False)
        )
    return "\n".join(lines)


def score(
    plan: dict[str, Any], scores: list[dict[str, float] | None]
) -> dict[str, Any]:
    """What an evaluation came to, from the scores of its parts in the order
    of `plan`, None for those not done: the score of each of `SCORES`, None
    for what was not shown, and whether it was passed, None if not every
    module was done."""
    parts = plan["parts"]
    found: dict[str, float | None] = {}
    for module in plan["modules"]:
        name = module["id"]
        of = [(part, got) for part, got in zip(parts, scores) if part["module"] == name]
        points = sum(part["points"] for part, _ in of)
        if not points or all(got is None for _, got in of):
            found[name] = None
        else:
            total = sum(part["points"] * (got or {}).get(name, 0.0) for part, got in of)
            found[name] = round(total / points, 1)
        if name in RATED:
            for criterion in CRITERIA:
                rated = [
                    (part["points"], got[criterion])
                    for part, got in of
                    if got and criterion in got
                ]
                weight = sum(each for each, _ in rated)
                found[f"{name}_{criterion}"] = (
                    round(sum(each * value for each, value in rated) / weight, 1)
                    if weight
                    else None
                )
    modules = [module for module in plan["modules"]]
    done = all(found.get(module["id"]) is not None for module in modules)
    weights = sum(module["weight"] for module in modules)
    found["total"] = (
        round(
            sum(module["weight"] * (found[module["id"]] or 0) for module in modules)
            / weights,
            1,
        )
        if done and weights
        else None
    )
    passed: bool | None = None
    if done:
        rule, mark = next(iter(plan["pass"].items()))
        if rule == "total":
            passed = (found["total"] or 0) >= mark
        else:
            passed = all((found[module["id"]] or 0) >= mark for module in modules)
    return {"scores": {name: found.get(name) for name in SCORES}, "passed": passed}


def listed_scores(result: dict[str, Any]) -> str:
    """The scores of an evaluation, one after another."""
    scores = ", ".join(
        f"{name} {value:g}"
        for name, value in result["scores"].items()
        if value is not None
    )
    return scores or PROMPTS("evaluating.scores.none")


def describe_scores(result: dict[str, Any]) -> str:
    """The scores of an evaluation, as its log has them."""
    return PROMPTS("evaluating.scores.listed", scores=listed_scores(result))


def describe_passed(result: dict[str, Any]) -> str:
    if result["passed"] is None:
        return PROMPTS("evaluating.passed.incomplete")
    return PROMPTS(
        "evaluating.passed.yes" if result["passed"] else "evaluating.passed.no"
    )


class Evaluations:
    """The evaluations of one user, each part of which is a session of
    practice."""

    def __init__(
        self,
        store: UserStore,
        practice: Practice,
        directory: Path = EVALUATIONS_DIRECTORY,
        exercise_directory: Path | None = None,
        later: Later = do_now,
        sample: Callable[[list[str], int], list[str]] = random.sample,
    ) -> None:
        self._store = store
        self._practice = practice
        self._directory = directory
        self._exercises = exercise_directory
        self._later = later
        self._sample = sample

    def _manifests(self) -> dict[str, Manifest]:
        found = exercises(self._exercises) if self._exercises else exercises()
        return {manifest.id: manifest for manifest in found}

    def _exams(self, language: str) -> dict[str, Exam]:
        return exams(language, self._directory, self._exercises)

    def levels(self, language: str) -> list[dict[str, Any]]:
        """The exams there are of `language`: the level of each, what it is
        called, how long it takes in full and its modules. Raises
        EvaluationError."""
        return [
            {
                "level": exam.level,
                "exam": exam.title,
                "minutes": exam.minutes,
                "modules": [
                    {
                        **module,
                        "minutes": sum(
                            part.minutes
                            for part in exam.parts
                            if part.module == module["id"]
                        ),
                    }
                    for module in exam.modules
                ],
            }
            for _, exam in sorted(self._exams(language).items())
        ]

    def start(
        self, language: str, level: str, length: int, timed: bool
    ) -> dict[str, Any]:
        """Start an evaluation of `level`, of `length` half hours, timed or
        not. Raises ValueError, and EvaluationError."""
        exam = self._exams(language).get(level)
        if exam is None:
            raise ValueError(f"there is no exam of {language} at {level} yet")
        if not _whole(length) or length not in LENGTHS:
            raise ValueError("an evaluation takes 1 to 8 half hours")
        plan = {
            "exam": exam.title,
            "pass": exam.passing,
            "modules": exam.modules,
            "parts": scaled(exam, length, self._manifests()),
        }
        evaluation = self._store.start_evaluation(
            uuid.uuid4().hex, language, level, length, bool(timed), plan
        )
        return self.describe(evaluation)

    def evaluations(self) -> list[dict[str, Any]]:
        """Every evaluation, the latest first, as `describe` has it."""
        return [self.describe(each) for each in self._store.evaluations()]

    def evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        found = self._store.evaluation(evaluation_id)
        return self.describe(found) if found else None

    def describe(self, evaluation: dict[str, Any]) -> dict[str, Any]:
        """An evaluation with how far each part has got: its session, if it
        was started, whether it is `pending`, `running` or `done`, and its
        scores; with the scores so far, while it runs."""
        parts = []
        for position, part in enumerate(evaluation["plan"]["parts"]):
            session_id = evaluation["sessions"].get(str(position))
            session = self._store.session(session_id) if session_id else None
            status = "pending"
            scores = None
            if session:
                status = "running" if session["status"] == "running" else "done"
                scores = session["progress"][part["exercise"]]["scores"]
            parts.append(
                {**part, "session": session_id, "status": status, "scores": scores}
            )
        described = {**evaluation, "parts": parts}
        if evaluation["result"] is None:
            described["result"] = score(
                evaluation["plan"], [part["scores"] for part in parts]
            )
        return described

    def _running(self, evaluation_id: str) -> dict[str, Any]:
        evaluation = self.evaluation(evaluation_id)
        if evaluation is None:
            raise ValueError("there is no such evaluation")
        if evaluation["status"] != "running":
            raise ValueError("the evaluation is over")
        return evaluation

    def start_part(
        self, evaluation_id: str, position: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Start a part of an evaluation in a session of its own, or take
        up the one it is in. Returns the evaluation and the session. Raises
        ValueError, and EvaluationError."""
        evaluation = self._running(evaluation_id)
        parts = evaluation["parts"]
        if not _whole(position) or not 0 <= position < len(parts):
            raise ValueError("there is no such part")
        part = parts[position]
        if part["status"] == "done":
            raise ValueError("the part is done")
        if part["status"] == "running":
            session = self._store.session(part["session"])
            assert session
            return evaluation, session
        if any(each["status"] == "running" for each in parts):
            raise ValueError("finish the part that is running first")
        language, level = evaluation["language"], evaluation["level"]
        exam = self._exams(language).get(level)
        template = next(
            (
                each
                for each in (exam.parts if exam else [])
                if (each.module, each.title) == (part["module"], part["title"])
            ),
            None,
        )
        if exam is None or template is None:
            raise ValueError(f"the exam of {level} has no part {part['title']} now")
        themes = self._sample(exam.themes, min(THEMES, len(exam.themes)))
        exercise = part["exercise"]
        session, _ = self._practice.start_session(
            language,
            "",
            [],
            {exercise: part["instances"]},
            Choosing(),
            options={exercise: part["options"]},
            minutes={exercise: part["minutes"] if evaluation["timed"] else 0},
            exam=describe_part(exam, template, themes),
            reviewing=[
                lesson["id"]
                for lesson in self._practice.lessons(language)
                if lesson["level"] == level
            ],
        )
        self._store.add_part(evaluation_id, position, session["id"])
        described = self.evaluation(evaluation_id)
        assert described
        return described, session

    def finish_part(
        self,
        evaluation_id: str,
        position: int,
        context: dict[str, str],
        ask: Asker,
        draw: Drawer = cannot_draw,
    ) -> tuple[dict[str, Any], list[Profile]]:
        """Finish the part that is running, and the evaluation with it if
        it was the last. Raises ValueError."""
        evaluation = self._running(evaluation_id)
        parts = evaluation["parts"]
        if not _whole(position) or not 0 <= position < len(parts):
            raise ValueError("there is no such part")
        part = parts[position]
        if part["status"] != "running":
            raise ValueError("the part is not running")
        _, used = self._practice.end_session(
            part["session"], "finished", self._context(evaluation, context), ask, draw
        )
        evaluation = self._running(evaluation_id)
        if all(each["status"] == "done" for each in evaluation["parts"]):
            return self.end(evaluation_id, context, ask, draw, used)
        return evaluation, used

    def end(
        self,
        evaluation_id: str,
        context: dict[str, str],
        ask: Asker,
        draw: Drawer = cannot_draw,
        used: list[Profile] | None = None,
    ) -> tuple[dict[str, Any], list[Profile]]:
        """End an evaluation, after finishing the part that is running, and
        have its log written in the background. It is finished if every
        part was done, and abandoned otherwise. Raises ValueError."""
        used = list(used or [])
        evaluation = self._running(evaluation_id)
        for part in evaluation["parts"]:
            if part["status"] == "running":
                _, finishing = self._practice.end_session(
                    part["session"],
                    "finished",
                    self._context(evaluation, context),
                    ask,
                    draw,
                )
                used += finishing
        evaluation = self._running(evaluation_id)
        parts = evaluation["parts"]
        status = (
            "finished"
            if all(part["status"] == "done" for part in parts)
            else "abandoned"
        )
        result = score(evaluation["plan"], [part["scores"] for part in parts])
        self._store.end_evaluation(evaluation_id, status, result)
        ended = self.evaluation(evaluation_id)
        assert ended
        self._log_later(ended, ask)
        return ended, used

    def _context(
        self, evaluation: dict[str, Any], context: dict[str, str]
    ) -> dict[str, str]:
        """What the exercises are told of the learner: their level is that
        of the exam."""
        return {**context, "level": evaluation["level"]}

    def record(self, evaluation: dict[str, Any]) -> str:
        """What the model that writes the log is told the learner did, part
        by part."""
        blocks = []
        for part in evaluation["parts"]:
            title = f"{part['module']} {part['title']}: {part['exercise']}"
            if part["status"] == "pending":
                blocks.append(f"{title}\n{PROMPTS('evaluating.part.pending')}")
                continue
            grades = self._store.grades(part["session"], part["exercise"])
            written = self._store.written(part["session"], part["exercise"])
            scores = part["scores"] or {}
            scored = listed_scores({"scores": scores})
            done = describe_record(grades, written) or PROMPTS(
                "evaluating.part.nothing"
            )
            blocks.append(
                f"{title}\n{PROMPTS('evaluating.scores.listed', scores=scored)}\n{done}"
            )
        record = "\n\n".join(blocks)
        if len(record) > MAX_RECORD:
            record = record[:MAX_RECORD] + "\n" + PROMPTS("cut")
        return record

    def _log_later(self, evaluation: dict[str, Any], ask: Asker) -> None:
        """Have the log of an evaluation that is over written in the
        background, if any part of it was done."""
        if all(part["status"] == "pending" for part in evaluation["parts"]):
            return
        result = evaluation["result"]
        minutes = sum(part["minutes"] for part in evaluation["plan"]["parts"])
        title = f"{evaluation['plan']['exam']}, {minutes} min"

        def write() -> list[Profile]:
            prompt = PROMPTS(
                "evaluating.log",
                exam=evaluation["plan"]["exam"],
                language=evaluation["language"],
                level=evaluation["level"],
                minutes=minutes,
                timed=PROMPTS(
                    "evaluating.timed.yes"
                    if evaluation["timed"]
                    else "evaluating.timed.no"
                ),
                record=self.record(evaluation),
                scores=listed_scores(result),
                passed=describe_passed(result),
                lines=LOG_LINES,
                worked=MAX_WORKED,
                failed=MAX_FAILED,
            )
            try:
                said, profile = ask([{"role": "user", "content": prompt}])
                content = format_log(read_log(said))
            except (LogError, TranslationError) as error:
                raise ExerciseError(
                    f"the log of {title} could not be written: {error}"
                ) from None
            content += f"\n{describe_scores(result)}\n{describe_passed(result)}"
            self._store.add_log(
                "evaluation",
                evaluation["language"],
                title,
                content,
                {
                    "kind": "evaluation",
                    "evaluation": evaluation["id"],
                    "level": evaluation["level"],
                    "scores": result["scores"],
                    "passed": result["passed"],
                },
            )
            return [profile]

        self._later(title, write)
