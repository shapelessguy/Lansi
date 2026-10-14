# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tasks import KEPT, Tasks


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
