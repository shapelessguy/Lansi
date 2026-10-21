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
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from anki_import import AnkiUnavailable
from categories import CATEGORIES
from intake import CHAT_TIMEOUT_SECS, read_usage
from known import ORDERS, Asked, Known
from logs import describe_record, read_json
from models import Model
from profiling import Profile, ProfileError, error_message
from prompts import PROMPTS
from storage import LOG_KINDS, read_day
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
# how many words the tool that looks them up gives at most, and how many
# when it is not told
MAX_KNOWN_WORDS = 200
USUAL_KNOWN_WORDS = 50
# how many recaps of the latest chats the tool that looks them up gives at
# most, and how many when it is not told
MAX_RECAPS = 50
USUAL_RECAPS = 10
# how many days after today the tutor is told how many entries of its
# calendar there are for
COMING_DAYS = 7
# the longest a strategy or an entry of the calendar may be, in characters
MAX_PLANNED = 600
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
    language: str,
    into: str,
    level: str,
    memories: list[dict[str, Any]],
    tone: str = "",
) -> str:
    """What the tutor is told before the chat: how to talk with the learner,
    the `tone` they set, if they set one, and of the `memories` it has of
    them, which go before the tone where they say otherwise, the facts in
    full; of the strategy, the recaps and the calendar, only how many there
    are, as it looks them up with memory_tools."""
    today = time.strftime("%Y-%m-%d")
    facts = [memory for memory in memories if memory.get("kind", "fact") == "fact"]
    strategies = [memory for memory in memories if memory.get("kind") == "strategy"]
    recaps = [memory for memory in memories if memory.get("kind") == "recap"]
    days = [memory["day"] for memory in memories if memory.get("kind") == "calendar"]
    coming = time.strftime(
        "%Y-%m-%d", time.localtime(time.time() + COMING_DAYS * 86400)
    )
    listed = "\n".join(
        f"- [{_day(memory['createdAt'])}] {memory['content']}" for memory in facts
    )
    told = [
        PROMPTS("tutor.memories.listed", memories=listed)
        if facts
        else PROMPTS("tutor.memories.none"),
        PROMPTS(
            "tutor.memories.recaps",
            count=len(recaps),
            latest=_day(recaps[-1]["createdAt"]),
        )
        if recaps
        else PROMPTS("tutor.memories.no_recaps"),
        PROMPTS(
            "tutor.memories.calendar",
            today=sum(day == today for day in days),
            coming=sum(today < day <= coming for day in days),
            days=COMING_DAYS,
            missed=sum(day < today for day in days),
        )
        if days
        else PROMPTS("tutor.memories.no_calendar"),
        PROMPTS("tutor.memories.strategy")
        if strategies
        else PROMPTS("tutor.memories.no_strategy"),
    ]
    told_all = PROMPTS(
        "tutor.system",
        language=language,
        into=into,
        level=level or "unknown",
        today=today,
        tone=PROMPTS("tutor.tone", tone=" ".join(tone.split())) if tone.strip() else "",
        memories="\n\n".join(told),
    )
    # a part that was left out leaves no gap
    return re.sub(r"\n{3,}", "\n\n", told_all)


def _said(chat: list[dict[str, str]]) -> str:
    """A chat with the tutor as a model reading it is told it."""
    return "\n\n".join(
        f"{'Learner' if message['role'] == 'user' else 'Tutor'}: {message['content']}"
        for message in chat
    )


