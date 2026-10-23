# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import pymupdf
import pytest
from books import BookError
from pdfs import _line, read_pdf
from test_books import png

TEXT = (
    "Es war einmal ein Hund, der gern las. Er las jeden Tag ein Buch, und am"
    " Abend erzählte er seiner Freundin, der Katze, was er gelesen hatte. "
) * 3


def a_pdf(pages: int = 4) -> bytes:
    """A book of `pages` pages, each with the title of the book at its top
    beside a logo and its number at the bottom; a chapter starts on every
    other page, and the second has a picture. The first page ends in the
    middle of a word, which the second goes on with."""
    logo = png(80, 40, "blue")
    document = pymupdf.open()
    for number in range(pages):
        page = document.new_page(width=420, height=600)
        page.insert_text((40, 30), "Der lesende Hund", fontsize=8)
        page.insert_image(pymupdf.Rect(360, 15, 400, 35), stream=logo)
        top = 80
        if number % 2 == 0:
            page.insert_text(
                (40, top), f"Kapitel {number // 2 + 1}", fontsize=20, fontname="hebo"
            )
            top += 40
        ending = "Am Ende der Seite geht der Satz wei-" if number == 0 else ""
        page.insert_textbox(
            pymupdf.Rect(40, top, 380, top + 200), TEXT + ending, fontsize=11
        )
        if number == 1:
            page.insert_textbox(
                pymupdf.Rect(40, 40, 380, 75), "ter auf der nächsten.", fontsize=11
            )
            page.insert_image(
                pymupdf.Rect(60, 330, 360, 530), stream=png(600, 400, "green")
            )
        page.insert_text((200, 580), str(number + 1), fontsize=9)
    document.set_toc([[1, "Kapitel 1", 1], [1, "Kapitel 2", 3]])
    document.set_metadata({"title": "Der lesende Hund", "author": "Ada"})
    return bytes(document.tobytes())


def test_a_pdf_is_read_into_headings_paragraphs_and_its_pictures() -> None:
    book = read_pdf(a_pdf())

    assert (book.title, book.author) == ("Der lesende Hund", "Ada")
    assert [block.tag for block in book.blocks] == [
        "h1",
        "p",
        "p",
        "img",
        "h1",
        "p",
        "p",
    ]
    assert book.blocks[0].text == "Kapitel 1"
    assert book.blocks[0].bold and book.blocks[0].size > 1.5
    assert book.blocks[1].size == 1
    assert (book.blocks[3].width, book.blocks[3].height) == (600, 400)
    assert list(book.pictures) == [book.blocks[3].image]
    assert [(entry.title, entry.block) for entry in book.contents] == [
        ("Kapitel 1", 0),
        ("Kapitel 2", 4),
    ]
    assert book.cover is not None and book.cover[1] == "image/jpeg"


def test_what_every_page_has_in_its_margin_is_left_out() -> None:
    text = " ".join(block.text for block in read_pdf(a_pdf()).blocks)

    assert "Der lesende Hund" not in text
    assert not any(block.text.strip().isdigit() for block in read_pdf(a_pdf()).blocks)


def test_a_sentence_and_a_word_cut_at_the_end_of_a_page_go_on_on_the_next() -> None:
    blocks = read_pdf(a_pdf()).blocks

    assert blocks[1].text.endswith(
        "Am Ende der Seite geht der Satz weiter auf der nächsten."
    )
    assert blocks[2].text.startswith("Es war einmal")


def test_a_pdf_without_text_or_that_is_not_one_is_refused() -> None:
    document = pymupdf.open()
    document.new_page().insert_image(
        pymupdf.Rect(0, 0, 500, 700), stream=png(500, 700, "white")
    )

    with pytest.raises(BookError, match="scanned"):
        read_pdf(document.tobytes())
    with pytest.raises(BookError, match="not a PDF"):
        read_pdf(b"%PDF-1.7 and no more")


