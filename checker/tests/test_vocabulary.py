# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import vocabulary as vocabulary_module
from vocabulary import Described, Form, Listed, Rejection, Vocabularies, Vocabulary


@pytest.fixture
def vocabulary() -> Vocabulary:
    return Vocabulary()


def test_a_word_is_found_by_any_of_its_forms_however_it_is_capitalised(
    vocabulary: Vocabulary,
) -> None:
    saved, _ = vocabulary.save(
        "verb", "gehen", {"auxiliary": "sein"}, [Form("ging", "präteritum ich")]
    )

    found = vocabulary.find("verb", "Ging")

    assert found == saved
    assert (found.lemma, found.variants[0].details) == ("gehen", {"auxiliary": "sein"})


def test_a_word_is_found_by_its_dictionary_form_though_it_was_not_among_the_forms(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("verb", "gehen", {}, [Form("ging")])

    found = vocabulary.find("verb", "gehen")

    assert found is not None
    assert [form.form for form in found.forms] == ["ging", "gehen"]


def test_a_word_is_not_found_in_a_category_it_was_not_stored_in(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("verb", "essen", {}, [])

    assert vocabulary.find("noun", "Essen") is None


def test_words_that_differ_by_a_sharp_s_are_not_taken_for_each_other(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("noun", "Masse", {}, [])

    assert vocabulary.find("noun", "Maße") is None


def test_a_form_of_two_words_finds_the_one_it_is_the_dictionary_form_of(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("verb", "sein", {}, [Form("wäre")])
    vocabulary.save("verb", "wären", {}, [Form("sein")])
    vocabulary.save("verb", "waren", {}, [])

    found = vocabulary.find("verb", "sein")

    assert found is not None and found.lemma == "sein"


def test_saving_a_stored_word_again_adds_the_forms_it_lacks_and_keeps_the_rest(
    vocabulary: Vocabulary,
) -> None:
    first, new = vocabulary.save("verb", "gehen", {"auxiliary": "sein"}, [Form("ging")])

    again, new_again = vocabulary.save(
        "verb", "gehen", {"auxiliary": "haben"}, [Form("ging"), Form("gehst")]
    )

    assert (new, new_again) == (True, False)
    assert again.id == first.id
    assert again.variants[0].details == {"auxiliary": "sein"}
    assert [form.form for form in again.forms] == ["ging", "gehen", "gehst"]


def test_one_spelling_is_stored_once_for_each_form_it_is(
    vocabulary: Vocabulary,
) -> None:
    entry, _ = vocabulary.save(
        "verb",
        "gehen",
        {},
        [Form("gehen", "präsens wir"), Form("gehen", "präsens sie")],
    )

    tags = [form.tags for form in entry.forms]

    assert tags == ["präsens wir", "präsens sie"]
    # each has a number of its own, for what is kept about it later
    assert len({form.id for form in entry.forms}) == 2


def test_the_closest_words_are_those_of_the_category_spelt_most_alike_first(
    vocabulary: Vocabulary,
) -> None:
    for lemma in ("kaufen", "sein", "laufen"):
        vocabulary.save("verb", lemma, {}, [])
    vocabulary.save("noun", "Laufen", {}, [])

    closest = vocabulary.closest("verb", "Laufe", count=2)

    assert [(entry.category, entry.lemma) for entry in closest] == [
        ("verb", "laufen"),
        ("verb", "kaufen"),
    ]


def test_a_rejected_word_is_remembered_with_the_reason_for_its_category_only(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.reject("noun", "Hundd", "misspelt")

    vocabulary.reject("noun", "lief", "", belongs_to="verb")

    assert vocabulary.rejection("noun", "hundd") == Rejection("misspelt")
    assert vocabulary.rejection("noun", "Lief") == Rejection("", "verb")
    assert vocabulary.rejection("verb", "Hundd") is None
    assert vocabulary.rejection("noun", "Hund") is None


def test_a_discarded_word_is_remembered_with_the_reason_however_it_is_capitalised(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.discard("Hundd", "misspelt")

    assert vocabulary.discarded("hundd") == "misspelt"
    assert vocabulary.discarded("Hund") is None
    assert vocabulary.rejection("noun", "Hundd") is None


def test_a_discarded_word_is_not_taken_for_no_word_once_it_is_spelt_as_a_stored_one(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.discard("Essen", "for the test")
    vocabulary.discard("ging", "for the test")

    vocabulary.save("verb", "essen", {}, [])
    vocabulary.save("verb", "gehen", {}, [Form("ging")])

    assert vocabulary.discarded("Essen") is None
    assert vocabulary.discarded("ging") is None


def test_the_words_are_still_there_when_the_file_is_opened_again(
    tmp_path: Path,
) -> None:
    path = tmp_path / "data" / "vocabulary.db"
    first = Vocabulary(path)
    first.save("noun", "Hund", {}, [Form("Hunde", "der nominativ plural")])
    first.close()

    found = Vocabulary(path).find("noun", "hunde")

    assert found is not None and found.lemma == "Hund"


def test_the_words_are_listed_by_category_and_alphabet_with_how_many_forms_each_has(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("verb", "sehen", {}, [Form("sah"), Form("sieht")])
    hund, _ = vocabulary.save("noun", "Hund", {}, [])
    vocabulary.save("noun", "Apfel", {}, [Form("Äpfel")])

    listed = vocabulary.listing()

    assert [(word.category, word.lemma, word.forms) for word in listed] == [
        ("noun", "Apfel", 2),
        ("noun", "Hund", 1),
        ("verb", "sehen", 3),
    ]
    assert Listed(hund.id, "noun", "Hund", hund.created_at, 1) in listed


def test_a_word_is_got_by_its_number_with_all_that_is_stored_of_it(
    vocabulary: Vocabulary,
) -> None:
    saved, _ = vocabulary.save("verb", "sehen", {"auxiliary": "haben"}, [Form("sah")])

    got = vocabulary.get(saved.id)

    assert got == saved
    assert got is not None and got.created_at != ""
    assert vocabulary.get(saved.id + 1) is None


def test_the_words_that_were_never_taken_in_are_told_from_those_that_were(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.note_taken("Hund", "added")
    vocabulary.note_taken("Claudio", "skipped")

    new = vocabulary.not_taken(["hund", "Katze", "Claudio", "gehen", "Katze"])

    assert new == ["Katze", "gehen"]


def test_a_file_of_an_older_version_is_brought_up_to_date(tmp_path: Path) -> None:
    path = tmp_path / "vocabulary.db"
    old = sqlite3.connect(path)
    old.executescript(vocabulary_module._SCHEMA_STEPS[0])
    old.execute("INSERT INTO entries (category, lemma) VALUES ('noun', 'Hund')")
    old.execute("PRAGMA user_version = 1")
    old.commit()
    old.close()

    vocabulary = Vocabulary(path)
    vocabulary.note_taken("Hund", "added")

    assert vocabulary.entry("noun", "Hund") is not None
    assert vocabulary.not_taken(["Hund", "Katze"]) == ["Katze"]


def older(path: Path, version: int, *statements: str) -> None:
    """A file of that version of the tables, with what `statements` put in."""
    old = sqlite3.connect(path)
    for step in vocabulary_module._SCHEMA_STEPS[:version]:
        old.executescript(step)
    for statement in statements:
        old.execute(statement)
    old.execute(f"PRAGMA user_version = {version}")
    old.commit()
    old.close()


def test_a_word_kept_with_its_meanings_in_its_details_becomes_one_variant(
    tmp_path: Path,
) -> None:
    older(
        tmp_path / "vocabulary.db",
        4,
        "INSERT INTO entries (category, lemma, details) VALUES"
        """ ('verb', 'gehen', '{"meanings": ["to go"], "auxiliary": "sein"}')""",
        "INSERT INTO forms (entry_id, form, folded, tags)"
        " VALUES (1, 'ging', 'ging', 'präteritum ich')",
    )

    entry = Vocabulary(tmp_path / "vocabulary.db").entry("verb", "gehen")

    assert entry is not None
    (variant,) = entry.variants
    assert variant.details == {"auxiliary": "sein"}
    assert variant.translations == {"English": ["to go"]}
    assert [form.variant for form in entry.forms] == [variant.id]


def test_each_sense_a_word_was_kept_by_becomes_a_variant_with_its_forms(
    tmp_path: Path,
) -> None:
    older(
        tmp_path / "vocabulary.db",
        5,
        "INSERT INTO entries (category, lemma) VALUES ('noun', 'Band')",
        "INSERT INTO meanings VALUES (1, 'der', 'English', '[\"volume\"]')",
        "INSERT INTO meanings VALUES (1, 'das', 'English', '[\"ribbon\"]')",
        "INSERT INTO forms (entry_id, form, folded, tags)"
        " VALUES (1, 'Bände', 'bände', 'der nominativ plural'),"
        " (1, 'Bänder', 'bänder', 'das nominativ plural'), (1, 'band', 'band', '')",
    )

    entry = Vocabulary(tmp_path / "vocabulary.db").entry("noun", "Band")

    assert entry is not None
    der, das = entry.variants
    assert (der.translations, das.translations) == (
        {"English": ["volume"]},
        {"English": ["ribbon"]},
    )
    by_form = {form.form: form.variant for form in entry.forms}
    assert by_form == {"Bände": der.id, "Bänder": das.id, "band": 0}


def test_a_word_is_stored_with_the_translations_of_each_of_its_variants(
    vocabulary: Vocabulary,
) -> None:
    bank, _ = vocabulary.save_variants(
        "noun",
        "Bank",
        [
            Described({}, ["bank"], [Form("Banken", "die nominativ plural")]),
            Described({}, ["bench"], [Form("Bänke", "die nominativ plural")]),
        ],
        "English",
    )

    vocabulary.set_translations(bank.id, "Italian", [["banca"], ["panca"]])
    bank = vocabulary.set_translations(bank.id, "Italian", [["banca"], ["panchina"]])

    assert [variant.translations for variant in bank.variants] == [
        {"English": ["bank"], "Italian": ["banca"]},
        {"English": ["bench"], "Italian": ["panchina"]},
    ]
    of_the_bank, of_the_bench = (form for form in bank.forms if form.tags)
    assert (of_the_bank.variant, of_the_bench.variant) == (
        bank.variants[0].id,
        bank.variants[1].id,
    )
    assert bank.shown_in("German") == "English"
    assert bank.translations_into("Italian") == ["banca", "panchina"]


def test_the_translations_of_a_word_are_stored_only_for_every_variant(
    vocabulary: Vocabulary,
) -> None:
    hund, _ = vocabulary.save("noun", "Hund", {}, [], ["dog"], "English")

    with pytest.raises(ValueError, match="every variant"):
        vocabulary.set_translations(hund.id, "Italian", [["cane"], ["altro"]])


def test_the_words_without_translations_in_a_language_are_those_lacking_them(
    vocabulary: Vocabulary,
) -> None:
    hund, _ = vocabulary.save("noun", "Hund", {}, [], ["dog"], "English")
    katze, _ = vocabulary.save("noun", "Katze", {}, [], ["gatto"], "Italian")
    leer, _ = vocabulary.save("adjective", "leer", {}, [])

    assert vocabulary.lacking_translations("Italian") == [hund.id, leer.id]
    assert vocabulary.lacking_translations("English") == [katze.id, leer.id]


def test_a_word_merged_into_its_twin_gives_it_its_forms_as_forms_of_the_whole(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("noun", "hund", {}, [Form("hunden", "der dativ plural")], ["hound"])
    vocabulary.save(
        "noun", "Hund", {}, [Form("Hunde", "der nominativ plural")], ["dog"]
    )

    vocabulary.respell("noun", lambda lemma: lemma.capitalize())

    merged = vocabulary.entry("noun", "Hund")
    assert merged is not None
    (variant,) = merged.variants
    assert {form.form: form.variant for form in merged.forms} == {
        "Hunde": variant.id,
        "Hund": 0,
        "hunden": 0,
        "hund": 0,
    }


def test_the_first_part_of_a_separated_verb_is_found_when_the_rest_comes_later(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("verb", "ankommen", {}, [Form("kommt an", "präsens er")])
    anfangen, _ = vocabulary.save(
        "verb", "anfangen", {}, [Form("fängt an", "präsens er"), Form("zu fangen")]
    )
    vocabulary.save("verb", "vorkommen", {}, [Form("kommt vor", "präsens er")])

    in_two_parts = vocabulary.find("verb", "Fängt", "Fängt der Film abends an?")
    of_the_other_verb = vocabulary.find("verb", "kommt", "Das kommt selten vor.")

    assert in_two_parts == anfangen
    assert of_the_other_verb is not None and of_the_other_verb.lemma == "vorkommen"


def test_the_first_part_of_a_separated_verb_is_not_found_without_the_rest(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("verb", "anfangen", {}, [Form("fängt an", "präsens er")])

    assert vocabulary.find("verb", "fängt") is None
    assert vocabulary.find("verb", "fängt", "Er fängt den Ball.") is None
    # the other part has to come after the word, not before it
    assert vocabulary.find("verb", "fängt", "An dem Tag fängt er nichts.") is None
    assert vocabulary.find("noun", "fängt", "Der Film fängt abends an.") is None


def test_a_word_that_is_a_form_as_it_is_comes_before_one_that_is_part_of_a_form(
    vocabulary: Vocabulary,
) -> None:
    vocabulary.save("verb", "anfangen", {}, [Form("fängt an", "präsens er")])
    fangen, _ = vocabulary.save("verb", "fangen", {}, [Form("fängt", "präsens er")])

    assert vocabulary.find("verb", "fängt", "Der Film fängt abends an.") == fangen


def test_each_language_has_a_vocabulary_of_its_own_in_a_file_of_its_own(
    tmp_path: Path,
) -> None:
    vocabularies = Vocabularies(tmp_path / "data")

    vocabularies.of("German").save("noun", "Hund", {}, [])
    vocabularies.of("Italian").save("noun", "cane", {}, [])

    assert vocabularies.of("german") is vocabularies.of("German ")
    assert vocabularies.has("Italian") and not vocabularies.has("French")
    assert vocabularies.of("German").find("noun", "cane") is None
    assert vocabularies.of("Italian").find("noun", "cane") is not None
    assert sorted(path.name for path in (tmp_path / "data").iterdir()) == [
        "vocabulary.german.db",
        "vocabulary.italian.db",
    ]
    assert vocabularies.path_of("Brazilian Portuguese").name == (
        "vocabulary.brazilian-portuguese.db"
    )


def test_the_vocabulary_kept_before_there_was_one_for_each_language_is_german(
    tmp_path: Path,
) -> None:
    before = Vocabulary(tmp_path / "vocabulary.db")
    before.save("noun", "Hund", {}, [])
    before.close()

    vocabularies = Vocabularies(tmp_path)

    assert vocabularies.of("Italian").find("noun", "Hund") is None
    assert vocabularies.of("German").find("noun", "Hund") is not None
    assert not (tmp_path / "vocabulary.db").exists()


def test_a_set_of_words_comes_back_as_it_was_kept(vocabulary: Vocabulary) -> None:
    travel = {"id": "set-1", "name": "Travel", "rule": {"minUsed": 2}, "added": [4]}

    vocabulary.save_set("set-1", travel)
    vocabulary.save_set("set-2", {"id": "set-2", "name": "Verbs"})
    vocabulary.save_set("set-1", {**travel, "added": [4, 9]})

    assert vocabulary.sets() == [
        {"id": "set-2", "name": "Verbs"},
        {**travel, "added": [4, 9]},
    ]


def test_a_deleted_set_is_gone(vocabulary: Vocabulary) -> None:
    vocabulary.save_set("set-1", {"id": "set-1", "name": "Travel"})

    vocabulary.delete_set("set-1")

    assert vocabulary.sets() == []


@pytest.mark.parametrize(
    "body",
    [{"id": "set-1"}, {"id": "set-1", "name": " "}, {"id": "other", "name": "Travel"}],
)
def test_a_set_without_a_name_or_under_another_id_is_not_kept(
    vocabulary: Vocabulary, body: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        vocabulary.save_set("set-1", body)


def test_an_entry_respelt_as_another_is_merged_into_it_with_its_uses_and_sets(
    vocabulary: Vocabulary,
) -> None:
    small, _ = vocabulary.save("noun", "verb", {}, [Form("verbs")])
    capital, _ = vocabulary.save("noun", "Verb", {}, [])
    hand, _ = vocabulary.save("noun", "hand", {}, [])
    vocabulary.record_uses("message", "chat", 0, "user", 1.0, [(small.id, "verbs")])
    vocabulary.save_set("s", {"id": "s", "name": "S", "added": [small.id, capital.id]})

    vocabulary.respell("noun", str.capitalize)

    assert vocabulary.get(small.id) is None
    assert [listed.lemma for listed in vocabulary.listing()] == ["Hand", "Verb"]
    assert vocabulary.get(hand.id) == vocabulary.entry("noun", "Hand")
    assert vocabulary.find("noun", "verbs") == vocabulary.get(capital.id)
    assert vocabulary.uses_of(capital.id) == [("verbs", "user", 1.0)]
    assert vocabulary.sets()[0]["added"] == [capital.id]


def test_the_listing_says_when_the_learner_and_a_model_last_used_each_word(
    vocabulary: Vocabulary,
) -> None:
    hund, _ = vocabulary.save("noun", "Hund", {}, [])
    vocabulary.record_uses("message", "chat", 0, "user", 1.0, [(hund.id, "hund")])
    vocabulary.record_uses("message", "chat", 1, "assistant", 5.0, [(hund.id, "hund")])
    vocabulary.record_uses("message", "chat", 2, "user", 3.0, [(hund.id, "hund")])

    (listed,) = vocabulary.listing()

    assert (listed.last_used_by_user, listed.last_used_by_assistant) == (3.0, 5.0)
    assert (listed.first_used, listed.last_used) == (1.0, 5.0)


def test_the_entries_having_a_word_as_a_form_are_found_whatever_its_capitals(
    vocabulary: Vocabulary,
) -> None:
    hund, _ = vocabulary.save("noun", "Hund", {}, [Form("Hunde")])
    gehen, _ = vocabulary.save("verb", "gehen", {}, [Form("ging")])
    vocabulary.save("verb", "sehen", {}, [])

    assert vocabulary.having_forms(["hunde", "GING", "Katze"]) == {hund.id, gehen.id}


def test_words_spelt_alike_share_their_uses_whatever_their_category(
    vocabulary: Vocabulary,
) -> None:
    article, _ = vocabulary.save("article", "der", {}, [])
    pronoun, _ = vocabulary.save("pronoun", "der", {}, [Form("dessen")])
    vocabulary.save("noun", "Hund", {}, [])
    vocabulary.record_uses("message", "c", 0, "user", 1.0, [(article.id, "der")])
    vocabulary.record_uses(
        "message", "c", 1, "assistant", 5.0, [(pronoun.id, "dessen")]
    )

    listed = {word.category: word for word in vocabulary.listing()}

    for category in ("article", "pronoun"):
        word = listed[category]
        assert (word.used, word.seen, word.first_used, word.last_used) == (
            1,
            1,
            1.0,
            5.0,
        )
        assert (word.last_used_by_user, word.last_used_by_assistant) == (1.0, 5.0)
    assert (listed["noun"].used, listed["noun"].last_used) == (0, None)
