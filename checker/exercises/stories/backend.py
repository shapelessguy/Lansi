# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Short stories written by a model for the lesson and the topics, to read
and to listen to, and then, as the learner chose in the option `then`:

    questions   answer questions on the story, as many as the option
                `questions` says, in the language
                learned, judged together by a model
    retell      retell the story in a few sentences, judged by a model
    read        nothing more: the story is read, and nothing is graded

An instance is a story, graded once. The stories are made one at a time:
the first when the exercise starts, and each other once the one before was
answered, when the interface asks for it to be `prepare`d while the
learner reads how it went, or else when it goes on to the `next`.

A story is reported as written by the model in the step it is first shown
in, with its questions; once it is answered, what the learner wrote is
reported as written by them, and the corrections as written by the model.
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

# how many questions are asked on a story, unless the learner chose otherwise
QUESTIONS = 3
# about how many words a story is at each level, and at a level not known
LENGTHS = {"A1": 80, "A2": 120, "B1": 180, "B2": 240, "C1": 300, "C2": 350}
DEFAULT_LENGTH = 150
# how much longer than that a story is, by the option `length`
LENGTH_FACTORS = {"level": 1.0, "shorter": 0.6, "longer": 1.6}
# more than anyone writes in one answer, or in a retelling
MAX_ANSWER_LENGTH = 1000
MAX_RETELLING_LENGTH = 4000
MODES = ("questions", "retell", "read")

# what the exercise tells the models, by name
PROMPTS = prompts_beside(__file__)


def mode_of(context: dict[str, Any]) -> str:
    """What the learner does once they read a story."""
    mode = option(context, "then", MODES[0])
    return mode if mode in MODES else MODES[0]


def questions_of(context: dict[str, Any]) -> int:
    """How many questions are asked on a story."""
    return int(option(context, "questions", QUESTIONS))


def length_of(context: dict[str, Any]) -> int:
    """About how many words a story is, at the learner's level, made
    shorter or longer as they chose."""
    usual = LENGTHS.get(level_of(context).strip().upper(), DEFAULT_LENGTH)
    factor = LENGTH_FACTORS.get(option(context, "length", "level"), 1.0)
    return round(usual * factor / 10) * 10


def describe_stories(stories: list[dict[str, Any]]) -> str:
    """The stories made before in the exercise, as a model is told them so
    as to write another; nothing if there are none."""
    if not stories:
        return ""
    listed = "\n".join(f"- {story['title']}" for story in stories)
    return f"\n{PROMPTS('made', listed=listed)}\n"


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def read_story(reply: Any, mode: str, count: int = QUESTIONS) -> dict[str, Any]:
    """The story the model wrote, with its questions if they were asked
    for, no more than `count` of them. Raises ModelError if there is no
    story, or no question when there are to be some."""
    reply = reply if isinstance(reply, dict) else {}
    text = _text(reply.get("text"))
    if not text:
        raise ModelError("the model wrote no story")
    story: dict[str, Any] = {"title": _text(reply.get("title")), "text": text}
    if mode == "questions":
        listed = reply.get("questions")
        questions = [
            {"question": _text(each["question"]), "answer": _text(each.get("answer"))}
            for each in (listed if isinstance(listed, list) else [])
            if isinstance(each, dict) and _text(each.get("question"))
        ]
        if not questions:
            raise ModelError("the model asked no question on the story")
        story["questions"] = questions[:count]
    return story


def read_verdict(reply: Any) -> tuple[str, str, str]:
    """The result, correction and note of a judgement. Raises ModelError."""
    if not isinstance(reply, dict) or reply.get("result") not in RESULTS:
        raise ModelError("the model gave no judgement")
    return reply["result"], _text(reply.get("correction")), _text(reply.get("note"))


def read_verdicts(reply: Any, count: int) -> list[tuple[str, str, str]]:
    """The judgement of each of `count` answers. Raises ModelError if there
    is not one for each."""
    listed = reply.get("verdicts") if isinstance(reply, dict) else None
    if not isinstance(listed, list) or len(listed) != count:
        raise ModelError(f"the model did not judge each of the {count} answers")
    return [read_verdict(each) for each in listed]


