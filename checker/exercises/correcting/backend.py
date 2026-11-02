# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""One of the learner's own texts, such as their homework, as the option
`text` chooses it among those that are not corrected yet, corrected at
once, with nothing for the learner to do. It is not chosen among the
exercises: the app runs it when the learner asks for a text to be
corrected, typed or written by hand alike.

The text comes as its words, each by its id, its place among them from 0,
as `words` of the text in the context has them: those read from its pages,
for one written by hand, and those between its spaces, for a typed one, a
mark such as a comma going with the word it is written against. A model
answers with what is to be done to them, each a function of its own, named
by `type`, with the ids it is about:

    replace   from_id, to_id, text    the words are wrong: these are right
    erase     from_id, to_id          the words are too many
    insert    after_id, text          words are missing after it, -1 for
                                      before the first
    move      from_id, to_id, after_id   the words go elsewhere
    join      from_id, to_id, text    the words are one
    split     id, text                the word is several
    suggest   from_id, to_id, text    right, but this is said more naturally
    comment   from_id, to_id, text    a note, with nothing changed
    praise    from_id, to_id, text    done well
    misread   from_id, to_id, text    the words were read wrong from the
                                      page: this is what is written
    illegible from_id, to_id          they cannot be read

each with the `category` of the mistake and an `explanation`, but misread
and illegible, which are not the learner's, and with the words it is about
as they are written, `was`, and the word an insertion goes after, `after`,
by which one whose ids are a few words off is put where it belongs, as a
model may miscount them, and one that is not about the words it says is left
out. The app shows them in the text, or draws them on the pages written by
hand; where only some of the letters of a word are wrong, it finds them
itself, the model giving the whole word.

