# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from typing import Any

import pytest
from kit import ModelError

from cloze.backend import (
    act,
    answers_of,
    filled,
    finish,
    hints_of,
    judge,
    parts_of,
    start,
)

LESSON = {
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
        }
    ],
}
CONTEXT = {
    "language": "German",
    "into": "English",
    "level": "A1",
    "lesson": LESSON,
    "topics": [],
    "instances": 2,
}


class FakeModel:
    def __init__(self, reply: object) -> None:
        self.reply = reply
        self.asked: list[list[dict[str, str]]] = []

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        raise ModelError("draws nothing")

    def look(self, messages: list[dict[str, Any]]) -> str:
        return self.ask(messages)

    def ask(self, messages: list[dict[str, Any]]) -> str:
        self.asked.append(messages)
        return f"```json\n{json.dumps(self.reply)}\n```"


ITEMS = {
    "items": [
        {
            "text": "Ich [stehe] um 6 Uhr [auf].",
            "hints": ["stehen", "auf"],
            "translation": "I get up.",
        },
        {
            "text": "Er [kauft|kauft] heute [ein].",
            "hints": ["kaufen"],
            "translation": "",
        },
        {"text": "Ein Satz ohne Lücke.", "hints": [], "translation": ""},
        {"text": "Wir [rufen] dich [an].", "hints": ["rufen", ""], "translation": ""},
        {
            "text": "Du [machst] die Tür [zu].",
            "hints": ["machen", ""],
            "translation": "",
        },
        {"text": "Sie [kommt] [mit].", "hints": ["kommen", ""], "translation": ""},
        {"text": "Ihr [seht] [fern].", "hints": ["sehen", ""], "translation": ""},
    ]
}
RIGHT = [
    ["stehe", "auf"],
    ["kauft", "ein"],
    ["rufen", "an"],
    ["machst", "zu"],
    ["kommt", "mit"],
]


def test_a_sentence_is_shown_with_its_gaps_and_without_what_goes_in_them() -> None:
    assert parts_of("Ich [stehe] um 6 Uhr [auf].") == [
        "Ich ",
        None,
        " um 6 Uhr ",
        None,
        ".",
    ]
    assert parts_of("[Steh] auf!") == [None, " auf!"]


def test_a_gap_may_take_more_than_one_answer() -> None:
    assert answers_of("Er [isst|frisst] gern.") == [["isst", "frisst"]]
    assert filled("Er [isst|frisst] gern.", ["frisst"]) == "Er frisst gern."


@pytest.mark.parametrize(
    "given, result",
    [
        (["stehe", "auf"], "right"),
        (["stehe", " auf "], "right"),
        (["stehe", "an"], "partial"),
        (["Stehe", "auf"], "partial"),
        (["steh", "ab"], "wrong"),
        ([], "wrong"),
    ],
)
def test_an_answer_is_right_only_when_every_gap_is(
    given: list[str], result: str
) -> None:
    assert judge("Ich [stehe] um 6 Uhr [auf].", given)[0] == result


def test_an_answer_that_differs_only_in_an_umlaut_is_partial_with_a_note() -> None:
    result, note = judge("Er [fährt] nach Berlin.", ["faehrt"])

    assert result == "partial"
    assert "faehrt → fährt" in note


def test_a_set_of_five_sentences_with_gaps_is_made_when_it_starts() -> None:
    model = FakeModel(ITEMS)

    step = start(CONTEXT, model)

    assert [item["text"] for item in step.state["sets"][0]] == [
        "Ich [stehe] um 6 Uhr [auf].",
        "Er [kauft|kauft] heute [ein].",
        "Wir [rufen] dich [an].",
        "Du [machst] die Tür [zu].",
        "Sie [kommt] [mit].",
    ]
    assert len(step.show["items"]) == 5
    assert step.show["items"][0]["parts"] == ["Ich ", None, " um 6 Uhr ", None, "."]
    assert (step.show["at"], step.show["total"]) == (0, 2)
    prompt = model.asked[0][0]["content"]
    assert "The prefix goes to the end." in prompt
    # as long and as built as an A1 learner reads
    assert "4 to 8 words" in prompt


def test_each_gap_has_its_own_hint_but_none_that_gives_the_answer_away() -> None:
    model = FakeModel(ITEMS)

    step = start(CONTEXT, model)

    assert step.show["items"][0]["hints"] == ["stehen", ""]
    assert step.show["items"][1]["hints"] == ["kaufen", ""]
    assert hints_of("Er gibt [mir] das [Buch].", ["MIR", 3]) == ["", ""]
    assert hints_of("Ich [möchte] das.", ["moechte"]) == [""]


