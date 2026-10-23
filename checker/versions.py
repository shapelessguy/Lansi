# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The versions of a book, each made from the book or from another version
of it, and kept as a book of its own under the one it is a version of, so
that it is read, read aloud and found one's way in as any book is. A
version is a copy of what it says, which leads nowhere: its links are left
out, and it does not say what it was made from.

There are two kinds. A "stripped" version is made of some of the blocks of
the one it is made from, those that are the text itself, without what was
put around it, such as the words and the questions after each chapter. A
"transformed" one is written anew by the reasoning model, as a prompt says,
such as in another language or for a lower or a higher level, each part of
the book that is independent of the others on its own, as the prompt
versions/part.md says: the part is sent as a JSON object of its blocks by
their places, and the model answers with an object of the same keys, each
with the block written anew. A block keeps how it was written, its size and
its element, with the text the model wrote for it.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Any

from intake import read_usage
from logs import read_json
from models import Model
from profiling import Profile, ProfileError, spent, spent_by
from prompts import PROMPTS
from sections import headings
from tokens import count
from tutor import stream_chat

KINDS = ("stripped", "transformed")
# the prompts a transformed version can be written anew with, as the
# learner is offered them to start from, by their variants
TRANSFORM_PROMPTS = "versions.transform"
# how long the name of a version may be
MAX_NAME = 80
# How long to wait for the next piece of the answer of the model that
# transforms a part, and for the whole of it, in seconds: a model that
# reasons before it writes a whole story anew takes minutes.
TRANSFORM_TIMEOUT_SECS = 300
TRANSFORM_WITHIN_SECS = 3600
# how many parts of a book are transformed at the same time
PARALLEL_PARTS = 4
# the most tokens the model may reason in before it writes a part
MAX_REASONING = 32_000
# how many answers a part may take, one after another as each breaks off
MAX_ROUNDS = 20

# Sends a chat request to a model and gives each piece of its streamed
# answer as it comes. Raises ProfileError.
Stream = Callable[[dict[str, Any], Model], Iterator[dict[str, Any]]]
# a block of a version, by the place of the block of the book it is made
# from, or None for one the model added, with the text it says instead, or
# None for the text it had
Emitted = tuple[int | None, str | None]


class TransformError(Exception):
    """A part of a book could not be transformed. The message says why."""


def kept_stretches(keep: object, count: int) -> list[tuple[int, int]]:
    """The stretches of blocks to keep of a book of `count` blocks, each
    from its first block to the one after its last, as they were asked for.
    Raises ValueError for stretches that are not in order, overlap, are not
    in the book, or keep nothing."""
    if not isinstance(keep, list) or not keep:
        raise ValueError("a stripped version keeps some of the book")
    stretches: list[tuple[int, int]] = []
    for stretch in keep:
        if (
            not isinstance(stretch, list)
            or len(stretch) != 2
            or not all(type(place) is int for place in stretch)
        ):
            raise ValueError("a stretch to keep is where it starts and ends")
        start, end = stretch
        after = stretches[-1][1] if stretches else 0
        if not after <= start < end <= count:
            raise ValueError("the stretches to keep are in order and in the book")
        stretches.append((start, end))
    return stretches


def transformed_parts(parts: object, count: int) -> list[list[tuple[int, int]]]:
    """The parts of a book of `count` blocks to transform, each its own,
    with its stretches of blocks, as they were asked for. Raises ValueError
    for parts that are not lists of stretches, have none, or take in a
    block that another part does."""
    if not isinstance(parts, list) or not parts:
        raise ValueError("a transformed version transforms some of the book")
    found = [kept_stretches(part, count) for part in parts]
    taken = [
        place for part in found for start, end in part for place in range(start, end)
    ]
    if len(taken) != len(set(taken)):
        raise ValueError("no block is in two parts")
    return found


def stream_transforming(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
    """Sends a chat request that may take long, as one to transform a part
    of a book does, and gives each piece of the streamed answer as it comes.
    Raises ProfileError."""
    return stream_chat(body, model, TRANSFORM_TIMEOUT_SECS)


def part_blocks(book: dict[str, Any], part: list[tuple[int, int]]) -> dict[str, str]:
    """The blocks of a part of `book` as the model is sent them: the text of
    each by its place, in order."""
    return {
        str(place): book["blocks"][place]["text"]
        for start, end in part
        for place in range(start, end)
    }


def read_part(said: str) -> dict[str, str]:
    """The blocks of a part as the model wrote them, in the order it wrote
    them, each by its key. A value that is not text, such as a number, is
    taken as JSON writes it, and one that is null is left out. Raises
    TransformError."""
    found = read_json(said)
    if not isinstance(found, dict) or not found:
        raise TransformError("the model did not write the part as a JSON object")
    return {
        str(key): value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False)
        for key, value in found.items()
        if value is not None
    }


