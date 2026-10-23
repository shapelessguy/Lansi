# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import intake as intake_module
import pytest
from intake import (
    IN_LANGUAGE,
    Intake,
    Outcome,
    Word,
    category_questions,
    read_words,
    send_chat,
)
from languages.german.test_categories import verb
from models import Model
from profiling import Answer, Profile, ProfileError, Profiler, Questions
from vocabulary import Described, Entry, Form, Rejection, Vocabularies, Vocabulary

KEY = "the-key"
MODEL = "some/chat-model"
CHAT = Model(MODEL, key=KEY)
# the usual decision model, on OpenRouter
DECIDER = Model(key=KEY)


class FakeProfiler(Profiler):
    """Sorts words into the categories it was told, in place of a decision
    model, and into nouns otherwise; and says every sentence is in the
    language but those it was told are not."""

    def __init__(
        self, categories: dict[str, str] | None = None, foreign: set[str] | None = None
    ) -> None:
        super().__init__()
        self.categories = categories or {}
        self.foreign = foreign or set()
        self.asked: list[tuple[dict[str, Any], str | None]] = []
        # the sentences it was asked whether they are in the language
        self.judged: list[str] = []
        # how much of a yes other categories are given than the one told
        self.also: dict[str, float] = {}

    def ask(
        self,
        state: dict[str, Any],
        questions: Questions,
        model: Model,
    ) -> Profile:
        if IN_LANGUAGE in questions:
            self.judged.append(state["sentence"])
            yes = 0.1 if state["sentence"] in self.foreign else 0.9
            return Profile({IN_LANGUAGE: Answer("noul", yes=yes)}, cost=0.0001)
        self.questions = questions
        self.asked.append((state, model.name or None))
        likely = {self.categories.get(state["word"], "noun"): 0.9, **self.also}
        return Profile(
            {name: Answer("noul", yes=likely.get(name, 0.1)) for name in questions},
            cost=0.0001,
            id=f"decision-{len(self.asked)}",
        )


NOT_SAVABLE = {"savable": False, "category": "", "lemma": "", "reason": "no word"}


def noun(
    article: str, singular: str, plural: str, *meanings: str
) -> dict[str, list[dict[str, object]]]:
    """The description of a noun of one variant, whose cases are all alike."""
    cases = ("nominativ", "genitiv", "dativ", "akkusativ")
    variant: dict[str, object] = {
        "article": article,
        "meanings": list(meanings),
        "singular": dict.fromkeys(cases, singular),
        "plural": dict.fromkeys(cases, plural),
    }
    return {"variants": [variant]}


def savable(category: str, lemma: str) -> dict[str, object]:
    return {"savable": True, "category": category, "lemma": lemma, "reason": ""}


class FakeChat:
    """Answers in place of a language model: with the verdict it was told
    for a word, and with the description it was told for a dictionary form."""

    def __init__(self) -> None:
        self.verdicts: dict[str, dict[str, str]] = {}
        self.descriptions: dict[str, object] = {}
        # what is answered when a word that could not be placed is asked
        # about again; a word that is not here is said not to be savable
        self.rescues: dict[str, dict[str, object]] = {}
        # the translations of each variant of a stored word, by its dictionary form
        self.translations: dict[str, list[list[str]]] = {}
        self.bodies: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def judged(
        self,
        word: str,
        verdict: str,
        lemma: str = "",
        reason: str = "",
        category: str = "",
    ) -> None:
        self.verdicts[word] = {
            "verdict": verdict,
            "lemma": lemma,
            "category": category,
            "reason": reason,
        }

    def asked_for(self, name: str) -> list[dict[str, Any]]:
        """What was given with each request for an answer of this shape."""
        return [
            json.loads(body["messages"][1]["content"])
            for body in self.bodies
            if body["response_format"]["json_schema"]["name"] == name
        ]

    def __call__(self, body: dict[str, Any], model: Model) -> dict[str, Any]:
        assert model.key == KEY
        with self._lock:
            self.bodies.append(body)
            number = len(self.bodies)
        given = json.loads(body["messages"][1]["content"])
        name = body["response_format"]["json_schema"]["name"]
        if name == "verdict":
            answer: object = self.verdicts[given["word"]]
        elif name == "rescue":
            answer = self.rescues.get(given["word"], NOT_SAVABLE)
        elif name == "translations":
            answer = {
                f"variant_{number}": translations
                for number, translations in enumerate(
                    self.translations[given["lemma"]], start=1
                )
            }
        else:
            answer = self.descriptions[given["lemma"]]
        return {
            "id": f"chat-{number}",
            "model": body["model"],
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"prompt_tokens": 200, "completion_tokens": 90, "cost": 0.003},
        }


