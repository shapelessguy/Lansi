# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""One of the learner's own texts, such as their homework, as the option
`text` chooses it among those that are not corrected yet, corrected at
once, with nothing for the learner to do: the interface finishes the
exercise as soon as it shows the corrections. A model marks each
mistake with its correction and why, and the text and a copy of it with the
corrections and their comments worked in, in Markdown, are what the
exercise comes to; the app shows the copy in place of the text, which it
locks.

The instance is the text, graded once: right if it had no mistake, and
partial otherwise, with the corrected text and the mistakes as the note.
"""

from __future__ import annotations

from typing import Any

from kit import (
    Model,
    ModelError,
    Step,
    ask_json,
    describe_guidance,
    describe_level,
    grade,
    prompts_beside,
    serve,
    written,
)

PROMPTS = prompts_beside(__file__)
# how many times the model is asked to mark the text before it is given up on
TRIES = 2


def start(context: dict[str, Any], model: Model) -> Step:
    """Corrects the text chosen at once: there is nothing for the learner to
    do but see the corrections, as the interface finishes the exercise as
    soon as it shows them."""
    text = context.get("texts", {}).get("text")
    if not text:
        raise ModelError(
            "this exercise needs one of your texts that is not corrected yet"
        )
    if not text["content"].strip():
        raise ModelError("the text is empty: write something in it first")
    state = {
        "title": text["title"],
        "text": text["content"],
        "parts": None,
        "summary": "",
    }
    return _corrected(context, state, model)


def _show(state: dict[str, Any]) -> dict[str, Any]:
    """The text with its corrections, which is all there is to see."""
    return {
        "title": state["title"],
        "parts": state["parts"],
        "summary": state["summary"],
    }


def read_parts(reply: Any) -> list[dict[str, str]] | None:
    """The parts the model wrote the text in, each a part that is right,
    `{"text": ...}`, or a mistake, `{"wrong": ..., "right": ..., "why": ...}`;
    or None if it wrote none. The text is as the model wrote it out, which
    may differ a little from the learner's, such as in its spaces."""
    listed = reply.get("parts") if isinstance(reply, dict) else None
    parts: list[dict[str, str]] = []
    for part in listed if isinstance(listed, list) else []:
        if not isinstance(part, dict):
            continue
        if "wrong" in part or "right" in part:
            wrong, right = str(part.get("wrong") or ""), str(part.get("right") or "")
            if wrong != right:
                parts.append(
                    {"wrong": wrong, "right": right, "why": str(part.get("why") or "")}
                )
                continue
            part = {"text": wrong}
        if isinstance(part.get("text"), str) and part["text"]:
            # parts that are right are joined, as the model may cut them anywhere
            if parts and "text" in parts[-1]:
                parts[-1] = {"text": parts[-1]["text"] + part["text"]}
            else:
                parts.append({"text": part["text"]})
    return parts or None


def corrected_of(parts: list[dict[str, str]]) -> str:
    """The text as it is once corrected."""
    return "".join(part.get("text", part.get("right", "")) for part in parts)


def mistakes_of(parts: list[dict[str, str]]) -> list[dict[str, str]]:
    return [part for part in parts if "wrong" in part]


def _wrapped(text: str, mark: str) -> tuple[str, str, str]:
    """`text` between `mark`s, with the spaces at its ends left outside
    them, as Markdown takes a mark only next to a word: what goes before,
    the marked text, and what goes after."""
    core = text.strip()
    if not core:
        return text, "", ""
    start = text.index(core)
    return text[:start], f"{mark}{core}{mark}", text[start + len(core) :]


def _marked(part: dict[str, str]) -> str:
    """A mistake as Markdown: what was wrong struck through, what is right
    in bold beside it, and why in italics after them, as a comment."""
    before, wrong, after = _wrapped(part["wrong"], "~~")
    lead, right, trail = _wrapped(part["right"], "**")
    why = " ".join(part["why"].split())
    comment = f" _({why})_" if why else ""
    if wrong and right:
        return f"{before or lead}{wrong} {right}{comment}{after or trail}"
    if wrong:
        return before + wrong + comment + after
    return lead + right + comment + trail


def markdown_of(parts: list[dict[str, str]]) -> str:
    """The text as it was written, with its corrections and their comments
    worked in, in Markdown: each mistake struck through, its correction in
    bold beside it, and why in italics after them."""
    return (
        "".join(part["text"] if "text" in part else _marked(part) for part in parts)
        + "\n"
    )


def _corrected(context: dict[str, Any], state: dict[str, Any], model: Model) -> Step:
    """Has the model mark the mistakes of the text of `state`, and the text
    graded once on them."""
    text = state["text"]
    prompt = PROMPTS(
        "correcting",
        language=context["language"],
        into=context["into"],
        level=describe_level(context),
        title=state["title"],
        guidance=describe_guidance(context),
        text=text,
    )
    parts = None
    for _ in range(TRIES):
        reply = ask_json(model, [{"role": "user", "content": prompt}])
        parts = read_parts(reply)
        if parts is not None:
            break
    if parts is None:
        raise ModelError("the model wrote no text with its corrections")
    summary = str(reply.get("summary") or "") if isinstance(reply, dict) else ""
    state.update(parts=parts, summary=summary)
    mistakes = mistakes_of(parts)
    corrected = corrected_of(parts)
    one = grade(
        "partial" if mistakes else "right",
        text,
        corrected if mistakes else "",
        "\n".join(
            f"{part['wrong'] or '(nothing)'} → {part['right'] or '(nothing)'}: {part['why']}"
            for part in mistakes
        ),
        f'Their own text, "{state["title"]}"',
    )
    return Step(
        state=state,
        show=_show(state),
        graded=[one],
        written=written([text], [corrected] if mistakes else []),
    )


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    """There is nothing to act on: the text is corrected as it starts."""
    return Step(state=state, show=_show(state))


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    """Keeps the text as it was corrected, and the copy of it with the
    corrections marked, if it was corrected."""
    if state["parts"] is None:
        return Step(state=state)
    return Step(
        state=state,
        results={
            "texts": {
                "text": {
                    "content": state["text"],
                    "correction": markdown_of(state["parts"]),
                }
            },
            "mistakes": len(mistakes_of(state["parts"])),
        },
    )


if __name__ == "__main__":
    serve(start, act, finish)