@dataclass
class PartProgress:
    """How the transforming of a part is going."""

    # what the part is called, such as the title of its story
    title: str = ""
    # "waiting" to be sent, "thinking" before the model writes, "writing",
    # or "done"
    state: str = "waiting"
    # the tokens the model has reasoned and written so far
    reasoning: int = 0
    written: int = 0
    # the tokens of the part as it was sent, which what is written is about
    # as long as
    expected: int = 0
    # the most tokens the model may reason in, if it reasons
    budget: int | None = None
    # how many answers the model has been asked for: more than one once
    # an answer broke off
    round: int = 0


def _said(piece: dict[str, Any]) -> tuple[str, str]:
    """What a piece of a streamed answer reasons and writes."""
    try:
        delta = piece["choices"][0]["delta"]
    except (KeyError, IndexError, TypeError):
        return "", ""
    if not isinstance(delta, dict):
        return "", ""
    reasoning = delta.get("reasoning") or delta.get("reasoning_content") or ""
    content = delta.get("content") or ""
    return (
        reasoning if isinstance(reasoning, str) else "",
        content if isinstance(content, str) else "",
    )


def _reasoned(usage: object) -> int | None:
    """The tokens of reasoning a model was billed for, if it says."""
    details = (
        usage.get("completion_tokens_details") if isinstance(usage, dict) else None
    )
    count = details.get("reasoning_tokens") if isinstance(details, dict) else None
    return count if isinstance(count, int) else None


@dataclass
class Streamed:
    """What a model answered, as it streamed it."""

    # what it wrote, and what it reasoned, if it showed it
    text: str
    reasoning: str
    # why it stopped: "length" if it reached the most it may write in one
    # answer, which cuts the answer short
    finish: str
    used: Profile


