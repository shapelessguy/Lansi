# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import hashlib
import io
import zipfile
from typing import Any

from books import read_epub
from exporting import write_epub
from test_books import png

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32


def a_book(**more: Any) -> dict[str, Any]:
    return {
        "id": "b1",
        "title": "Der Hund",
        "author": "Ada",
        "language": "de",
        "blocks": [
            {"text": "Kapitel 1", "size": 2, "tag": "h1"},
            {"text": "Es war einmal ein Hund & eine Katze.", "size": 1},
            {"text": "Siehe Kapitel 2.", "size": 1, "links": [[6, 15, 3]]},
            {"text": "Kapitel 2", "size": 2, "tag": "h1"},
            {"text": "Ende <gut>.", "size": 1, "italic": True},
        ],
        "contents": [
            {"title": "Kapitel 1", "block": 0},
            {"title": "Kapitel 2", "block": 3},
        ],
        "landmarks": [],
        **more,
    }


def test_a_book_written_as_an_epub_is_read_back_as_it_was() -> None:
    read = read_epub(write_epub(a_book(), (PNG, "image/png")))

    assert (read.title, read.author, read.language) == ("Der Hund", "Ada", "de")
    assert [block.text for block in read.blocks] == [
        "Kapitel 1",
        "Es war einmal ein Hund & eine Katze.",
        "Siehe Kapitel 2.",
        "Kapitel 2",
        "Ende <gut>.",
    ]
    assert [block.tag for block in read.blocks] == ["h1", "p", "p", "h1", "p"]
    assert read.blocks[2].links == [(6, 15, 3)]
    assert read.blocks[4].italic
    assert [(entry.title, entry.block) for entry in read.contents] == [
        ("Kapitel 1", 0),
        ("Kapitel 2", 3),
    ]
    assert read.cover == (PNG, "image/png")


def test_an_epub_starts_with_its_kind_of_file_uncompressed() -> None:
    archive = zipfile.ZipFile(io.BytesIO(write_epub(a_book())))

    first = archive.infolist()[0]
    assert (first.filename, first.compress_type) == ("mimetype", zipfile.ZIP_STORED)
    assert archive.read("mimetype") == b"application/epub+zip"


def test_a_version_is_named_with_what_it_is_called_and_listed_by_its_sections() -> None:
    book = a_book(contents=[], version={"name": "Nur Text", "kind": "stripped"})

    read = read_epub(write_epub(book))

    assert read.title == "Der Hund (Nur Text)"
    assert [(entry.title, entry.block) for entry in read.contents] == [
        ("Kapitel 1", 0),
        ("Kapitel 2", 3),
    ]


def test_the_pictures_in_the_text_are_written_where_they_were() -> None:
    picture = png(300, 200)
    picture_id = hashlib.sha256(picture).hexdigest()[:24] + ".png"
    shown = {"text": "", "size": 1, "tag": "img", "image": picture_id}
    gone = {**shown, "image": "cd" * 12 + ".png"}
    book = a_book()
    book["blocks"] = [
        *book["blocks"][:2],
        {**shown, "alt": "Ein Hund"},
        gone,
        *book["blocks"][2:],
    ]
    book["contents"] = [{"title": "Kapitel 1", "block": 0}]

    read = read_epub(
        write_epub(book, picture=lambda id: picture if id == shown["image"] else None)
    )

    assert [block.image or block.text for block in read.blocks] == [
        "Kapitel 1",
        "Es war einmal ein Hund & eine Katze.",
        shown["image"],
        "Siehe Kapitel 2.",
        "Kapitel 2",
        "Ende <gut>.",
    ]
    assert (read.blocks[2].alt, read.blocks[2].width) == ("Ein Hund", 300)
    assert read.pictures == {shown["image"]: picture}
