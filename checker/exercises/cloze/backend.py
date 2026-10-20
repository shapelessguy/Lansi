# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Sentences with gaps to fill in, made by a model for the points of the
lesson, and checked against what the model meant to go into each gap.

A sentence is written with its gaps in brackets, such as
`I [get] [up] at six.`, and a gap that takes more than one answer
lists them with `|`. A sentence is right if every gap is, partial if some
are, or if they differ only in capitals, in the marks on letters or in the
letters of the language written otherwise, and wrong otherwise.

An instance is a set of sentences, as many as the option `sentences` says,
shown and checked together, and graded once. The sets are made one at a time: the first when the
exercise starts, and each other once the one before was checked, when the
interface asks for it to be `prepare`d while the learner reads what was
right, or else when it goes on to the `next`.

Once a set is checked, what the learner wrote into the gaps is reported as
written by them, and the sentences as they are right as written by the
model.
"""

from __future__ import annotations

import re
from typing import Any

from kit import (
    Model,
    ModelError,
    Step,
    ask_json,
    describe_guidance,
    describe_lesson,
    describe_level,
    describe_made,
    describe_plan,
    describe_topics,
    describe_words,
    grade,
    grade_of,
    letters_of,
    loose,
    marks_of,
    option,
    prompts_beside,
    score_of,
    serve,
    written,
)

_GAP = re.compile(r"\[([^\[\]]+)\]")
# how many hints there may be in all the sentences of a set
MAX_HINTS = 1
# how many sentences an instance is
SENTENCES = 5
# what the answers for the gaps of a sentence are joined with in its grade
GAPS_JOINED = "; "

# what the exercise tells the model, by name
PROMPTS = prompts_beside(__file__)


def parts_of(text: str) -> list[str | None]:
    """The text of a sentence with each gap as None."""
    parts: list[str | None] = []
    for number, piece in enumerate(_GAP.split(text)):
        parts.append(piece if number % 2 == 0 else None)
    return [part for part in parts if part != ""]


def answers_of(text: str) -> list[list[str]]:
    """What may go into each gap of a sentence."""
    return [
        [answer.strip() for answer in gap.split("|") if answer.strip()]
        for gap in _GAP.findall(text)
    ]


def filled(text: str, answers: list[str]) -> str:
    """The sentence with its gaps filled in by `answers`."""
    given = iter(answers)
    return _GAP.sub(lambda gap: next(given, ""), text)


def task_of(item: dict[str, Any]) -> str:
    """The sentence as the learner was given it, each gap a ___ with its
    hint, if it has one."""
    hints = iter(item["hints"])

    def gap(_: re.Match[str]) -> str:
        hint = next(hints, "")
        return f"___ ({hint})" if hint else "___"

    return _GAP.sub(gap, item["text"])


def fills(answers: list[str]) -> str:
    """What went into the gaps of a sentence, in their order."""
    return GAPS_JOINED.join(" ".join(answer.split()) or "(empty)" for answer in answers)


def judge(
    text: str,
    given: list[str],
    letters: dict[str, str] | None = None,
    marks: str = "accents",
) -> tuple[str, str]:
    """Whether what was given for the gaps of a sentence is right, partial
    or wrong, with a note on a gap that is almost right: one that is right
    but for its capitals, its `marks` or its `letters`, as `loose` has them."""
    gaps = answers_of(text)
    exact = near = 0
    almost = []
    for accepted, answer in zip(gaps, given + [""] * len(gaps)):
        answer = " ".join(answer.split())
        if answer in accepted:
            exact += 1
        elif answer and loose(answer, letters) in {
            loose(each, letters) for each in accepted
        }:
            near += 1
            almost.append(f"{answer} → {accepted[0]}")
    note = f"capitals or {marks}: {', '.join(almost)}" if almost else ""
    if exact == len(gaps):
        return "right", note
    if exact or near:
        return "partial", note
    return "wrong", note


def hints_of(text: str, hints: Any, letters: dict[str, str] | None = None) -> list[str]:
    """A hint for each gap of a sentence, from those the model gave: empty
    where it gave none, or one that is what goes into the gap, as `loose`
    has it with the `letters` of the language, as that would give the
    answer away."""
    given = hints if isinstance(hints, list) else []
    kept = []
    for number, accepted in enumerate(answers_of(text)):
        hint = given[number] if number < len(given) else ""
        hint = " ".join(hint.split()) if isinstance(hint, str) else ""
        answers = {loose(answer, letters) for answer in accepted}
        kept.append("" if loose(hint, letters) in answers else hint)
    return kept


def read_items(
    reply: Any, count: int = SENTENCES, letters: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """The sentences the model made, those with a gap and no more than
    `count`. Raises ModelError if there are none."""
    listed = reply.get("items") if isinstance(reply, dict) else None
    items = []
    for item in listed if isinstance(listed, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        if not answers_of(item["text"]) or not all(answers_of(item["text"])):
            continue
        items.append(
            {
                "text": item["text"].strip(),
                "hints": hints_of(item["text"], item.get("hints"), letters),
                "translation": str(item.get("translation") or ""),
            }
        )
    if not items:
        raise ModelError("the model made no sentence with a gap")
    return fewer_hints(items[:count])


def fewer_hints(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The sentences of a set with no more than `MAX_HINTS` hints in all,
    the first ones given, as a learner finds a word from the sentence and
    the rule rather than from a hint."""
    left = MAX_HINTS
    for item in items:
        kept = []
        for hint in item["hints"]:
            kept.append(hint if hint and left > 0 else "")
            left -= 1 if hint else 0
        item["hints"] = kept
    return items