def recap(
    chat: list[dict[str, str]],
    language: str,
    ask: Callable[[list[dict[str, Any]]], tuple[str, Profile]],
) -> tuple[str, Profile]:
    """A recap of a `chat` that is over, as long as what was done in it
    needs, as the model `ask` asks writes it, and what asking it used.
    Raises TutorError."""
    prompt = PROMPTS(
        "tutor.recap",
        language=language,
        today=time.strftime("%Y-%m-%d"),
        chat=_said(chat),
    )
    try:
        reply, used = ask([{"role": "user", "content": prompt}])
    except TranslationError as error:
        raise TutorError(str(error)) from None
    # bullets are left off, should the model have put them in all the same
    lines = [line.strip().lstrip("-*• ").strip() for line in reply.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        raise TutorError("the model wrote no recap")
    return "\n".join(lines), used


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
    said = _said(chat)
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
        # a session left before anything was done in it is not practice
        return {
            session["lesson"]
            for session in store.sessions()
            if session["lesson"] and not session.get("hidden")
        }

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
            if session["language"] == language and not session.get("hidden")
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


def memory_tools(store: Any) -> list[Tool]:
    """The tools with which the tutor looks up, in `store`, the recaps of
    the latest chats, the strategy and its calendar, and with which it
    writes down a strategy and an entry of the calendar as soon as the
    learner agrees on it, and crosses either out."""

    def kept(memory: dict[str, Any]) -> dict[str, Any]:
        return {"id": memory["id"], "agreed": _day(memory["createdAt"])}

    def list_recaps(arguments: dict[str, Any]) -> Done:
        count = arguments.get("count")
        count = USUAL_RECAPS if count is None else _whole(count, "count", 1, MAX_RECAPS)
        listed = [
            {"day": _day(memory["createdAt"]), "recap": memory["content"].splitlines()}
            for memory in reversed(store.memories(kind="recap"))
        ][:count]
        return Done(json.dumps(listed, ensure_ascii=False))

    def list_strategy(_: dict[str, Any]) -> Done:
        listed = [
            {**kept(memory), "what": memory["content"]}
            for memory in store.memories(kind="strategy")
        ]
        return Done(json.dumps(listed, ensure_ascii=False))

    def list_calendar(arguments: dict[str, Any]) -> Done:
        bounds = [arguments.get(name) for name in ("from", "to")]
        try:
            least, most = [
                None if bound is None else read_day(bound) for bound in bounds
            ]
        except ValueError as error:
            raise ToolError(f"from and to are days: {error}") from None
        entries = [
            {**kept(memory), "day": memory["day"], "what": memory["content"]}
            for memory in store.memories(kind="calendar")
        ] + [
            {
                **kept(memory),
                "day": memory["day"],
                "what": memory["content"],
                "crossed_out": {
                    "by": memory["removedBy"],
                    "why": memory["removedWhy"],
                },
            }
            for memory in store.memories(removed=True, kind="calendar")
        ]
        listed = sorted(
            (
                entry
                for entry in entries
                if (least is None or entry["day"] >= least)
                and (most is None or entry["day"] <= most)
            ),
            key=lambda entry: (entry["day"], entry["id"]),
        )
        return Done(json.dumps(listed, ensure_ascii=False))

    def said(arguments: dict[str, Any]) -> str:
        what = arguments.get("what")
        if not isinstance(what, str) or not what.strip():
            raise ToolError("what is what was agreed on, in a sentence or two")
        if len(what) > MAX_PLANNED:
            raise ToolError(f"what is at most {MAX_PLANNED} characters long")
        return what

    def held(memory_id: object, kinds: tuple[str, ...]) -> dict[str, Any]:
        memories: list[dict[str, Any]] = store.memories()
        for memory in memories:
            if memory["id"] == memory_id and memory["kind"] in kinds:
                return memory
        raise ToolError(f"there is no entry {memory_id!r} to cross out")

    def agree(arguments: dict[str, Any]) -> Done:
        what = said(arguments)
        replaces = arguments.get("replaces") or []
        if not isinstance(replaces, list):
            raise ToolError("replaces is a list of the ids of strategies")
        replaced = [held(each, ("strategy",)) for each in replaces]
        memory_id = store.add_memory(what, kind="strategy")
        for memory in replaced:
            store.remove_memory(
                memory["id"], f"replaced by the strategy {memory_id}", "tutor"
            )
        return Done(json.dumps({"id": memory_id, "replaced": replaces}))

    def plan(arguments: dict[str, Any]) -> Done:
        what = said(arguments)
        try:
            day = read_day(arguments.get("day"))
        except ValueError as error:
            raise ToolError(str(error)) from None
        if day < time.strftime("%Y-%m-%d"):
            raise ToolError("a day that has passed cannot be planned")
        return Done(
            json.dumps({"id": store.add_memory(what, kind="calendar", day=day)})
        )

    def cross_out(arguments: dict[str, Any]) -> Done:
        memory = held(arguments.get("id"), ("strategy", "calendar"))
        why = arguments.get("why")
        if not isinstance(why, str) or not why.strip():
            raise ToolError("why says why it is crossed out, such as that it was done")
        store.remove_memory(memory["id"], " ".join(why.split()), "tutor")
        return Done(json.dumps({"crossed_out": memory["id"]}))

    def text(name: str) -> dict[str, Any]:
        return {"type": "string", "description": PROMPTS(f"tutor.tools.{name}")}

    return [
        Tool(
            "recaps",
            PROMPTS("tutor.tools.recaps", usual=USUAL_RECAPS),
            {
                "type": "object",
                "properties": {
                    "count": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": MAX_RECAPS,
                        "description": PROMPTS("tutor.tools.count", most=MAX_RECAPS),
                    }
                },
            },
            list_recaps,
            lambda _: "Reading the recaps of the lessons",
        ),
        Tool(
            "strategy",
            PROMPTS("tutor.tools.strategy"),
            {"type": "object", "properties": {}},
            list_strategy,
            lambda _: "Looking at the strategy",
        ),
        Tool(
            "calendar",
            PROMPTS("tutor.tools.calendar"),
            {
                "type": "object",
                "properties": {"from": text("from"), "to": text("to")},
            },
            list_calendar,
            lambda _: "Looking at the calendar",
        ),
        Tool(
            "agree_strategy",
            PROMPTS("tutor.tools.agree_strategy"),
            {
                "type": "object",
                "properties": {
                    "what": text("strategy_what"),
                    "replaces": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": PROMPTS("tutor.tools.replaces"),
                    },
                },
                "required": ["what"],
            },
            agree,
            lambda _: "Writing down the strategy",
        ),
        Tool(
            "plan",
            PROMPTS("tutor.tools.plan"),
            {
                "type": "object",
                "properties": {"day": text("day"), "what": text("plan_what")},
                "required": ["day", "what"],
            },
            plan,
            lambda arguments: f"Putting it on the calendar for {arguments.get('day')}",
        ),
        Tool(
            "cross_out",
            PROMPTS("tutor.tools.cross_out"),
            {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "integer",
                        "description": PROMPTS("tutor.tools.entry"),
                    },
                    "why": text("why"),
                },
                "required": ["id", "why"],
            },
            cross_out,
            lambda _: "Crossing it out",
        ),
    ]


