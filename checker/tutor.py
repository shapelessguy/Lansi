# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The tutor: a chat with a model that reasons, and that calls tools to
find out what the learner has done and to offer them practice.

A tool is the same to the tutor whatever it does: a name, what it is for,
the JSON schema of what it is called with, and what runs it, which may
look something up or ask a model of its own. Each exercise of practice is
a tool, whose parameters are those of its manifest; calling it offers the
exercise to the learner, who decides whether to start it.

The tutor is answered as it goes: `converse` tells whoever asked each
event as it comes, so that the chat can show what the model is thinking
and what it is doing while the answer is still to come:

    {"type": "thinking", "text": ...}    a piece of what the model reasons
    {"type": "text", "text": ...}        a piece of the answer
    {"type": "tool", "id": ..., "name": ..., "doing": ...}
                                         a tool was called; `doing` says
                                         what it does, for the learner
    {"type": "tool_done", "id": ..., "failed": ..., "shown": ...}
                                         it is done; `shown` is what the
                                         chat is to show of it, such as an
                                         exercise offered, or null

and, for whoever wants to see what the model is told and what it costs,
each request to the model as it is sent and what came of it:

    {"type": "call", "id": ..., "at": ..., "request": {...}}
                                         the request, as it was sent, with
                                         when, in seconds since the epoch
    {"type": "call_done", "id": ..., "message": {...}, "reasoning": ...,
     "usage": {...}, "model": ..., "provider": ..., "generation": ...,
     "finish_reason": ..., "first_ms": ..., "total_ms": ...}
                                         what it came to: the message, all
                                         that was reasoned, the usage as
                                         the model reported it, and how
                                         long the first piece and the whole
                                         took; or `"error": ...`

The `tool` event also has the `arguments` the tool was called with, and
`tool_done` what the model is told it came to, its `content`, and how long
it took, `ms`.

What the tutor is told is in prompts/tutor/.
"""

from __future__ import annotations

import itertools
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from intake import CHAT_TIMEOUT_SECS, read_usage
from logs import describe_record, read_json
from models import Model
from profiling import Profile, ProfileError, error_message
from prompts import PROMPTS
from storage import LOG_KINDS
from translating import TranslationError

# Sends a chat request to a model to be streamed, and gives each piece of
# the response as it comes. Raises ProfileError.
Stream = Callable[[dict[str, Any], Model], Iterator[dict[str, Any]]]
Emit = Callable[[dict[str, Any]], None]

# how many times the model may be asked for one answer, calling tools in
# between; the last time, it is given no tools, so that it answers
MAX_TURNS = 8
# what comes a bit at a time in the pieces of a streamed response: the text
# of reasoning or its summary, and the arguments of a call of a tool
STREAMED = ("text", "summary", "arguments")
# how long the focus an exercise is steered with may be, and how many words
# it may be given
MAX_FOCUS = 600
MAX_WORDS = 30
# how many tools called at once are run together at most
MAX_AT_ONCE = 8
# the most of the mock exams taken that the tool that lists them gives, and
# how many half hours one may take
MAX_EVALUATIONS = 10
MAX_HALF_HOURS = 8
# the most of each that a tool that lists them gives
MAX_SESSIONS = 20
MAX_LOGS = 50
# how many instances of an exercise may be offered, as practice allows
MAX_INSTANCES = 50
# how long the log of an exercise done in the chat is waited for, and how
# often whether it is written is looked at meanwhile
LOG_WAIT_SECS = 120
LOG_LOOK_SECS = 0.25
# The roles of the messages of a chat with the tutor that came in from
# outside, and how many of them there may be.
ROLES = ("user", "assistant", "tool")
MAX_MESSAGES = 200


class TutorError(Exception):
    """The tutor could not answer. The message says why."""


class ToolError(Exception):
    """A tool was called with what it cannot take. The message, which the
    model is told, says why."""


@dataclass
class Done:
    """What a tool came to."""

    # what the model is told
    content: str
    # what the chat is to show of it, or None for nothing
    shown: dict[str, Any] | None = None


@dataclass
class Tool:
    name: str
    description: str
    # the JSON schema of what it is called with
    parameters: dict[str, Any]
    # runs it on what it was called with. Raises ToolError.
    run: Callable[[dict[str, Any]], Done]
    # what it does, for the learner, by what it was called with
    doing: Callable[[dict[str, Any]], str]

    def described(self) -> dict[str, Any]:
        """The tool as a chat request gives it to the model."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def instructions(
    language: str, into: str, level: str, memories: list[dict[str, Any]]
) -> str:
    """What the tutor is told before the chat, with the `memories` it has
    of the learner."""
    listed = "\n".join(
        f"- [{_day(memory['createdAt'])}] {memory['content']}" for memory in memories
    )
    return PROMPTS(
        "tutor.system",
        language=language,
        into=into,
        level=level or "unknown",
        today=time.strftime("%Y-%m-%d"),
        memories=PROMPTS("tutor.memories.listed", memories=listed)
        if memories
        else PROMPTS("tutor.memories.none"),
    )


