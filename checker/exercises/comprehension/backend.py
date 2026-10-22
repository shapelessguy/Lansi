# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Texts written by a model to be understood, read or listened to as the
option `by` says, with questions on each that are answered by choosing, as
the option `answers` says:

    choice      one of three answers, a, b or c
    truefalse   Richtig or Falsch, of a statement
    yesno       Ja or Nein, of a statement
    match       which of a list, such as adverts a to f, goes with each
                question, or x for none

An instance is a text, with as many questions as the option `questions`
says, graded once. The answers are known when the text is written, so they
are checked here, without asking a model. A text that is listened to is read
aloud by the app, as often as the option `plays` lets, and is shown only
once it was answered; what goes with it to be read, such as the list to
match, is shown all along.

The texts are made one at a time, as the stories are: the first when the
exercise starts, and each other once the one before was answered, when the
interface asks for it to be `prepare`d, or else when it goes on to the
`next`. The score is the share of the questions answered right, as reading
or as listening.

Each text, with its questions, is an instance, reported as made in the step
it is written in; when the exercise is done again, the texts it wrote are
taken in order from `replay` in place of being written.
"""

from __future__ import annotations

import json
from typing import Any

from kit import (
    Model,
    ModelError,
    Step,
    ask_json,
    describe_exam,
    describe_guidance,
    describe_lesson,
    describe_level,
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

QUESTIONS = 3
# the answers of statements, which are the same for every question
FIXED = {"truefalse": ["Richtig", "Falsch"], "yesno": ["Ja", "Nein"]}
ANSWERS = ("choice", "truefalse", "yesno", "match")
# about how many words a text is at each level, and at a level not known
LENGTHS = {"A1": 60, "A2": 110, "B1": 200, "B2": 300, "C1": 400, "C2": 450}
DEFAULT_LENGTH = 150

# what the exercise tells the models, by name
PROMPTS = prompts_beside(__file__)


def by_of(context: dict[str, Any]) -> str:
    """Whether the texts are read or listened to."""
    by = option(context, "by", "reading")
    return by if by in ("reading", "listening") else "reading"


def answers_of(context: dict[str, Any]) -> str:
    """How the questions are answered."""
    answers = option(context, "answers", ANSWERS[0])
    return answers if answers in ANSWERS else ANSWERS[0]


def questions_of(context: dict[str, Any]) -> int:
    return int(option(context, "questions", QUESTIONS))


def plays_of(context: dict[str, Any]) -> int:
    """How often a text may be heard, 0 for as often as the learner likes."""
    try:
        return max(0, int(option(context, "plays", "2")))
    except ValueError:
        return 2


def kind_of(context: dict[str, Any]) -> str:
    """The kind of text that is to be written, as a model is told."""
    kind = option(context, "text", "any")
    texts = PROMPTS.table("texts")
    if kind in texts:
        return str(texts[kind])
    return PROMPTS(f"any_text.{by_of(context)}")


def length_of(context: dict[str, Any]) -> int:
    return LENGTHS.get(level_of(context).strip().upper(), DEFAULT_LENGTH)


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def read_text(reply: Any, answers: str, count: int) -> dict[str, Any]:
    """The text the model wrote, with no more than `count` questions, each
    with its options and the place of the right one. Raises ModelError if
    there is no text, or no question that can be answered."""
    reply = reply if isinstance(reply, dict) else {}
    text = _text(reply.get("text"))
    if not text:
        raise ModelError("the model wrote no text")
    questions = []
    listed = reply.get("questions")
    for each in listed if isinstance(listed, list) else []:
        if not isinstance(each, dict) or not _text(each.get("prompt")):
            continue
        options = FIXED.get(answers) or [
            _text(choice) for choice in each.get("options") or [] if _text(choice)
        ]
        answer = each.get("answer")
        if (
            len(options) < 2
            or isinstance(answer, bool)
            or not isinstance(answer, int)
            or not 0 <= answer < len(options)
        ):
            continue
        questions.append(
            {"prompt": _text(each["prompt"]), "options": options, "answer": answer}
        )
    if not questions:
        raise ModelError("the model asked no question that can be answered")
    return {
        "title": _text(reply.get("title")),
        "shown": _text(reply.get("shown")),
        "text": text,
        "questions": questions[:count],
    }


def describe_made(texts: list[dict[str, Any]]) -> str:
    """The texts made before in the exercise, as a model is told them so as
    to write another; nothing if there are none."""
    if not texts:
        return ""
    listed = "\n".join(f"- {each['title'] or each['text'][:80]}" for each in texts)
    return f"\n{PROMPTS('made', listed=listed)}\n"


def make_text(
    context: dict[str, Any], state: dict[str, Any], model: Model
) -> list[dict[str, Any]]:
    """Has the model write the next text, unless it was written already or
    every text was; or takes it from those done again. Returns what was
    written, as the instances to report."""
    texts = state["texts"]
    if len(texts) > len(state["done"]) or len(texts) >= context["instances"]:
        return []
    replay = context.get("replay")
    if replay:
        texts.append(json.loads(json.dumps(replay[len(texts)])))
        return []
    answers = answers_of(context)
    heard = by_of(context) == "listening"
    prompt = PROMPTS(
        "making",
        language=context["language"],
        by=PROMPTS(f"by.{by_of(context)}"),
        kind=kind_of(context),
        length=length_of(context),
        count=questions_of(context),
        level=describe_level(context),
        # in an exam, the level is what is examined, not the rules of a lesson
        lesson="" if context.get("exam") else describe_lesson(context),
        topics=describe_topics(context),
        words=describe_words(context),
        guidance=describe_guidance(context),
        exam=describe_exam(context),
        made=describe_made(texts),
        answers=PROMPTS(f"answering.{answers}"),
        heard=PROMPTS("heard") if heard else "",
    )
    reply = ask_json(model, [{"role": "user", "content": prompt}])
    texts.append(read_text(reply, answers, questions_of(context)))
    return [json.loads(json.dumps(texts[-1]))]


def check(text: dict[str, Any], chosen: list[Any]) -> list[dict[str, Any]]:
    """How each answer chosen went, by the place of the option chosen, or
    anything else for none."""
    feedback = []
    for number, question in enumerate(text["questions"]):
        given = chosen[number] if number < len(chosen) else None
        picked = (
            given
            if isinstance(given, int)
            and not isinstance(given, bool)
            and 0 <= given < len(question["options"])
            else None
        )
        feedback.append(
            {
                "prompt": question["prompt"],
                "options": question["options"],
                "chosen": picked,
                "answer": question["answer"],
                "result": "right" if picked == question["answer"] else "wrong",
            }
        )
    return feedback


def _show(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """What the interface shows: the text to be understood with its
    questions, or how the last went, with whether there is another and
    whether it was written already. A text that is heard is sent all the
    same, to be read aloud, and is shown only once it was answered."""
    done = state["done"]
    shown: dict[str, Any] = {
        "at": len(done),
        "total": context["instances"],
        "by": by_of(context),
        "plays": plays_of(context),
        "minutes": context.get("minutes") or 0,
        # in an exam, what is answered goes on to the next at once
        "exam": bool(context.get("exam")),
    }
    if state["reviewing"]:
        text = state["texts"][len(done) - 1]
        shown["text"] = {key: text[key] for key in ("title", "shown", "text")}
        shown["number"] = len(done) - 1
        # in an exam, how it went is told only once the evaluation is over
        if context.get("exam"):
            shown["withheld"] = True
        else:
            shown["feedback"] = done[-1]["feedback"]
        shown["more"] = len(done) < context["instances"]
        shown["prepared"] = len(state["texts"]) > len(done)
    else:
        text = state["texts"][len(done)]
        shown["text"] = {key: text[key] for key in ("title", "shown", "text")}
        shown["number"] = len(done)
        shown["questions"] = [
            {"prompt": each["prompt"], "options": each["options"]}
            for each in text["questions"]
        ]
    return shown


def _told(state: dict[str, Any]) -> list[str]:
    """The text on show, with its questions, if it was not told before as
    written; it is noted as told."""
    at = len(state["done"])
    if state["reviewing"] or state["told"] > at:
        return []
    state["told"] = at + 1
    text = state["texts"][at]
    return [part for part in (text["title"], text["text"], text["shown"]) if part] + [
        each["prompt"] for each in text["questions"]
    ]


def start(context: dict[str, Any], model: Model) -> Step:
    state: dict[str, Any] = {"texts": [], "done": [], "reviewing": False, "told": 0}
    made = make_text(context, state, model)
    return Step(
        state=state,
        show=_show(context, state),
        written=written([], _told(state)),
        made=made,
    )


def _onward(
    context: dict[str, Any], state: dict[str, Any], model: Model, step: Step
) -> Step:
    """In an exam, what was just answered goes on at once to the next text,
    as an exam tells nothing of how it went: the step answered, with the
    next text made and shown. Otherwise, and after the last, the step as it
    is."""
    if not context.get("exam") or len(state["done"]) >= context["instances"]:
        return step
    made = make_text(context, state, model)
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
    """Checks the answers chosen for the text on show, as `{"answers":
    [...]}`, each the place of the option chosen, or null for none; writes
    the next text, as `{"prepare": true}`; or goes on to it, as `{"next":
    true}`."""
    message = message if isinstance(message, dict) else {}
    more = len(state["done"]) < context["instances"]
    if message.get("prepare") and state["reviewing"] and more:
        made = make_text(context, state, model)
        return Step(state=state, show=_show(context, state), made=made)
    if message.get("next") and state["reviewing"] and more:
        made = make_text(context, state, model)
        state["reviewing"] = False
        return Step(
            state=state,
            show=_show(context, state),
            written=written([], _told(state)),
            made=made,
        )
    if isinstance(message.get("answers"), list) and not state["reviewing"]:
        text = state["texts"][len(state["done"])]
        feedback = check(text, message["answers"])
        one = grade_of(
            [
                grade(
                    each["result"],
                    "" if each["chosen"] is None else each["options"][each["chosen"]],
                    each["options"][each["answer"]],
                    "",
                    f"{each['prompt']} ({' / '.join(each['options'])})",
                )
                for each in feedback
            ],
            # the questions are not understood without the text
            "\n\n".join(
                part for part in (text["title"], text["text"], text["shown"]) if part
            ),
        )
        state["done"].append({"feedback": feedback, "result": one["result"]})
        state["reviewing"] = True
        return _onward(
            context,
            state,
            model,
            Step(state=state, show=_show(context, state), graded=[one]),
        )
    return Step(state=state, show=_show(context, state))


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    score = score_of(
        [each["result"] for answered in state["done"] for each in answered["feedback"]]
    )
    skill = "listening" if by_of(context) == "listening" else "reading"
    return Step(
        state=state,
        results={
            "texts": [
                {"text": text, **answered}
                for text, answered in zip(state["texts"], state["done"])
            ],
            "by": by_of(context),
            "total": context["instances"],
        },
        scores=None if score is None else {skill: score},
    )


if __name__ == "__main__":
    serve(start, act, finish)
