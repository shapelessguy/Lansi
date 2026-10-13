# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from profiling import (
    QUESTIONS,
    Answer,
    LocalModel,
    Profile,
    ProfileError,
    Profiler,
    WordRating,
    describe_assessment,
    doubt_about,
    read_profile,
    read_questions,
    weigh_ratings,
)


def response(**changes: Any) -> dict[str, Any]:
    """What the Decisions API returns for the two questions, with changes."""
    answers: dict[str, Any] = {
        "grammar_errors": {
            "type": "choice",
            "choice": "one",
            "confidence": 0.87,
            "probabilities": {"none": 0.05, "one": 0.9, "several": 0.05},
        },
        "clarity": {
            "type": "score",
            "score": 2.6,
            "confidence": 0.7,
            "probabilities": {"0": 0, "1": 0.05, "2": 0.3, "3": 0.65},
        },
    }
    answers.update(changes)
    return {
        "id": "gen-dec-1",
        "model": "typesafe/jev-1.13",
        "answers": answers,
        "usage": {"input_tokens": 180, "output_tokens": 0, "cost": 0.0000076},
    }


def test_read_profile_gives_the_answer_to_each_question_and_what_it_used() -> None:
    assert read_profile(response()) == Profile(
        {
            # no errors, the best there is, was given 5%
            "grammar_errors": Answer(
                "choice", choice="one", confidence=0.87, best=0.05
            ),
            "clarity": Answer(
                "score", score=2.6, max_score=3, confidence=0.7, best=2.6 / 3
            ),
        },
        cost=0.0000076,
        id="gen-dec-1",
        model="typesafe/jev-1.13",
        input_tokens=180,
        output_tokens=0,
    )


def test_read_profile_accepts_a_response_without_confidence_or_usage() -> None:
    reply = response(grammar_errors={"type": "choice", "choice": "none"})
    del reply["usage"]

    profile = read_profile(reply)

    # without the chance of each option, the one picked is all there is to go by
    assert profile.answers["grammar_errors"] == Answer(
        "choice", choice="none", best=1.0
    )
    assert (profile.cost, profile.input_tokens, profile.output_tokens) == (None, 0, 0)


def test_read_profile_gives_each_request_its_own_id_when_none_is_sent() -> None:
    reply = response()
    del reply["id"]

    first, second = read_profile(reply), read_profile(reply)

    assert first.id and second.id
    assert first.id != second.id


@pytest.mark.parametrize(
    "broken",
    [
        {"answers": None},
        {},
        response(grammar_errors=None),
        response(grammar_errors={"type": "choice", "choice": "dozens"}),
        response(clarity={"type": "score", "score": "high"}),
        response(clarity={"type": "score"}),
    ],
)
def test_read_profile_refuses_a_response_that_does_not_answer_the_questions(
    broken: dict[str, Any],
) -> None:
    with pytest.raises(ProfileError):
        read_profile(broken)


def test_profile_sends_the_sentence_and_every_question_with_the_key() -> None:
    sent: list[tuple[dict[str, Any], str]] = []

    def send(body: dict[str, Any], api_key: str) -> dict[str, Any]:
        sent.append((body, api_key))
        return response()

    profile = Profiler("some/model", send).profile("Er ist gut.", "the-key")

    assert sent == [
        (
            {
                "model": "some/model",
                "state": {"sentence": "Er ist gut."},
                "questions": QUESTIONS,
            },
            "the-key",
        )
    ]
    assert profile.answers["grammar_errors"].choice == "one"


def test_profile_asks_the_model_it_is_given_instead_of_the_usual_one() -> None:
    asked: list[str] = []

    def send(body: dict[str, Any], api_key: str) -> dict[str, Any]:
        asked.append(body["model"])
        return response()

    profiler = Profiler("usual/model", send)
    profiler.profile("Er ist gut.", "the-key", "other/model")
    profiler.profile("Er ist gut.", "the-key", None)

    assert asked == ["other/model", "usual/model"]


POLITE = {
    "type": "choice",
    "instructions": "Is the sentence polite?",
    "criteria": {"yes": "It is polite.", "no": "It is not polite."},
}


def test_profile_asks_the_questions_it_is_given_and_reads_their_answers() -> None:
    asked: list[Any] = []

    def send(body: dict[str, Any], api_key: str) -> dict[str, Any]:
        asked.append(body["questions"])
        return {"answers": {"polite": {"type": "choice", "choice": "yes"}}}

    profile = Profiler(send=send).profile(
        "Er ist gut.", "the-key", questions={"polite": POLITE}
    )

    assert asked == [{"polite": POLITE}]
    assert profile.answers == {"polite": Answer("choice", choice="yes", best=0.0)}


