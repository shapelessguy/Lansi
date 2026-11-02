# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

import pytest
from ocr import OcrError, page_of, read_picture, text_of


def box(x: int, y: int, wide: int, high: int = 20) -> dict[str, Any]:
    """A box as Vision gives it, `wide` and `high` from `x` and `y`."""
    return {
        "vertices": [
            {"x": x, "y": y},
            {"x": x + wide, "y": y},
            {"x": x + wide, "y": y + high},
            {"x": x, "y": y + high},
        ]
    }


def symbol(
    char: str, after: str | None = None, at: tuple[int, int] | None = None
) -> dict[str, Any]:
    """A symbol as Vision reads it, with the break `after` it, if any, ten
    pixels wide from `at`, if it is placed."""
    found: dict[str, Any] = {"text": char}
    if at:
        found["boundingBox"] = box(at[0], at[1], 10)
    if after:
        found["property"] = {"detectedBreak": {"type": after}}
    return found


def word(text: str, x: int, y: int, after: str | None = "SPACE") -> dict[str, Any]:
    """A word as Vision reads it, ten pixels wide for each letter, at `x`
    and `y`, followed by `after`."""
    last = len(text) - 1
    return {
        "boundingBox": box(x, y, 10 * len(text)),
        "confidence": 0.9,
        "symbols": [
            symbol(char, after if at == last else None, (x + 10 * at, y))
            for at, char in enumerate(text)
        ],
    }


def reading(*paragraphs: list[dict[str, Any]]) -> dict[str, Any]:
    """Vision's answer for a page of `paragraphs`, each a list of words."""
    return {
        "fullTextAnnotation": {
            "pages": [
                {"blocks": [{"paragraphs": [{"words": each} for each in paragraphs]}]}
            ]
        }
    }


def test_a_comma_goes_with_the_word_it_is_written_against() -> None:
    page = page_of(
        reading([word("Hallo", 0, 0, None), word(",", 50, 0), word("du", 70, 0)]),
        500,
        500,
    )

    assert [each.text for each in page.words] == ["Hallo,", "du"]
    assert page.words[0].box == [[0, 0], [60, 0], [60, 20], [0, 20]]


def test_each_letter_of_a_word_is_kept_with_its_box() -> None:
    page = page_of(reading([word("Hund", 0, 0, None), word(",", 40, 0)]), 500, 500)

    letters = page.words[0].kept()["letters"]
    assert [each["text"] for each in letters] == ["H", "u", "n", "d", ","]
    assert letters[2]["box"] == [[20, 0], [30, 0], [30, 20], [20, 20]]


def test_a_word_whose_letters_were_not_all_placed_keeps_none() -> None:
    read = word("Hund", 0, 0)
    del read["symbols"][1]["boundingBox"]
    page = page_of(reading([read]), 500, 500)

    assert "letters" not in page.words[0].kept()


def test_an_opening_quotation_mark_goes_with_the_word_after_it() -> None:
    page = page_of(reading([word("„", 0, 0, None), word("Ja", 10, 0)]), 500, 500)

    assert [each.text for each in page.words] == ["„Ja"]


def test_words_are_on_the_lines_they_are_written_on_and_in_their_paragraphs() -> None:
    page = page_of(
        reading(
            [word("Ich", 0, 0), word("lerne", 0, 30, "EOL_SURE_SPACE")],
            [word("Gut", 0, 60, "LINE_BREAK")],
        ),
        500,
        500,
    )

    assert [(each.line, each.paragraph) for each in page.words] == [
        (0, 0),
        (0, 0),
        (1, 1),
    ]


def test_a_box_is_kept_within_the_photo() -> None:
    page = page_of(reading([word("Weit", 480, 490)]), 500, 500)

    assert page.words[0].box[2] == [500, 500]


def test_a_page_with_nothing_written_on_it_has_no_words() -> None:
    assert page_of({}, 500, 500).words == []


def test_a_word_cut_at_the_end_of_a_line_is_joined_again_in_what_the_text_says() -> (
    None
):
    page = page_of(
        reading(
            [
                word("anzu", 0, 0, None),
                word("-", 40, 0, "HYPHEN"),
                word("sehen.", 0, 30),
            ]
        ),
        500,
        500,
    )

    assert [each.text for each in page.words] == ["anzu-", "sehen."]
    assert text_of([page.kept()]) == "anzusehen."


def test_a_paragraph_cut_in_the_middle_of_a_sentence_goes_on_with_the_next() -> None:
    page = page_of(
        reading(
            [word("zu", 0, 0), word("meinen", 30, 0, "LINE_BREAK")],
            [word("Fortschritten.", 0, 30, "LINE_BREAK")],
            [word("Tschüss!", 0, 60)],
        ),
        500,
        500,
    )

    assert text_of([page.kept()]) == "zu meinen Fortschritten.\n\nTschüss!"


def test_each_page_starts_a_paragraph_of_its_own() -> None:
    first = page_of(reading([word("Ich", 0, 0)]), 500, 500).kept()
    second = page_of(reading([word("Du", 0, 0)]), 500, 500).kept()

    assert text_of([first, second]) == "Ich\n\nDu"


def test_a_page_is_not_read_without_a_key() -> None:
    with pytest.raises(OcrError):
        read_picture(b"", 10, 10, "", "de-t-i0-handwrit")