@pytest.fixture
def vocabulary() -> Vocabulary:
    return Vocabulary()


@pytest.fixture
def profiler() -> FakeProfiler:
    return FakeProfiler(dict.fromkeys(("ging", "gehe", "gehen", "gehst"), "verb"))


@pytest.fixture
def chat() -> FakeChat:
    chat = FakeChat()
    chat.descriptions["gehen"] = verb()
    return chat


@pytest.fixture
def intake(vocabulary: Vocabulary, profiler: FakeProfiler, chat: FakeChat) -> Intake:
    return Intake(vocabulary, profiler, chat)


def take(intake: Intake, *words: str) -> list[Outcome]:
    outcomes, _ = intake.take([Word(word) for word in words], CHAT, DECIDER)
    return outcomes


def test_a_word_that_is_a_stored_form_is_known_without_asking_the_language_model(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    stored, _ = vocabulary.save("verb", "gehen", {}, [Form("ging")])

    (outcome,) = take(intake, "ging")

    assert (outcome.status, outcome.category, outcome.entry) == (
        "known",
        "verb",
        stored,
    )
    assert chat.bodies == []


def test_the_words_of_a_sentence_not_mostly_in_the_language_are_skipped(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    english = "The word ging is the past of gehen."
    profiler = FakeProfiler({"ging": "verb"}, foreign={english})
    intake = Intake(vocabulary, profiler, chat)
    vocabulary.save("verb", "gehen", {}, [Form("ging")])

    outcomes, _ = intake.take(
        [Word("ging", english), Word("gehen", english), Word("ging", "Er ging.")],
        CHAT,
        DECIDER,
    )

    assert [(each.status, each.reason) for each in outcomes] == [
        ("skipped", "its sentence is not mostly in German"),
        ("skipped", "its sentence is not mostly in German"),
        ("known", ""),
    ]
    # each sentence is asked about once, and the words of the one in another
    # language are not sorted into categories at all
    assert sorted(profiler.judged) == sorted([english, "Er ging."])
    assert [state["word"] for state, _ in profiler.asked] == ["ging"]


def test_a_sentence_is_asked_about_once_however_often_its_words_are_taken_in(
    intake: Intake, vocabulary: Vocabulary, profiler: FakeProfiler
) -> None:
    vocabulary.save("verb", "gehen", {}, [Form("ging")])

    for _ in range(2):
        intake.take([Word("ging", "Er ging.")], CHAT, DECIDER)
    intake.take([Word("ging")], CHAT, DECIDER, language="Italian")

    assert profiler.judged == ["Er ging."]


def test_the_words_of_a_sentence_that_could_not_be_asked_about_fail(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    class Unreachable(FakeProfiler):
        def ask(
            self, state: dict[str, Any], questions: Questions, model: Model
        ) -> Profile:
            if IN_LANGUAGE in questions:
                raise ProfileError("the decision model could not be reached")
            return super().ask(state, questions, model)

    intake = Intake(vocabulary, Unreachable(), chat)

    (outcome,), _ = intake.take([Word("Hund", "Der Hund.")], CHAT, DECIDER)

    assert (outcome.status, outcome.reason) == (
        "failed",
        "the decision model could not be reached",
    )


def test_a_new_word_is_stored_under_its_dictionary_form_with_all_its_forms(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("ging", "new", "gehen")

    (outcome,) = take(intake, "ging")

    assert (outcome.status, outcome.category) == ("added", "verb")
    stored = vocabulary.find("verb", "gegangen")
    assert stored is not None and stored == outcome.entry
    assert (stored.lemma, stored.variants[0].details["auxiliary"]) == ("gehen", "sein")
    assert chat.asked_for("verb") == [{"lemma": "gehen"}]
    # none of its forms needs to be asked about again
    assert [found.status for found in take(intake, "gehst", "ging", "gehen")] == [
        "known"
    ] * 3


def test_a_new_word_is_translated_into_the_language_translated_into_at_the_time(
    vocabulary: Vocabulary, profiler: FakeProfiler, chat: FakeChat
) -> None:
    intake = Intake(vocabulary, profiler, chat, into=lambda: "Italian")
    chat.judged("ging", "new", "gehen")

    (outcome,) = take(intake, "ging")

    assert outcome.entry is not None
    assert outcome.entry.variants[0].translations == {"Italian": ["to go", "to walk"]}
    assert "Write the meanings in Italian." in chat.bodies[-1]["messages"][0]["content"]


def test_a_new_word_is_stored_with_every_variant_it_was_described_with(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("Bänke", "new", "Bank")
    bank_noun = noun("die", "Bank", "Banken", "bank")
    bench_noun = noun("die", "Bank", "Bänke", "bench", "workbench")
    chat.descriptions["Bank"] = {
        "variants": bank_noun["variants"] + bench_noun["variants"]
    }

    (outcome,), _ = intake.take([Word("Bänke")], CHAT, DECIDER)

    assert outcome.entry is not None
    bank, bench = outcome.entry.variants
    assert bench.translations == {"English": ["bench", "workbench"]}
    plurals = {
        form.form: form.variant
        for form in outcome.entry.forms
        if form.tags == "die nominativ plural"
    }
    assert plurals == {"Banken": bank.id, "Bänke": bench.id}


def bank(vocabulary: Vocabulary) -> Entry:
    """die Bank, which is a bank with the plural Banken and a bench with Bänke."""
    entry, _ = vocabulary.save_variants(
        "noun",
        "Bank",
        [
            Described({}, ["bank"], [Form("Banken", "die nominativ plural")]),
            Described({}, ["bench"], [Form("Bänke", "die nominativ plural")]),
        ],
        "English",
    )
    return entry


def test_a_stored_word_is_translated_variant_by_variant(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.translations["Bank"] = [["banca"], ["panchina"]]

    translated = intake.translate("German", bank(vocabulary), "Italian", CHAT, [])

    assert [variant.translations["Italian"] for variant in translated.variants] == [
        ["banca"],
        ["panchina"],
    ]
    assert chat.asked_for("translations") == [
        {
            "lemma": "Bank",
            "variants": {
                "variant_1": {"English": ["bank"]},
                "variant_2": {"English": ["bench"]},
            },
        }
    ]
    # the answer is held to one list for each variant, by its name
    schema = chat.bodies[-1]["response_format"]["json_schema"]["schema"]
    assert schema["required"] == ["variant_1", "variant_2"]


def test_a_translation_that_is_not_of_every_variant_is_not_stored(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    stored = bank(vocabulary)
    chat.translations["Bank"] = [["banca"]]

    with pytest.raises(intake_module.IntakeError):
        intake.translate("German", stored, "Italian", CHAT, [])

    assert vocabulary.lacking_translations("Italian") == [stored.id]


def test_the_language_model_is_held_to_the_shape_of_the_category(
    intake: Intake, chat: FakeChat
) -> None:
    chat.judged("ging", "new", "gehen")

    take(intake, "ging")

    judging, describing = chat.bodies
    assert judging["model"] == describing["model"] == MODEL
    assert judging["response_format"]["json_schema"]["strict"] is True
    assert describing["response_format"]["json_schema"]["name"] == "verb"
    assert (
        "praeteritum"
        in describing["response_format"]["json_schema"]["schema"]["properties"]
    )
    assert 'category "verb"' in judging["messages"][0]["content"]
    assert "infinitive" in judging["messages"][0]["content"]


def test_a_new_word_is_judged_against_the_stored_words_spelt_most_like_it(
    intake: Intake, vocabulary: Vocabulary, profiler: FakeProfiler, chat: FakeChat
) -> None:
    for number in range(12):
        vocabulary.save("noun", f"Wort{number}", {}, [])
    vocabulary.save("noun", "Hund", {}, [], ["dog"], "English")
    vocabulary.save("verb", "hunden", {}, [])
    chat.judged("Hunds", "form", "Hund")

    take(intake, "Hunds")

    (given,) = chat.asked_for("verdict")
    assert given["word"] == "Hunds"
    assert given["candidates"][0] == {"lemma": "Hund", "meanings": ["dog"]}
    assert len(given["candidates"]) == 10
    assert "hunden" not in [candidate["lemma"] for candidate in given["candidates"]]


def test_a_word_judged_a_form_of_a_stored_word_is_added_to_its_forms(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    stored, _ = vocabulary.save("noun", "Hund", {}, [])
    chat.judged("Hunds", "form", "Hund")

    (outcome,) = take(intake, "Hunds")
    (again,) = take(intake, "Hunds")

    assert outcome.status == "form"
    assert outcome.entry is not None and outcome.entry.id == stored.id
    assert again.status == "known"
    # nothing was described, and the second time nothing was asked at all
    assert len(chat.bodies) == 1


def test_a_new_noun_is_stored_with_a_capital_letter_when_the_model_gave_none(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("hand", "new", "hand")
    chat.descriptions["Hand"] = noun("die", "hand", "hände", "hand")

    (outcome,), _ = intake.take([Word("hand", "Gib mir die hand.")], CHAT, DECIDER)

    assert outcome.status == "added"
    assert outcome.entry is not None and outcome.entry.lemma == "Hand"
    assert chat.asked_for("noun") == [{"lemma": "Hand"}]


def test_nouns_stored_without_a_capital_letter_are_given_one_and_merged_with_twins(
    profiler: FakeProfiler, chat: FakeChat
) -> None:
    vocabulary = Vocabulary()
    verb_in_small, _ = vocabulary.save("noun", "verb", {}, [Form("verbs")])
    verb, _ = vocabulary.save("noun", "Verb", {}, [])
    hand, _ = vocabulary.save("noun", "hand", {}, [])
    vocabulary.save("verb", "gehen", {}, [])

    Intake(vocabulary, profiler, chat).vocabulary  # noqa: B018

    assert vocabulary.entry("noun", "Hand") == vocabulary.get(hand.id)
    assert vocabulary.get(verb_in_small.id) is None
    merged = vocabulary.find("noun", "verbs")
    assert merged is not None and merged.id == verb.id
    assert vocabulary.entry("verb", "gehen") is not None


def test_a_word_that_cannot_be_placed_is_asked_about_again_with_what_went_wrong(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    # the model calls ging a form of gehen, which is not stored
    chat.judged("ging", "form", "gehen")
    chat.rescues["ging"] = savable("verb", "gehen")

    (outcome,) = take(intake, "ging")

    (given,) = chat.asked_for("rescue")
    assert given == {
        "word": "ging",
        "category": "verb",
        "problem": "it was judged a form of gehen, which is not a stored verb",
    }
    assert outcome.status == "added"
    assert outcome.entry is not None and outcome.entry.lemma == "gehen"
    assert outcome.reason.startswith("saved when asked again, after: it was judged")
    assert vocabulary.find("verb", "gegangen") is not None
    assert vocabulary.not_taken(["ging"]) == []


def test_a_word_saved_when_asked_again_may_go_to_another_category(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    stored, _ = vocabulary.save("adverb", "gern", {}, [])
    chat.judged("lieber", "form", "lieb")
    chat.rescues["lieber"] = savable("adverb", "gern")

    (outcome,) = take(intake, "lieber")

    assert (outcome.status, outcome.category) == ("form", "adverb")
    assert outcome.entry is not None and outcome.entry.id == stored.id
    assert vocabulary.find("adverb", "lieber") is not None


def test_a_word_found_not_savable_when_asked_again_is_rejected_for_good(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("Hunds", "form", "Hund")

    (outcome,) = take(intake, "Hunds")
    (again,) = take(intake, "Hunds")

    assert (outcome.status, outcome.reason) == ("rejected", "no word")
    assert again.status == "rejected"
    assert len(chat.asked_for("rescue")) == 1


def test_a_word_fails_when_asking_again_does_not_help_either(
    intake: Intake, chat: FakeChat
) -> None:
    chat.judged("Hunds", "form", "Hund")
    chat.rescues["Hunds"] = savable("", "")

    (outcome,) = take(intake, "Hunds")

    assert outcome.status == "failed"
    assert outcome.reason == (
        "it was judged a form of Hund, which is not a stored noun; and asked"
        " again: no category or dictionary form was given for it"
    )


def test_a_rejected_word_is_not_stored_and_not_asked_about_again(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("Hundd", "reject", reason="misspelt")

    (outcome,) = take(intake, "Hundd")
    (again,) = take(intake, "Hundd")

    assert (outcome.status, outcome.reason) == ("rejected", "misspelt")
    assert (again.status, again.reason) == ("rejected", "misspelt")
    assert vocabulary.find("noun", "Hundd") is None
    assert len(chat.bodies) == 1


def test_a_word_found_to_be_no_word_is_not_sorted_again_when_met_in_another_sentence(
    intake: Intake, profiler: FakeProfiler, chat: FakeChat
) -> None:
    chat.judged("Hundd", "reject", reason="misspelt")

    (outcome,), _ = intake.take([Word("Hundd", "Der Hundd bellt.")], CHAT, DECIDER)
    (again,), _ = intake.take([Word("hundd", "Ich sehe den hundd.")], CHAT, DECIDER)

    assert (outcome.status, outcome.reason) == ("rejected", "misspelt")
    assert (again.status, again.reason) == ("rejected", "misspelt")
    assert len(profiler.asked) == 1
    assert len(chat.bodies) == 1


def test_a_word_found_not_savable_when_asked_again_is_not_sorted_again(
    intake: Intake, profiler: FakeProfiler, chat: FakeChat
) -> None:
    chat.judged("Hunds", "form", "Hund")

    take(intake, "Hunds")
    (again,), _ = intake.take([Word("Hunds", "Des Hunds Knochen.")], CHAT, DECIDER)

    assert (again.status, again.reason) == ("rejected", "no word")
    assert len(profiler.asked) == 1


def test_a_word_found_to_be_no_word_is_still_known_when_spelt_as_a_stored_word(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    stored, _ = vocabulary.save("verb", "essen", {}, [Form("essen")])
    chat.judged("Essen", "reject", reason="for the test")
    profiler = FakeProfiler({"Essen": "noun", "essen": "verb"})
    intake = Intake(vocabulary, profiler, chat)

    take(intake, "Essen")
    (outcome,), _ = intake.take([Word("essen", "Wir essen.")], CHAT, DECIDER)

    assert (outcome.status, outcome.entry) == ("known", stored)


def test_a_word_found_to_be_of_another_category_is_taken_in_as_one_of_that(
    vocabulary: Vocabulary,
) -> None:
    class Chat(FakeChat):
        """Finds ging not to be an adjective, but a new verb."""

        def __call__(self, body: dict[str, Any], model: Model) -> dict[str, Any]:
            if 'category "adjective"' in body["messages"][0]["content"]:
                self.judged("ging", "elsewhere", category="verb")
            else:
                self.judged("ging", "new", "gehen")
            return super().__call__(body, model)

    chat = Chat()
    chat.descriptions["gehen"] = verb()
    intake = Intake(vocabulary, FakeProfiler({"ging": "adjective"}), chat)

    (outcome,) = take(intake, "ging")
    vocabulary.save("verb", "sehen", {}, [Form("sah")])
    vocabulary.reject("adjective", "sah", "", belongs_to="verb")
    intake_of_sah = Intake(vocabulary, FakeProfiler({"sah": "adjective"}), chat)
    (remembered,) = take(intake_of_sah, "sah")

    assert (outcome.status, outcome.category) == ("added", "verb")
    assert outcome.entry is not None and outcome.entry.lemma == "gehen"
    assert vocabulary.rejection("adjective", "ging") == Rejection("", "verb")
    # what was found once is gone by the next time, without asking
    assert (remembered.status, remembered.category) == ("known", "verb")
    assert len(chat.bodies) == 3


def test_a_word_sent_back_and_forth_between_categories_fails(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("ging", "elsewhere", category="verb")
    intake = Intake(vocabulary, FakeProfiler({"ging": "verb"}), chat)

    (outcome,) = take(intake, "ging")

    (given,) = chat.asked_for("rescue")
    assert given["problem"] == "it was found to be a verb and then not to be"
    assert outcome.status == "rejected"


def test_what_a_word_in_a_sentence_was_found_to_be_is_not_taken_to_hold_elsewhere(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("Essen", "elsewhere", category="other")
    chat.judged("laufen", "elsewhere", category="verb")
    intake = Intake(vocabulary, FakeProfiler({"Essen": "noun", "laufen": "noun"}), chat)

    outcomes, _ = intake.take(
        [Word("laufen", "Wir laufen."), Word("Essen")], CHAT, DECIDER
    )

    assert vocabulary.rejection("noun", "laufen") is None
    # a category that there is not is not gone by
    (about_essen,) = [
        given for given in chat.asked_for("rescue") if given["word"] == "Essen"
    ]
    assert "answer.category is not one of" in about_essen["problem"]
    assert outcomes[1].status == "rejected"


def test_a_word_of_a_kind_that_is_not_stored_is_skipped(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    intake = Intake(vocabulary, FakeProfiler({"Claudio": "name"}), chat)

    (outcome,) = take(intake, "Claudio")

    assert (outcome.status, outcome.category) == ("skipped", "name")
    assert chat.bodies == []


def test_a_stored_word_used_as_another_category_is_taken_in_again_for_that_one(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    vocabulary.save("verb", "essen", {}, [])
    chat.judged("Essen", "reject", reason="for the test")
    intake = Intake(vocabulary, FakeProfiler({"Essen": "noun"}), chat)

    (outcome,) = take(intake, "Essen")

    assert (outcome.status, outcome.category) == ("rejected", "noun")
    assert len(chat.asked_for("verdict")) == 1


def test_the_decision_model_is_given_the_sentence_a_word_was_used_in(
    intake: Intake, profiler: FakeProfiler, chat: FakeChat
) -> None:
    chat.judged("Essen", "reject")
    chat.judged("Hund", "reject")

    intake.take(
        [Word("Essen", "Das Essen ist gut."), Word("Hund")],
        CHAT,
        Model("some/decider", key=KEY),
    )

    assert sorted(profiler.asked, key=lambda asked: len(asked[0])) == [
        ({"word": "Hund"}, "some/decider"),
        ({"word": "Essen", "sentence": "Das Essen ist gut."}, "some/decider"),
    ]
    assert {"word": "Essen", "sentence": "Das Essen ist gut.", "candidates": []} in (
        chat.asked_for("verdict")
    )


def test_two_forms_of_a_new_word_taken_in_together_have_it_described_once(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("ging", "new", "gehen")
    chat.judged("gehe", "new", "gehen")

    outcomes = take(intake, "ging", "gehe")

    assert sorted(outcome.status for outcome in outcomes) == ["added", "known"]
    assert len(chat.asked_for("verb")) == 1
    assert outcomes[0].entry is not None and outcomes[1].entry is not None
    assert outcomes[0].entry.id == outcomes[1].entry.id


def test_a_word_given_twice_is_worked_on_once_and_answered_twice(
    intake: Intake, profiler: FakeProfiler, chat: FakeChat
) -> None:
    chat.judged("ging", "new", "gehen")

    outcomes = take(intake, "ging", "ging")

    assert [outcome.status for outcome in outcomes] == ["added", "added"]
    assert len(profiler.asked) == 1


def test_a_new_word_fails_without_a_key_or_a_model_but_a_known_one_does_not(
    intake: Intake, vocabulary: Vocabulary
) -> None:
    vocabulary.save("verb", "gehen", {}, [])

    without_key, _ = intake.take([Word("gehen"), Word("Hund")], Model(MODEL), DECIDER)
    without_model, _ = intake.take([Word("Hund")], Model(key=KEY), DECIDER)

    assert [outcome.status for outcome in without_key] == ["known", "failed"]
    assert "an OpenRouter key is needed" in without_key[1].reason
    assert without_model[0].status == "failed"


def test_the_model_named_when_the_intake_was_made_is_asked_if_a_request_names_none(
    vocabulary: Vocabulary, profiler: FakeProfiler, chat: FakeChat
) -> None:
    chat.judged("Hund", "reject")

    Intake(vocabulary, profiler, chat, model="usual/model").take(
        [Word("Hund")], Model(key=KEY), DECIDER
    )

    assert chat.bodies[0]["model"] == "usual/model"


def test_a_word_whose_description_is_not_of_the_shape_fails_and_is_not_stored(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("ging", "new", "gehen")
    chat.descriptions["gehen"] = verb(reflexive="maybe")
    chat.rescues["ging"] = savable("verb", "gehen")
    chat.judged("Hund", "reject")

    failed, other = take(intake, "ging", "Hund")

    assert failed.status == "failed"
    assert "answer.reflexive is not one of" in failed.reason
    assert vocabulary.find("verb", "ging") is None
    # the other words are taken in all the same
    assert other.status == "rejected"


def test_a_word_fails_when_the_decision_model_cannot_be_asked(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    class NoProfiler(FakeProfiler):
        def ask(self, *args: Any, **kwargs: Any) -> Profile:
            raise ProfileError("an OpenRouter key is needed")

    (outcome,) = take(Intake(vocabulary, NoProfiler(), chat), "Hund")

    assert (outcome.status, outcome.category) == ("failed", "")
    assert outcome.reason == "an OpenRouter key is needed"


def test_every_request_that_is_paid_for_is_reported(
    intake: Intake, chat: FakeChat
) -> None:
    chat.judged("ging", "new", "gehen")

    _, used = intake.take([Word("ging")], CHAT, DECIDER)

    assert [(request.id, request.model) for request in used] == [
        ("decision-1", ""),
        ("chat-1", MODEL),
        ("chat-2", MODEL),
    ]
    assert (used[1].input_tokens, used[1].output_tokens, used[1].cost) == (
        200,
        90,
        0.003,
    )


def test_every_category_and_what_is_not_stored_is_asked_about_at_once() -> None:
    questions = category_questions("German")
    names = list(questions)

    assert names[:4] == ["noun", "verb", "adjective", "adverb"]
    assert names[-2:] == ["name", "other"]
    assert {question["type"] for question in questions.values()} == {"noul"}
    assert "gegangen" in questions["verb"]["instructions"]


def test_a_word_in_the_dictionary_is_not_taken_for_no_word(
    vocabulary: Vocabulary, chat: FakeChat
) -> None:
    profiler = FakeProfiler({"kam": "other", "xqz": "other"})
    profiler.also = {"verb": 0.4}
    intake = Intake(vocabulary, profiler, chat, known=lambda word: word == "kam")
    chat.judged("kam", "reject")

    in_the_dictionary, not_in_it = take(intake, "kam", "xqz")

    assert in_the_dictionary.category == "verb"
    assert (not_in_it.category, not_in_it.status) == ("other", "skipped")


def test_a_word_on_its_own_in_small_letters_is_not_taken_for_a_noun_or_a_name(
    chat: FakeChat,
) -> None:
    profiler = FakeProfiler({"macht": "noun", "Macht": "noun"})
    profiler.also = {"name": 0.6, "verb": 0.4}
    for word in ("macht", "Macht"):
        chat.judged(word, "reject")

    def category(word: Word) -> str:
        # A word that is rejected is no word in any spelling, so each is
        # taken into a vocabulary of its own, as not to be rejected for
        # another that was.
        intake = Intake(Vocabulary(), profiler, chat)
        (outcome,), _ = intake.take([word], CHAT, DECIDER)
        return outcome.category

    words = [Word("macht"), Word("Macht"), Word("macht", "Die macht ist groß.")]

    assert [category(word) for word in words] == ["verb", "noun", "noun"]


def test_words_come_in_as_text_or_with_the_sentence_they_were_used_in() -> None:
    words = read_words([" Hund ", {"word": "Essen", "sentence": " Das Essen. "}])

    assert words == [Word("Hund"), Word("Essen", "Das Essen.")]


@pytest.mark.parametrize(
    "words",
    [None, [], "Hund", [3], [""], [{"sentence": "x"}], [{"word": "a", "sentence": 1}]],
)
def test_words_that_are_not_a_list_of_words_are_refused(words: object) -> None:
    with pytest.raises(ValueError):
        read_words(words)


def test_words_that_came_on_their_own_are_noted_as_taken_in_unless_they_failed(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    chat.judged("ging", "new", "gehen")
    chat.judged("Hundd", "reject", reason="misspelt")
    chat.judged("Katze", "form", "Katz")
    chat.rescues["Katze"] = savable("", "")
    chat.judged("Essen", "reject")

    intake.take(
        [Word("ging"), Word("Hundd"), Word("Katze"), Word("Essen", "Das Essen.")],
        CHAT,
        DECIDER,
    )

    assert vocabulary.not_taken(["ging", "Hundd", "Katze", "Essen"]) == [
        "Katze",
        "Essen",
    ]


def test_a_language_model_that_cannot_be_reached_is_asked_a_second_time(
    vocabulary: Vocabulary, profiler: FakeProfiler, chat: FakeChat
) -> None:
    chat.judged("Hund", "reject", reason="for the test")
    calls = 0

    def once_out_of_reach(body: dict[str, Any], model: Model) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProfileError("OpenRouter took longer than 90 seconds")
        return chat(body, model)

    (outcome,) = take(Intake(vocabulary, profiler, once_out_of_reach), "Hund")

    assert (outcome.status, calls) == ("rejected", 2)


def test_a_word_fails_when_the_language_model_cannot_be_reached_twice_running(
    vocabulary: Vocabulary, profiler: FakeProfiler
) -> None:
    def out_of_reach(body: dict[str, Any], model: Model) -> dict[str, Any]:
        raise ProfileError("OpenRouter took longer than 90 seconds")

    (outcome,) = take(Intake(vocabulary, profiler, out_of_reach), "Hund")

    assert outcome.status == "failed"
    assert outcome.reason == "OpenRouter took longer than 90 seconds"


def test_the_first_part_of_a_separated_verb_is_known_by_the_rest_of_its_sentence(
    intake: Intake, vocabulary: Vocabulary, chat: FakeChat
) -> None:
    stored, _ = vocabulary.save("verb", "anfangen", {}, [Form("fängt an")])
    profiler = FakeProfiler({"fängt": "verb"})
    intake = Intake(vocabulary, profiler, chat)

    outcomes, _ = intake.take(
        [Word("fängt", "Der Film fängt abends an.")], CHAT, DECIDER
    )

    assert (outcomes[0].status, outcomes[0].entry) == ("known", stored)
    assert chat.bodies == []


def test_the_models_are_told_which_language_the_words_are_of(
    intake: Intake, profiler: FakeProfiler, chat: FakeChat
) -> None:
    chat.judged("ging", "new", "gehen")
    chat.judged("Hunds", "form", "Hund")

    take(intake, "ging", "Hunds")

    judging, describing, rescuing = (
        next(
            body["messages"][0]["content"]
            for body in chat.bodies
            if body["response_format"]["json_schema"]["name"] == name
        )
        for name in ("verdict", "verb", "rescue")
    )
    assert profiler.questions["noun"]["instructions"].startswith("Is the German `word`")
    assert "a vocabulary of German" in judging
    assert "it is not a German word of any category" in judging
    assert "the entry of a German verb" in describing
    assert "a vocabulary of German" in rescuing
    # a word is stored in small letters unless it always has a capital
    for told in (judging, rescuing):
        assert "in small letters" in told
        assert "always has a capital letter in German" in told


def test_the_language_is_the_one_that_was_named(
    intake: Intake, profiler: FakeProfiler, chat: FakeChat
) -> None:
    intake.language = "Italian"
    chat.judged("ging", "reject")

    take(intake, "ging")

    assert profiler.questions["verb"]["instructions"].startswith(
        "Is the Italian `word`"
    )
    assert "a vocabulary of Italian" in chat.bodies[0]["messages"][0]["content"]
    assert "German" not in chat.bodies[0]["messages"][0]["content"].split("rules")[0]


def test_words_of_another_language_go_by_its_rules_into_its_own_vocabulary(
    tmp_path: Path, profiler: FakeProfiler, chat: FakeChat
) -> None:
    vocabularies = Vocabularies(tmp_path)
    intake = Intake(vocabularies, profiler, chat)
    intake.language = "French"
    chat.judged("parle", "new", "parler")
    chat.descriptions["parler"] = {
        "meanings": ["to speak"],
        "forms": [{"form": "parle", "tags": "present 1st singular"}],
    }
    profiler.categories["parle"] = "verb"

    (outcome,) = take(intake, "parle")

    describing = chat.bodies[-1]
    assert outcome.status == "added"
    assert "the entry of a French verb" in describing["messages"][0]["content"]
    assert list(
        describing["response_format"]["json_schema"]["schema"]["properties"]
    ) == [
        "meanings",
        "forms",
    ]
    assert vocabularies.of("French").find("verb", "parle") is not None
    assert vocabularies.of("German").find("verb", "parlo") is None


def test_a_small_letter_rules_out_a_noun_only_where_nouns_have_capitals(
    tmp_path: Path, chat: FakeChat
) -> None:
    profiler = FakeProfiler({"cane": "noun"})
    profiler.also = {"verb": 0.4}
    intake = Intake(Vocabularies(tmp_path), profiler, chat)
    chat.judged("cane", "reject")

    (in_german,) = take(intake, "cane")
    intake.language = "Italian"
    (in_italian,) = take(intake, "cane")

    assert (in_german.category, in_italian.category) == ("verb", "noun")


def test_words_stay_of_the_language_they_came_in_as_though_it_is_changed_meanwhile(
    tmp_path: Path, profiler: FakeProfiler
) -> None:
    vocabularies = Vocabularies(tmp_path)
    profiler.categories["ging"] = "verb"

    class Switching(FakeChat):
        """Has the language changed while the word is being judged."""

        def __call__(self, body: dict[str, Any], model: Model) -> dict[str, Any]:
            taking.language = "Arabic"
            return super().__call__(body, model)

    chat = Switching()
    chat.judged("ging", "new", "gehen")
    chat.descriptions["gehen"] = verb()
    taking = Intake(vocabularies, profiler, chat)

    (outcome,) = take(taking, "ging")

    describing = chat.bodies[-1]["messages"][0]["content"]
    assert (outcome.status, taking.language) == ("added", "Arabic")
    assert "the entry of a German verb" in describing
    assert vocabularies.of("German").find("verb", "gegangen") is not None
    assert vocabularies.of("German").not_taken(["ging"]) == []
    assert not vocabularies.has("Arabic")


# reasoning


def test_a_chat_model_is_asked_to_answer_without_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []

    def answering(url: str, body: dict[str, Any], *rest: Any) -> dict[str, Any]:
        sent.append(body)
        return {}

    monkeypatch.setattr(intake_module, "post", answering)

    send_chat({"messages": []}, CHAT)
    send_chat({"messages": [], "reasoning": {"effort": "high"}}, CHAT)

    assert [body["reasoning"] for body in sent] == [
        {"enabled": False},
        {"effort": "high"},
    ]


def test_a_model_that_cannot_but_reason_is_asked_again_as_the_request_was(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, Any]] = []

    def refusing(url: str, body: dict[str, Any], *rest: Any) -> dict[str, Any]:
        sent.append(body)
        if "reasoning" in body:
            raise ProfileError(
                "OpenRouter refused the request (400): reasoning is mandatory"
            )
        return {"answered": True}

    monkeypatch.setattr(intake_module, "post", refusing)

    assert send_chat({"messages": []}, CHAT) == {"answered": True}
    assert ["reasoning" in body for body in sent] == [True, False]