def test_read_questions_keeps_usable_questions_as_they_are() -> None:
    scale = {
        "type": "score",
        "instructions": "How formal is it?",
        "criteria": ["Casual", "Neutral", "Formal"],
    }

    assert read_questions({"polite": POLITE, "formal": scale}) == {
        "polite": POLITE,
        "formal": scale,
    }


@pytest.mark.parametrize(
    "questions",
    [
        ["polite"],
        {"polite": "Is it polite?"},
        {"polite": {**POLITE, "instructions": " "}},
        {"polite": {**POLITE, "type": "essay"}},
        {"polite": {**POLITE, "criteria": {"yes": "It is polite."}}},
        {"polite": {**POLITE, "criteria": ["It is polite.", "It is not."]}},
        {"formal": {**POLITE, "type": "score"}},
        {f"q{number}": POLITE for number in range(21)},
    ],
)
def test_read_questions_refuses_questions_that_cannot_be_asked(
    questions: object,
) -> None:
    with pytest.raises(ValueError):
        read_questions(questions)


# rating the words


def test_rate_words_asks_of_every_word_whether_it_is_right_by_what_was_found() -> None:
    sent: list[dict[str, Any]] = []

    def send(body: dict[str, Any], api_key: str) -> dict[str, Any]:
        sent.append(body)
        return {
            "id": "gen-dec-2",
            "answers": {
                "w1": {"type": "noul", "noul": 0.92},
                "w2": {"type": "noul", "noul": 0.31},
                "w3": {"type": "noul", "noul": 0.55},
            },
            "usage": {"input_tokens": 400, "output_tokens": 0, "cost": 0.00002},
        }

    assessment = [{"question": "How many errors?", "answer": "one: One error."}]

    ratings, profile = Profiler("some/model", send).rate_words(
        "Ich habe, Hund.", assessment, "the-key"
    )

    (body,) = sent
    assert body["model"] == "some/model"
    assert body["state"] == {"sentence": "Ich habe, Hund.", "assessment": assessment}
    assert list(body["questions"]) == ["w1", "w2", "w3"]
    assert {question["type"] for question in body["questions"].values()} == {"noul"}
    assert '"Hund" (word 3 of the sentence)' in body["questions"]["w3"]["instructions"]
    assert ratings == [
        WordRating("Ich", 0, 3, 0.92),
        # the comma is not part of the word
        WordRating("habe", 4, 8, 0.31),
        WordRating("Hund", 10, 14, 0.55),
    ]
    assert (profile.id, profile.input_tokens) == ("gen-dec-2", 400)


def test_rate_words_fails_when_a_word_is_not_given_a_value() -> None:
    def send(body: dict[str, Any], api_key: str) -> dict[str, Any]:
        return {"answers": {"w1": {"type": "noul", "noul": "yes"}}}

    with pytest.raises(ProfileError, match="w1 is not a yes or a no"):
        Profiler(send=send).rate_words("Hund.", [], "the-key")


def test_rate_words_fails_for_a_sentence_without_words() -> None:
    with pytest.raises(ProfileError):
        Profiler(send=lambda body, key: {}).rate_words("...", [], "the-key")


def test_an_assessment_gives_each_question_with_its_answer_in_words() -> None:
    answers = {
        "grammar_errors": Answer("choice", choice="one", confidence=0.6),
        "clarity": Answer("score", score=2.6, max_score=3),
    }

    assert describe_assessment(QUESTIONS, answers) == [
        {
            "question": QUESTIONS["grammar_errors"]["instructions"],
            "answer": "one: The sentence has exactly one grammar error.",
        },
        {
            "question": QUESTIONS["clarity"]["instructions"],
            "answer": "Clear: the meaning is plain on first reading. (2.6 of 3)",
        },
    ]


def test_an_assessment_leaves_out_questions_that_have_no_answer() -> None:
    answers = {"clarity": Answer("score", score=0.2, max_score=3)}

    (only,) = describe_assessment(QUESTIONS, answers)

    assert only["answer"].startswith("Unclear")


# weighing the ratings by what was found out about the sentence


def test_there_is_as_much_to_doubt_in_a_sentence_as_its_worst_answer_is_from_the_best() -> (
    None
):
    answers = {
        "grammar_errors": Answer("choice", choice="none", best=0.8),
        "clarity": Answer("score", score=2.7, max_score=3, best=0.9),
    }

    assert doubt_about(answers) == pytest.approx(0.2)


def test_everything_is_in_doubt_when_no_answer_can_be_placed() -> None:
    assert doubt_about({"polite": Answer("choice", choice="yes")}) == 1.0
    assert doubt_about({}) == 1.0


