# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Keeps track of what is done for a user in the background.

Something that takes a while, such as taking the words of a selection into
the vocabulary, is started as a task and answered at once. What the task is
doing, and what came of it, is asked for afterwards. The tasks are kept
only as long as the server runs, and only the last few of them.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

# how many tasks are remembered, the newest ones
KEPT = 20


@dataclass
class Task:
    """Something done in the background."""

    id: str
    # what kind of thing is done, such as "words"
    kind: str
    # what it is done to, in a few words, to tell the task by
    title: str
    # how many steps there are to it, and how many of them are done
    total: int
    done: int = 0
    # "running", "done" or "failed"
    state: str = "running"
    # when it was started and when it came to an end, in seconds since the epoch
    started_at: float = 0.0
    finished_at: float | None = None
    # why it failed, if it did
    error: str = ""
    # What came of it, once it is done: for words, what became of each.
    result: list[dict[str, Any]] = field(default_factory=list)
    # the requests to the models it made, for whoever keeps count
    usage: list[dict[str, Any]] = field(default_factory=list)


# What a task does. It is given what to call after each step, and returns
# what came of it with the requests to the models it made.
Job = Callable[[Callable[[], None]], tuple[list[dict[str, Any]], list[dict[str, Any]]]]


def run_on_a_thread(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name="task", daemon=True).start()


class Tasks:
    def __init__(
        self,
        background: Callable[[Callable[[], None]], None] = run_on_a_thread,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._background = background
        self._now = now
        # the newest first
        self._tasks: list[Task] = []
        self._lock = threading.Lock()

    def start(self, kind: str, title: str, total: int, job: Job) -> dict[str, Any]:
        """Start `job` in the background, as a task of `total` steps, and
        return the task as it is at the start."""
        task = Task(uuid.uuid4().hex, kind, title, total, started_at=self._now())
        with self._lock:
            self._tasks = [task, *self._tasks][:KEPT]
            started = asdict(task)

        def step() -> None:
            with self._lock:
                task.done += 1

        def run() -> None:
            try:
                result, usage = job(step)
            except Exception as error:
                # whatever went wrong is what the user is told
                with self._lock:
                    task.state, task.error = (
                        "failed",
                        str(error) or type(error).__name__,
                    )
                    task.finished_at = self._now()
                return
            with self._lock:
                task.result, task.usage = result, usage
                task.state, task.finished_at = "done", self._now()

        self._background(run)
        return started

    def listing(self) -> list[dict[str, Any]]:
        """The tasks as they are now, the newest first."""
        with self._lock:
            return [asdict(task) for task in self._tasks]