def make_story(context: dict[str, Any], state: dict[str, Any], model: Model) -> None:
    """Has the model write the next story, other than those before, unless
    it was written already or every story was."""
    stories = state["stories"]
    if len(stories) > len(state["done"]) or len(stories) >= context["instances"]:
        return
    mode = mode_of(context)
    prompt = PROMPTS(
        "making",
        language=context["language"],
        length=length_of(context),
        level=describe_level(context),
        lesson=describe_lesson(context),
        topics=describe_topics(context),
        words=describe_words(context),
        guidance=describe_guidance(context),
        made=describe_stories(stories),
        asking=PROMPTS(
            "asking", language=context["language"], count=questions_of(context)
        )
        if mode == "questions"
        else "",
        shape=PROMPTS("asked_shape") if mode == "questions" else "",
    )
    reply = ask_json(model, [{"role": "user", "content": prompt}])
    stories.append(read_story(reply, mode, questions_of(context)))


def judge_answers(
    context: dict[str, Any], story: dict[str, Any], answers: list[str], model: Model
) -> list[dict[str, str]]:
    """What the learner is told of each answer to the questions on a
    story: those left empty are wrong, and the others are judged by the
    model, together. Raises ModelError."""
    questions = story["questions"]
    given = [number for number, answer in enumerate(answers) if answer]
    verdicts: dict[int, tuple[str, str, str]] = {}
    if given:
        listed = "\n\n".join(
            PROMPTS(
                "answer",
                number=place,
                question=questions[number]["question"],
                answer=questions[number]["answer"],
                given=answers[number],
            )
            for place, number in enumerate(given, 1)
        )
        prompt = PROMPTS(
            "judging_answers",
            language=context["language"],
            level=level_of(context),
            story=story["text"],
            answers=listed,
            into=context["into"],
        )
        reply = ask_json(model, [{"role": "user", "content": prompt}])
        verdicts = dict(zip(given, read_verdicts(reply, len(given))))
    feedback = []
    for number, question in enumerate(questions):
        result, correction, note = verdicts.get(
            number, ("wrong", question["answer"], "")
        )
        feedback.append(
            {
                "result": result,
                "question": question["question"],
                "answer": answers[number],
                "correction": correction,
                "reference": question["answer"],
                "note": note,
            }
        )
    return feedback


def judge_retelling(
    context: dict[str, Any], story: dict[str, Any], retelling: str, model: Model
) -> dict[str, str]:
    """What the learner is told of how they retold a story. Raises
    ModelError."""
    prompt = PROMPTS(
        "judging_retelling",
        language=context["language"],
        level=level_of(context),
        story=story["text"],
        retelling=retelling,
        into=context["into"],
    )
    result, correction, note = read_verdict(
        ask_json(model, [{"role": "user", "content": prompt}])
    )
    return {
        "result": result,
        "answer": retelling,
        "correction": correction,
        "note": note,
    }


