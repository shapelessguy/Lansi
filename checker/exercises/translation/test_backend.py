# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any
from unittest.mock import ANY

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


def test_a_set_is_judged_in_one_request_and_graded_once_with_its_tasks() -> None:
    wrong = {
        "result": "wrong",
        "correction": "Ich stehe um sechs auf.",
        "note": "The prefix goes to the end.",
    }
    model = FakeModel(ITEMS, {"verdicts": [wrong, RIGHT, RIGHT, RIGHT]})
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": ANSWERS}, model)

    assert step.graded == [
        {
            "result": "partial",
            "task": "1. Translate from English: I get up at six."
            "\n2. Translate from English: She calls me."
            "\n3. Translate from English: He shops today."
            "\n4. Translate from English: We come along."
            "\n5. Translate from English: You close the door.",
            "answer": "1. Ich aufstehe um sechs.\n2. Sie ruft mich an.\n3. (nothing)"
            "\n4. Wir kommen mit.\n5. Du machst die Tür zu.",
            "correction": "1. Ich stehe um sechs auf.\n2. (right)"
            "\n3. Er kauft heute ein.\n4. (right)\n5. (right)",
            "note": "1. The prefix goes to the end.",
            "parts": ANY,
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


def test_once_a_set_is_judged_the_translations_and_the_corrections_are_written() -> (
    None
):
    wrong = {"result": "wrong", "correction": "Ich stehe um sechs auf.", "note": ""}
    model = FakeModel(ITEMS, {"verdicts": [wrong, RIGHT, RIGHT, RIGHT]})
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": ANSWERS}, model)

    assert step.written["user"] == [
        " ".join(answer.split()) for answer in ANSWERS if answer.strip()
    ]
    assert "Ich stehe um sechs auf." in step.written["assistant"]
    # what was left empty is shown the way it is said
    assert "Er kauft heute ein." in step.written["assistant"]


def test_a_set_with_nothing_written_is_not_judged() -> None:
    model = FakeModel(ITEMS)
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": ["  ", ""]}, model)

    assert (step.graded, step.show["at"], len(model.asked)) == ([], 0, 1)


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


def test_each_set_is_reported_as_made_in_the_step_it_is_made_in() -> None:
    model = FakeModel(ITEMS, {"verdicts": [RIGHT] * 4}, ITEMS)
    started = start(CONTEXT, model)
    judged = act(CONTEXT, started.state, {"answers": ANSWERS}, model)

    prepared = act(CONTEXT, judged.state, {"prepare": True}, model)

    [made] = started.made
    assert made == {"items": started.state["sets"][0]}
    assert set(made["items"][0]) == {"source", "reference"}
    assert (judged.made, len(prepared.made)) == ([], 1)


def test_a_set_done_again_is_taken_from_those_made_before_and_only_judged() -> None:
    made = start(CONTEXT, FakeModel(ITEMS)).made
    again = {**CONTEXT, "instances": 1, "replay": made}
    model = FakeModel({"verdicts": [RIGHT] * 4})

    started = start(again, model)
    act(again, started.state, {"answers": ANSWERS}, model)

    assert started.made == []
    assert started.show["sources"] == [item["source"] for item in made[0]["items"]]
    # the only request is the one that judges what was translated
    assert len(model.asked) == 1
