# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Sentences to translate into the language being learned, made by a model
so that translating them takes the points of the lesson, and judged by a
model against those points.

An instance is a set of `SENTENCES` sentences, shown together, judged in one
request to the model and logged once. The sets are made one at a time: the
first when the exercise starts, and each other once the one before was
judged, when the interface asks for it to be `prepare`d while the learner
reads the judgement, or else when it goes on to the `next`.

Once a set is judged, the translations are reported as written by the
learner, and the corrections and the other ways the learner is shown as
written by the model.
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
    level_of,
    log,
    log_of,
    serve,
    written,
)

# how many sentences an instance is
SENTENCES = 5
# more than anyone writes for one sentence
MAX_ANSWER_LENGTH = 1000

MAKING = """\
You write translation exercises for someone learning {language}. Write \
{count} different sentences in {into} which, translated into {language}, \
need the rules below, and keep to the topics below. {level}

{lesson}
{topics}
{words}{guidance}{made}

Give each sentence with a good translation into {language}.

Reply with JSON alone: {{"items": [{{"source": "...", "reference": "..."}}]}}"""

JUDGING = """\
You check translations by someone learning {language} at level {level}. \
The lesson they practise:

{lesson}

The sentences, each in {into}, with a good translation and the learner's:

{sentences}

Judge each translation of the learner, not how close it is to the good one: \
another wording that is right is right. "right" if it is correct {language} \
and means the sentence, "partial" if it has small mistakes, "wrong" if it \
has mistakes in the rules of the lesson or does not mean the sentence. The \
correction is the learner's translation with as few changes as make it \
right, or "" if it is right. The note says in a sentence of {into} what was \
wrong, or "" if nothing was.

Reply with JSON alone, with a verdict for each sentence in turn: \
{{"verdicts": [{{"result": "...", "correction": "...", "note": "..."}}]}}"""


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


def make_set(context: dict[str, Any], state: dict[str, Any], model: Model) -> None:
    """Has the model make the next set of sentences, other than those made
    before, unless it was made already or every set was."""
    sets = state["sets"]
    if len(sets) > len(state["checked"]) or len(sets) >= context["instances"]:
        return
    prompt = MAKING.format(
        language=context["language"],
        count=SENTENCES,
        into=context["into"],
        level=describe_level(context),
        lesson=describe_lesson(context),
        topics=describe_topics(context),
        words=describe_words(context),
        guidance=describe_guidance(context),
        made=describe_made([item["source"] for made in sets for item in made]),
    )
    sets.append(read_items(ask_json(model, [{"role": "user", "content": prompt}])))


def judge(
    context: dict[str, Any],
    items: list[dict[str, str]],
    answers: list[str],
    model: Model,
) -> list[dict[str, str]]:
    """What the learner is told of each translation of a set, which is
    logged as it is: those that were left empty are wrong, and the others
    are judged by the model, together. Raises ModelError."""
    written = [number for number, answer in enumerate(answers) if answer]
    sentences = "\n\n".join(
        f"{order}. In {context['into']}: {items[number]['source']}\n"
        f"   Good: {items[number]['reference']}\n"
        f"   The learner's: {answers[number]}"
        for order, number in enumerate(written, start=1)
    )
    verdicts: dict[int, tuple[str, str, str]] = {}
    if written:
        prompt = JUDGING.format(
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
    make_set(context, state, model)
    return Step(state=state, show=_show(context, state))


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    """Judges the translations of the set on show, as `{"answers": [...]}`;
    makes the next set, as `{"prepare": true}`; or goes on to it, as
    `{"next": true}`. A set with nothing written is not judged."""
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
        answers = [
            " ".join(answer.split())[:MAX_ANSWER_LENGTH]
            if isinstance(answer, str)
            else ""
            for answer in [*message["answers"], *[""] * len(items)][: len(items)]
        ]
        if any(answers):
            feedback = judge(context, items, answers, model)
            logged = log_of(
                [
                    log(
                        each["result"], each["answer"], each["correction"], each["note"]
                    )
                    for each in feedback
                ]
            )
            checked.append({"feedback": feedback, "result": logged["result"]})
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
                state=state, show=_show(context, state), logs=[logged], written=said
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
