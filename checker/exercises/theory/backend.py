# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The theory of a lesson, shown page by page, with a chat beside it in
which the learner asks about it.

The pages are the `more_info` of the lesson, written in Markdown, with a
line of `---` between one page and the next. Turning the pages is done by
the interface alone; the backend is asked only when the learner asks
something, and is told which page they are on. Nothing is answered here
that counts, so no logs are kept: what was asked stays in the state, and
how many questions there were in the results.
"""

from __future__ import annotations

import re
from typing import Any

from kit import Model, ModelError, Step, describe_lesson, serve

# the line between one page and the next
_BREAK = re.compile(r"^\s*---\s*$", re.MULTILINE)
# how many of the questions before, with their answers, the model is shown
MAX_TURNS = 10
# how many questions and answers are kept in the state at the most
MAX_CHAT = 100
MAX_QUESTION = 2000

TEACHING = """\
You are a patient teacher of {language}. The learner, at level {level}, is \
reading the lesson below page by page, and asks you about it.

Answer what they ask, about the lesson or about {language}, briefly and \
clearly: a few sentences, with examples in {language} where they help. \
Write in the language the learner wrote in; if they wrote in {language}, \
write simple {language} that a learner at level {level} understands. The \
learner's own language is {into}: whatever you translate or say the meaning \
of, say in {into}. If \
they try the exercise at the end of a page, say which of their answers are \
right, and correct the others, saying why. Use Markdown for bold, lists and \
small tables where they help, but no headings. Colour a part of a {language} \
sentence as the pages do only where it is what the lesson or the question \
is about, and leave the rest plain: {{v:stehe}} for the conjugated verb, \
{{p:auf}} a prefix, {{i:aufstehen}} a verb at the end, {{e:st}} an ending, \
{{c:i}} a vowel that changes, {{x:...}} what is wrong.

{lesson}

The pages of the lesson, with --- between them:

{pages}"""


def pages_of(text: str) -> list[str]:
    """The pages of the theory of a lesson, those with something on them."""
    return [page.strip() for page in _BREAK.split(text) if page.strip()]


def _show(state: dict[str, Any]) -> dict[str, Any]:
    chat = state["chat"]
    return {
        "title": state["title"],
        "pages": state["pages"],
        # the page asked about last, where an interface opened again starts
        "page": chat[-1]["page"] if chat else 0,
        "chat": chat,
    }


def start(context: dict[str, Any], model: Model) -> Step:
    lesson = context["lesson"]
    pages = pages_of(lesson.get("more_info") or "")
    if not pages:
        raise ModelError("this lesson has no theory yet")
    state = {"title": lesson["title"], "pages": pages, "chat": []}
    return Step(state=state, show=_show(state))


def act(context: dict[str, Any], state: Any, message: Any, model: Model) -> Step:
    question = message.get("question") if isinstance(message, dict) else None
    page = message.get("page") if isinstance(message, dict) else None
    if not isinstance(question, str) or not question.strip():
        return Step(state=state, show=_show(state))
    question = question.strip()[:MAX_QUESTION]
    pages = state["pages"]
    page = page if isinstance(page, int) and 0 <= page < len(pages) else 0
    level = context["level"] or context["lesson"]["level"]
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": TEACHING.format(
                language=context["language"],
                into=context["into"],
                level=level,
                lesson=describe_lesson(context, ("new", "review", "preview")),
                pages="\n\n---\n\n".join(pages),
            ),
        }
    ]
    for turn in state["chat"][-MAX_TURNS:]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append(
        {
            "role": "user",
            "content": f"(I am on page {page + 1} of {len(pages)}.)\n\n{question}",
        }
    )
    answer = model.ask(messages).strip()
    if not answer:
        raise ModelError("the model gave no answer")
    state["chat"] = (
        state["chat"] + [{"page": page, "question": question, "answer": answer}]
    )[-MAX_CHAT:]
    return Step(state=state, show=_show(state))


def finish(context: dict[str, Any], state: Any, model: Model) -> Step:
    return Step(state=state, results={"questions": len(state["chat"])})


if __name__ == "__main__":
    serve(start, act, finish)