def sentences_of(context: dict[str, Any]) -> int:
    """How many sentences a set is, as the learner chose."""
    return int(option(context, "sentences", SENTENCES))


def make_set(context: dict[str, Any], state: dict[str, Any], model: Model) -> None:
    """Has the model make the next set of sentences, other than those made
    before, unless it was made already or every set was."""
    sets = state["sets"]
    if len(sets) > len(state["checked"]) or len(sets) >= context["instances"]:
        return
    prompt = PROMPTS(
        "making",
        language=context["language"],
        count=sentences_of(context),
        level=describe_level(context),
        lesson=describe_lesson(context),
        # each set goes on from where the one before left the rules
        plan=describe_plan(
            context, sentences_of(context), sum(len(made) for made in sets)
        ),
        topics=describe_topics(context),
        words=describe_words(context),
        guidance=describe_guidance(context),
        made=describe_made([item["text"] for made in sets for item in made]),
        into=context["into"],
    )
    reply = ask_json(model, [{"role": "user", "content": prompt}])
    sets.append(read_items(reply, sentences_of(context), letters_of(context)))


def check(context: dict[str, Any], text: str, given: list[str]) -> dict[str, str]:
    """What the learner is told of the answers given for the gaps of a
    sentence, which is graded as it is."""
    result, note = judge(text, given, letters_of(context), marks_of(context))
    correct = filled(text, [gap[0] for gap in answers_of(text)])
    answered = filled(text, given)
    return {
        "result": result,
        "answer": answered,
        "correction": "" if result == "right" else correct,
        "correct": correct,
        "note": note,
    }


def _show(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """What the interface shows: the set of sentences to be answered, or
    how the last set went, with whether there is another and whether it
    was made already."""
    checked = state["checked"]
    shown: dict[str, Any] = {"at": len(checked), "total": context["instances"]}
    if state["reviewing"]:
        shown["feedback"] = checked[-1]["feedback"]
        shown["result"] = checked[-1]["result"]
        shown["more"] = len(checked) < context["instances"]
        shown["prepared"] = len(state["sets"]) > len(checked)
    else:
        shown["items"] = [
            {
                "parts": parts_of(item["text"]),
                # sets made before there was a hint for each gap have one for all
                "hints": item.get("hints", []),
                "hint": item.get("hint", ""),
                "translation": item["translation"],
            }
            for item in state["sets"][len(checked)]
        ]
    return shown


def start(context: dict[str, Any], model: Model) -> Step:
    state: dict[str, Any] = {"sets": [], "checked": [], "reviewing": False}
    make_set(context, state, model)
    return Step(state=state, show=_show(context, state))


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    """Checks the answers of the set on show, as `{"answers": [[...], ...]}`
    with those for the gaps of each sentence; makes the next set, as
    `{"prepare": true}`; or goes on to it, as `{"next": true}`."""
    message = message if isinstance(message, dict) else {}
    checked = state["checked"]
    more = len(checked) < context["instances"]
    if message.get("prepare") and state["reviewing"] and more:
        make_set(context, state, model)
    elif message.get("next") and state["reviewing"] and more:
        make_set(context, state, model)
        state["reviewing"] = False
    elif isinstance(message.get("answers"), list) and not state["reviewing"]:
        items = state["sets"][len(checked)]
        answers = [*message["answers"], *[[]] * len(items)][: len(items)]
        given_gaps = [
            [each if isinstance(each, str) else "" for each in given]
            if isinstance(given, list)
            else []
            for given in answers
        ]
        feedback = [
            check(context, item["text"], given)
            for item, given in zip(items, given_gaps)
        ]
        # the learner wrote only what went into the gaps, and is graded on it
        graded = grade_of(
            [
                grade(
                    each["result"],
                    fills(given + [""] * (len(gaps) - len(given))),
                    ""
                    if each["result"] == "right"
                    else fills([gap[0] for gap in gaps]),
                    each["note"],
                    task_of(item),
                )
                for item, given, each in zip(items, given_gaps, feedback)
                for gaps in [answers_of(item["text"])]
            ]
        )
        checked.append({"feedback": feedback, "result": graded["result"]})
        state["reviewing"] = True
        said = written(
            [
                " ".join(each for each in given if isinstance(each, str) and each)
                for given in answers
                if isinstance(given, list)
            ],
            [each["correct"] for each in feedback],
        )
        return Step(
            state=state, show=_show(context, state), graded=[graded], written=said
        )
    return Step(state=state, show=_show(context, state))


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    done = [
        {"items": made, **checked}
        for made, checked in zip(state["sets"], state["checked"])
    ]
    # each sentence counts, of every set that was checked
    score = score_of(
        [each["result"] for checked in state["checked"] for each in checked["feedback"]]
    )
    return Step(
        state=state,
        results={"sets": done, "total": context["instances"]},
        scores=None if score is None else {"structures": score},
    )


if __name__ == "__main__":
    serve(start, act, finish)
