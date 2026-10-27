# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import ANY

import pytest
from anki_import import AnkiUnavailable
from known import known_words
from models import Model
from profiling import Profile, ProfileError, spent_by
from storage import UserStore
from tutor import (
    MAX_FOCUS,
    MAX_TURNS,
    USUAL_KNOWN_WORDS,
    USUAL_RECAPS,
    Done,
    LastCall,
    Tool,
    ToolError,
    TutorError,
    _call_all,
    _date,
    converse,
    data_tools,
    evaluation_tool,
    exercise_tool,
    instructions,
    memory_tools,
    practised,
    read_messages,
    recap,
    wait_for,
    words_tool,
)
from vocabulary import Vocabulary

MODEL = Model("thinker", key="key")
ASKED = [{"role": "user", "content": "What should I practise?"}]

CLOZE = {
    "id": "cloze",
    "title": "Fill the gaps",
    "description": "Fill in the gaps of sentences.",
    "theory": False,
    "options": {
        "sentences": {"label": "Sentences in a set", "min": 1, "max": 10, "default": 5}
    },
}
STORIES = {
    "id": "stories",
    "title": "Stories",
    "description": "Read a short story.",
    "theory": False,
    "options": {
        "then": {
            "label": "Then",
            "choices": {"questions": "Answer questions", "retell": "Retell it"},
        }
    },
}
THEORY = {
    "id": "theory",
    "title": "Theory",
    "description": "Read the lesson.",
    "theory": True,
    "options": {},
}
LESSONS = [
    {"id": "dative", "level": "A2", "title": "The dative"},
    {"id": "perfect", "level": "A2", "title": "The perfect"},
]
TOPICS = [{"id": "t1", "title": "At the doctor's", "description": ""}]


class FakeStream:
    """Streams what it was given for each request in turn, as a model on
    OpenRouter streams it, and keeps the requests."""

    def __init__(self, *replies: list[dict[str, Any]] | Exception) -> None:
        self.replies = list(replies)
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        self.bodies.append(json.loads(json.dumps(body)))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        yield from reply


def delta(**said: Any) -> dict[str, Any]:
    return {"choices": [{"delta": said}]}


def called(
    name: str, arguments: dict[str, Any], call_id: str = "call-1"
) -> list[dict[str, Any]]:
    """The pieces of a call of a tool, its arguments split in two as they
    are streamed."""
    given = json.dumps(arguments)
    half = len(given) // 2
    return [
        delta(
            tool_calls=[
                {
                    "index": 0,
                    "id": call_id,
                    "function": {"name": name, "arguments": given[:half]},
                }
            ]
        ),
        delta(tool_calls=[{"index": 0, "function": {"arguments": given[half:]}}]),
    ]