The instance is the text, graded once: right if it had no mistake, and
partial otherwise, with the text corrected and the mistakes as the note.
"""

from __future__ import annotations

import json
from typing import Any, TypeGuard

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
# how many times the model is asked to correct the text before it is given up on
TRIES = 2

# what each function is told with, besides its type
SHAPES: dict[str, tuple[str, ...]] = {
    "replace": ("span", "text"),
    "erase": ("span",),
    "insert": ("after", "text"),
    "move": ("span", "after"),
    "join": ("span", "text"),
    "split": ("id", "text"),
    "suggest": ("span", "text"),
    "comment": ("span", "text"),
    "praise": ("span", "text"),
    "misread": ("span", "text"),
    "illegible": ("span",),
}
# those that correct a mistake of the learner's
MISTAKES = frozenset({"replace", "erase", "insert", "move", "join", "split"})
# those that change the words, which may not change the same word twice
CHANGES = MISTAKES | {"misread"}
# how many words away from where its ids put it a correction is looked for
# by the words it says it is about
NEAR = 3


def _same(one: str, other: str) -> bool:
    """Whether two stretches of words are the same, but for their spaces."""
    return one.split() == other.split()


def _placed(words: list[str], start: int, length: int, was: str) -> int | None:
    """Where the `length` words that are `was` start, the nearest to `start`
    first, at most `NEAR` words away; None if they are nowhere near it."""
    for away in range(NEAR + 1):
        for at in (start - away, start + away) if away else (start,):
            if (
                0 <= at
                and at + length <= len(words)
                and _same(" ".join(words[at : at + length]), was)
            ):
                return at
    return None


def start(context: dict[str, Any], model: Model) -> Step:
    """Corrects the text chosen at once: there is nothing for the learner to
    do but see the corrections."""
    text = context.get("texts", {}).get("text")
    if not text:
        raise ModelError(
            "this exercise needs one of your texts that is not corrected yet"
        )
    words = [str(word) for word in text.get("words") or []]
    if not words:
        raise ModelError("the text is empty: write something in it first")
    state = {
        "title": text["title"],
        "text": text["content"],
        "words": words,
        "handwritten": bool(text.get("handwritten")),
        "corrections": None,
        "summary": "",
    }
    return _corrected(context, state, model)


def _show(state: dict[str, Any]) -> dict[str, Any]:
    """The text with its corrections, which is all there is to see."""
    return {
        "title": state["title"],
        "words": state["words"],
        "corrections": state["corrections"],
        "summary": state["summary"],
    }


def _whole(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _spanned(correction: dict[str, Any]) -> range:
    """The ids of the words a correction changes."""
    if "id" in correction:
        return range(correction["id"], correction["id"] + 1)
    if "from_id" in correction:
        return range(correction["from_id"], correction["to_id"] + 1)
    return range(0)


def _spaced(correction: dict[str, Any], words: list[str]) -> dict[str, Any]:
    """A replacement as what it only does, which the app marks as such: the
    insertion of words before or after those it keeps as they are, or the
    split or the join of words."""
    start, end, text = correction["from_id"], correction["to_id"], correction["text"]
    was = words[start : end + 1]
    told = text.split()
    about: dict[str, Any] = {
        key: correction[key] for key in ("category", "explanation") if key in correction
    }
    if len(told) > len(was) and told[-len(was) :] == was:
        added = " ".join(told[: len(told) - len(was)])
        return {"type": "insert", "after_id": start - 1, "text": added, **about}
    if len(told) > len(was) and told[: len(was)] == was:
        added = " ".join(told[len(was) :])
        return {"type": "insert", "after_id": end, "text": added, **about}
    if "".join(was) != "".join(told) or len(was) == len(told):
        return correction
    if start == end:
        return {"type": "split", "id": start, "text": text, **about}
    return {"type": "join", "from_id": start, "to_id": end, "text": text, **about}


def read_corrections(
    reply: Any, count: int, words: list[str] | None = None
) -> list[dict[str, Any]] | None:
    """The corrections the model gave of a text of `count` words, those
    that are what a function takes, and that do not change a word another
    one changed before; or None if it gave no list of them. With the
    `words`, one that says which words it is about is put where they are,
    if they are a few words off its ids, and left out if they are not
    near."""
    listed = reply.get("corrections") if isinstance(reply, dict) else None
    if not isinstance(listed, list):
        return None
    taken: list[dict[str, Any]] = []
    changed: set[int] = set()
    for each in listed:
        if not isinstance(each, dict) or each.get("type") not in SHAPES:
            continue
        kind = each["type"]
        kept: dict[str, Any] = {"type": kind}
        fields = SHAPES[kind]
        said = each.get("was")
        was = said if isinstance(said, str) and said.strip() else None
        if "span" in fields:
            start, end = each.get("from_id"), each.get("to_id")
            if not (_whole(start) and _whole(end) and 0 <= start <= end < count):
                continue
            if was is not None and words is not None:
                found = _placed(words, start, len(was.split()), was)
                if found is None:
                    continue
                start, end = found, found + len(was.split()) - 1
            kept.update(from_id=start, to_id=end)
        if "id" in fields:
            if not (_whole(each.get("id")) and 0 <= each["id"] < count):
                continue
            kept["id"] = each["id"]
            if was is not None and words is not None:
                found = _placed(words, each["id"], 1, was)
                if found is None:
                    continue
                kept["id"] = found
        if "after" in fields:
            after = each.get("after_id")
            if not (_whole(after) and -1 <= after < count):
                continue
            behind = each.get("after")
            if (
                isinstance(behind, str)
                and behind.strip()
                and words is not None
                and after >= 0
            ):
                found = _placed(words, after, 1, behind)
                if found is None:
                    continue
                after = found
            kept["after_id"] = after
        if "text" in fields:
            text = each.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            kept["text"] = text.strip()
        if kind == "replace" and words is not None:
            kept = _spaced(kept, words)
        if kind in CHANGES:
            spanned = set(_spanned(kept))
            if spanned & changed:
                continue
            changed |= spanned
        if kind not in ("misread", "illegible"):
            for name in ("category", "explanation"):
                if isinstance(each.get(name), str) and each[name].strip():
                    kept[name] = each[name].strip()
        taken.append(kept)
    return taken


def applied(
    words: list[str], corrections: list[dict[str, Any]], kinds: frozenset[str]
) -> str:
    """`words` with those of `corrections` of `kinds` done to them, as a
    text: the words moved last, where they go once the others are done."""
    tokens: list[list[str]] = [[word] for word in words]
    before: list[str] = []

    def after(at: int) -> list[str]:
        return before if at < 0 else tokens[at]

    for correction in corrections:
        kind = correction["type"]
        if kind not in kinds or kind == "move":
            continue
        if kind in ("replace", "join", "misread", "erase"):
            spanned = _spanned(correction)
            for at in spanned:
                tokens[at] = []
            if kind != "erase":
                tokens[spanned.start] = [correction["text"]]
        elif kind == "split":
            tokens[correction["id"]] = [correction["text"]]
        elif kind == "insert":
            after(correction["after_id"]).append(correction["text"])
    for correction in corrections:
        if correction["type"] == "move" and "move" in kinds:
            spanned = _spanned(correction)
            moved = [token for at in spanned for token in tokens[at]]
            for at in spanned:
                tokens[at] = []
            after(correction["after_id"]).extend(moved)
    return " ".join(before + [token for each in tokens for token in each])


def _described(words: list[str], correction: dict[str, Any]) -> str:
    """A mistake as the note of the grade says it."""
    was = " ".join(words[at] for at in _spanned(correction))
    if correction["type"] == "insert":
        was = "(nothing)"
    kind = correction["type"]
    right = correction.get("text") or ("(nothing)" if kind == "erase" else "")
    if kind == "move":
        place = correction["after_id"]
        right = f"moved after «{words[place]}»" if place >= 0 else "moved to the start"
    return f"{was} → {right}: {correction.get('explanation', '')}".rstrip(": ")


def _corrected(context: dict[str, Any], state: dict[str, Any], model: Model) -> Step:
    """Has the model correct the words of the text of `state`, and the text
    graded once on them."""
    words = state["words"]
    prompt = PROMPTS(
        "correcting",
        language=context["language"],
        into=context["into"],
        level=describe_level(context),
        title=state["title"],
        guidance=describe_guidance(context),
        reading=PROMPTS(
            "reading.handwritten" if state["handwritten"] else "reading.typed"
        ),
        words=json.dumps(dict(enumerate(words)), ensure_ascii=False, indent=0),
    )
    corrections = None
    reply: Any = None
    for _ in range(TRIES):
        reply = ask_json(model, [{"role": "user", "content": prompt}])
        corrections = read_corrections(reply, len(words), words)
        if corrections is not None:
            break
    if corrections is None:
        raise ModelError("the model gave no corrections of the text")
    summary = str(reply.get("summary") or "") if isinstance(reply, dict) else ""
    state.update(corrections=corrections, summary=summary)
    # what the learner wrote, as it is on the page, and as it is once corrected
    wrote = applied(words, corrections, frozenset({"misread"}))
    corrected = applied(words, corrections, CHANGES)
    mistakes = [each for each in corrections if each["type"] in MISTAKES]
    one = grade(
        "partial" if mistakes else "right",
        wrote,
        corrected if mistakes else "",
        "\n".join(_described(words, each) for each in mistakes),
        f'Their own text, "{state["title"]}"',
    )
    return Step(
        state=state,
        show=_show(state),
        graded=[one],
        written=written([wrote], [corrected] if mistakes else []),
    )


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    """There is nothing to act on: the text is corrected as it starts."""
    return Step(state=state, show=_show(state))


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    """Keeps the text as it was corrected, with its words and their
    corrections as the correction, in JSON, if it was corrected."""
    if state["corrections"] is None:
        return Step(state=state)
    return Step(
        state=state,
        results={
            "texts": {
                "text": {
                    "content": state["text"],
                    "correction": json.dumps(
                        {
                            "words": state["words"],
                            "corrections": state["corrections"],
                            "summary": state["summary"],
                        },
                        ensure_ascii=False,
                    ),
                }
            },
            "mistakes": sum(
                1 for each in state["corrections"] if each["type"] in MISTAKES
            ),
        },
    )


if __name__ == "__main__":
    serve(start, act, finish)
