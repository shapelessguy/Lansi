# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Tasks of writing, made by a model, as the option `kind` says:

    message     a short message to a friend, addressed informally
    email       an email addressed formally, to a teacher, an office or a
                landlord
    opinion     an opinion on a question, as posted in a forum
    form        a form to fill in with what a short text says

The first three are a situation with the points to write about, about as
many words long as the option `words` says, and what is written is rated by
a model by the `CRITERIA` of the kit, as the examiners of an exam rate it,
with a correction and a note. A form is a text and the fields to fill in
from it, each checked against what the text says.

An instance is a task, graded once. The tasks are made one at a time, as
the stories are. The score of writing is the mean of those of the tasks,
the ratings of each made into a share of the most, and the score of each
criterion that of its ratings.

Each task is an instance, reported as made in the step it is made in; when
the exercise is done again, the tasks it made are taken in order from
`replay` in place of being made.
"""

from __future__ import annotations

import json
from typing import Any

from kit import (
    RESULTS,
    Model,
    ModelError,
    Step,
    ask_json,
    criteria_scores,
    describe_criteria,
    describe_exam,
    describe_guidance,
    describe_lesson,
    describe_level,
    describe_topics,
    describe_words,
    grade,
    grade_of,
    letters_of,
    level_of,
    loose,
    option,
    prompts_beside,
    read_ratings,
    result_of_ratings,
    score_of,
    serve,
    written,
)

KINDS = ("message", "email", "opinion", "form")
# what is rated of what is written
RATED = ["task", "coherence", "vocabulary", "structures"]
WORDS = 40
# how many fields a form has
FIELDS = 5
# more than anyone writes for one task
MAX_TEXT_LENGTH = 4000
MAX_FIELD_LENGTH = 200

# what the exercise tells the models, by name
PROMPTS = prompts_beside(__file__)


def kind_of(context: dict[str, Any]) -> str:
    kind = option(context, "kind", KINDS[0])
    return kind if kind in KINDS else KINDS[0]


def words_of(context: dict[str, Any]) -> int:
    return int(option(context, "words", WORDS))


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def read_task(reply: Any, kind: str) -> dict[str, Any]:
    """The task the model made. Raises ModelError if it is not whole."""
    reply = reply if isinstance(reply, dict) else {}
    if kind == "form":
        text = _text(reply.get("text"))
        listed = reply.get("fields")
        fields = [
            {"label": _text(each["label"]), "answer": _text(each.get("answer"))}
            for each in (listed if isinstance(listed, list) else [])
            if isinstance(each, dict)
            and _text(each.get("label"))
            and _text(each.get("answer"))
        ]
        if not text or not fields:
            raise ModelError("the model made no form to fill in")
        return {"kind": kind, "text": text, "fields": fields[:FIELDS]}
    situation = _text(reply.get("situation"))
    listed = reply.get("points")
    points = [_text(each) for each in (listed if isinstance(listed, list) else [])]
    points = [each for each in points if each]
    if not situation or not points:
        raise ModelError("the model made no task to write")
    return {"kind": kind, "situation": situation, "points": points}


def describe_made(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return ""
    listed = "\n".join(
        f"- {each.get('situation') or each.get('text', '')[:80]}" for each in tasks
    )
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
    kind = kind_of(context)
    exam = context.get("exam")
    values = {
        "language": context["language"],
        "level": describe_level(context),
        "topics": describe_topics(context),
        "guidance": describe_guidance(context, len(tasks) + 1),
        "exam": describe_exam(context),
        "made": describe_made(tasks),
    }
    if kind == "form":
        prompt = PROMPTS("making_form", **values, count=FIELDS)
    else:
        prompt = PROMPTS(
            "making",
            **values,
            kind=PROMPTS(f"tasks.{kind}"),
            lesson="" if exam else describe_lesson(context),
            words=describe_words(context),
            count=words_of(context),
        )
    tasks.append(
        read_task(ask_json(model, [{"role": "user", "content": prompt}]), kind)
    )
    return [json.loads(json.dumps(tasks[-1]))]


def rate(
    context: dict[str, Any], task: dict[str, Any], text: str, model: Model
) -> dict[str, Any]:
    """How what the learner wrote for a task is rated, with its correction
    and a note. Raises ModelError."""
    prompt = PROMPTS(
        "rating",
        language=context["language"],
        level=level_of(context),
        situation=task["situation"],
        points="\n".join(f"- {point}" for point in task["points"]),
        count=words_of(context),
        written=len(text.split()),
        text=text,
        criteria=describe_criteria(RATED),
        into=context["into"],
        shape=", ".join(f'"{name}": 0' for name in RATED),
    )
    reply = ask_json(model, [{"role": "user", "content": prompt}])
    if not isinstance(reply, dict):
        raise ModelError("the model gave no rating")
    ratings = read_ratings(reply.get("ratings"), RATED)
    return {
        "result": result_of_ratings(ratings),
        "ratings": ratings,
        "answer": text,
        "correction": _text(reply.get("correction")),
        "note": _text(reply.get("note")),
    }


def check_form(
    context: dict[str, Any], task: dict[str, Any], answers: list[str], model: Model
) -> list[dict[str, str]]:
    """How each field of a form was filled in: one that says what the text
    gives, as it is, is right, one left empty wrong, and the others are
    judged by the model. Raises ModelError."""
    fields = task["fields"]
    verdicts: dict[int, tuple[str, str]] = {}
    for number, (field, answer) in enumerate(zip(fields, answers)):
        if not answer:
            verdicts[number] = ("wrong", "")
        elif loose(answer, letters_of(context)) == loose(
            field["answer"], letters_of(context)
        ):
            verdicts[number] = ("right", "")
    asked = [number for number in range(len(fields)) if number not in verdicts]
    if asked:
        listed = "\n".join(
            PROMPTS(
                "field",
                number=place,
                label=fields[number]["label"],
                answer=fields[number]["answer"],
                given=answers[number],
            )
            for place, number in enumerate(asked, 1)
        )
        prompt = PROMPTS(
            "checking_form",
            language=context["language"],
            text=task["text"],
            fields=listed,
            into=context["into"],
        )
        reply = ask_json(model, [{"role": "user", "content": prompt}])
        found = reply.get("verdicts") if isinstance(reply, dict) else None
        if not isinstance(found, list) or len(found) != len(asked):
            raise ModelError(f"the model did not judge each of the {len(asked)} fields")
        for number, verdict in zip(asked, found):
            result = verdict.get("result") if isinstance(verdict, dict) else None
            if result not in RESULTS:
                raise ModelError("the model gave no judgement")
            verdicts[number] = (result, _text(verdict.get("note")))
    return [
        {
            "label": field["label"],
            "answer": answer,
            "reference": field["answer"],
            "result": verdicts[number][0],
            "note": verdicts[number][1],
        }
        for number, (field, answer) in enumerate(zip(fields, answers))
    ]


def _show(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """What the interface shows: the task to be done, or how the last went,
    with whether there is another and whether it was made already."""
    done = state["done"]
    shown: dict[str, Any] = {
        "at": len(done),
        "total": context["instances"],
        "words": words_of(context),
        # in an exam, what is answered goes on to the next at once
        "exam": bool(context.get("exam")),
    }
    reviewing = state["reviewing"]
    task = state["tasks"][len(done) - 1 if reviewing else len(done)]
    if task["kind"] == "form":
        shown["task"] = {
            "kind": "form",
            "text": task["text"],
            "fields": [field["label"] for field in task["fields"]],
        }
    else:
        shown["task"] = {
            "kind": task["kind"],
            "situation": task["situation"],
            "points": task["points"],
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
    """The task on show, if it was not told before as written."""
    at = len(state["done"])
    if state["reviewing"] or state["told"] > at:
        return []
    state["told"] = at + 1
    task = state["tasks"][at]
    if task["kind"] == "form":
        return [task["text"]]
    return [task["situation"], *task["points"]]


def start(context: dict[str, Any], model: Model) -> Step:
    state: dict[str, Any] = {"tasks": [], "done": [], "reviewing": False, "told": 0}
    made = make_task(context, state, model)
    return Step(
        state=state,
        show=_show(context, state),
        written=written([], _told(state)),
        made=made,
    )


def _answered(
    context: dict[str, Any],
    state: dict[str, Any],
    message: dict[str, Any],
    model: Model,
) -> Step | None:
    """Rates what was written for the task on show, or checks the form;
    None if nothing was written."""
    task = state["tasks"][len(state["done"])]
    if task["kind"] == "form":
        given = message.get("fields")
        if not isinstance(given, list):
            return None
        count = len(task["fields"])
        answers = [
            " ".join(each.split())[:MAX_FIELD_LENGTH] if isinstance(each, str) else ""
            for each in [*given, *[""] * count][:count]
        ]
        if not any(answers):
            return None
        fields = check_form(context, task, answers, model)
        one = grade_of(
            [
                grade(
                    each["result"],
                    each["answer"],
                    "" if each["result"] == "right" else each["reference"],
                    each["note"],
                    f"Fill in the form from the text: {each['label']}",
                )
                for each in fields
            ]
        )
        done = {"kind": "form", "result": one["result"], "fields": fields}
        said = written([answer for answer in answers if answer], [])
    else:
        text = message.get("text")
        text = text.strip()[:MAX_TEXT_LENGTH] if isinstance(text, str) else ""
        if not text:
            return None
        rated = rate(context, task, text, model)
        points = "; ".join(task["points"])
        one = grade(
            rated["result"],
            text,
            rated["correction"],
            rated["note"],
            f"Write about {words_of(context)} words. {task['situation']} Points: {points}",
        )
        done = {"kind": task["kind"], **rated}
        said = written([text], [rated["correction"]] if rated["correction"] else [])
    state["done"].append(done)
    state["reviewing"] = True
    return Step(state=state, show=_show(context, state), graded=[one], written=said)


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
    """Rates what was written for the task on show, as `{"text": "..."}`, or
    checks a form, as `{"fields": [...]}`; makes the next task, as
    `{"prepare": true}`; or goes on to it, as `{"next": true}`."""
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
    if not state["reviewing"]:
        answered = _answered(context, state, message, model)
        if answered:
            return _onward(context, state, model, answered)
    return Step(state=state, show=_show(context, state))


def scores_of(done: list[dict[str, Any]]) -> dict[str, float] | None:
    """The scores of the tasks done: that of writing, the mean of those of
    the tasks, and that of each criterion rated."""
    rated = [each["ratings"] for each in done if each.get("ratings")]
    tasks: list[float] = []
    for each in done:
        if each.get("ratings"):
            tasks.append(
                100 * sum(each["ratings"].values()) / (4 * len(each["ratings"]))
            )
        elif (
            form := score_of([field["result"] for field in each["fields"]])
        ) is not None:
            tasks.append(form)
    if not tasks:
        return None
    scores = {
        name: score for name, score in criteria_scores(rated).items() if name != "all"
    }
    return {"writing": round(sum(tasks) / len(tasks), 1), **scores}


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    return Step(
        state=state,
        results={
            "tasks": [
                {"task": task, **answered}
                for task, answered in zip(state["tasks"], state["done"])
            ],
            "total": context["instances"],
        },
        scores=scores_of(state["done"]),
    )


if __name__ == "__main__":
    serve(start, act, finish)
