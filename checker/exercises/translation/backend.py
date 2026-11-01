# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Sentences to translate into the language being learned, made by a model
so that translating them takes the points of the lesson, and judged by a
model against those points; or, the other way, from the language learned
into the one the learner reads, judged by whether they understood them.

Each sentence is made with a good translation, which the learner may look
at before they check theirs; it is no answer they must give, and the model
judges what they wrote against the sentence alone. That they looked is
told in the task of the grade. Which way they translate is the option
`direction` at first, and the learner may turn it, as `{"reverse": ...}`,
for the set they are on and those after it: each sentence is made with
both sides, so the same set may be done either way.

An instance is a set of sentences, as many as the option `sentences` says,
shown together, judged in one request to the model and graded once. The sets are made one at a time: the
first when the exercise starts, and each other once the one before was
judged, when the interface asks for it to be `prepare`d while the learner
reads the judgement, or else when it goes on to the `next`.

Once a set is judged, the translations are reported as written by the
learner, and the corrections and the other ways the learner is shown as
written by the model; the other way, what the learner wrote and the
corrections are in the language they read, and only the sentences they
translated are reported, as written by the model.

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


def reversed_of(context: dict[str, Any]) -> bool:
    """Whether the learner translates from the language learned at first,
    as they chose."""
    return bool(option(context, "direction", "into") == "from")


def sides(item: dict[str, str], reverse: bool) -> tuple[str, str]:
    """What the learner translates of a sentence, and a good translation of
    it, the way they translate."""
    if reverse:
        return item["reference"], item["source"]
    return item["source"], item["reference"]


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
    reverse: bool = False,
) -> list[dict[str, str]]:
    """What the learner is told of each translation of a set, which is
    graded as it is: those that were left empty are wrong, and the others
    are judged by the model, together, the way they were translated. The
    `source` of each is what the learner translated, and its `reference`
    a good translation of it. Raises ModelError."""
    written = [number for number, answer in enumerate(answers) if answer]
    sentences = "\n\n".join(
        PROMPTS(
            "sentence_back" if reverse else "sentence",
            number=order,
            language=context["language"],
            into=context["into"],
            source=sides(items[number], reverse)[0],
            reference=sides(items[number], reverse)[1],
            given=answers[number],
        )
        for order, number in enumerate(written, start=1)
    )
    verdicts: dict[int, tuple[str, str, str]] = {}
    if written:
        prompt = PROMPTS(
            "judging_back" if reverse else "judging",
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
        source, reference = sides(item, reverse)
        result, correction, note = verdicts.get(number, ("wrong", reference, ""))
        feedback.append(
            {
                "result": result,
                "source": source,
                "answer": answers[number],
                "correction": correction,
                "reference": reference,
                "note": note,
            }
        )
    return feedback


def _show(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """What the interface shows: the set of sentences to be translated, or
    how the last set went, with whether there is another and whether it
    was made already. The sentences are shown with their good translations,
    which the interface keeps hidden until the learner asks for them, and
    with the languages they are translated from and into."""
    checked = state["checked"]
    reverse = state.get("reversed", False)
    shown: dict[str, Any] = {
        "at": len(checked),
        "total": context["instances"],
        "reversed": reverse,
        "from": context["language"] if reverse else context["into"],
        "to": context["into"] if reverse else context["language"],
    }
    if state["reviewing"]:
        shown["feedback"] = checked[-1]["feedback"]
        shown["result"] = checked[-1]["result"]
        shown["more"] = len(checked) < context["instances"]
        shown["prepared"] = len(state["sets"]) > len(checked)
    else:
        items = state["sets"][len(checked)]
        shown["sources"] = [sides(item, reverse)[0] for item in items]
        shown["references"] = [sides(item, reverse)[1] for item in items]
    return shown


def start(context: dict[str, Any], model: Model) -> Step:
    state: dict[str, Any] = {
        "sets": [],
        "checked": [],
        "reviewing": False,
        "reversed": reversed_of(context),
    }
    made = make_set(context, state, model)
    return Step(state=state, show=_show(context, state), made=made)


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    """Judges the translations of the set on show, as `{"answers": [...],
    "looked": [...]}`, the second saying of each whether the learner looked
    at its good translation; makes the next set, as `{"prepare": true}`;
    goes on to it, as `{"next": true}`; or turns the way the learner
    translates, as `{"reverse": true}` or false, while they have not
    checked the set on show. A set with nothing written is not judged."""
    message = message if isinstance(message, dict) else {}
    checked = state["checked"]
    more = len(checked) < context["instances"]
    if isinstance(message.get("reverse"), bool) and not state["reviewing"]:
        state["reversed"] = message["reverse"]
        return Step(state=state, show=_show(context, state))
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
        looked = message.get("looked")
        looked = looked if isinstance(looked, list) else []
        if any(answers):
            reverse = state.get("reversed", False)
            feedback = judge(context, items, answers, model, reverse)
            graded = grade_of(
                [
                    grade(
                        each["result"],
                        each["answer"],
                        each["correction"],
                        each["note"],
                        task_of(context, each["source"], reverse, looked, number),
                    )
                    for number, each in enumerate(feedback)
                ]
            )
            checked.append(
                {"feedback": feedback, "result": graded["result"], "reversed": reverse}
            )
            state["reviewing"] = True
            if reverse:
                # what the learner wrote, and what corrects it, is in the
                # language they read, and only what they translated is not
                said = written([], [each["source"] for each in feedback])
            else:
                said = written(
                    [answer for answer in answers if answer],
                    [
                        shown
                        for each in feedback
                        for shown in dict.fromkeys(
                            [each["correction"], each["reference"]]
                        )
                        if shown
                    ],
                )
            return Step(
                state=state, show=_show(context, state), graded=[graded], written=said
            )
    return Step(state=state, show=_show(context, state))


def task_of(
    context: dict[str, Any], source: str, reverse: bool, looked: list[Any], number: int
) -> str:
    """What the learner was given to translate, the way they did, and
    whether they looked at its good translation first."""
    language = context["language"] if reverse else context["into"]
    task = f"Translate from {language}: {source}"
    if number < len(looked) and looked[number] is True:
        task += " (looked at a good translation first)"
    return task


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    done = [
        {"items": made, **checked}
        for made, checked in zip(state["sets"], state["checked"])
    ]
    # each sentence counts, of every set that was checked: translated into
    # the language learned for its grammar, and from it for reading it
    scores: dict[str, float] = {}
    for name, reverse in (("structures", False), ("reading", True)):
        score = score_of(
            [
                each["result"]
                for checked in state["checked"]
                if checked.get("reversed", False) == reverse
                for each in checked["feedback"]
            ]
        )
        if score is not None:
            scores[name] = score
    return Step(
        state=state,
        results={"sets": done, "total": context["instances"]},
        scores=scores or None,
    )


if __name__ == "__main__":
    serve(start, act, finish)