@dataclass
class Remembered:
    """What the tutor is to remember of a chat: new memories, and those to
    forget by their ids, each with why."""

    add: list[str]
    remove: list[tuple[int, str]]


def remember(
    chat: list[dict[str, str]],
    memories: list[dict[str, Any]],
    language: str,
    ask: Callable[[list[dict[str, Any]]], tuple[str, Profile]],
) -> tuple[Remembered, Profile]:
    """What the tutor is to remember of a `chat` that is over, what the
    learner wrote and what it answered, with the `memories` it has, as the
    model `ask` asks decides, and what asking it used. A memory to forget
    that the tutor does not have is left out. Raises TutorError."""
    said = "\n\n".join(
        f"{'Learner' if message['role'] == 'user' else 'Tutor'}: {message['content']}"
        for message in chat
    )
    listed = "\n".join(
        f"- [id {memory['id']}, {_day(memory['createdAt'])}] {memory['content']}"
        for memory in memories
    )
    prompt = PROMPTS(
        "tutor.remembering",
        language=language,
        today=time.strftime("%Y-%m-%d"),
        memories=listed or "none",
        chat=said,
    )
    try:
        reply, used = ask([{"role": "user", "content": prompt}])
    except TranslationError as error:
        raise TutorError(str(error)) from None
    found = read_json(reply)
    if not isinstance(found, dict):
        raise TutorError("the model did not say what to remember as it was asked")
    added = found.get("add")
    removed = found.get("remove")
    have = {memory["id"] for memory in memories}
    # what the tutor remembers already is not remembered twice
    known = {" ".join(memory["content"].split()).casefold() for memory in memories}
    return (
        Remembered(
            [
                " ".join(each.split())
                for each in (added if isinstance(added, list) else [])
                if isinstance(each, str)
                and each.strip()
                and " ".join(each.split()).casefold() not in known
            ],
            [
                (each["id"], str(each.get("why") or ""))
                for each in (removed if isinstance(removed, list) else [])
                if isinstance(each, dict) and each.get("id") in have
            ],
        ),
        used,
    )


def _day(seconds: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(seconds))


def converse(
    messages: list[dict[str, Any]],
    tools: list[Tool],
    model: Model,
    told: str,
    emit: Emit,
    stream: Stream | None = None,
) -> tuple[list[dict[str, Any]], list[Profile]]:
    """Answer the last of `messages`, the chat so far as the model was told
    it, with the model having been `told` what it is first. The model may
    call `tools`, as often as it needs, before it answers. `emit` is told
    each event as it comes, as the module says. Returns the messages that
    were added, the calls of the tools and what they came to among them,
    the answer last, with what the requests to the model used. Raises
    TutorError."""
    problem = model.problem()
    if problem:
        raise TutorError(problem)
    send = stream or stream_chat
    by_name = {tool.name: tool for tool in tools}
    numbers = itertools.count(1)
    added: list[dict[str, Any]] = []
    used: list[Profile] = []
    for turn in range(MAX_TURNS):
        body: dict[str, Any] = {
            "model": model.name,
            "messages": [{"role": "system", "content": told}, *messages, *added],
            "stream": True,
            "reasoning": {"enabled": True},
            # what is looked up in different places is asked for at once
            "parallel_tool_calls": True,
            "usage": {"include": True},
        }
        if tools and turn < MAX_TURNS - 1:
            body["tools"] = [tool.described() for tool in tools]
        message, usage = _ask(body, model, send, emit, numbers)
        if usage:
            used.append(usage)
        added.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            return added, used
        added += _call_all(calls, by_name, emit)
    raise TutorError("the model kept calling tools and never answered")