def words_tool(
    known: Callable[[Asked], tuple[list[Known], int]],
    sets: list[str],
    anki: bool,
    practised: list[str],
) -> Tool:
    """The tool that looks up the words the learner knows, which `known`
    gives as they are asked for, with how many there are in all. `sets`
    are the names of the learner's sets of words, `anki` is whether they
    have Anki, whose words can be asked for alone, and `practised` are the
    categories whose words practice is best built on."""

    def list_words(arguments: dict[str, Any]) -> Done:
        categories = arguments.get("categories") or []
        if not isinstance(categories, list) or not all(
            isinstance(each, str) for each in categories
        ):
            raise ToolError("categories is a list of the names of categories")
        word_set = arguments.get("set") or ""
        if not isinstance(word_set, str):
            raise ToolError("set is the name of a set")
        flags = {name: arguments.get(name, False) for name in ("anki_only", "reverse")}
        for name, value in flags.items():
            if not isinstance(value, bool):
                raise ToolError(f"{name} is true or false")
        try:
            words, total = known(
                Asked(
                    categories=frozenset(categories),
                    set=word_set,
                    anki_only=flags["anki_only"],
                    order=arguments.get("sorted_by") or "last_used",
                    reverse=flags["reverse"],
                    limit=_count(arguments, MAX_KNOWN_WORDS)
                    if arguments.get("count") is not None
                    else USUAL_KNOWN_WORDS,
                )
            )
        except (ValueError, LookupError, AnkiUnavailable) as error:
            raise ToolError(str(error)) from None
        listed = [
            {
                "word": word.lemma,
                "categories": word.categories,
                "used": word.used,
                "seen": word.seen,
                "last_used_by_user": _date(word.last_used_by_user),
                "last_used_by_assistant": _date(word.last_used_by_assistant),
            }
            for word in words
        ]
        return Done(json.dumps({"total": total, "words": listed}, ensure_ascii=False))

    properties: dict[str, Any] = {
        "categories": {
            "type": "array",
            "items": {"type": "string", "enum": list(CATEGORIES)},
            "description": PROMPTS("tutor.tools.categories"),
        },
        "sorted_by": {
            "type": "string",
            "enum": list(ORDERS),
            "description": PROMPTS("tutor.tools.sorted_by"),
        },
        "reverse": {"type": "boolean", "description": PROMPTS("tutor.tools.reverse")},
        "count": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_KNOWN_WORDS,
            "description": PROMPTS("tutor.tools.count", most=MAX_KNOWN_WORDS),
        },
    }
    if sets:
        properties["set"] = {
            "type": "string",
            "enum": sets,
            "description": PROMPTS("tutor.tools.set"),
        }
    if anki:
        properties["anki_only"] = {
            "type": "boolean",
            "description": PROMPTS("tutor.tools.anki_only"),
        }
    return Tool(
        "words",
        PROMPTS(
            "tutor.tools.words_known",
            practised=", ".join(practised),
            usual=USUAL_KNOWN_WORDS,
        ),
        {"type": "object", "properties": properties},
        list_words,
        lambda arguments: (
            "Looking at the words you know from Anki"
            if arguments.get("anki_only") is True
            else "Looking at the words you know"
        ),
    )


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


