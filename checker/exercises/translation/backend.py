# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Sentences to translate into the language being learned, made by a model
so that translating them takes the points of the lesson, and judged by a
model against those points.

An instance is a set of sentences, as many as the option `sentences` says,
shown together, judged in one request to the model and graded once. The sets are made one at a time: the
first when the exercise starts, and each other once the one before was
judged, when the interface asks for it to be `prepare`d while the learner
reads the judgement, or else when it goes on to the `next`.

Once a set is judged, the translations are reported as written by the
learner, and the corrections and the other ways the learner is shown as
written by the model.

Each set is an instance, reported as made in the step it is made in, as
`{"items": [...]}`; when the exercise is done again, the sets it made are
taken in order from `replay` in place of being made, and those it
had not made yet when it was left are made as before.
"""

from __future__ import annotations

from typing import Any

from kit import (
    RESULTS,
    Model,
    ModelError,
    Step,
    ask_json,
    describe_guidance,
    describe_lesson,
    describe_level,
    describe_made,
    describe_topics,
    describe_words,
    grade,
    grade_of,
    level_of,
    option,
    prompts_beside,
    score_of,
    serve,
    written,
)

# how many sentences an instance is
SENTENCES = 5
# more than anyone writes for one sentence
MAX_ANSWER_LENGTH = 1000

# what the exercise tells the models, by name
PROMPTS = prompts_beside(__file__)


def read_items(reply: Any, count: int = SENTENCES) -> list[dict[str, str]]:
    """The sentences the model made, no more than `count`. Raises
    ModelError if there are none."""
    listed = reply.get("items") if isinstance(reply, dict) else None
    items = [
        {"source": item["source"].strip(), "reference": item["reference"].strip()}
        for item in (listed if isinstance(listed, list) else [])
        if isinstance(item, dict)
        and isinstance(item.get("source"), str)
        and isinstance(item.get("reference"), str)
        and item["source"].strip()
    ]
    if not items:
        raise ModelError("the model made no sentence to translate")
    return items[:count]


def read_verdict(reply: Any) -> tuple[str, str, str]:
    """The result, correction and note of a judgement. Raises ModelError."""
    if not isinstance(reply, dict) or reply.get("result") not in RESULTS:
        raise ModelError("the model gave no judgement")
    correction, note = reply.get("correction"), reply.get("note")
    return (
        reply["result"],
        correction if isinstance(correction, str) else "",
        note if isinstance(note, str) else "",
    )


def read_verdicts(reply: Any, count: int) -> list[tuple[str, str, str]]:
    """The judgement of each of `count` translations. Raises ModelError if
    there is not one for each."""
    listed = reply.get("verdicts") if isinstance(reply, dict) else None
    if not isinstance(listed, list) or len(listed) != count:
        raise ModelError(f"the model did not judge each of the {count} translations")
    return [read_verdict(each) for each in listed]


def sentences_of(context: dict[str, Any]) -> int:
    """How many sentences a set is, as the learner chose."""
    return int(option(context, "sentences", SENTENCES))


def make_set(
    context: dict[str, Any], state: dict[str, Any], model: Model
) -> list[dict[str, Any]]:
    """Has the model make the next set of sentences, other than those made
    before, unless it was made already or every set was; or takes it from
    those done again. Returns what was made, as the instances to report."""
    sets = state["sets"]
    if len(sets) > len(state["checked"]) or len(sets) >= context["instances"]:
        return []
    replay = context.get("replay")
    # what was made before is done again, and what was not made then is made now
    if replay and len(sets) < len(replay):
        sets.append([dict(item) for item in replay[len(sets)]["items"]])
        return []
    prompt = PROMPTS(
        "making",
        language=context["language"],
        count=sentences_of(context),
        into=context["into"],
        level=describe_level(context),
        lesson=describe_lesson(context),
        topics=describe_topics(context),
        words=describe_words(context),
        guidance=describe_guidance(context, len(sets) + 1),
        made=describe_made([item["source"] for made in sets for item in made]),
    )
    reply = ask_json(model, [{"role": "user", "content": prompt}])
    sets.append(read_items(reply, sentences_of(context)))
    return [{"items": [dict(item) for item in sets[-1]]}]


def judge(
    context: dict[str, Any],
    items: list[dict[str, str]],
    answers: list[str],
    model: Model,
) -> list[dict[str, str]]:
    """What the learner is told of each translation of a set, which is
    graded as it is: those that were left empty are wrong, and the others
    are judged by the model, together. Raises ModelError."""
    written = [number for number, answer in enumerate(answers) if answer]
    sentences = "\n\n".join(
        PROMPTS(
            "sentence",
            number=order,
            into=context["into"],
            source=items[number]["source"],
            reference=items[number]["reference"],
            given=answers[number],
        )
        for order, number in enumerate(written, start=1)
    )
    verdicts: dict[int, tuple[str, str, str]] = {}
    if written:
        prompt = PROMPTS(
            "judging",
            language=context["language"],
            level=level_of(context),
            lesson=describe_lesson(context),
            into=context["into"],
            sentences=sentences,
        )
        reply = ask_json(model, [{"role": "user", "content": prompt}])
        verdicts = dict(zip(written, read_verdicts(reply, len(written))))
    feedback = []
    for number, item in enumerate(items):
        result, correction, note = verdicts.get(
            number, ("wrong", item["reference"], "")
        )
        feedback.append(
            {
                "result": result,
                "source": item["source"],
                "answer": answers[number],
                "correction": correction,
                "reference": item["reference"],
                "note": note,
            }
        )
    return feedback


def _show(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """What the interface shows: the set of sentences to be translated, or
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
        shown["sources"] = [item["source"] for item in state["sets"][len(checked)]]
    return shown


def start(context: dict[str, Any], model: Model) -> Step:
    state: dict[str, Any] = {"sets": [], "checked": [], "reviewing": False}
    made = make_set(context, state, model)
    return Step(state=state, show=_show(context, state), made=made)


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    """Judges the translations of the set on show, as `{"answers": [...]}`;
    makes the next set, as `{"prepare": true}`; or goes on to it, as
    `{"next": true}`. A set with nothing written is not judged."""
    message = message if isinstance(message, dict) else {}
    checked = state["checked"]
    more = len(checked) < context["instances"]
    if message.get("prepare") and state["reviewing"] and more:
        made = make_set(context, state, model)
        return Step(state=state, show=_show(context, state), made=made)
    if message.get("next") and state["reviewing"] and more:
        made = make_set(context, state, model)
        state["reviewing"] = False
        return Step(state=state, show=_show(context, state), made=made)
    if isinstance(message.get("answers"), list) and not state["reviewing"]:
        items = state["sets"][len(checked)]
        answers = [
            " ".join(answer.split())[:MAX_ANSWER_LENGTH]
            if isinstance(answer, str)
            else ""
            for answer in [*message["answers"], *[""] * len(items)][: len(items)]
        ]
        if any(answers):
            feedback = judge(context, items, answers, model)
            graded = grade_of(
                [
                    grade(
                        each["result"],
                        each["answer"],
                        each["correction"],
                        each["note"],
                        f"Translate from {context['into']}: {item['source']}",
                    )
                    for item, each in zip(items, feedback)
                ]
            )
            checked.append({"feedback": feedback, "result": graded["result"]})
            state["reviewing"] = True
            said = written(
                [answer for answer in answers if answer],
                [
                    shown
                    for each in feedback
                    for shown in dict.fromkeys([each["correction"], each["reference"]])
                    if shown
                ],
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
