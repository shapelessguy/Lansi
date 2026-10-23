# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from typing import Any

from sections import Section, headings, outline


def text(words: str = "Es war einmal ein Hund, der gern las.") -> dict[str, Any]:
    return {"text": words, "size": 1}


def heading(words: str, tag: str = "h2", size: float = 1.5) -> dict[str, Any]:
    return {"text": words, "size": size, "tag": tag, "bold": True}


def titles(sections: list[Section]) -> list[Any]:
    """The sections as their titles with where each starts and ends, and
    those under each."""
    return [
        (section.title, section.start, section.end, titles(section.sections))
        if section.sections
        else (section.title, section.start, section.end)
        for section in sections
    ]


def test_a_block_is_a_heading_by_its_element_its_size_or_being_bold_and_short() -> None:
    blocks = [
        {"text": "Kapitel 1", "size": 1, "italic": True},
        {"text": "Größer", "size": 1.3},
        {"text": "Anhang zu Kapitel 1", "size": 1, "bold": True},
        {"text": "Nicht ganz:", "size": 1, "bold": True},
        {"text": "Kaum größer", "size": 1.02},
        {"text": "* * *", "size": 2},
        {"text": "Lang " * 50, "size": 1.5},
        text(),
    ]

    assert sorted(headings(blocks)) == [1, 2]
    assert sorted(headings([heading("Kapitel 1", "h3", 1), *blocks[1:]])) == [0, 1]


def test_a_heading_is_higher_for_being_larger_then_a_higher_heading_then_bold() -> None:
    blocks = [
        heading("Größte", "h3", 2),
        heading("Erste", "h1", 1.2),
        heading("Zweite", "h2", 1.2),
        {"text": "Fett", "size": 1.2, "bold": True},
        {"text": "Mager", "size": 1.2},
    ]

    assert headings(blocks) == {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}


def test_short_bold_lines_one_after_another_are_a_list_and_not_headings() -> None:
    words: list[dict[str, Any]] = [
        {"text": word, "size": 1, "bold": True} for word in ("Hund", "Katze", "Maus")
    ]
    blocks = [{"text": "Vokabeln", "size": 1.2}, *words, text(), words[0], text()]

    assert sorted(headings(blocks)) == [0, 5]


def test_a_bold_line_is_no_heading_in_a_book_whose_headings_are_marked_as_such() -> (
    None
):
    blocks = [
        heading("Vokabeln", "h3", 0.9),
        {"text": "der Hund dog", "size": 1, "bold": True},
        text(),
        {"text": "Größer", "size": 1.3},
    ]

    assert sorted(headings(blocks)) == [0, 3]


def test_a_book_without_contents_is_made_into_sections_by_its_headings() -> None:
    blocks = [
        text("Copyright"),
        heading("Geschichte", "h1", 2),
        heading("Kapitel 1", "h2", 1.5),
        text(),
        heading("Vokabeln", "h3", 0.9),
        text(),
        heading("Kapitel 2", "h2", 1.5),
        text(),
        heading("Glossar", "h1", 2),
        text(),
    ]

    assert titles(outline(blocks)) == [
        ("", 0, 1),
        (
            "Geschichte",
            1,
            8,
            [("Kapitel 1", 2, 6, [("Vokabeln", 4, 6)]), ("Kapitel 2", 6, 8)],
        ),
        ("Glossar", 8, 10),
    ]


def test_the_table_of_contents_gives_the_sections_and_the_headings_split_them() -> None:
    blocks = [
        heading("Inhalt", "h1", 2),
        text(),
        heading("Der Feuer-Traum", "h1", 1.5),
        heading("Kapitel 1", "h2", 1.1),
        text(),
        heading("Anhang zu Kapitel 1", "h2", 1),
        heading("Vokabeln", "h3", 0.9),
        {"text": "der Hund dog", "size": 1, "bold": True},
        text(),
        heading("Kapitel 2", "h2", 1.1),
        text(),
        heading("Answer Key", "h1", 2),
        text(),
    ]
    contents = [
        {
            "title": "Der Feuer-Traum",
            "block": 2,
            "entries": [
                {"title": "Kapitel 1", "block": 3},
                {"title": "Kapitel 2", "block": 9},
            ],
        },
        {"title": "Answer Key", "block": 11},
    ]

    assert titles(outline(blocks, contents)) == [
        ("Inhalt", 0, 2),
        (
            "Der Feuer-Traum",
            2,
            11,
            [
                (
                    "Kapitel 1",
                    3,
                    9,
                    [("Anhang zu Kapitel 1", 5, 9, [("Vokabeln", 6, 9)])],
                ),
                ("Kapitel 2", 9, 11),
            ],
        ),
        ("Answer Key", 11, 13),
    ]


def test_an_entry_that_leads_just_before_its_heading_does_not_make_it_twice() -> None:
    blocks = [
        text("Seite 1"),
        heading("Kapitel 1"),
        text(),
        heading("Vokabeln", "h3", 1),
    ]
    contents = [{"title": "Kapitel 1", "block": 0}]

    assert titles(outline(blocks, contents)) == [
        ("Kapitel 1", 0, 4, [("Vokabeln", 3, 4)])
    ]


def test_a_section_without_blocks_is_left_out() -> None:
    blocks = [text("Titel"), text(), text()]
    contents = [
        {"title": "Title Page", "block": 0},
        {"title": "Contents", "block": 0, "entries": [{"title": "Leer", "block": 1}]},
        {"title": "Audio", "block": 1},
        {"title": "Autor", "block": 1},
    ]

    assert titles(outline(blocks, contents)) == [("Contents", 0, 1), ("Autor", 1, 3)]


def test_an_entry_that_leads_back_is_left_out_with_those_under_it() -> None:
    blocks = [text(), text(), text(), text()]
    contents = [
        {"title": "Zwei", "block": 2},
        {"title": "Zurück", "block": 1, "entries": [{"title": "Drei", "block": 3}]},
        {"title": "Drei", "block": 3},
        {"title": "Fort", "block": 99},
    ]

    assert titles(outline(blocks, contents)) == [
        ("", 0, 2),
        ("Zwei", 2, 3),
        ("Drei", 3, 4),
    ]


def test_a_section_is_kept_with_those_under_it_only_if_it_has_any() -> None:
    section = Section("Eins", 0, 4, [Section("Zwei", 1, 4)])

    assert section.kept() == {
        "title": "Eins",
        "start": 0,
        "end": 4,
        "sections": [{"title": "Zwei", "start": 1, "end": 4}],
    }