def exercise_tool(
    manifests: list[dict[str, Any]],
    lessons: list[dict[str, Any]],
    topics: list[dict[str, Any]],
) -> list[Tool]:
    """The tool that offers the learner an exercise of `manifests`, which
    its description lists, each with its options, so that what every
    exercise is chosen with is said once: a lesson of `lessons`, how many
    times it is done, the `topics` it is about, its options and what steers
    it. An exercise whose manifest says so, such as one that makes
    nothing, has a tool of its own, by its id, called with its options.
    None where there is no exercise to offer."""
    # one that has nothing to choose, such as a text where there is none,
    # cannot be offered
    offerable = {
        manifest["id"]: manifest
        for manifest in manifests
        if all(
            option.get("choices", True)
            for option in (manifest.get("options") or {}).values()
        )
    }
    own = [manifest for manifest in offerable.values() if manifest.get("own_tool")]
    offerable = {
        exercise: manifest
        for exercise, manifest in offerable.items()
        if not manifest.get("own_tool")
    }
    lesson_ids = [lesson["id"] for lesson in lessons]
    titles = {lesson["id"]: lesson["title"] for lesson in lessons}
    # by title, as the model is told them; the newest of a title stands for it
    topic_ids: dict[str, str] = {}
    for topic in reversed(topics):
        topic_ids[topic["title"]] = topic["id"]
    properties: dict[str, Any] = {
        "exercise": {
            "type": "string",
            "enum": list(offerable),
            "description": PROMPTS("tutor.tools.exercise_id"),
        },
        "lesson": {
            "type": "string",
            "enum": [*lesson_ids, ""],
            "description": PROMPTS("tutor.tools.lesson"),
        },
        "instances": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_INSTANCES,
            "description": PROMPTS("tutor.tools.instances"),
        },
        "options": {
            "type": "object",
            "description": PROMPTS("tutor.tools.options"),
        },
        # what steers it to what the learner needs now
        "focus": {
            "type": "string",
            "maxLength": MAX_FOCUS,
            "description": PROMPTS("tutor.tools.focus"),
        },
        "words": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_WORDS,
            "description": PROMPTS("tutor.tools.words"),
        },
    }
    if topic_ids:
        properties["topics"] = {
            "type": "array",
            "items": {"type": "string", "enum": list(topic_ids)},
            "description": PROMPTS("tutor.tools.topics"),
        }

    def offer(arguments: dict[str, Any]) -> Done:
        manifest = offerable.get(arguments.get("exercise"))
        if manifest is None:
            raise ToolError(
                f"there is no exercise {arguments.get('exercise')!r};"
                f" there are {', '.join(offerable)}"
            )
        return _offered(manifest, arguments, lesson_ids, titles, topic_ids)

    catalog = "\n".join(_listed(manifest) for manifest in offerable.values())
    own_tools = [_own_tool(manifest, lesson_ids, titles, topic_ids) for manifest in own]
    if not offerable:
        return own_tools
    return [
        *own_tools,
        Tool(
            "exercise",
            PROMPTS("tutor.tools.exercise", exercises=catalog),
            {"type": "object", "properties": properties, "required": ["exercise"]},
            offer,
            lambda arguments: (
                f"Preparing the exercise “{offerable[arguments['exercise']]['title']}”"
                if arguments.get("exercise") in offerable
                else "Preparing an exercise"
            ),
        ),
    ]


