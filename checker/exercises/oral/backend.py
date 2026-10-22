# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tasks of speaking, made by a model, as the option `kind` says:

    introduce   introduce yourself, to the points of a card
    cards       ask a partner with word cards, and answer what they ask
    requests    ask a partner for things, and react to what they ask
    talk        talk about your own life, to the points of a card
    plan        plan something with a partner, turn by turn

Until speech is taken in, what the learner says is typed, as they would
say it. A task is a card, or the turns of a partner, with as many turns to
answer as the option `prompts` says, but one for those that are talked
through at once. What the learner says to all of them is rated together
by a model, by the `CRITERIA` of the kit, as the examiners of an exam rate
speaking, with a correction of each turn; pronunciation is not rated, as
nothing is heard.

An instance is a task, graded once. The tasks are made one at a time, as
the stories are. The score of speaking is the mean of those of the tasks,
and the score of each criterion that of its ratings.

Each task is an instance, reported as made in the step it is made in; when
the exercise is done again, the tasks it made are taken in order from
`replay` in place of being made.
"""

from __future__ import annotations

import json
from typing import Any

from kit import (
    Model,
    ModelError,
    Step,
    ask_json,
    criteria_scores,
    describe_criteria,
    describe_exam,
    describe_guidance,
    describe_level,
    describe_topics,
    describe_words,
    grade,
    grade_of,
    level_of,
    option,
    prompts_beside,
    read_ratings,
    result_of_ratings,
    serve,
    written,
)

KINDS = ("introduce", "cards", "requests", "talk", "plan")
# how many turns a task has, unless it is talked through at once
TURNS = 4
# those talked through at once, to a card, which have one turn
WHOLE = ("introduce", "talk")
# what is rated of each kind of task: a turn of a few words is not one text
RATED = {
    "introduce": ["task", "coherence", "vocabulary", "structures"],
    "cards": ["task", "vocabulary", "structures"],
    "requests": ["task", "vocabulary", "structures"],
    "talk": ["task", "coherence", "vocabulary", "structures"],
    "plan": ["task", "coherence", "vocabulary", "structures"],
}
MAX_ANSWER_LENGTH = 2000

# what the exercise tells the models, by name
PROMPTS = prompts_beside(__file__)


def kind_of(context: dict[str, Any]) -> str:
    kind = option(context, "kind", KINDS[0])
    return kind if kind in KINDS else KINDS[0]


def prompts_of(context: dict[str, Any]) -> int:
    """How many turns a task has."""
    if kind_of(context) in WHOLE:
        return 1
    return int(option(context, "prompts", TURNS))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def read_task(reply: Any, count: int) -> dict[str, Any]:
    """The task the model made, with no more than `count` turns. Raises
    ModelError if it has none."""
    reply = reply if isinstance(reply, dict) else {}
    listed = reply.get("prompts")
    prompts = [_text(each) for each in (listed if isinstance(listed, list) else [])]
    prompts = [each for each in prompts if each]
    if not prompts:
        raise ModelError("the model made no task to speak to")
    return {"card": _text(reply.get("card")), "prompts": prompts[:count]}


def describe_made(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return ""
    listed = "\n".join(f"- {each['card'] or each['prompts'][0]}" for each in tasks)
    return f"\n{PROMPTS('made', listed=listed)}\n"


def make_task(
    context: dict[str, Any], state: dict[str, Any], model: Model
) -> list[dict[str, Any]]:
    """Has the model make the next task, unless it was made already or every
    task was; or takes it from those done again. Returns what was made, as
    the instances to report."""
    tasks = state["tasks"]
    if len(tasks) > len(state["done"]) or len(tasks) >= context["instances"]:
        return []
    replay = context.get("replay")
    if replay:
        tasks.append(json.loads(json.dumps(replay[len(tasks)])))
        return []
    prompt = PROMPTS(
        "making",
        language=context["language"],
        task=PROMPTS(f"tasks.{kind_of(context)}"),
        level=describe_level(context),
        topics=describe_topics(context),
        words=describe_words(context),
        guidance=describe_guidance(context),
        exam=describe_exam(context),
        made=describe_made(tasks),
        count=prompts_of(context),
    )
    reply = ask_json(model, [{"role": "user", "content": prompt}])
    tasks.append(read_task(reply, prompts_of(context)))
    return [json.loads(json.dumps(tasks[-1]))]


def rate(
    context: dict[str, Any], task: dict[str, Any], answers: list[str], model: Model
) -> dict[str, Any]:
    """How what the learner said to a task is rated, with the correction of
    each turn and a note. Raises ModelError."""
    names = RATED[kind_of(context)]
    turns = "\n\n".join(
        PROMPTS("turn", number=number, prompt=prompt, answer=answer or "(nothing)")
        for number, (prompt, answer) in enumerate(zip(task["prompts"], answers), 1)
    )
    prompt = PROMPTS(
        "rating",
        language=context["language"],
        level=level_of(context),
        card=task["card"] or "(none)",
        turns=turns,
        criteria=describe_criteria(names),
        into=context["into"],
        shape=", ".join(f'"{name}": 0' for name in names),
    )
    reply = ask_json(model, [{"role": "user", "content": prompt}])
    if not isinstance(reply, dict):
        raise ModelError("the model gave no rating")
    ratings = read_ratings(reply.get("ratings"), names)
    listed = reply.get("corrections")
    corrections = [_text(each) for each in (listed if isinstance(listed, list) else [])]
    corrections = [*corrections, *[""] * len(answers)][: len(answers)]
    return {
        "result": result_of_ratings(ratings),
        "ratings": ratings,
        "turns": [
            {"prompt": prompt, "answer": answer, "correction": correction}
            for prompt, answer, correction in zip(task["prompts"], answers, corrections)
        ],
        "note": _text(reply.get("note")),
    }


def _show(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    done = state["done"]
    reviewing = state["reviewing"]
    task = state["tasks"][len(done) - 1 if reviewing else len(done)]
    shown: dict[str, Any] = {
        "at": len(done),
        "total": context["instances"],
        "kind": kind_of(context),
        "task": task,
        # in an exam, what is answered goes on to the next at once
        "exam": bool(context.get("exam")),
    }
    if reviewing:
        # in an exam, how it went is told only once the evaluation is over
        if context.get("exam"):
            shown["withheld"] = True
        else:
            shown["feedback"] = done[-1]
        shown["more"] = len(done) < context["instances"]
        shown["prepared"] = len(state["tasks"]) > len(done)
    return shown


def _told(state: dict[str, Any]) -> list[str]:
    at = len(state["done"])
    if state["reviewing"] or state["told"] > at:
        return []
    state["told"] = at + 1
    task = state["tasks"][at]
    return [part for part in (task["card"], *task["prompts"]) if part]


def start(context: dict[str, Any], model: Model) -> Step:
    state: dict[str, Any] = {"tasks": [], "done": [], "reviewing": False, "told": 0}
    made = make_task(context, state, model)
    return Step(
        state=state,
        show=_show(context, state),
        written=written([], _told(state)),
        made=made,
    )


def _onward(
    context: dict[str, Any], state: dict[str, Any], model: Model, step: Step
) -> Step:
    """In an exam, what was just answered goes on at once to the next task,
    as an exam tells nothing of how it went: the step answered, with the
    next task made and shown. Otherwise, and after the last, the step as it
    is."""
    if not context.get("exam") or len(state["done"]) >= context["instances"]:
        return step
    made = make_task(context, state, model)
    state["reviewing"] = False
    said = step.written or written()
    return Step(
        state=state,
        show=_show(context, state),
        graded=step.graded,
        written=written(said.get("user"), [*said.get("assistant", []), *_told(state)]),
        made=made,
    )


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    """Rates what the learner said to the turns of the task on show, as
    `{"answers": [...]}`; makes the next task, as `{"prepare": true}`; or
    goes on to it, as `{"next": true}`."""
    message = message if isinstance(message, dict) else {}
    more = len(state["done"]) < context["instances"]
    if message.get("prepare") and state["reviewing"] and more:
        made = make_task(context, state, model)
        return Step(state=state, show=_show(context, state), made=made)
    if message.get("next") and state["reviewing"] and more:
        made = make_task(context, state, model)
        state["reviewing"] = False
        return Step(
            state=state,
            show=_show(context, state),
            written=written([], _told(state)),
            made=made,
        )
    if isinstance(message.get("answers"), list) and not state["reviewing"]:
        task = state["tasks"][len(state["done"])]
        count = len(task["prompts"])
        answers = [
            " ".join(each.split())[:MAX_ANSWER_LENGTH] if isinstance(each, str) else ""
            for each in [*message["answers"], *[""] * count][:count]
        ]
        if any(answers):
            rated = rate(context, task, answers, model)
            one = grade_of(
                [
                    grade(
                        "right"
                        if not turn["correction"] and turn["answer"]
                        else "wrong"
                        if not turn["answer"]
                        else "partial",
                        turn["answer"],
                        turn["correction"],
                        "",
                        f"Say, as in a speaking exam: {turn['prompt']}",
                    )
                    for turn in rated["turns"]
                ]
            )
            # the task is rated as a whole, as an examiner rates it
            one["result"] = rated["result"]
            one["note"] = rated["note"]
            state["done"].append(rated)
            state["reviewing"] = True
            said = written(
                [answer for answer in answers if answer],
                [turn["correction"] for turn in rated["turns"] if turn["correction"]],
            )
            return _onward(
                context,
                state,
                model,
                Step(
                    state=state, show=_show(context, state), graded=[one], written=said
                ),
            )
    return Step(state=state, show=_show(context, state))


def scores_of(done: list[dict[str, Any]]) -> dict[str, float] | None:
    """The scores of the tasks done: that of speaking, and that of each
    criterion rated."""
    rated = [each["ratings"] for each in done if each.get("ratings")]
    if not rated:
        return None
    tasks = [100 * sum(each.values()) / (4 * len(each)) for each in rated]
    scores = {
        name: score for name, score in criteria_scores(rated).items() if name != "all"
    }
    return {"speaking": round(sum(tasks) / len(tasks), 1), **scores}


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    return Step(
        state=state,
        results={
            "tasks": [
                {"task": task, **answered}
                for task, answered in zip(state["tasks"], state["done"])
            ],
            "kind": kind_of(context),
            "total": context["instances"],
        },
        scores=scores_of(state["done"]),
    )


if __name__ == "__main__":
    serve(start, act, finish)
