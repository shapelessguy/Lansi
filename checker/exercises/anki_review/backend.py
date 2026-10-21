# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The cards of a deck of the learner's Anki collection, as the option
`deck` chooses it, reviewed as the reviewer of Anki reviews them: the
question, then the answer, and one of the four buttons, Again, Hard, Good
and Easy, each answer a review of the collection, scheduled by the options
of the deck and synced to the learner's other devices. Nothing is asked of
a model.

The collection is synced as the exercise starts, so that the cards are as
the learner left them elsewhere. Each card is graded by the button: Again
wrong, Hard partial, and Good and Easy right. The exercise is done once,
with no time limit: it is over once nothing more is due today, or the
learner leaves it.

The words of the cards are not taken into the vocabulary here, as the
import of the Anki words has them already.
"""

from __future__ import annotations

import html
import re
from typing import Any

from kit import AnkiError, Model, Step, ask_anki, grade, serve

# the buttons by the ratings they give, as the keys of the reviewer are
BUTTONS = {1: "Again", 2: "Hard", 3: "Good", 4: "Easy"}
RESULTS = {1: "wrong", 2: "partial", 3: "right", 4: "right"}
# how much of a side is kept for the grade and the log
MAX_SIDE = 300

_HIDDEN = re.compile(r"<(style|script)\b.*?</\1\s*>", re.DOTALL | re.IGNORECASE)
_BREAK = re.compile(r"<br\s*/?>|</(?:div|p|li|tr|h\d)\s*>|<hr\b[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]*>")
_MARKER = re.compile(r"\[anki:play:[qa]:\d+\]|\[\[type:[^\]]*\]\]")


def plain(side: str) -> str:
    """A side of a card as text: its lines, without markup, sounds or the
    boxes an answer is typed in."""
    text = _BREAK.sub("\n", _HIDDEN.sub(" ", side))
    text = html.unescape(_MARKER.sub("", _TAG.sub("", text)))
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def _cut(text: str) -> str:
    return text if len(text) <= MAX_SIDE else text[:MAX_SIDE].rstrip() + "…"


def _deck(context: dict[str, Any]) -> dict[str, Any]:
    deck = (context.get("anki_decks") or {}).get("deck")
    if not deck:
        raise AnkiError(
            "this exercise needs a deck of your Anki collection: link one first"
        )
    return dict(deck)


def _showing(
    context: dict[str, Any],
    state: dict[str, Any],
    shown: dict[str, Any],
    notice: str = "",
) -> Step:
    """The step that shows the card `shown`, or that the exercise is over;
    the card is kept in the state, by its id and its question as text."""
    card = shown.get("card")
    over = card is None
    state = {
        **state,
        "card": {"id": card["id"], "question": _cut(plain(card["question"]))}
        if card is not None and not over
        else None,
    }
    show = {
        "deck": state["deck"]["name"],
        "card": None if over else card,
        "counts": shown.get("counts") or {},
        "reviewed": state["reviewed"],
        "ratings": state["ratings"],
        "over": over,
        # whether nothing more is due in the deck today
        "done_for_today": card is None,
        "notice": notice,
    }
    return Step(state=state, show=show)


def start(context: dict[str, Any], model: Model) -> Step:
    """Syncs the collection, and shows the first card of the deck."""
    deck = _deck(context)
    notice = ""
    try:
        ask_anki(model, {"op": "sync"})
    except AnkiError as error:
        notice = (
            "Anki could not be synced, so the cards are as they were at the"
            f" last sync: {error}"
        )
    shown = ask_anki(model, {"op": "next", "deck": deck["id"]})
    state = {"deck": deck, "reviewed": 0, "ratings": {}, "card": None}
    return _showing(context, state, shown, notice)


def act(
    context: dict[str, Any], state: dict[str, Any], message: Any, model: Model
) -> Step:
    """Answers the card shown with the button of `{"rating": 1 to 4,
    "millis": ...}`, how long it was looked at, and shows the next."""
    card = state.get("card")
    rating = message.get("rating") if isinstance(message, dict) else None
    if card is None or rating not in BUTTONS:
        raise AnkiError("a card is answered with Again, Hard, Good or Easy")
    millis = message.get("millis")
    reply = ask_anki(
        model,
        {
            "op": "answer",
            "deck": state["deck"]["id"],
            "card": card["id"],
            "rating": rating,
            "millis": millis if isinstance(millis, int) and millis >= 0 else 0,
        },
    )
    if not reply.get("answered"):
        return _showing(
            context,
            state,
            reply,
            "The card was reviewed elsewhere since it was shown: here is the next.",
        )
    ratings = dict(state["ratings"])
    ratings[BUTTONS[rating]] = ratings.get(BUTTONS[rating], 0) + 1
    answered = {**state, "reviewed": state["reviewed"] + 1, "ratings": ratings}
    step = _showing(context, answered, reply)
    step.graded = [grade(RESULTS[rating], BUTTONS[rating], task=card["question"])]
    return step


def finish(context: dict[str, Any], state: dict[str, Any], model: Model) -> Step:
    """What the review came to: how many cards were answered with each
    button, which is its log too, as the buttons say too little for a model
    to write more of. The answers were synced as they were given."""
    counted = ", ".join(
        f"{button} {state['ratings'][button]}"
        for button in BUTTONS.values()
        if state["ratings"].get(button)
    )
    reviewed = state["reviewed"]
    return Step(
        state=state,
        results={
            "deck": state["deck"]["name"],
            "reviewed": reviewed,
            "ratings": state["ratings"],
        },
        log=f"Reviewed {reviewed} {'card' if reviewed == 1 else 'cards'} of"
        f" {state['deck']['name']} in Anki" + (f": {counted}." if counted else "."),
    )


if __name__ == "__main__":
    serve(start, act, finish)