def _ask(
    body: dict[str, Any],
    model: Model,
    send: Stream,
    emit: Emit,
    numbers: Iterator[int],
) -> tuple[dict[str, Any], Profile | None]:
    """Ask the model once, telling `emit` the request, what the model thinks
    and writes as it comes, and what came of it, and return the message it
    came to, with what it used. A model that cannot reason is asked again
    without being told to."""
    try:
        return _send(body, model, send, emit, next(numbers))
    except ProfileError as error:
        if "(400)" not in str(error):
            raise TutorError(str(error)) from None
    body = {name: value for name, value in body.items() if name != "reasoning"}
    try:
        return _send(body, model, send, emit, next(numbers))
    except ProfileError as error:
        raise TutorError(str(error)) from None


def _send(
    body: dict[str, Any], model: Model, send: Stream, emit: Emit, number: int
) -> tuple[dict[str, Any], Profile | None]:
    """Send one request, telling `emit` it as it was sent and what came of
    it. Raises ProfileError."""
    emit({"type": "call", "id": number, "at": time.time(), "request": body})
    took = Took()
    try:
        message, usage, about = _gather(send(body, model), model, emit, took)
    except ProfileError as error:
        emit({"type": "call_done", "id": number, "error": str(error), **took.ms()})
        raise
    emit({"type": "call_done", "id": number, "message": message, **about, **took.ms()})
    return message, usage


