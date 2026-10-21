# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest
from models import Model
from profiling import (
    QUESTIONS,
    Answer,
    Profile,
    ProfileError,
    Profiler,
    WordRating,
    describe_assessment,
    doubt_about,
    post,
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


KEYED = Model(key="the-key")


def test_profile_sends_the_sentence_and_every_question_to_the_model() -> None:
    sent: list[tuple[dict[str, Any], Model]] = []

    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
        sent.append((body, model))
        return response()

    profile = Profiler("some/model", send).profile("Er ist gut.", KEYED)

    assert sent == [
        (
            {
                "model": "some/model",
                "state": {"sentence": "Er ist gut."},
                "questions": QUESTIONS,
            },
            Model("some/model", key="the-key"),
        )
    ]
    assert profile.answers["grammar_errors"].choice == "one"


def test_profile_asks_the_model_it_is_given_instead_of_the_usual_one() -> None:
    asked: list[str] = []

    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
        asked.append(body["model"])
        return response()

    profiler = Profiler("usual/model", send)
    profiler.profile("Er ist gut.", Model("other/model", key="the-key"))
    profiler.profile("Er ist gut.", KEYED)

    assert asked == ["other/model", "usual/model"]


POLITE = {
    "type": "choice",
    "instructions": "Is the sentence polite?",
    "criteria": {"yes": "It is polite.", "no": "It is not polite."},
}


def test_profile_asks_the_questions_it_is_given_and_reads_their_answers() -> None:
    asked: list[Any] = []

    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
        asked.append(body["questions"])
        return {"answers": {"polite": {"type": "choice", "choice": "yes"}}}

    profile = Profiler(send=send).profile(
        "Er ist gut.", KEYED, questions={"polite": POLITE}
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

    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
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
        "Ich habe, Hund.", assessment, KEYED
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


def test_rate_words_gives_the_model_the_correction_of_the_sentence_if_there_is_one() -> (
    None
):
    sent: list[dict[str, Any]] = []

    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
        sent.append(body)
        answers = {f"w{n}": {"type": "noul", "noul": 0.5} for n in range(1, 5)}
        return {"id": "gen-dec-3", "answers": answers}

    Profiler("some/model", send).rate_words(
        "Ich habe ein Hund.", [], KEYED, "Ich habe einen Hund."
    )

    assert sent[0]["state"] == {
        "sentence": "Ich habe ein Hund.",
        "correction": "Ich habe einen Hund.",
        "assessment": [],
    }


def test_rate_words_fails_when_a_word_is_not_given_a_value() -> None:
    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
        return {"answers": {"w1": {"type": "noul", "noul": "yes"}}}

    with pytest.raises(ProfileError, match="w1 is not a yes or a no"):
        Profiler(send=send).rate_words("Hund.", [], KEYED)


def test_rate_words_fails_for_a_sentence_without_words() -> None:
    with pytest.raises(ProfileError):
        Profiler(send=lambda body, model: {}).rate_words("...", [], KEYED)


def test_an_assessment_gives_each_question_with_its_answer_in_words() -> None:
    answers = {
        "grammar_errors": Answer("choice", choice="one", confidence=0.6),
        "clarity": Answer("score", score=2.6, max_score=3),
    }

    assert describe_assessment(QUESTIONS, answers) == [
        {
            "question": QUESTIONS["grammar_errors"]["instructions"],
            "answer": "one: " + QUESTIONS["grammar_errors"]["criteria"]["one"],
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


# a model at an address of the learner's own

LOCAL = Model("local/clef", "http://127.0.0.1:10000/v1")


def test_a_model_at_an_address_is_asked_there_without_an_openrouter_key() -> None:
    sent: list[Model] = []

    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
        sent.append(model)
        # as a server of one's own may answer: no id and no cost
        return {
            "model": "local/clef",
            "answers": response()["answers"],
            "usage": {"input_tokens": 292, "output_tokens": 0},
        }

    profile = Profiler("some/model", send).profile("Er ist gut.", LOCAL)

    assert sent == [LOCAL]
    assert (profile.model, profile.cost) == ("local/clef", None)
    assert profile.answers["grammar_errors"].choice == "one"


def test_a_model_on_openrouter_is_not_asked_without_a_key() -> None:
    with pytest.raises(ProfileError, match="OpenRouter key is needed"):
        Profiler(send=lambda body, model: response()).profile("Er ist gut.", Model())


def test_requests_to_a_model_at_an_address_are_sent_one_after_another() -> None:
    sending = 0
    most_at_once = 0

    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
        nonlocal sending, most_at_once
        sending += 1
        most_at_once = max(most_at_once, sending)
        time.sleep(0.02)
        sending -= 1
        return response()

    profiler = Profiler(send=send)
    threads = [
        threading.Thread(target=profiler.profile, args=("Er ist gut.", LOCAL))
        for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert most_at_once == 1


def test_the_questions_offer_several_one_or_no_errors_and_a_clarity_scale() -> None:
    assert QUESTIONS["grammar_errors"]["type"] == "choice"
    # from the worst to the best
    assert list(QUESTIONS["grammar_errors"]["criteria"]) == ["several", "one", "none"]
    assert QUESTIONS["clarity"]["type"] == "score"
    assert len(QUESTIONS["clarity"]["criteria"]) == 4


class Trickling(BaseHTTPRequestHandler):
    """Answers with an object, a little at a time, as OpenRouter does while
    a slow model is writing."""

    def do_POST(self) -> None:
        self.send_response(200)
        self.end_headers()
        try:
            for _ in range(20):
                self.wfile.write(b" ")
                self.wfile.flush()
                time.sleep(0.02)
            self.wfile.write(b'{"done": true}')
        except OSError:
            # whoever asked has given up
            pass

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def trickling() -> Any:
    server = HTTPServer(("127.0.0.1", 0), Trickling)
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
    )
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_a_response_that_keeps_coming_is_given_up_on_after_the_time_it_is_given(
    trickling: str,
) -> None:
    with pytest.raises(ProfileError, match="the model took longer than 0 seconds"):
        post(trickling, {}, {}, "the model", timeout=5, within=0.1)


def test_a_response_that_comes_in_pieces_within_its_time_is_read_whole(
    trickling: str,
) -> None:
    assert post(trickling, {}, {}, "the model", timeout=5, within=5) == {"done": True}


def test_the_model_is_told_the_language_being_studied_once_it_is_known() -> None:
    sent: list[dict[str, Any]] = []

    def send(body: dict[str, Any], model: Model) -> dict[str, Any]:
        sent.append(body)
        return {"answers": {"polite": {"type": "choice", "choice": "yes"}}}

    questions = {
        "polite": {
            "type": "choice",
            "instructions": "?",
            "criteria": {"no": "", "yes": ""},
        }
    }
    profiler = Profiler(send=send)

    profiler.profile("Wie geht es?", KEYED, questions=questions)
    profiler.language = "German"
    profiler.profile("Wie geht es?", KEYED, questions=questions)

    assert [body["state"] for body in sent] == [
        {"sentence": "Wie geht es?"},
        {"sentence": "Wie geht es?", "language": "German"},
    ]