def test_letters_drawn_joined_are_read_apart_and_what_is_not_text_left_out() -> None:
    span = {
        "text": "Die \ufb01nale Well-\xadBeing\x08 Datei\x07.",
        "size": 11.0,
        "flags": 0,
        "font": "Times",
    }

    line = _line({"spans": [span], "bbox": (0, 0, 100, 12)})

    assert line is not None and line.text == "Die finale Well-Being  Datei ."


def test_a_pdf_called_nothing_that_is_a_name_is_called_by_its_file() -> None:
    document = pymupdf.open()
    document.new_page().insert_text((50, 100), "Die Datei.", fontsize=11)
    document.set_metadata({"title": "()"})

    assert read_pdf(document.tobytes(), "Hund").title == "Hund"


def test_a_word_cut_with_a_soft_hyphen_at_the_end_of_a_line_is_joined_again() -> None:
    document = pymupdf.open()
    page = document.new_page(width=420, height=600)
    page.insert_text((40, 100), "Es war eine lange Entwick\xad", fontsize=11)
    page.insert_text((40, 114), "lung, die nie endete.", fontsize=11)

    assert [block.text for block in read_pdf(document.tobytes()).blocks] == [
        "Es war eine lange Entwicklung, die nie endete."
    ]


def test_a_figure_drawn_of_shapes_is_a_picture_with_its_words_and_a_framed_text_is_not() -> (
    None
):
    text = "It does not mean that the machine is intelligent, or that it thinks. " * 2
    document = pymupdf.open()
    page = document.new_page(width=420, height=600)
    page.insert_textbox(pymupdf.Rect(40, 40, 380, 110), text, fontsize=11)
    for number, label in enumerate(
        ["Genetic Algorithms", "Evolutionary", "Optimisation"]
    ):
        box = pymupdf.Rect(60 + number * 110, 140, 150 + number * 110, 180)
        page.draw_rect(box)
        page.insert_textbox(box + (4, 4, -4, -4), label, fontsize=7)
        if number:
            page.draw_line((box.x0 - 20, 160), (box.x0, 160))
    page.draw_rect(pymupdf.Rect(36, 220, 384, 300))
    page.insert_textbox(pymupdf.Rect(40, 224, 380, 296), text, fontsize=11)
    page.draw_line((40, 320), (380, 320))
    page.insert_textbox(pymupdf.Rect(40, 330, 380, 400), text, fontsize=11)

    book = read_pdf(document.tobytes())

    assert [block.tag for block in book.blocks] == ["p", "img", "p", "p"]
    assert all(
        block.text.startswith("It does not") for block in book.blocks if block.text
    )
    figure = book.blocks[1]
    # drawn twice as large, with room around it
    assert figure.width > 2 * 310 and figure.height > 2 * 40
    assert list(book.pictures) == [figure.image]


def test_a_figure_on_a_page_turned_sideways_is_whole_with_its_words_however_large() -> (
    None
):
    document = pymupdf.open()
    page = document.new_page(width=420, height=600)
    page.insert_textbox(pymupdf.Rect(40, 300, 380, 500), TEXT, fontsize=11)
    page.draw_rect(pymupdf.Rect(60, 60, 200, 260))
    page.insert_text((70, 160), "Ethics", fontsize=14)
    page.insert_text((180, 268), "Law", fontsize=7)
    page.set_rotation(90)

    book = read_pdf(document.tobytes())

    pictures = [block for block in book.blocks if block.image]
    assert len(pictures) == 1
    # drawn as it is shown, with the page turned: wider than high
    assert pictures[0].width > pictures[0].height
    assert [block.text[:13] for block in book.blocks if block.text] == ["Es war einmal"]


def test_the_title_at_the_top_of_the_pages_of_a_chapter_is_left_out() -> None:
    document = pymupdf.open()
    for number in range(8):
        page = document.new_page(width=420, height=600)
        header = "Kapitel Eins" if number < 4 else "Kapitel Zwei"
        page.insert_text((40, 30), header, fontsize=8)
        page.insert_textbox(
            pymupdf.Rect(40, 80, 380, 280), f"Seite {number}. {TEXT}", fontsize=11
        )

    text = " ".join(block.text for block in read_pdf(document.tobytes()).blocks)

    assert "Kapitel" not in text