def chat_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The events the chat shows, without those of each request."""
    return [event for event in events if event["type"] not in ("call", "call_done")]


def answered(text: str) -> list[dict[str, Any]]:
    return [
        delta(content=text),
        {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 3}},
    ]


def echo_tool(name: str = "echo") -> Tool:
    return Tool(
        name,
        "Says what it was called with.",
        {"type": "object", "properties": {}},
        lambda arguments: Done(f"echoed {json.dumps(arguments)}", {"kind": "echo"}),
        lambda _: "Echoing",
    )


def test_the_thinking_and_the_answer_are_told_as_they_come() -> None:
    stream = FakeStream(
        [
            delta(reasoning="Let me "),
            delta(reasoning="think."),
            delta(content="Prac"),
            delta(content="tise the dative."),
        ]
    )
    events: list[dict[str, Any]] = []

    added, _ = converse(ASKED, [], MODEL, "Be a tutor.", events.append, stream)

    assert chat_events(events) == [
        {"type": "thinking", "text": "Let me "},
        {"type": "thinking", "text": "think."},
        {"type": "text", "text": "Prac"},
        {"type": "text", "text": "tise the dative."},
    ]
    assert added == [{"role": "assistant", "content": "Practise the dative."}]
    assert stream.bodies[0]["messages"][0] == {
        "role": "system",
        "content": "Be a tutor.",
    }
    assert stream.bodies[0]["reasoning"] == {"enabled": True}


def test_a_tool_the_model_calls_is_run_and_the_model_is_told_what_it_came_to() -> None:
    stream = FakeStream(called("echo", {"word": "Hund"}), answered("Done."))
    events: list[dict[str, Any]] = []

    added, used = converse(ASKED, [echo_tool()], MODEL, "", events.append, stream)

    shown = chat_events(events)
    assert [event["type"] for event in shown] == ["tool", "tool_done", "text"]
    assert shown[0] == {
        "type": "tool",
        "id": "call-1",
        "name": "echo",
        "doing": "Echoing",
        "arguments": '{"word": "Hund"}',
    }
    assert shown[1] == {
        "type": "tool_done",
        "id": "call-1",
        "failed": False,
        "shown": {"kind": "echo"},
        "content": 'echoed {"word": "Hund"}',
        "ms": ANY,
    }
    assert added[0]["tool_calls"] == [
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "echo", "arguments": '{"word": "Hund"}'},
        }
    ]
    assert added[1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": 'echoed {"word": "Hund"}',
    }
    assert stream.bodies[1]["messages"][-2:] == added[:2]
    assert added[2] == {"role": "assistant", "content": "Done."}
    assert [(each.input_tokens, each.output_tokens) for each in used] == [(9, 3)]


def test_a_tool_that_is_not_there_is_told_to_the_model_as_an_error() -> None:
    stream = FakeStream(called("nothing", {}), answered("Sorry."))
    events: list[dict[str, Any]] = []

    added, _ = converse(ASKED, [echo_tool()], MODEL, "", events.append, stream)

    assert added[1]["content"] == "error: there is no tool nothing"
    assert chat_events(events)[1]["failed"] is True


REASONED = {"type": "reasoning.text", "format": "unknown"}


def test_the_reasoning_the_model_streams_is_handed_back_with_its_message() -> None:
    stream = FakeStream(
        [
            # each piece says its type and format again, as OpenRouter's do
            delta(reasoning_details=[{"index": 0, **REASONED, "text": "Hm"}]),
            delta(reasoning_details=[{"index": 0, **REASONED, "text": "m."}]),
            *called("echo", {}),
        ],
        answered("Done."),
    )

    added, _ = converse(ASKED, [echo_tool()], MODEL, "", lambda _: None, stream)

    assert added[0]["reasoning_details"] == [{**REASONED, "text": "Hmm."}]


def test_a_model_that_cannot_reason_is_asked_again_without_being_told_to() -> None:
    stream = FakeStream(
        ProfileError("OpenRouter refused the request (400): no"), answered("Hi.")
    )

    added, _ = converse(ASKED, [], MODEL, "", lambda _: None, stream)

    assert added == [{"role": "assistant", "content": "Hi."}]
    assert "reasoning" not in stream.bodies[1]


def test_the_model_is_given_no_tools_the_last_time_so_that_it_answers() -> None:
    stream = FakeStream(
        *[called("echo", {}) for _ in range(MAX_TURNS - 1)], answered("At last.")
    )

    added, _ = converse(ASKED, [echo_tool()], MODEL, "", lambda _: None, stream)

    assert added[-1] == {"role": "assistant", "content": "At last."}
    assert "tools" in stream.bodies[-2] and "tools" not in stream.bodies[-1]


def test_the_tutor_cannot_answer_without_a_model_it_can_ask() -> None:
    with pytest.raises(TutorError, match="no model was named"):
        converse(ASKED, [], Model(), "", lambda _: None, FakeStream())


def test_the_exercises_are_one_tool_that_lists_each_with_its_options() -> None:
    [tool] = exercise_tool([CLOZE, STORIES, THEORY], LESSONS, TOPICS)

    assert tool.name == "exercise"
    # what is to be thought of on every call, which some models leave out unless required
    assert tool.parameters["required"] == ["exercise", "lesson", "options", "focus"]
    properties = tool.parameters["properties"]
    assert properties["exercise"]["enum"] == ["cloze", "stories", "theory"]
    assert properties["lesson"]["enum"] == ["dative", "perfect", ""]
    assert properties["topics"]["items"]["enum"] == ["At the doctor's"]
    assert (
        "- cloze: Fill the gaps. Fill in the gaps of sentences. Options: sentences,"
        " Sentences in a set, from 1 to 10, 5 unless another fits better."
    ) in tool.description
    assert "then, Then, one of questions (Answer questions)" in tool.description
    assert "- theory: Theory. Read the lesson. It teaches a lesson" in tool.description


def test_calling_an_exercise_offers_it_with_the_options_it_was_not_called_with_as_usual() -> (
    None
):
    [tool] = exercise_tool([CLOZE, STORIES, THEORY], LESSONS, TOPICS)

    offered = tool.run(
        {
            "exercise": "stories",
            "lesson": "dative",
            "instances": 2,
            "topics": ["At the doctor's"],
        }
    )

    assert offered.shown == {
        "kind": "exercise",
        "exercise": "stories",
        "title": "Stories",
        "theory": False,
        "practises_lesson": True,
        "lesson": "dative",
        "lesson_title": "The dative",
        "instances": 2,
        "topics": ["t1"],
        "topic_titles": ["At the doctor's"],
        "options": {"then": "questions"},
        "labels": {"then": "Answer questions"},
        "focus": "",
        "words": [],
    }
    assert '"lesson_title": "The dative"' in offered.content
    reviewing = tool.run({"exercise": "cloze", "lesson": ""}).shown
    assert reviewing is not None and reviewing["options"] == {"sentences": 5}
    assert reviewing["instances"] == 1


@pytest.mark.parametrize(
    "arguments, error",
    [
        (
            {"exercise": "sing", "lesson": "dative"},
            "there is no exercise 'sing'; there are stories, theory",
        ),
        (
            {"exercise": "stories", "lesson": "genitive", "instances": 2},
            "there is no lesson 'genitive'; the lessons tool lists them",
        ),
        (
            {"exercise": "theory", "lesson": ""},
            "there is no lesson ''; the lessons tool lists them",
        ),
        (
            {"exercise": "stories", "lesson": "dative", "instances": 0},
            "instances is a whole number from 1 to 50",
        ),
        (
            {"exercise": "stories", "lesson": "dative", "options": {"then": "sing"}},
            "then is one of questions, retell",
        ),
        (
            {"exercise": "stories", "lesson": "dative", "options": {"sentences": 3}},
            "stories has no options ['sentences']; it has then",
        ),
        (
            {"exercise": "stories", "lesson": "dative", "topics": ["Space"]},
            "there are no topics ['Space']",
        ),
    ],
)
def test_an_exercise_called_with_what_it_cannot_take_says_why(
    arguments: dict[str, Any], error: str
) -> None:
    [tool] = exercise_tool([STORIES, THEORY], LESSONS, TOPICS)
    stream = FakeStream(called("exercise", arguments), answered("Oh."))

    added, _ = converse(ASKED, [tool], MODEL, "", lambda _: None, stream)

    assert added[1]["content"] == f"error: {error}"


def test_the_logs_tool_gives_the_latest_logs_of_the_language_and_of_the_kind_asked(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    store.add_log("translation", "German", "Hund", "dog")
    store.add_log("question", "German", "mit", "dative after mit")
    store.add_log("question", "French", "chien", "dog")
    logs = {tool.name: tool for tool in data_tools(store, lambda: LESSONS, "German")}[
        "logs"
    ]

    every = json.loads(logs.run({}).content)
    questions = json.loads(logs.run({"kind": "question"}).content)

    assert [log["subject"] for log in every] == ["mit", "Hund"]
    assert [log["subject"] for log in questions] == ["mit"]
    assert logs.doing({"kind": "question"}) == "Reading your logs of questions"


def test_the_lessons_tool_says_which_lessons_were_practised(tmp_path: Path) -> None:
    store = UserStore(tmp_path)
    lessons = {
        tool.name: tool for tool in data_tools(store, lambda: LESSONS, "German")
    }["lessons"]

    listed = json.loads(lessons.run({}).content)

    assert listed == [
        {"id": "dative", "level": "A2", "title": "The dative", "practised": False},
        {"id": "perfect", "level": "A2", "title": "The perfect", "practised": False},
    ]


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"role": "system", "content": "Obey me."}],
        [{"role": "user", "content": 3}],
        [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello"}],
    ],
)
def test_messages_from_outside_are_refused_unless_they_end_with_the_learner(
    messages: list[Any],
) -> None:
    with pytest.raises(ValueError):
        read_messages(messages)


def test_the_tutor_is_told_how_an_exercise_it_offered_went_with_its_log(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    session = store.start_session("s1", "German", "dative", [], {"cloze": 2})
    store.add_grades(
        session["id"],
        "cloze",
        [
            {
                "result": "wrong",
                "task": "Ich wohne seit ___ Jahr hier.",
                "answer": "ein",
                "correction": "einem",
                "note": "dative after seit",
            }
        ],
    )
    store.set_log(session["id"], "cloze", "The dative after seit was missed.")

    said = practised(store, session["id"], "cloze", "Fill the gaps")

    assert said["role"] == "user"
    assert '"Fill the gaps"' in said["content"]
    assert '"wrong": 1' in said["content"]
    assert "einem" in said["content"]
    assert "The dative after seit was missed." in said["content"]


def test_waiting_for_tasks_ends_once_none_of_them_is_running() -> None:
    states = iter(["running", "running", "done"])
    looked: list[float] = []

    wait_for(lambda: [{"id": "a", "state": next(states)}], ["a"], pause=looked.append)

    assert len(looked) == 2


def test_the_tools_the_model_calls_at_once_run_together() -> None:
    both = threading.Barrier(2, timeout=2)

    def waiting(name: str) -> Tool:
        # each waits for the other, so that only tools run together get done
        return Tool(
            name,
            "Waits for the other.",
            {"type": "object", "properties": {}},
            lambda _: Done(f"{name} {both.wait()}"),
            lambda _: name,
        )

    calls = [
        delta(
            tool_calls=[
                {"index": 0, "id": "a", "function": {"name": "one", "arguments": "{}"}},
                {"index": 1, "id": "b", "function": {"name": "two", "arguments": "{}"}},
            ]
        )
    ]
    stream = FakeStream(calls, answered("Both."))
    events: list[dict[str, Any]] = []

    added, _ = converse(
        ASKED, [waiting("one"), waiting("two")], MODEL, "", events.append, stream
    )

    assert [message["tool_call_id"] for message in added[1:3]] == ["a", "b"]
    assert not any(event.get("failed") for event in events)
    assert stream.bodies[0]["parallel_tool_calls"] is True


def test_each_request_is_told_as_it_was_sent_and_with_what_came_of_it() -> None:
    stream = FakeStream(
        [
            {
                "id": "gen-1",
                "model": "thinker-v2",
                "provider": "Somewhere",
                **delta(reasoning="Hm."),
            },
            {"choices": [{"delta": {"content": "Hi."}, "finish_reason": "stop"}]},
            {
                "choices": [],
                "usage": {"prompt_tokens": 9, "completion_tokens": 3, "cost": 0.01},
            },
        ]
    )
    events: list[dict[str, Any]] = []

    converse(ASKED, [echo_tool()], MODEL, "Be a tutor.", events.append, stream)

    call, done = [event for event in events if event["type"] in ("call", "call_done")]
    assert call["id"] == done["id"] == 1
    assert call["request"]["messages"] == [
        {"role": "system", "content": "Be a tutor."},
        *ASKED,
    ]
    assert [tool["function"]["name"] for tool in call["request"]["tools"]] == ["echo"]
    assert done == {
        "type": "call_done",
        "id": 1,
        "message": {"role": "assistant", "content": "Hi."},
        "reasoning": "Hm.",
        "usage": {"prompt_tokens": 9, "completion_tokens": 3, "cost": 0.01},
        "model": "thinker-v2",
        "provider": "Somewhere",
        "generation": "gen-1",
        "finish_reason": "stop",
        "first_ms": ANY,
        "total_ms": ANY,
    }


def test_the_last_call_is_the_last_request_of_the_turn_with_its_tools() -> None:
    stream = FakeStream(
        called("echo", {"word": "Hund"}),
        [*called("echo", {"word": "Katze"}, "call-2"), {"choices": []}],
        answered("Done."),
    )
    last = LastCall("What should I practise?")
    second = LastCall("")
    events: list[dict[str, Any]] = []

    def emit(event: dict[str, Any]) -> None:
        events.append(event)
        last.follow(event)
        # what the turn tells after its second request, which called a tool
        if sum(each["type"] == "call" for each in events) == 2:
            second.follow(event)

    converse(ASKED, [echo_tool()], MODEL, "Be a tutor.", emit, stream)

    record = last.record()
    assert record is not None
    assert record["label"] == "What should I practise?"
    call = record["call"]
    assert call["id"] == 3
    assert call["request"]["messages"][-1]["role"] == "tool"
    assert call["reply"]["message"] == {"role": "assistant", "content": "Done."}
    assert call["reply"]["usage"] == {"prompt_tokens": 9, "completion_tokens": 3}
    assert call["tools"] == []
    kept = second.record()
    assert kept is not None
    assert kept["call"]["tools"] == [
        {
            "id": "call-2",
            "name": "echo",
            "doing": "Echoing",
            "arguments": '{"word": "Katze"}',
            "content": 'echoed {"word": "Katze"}',
            "ms": ANY,
            "failed": False,
        }
    ]


def test_the_last_call_is_none_when_no_request_was_made() -> None:
    last = LastCall("Hallo")

    last.follow({"type": "tool", "id": "log", "name": "", "doing": "Writing the log"})

    assert last.record() is None


def test_a_request_that_failed_is_told_with_why() -> None:
    stream = FakeStream(ProfileError("OpenRouter refused the request (500): down"))
    events: list[dict[str, Any]] = []

    with pytest.raises(TutorError):
        converse(ASKED, [], MODEL, "", events.append, stream)

    assert events[-1]["type"] == "call_done"
    assert events[-1]["error"] == "OpenRouter refused the request (500): down"


def test_a_turn_that_fails_carries_what_the_requests_answered_before_used() -> None:
    stream = FakeStream(
        [
            *called("echo", {"word": "Hund"}),
            {"choices": [], "usage": {"prompt_tokens": 9, "completion_tokens": 3}},
        ],
        ProfileError("OpenRouter refused the request (500): down"),
    )

    with pytest.raises(TutorError) as raised:
        converse(ASKED, [echo_tool()], MODEL, "", lambda _: None, stream)

    assert [used.input_tokens for used in spent_by(raised.value)] == [9]


# made at noon on 1 January 1971, which is that day wherever the tests run
MADE_AT = 365 * 86400 + 12 * 3600
MEMORIES = [
    {"id": 3, "content": "Has the B1 exam on 2026-12-05.", "createdAt": MADE_AT},
    {"id": 4, "content": "Likes football.", "createdAt": MADE_AT},
]


def test_the_tutor_is_told_the_memories_it_has() -> None:
    told = instructions("German", "B1", MEMORIES)

    assert "- [1971-01-01] Likes football." in told
    assert "do not remember anything" in instructions("German", "B1", [])


def test_a_recap_of_a_chat_is_what_the_model_wrote_however_long() -> None:
    told: list[list[dict[str, Any]]] = []

    def ask(messages: list[dict[str, Any]]) -> tuple[str, Profile]:
        told.append(messages)
        lines = [f"- Point {number}." for number in range(8)]
        return "\n\n".join(lines), Profile({}, id="gen-2")

    chat = [{"role": "user", "content": "Can we do the dative?"}]

    written, used = recap(chat, "German", ask)

    assert written.splitlines() == [f"Point {number}." for number in range(8)]
    assert used.id == "gen-2"
    assert "Learner: Can we do the dative?" in told[0][0]["content"]


def test_a_recap_that_says_nothing_is_an_error_that_carries_what_asking_used() -> None:
    with pytest.raises(TutorError) as raised:
        recap([], "German", lambda _: ("  \n", Profile({}, id="gen-1")))

    assert [used.id for used in spent_by(raised.value)] == ["gen-1"]


def test_the_tutor_is_told_how_many_recaps_and_entries_there_are_but_not_what_they_say() -> (
    None
):
    today = time.strftime("%Y-%m-%d")
    tomorrow = time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))
    memories = [
        *MEMORIES,
        {"id": 5, "content": "Chat.", "createdAt": MADE_AT, "kind": "recap"},
        {"id": 6, "content": "Anki first.", "createdAt": MADE_AT, "kind": "strategy"},
        {
            "id": 7,
            "content": "A mock exam of A2.",
            "createdAt": MADE_AT,
            "kind": "calendar",
            "day": today,
        },
        {
            "id": 8,
            "content": "Chapter 3 read.",
            "createdAt": MADE_AT,
            "kind": "calendar",
            "day": tomorrow,
        },
        {
            "id": 9,
            "content": "Chapter 2 read.",
            "createdAt": MADE_AT,
            "kind": "calendar",
            "day": "1971-01-01",
        },
    ]

    told = instructions("German", "B1", memories)

    assert "- [1971-01-01] Likes football." in told
    for kept in ("Chat.", "Anki first.", "A mock exam of A2.", "Chapter 3 read."):
        assert kept not in told
    assert "1 in all, the latest of 1971-01-01" in told
    assert "today: 1; for the next 7 days: 1; for days gone by, still on it: 1" in told
    assert "agreed on how to hold the lessons, which the strategy tool" in told


def test_the_tutor_with_no_strategy_is_told_to_ask_the_learner_for_one() -> None:
    told = instructions("German", "B1", MEMORIES)

    assert "ask them what they would like to do in the lessons to come" in told
    assert "first lesson with your student" in told
    assert "Your calendar is empty." in told


def test_the_recaps_tool_gives_the_latest_recaps_first_as_many_as_asked(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    for number in range(USUAL_RECAPS + 2):
        store.add_memory(f"Chat {number}.\nAgreed on more.", kind="recap")
    recaps = {tool.name: tool for tool in memory_tools(store)}["recaps"]

    usual = json.loads(recaps.run({}).content)
    two = json.loads(recaps.run({"count": 2}).content)

    assert len(usual) == USUAL_RECAPS
    assert [each["recap"] for each in two] == [
        [f"Chat {USUAL_RECAPS + 1}.", "Agreed on more."],
        [f"Chat {USUAL_RECAPS}.", "Agreed on more."],
    ]


def test_a_strategy_agreed_on_is_written_down_and_takes_the_place_of_one_it_replaces(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    old = store.add_memory("Anki first, then an exercise.", kind="strategy")
    tools = {tool.name: tool for tool in memory_tools(store)}

    tools["agree_strategy"].run(
        {"what": "One exercise, then a chapter of the book.", "replaces": [old]}
    )

    [kept] = json.loads(tools["strategy"].run({}).content)
    assert kept["what"] == "One exercise, then a chapter of the book."
    [replaced] = store.memories(removed=True)
    assert (replaced["id"], replaced["removedBy"]) == (old, "tutor")
    with pytest.raises(ToolError):
        tools["agree_strategy"].run({"what": "More.", "replaces": [kept["id"] + 99]})


def test_the_calendar_gives_what_was_planned_by_day_with_what_was_crossed_out(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    tools = {tool.name: tool for tool in memory_tools(store)}
    later = time.strftime("%Y-%m-%d", time.localtime(time.time() + 9 * 86400))
    today = time.strftime("%Y-%m-%d")

    tools["plan"].run({"day": later, "what": "Chapter 3 read."})
    exam = json.loads(tools["plan"].run({"day": today, "what": "A mock exam."}).content)
    tools["cross_out"].run({"id": exam["id"], "why": "done"})

    every = json.loads(tools["calendar"].run({}).content)
    until_today = json.loads(tools["calendar"].run({"to": today}).content)
    assert [(each["day"], each["what"]) for each in every] == [
        (today, "A mock exam."),
        (later, "Chapter 3 read."),
    ]
    assert every[0]["crossed_out"] == {"by": "tutor", "why": "done"}
    assert "crossed_out" not in every[1]
    assert [each["what"] for each in until_today] == ["A mock exam."]


def test_the_calendar_takes_no_day_gone_by_nor_one_that_is_not_a_day(
    tmp_path: Path,
) -> None:
    tools = {tool.name: tool for tool in memory_tools(UserStore(tmp_path))}

    for day in ("2000-01-01", "21.10.26", "2026-02-30", None):
        with pytest.raises(ToolError):
            tools["plan"].run({"day": day, "what": "A mock exam."})
    with pytest.raises(ToolError):
        tools["calendar"].run({"from": "tomorrow"})


def test_a_fact_the_learner_asks_to_be_remembered_is_written_down_at_once_and_once(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    tools = {tool.name: tool for tool in memory_tools(store)}

    first = json.loads(
        tools["remember"].run({"what": " Wants  the words listed first. "}).content
    )
    again = json.loads(
        tools["remember"].run({"what": "wants the words listed first."}).content
    )
    for what in ("", "  ", None, "x" * 601):
        with pytest.raises(ToolError):
            tools["remember"].run({"what": what})

    assert [(each["content"], each["kind"]) for each in store.memories()] == [
        ("Wants the words listed first.", "fact")
    ]
    assert again == {"id": first["id"], "already": True}


def test_only_a_strategy_or_an_entry_of_the_calendar_is_crossed_out(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    fact = store.add_memory("Likes football.")
    tools = {tool.name: tool for tool in memory_tools(store)}

    with pytest.raises(ToolError):
        tools["cross_out"].run({"id": fact, "why": "no longer"})
    assert [each["id"] for each in store.memories()] == [fact]


def test_the_tutor_is_told_the_tone_set_last_with_its_memories_going_first() -> None:
    told = instructions("German", "B1", MEMORIES, "  Friendly,\n but   direct. ")

    assert told.index("Likes football.") < told.index("Friendly, but direct.")
    assert "how much to write, in every message" in told
    assert "Only what your memories say your student asked you for" in told
    # the last word on how to talk
    assert told.rstrip().endswith("as it is what they want now.")


def test_the_tutor_is_told_no_tone_when_none_is_set() -> None:
    told = instructions("German", "B1", MEMORIES, " ")

    assert "Your student set how you are to talk" not in told
    assert "\n\n\n" not in told


CORRECTING = {
    "id": "correcting",
    "title": "Correct my text",
    "description": "Have one of your texts corrected.",
    "theory": False,
    "lesson": False,
    "once": True,
    "options": {
        "text": {"label": "Text", "texts": True, "choices": {"t1": "Wochenende"}}
    },
}


def test_an_exercise_on_a_text_is_called_with_the_text_and_no_lesson() -> None:
    [tool] = exercise_tool([CORRECTING], LESSONS, TOPICS)

    offered = tool.run(
        {"exercise": "correcting", "instances": 3, "options": {"text": "t1"}}
    )

    # done once, on no lesson, it is called with neither
    assert "It practises no lesson" in tool.description
    assert "It is done once" in tool.description
    assert "one of t1 (Wochenende)" in tool.description
    assert offered.shown is not None and offered.shown["instances"] == 1
    assert offered.shown is not None
    assert (offered.shown["lesson"], offered.shown["labels"]) == (
        "",
        {"text": "Wochenende"},
    )


def test_an_answer_offers_one_exercise_and_the_calls_after_are_refused() -> None:
    [cloze] = exercise_tool([CLOZE], LESSONS, TOPICS)
    calls = [
        {
            "id": f"call-{number}",
            "function": {"name": "exercise", "arguments": '{"exercise": "cloze"}'},
        }
        for number in range(3)
    ]
    events: list[dict[str, Any]] = []

    told = _call_all(calls, {"exercise": cloze}, events.append)

    shown = [event["shown"] for event in events if event["type"] == "tool_done"]
    assert sum(each is not None for each in shown) == 1
    assert (
        sum(
            "offered something in this answer already" in each["content"]
            for each in told
        )
        == 2
    )


def test_an_exercise_on_a_text_is_not_offered_where_there_is_no_text() -> None:
    none = {
        **CORRECTING,
        "options": {"text": {"label": "Text", "texts": True, "choices": {}}},
    }

    assert exercise_tool([none], LESSONS, TOPICS) == []


def test_an_exercise_is_steered_by_a_focus_and_the_words_it_is_given() -> None:
    [cloze] = exercise_tool([CLOZE], LESSONS, TOPICS)

    offered = cloze.run(
        {
            "exercise": "cloze",
            "lesson": "dative",
            "instances": 2,
            "focus": "  Every sentence needs seit  with the dative. \n\n1. seit drei Jahren",
            "words": ["Jahr", "seit", "Jahr"],
        }
    )

    # the length is checked on the call, as a provider may decode a call
    # against a long maxLength badly
    assert cloze.parameters["properties"]["focus"] == {
        "type": "string",
        "description": ANY,
    }
    assert offered.shown is not None
    assert offered.shown["focus"] == (
        "Every sentence needs seit with the dative.\n1. seit drei Jahren"
    )
    assert offered.shown["words"] == ["Jahr", "seit"]
    assert "Every sentence needs seit" in offered.content


@pytest.mark.parametrize(
    "steering, error",
    [
        ({"focus": "x" * (MAX_FOCUS + 1)}, "focus is a text"),
        ({"words": ["", "Jahr"]}, "words are at most"),
    ],
)
def test_an_exercise_steered_with_what_it_cannot_take_says_why(
    steering: dict[str, Any], error: str
) -> None:
    [cloze] = exercise_tool([CLOZE], LESSONS, TOPICS)
    stream = FakeStream(
        called("exercise", {"exercise": "cloze", "lesson": "dative", **steering}),
        answered("Oh."),
    )

    added, _ = converse(ASKED, [cloze], MODEL, "", lambda _: None, stream)

    assert added[1]["content"].startswith(f"error: {error}")


LEVELS = [
    {
        "level": "B1",
        "exam": "Zertifikat B1",
        "minutes": 165,
        "sizes": [60, 80, 105, 130, 165],
        "modules": [{"id": "reading", "title": "Lesen"}],
    }
]


class FakeEvaluations:
    def levels(self, language: str) -> list[dict[str, Any]]:
        return LEVELS

    def evaluations(self) -> list[dict[str, Any]]:
        return [
            {
                "language": "German",
                "level": "B1",
                "size": 2,
                "timed": True,
                "status": "finished",
                "started_at": MADE_AT,
                "plan": {"exam": "Zertifikat B1"},
                "result": {"reading": 60.0, "passed": True},
                "parts": [
                    {
                        "module": "reading",
                        "exercise": "comprehension",
                        "minutes": 80,
                        "status": "done",
                        "scores": {"reading": 60.0},
                    }
                ],
            },
            {"language": "French", "level": "A1"},
        ]


def test_the_mock_exams_there_are_and_those_taken_are_looked_up(tmp_path: Path) -> None:
    tools = data_tools(
        UserStore(tmp_path), lambda: LESSONS, "German", FakeEvaluations()
    )
    evaluations = {tool.name: tool for tool in tools}["evaluations"]

    found = json.loads(evaluations.run({}).content)

    assert found["exams"] == [
        {
            "level": "B1",
            "exam": "Zertifikat B1",
            "minutes": 165,
            "minutes_by_size": [60, 80, 105, 130, 165],
            "modules": ["Lesen"],
        }
    ]
    [taken] = found["taken"]
    assert (taken["level"], taken["result"]["passed"]) == ("B1", True)
    assert (taken["size"], taken["minutes"]) == (2, 80)
    assert taken["parts"][0]["scores"] == {"reading": 60.0}


def test_a_mock_exam_is_offered_of_a_level_there_is_an_exam_of_and_a_size_it_has() -> (
    None
):
    [offer] = evaluation_tool(LEVELS)

    offered = offer.run({"level": "B1", "size": 3, "timed": True})

    assert offered.shown == {
        "kind": "evaluation",
        "level": "B1",
        "exam": "Zertifikat B1",
        "size": 3,
        "minutes": 105,
        "timed": True,
    }
    assert offer.parameters["properties"]["level"]["enum"] == ["B1"]
    size = offer.parameters["properties"]["size"]
    assert size["maximum"] == 5
    assert "B1: 60 min, 80 min, 105 min, 130 min, 165 min" in size["description"]
    assert evaluation_tool([]) == []
    with pytest.raises(ToolError):
        offer.run({"level": "C2", "size": 3})
    with pytest.raises(ToolError):
        offer.run({"level": "B1", "size": 6})


PRACTISED = ["noun", "verb"]


def known_vocabulary() -> Vocabulary:
    """A vocabulary with a noun the learner used, a noun a model wrote, a
    verb nobody used, and a set of the nouns."""
    vocabulary = Vocabulary()
    hund, _ = vocabulary.save("noun", "Hund", {}, [])
    katze, _ = vocabulary.save("noun", "Katze", {}, [])
    vocabulary.save("verb", "gehen", {}, [])
    vocabulary.record_uses("message", "c", 0, "user", 10.0, [(hund.id, "hund")])
    vocabulary.record_uses("message", "c", 1, "assistant", 20.0, [(katze.id, "katze")])
    vocabulary.save_set(
        "s1", {"id": "s1", "name": "Nouns", "rules": {"verb": {"included": False}}}
    )
    return vocabulary


def test_the_words_tool_gives_the_words_known_as_they_are_asked_for() -> None:
    vocabulary = known_vocabulary()
    words = words_tool(
        partial(known_words, vocabulary), ["Nouns"], anki=False, practised=PRACTISED
    )

    first = json.loads(words.run({}).content)
    least = json.loads(words.run({"reverse": True, "count": 2}).content)
    of_set = json.loads(
        words.run({"set": "Nouns", "sorted_by": "alphabetical"}).content
    )
    verbs = json.loads(words.run({"categories": ["verb"]}).content)

    assert [word["word"] for word in first["words"]] == ["Katze", "Hund", "gehen"]
    assert first["words"][1] == {
        "word": "Hund",
        "categories": ["noun"],
        "used": 1,
        "seen": 0,
        "last_used_by_user": _date(10.0),
        "last_used_by_assistant": None,
    }
    assert ([word["word"] for word in least["words"]], least["total"]) == (
        ["gehen", "Hund"],
        3,
    )
    assert [word["word"] for word in of_set["words"]] == ["Hund", "Katze"]
    assert [word["word"] for word in verbs["words"]] == ["gehen"]


def test_the_words_tool_offers_the_sets_and_anki_only_where_there_are_any() -> None:
    bare = words_tool(partial(known_words, None), [], anki=False, practised=PRACTISED)
    full = words_tool(
        partial(known_words, None), ["Nouns"], anki=True, practised=PRACTISED
    )

    assert {"set", "anki_only"}.isdisjoint(bare.parameters["properties"])
    assert full.parameters["properties"]["set"]["enum"] == ["Nouns"]
    assert "anki_only" in full.parameters["properties"]
    assert full.doing({"anki_only": True}) == "Looking at the words you know from Anki"


def test_the_words_tool_gives_only_the_anki_words_when_asked() -> None:
    known = partial(known_words, known_vocabulary(), anki_words=lambda: ["Katze"])
    words = words_tool(known, [], anki=True, practised=PRACTISED)

    found = json.loads(words.run({"anki_only": True}).content)

    assert [word["word"] for word in found["words"]] == ["Katze"]


def test_the_words_tool_tells_the_model_what_it_cannot_give() -> None:
    def unreachable() -> list[str]:
        raise AnkiUnavailable("the deck-status server cannot be reached")

    known = partial(known_words, known_vocabulary(), anki_words=unreachable)
    words = words_tool(known, [], anki=True, practised=PRACTISED)

    refused: list[tuple[dict[str, Any], str]] = [
        ({"categories": ["colour"]}, "there is no category colour"),
        ({"sorted_by": "loudest"}, "sorted_by must be one of"),
        ({"set": "Verbs"}, "no such set"),
        ({"anki_only": True}, "the deck-status server cannot be reached"),
        ({"count": 0}, "count is a whole number"),
    ]
    for arguments, said in refused:
        with pytest.raises(ToolError, match=said):
            words.run(arguments)


def test_the_words_tool_gives_the_usual_number_of_words_unless_told_otherwise() -> None:
    vocabulary = Vocabulary()
    for number in range(USUAL_KNOWN_WORDS + 5):
        vocabulary.save("noun", f"Wort{number}", {}, [])
    words = words_tool(partial(known_words, vocabulary), [], False, PRACTISED)

    usual = json.loads(words.run({}).content)
    more = json.loads(words.run({"count": USUAL_KNOWN_WORDS + 5}).content)

    assert len(usual["words"]) == USUAL_KNOWN_WORDS
    assert len(more["words"]) == USUAL_KNOWN_WORDS + 5


def test_the_words_tool_tells_the_model_which_categories_to_build_on() -> None:
    words = words_tool(partial(known_words, None), [], False, ["noun", "particle"])

    assert "noun, particle" in words.description
    assert str(USUAL_KNOWN_WORDS) in words.description


def test_the_tutor_does_not_see_a_session_left_before_anything_was_done_in_it(
    tmp_path: Path,
) -> None:
    store = UserStore(tmp_path)
    store.start_session("s1", "German", "dative", [], {"cloze": 1})
    store.hide_session("s1")
    tools = {tool.name: tool for tool in data_tools(store, lambda: LESSONS, "German")}

    sessions = json.loads(tools["sessions"].run({}).content)
    lessons = json.loads(tools["lessons"].run({}).content)

    assert sessions == []
    assert not any(lesson["practised"] for lesson in lessons)
