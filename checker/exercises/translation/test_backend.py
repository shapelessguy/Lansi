# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any

import pytest
from kit import ModelError

from translation.backend import act, finish, start

CONTEXT = {
    "language": "German",
    "into": "English",
    "level": "",
    "lesson": {
        "id": "trennbare-verben",
        "level": "A1",
        "title": "Trennbare Verben",
        "more_info": "",
        "points": [
            {
                "id": "trennbar-hauptsatz",
                "role": "new",
                "title": "Separable verbs in a main clause",
                "statement": "The prefix goes to the end.",
                "when": "main clause",
            },
            {
                "id": "trennbar-nebensatz",
                "role": "preview",
                "title": "Separable verbs in a subordinate clause",
                "statement": "The verb stays whole at the end.",
                "when": "subordinate clause",
            },
        ],
    },
    "topics": [{"title": "Beim Arzt", "description": "symptoms and appointments"}],
    "instances": 3,
}
ITEMS = {
    "items": [
        {"source": "I get up at six.", "reference": "Ich stehe um sechs auf."},
        {"source": "She calls me.", "reference": "Sie ruft mich an."},
        {"source": "He shops today.", "reference": "Er kauft heute ein."},
        {"source": "We come along.", "reference": "Wir kommen mit."},
        {"source": "You close the door.", "reference": "Du machst die Tür zu."},
        {"source": "They watch TV.", "reference": "Sie sehen fern."},
    ]
}
RIGHT = {"result": "right", "correction": "", "note": ""}
ANSWERS = [
    "Ich  aufstehe um sechs.",
    "Sie ruft mich an.",
    "",
    "Wir kommen mit.",
    "Du machst die Tür zu.",
]


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


def test_a_set_of_five_sentences_is_made_for_the_points_taught_and_the_topics() -> None:
    model = FakeModel(ITEMS)

    step = start(CONTEXT, model)

    assert step.show == {
        "at": 0,
        "total": 3,
        "sources": [
            "I get up at six.",
            "She calls me.",
            "He shops today.",
            "We come along.",
            "You close the door.",
        ],
    }
    prompt = model.asked[0]
    assert "The prefix goes to the end." in prompt
    # what is only previewed is not practised
    assert "The verb stays whole" not in prompt
    assert "Beim Arzt" in prompt
    # with no level of their own, the learner is at that of the lesson
    assert "level A1" in prompt and "4 to 8 words" in prompt


def test_a_set_is_judged_in_one_request_and_logged_once() -> None:
    wrong = {
        "result": "wrong",
        "correction": "Ich stehe um sechs auf.",
        "note": "The prefix goes to the end.",
    }
    model = FakeModel(ITEMS, {"verdicts": [wrong, RIGHT, RIGHT, RIGHT]})
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": ANSWERS}, model)

    assert step.logs == [
        {
            "result": "partial",
            "answer": "Ich aufstehe um sechs. / Sie ruft mich an. /  / Wir kommen mit."
            " / Du machst die Tür zu.",
            "correction": "Ich stehe um sechs auf. / Sie ruft mich an."
            " / Er kauft heute ein. / Wir kommen mit. / Du machst die Tür zu.",
            "note": "1. The prefix goes to the end.",
        }
    ]
    # what was left empty is wrong, and is not sent to be judged
    assert "He shops today." not in model.asked[1]
    assert "Ich aufstehe um sechs." in model.asked[1]
    assert [each["result"] for each in step.show["feedback"]] == [
        "wrong",
        "right",
        "wrong",
        "right",
        "right",
    ]
    assert step.show["feedback"][2]["reference"] == "Er kauft heute ein."
    assert (step.show["more"], step.show["prepared"]) == (True, False)


def test_a_set_with_nothing_written_is_not_judged() -> None:
    model = FakeModel(ITEMS)
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": ["  ", ""]}, model)

    assert (step.logs, step.show["at"], len(model.asked)) == ([], 0, 1)


@pytest.mark.parametrize(
    "verdicts", [{"verdicts": [{"result": "great"}] * 4}, {"verdicts": [RIGHT]}]
)
def test_a_judgement_that_is_not_one_for_each_is_a_failure_and_nothing_is_logged(
    verdicts: object,
) -> None:
    model = FakeModel(ITEMS, verdicts)
    state = start(CONTEXT, model).state

    with pytest.raises(ModelError):
        act(CONTEXT, state, {"answers": ANSWERS}, model)
    assert state["checked"] == []


def test_the_next_set_is_made_once_and_other_than_those_before() -> None:
    model = FakeModel(ITEMS, {"verdicts": [RIGHT] * 4}, ITEMS)
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"answers": ANSWERS}, model).state

    prepared = act(CONTEXT, state, {"prepare": True}, model)
    shown = act(CONTEXT, prepared.state, {"next": True}, model)

    assert prepared.show["prepared"]
    assert len(model.asked) == 3
    assert "- I get up at six." in model.asked[2]
    assert (shown.show["at"], len(shown.show["sources"])) == (1, 5)


def test_what_was_translated_is_in_the_results() -> None:
    model = FakeModel(ITEMS, {"verdicts": [RIGHT] * 4})
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"answers": ANSWERS}, model).state

    results = finish(CONTEXT, state, model).results

    assert results["total"] == 3
    assert results["sets"][0]["result"] == "partial"
    assert results["sets"][0]["items"][0] == {
        "source": "I get up at six.",
        "reference": "Ich stehe um sechs auf.",
    }
    assert results["sets"][0]["feedback"][0]["answer"] == "Ich aufstehe um sechs."
