# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from profiling import Profile, spent
from tasks import KEPT, Step, Tasks


def test_a_task_is_listed_as_running_until_its_job_is_run() -> None:
    waiting: list[Callable[[], None]] = []
    tasks = Tasks(background=waiting.append, now=lambda: 100.0)

    def job(step: Callable[[], None]) -> tuple[list[dict[str, Any]], list[Any]]:
        step()
        step()
        return [{"word": "Hund", "status": "added"}], [{"id": "gen-1"}]

    started = tasks.start("words", "Der Hund", 2, job)

    assert (started["state"], started["done"], started["total"]) == ("running", 0, 2)
    assert tasks.listing() == [started]

    waiting[0]()

    (finished,) = tasks.listing()
    assert (finished["state"], finished["done"]) == ("done", 2)
    assert finished["result"] == [{"word": "Hund", "status": "added"}]
    assert finished["usage"] == [{"id": "gen-1"}]
    assert finished["finished_at"] == 100.0


def test_a_task_whose_job_breaks_is_listed_as_failed_with_the_reason() -> None:
    tasks = Tasks(background=lambda job: job())

    def job(step: Callable[[], None]) -> tuple[list[dict[str, Any]], list[Any]]:
        raise RuntimeError("the vocabulary is gone")

    tasks.start("words", "Der Hund", 2, job)

    (failed,) = tasks.listing()
    assert (failed["state"], failed["error"]) == ("failed", "the vocabulary is gone")


def test_only_the_newest_tasks_are_remembered_the_newest_first() -> None:
    tasks = Tasks(background=lambda job: job())

    for number in range(KEPT + 2):
        tasks.start("words", str(number), 0, lambda step: ([], []))

    titles = [task["title"] for task in tasks.listing()]
    assert titles == [str(number) for number in range(KEPT + 1, 1, -1)]


def test_what_a_task_used_is_told_once_it_is_done_and_not_when_it_breaks() -> None:
    told: list[tuple[str, list[Any]]] = []
    tasks = Tasks(background=lambda job: job(), on_used=lambda *each: told.append(each))

    def job(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
        return [], [{"id": "gen-1"}]

    def broken(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
        raise RuntimeError("gone")

    tasks.start("icon", "Beim Arzt", 1, job)
    tasks.start("words", "Der Hund", 1, broken)

    assert told == [("icon", [{"id": "gen-1"}])]


def test_what_a_task_that_breaks_had_used_before_is_told_all_the_same() -> None:
    told: list[tuple[str, list[Any]]] = []
    tasks = Tasks(background=lambda job: job(), on_used=lambda *each: told.append(each))

    def broken(step: Callable[[], None]) -> tuple[list[Any], list[Any]]:
        raise spent(RuntimeError("gone"), [Profile({}, id="gen-2", model="m")])

    task = tasks.start("memories", "Recap of the chat", 1, broken)

    assert [each["id"] for each in told[0][1]] == ["gen-2"]
    assert tasks.listing()[0]["id"] == task["id"]
    assert tasks.listing()[0]["state"] == "failed"


def test_what_a_request_of_a_task_used_is_told_as_soon_as_it_is_done() -> None:
    told: list[tuple[str, list[Any]]] = []
    tasks = Tasks(background=lambda job: job(), on_used=lambda *each: told.append(each))
    seen: list[int] = []

    def job(step: Step) -> tuple[list[Any], list[Any]]:
        step.used(Profile({}, id="gen-3", model="m"))
        seen.append(len(told))
        return [], []

    tasks.start("transform", "Der Hund · B1", 1, job)

    assert seen == [1]
    assert [(kind, [each["id"] for each in used]) for kind, used in told] == [
        ("transform", ["gen-3"])
    ]


def test_a_task_is_listed_with_how_its_steps_are_going_as_it_reports_them() -> None:
    waiting: list[Callable[[], None]] = []
    tasks = Tasks(background=waiting.append)
    seen: list[list[dict[str, Any]]] = []

    def job(step: Step) -> tuple[list[dict[str, Any]], list[Any]]:
        step.report([{"state": "writing", "written": 40}])
        seen.append(tasks.listing()[0]["progress"])
        step()
        return [], []

    started = tasks.start("transform", "Ein Buch", 1, job)
    waiting[0]()

    assert started["progress"] == []
    assert seen == [[{"state": "writing", "written": 40}]]
