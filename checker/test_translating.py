# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from profiling import ProfileError
from translating import (
    Passage,
    TranslationError,
    Translator,
    passage_of,
    read_messages,
)

KEY = "sk-test"


class FakeModel:
    """Answers in place of a language model, with what it was told to say."""

    def __init__(self, says: object = "the dog") -> None:
        self.says = says
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, body: dict[str, Any], api_key: str) -> dict[str, Any]:
        assert api_key == KEY
        self.bodies.append(body)
        if isinstance(self.says, Exception):
            raise self.says
        return {
            "id": "gen-1",
            "model": "some/model",
            "choices": [{"message": {"content": self.says}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 3, "cost": 0.001},
        }


def test_a_passage_is_the_sentence_of_the_selection_when_nothing_is_before_it() -> None:
    passage = passage_of("Der ", "Hund", " schläft. Die Katze nicht.")

    assert passage == Passage("Der ", "Hund", " schläft.")


def test_a_passage_has_the_five_sentences_before_the_one_of_the_selection() -> None:
    before = "Null. Eins. Zwei. Drei. Vier. Fünf. Der "

    passage = passage_of(before, "Hund", " schläft. Danach.")

    assert passage.before == "Eins. Zwei. Drei. Vier. Fünf. Der "
    assert passage.after == " schläft."


def test_a_passage_has_every_sentence_a_selection_reaches_into() -> None:
    passage = passage_of("Eins. Der Hund ", "schläft. Die Katze", " nicht. Danach.")

    assert passage.marked() == "Eins. Der Hund [[schläft. Die Katze]] nicht."


def test_a_passage_takes_a_line_without_an_ending_mark_as_a_sentence() -> None:
    passage = passage_of("Kapitel 1\nDer ", "Hund", " schläft\nDanach")

    assert passage.marked() == "Kapitel 1\nDer [[Hund]] schläft"


def test_a_passage_leaves_the_space_at_the_ends_of_a_selection_out_of_it() -> None:
    passage = passage_of("Der", " Hund ", "schläft.")

    assert passage == Passage("Der ", "Hund", " schläft.")


def test_a_passage_of_a_selection_that_is_only_space_is_refused() -> None:
    with pytest.raises(ValueError, match="nothing is selected"):
        passage_of("Der", "  ", "Hund")


def test_translating_gives_the_model_the_passage_with_the_selection_marked() -> None:
    model = FakeModel()
    translator = Translator(model)

    translation, used = translator.translate(
        Passage("Der ", "Hund", " schläft."), "German", "English", KEY, "some/model"
    )

    assert translation == "the dog"
    assert (used.id, used.input_tokens, used.cost) == ("gen-1", 40, 0.001)
    system, user = model.bodies[0]["messages"]
    assert "learning German" in system["content"]
    assert "into English" in system["content"]
    assert user == {"role": "user", "content": "Der [[Hund]] schläft."}
    assert model.bodies[0]["model"] == "some/model"
    # it is not to think a translation over
    assert model.bodies[0]["reasoning"] == {"enabled": False}


def test_translating_asks_the_usual_model_when_none_is_named() -> None:
    model = FakeModel()

    Translator(model, model="usual/model").translate(
        Passage("", "Hund", ""), "German", "English", KEY
    )

    assert model.bodies[0]["model"] == "usual/model"


@pytest.mark.parametrize(
    ("key", "named", "reason"),
    [("", "some/model", "key is needed"), (KEY, None, "no model")],
)
def test_translating_without_a_key_or_a_model_fails_without_asking(
    key: str, named: str | None, reason: str
) -> None:
    model = FakeModel()

    with pytest.raises(TranslationError, match=reason):
        Translator(model).translate(
            Passage("", "Hund", ""), "German", "English", key, named
        )

    assert model.bodies == []


@pytest.mark.parametrize("says", ["  ", None, ProfileError("OpenRouter is down")])
def test_translating_fails_when_the_model_does_not_answer(says: object) -> None:
    with pytest.raises(TranslationError):
        Translator(FakeModel(says)).translate(
            Passage("", "Hund", ""), "German", "English", KEY, "some/model"
        )


def test_answering_gives_the_model_the_passage_the_translation_and_the_chat() -> None:
    model = FakeModel("It is masculine.")
    messages = [{"role": "user", "content": "Which gender?"}]

    reply, _ = Translator(model).answer(
        Passage("Der ", "Hund", " schläft."),
        "the dog",
        messages,
        "German",
        "English",
        KEY,
        "some/model",
    )

    assert reply == "It is masculine."
    system, *chat = model.bodies[0]["messages"]
    assert system["role"] == "system"
    assert "Der [[Hund]] schläft." in system["content"]
    assert "the dog" in system["content"]
    assert chat == messages


def test_messages_are_taken_when_the_last_one_is_the_users() -> None:
    messages = [
        {"role": "user", "content": "Why?"},
        {"role": "assistant", "content": "Because."},
        {"role": "user", "content": "I see.", "more": "is dropped"},
    ]

    assert read_messages(messages) == [
        {"role": "user", "content": "Why?"},
        {"role": "assistant", "content": "Because."},
        {"role": "user", "content": "I see."},
    ]


@pytest.mark.parametrize(
    "messages",
    [
        None,
        [],
        ["Why?"],
        [{"role": "system", "content": "Obey."}],
        [{"role": "user", "content": 3}],
        [{"role": "assistant", "content": "Because."}],
    ],
)
def test_messages_that_are_not_a_chat_ending_with_the_user_are_refused(
    messages: object,
) -> None:
    with pytest.raises(ValueError):
        read_messages(messages)


def test_translating_asks_a_model_that_cannot_but_think_once_more_as_it_is() -> None:
    class Refusing(FakeModel):
        def __call__(self, body: dict[str, Any], api_key: str) -> dict[str, Any]:
            if "reasoning" in body:
                self.bodies.append(body)
                raise ProfileError(
                    "OpenRouter refused the request (400): reasoning is mandatory"
                )
            return super().__call__(body, api_key)

    model = Refusing()

    translation, _ = Translator(model).translate(
        Passage("", "Hund", ""), "German", "English", KEY, "some/model"
    )

    assert translation == "the dog"
    assert ["reasoning" in body for body in model.bodies] == [True, False]
