# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from kit import AnkiError, ModelError

from anki_review.backend import act, finish, plain, start

CONTEXT: dict[str, Any] = {
    "language": "German",
    "into": "English",
    "level": "",
    "lesson": {"id": "", "level": "", "title": "", "more_info": "", "points": []},
    "topics": [],
    "instances": 1,
    "options": {"deck": "7"},
    "anki_decks": {"deck": {"id": 7, "name": "Deutsch::Tiere"}},
}


def card(card_id: int, front: str, back: str) -> dict[str, Any]:
    return {
        "id": card_id,
        "note_id": card_id * 10,
        "ord": 1,
        "queue": "new",
        "question": f"<style>.x{{}}</style>{front} [anki:play:q:0]",
        "answer": f"{front}<hr id=answer>{back}",
        "css": ".card {}",
        "question_av": [{"kind": "sound", "file": "a.mp3"}],
        "answer_av": [],
        "labels": ["<1m", "<6m", "<10m", "4d"],
        "settings": {"autoplay": True},
    }


def shown(next_card: dict[str, Any] | None, **more: Any) -> dict[str, Any]:
    return {"card": next_card, "counts": {"new": 2, "learning": 0, "review": 0}, **more}


class FakeAnki:
    """Replies to what is asked of Anki with each of `replies` in turn,
    and remembers what was asked; a reply that is an AnkiError is raised."""

    def __init__(self, *replies: object) -> None:
        self.replies = list(replies)
        self.asked: list[dict[str, Any]] = []

    def anki(self, request: dict[str, Any]) -> Any:
        self.asked.append(request)
        reply = self.replies.pop(0)
        if isinstance(reply, AnkiError):
            raise reply
        return reply

    def ask(self, messages: list[dict[str, Any]]) -> str:
        raise ModelError("asks no model")

    def look(self, messages: list[dict[str, Any]]) -> str:
        raise ModelError("asks no model")

    def draw(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        raise ModelError("draws nothing")


def test_plain_leaves_the_markup_sounds_and_styles_out_of_a_side() -> None:
    side = "<style>.a{}</style><b>der Hund</b>&nbsp;[anki:play:q:0]<br>[[type:Back]]dog"

    assert plain(side) == "der Hund\ndog"


def test_start_syncs_and_shows_the_first_card_of_the_deck() -> None:
    anki = FakeAnki({"synced": True}, shown(card(1, "der Hund", "dog")))

    step = start(CONTEXT, anki)

    assert anki.asked == [{"op": "sync"}, {"op": "next", "deck": 7}]
    assert step.show["card"]["id"] == 1
    assert step.show["deck"] == "Deutsch::Tiere"
    assert not step.show["over"]
    assert step.state["card"] == {"id": 1, "question": "der Hund"}
    # its words are not taken in, as the import of the Anki words has them
    assert step.written == {}


def test_start_goes_on_with_the_last_sync_when_anki_cannot_be_synced() -> None:
    anki = FakeAnki(AnkiError("offline"), shown(card(1, "der Hund", "dog")))

    step = start(CONTEXT, anki)

    assert "offline" in step.show["notice"]
    assert step.show["card"]["id"] == 1


def test_start_needs_a_deck() -> None:
    with pytest.raises(AnkiError, match="deck"):
        start({**CONTEXT, "anki_decks": {}}, FakeAnki())


def test_act_answers_the_card_shown_and_grades_it_by_the_button() -> None:
    anki = FakeAnki(
        {"synced": True},
        shown(card(1, "der Hund", "dog")),
        shown(card(2, "die Katze", "cat"), answered=True),
    )
    first = start(CONTEXT, anki)

    step = act(CONTEXT, first.state, {"rating": 2, "millis": 3500}, anki)

    assert anki.asked[-1] == {
        "op": "answer",
        "deck": 7,
        "card": 1,
        "rating": 2,
        "millis": 3500,
    }
    assert step.graded == [
        {
            "result": "partial",
            "task": "der Hund",
            "answer": "Hard",
            "correction": "",
            "note": "",
        }
    ]
    assert step.show["card"]["id"] == 2
    assert step.show["reviewed"] == 1
    assert step.state["ratings"] == {"Hard": 1}


def test_act_grades_nothing_when_the_card_was_reviewed_elsewhere() -> None:
    anki = FakeAnki(
        {"synced": True},
        shown(card(1, "der Hund", "dog")),
        shown(card(2, "die Katze", "cat"), answered=False),
    )
    first = start(CONTEXT, anki)

    step = act(CONTEXT, first.state, {"rating": 3}, anki)

    assert step.graded == []
    assert step.show["reviewed"] == 0
    assert "elsewhere" in step.show["notice"]
    assert step.state["card"]["id"] == 2


def test_the_review_goes_on_while_cards_are_due_however_many_were_answered() -> None:
    anki = FakeAnki(
        {"synced": True},
        shown(card(1, "der Hund", "dog")),
        shown(card(2, "die Katze", "cat"), answered=True),
        shown(card(3, "die Maus", "mouse"), answered=True),
    )
    state = start(CONTEXT, anki).state
    state = act(CONTEXT, state, {"rating": 3}, anki).state

    step = act(CONTEXT, state, {"rating": 1}, anki)

    assert not step.show["over"]
    assert (step.show["card"]["id"], step.show["reviewed"]) == (3, 2)


def test_the_review_is_over_when_nothing_more_is_due() -> None:
    anki = FakeAnki(
        {"synced": True},
        shown(card(1, "der Hund", "dog")),
        shown(None, answered=True),
    )
    state = start(CONTEXT, anki).state

    step = act(CONTEXT, state, {"rating": 4}, anki)

    assert step.show["over"]
    assert step.show["done_for_today"]
    assert step.show["ratings"] == {"Easy": 1}


def test_act_refuses_what_is_no_button() -> None:
    anki = FakeAnki({"synced": True}, shown(card(1, "der Hund", "dog")))
    state = start(CONTEXT, anki).state

    for message in [{"rating": 0}, {"rating": 5}, {}, "Good"]:
        with pytest.raises(AnkiError):
            act(CONTEXT, state, message, anki)


def test_finish_says_how_many_cards_were_answered_with_each_button() -> None:
    state = {
        "deck": {"id": 7, "name": "Deutsch::Tiere"},
        "reviewed": 3,
        "ratings": {"Good": 2, "Again": 1},
        "card": None,
    }

    step = finish(CONTEXT, state, FakeAnki())

    assert step.results == {
        "deck": "Deutsch::Tiere",
        "reviewed": 3,
        "ratings": {"Good": 2, "Again": 1},
    }
    # its log is that, as the buttons say too little for a model to say more
    assert step.log == "Reviewed 3 cards of Deutsch::Tiere in Anki: Again 1, Good 2."