def test_each_sentence_of_a_set_is_told_the_rule_it_is_centred_on() -> None:
    point: dict[str, str] = {"role": "new", "statement": "", "when": ""}
    lesson = {
        **LESSON,
        "points": [
            {**point, "title": "Separable verbs in a main clause"},
            {**point, "title": "Prefix verbs"},
        ],
    }
    model = FakeModel(ITEMS)

    state = start({**CONTEXT, "lesson": lesson}, model).state
    state = act({**CONTEXT, "lesson": lesson}, state, {"answers": RIGHT}, model).state
    act({**CONTEXT, "lesson": lesson}, state, {"next": True}, model)

    first, second = (asked[0]["content"] for asked in model.asked)
    assert "1. Separable verbs in a main clause\n2. Prefix verbs\n" in first
    assert "another side of it" in first
    # five were made before, so the next set goes on from the second rule
    assert "1. Prefix verbs\n2. Separable verbs in a main clause\n" in second


def test_the_sentences_are_made_heeding_what_the_app_says() -> None:
    model = FakeModel(ITEMS)

    start({**CONTEXT, "guidance": "Do not use: aufstehen"}, model)

    assert "\nDo not use: aufstehen\n" in model.asked[0][0]["content"]


def test_a_model_that_makes_no_sentence_with_a_gap_is_a_failure() -> None:
    with pytest.raises(ModelError):
        start(CONTEXT, FakeModel({"items": [{"text": "Keine Lücke."}]}))


def test_a_set_is_checked_together_and_logged_once_with_its_corrections() -> None:
    model = FakeModel(ITEMS)
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": [["aufstehe", ""], *RIGHT[1:]]}, model)

    assert step.logs == [
        {
            "result": "partial",
            "answer": "Ich aufstehe um 6 Uhr . / Er kauft heute ein. / Wir rufen dich an."
            " / Du machst die Tür zu. / Sie kommt mit.",
            "correction": "Ich stehe um 6 Uhr auf. / Er kauft heute ein."
            " / Wir rufen dich an. / Du machst die Tür zu. / Sie kommt mit.",
            "note": "",
        }
    ]
    assert [each["result"] for each in step.show["feedback"]] == [
        "wrong",
        "right",
        "right",
        "right",
        "right",
    ]
    assert step.show["feedback"][0]["correct"] == "Ich stehe um 6 Uhr auf."
    assert (step.show["at"], step.show["more"], step.show["prepared"]) == (
        1,
        True,
        False,
    )
    # nothing more is made until it is asked for
    assert len(model.asked) == 1


def test_once_a_set_is_checked_the_answers_and_the_right_sentences_are_written() -> (
    None
):
    model = FakeModel(ITEMS)
    state = start(CONTEXT, model).state

    step = act(CONTEXT, state, {"answers": [["aufstehe", ""], *RIGHT[1:]]}, model)

    assert step.written["user"][0] == "aufstehe"
    assert len(step.written["user"]) == 5
    assert step.written["assistant"][0] == "Ich stehe um 6 Uhr auf."
    assert len(step.written["assistant"]) == 5


def test_the_next_set_is_made_once_and_other_than_those_before() -> None:
    model = FakeModel(ITEMS)
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"answers": RIGHT}, model).state

    prepared = act(CONTEXT, state, {"prepare": True}, model)
    again = act(CONTEXT, prepared.state, {"prepare": True}, model)
    shown = act(CONTEXT, again.state, {"next": True}, model)

    assert prepared.show["prepared"] and "feedback" in again.show
    assert len(model.asked) == 2
    assert "- Ich [stehe] um 6 Uhr [auf]." in model.asked[1][0]["content"]
    assert (shown.show["at"], len(shown.show["items"])) == (1, 5)


def test_no_set_is_made_once_every_instance_was_done() -> None:
    model = FakeModel(ITEMS)
    state = start({**CONTEXT, "instances": 1}, model).state

    step = act({**CONTEXT, "instances": 1}, state, {"answers": RIGHT}, model)
    step = act({**CONTEXT, "instances": 1}, step.state, {"prepare": True}, model)

    assert step.show["more"] is False and step.logs == []
    assert step.show["feedback"][0]["result"] == "right"
    assert len(model.asked) == 1


def test_what_was_answered_is_in_the_results_however_far_it_got() -> None:
    model = FakeModel(ITEMS)
    state = start(CONTEXT, model).state
    state = act(CONTEXT, state, {"answers": RIGHT}, model).state

    results: Any = finish(CONTEXT, state, model).results

    assert results["total"] == 2
    assert [made["result"] for made in results["sets"]] == ["right"]
    assert results["sets"][0]["items"][0]["text"] == "Ich [stehe] um 6 Uhr [auf]."