def test_a_word_counts_as_wrong_only_as_far_as_its_sentence_was_found_wrong() -> None:
    ratings = [WordRating("Hi", 0, 2, 0.4), WordRating("ich", 3, 6, 0.9)]

    in_a_sentence_found_right = weigh_ratings(ratings, doubt=0.0)
    in_a_sentence_in_some_doubt = weigh_ratings(ratings, doubt=0.25)
    in_a_sentence_found_wrong = weigh_ratings(ratings, doubt=1.0)

    assert [rating.value for rating in in_a_sentence_found_right] == [1.0, 1.0]
    assert [rating.value for rating in in_a_sentence_in_some_doubt] == pytest.approx(
        [0.85, 0.975]
    )
    assert in_a_sentence_found_wrong == ratings


# a model on this machine


class Sent:
    """Stands in for both places a request can go, and notes what went where."""

    def __init__(self) -> None:
        self.to_openrouter: list[tuple[dict[str, Any], str]] = []
        self.to_local: list[dict[str, Any]] = []
        self.local_is_down = False

    def openrouter(self, body: dict[str, Any], api_key: str) -> dict[str, Any]:
        self.to_openrouter.append((body, api_key))
        return response()

    def local(self, body: dict[str, Any], _api_key: str) -> dict[str, Any]:
        if self.local_is_down:
            raise ProfileError("could not reach the local model: refused")
        self.to_local.append(body)
        # as the local server answers: no id and no cost
        return {
            "model": "local/clef",
            "answers": response()["answers"],
            "usage": {"input_tokens": 292, "output_tokens": 0},
        }


def profiler_with_local(sent: Sent, found: str | None = "local/clef") -> Profiler:
    local = LocalModel(probe=lambda _endpoint: found, send=sent.local)
    local.look()
    return Profiler("some/model", sent.openrouter, local)


def test_a_local_model_is_asked_instead_of_openrouter_and_needs_no_key() -> None:
    sent = Sent()

    profile = profiler_with_local(sent).profile("Er ist gut.", "")

    assert sent.to_local == [
        {"state": {"sentence": "Er ist gut."}, "questions": QUESTIONS}
    ]
    assert sent.to_openrouter == []
    assert (profile.local, profile.model, profile.cost) == (True, "local/clef", None)
    assert profile.answers["grammar_errors"].choice == "one"


def test_openrouter_is_asked_while_no_local_model_is_found() -> None:
    sent = Sent()
    profiler = profiler_with_local(sent, found=None)

    profile = profiler.profile("Er ist gut.", "the-key")

    assert profiler.local_model() is None
    assert sent.to_local == []
    assert [key for _, key in sent.to_openrouter] == ["the-key"]
    assert profile.local is False


def test_openrouter_is_asked_when_the_local_model_has_gone_since_it_was_found() -> None:
    sent = Sent()
    profiler = profiler_with_local(sent)
    sent.local_is_down = True

    profile = profiler.profile("Er ist gut.", "the-key")

    assert sent.to_openrouter[0][0]["model"] == "some/model"
    assert profile.local is False
    # and it is not tried again until it is found again
    assert profiler.local_model() is None


def test_a_profile_fails_when_the_local_model_has_gone_and_there_is_no_key() -> None:
    sent = Sent()
    profiler = profiler_with_local(sent)
    sent.local_is_down = True

    with pytest.raises(ProfileError, match="could not reach the local model"):
        profiler.profile("Er ist gut.", "")


def test_a_local_model_is_told_apart_by_looking_again() -> None:
    found: list[str | None] = [None]
    changes: list[str | None] = []
    local = LocalModel(probe=lambda _endpoint: found[0], on_change=changes.append)

    seen = [local.look()]
    for name in ["local/clef", "local/clef", None]:
        found[0] = name
        seen.append(local.look())

    assert seen == [None, "local/clef", "local/clef", None]
    # told only when it comes or goes
    assert changes == ["local/clef", None]


def test_a_local_model_is_looked_for_next_to_where_it_is_asked() -> None:
    asked: list[str] = []

    def probe(endpoint: str) -> str | None:
        asked.append(endpoint)
        return None

    LocalModel("http://127.0.0.1:10000/clef/v1/systemone", probe=probe).look()

    assert asked == ["http://127.0.0.1:10000/clef/v1/systemone"]


def test_the_questions_offer_several_one_or_no_errors_and_a_clarity_scale() -> None:
    assert QUESTIONS["grammar_errors"]["type"] == "choice"
    # from the worst to the best
    assert list(QUESTIONS["grammar_errors"]["criteria"]) == ["several", "one", "none"]
    assert QUESTIONS["clarity"]["type"] == "score"
    assert len(QUESTIONS["clarity"]["criteria"]) == 4