def _own_tool(
    manifest: dict[str, Any],
    lesson_ids: list[str],
    titles: dict[str, str],
    topic_ids: dict[str, str],
) -> Tool:
    """The tool of its own that offers an exercise, called with its options,
    and with a lesson and how many times it is done where it has them."""
    options = manifest.get("options") or {}
    properties: dict[str, Any] = {}
    if manifest.get("lesson", True) is not False:
        properties["lesson"] = {
            "type": "string",
            "enum": [*lesson_ids, ""],
            "description": PROMPTS("tutor.tools.lesson"),
        }
    if not manifest.get("once") and not manifest.get("theory"):
        properties["instances"] = {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_INSTANCES,
            "description": PROMPTS("tutor.tools.instances"),
        }
    for name, option in options.items():
        properties[name] = {
            "description": _option_said(name, option),
            **(
                {"type": "string", "enum": list(option["choices"])}
                if "choices" in option
                else {
                    "type": "integer",
                    "minimum": option["min"],
                    "maximum": option["max"],
                }
            ),
        }

    def offer(arguments: dict[str, Any]) -> Done:
        called = {
            "exercise": manifest["id"],
            "lesson": arguments.get("lesson", ""),
            "instances": arguments.get("instances", 1),
            "options": {name: arguments[name] for name in options if name in arguments},
        }
        return _offered(manifest, called, lesson_ids, titles, topic_ids)

    return Tool(
        manifest["id"],
        PROMPTS(
            "tutor.tools.own_exercise",
            title=manifest["title"],
            description=manifest["description"],
        ),
        {"type": "object", "properties": properties},
        offer,
        lambda _: f"Preparing the exercise “{manifest['title']}”",
    )


def _listed(manifest: dict[str, Any]) -> str:
    """An exercise as the description of the tool that offers it lists it:
    its id, title and description, what it is called with that others are
    not, and its options."""
    theory = bool(manifest.get("theory"))
    marks = []
    if theory:
        marks.append(PROMPTS("tutor.tools.exercise_theory"))
    elif manifest.get("lesson", True) is False:
        marks.append(PROMPTS("tutor.tools.exercise_no_lesson"))
    if manifest.get("once") and not theory:
        marks.append(PROMPTS("tutor.tools.exercise_once"))
    options = manifest.get("options") or {}
    if options and not theory:
        marks.append(
            PROMPTS(
                "tutor.tools.exercise_options",
                options="; ".join(
                    _option_said(name, option) for name, option in options.items()
                ),
            )
        )
    return " ".join(
        [f"- {manifest['id']}: {manifest['title']}. {manifest['description']}", *marks]
    )


def _offered(
    manifest: dict[str, Any],
    arguments: dict[str, Any],
    lesson_ids: list[str],
    titles: dict[str, str],
    topic_ids: dict[str, str],
) -> Done:
    """An exercise offered as it was called with `arguments`, with the
    options it was not called with as usual. Raises ToolError."""
    theory = bool(manifest.get("theory"))
    # one that practises no lesson is called with none
    lessons = manifest.get("lesson", True) is not False
    options = manifest.get("options") or {}
    lesson = arguments.get("lesson") or "" if lessons else ""
    if lessons and (
        not isinstance(lesson, str)
        or lesson not in lesson_ids
        and (theory or lesson != "")
    ):
        raise ToolError(f"there is no lesson {lesson!r}; the lessons tool lists them")
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
            if manifest.get("once")
            else _whole(arguments.get("instances", 1), "instances", 1, MAX_INSTANCES)
        )
        chosen = arguments.get("topics") or []
        unknown = [each for each in chosen if each not in topic_ids]
        if not isinstance(chosen, list) or unknown:
            raise ToolError(f"there are no topics {unknown!r}")
        offered["topics"] = [topic_ids[each] for each in chosen]
        offered["topic_titles"] = list(chosen)
        given = arguments.get("options") or {}
        if not isinstance(given, dict):
            raise ToolError("options are an object, of the options of the exercise")
        unknown = [name for name in given if name not in options]
        if unknown:
            raise ToolError(
                f"{manifest['id']} has no options {unknown!r}; it has"
                f" {', '.join(options) or 'none'}"
            )
        offered["options"] = {
            name: _option_value(name, option, given.get(name))
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
        PROMPTS("tutor.tools.offered", offered=json.dumps(told, ensure_ascii=False)),
        offered,
    )


def _option_said(name: str, option: dict[str, Any]) -> str:
    """An option of a manifest as the tool that offers the exercise lists
    it: one of its choices, each said with its label, or a whole number
    between its bounds."""
    if "choices" in option:
        return PROMPTS(
            "tutor.tools.option_choices",
            name=name,
            label=option["label"],
            choices=", ".join(
                f"{value} ({label})" for value, label in option["choices"].items()
            ),
        )
    return PROMPTS(
        "tutor.tools.option_number",
        name=name,
        label=option["label"],
        least=option["min"],
        most=option["max"],
        usual=option["default"],
    )


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