class Took:
    """How long a request took: to its first piece, and to its end."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.first: float | None = None

    def came(self) -> None:
        if self.first is None:
            self.first = time.monotonic()

    def ms(self) -> dict[str, int | None]:
        def since(moment: float | None) -> int | None:
            return None if moment is None else round((moment - self.started) * 1000)

        return {"first_ms": since(self.first), "total_ms": since(time.monotonic())}


def _gather(
    pieces: Iterator[dict[str, Any]], model: Model, emit: Emit, took: Took
) -> tuple[dict[str, Any], Profile | None, dict[str, Any]]:
    """The message the pieces of a streamed response come to, with what
    the request used and what is known of it, telling `emit` each piece of
    thinking and of text, and `took` when the first piece came."""
    text: list[str] = []
    thoughts: list[str] = []
    about: dict[str, Any] = {
        "reasoning": "",
        "usage": None,
        "model": None,
        "provider": None,
        "generation": None,
        "finish_reason": None,
    }
    # by their index, as they come in pieces
    calls: dict[int, dict[str, Any]] = {}
    details: dict[int, dict[str, Any]] = {}
    usage = None
    for piece in pieces:
        if isinstance(piece.get("error"), dict):
            raise ProfileError(f"{model.where} failed: {piece['error'].get('message')}")
        took.came()
        if isinstance(piece.get("usage"), dict):
            usage = read_usage(piece, model.name)
            about["usage"] = piece["usage"]
        for name, said in (
            ("model", "model"),
            ("provider", "provider"),
            ("generation", "id"),
        ):
            if isinstance(piece.get(said), str):
                about[name] = piece[said]
        choices = piece.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            about["finish_reason"] = (
                choices[0].get("finish_reason") or about["finish_reason"]
            )
        delta = (
            choices[0].get("delta") if isinstance(choices, list) and choices else None
        )
        if not isinstance(delta, dict):
            continue
        if isinstance(thought := delta.get("reasoning"), str) and thought:
            thoughts.append(thought)
            emit({"type": "thinking", "text": thought})
        if isinstance(written := delta.get("content"), str) and written:
            text.append(written)
            emit({"type": "text", "text": written})
        for detail in delta.get("reasoning_details") or []:
            if isinstance(detail, dict):
                _merge(
                    details.setdefault(detail.get("index", len(details)), {}), detail
                )
        for call in delta.get("tool_calls") or []:
            if isinstance(call, dict):
                _merge(calls.setdefault(call.get("index", len(calls)), {}), call)
    message: dict[str, Any] = {"role": "assistant", "content": "".join(text)}
    if calls:
        message["tool_calls"] = [
            {
                "id": call.get("id") or f"call_{index}",
                "type": "function",
                "function": {
                    "name": call.get("function", {}).get("name", ""),
                    "arguments": call.get("function", {}).get("arguments") or "{}",
                },
            }
            for index, call in sorted(calls.items())
        ]
    if details:
        # handed back with the message, for a model that goes on reasoning
        # from where it was
        message["reasoning_details"] = [
            {name: value for name, value in detail.items() if name != "index"}
            for _, detail in sorted(details.items())
        ]
    about["reasoning"] = "".join(thoughts)
    return message, usage, about


def _merge(into: dict[str, Any], piece: dict[str, Any]) -> None:
    """Add a piece of something streamed to what came of it before: what
    comes a bit at a time is joined on, and anything else, such as the
    type that each piece of reasoning says again, is taken as it is."""
    for name, value in piece.items():
        if isinstance(value, dict):
            _merge(into.setdefault(name, {}), value)
        elif (
            name in STREAMED
            and isinstance(value, str)
            and isinstance(into.get(name), str)
        ):
            into[name] += value
        elif value is not None:
            into[name] = value


def _call_all(
    calls: list[dict[str, Any]], tools: dict[str, Tool], emit: Emit
) -> list[dict[str, Any]]:
    """Run the tools the model called at once, all together, telling `emit`
    what each does as it starts and as it ends, and return the messages
    that tell the model what they came to, in the order they were called."""
    lock = threading.Lock()

    def told(event: dict[str, Any]) -> None:
        with lock:
            emit(event)

    if len(calls) == 1:
        return [_call(calls[0], tools, told)]
    with ThreadPoolExecutor(max_workers=min(len(calls), MAX_AT_ONCE)) as pool:
        return list(pool.map(lambda call: _call(call, tools, told), calls))


def _call(call: dict[str, Any], tools: dict[str, Tool], emit: Emit) -> dict[str, Any]:
    """Run the tool a model called, telling `emit` what it does, and return
    the message that tells the model what it came to."""
    name = call["function"]["name"]
    tool = tools.get(name)
    try:
        arguments = json.loads(call["function"]["arguments"])
    except ValueError:
        arguments = None
    emit(
        {
            "type": "tool",
            "id": call["id"],
            "name": name,
            "doing": tool.doing(arguments if isinstance(arguments, dict) else {})
            if tool
            else f"Calling {name}",
            "arguments": call["function"]["arguments"],
        }
    )
    started = time.monotonic()
    try:
        if tool is None:
            raise ToolError(f"there is no tool {name}")
        if not isinstance(arguments, dict):
            raise ToolError("a tool is called with a JSON object")
        done = tool.run(arguments)
    except ToolError as error:
        done, failed = Done(f"error: {error}"), True
    else:
        failed = False
    emit(
        {
            "type": "tool_done",
            "id": call["id"],
            "failed": failed,
            "shown": done.shown,
            "content": done.content,
            "ms": round((time.monotonic() - started) * 1000),
        }
    )
    return {"role": "tool", "tool_call_id": call["id"], "content": done.content}


def stream_chat(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
    """Send a chat request to `model` and give each piece of its streamed
    response as it comes. Raises ProfileError."""
    request = urllib.request.Request(
        model.endpoint("chat/completions"),
        data=json.dumps(body).encode(),
        headers={**model.headers(), "Content-Type": "application/json"},
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=CHAT_TIMEOUT_SECS)
    except urllib.error.HTTPError as error:
        raise ProfileError(error_message(error, model.where)) from None
    except OSError as error:
        raise ProfileError(f"could not reach {model.where}: {error}") from None
    with response:
        try:
            for line in response:
                # each piece is a line of server-sent events; the others
                # are comments that keep the connection open
                data = line.decode("utf-8").strip().removeprefix("data:").strip()
                if not line.startswith(b"data:") or not data:
                    continue
                if data == "[DONE]":
                    return
                piece = json.loads(data)
                if isinstance(piece, dict):
                    yield piece
        except (OSError, ValueError) as error:
            raise ProfileError(
                f"the answer of {model.where} broke off: {error}"
            ) from None


def read_messages(value: object, to_answer: bool = True) -> list[dict[str, Any]]:
    """The messages of a chat with the tutor that came in from outside, as
    the model was told them: what the learner wrote, what the tutor
    answered with the tools it called, and what they came to. A chat
    `to_answer` ends with what the learner wrote. Raises ValueError."""
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_MESSAGES:
        raise ValueError(f"messages must be a list of 1 to {MAX_MESSAGES}")
    for message in value:
        if not isinstance(message, dict) or message.get("role") not in ROLES:
            raise ValueError(f"each message has a role, one of {', '.join(ROLES)}")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise ValueError("the content of a message is text")
    if to_answer and value[-1]["role"] != "user":
        raise ValueError("the last message is what the learner wrote")
    return value


def wait_for(
    listing: Callable[[], list[dict[str, Any]]],
    ids: list[str],
    within: float = LOG_WAIT_SECS,
    pause: Callable[[float], None] = time.sleep,
) -> None:
    """Wait until none of the tasks `ids` names is running, as `listing`
    has them, or `within` seconds have gone by."""
    give_up_at = time.monotonic() + within
    while time.monotonic() < give_up_at and any(
        task["id"] in ids and task["state"] == "running" for task in listing()
    ):
        pause(LOG_LOOK_SECS)


def practised(store: Any, session_id: str, exercise: str, title: str) -> dict[str, Any]:
    """What the tutor is told, as if the learner said it, once the
    `exercise` of a session it offered, which goes by `title`, has been
    done: how it went, what was answered, and its log. Raises ValueError
    if there is no such exercise."""
    session = store.session(session_id)
    if session is None or exercise not in session["progress"]:
        raise ValueError("there is no such exercise of a session")
    progress = session["progress"][exercise]
    log = store.logs(session_id).get(exercise)
    content = PROMPTS(
        "tutor.practised",
        title=title,
        status=session["status"] if session["status"] != "running" else "finished",
        results=json.dumps(
            {**progress["results"], "scores": progress["scores"]}, ensure_ascii=False
        ),
        grades=describe_record(store.grades(session_id, exercise), {}),
        log=log or "none",
    )
    return {"role": "user", "content": content}


def data_tools(
    store: Any,
    lessons: Callable[[], list[dict[str, Any]]],
    language: str,
    evaluations: Any = None,
) -> list[Tool]:
    """The tools that look up what the learner has done: in `store`, their
    sessions and logs, and the `lessons` of the `language` they learn."""

    def practised() -> set[str]:
        return {session["lesson"] for session in store.sessions() if session["lesson"]}

    def list_lessons(_: dict[str, Any]) -> Done:
        done = practised()
        listed = [
            {
                "id": lesson["id"],
                "level": lesson["level"],
                "title": lesson["title"],
                "practised": lesson["id"] in done,
            }
            for lesson in lessons()
        ]
        return Done(json.dumps(listed, ensure_ascii=False))

    def list_sessions(arguments: dict[str, Any]) -> Done:
        count = _count(arguments, MAX_SESSIONS)
        listed = [
            {
                "started": _date(session["started_at"]),
                "lesson": session["lesson"] or "review",
                "status": session["status"],
                "exercises": {
                    exercise: {
                        **progress["results"],
                        "scores": progress["scores"],
                    }
                    for exercise, progress in session["progress"].items()
                },
            }
            for session in store.sessions()
            if session["language"] == language
        ][:count]
        return Done(json.dumps(listed, ensure_ascii=False))

    def list_logs(arguments: dict[str, Any]) -> Done:
        count, kind = _count(arguments, MAX_LOGS), arguments.get("kind")
        if kind is not None and kind not in LOG_KINDS:
            raise ToolError(f"there are no logs of the kind {kind!r}")
        listed: list[dict[str, Any]] = []
        before = None
        # read a page at a time, as only those of a kind may be wanted
        while len(listed) < count:
            page = store.all_logs(before, MAX_LOGS)
            if not page:
                break
            listed += [
                {
                    "id": log["id"],
                    "kind": log["kind"],
                    "written": _date(log["writtenAt"]),
                    "subject": log["subject"],
                    "content": log["content"],
                }
                for log in page
                if log["language"] == language and kind in (None, log["kind"])
            ]
            before = page[-1]["id"]
        return Done(json.dumps(listed[:count], ensure_ascii=False))

    def counted(most: int) -> dict[str, Any]:
        return {
            "type": "integer",
            "minimum": 1,
            "maximum": most,
            "description": PROMPTS("tutor.tools.count", most=most),
        }

    kinds = ", ".join(LOG_KINDS)
    return [
        Tool(
            "lessons",
            PROMPTS("tutor.tools.lessons"),
            {"type": "object", "properties": {}},
            list_lessons,
            lambda _: "Looking at the lessons",
        ),
        Tool(
            "sessions",
            PROMPTS("tutor.tools.sessions"),
            {"type": "object", "properties": {"count": counted(MAX_SESSIONS)}},
            list_sessions,
            lambda _: "Looking at your latest sessions of practice",
        ),
        Tool(
            "logs",
            PROMPTS("tutor.tools.logs"),
            {
                "type": "object",
                "properties": {
                    "count": counted(MAX_LOGS),
                    "kind": {
                        "type": "string",
                        "enum": list(LOG_KINDS),
                        "description": PROMPTS("tutor.tools.kind", kinds=kinds),
                    },
                },
            },
            list_logs,
            lambda arguments: (
                f"Reading your logs of {arguments['kind']}s"
                if arguments.get("kind") in LOG_KINDS
                else "Reading your logs"
            ),
        ),
        *([] if evaluations is None else [_evaluations_tool(evaluations, language)]),
    ]


def _evaluations_tool(evaluations: Any, language: str) -> Tool:
    """The tool that looks up the mock exams there are of `language`, and
    those the learner took, as `evaluations` has them."""

    def list_evaluations(_: dict[str, Any]) -> Done:
        try:
            levels = evaluations.levels(language)
        except Exception:  # noqa: BLE001 - a language with no exams has none
            levels = []
        exams = [
            {
                "level": exam["level"],
                "exam": exam["exam"],
                "minutes": exam["minutes"],
                "modules": [module["title"] for module in exam["modules"]],
            }
            for exam in levels
        ]
        taken = [
            {
                "started": _date(each["started_at"]),
                "level": each["level"],
                "exam": each["plan"]["exam"],
                "half_hours": each["length"],
                "timed": each["timed"],
                "status": each["status"],
                "result": each["result"],
                "parts": [
                    {
                        "module": part["module"],
                        "exercise": part["exercise"],
                        "status": part["status"],
                        "scores": part["scores"],
                    }
                    for part in each["parts"]
                ],
            }
            for each in evaluations.evaluations()
            if each["language"] == language
        ][:MAX_EVALUATIONS]
        return Done(json.dumps({"exams": exams, "taken": taken}, ensure_ascii=False))

    return Tool(
        "evaluations",
        PROMPTS("tutor.tools.evaluations"),
        {"type": "object", "properties": {}},
        list_evaluations,
        lambda _: "Looking at your mock exams",
    )


def evaluation_tool(levels: list[dict[str, Any]]) -> list[Tool]:
    """The tool that offers a mock exam of one of `levels`, the exams there
    are, as the evaluations list them; none if there are none."""
    if not levels:
        return []
    exams = {exam["level"]: exam["exam"] for exam in levels}

    def offer(arguments: dict[str, Any]) -> Done:
        level, length = arguments.get("level"), arguments.get("length", 4)
        if level not in exams:
            raise ToolError(f"there is no mock exam of the level {level!r}")
        offered = {
            "kind": "evaluation",
            "level": level,
            "exam": exams[level],
            "length": _whole(length, "length", 1, MAX_HALF_HOURS),
            "timed": arguments.get("timed") is True,
        }
        told = {name: value for name, value in offered.items() if name != "kind"}
        return Done(
            PROMPTS(
                "tutor.tools.offered_evaluation",
                offered=json.dumps(told, ensure_ascii=False),
            ),
            offered,
        )

    return [
        Tool(
            "evaluation",
            PROMPTS("tutor.tools.evaluation"),
            {
                "type": "object",
                "properties": {
                    "level": {
                        "type": "string",
                        "enum": list(exams),
                        "description": PROMPTS(
                            "tutor.tools.level", levels=", ".join(exams)
                        ),
                    },
                    "length": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_HALF_HOURS,
                        "description": PROMPTS("tutor.tools.length"),
                    },
                    "timed": {
                        "type": "boolean",
                        "description": PROMPTS("tutor.tools.timed"),
                    },
                },
                "required": ["level", "length"],
            },
            offer,
            lambda arguments: (
                f"Preparing a mock exam of {arguments.get('level', 'your level')}"
            ),
        )
    ]


def exercise_tools(
    manifests: list[dict[str, Any]],
    lessons: list[dict[str, Any]],
    topics: list[dict[str, Any]],
) -> list[Tool]:
    """A tool for each exercise of `manifests`, with what the exercise may
    be chosen with as its parameters: a lesson of `lessons`, how many times
    it is done and the `topics` it is about, and its options. Calling it
    offers the exercise to the learner."""
    lesson_ids = [lesson["id"] for lesson in lessons]
    titles = {lesson["id"]: lesson["title"] for lesson in lessons}
    # by title, as the model is told them; the newest of a title stands for it
    topic_ids: dict[str, str] = {}
    for topic in reversed(topics):
        topic_ids[topic["title"]] = topic["id"]
    return [
        _exercise_tool(manifest, lesson_ids, titles, topic_ids)
        for manifest in manifests
        # one that has nothing to choose, such as a text where there is none,
        # cannot be offered
        if all(
            option.get("choices", True)
            for option in (manifest.get("options") or {}).values()
        )
    ]


def _exercise_tool(
    manifest: dict[str, Any],
    lesson_ids: list[str],
    titles: dict[str, str],
    topic_ids: dict[str, str],
) -> Tool:
    theory = bool(manifest.get("theory"))
    # one that practises no lesson is called with none
    lessons = manifest.get("lesson", True) is not False
    options = manifest.get("options") or {}
    properties: dict[str, Any] = {}
    required = []
    if lessons:
        properties["lesson"] = {
            "type": "string",
            "enum": lesson_ids if theory else [*lesson_ids, ""],
            "description": PROMPTS(
                "tutor.tools.theory_lesson" if theory else "tutor.tools.lesson"
            ),
        }
        required.append("lesson")
    # one done once is not called with how many times
    once = bool(manifest.get("once"))
    if not theory and not once:
        properties["instances"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_INSTANCES,
            "description": PROMPTS("tutor.tools.instances"),
        }
        required.append("instances")
    if not theory:
        if topic_ids:
            properties["topics"] = {
                "type": "array",
                "items": {"type": "string", "enum": list(topic_ids)},
                "description": PROMPTS("tutor.tools.topics"),
            }
        for name, option in options.items():
            properties[name] = _option_schema(option)
        # what steers it to what the learner needs now
        properties["focus"] = {
            "type": "string",
            "maxLength": MAX_FOCUS,
            "description": PROMPTS("tutor.tools.focus"),
        }
        properties["words"] = {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_WORDS,
            "description": PROMPTS("tutor.tools.words"),
        }

    def offer(arguments: dict[str, Any]) -> Done:
        lesson = arguments.get("lesson", "") if lessons else ""
        if lessons and (
            not isinstance(lesson, str) or lesson not in properties["lesson"]["enum"]
        ):
            raise ToolError(
                f"there is no lesson {lesson!r}; the lessons tool lists them"
            )
        offered: dict[str, Any] = {
            "kind": "exercise",
            "exercise": manifest["id"],
            "title": manifest["title"],
            "theory": theory,
            # whether it practises a lesson, as one on a text does not
            "practises_lesson": lessons,
            "lesson": lesson,
            "lesson_title": titles.get(lesson, ""),
            "instances": 1,
            "topics": [],
            "options": {},
        }
        if not theory:
            offered["instances"] = (
                1
                if once
                else _whole(arguments.get("instances"), "instances", 1, MAX_INSTANCES)
            )
            chosen = arguments.get("topics") or []
            unknown = [each for each in chosen if each not in topic_ids]
            if not isinstance(chosen, list) or unknown:
                raise ToolError(f"there are no topics {unknown!r}")
            offered["topics"] = [topic_ids[each] for each in chosen]
            offered["topic_titles"] = list(chosen)
            offered["options"] = {
                name: _option_value(name, option, arguments.get(name))
                for name, option in options.items()
            }
            # what each choice is called, such as the title of a text
            offered["labels"] = {
                name: option["choices"][offered["options"][name]]
                for name, option in options.items()
                if "choices" in option
            }
            focus = arguments.get("focus") or ""
            words = arguments.get("words") or []
            if not isinstance(focus, str) or len(focus) > MAX_FOCUS:
                raise ToolError(f"focus is a text of at most {MAX_FOCUS} characters")
            if not (
                isinstance(words, list)
                and len(words) <= MAX_WORDS
                and all(isinstance(each, str) and each.strip() for each in words)
            ):
                raise ToolError(f"words are at most {MAX_WORDS} words")
            offered["focus"] = " ".join(focus.split())
            offered["words"] = list(dict.fromkeys(each.strip() for each in words))
        told = {
            name: value
            for name, value in offered.items()
            if name not in ("kind", "topics", "theory", "practises_lesson")
        }
        return Done(
            PROMPTS(
                "tutor.tools.offered", offered=json.dumps(told, ensure_ascii=False)
            ),
            offered,
        )

    return Tool(
        f"exercise_{manifest['id']}",
        PROMPTS(
            "tutor.tools.exercise",
            title=manifest["title"],
            description=manifest["description"],
        ),
        {"type": "object", "properties": properties, "required": required},
        offer,
        lambda _: f"Preparing the exercise “{manifest['title']}”",
    )


def _option_schema(option: dict[str, Any]) -> dict[str, Any]:
    """The schema of an option of a manifest: one of its choices, each said
    with its label, or a whole number between its bounds."""
    if "choices" in option:
        said = "; ".join(
            f"{value}: {label}" for value, label in option["choices"].items()
        )
        return {
            "type": "string",
            "enum": list(option["choices"]),
            "description": f"{option['label']} ({said})",
        }
    return {
        "type": "integer",
        "minimum": option["min"],
        "maximum": option["max"],
        "description": f"{option['label']}, {option['default']} unless another fits better",
    }


def _option_value(name: str, option: dict[str, Any], value: object) -> Any:
    """The value an option was called with, or the one it takes unless
    another is chosen. Raises ToolError."""
    if "choices" in option:
        if value is None:
            return next(iter(option["choices"]))
        if value not in option["choices"]:
            raise ToolError(f"{name} is one of {', '.join(option['choices'])}")
        return value
    if value is None:
        return option["default"]
    return _whole(value, name, option["min"], option["max"])


def _whole(value: object, name: str, least: int, most: int) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not least <= value <= most
    ):
        raise ToolError(f"{name} is a whole number from {least} to {most}")
    return value


def _count(arguments: dict[str, Any], most: int) -> int:
    count = arguments.get("count")
    if count is None:
        return most
    return _whole(count, "count", 1, most)


def _date(seconds: float | None) -> str | None:
    return (
        None
        if seconds is None
        else time.strftime("%Y-%m-%d %H:%M", time.localtime(seconds))
    )