def _show(context: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    """What the interface shows: the story to be read with what is asked
    on it, or how the last went, with whether there is another and whether
    it was written already."""
    done = state["done"]
    mode = mode_of(context)
    shown: dict[str, Any] = {
        "at": len(done),
        "total": context["instances"],
        "mode": mode,
    }
    if state["reviewing"]:
        story = state["stories"][len(done) - 1]
        shown["story"] = {"title": story["title"], "text": story["text"]}
        shown["feedback"] = done[-1]["feedback"]
        shown["result"] = done[-1]["result"]
        shown["more"] = len(done) < context["instances"]
        shown["prepared"] = len(state["stories"]) > len(done)
    else:
        story = state["stories"][len(done)]
        shown["story"] = {"title": story["title"], "text": story["text"]}
        shown["number"] = len(done)
        if mode == "questions":
            shown["questions"] = [each["question"] for each in story["questions"]]
    return shown


def _told(state: dict[str, Any]) -> list[str]:
    """The story on show, with its questions, if it was not told before as
    written; it is noted as told."""
    at = len(state["done"])
    if state["reviewing"] or state["told"] > at:
        return []
    state["told"] = at + 1
    story = state["stories"][at]
    return [
        story["text"],
        *(each["question"] for each in story.get("questions", [])),
    ]


def start(context: dict[str, Any], model: Model) -> Step:
    state: dict[str, Any] = {
        "stories": [],
        "done": [],
        "reviewing": False,
        # how many of the stories were reported as written
        "told": 0,
    }
    make_story(context, state, model)
    return Step(
        state=state, show=_show(context, state), written=written([], _told(state))
    )


def _answered(
    context: dict[str, Any],
    state: dict[str, Any],
    message: dict[str, Any],
    model: Model,
) -> Step | None:
    """Judges what the learner did with the story on show, and grades it;
    None if there was nothing to judge."""
    mode = mode_of(context)
    story = state["stories"][len(state["done"])]
    graded: list[dict[str, str]] = []
    if mode == "questions" and isinstance(message.get("answers"), list):
        count = len(story["questions"])
        answers = [
            " ".join(answer.split())[:MAX_ANSWER_LENGTH]
            if isinstance(answer, str)
            else ""
            for answer in [*message["answers"], *[""] * count][:count]
        ]
        if not any(answers):
            return None
        feedback = judge_answers(context, story, answers, model)
        one = grade_of(
            [
                grade(
                    each["result"],
                    each["answer"],
                    each["correction"],
                    each["note"],
                    f"Answer a question on the story: {each['question']}",
                )
                for each in feedback
            ]
        )
        graded, result = [one], one["result"]
        said = written(
            [answer for answer in answers if answer],
            [
                shown
                for each in feedback
                for shown in dict.fromkeys([each["correction"], each["reference"]])
                if shown
            ],
        )
    elif mode == "retell" and isinstance(message.get("retelling"), str):
        retelling = message["retelling"].strip()[:MAX_RETELLING_LENGTH]
        if not retelling:
            return None
        verdict = judge_retelling(context, story, retelling, model)
        feedback = [verdict]
        task = f'Retell the story "{story["title"]}" in a few sentences'
        graded, result = [grade(**verdict, task=task)], verdict["result"]
        said = written([retelling], [verdict["correction"]])
    elif mode == "read" and message.get("read"):
        feedback, result, said = [], "", {}
    else:
        return None
    state["done"].append({"feedback": feedback, "result": result})
    state["reviewing"] = True
    return Step(state=state, show=_show(context, state), graded=graded, written=said)


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    """Judges what was done with the story on show: the answers to its
    questions, as `{"answers": [...]}`, how it was retold, as
    `{"retelling": "..."}`, or that it was read, as `{"read": true}`; writes
    the next story, as `{"prepare": true}`; or goes on to it, as
    `{"next": true}`."""
    message = message if isinstance(message, dict) else {}
    more = len(state["done"]) < context["instances"]
    if message.get("prepare") and state["reviewing"] and more:
        make_story(context, state, model)
    elif message.get("next") and state["reviewing"] and more:
        make_story(context, state, model)
        state["reviewing"] = False
        return Step(
            state=state, show=_show(context, state), written=written([], _told(state))
        )
    elif not state["reviewing"]:
        answered = _answered(context, state, message, model)
        if answered:
            return answered
    return Step(state=state, show=_show(context, state))


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    done = [
        {"story": story, **answered}
        for story, answered in zip(state["stories"], state["done"])
    ]
    # each question answered counts as reading, and a retelling as writing
    score = score_of(
        [each["result"] for answered in state["done"] for each in answered["feedback"]]
    )
    skill = {"questions": "lesen", "retell": "schreiben"}.get(mode_of(context))
    return Step(
        state=state,
        results={
            "stories": done,
            "mode": mode_of(context),
            "total": context["instances"],
        },
        scores=None if score is None or skill is None else {skill: score},
    )


if __name__ == "__main__":
    serve(start, act, finish)