def _finish(piece: dict[str, Any]) -> str:
    try:
        reason = piece["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""
    return reason if isinstance(reason, str) else ""


def _streamed(
    body: dict[str, Any],
    model: Model,
    progress: PartProgress,
    report: Callable[[], None],
    stream: Stream,
) -> Streamed:
    """What the model answered, as it streamed it, keeping `progress` and
    calling `report` as it reasons and writes. Raises ProfileError and
    TransformError."""
    written: list[str] = []
    thought: list[str] = []
    usage: dict[str, Any] = {}
    finish = ""
    give_up_at = time.monotonic() + TRANSFORM_WITHIN_SECS
    reasoned_before = progress.reasoning
    progress.state = "thinking" if body["reasoning"].get("enabled", True) else "writing"
    report()
    for piece in stream(body, model):
        if time.monotonic() > give_up_at:
            raise TransformError("the model took too long to write the part")
        if isinstance(piece.get("error"), dict):
            message = piece["error"].get("message") or "the model failed"
            raise TransformError(str(message))
        if isinstance(piece.get("usage"), dict):
            usage = piece
        finish = _finish(piece) or finish
        reasoning, content = _said(piece)
        if not reasoning and not content:
            continue
        if reasoning:
            thought.append(reasoning)
            progress.reasoning += count(reasoning)
        if content:
            written.append(content)
            progress.state = "writing"
            progress.written += count(content)
        report()
    used = read_usage(usage, model.name)
    reasoned = _reasoned(usage.get("usage"))
    if reasoned is not None:
        progress.reasoning = reasoned_before + reasoned
    if not "".join(written).strip():
        raise spent(TransformError("the model gave no answer"), [used])
    return Streamed("".join(written), "".join(thought), finish, used)


def read_begun(said: str) -> dict[str, str]:
    """The blocks of a part the model wrote whole, by their keys, in an
    answer that broke off: each pair of a key and a value of the JSON object
    it began, read one after the other, up to the first that is not whole,
    which is left out with all after it."""
    start = said.find("{")
    if start == -1:
        return {}
    decoder = json.JSONDecoder()
    found: dict[str, str] = {}
    place = start + 1
    while True:
        try:
            place = _past_space(said, place)
            key, place = decoder.raw_decode(said, place)
            place = _past_space(said, place)
            if said[place] != ":":
                break
            value, place = decoder.raw_decode(said, _past_space(said, place + 1))
        except (ValueError, IndexError):
            break
        if not isinstance(key, str):
            break
        if isinstance(value, str):
            found[key] = value
        elif value is not None:
            found[key] = json.dumps(value, ensure_ascii=False)
        place = _past_space(said, place)
        if place >= len(said) or said[place] != ",":
            break
        place += 1
    return found


def _past_space(text: str, place: int) -> int:
    while place < len(text) and text[place].isspace():
        place += 1
    return place


def _prompt(instructions: str, part: str, budget: int | None) -> str:
    """What the model is told to transform a part with, and how long to
    reason over it, if it reasons within a budget."""
    reasoning = PROMPTS("versions.reasoning", budget=budget) if budget else ""
    prompt = PROMPTS(
        "versions.part",
        instructions=instructions.strip(),
        part=part,
        reasoning=reasoning,
    )
    # without a budget, the line it would be on is left out
    return prompt.replace("\n\n\n\n", "\n\n")


def _asked(
    prompt: str,
    model: Model,
    think: bool,
    budget: int,
    progress: PartProgress,
    report: Callable[[], None],
    stream: Stream,
) -> Streamed:
    """What the model answered to `prompt`, reasoning first in at most
    `budget` tokens if `think`. A model that cannot but reason is asked
    again with reasoning. Raises ProfileError and TransformError."""
    body: dict[str, Any] = {
        "model": model.name,
        "messages": [{"role": "user", "content": prompt}],
        "reasoning": {"max_tokens": budget} if think else {"enabled": False},
        "stream": True,
        "usage": {"include": True},
    }
    try:
        return _streamed(body, model, progress, report, stream)
    except ProfileError as error:
        if think or "(400)" not in str(error):
            raise
    body["reasoning"] = {"max_tokens": budget}
    return _streamed(body, model, progress, report, stream)


def transform_part(
    instructions: str,
    blocks: dict[str, str],
    model: Model,
    think: bool = True,
    progress: PartProgress | None = None,
    report: Callable[[], None] = lambda: None,
    stream: Stream = stream_transforming,
    budget: int | None = None,
) -> tuple[dict[str, str], list[Profile]]:
    """The blocks of a part, as `part_blocks` gives them, written anew by
    `model` as `instructions` say, with what asking used.

    The model reasons first if `think`, in at most `budget` tokens and never
    more than MAX_REASONING. An answer that breaks off, as the model reached
    the most it may write at once, is taken up by another request, without
    reasoning, until every block is written: the model is sent the part
    again, what it reasoned the first time and the blocks it has written
    whole, and writes those after the last of them. `progress` is kept as
    the answers stream in, and `report` called each time it changes. Raises
    TransformError, which carries what asking used."""
    problem = model.problem()
    if problem:
        raise TransformError(problem)
    text = json.dumps(blocks, ensure_ascii=False, indent=0)
    budget = min(budget or MAX_REASONING, MAX_REASONING)
    progress = progress or PartProgress()
    progress.expected = count(text)
    progress.budget = budget if think else None
    keys = list(blocks)
    written: dict[str, str] = {}
    notes = ""
    # the last block written whole, after which the next answer goes on
    last = keys[0]
    used: list[Profile] = []
    try:
        while True:
            progress.round += 1
            if progress.round == 1:
                prompt = _prompt(instructions, text, budget if think else None)
            else:
                prompt = PROMPTS(
                    "versions.continue",
                    instructions=instructions.strip(),
                    notes=notes.strip() or "(none)",
                    part=text,
                    written=json.dumps(written, ensure_ascii=False, indent=0),
                    next=keys[keys.index(last) + 1],
                )
            answer = _asked(
                prompt,
                model,
                think and progress.round == 1,
                budget,
                progress,
                report,
                stream,
            )
            used.append(answer.used)
            notes = notes or answer.reasoning
            if answer.finish != "length":
                written.update(read_part(answer.text))
                break
            begun = read_begun(answer.text)
            if not set(begun) - set(written):
                raise TransformError(
                    "the model reached the most it may write before it wrote a"
                    " whole block"
                )
            written.update(begun)
            last = max((key for key in written if key in blocks), key=keys.index)
            if last == keys[-1]:
                break
            if progress.round >= MAX_ROUNDS:
                raise TransformError(
                    f"the part was not written whole in {MAX_ROUNDS} answers"
                )
    except ProfileError as error:
        raise spent(TransformError(str(error)), used) from None
    except TransformError as error:
        raise spent(error, used) from None
    progress.state = "done"
    report()
    return written, used


def transform_parts(
    instructions: str,
    book: dict[str, Any],
    parts: list[list[tuple[int, int]]],
    model: Model,
    step: Callable[[], None],
    report: Callable[[list[dict[str, Any]]], None] = lambda progress: None,
    think: bool = True,
    stream: Stream = stream_transforming,
    titles: Sequence[str] = (),
    budget: int | None = None,
) -> tuple[list[dict[str, str]], list[Profile]]:
    """What `model` wrote for each part of `book`, as `transform_part` gives
    it, with what asking used. The parts are transformed a few at a time;
    `step` is called as each is done, and `report` told how each is going,
    as `PartProgress` says, whenever any changes, each by its title in
    `titles` if it has one. The model reasons in at most `budget` tokens
    for each part, if there is one. Raises the error of the first part that failed,
    carrying what asking for every part used."""
    progress = [
        PartProgress(titles[place] if place < len(titles) else "")
        for place in range(len(parts))
    ]
    lock = threading.Lock()

    def told() -> None:
        with lock:
            report([asdict(each) for each in progress])

    def one(place: int) -> tuple[dict[str, str], list[Profile]]:
        written = transform_part(
            instructions,
            part_blocks(book, parts[place]),
            model,
            think,
            progress[place],
            told,
            stream,
            budget,
        )
        step()
        return written

    told()
    with ThreadPoolExecutor(max_workers=PARALLEL_PARTS) as pool:
        futures = [pool.submit(one, place) for place in range(len(parts))]
    written: list[dict[str, str]] = []
    used: list[Profile] = []
    failed: BaseException | None = None
    for future in futures:
        try:
            blocks, profiles = future.result()
        except Exception as error:
            failed = failed or error
            used += spent_by(error)
            continue
        written.append(blocks)
        used += profiles
    if failed is not None:
        raise spent(failed, used)
    return written, used


def matches(part: list[tuple[int, int]], written: dict[str, str]) -> bool:
    """Whether the model wrote a part with the keys it was sent, in order."""
    return list(written) == [
        str(place) for start, end in part for place in range(start, end)
    ]


def _copied(
    book: dict[str, Any], emitted: Sequence[Emitted]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The blocks, the table of contents and the landmarks of a version of
    `book` made of the blocks `emitted` says, in order, without their links.
    A block the model added is a paragraph. An entry of the table of
    contents that leads to a heading written anew is called as it now says.
    An entry or a landmark that leads to a block that is left out is left
    out; the entries under such an entry are moved up to where it was."""
    blocks: list[dict[str, Any]] = []
    places: dict[int, int] = {}
    rewrite: dict[int, str] = {}
    for old, text in emitted:
        if old is None:
            blocks.append({"text": text or "", "size": 1})
            continue
        block = {
            name: value
            for name, value in book["blocks"][old].items()
            if name != "links"
        }
        if text is not None:
            block["text"] = rewrite[old] = text
        places[old] = len(blocks)
        blocks.append(block)
    ranks = headings(book["blocks"]) if rewrite else {}

    def entries(listed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for entry in listed:
            under = entries(entry.get("entries", []))
            block = entry.get("block")
            if block in places:
                kept: dict[str, Any] = {
                    "title": rewrite[block]
                    if block in rewrite and block in ranks
                    else entry.get("title", ""),
                    "block": places[block],
                }
                if under:
                    kept["entries"] = under
                found.append(kept)
            else:
                found += under
        return found

    landmarks = [
        {**landmark, "block": places[landmark["block"]]}
        for landmark in book.get("landmarks", [])
        if landmark.get("block") in places
    ]
    return blocks, entries(book.get("contents", [])), landmarks


def transformed(
    book: dict[str, Any],
    parts: list[list[tuple[int, int]]],
    written: list[dict[str, str]],
    untouched_kept: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The blocks, the table of contents and the landmarks of a version of
    `book` with each of `parts` as the model wrote it, as `transform_part`
    gives it. The model is told not to change the structure of a part, but
    what it wrote is kept as it wrote it if it did: a block it left out is
    left out, and a key it added is a paragraph after the block it wrote
    before it, or before the first of the part. The blocks in no part are
    kept as they are if `untouched_kept`, and left out if not."""
    # what each block of a part is written as, from where it is on: its
    # text, then those the model added after it
    at: dict[int, list[Emitted]] = {}
    in_parts: set[int] = set()
    for part, blocks in zip(parts, written, strict=True):
        places = {
            str(place): place for start, end in part for place in range(start, end)
        }
        in_parts.update(places.values())
        anchor = part[0][0]
        for key, text in blocks.items():
            place = places.get(key)
            if place is not None:
                anchor = place
            at.setdefault(anchor, []).append((place, text))
    emitted: list[Emitted] = []
    for place in range(len(book["blocks"])):
        if place in in_parts:
            emitted += at.get(place, [])
        elif untouched_kept:
            emitted.append((place, None))
    return _copied(book, emitted)


def stripped(
    book: dict[str, Any], keep: list[tuple[int, int]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """The blocks, the table of contents and the landmarks of a version of
    `book`, kept as the store keeps them, made of the blocks in the
    stretches `keep`, without their links. An entry or a landmark that
    leads to a block that is left out is left out; the entries under such
    an entry are moved up to where it was."""
    return _copied(
        book, [(place, None) for start, end in keep for place in range(start, end)]
    )
