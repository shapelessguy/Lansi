# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Sentences with gaps to fill in, made by a model for the points of the
lesson, and checked against what the model meant to go into each gap.

A sentence is written with its gaps in brackets, such as
`Ich [stehe] um 6 Uhr [auf].`, and a gap that takes more than one answer
lists them with `|`. A sentence is right if every gap is, partial if some
are, or if they differ only in capitals or umlauts, and wrong otherwise.

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
    loose,
    option,
    serve,
    written,
)

_GAP = re.compile(r"\[([^\[\]]+)\]")
# how many sentences an instance is
SENTENCES = 5
# what the answers for the gaps of a sentence are joined with in its grade
GAPS_JOINED = "; "

MAKING = """\
You write fill-in-the-gap exercises for someone learning {language}. Write \
{count} different sentences in {language} that practise the rules below, \
about the topics below. {level}

{lesson}
{plan}{topics}
{words}{guidance}{made}

In each sentence, put the words the learner is to fill in between [ and ]: \
one or two gaps, each a word whose form, or whose choice, the rule the \
sentence practises decides. A word the learner could only guess, whatever \
they know of the rule, is no gap. If more than one answer is right, list \
them in the gap separated by |.

Give a hint for each gap: what the learner starts from to find the word, \
such as the form a dictionary lists it under. Leave the hint empty where \
it would be the word itself, or give it away. Give each sentence a \
translation into {into}.

Reply with JSON alone, an item for each sentence in the order asked, and a \
hint for each gap of it, in order: {{"items": [{{"text": "...", "hints": \
["..."], "translation": "..."}}]}}"""


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


def judge(text: str, given: list[str]) -> tuple[str, str]:
    """Whether what was given for the gaps of a sentence is right, partial
    or wrong, with a note on a gap that is almost right."""
    gaps = answers_of(text)
    exact = near = 0
    almost = []
    for accepted, answer in zip(gaps, given + [""] * len(gaps)):
        answer = " ".join(answer.split())
        if answer in accepted:
            exact += 1
        elif answer and loose(answer) in {loose(each) for each in accepted}:
            near += 1
            almost.append(f"{answer} → {accepted[0]}")
    note = f"capitals or umlauts: {', '.join(almost)}" if almost else ""
    if exact == len(gaps):
        return "right", note
    if exact or near:
        return "partial", note
    return "wrong", note


def hints_of(text: str, hints: Any) -> list[str]:
    """A hint for each gap of a sentence, from those the model gave: empty
    where it gave none, or one that is what goes into the gap, but for
    capitals and umlauts, as that would give the answer away."""
    given = hints if isinstance(hints, list) else []
    kept = []
    for number, accepted in enumerate(answers_of(text)):
        hint = given[number] if number < len(given) else ""
        hint = " ".join(hint.split()) if isinstance(hint, str) else ""
        answers = {loose(answer) for answer in accepted}
        kept.append("" if loose(hint) in answers else hint)
    return kept


def read_items(reply: Any, count: int = SENTENCES) -> list[dict[str, Any]]:
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
                "hints": hints_of(item["text"], item.get("hints")),
                "translation": str(item.get("translation") or ""),
            }
        )
    if not items:
        raise ModelError("the model made no sentence with a gap")
    return items[:count]


def sentences_of(context: dict[str, Any]) -> int:
    """How many sentences a set is, as the learner chose."""
    return int(option(context, "sentences", SENTENCES))


def make_set(context: dict[str, Any], state: dict[str, Any], model: Model) -> None:
    """Has the model make the next set of sentences, other than those made
    before, unless it was made already or every set was."""
    sets = state["sets"]
    if len(sets) > len(state["checked"]) or len(sets) >= context["instances"]:
        return
    prompt = MAKING.format(
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
    sets.append(read_items(reply, sentences_of(context)))


def check(text: str, given: list[str]) -> dict[str, str]:
    """What the learner is told of the answers given for the gaps of a
    sentence, which is graded as it is."""
    result, note = judge(text, given)
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
            check(item["text"], given) for item, given in zip(items, given_gaps)
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
    return Step(state=state, results={"sets": done, "total": context["instances"]})


if __name__ == "__main__":
    serve(start, act, finish)
