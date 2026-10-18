# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any

from kit import ModelError

from oral.backend import act, finish, start

CONTEXT: dict[str, Any] = {
    "language": "German",
    "into": "English",
    "level": "A1",
    "lesson": {"id": "", "level": "A1", "title": "A1", "more_info": "", "points": []},
    "topics": [],
    "instances": 1,
    "options": {"kind": "cards", "prompts": 2},
}
TASK = {
    "card": "Thema: Essen und Trinken",
    "prompts": [
        "Karte: Frühstück. Stellen Sie eine Frage.",
        "Ihr Partner fragt: „Was trinkst du gern?“",
        "one too many",
    ],
}
RATED = {
    "ratings": {"aufgabe": 4, "wortschatz": 2, "strukturen": 2},
    "corrections": ["", "Ich trinke gern Tee."],
    "note": "The verb is second.",
}


class FakeModel:
    """Replies with each of `replies` in turn, as JSON."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.asked: list[str] = []

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        raise ModelError("draws nothing")

    def look(self, messages: list[dict[str, Any]]) -> str:
        return self.ask(messages)

    def ask(self, messages: list[dict[str, Any]]) -> str:
        self.asked.append(messages[-1]["content"])
        return json.dumps(self.replies.pop(0))


def test_a_task_has_as_many_turns_as_were_chosen() -> None:
    step = start(CONTEXT, FakeModel(TASK))

    assert step.show["task"]["prompts"] == TASK["prompts"][:2]


def test_a_task_talked_through_at_once_has_one_turn() -> None:
    model = FakeModel({"card": "Name? · Alter?", "prompts": ["Erzählen Sie.", "more"]})

    step = start({**CONTEXT, "options": {"kind": "introduce", "prompts": 4}}, model)

    assert step.show["task"]["prompts"] == ["Erzählen Sie."]


def test_what_was_said_is_rated_as_a_whole_with_a_correction_of_each_turn() -> None:
    model = FakeModel(TASK, RATED)
    state = start(CONTEXT, model).state

    step = act(
        CONTEXT,
        state,
        {"answers": ["Isst du Frühstück?", "Ich gern Tee trinke."]},
        model,
    )

    assert "typed" in model.asked[1]
    assert "Ich gern Tee trinke." in model.asked[1]
    turns = step.show["feedback"]["turns"]
    assert [turn["correction"] for turn in turns] == ["", "Ich trinke gern Tee."]
    (one,) = step.graded
    # rated 8 of 12, which is not yet right
    assert one["result"] == "partial"
    assert one["note"] == "The verb is second."


def test_speaking_scores_the_ratings_without_pronunciation() -> None:
    model = FakeModel(TASK, RATED)
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"answers": ["Isst du?", "Tee."]}, model).state

    scores = finish(CONTEXT, state, model).scores

    assert scores == {
        "sprechen": 66.7,
        "aufgabe": 100.0,
        "wortschatz": 50.0,
        "strukturen": 50.0,
    }
