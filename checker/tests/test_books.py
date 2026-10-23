# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import io
import zipfile

import pytest
from books import Block, BookError, Entry, Landmark, font_size, read_epub

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

# enough of it for most of the book to be written in its size
TEXT = "Es war einmal ein Hund, der gern las. " * 5


def page(body: str, head: str = "") -> str:
    return (
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        f"<head><title>Ignored</title>{head}</head><body>{body}</body></html>"
    )


def epub(
    *pages: str,
    files: dict[str, str] | None = None,
    metadata: str = "<dc:title>Der Hund</dc:title>",
    manifest: str = "",
    guide: str = "",
) -> bytes:
    """An EPUB file with the pages in the order given, and what else it is
    to have in it, by name."""
    items = "".join(
        f'<item id="p{number}" href="text/p{number}.xhtml"'
        ' media-type="application/xhtml+xml"/>'
        for number in range(len(pages))
    )
    spine = "".join(f'<itemref idref="p{number}"/>' for number in range(len(pages)))
    package = (
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        f'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">{metadata}</metadata>'
        f"<manifest>{items}{manifest}</manifest><spine>{spine}</spine>"
        f"<guide>{guide}</guide></package>"
    )
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", CONTAINER)
        archive.writestr("OEBPS/content.opf", package)
        for number, content in enumerate(pages):
            archive.writestr(f"OEBPS/text/p{number}.xhtml", content)
        for name, content in (files or {}).items():
            archive.writestr(name, content)
    return data.getvalue()


def blocks(*pages: str, files: dict[str, str] | None = None) -> list[tuple[str, float]]:
    """The text of a book with those pages, without the paragraph that most
    of it is written in the size of."""
    book = read_epub(epub(*pages, page(f"<p>{TEXT}</p>"), files=files))
    return [(block.text, block.size) for block in book.blocks[:-1]]


def test_a_book_is_read_into_its_paragraphs_in_the_order_of_its_pages() -> None:
    book = read_epub(
        epub(
            page("<p>Erster  Absatz,\n noch <i>immer</i>.</p><p>Zweiter Absatz.</p>"),
            page("<div>Dritter Absatz.</div>"),
        )
    )

    assert book.title == "Der Hund"
    assert book.blocks == [
        Block("Erster Absatz, noch immer.", 1, page="OEBPS/text/p0.xhtml"),
        Block("Zweiter Absatz.", 1),
        Block("Dritter Absatz.", 1, tag="div", page="OEBPS/text/p1.xhtml"),
    ]


def test_a_book_says_who_wrote_it_and_in_which_language() -> None:
    described = (
        "<dc:title>Der Hund</dc:title><dc:creator>Ada Autorin</dc:creator>"
        "<dc:language>de</dc:language>"
    )

    book = read_epub(epub(page("<p>Text.</p>"), metadata=described))

    assert (book.author, book.language) == ("Ada Autorin", "de")


def test_a_book_without_a_title_is_called_what_its_file_is() -> None:
    book = read_epub(epub(page("<p>Text.</p>"), metadata=""), "hund.epub")

    assert book.title == "hund.epub"


def test_a_heading_is_larger_than_the_text_unless_the_book_says_otherwise() -> None:
    assert blocks(page("<h1>Eins</h1><h2>Zwei</h2><h4>Vier</h4>")) == [
        ("Eins", 2),
        ("Zwei", 1.5),
        ("Vier", 1),
    ]


def test_the_size_of_a_paragraph_is_what_the_style_sheet_of_the_page_gives_it() -> None:
    styled = page(
        '<h1>Titel</h1><p class="note">Klein.</p><p style="font-size: 24px">Groß.</p>',
        '<link rel="stylesheet" href="../styles/book.css"/>',
    )
    sheet = "/* sizes */ h1 { font-size: 1.25em; color: red } .note { font-size: 80% }"

    read = blocks(styled, files={"OEBPS/styles/book.css": sheet})

    assert read == [("Titel", 1.25), ("Klein.", 0.8), ("Groß.", 1.5)]


def test_a_size_holds_for_what_is_inside_and_is_counted_from_it() -> None:
    styled = page(
        '<div class="motto"><p>Aus einem Buch.</p><p><small>Von wem.</small></p></div>',
        "<style>.motto { font-size: 12px } small { font-size: 0.5em }</style>",
    )

    assert blocks(styled) == [("Aus einem Buch.", 0.75), ("Von wem.", 0.38)]


def test_the_rule_with_the_more_exact_selector_is_the_one_that_counts() -> None:
    styled = page(
        '<div id="start"><p class="first">Eins.</p></div><p class="first">Zwei.</p>',
        "<style>#start > p { font-size: 32px } p.first { font-size: 8px }"
        " p { font-size: 4px !important } p.first { font-size: 24px }"
        " @media print { p { font-size: 1px !important } }"
        " p::first-letter { font-size: 5px !important }</style>",
    )

    assert blocks(styled) == [("Eins.", 0.25), ("Zwei.", 0.25)]
    assert blocks(styled.replace(" !important }", " }", 1)) == [
        ("Eins.", 2),
        ("Zwei.", 1.5),
    ]


def test_a_paragraph_is_of_the_size_most_of_it_is_written_in() -> None:
    styled = page(
        '<p><span style="font-size: 3em">E</span>s war einmal.</p>'
        '<p style="font-size: 2em">Kurz<br/>und <span style="font-size: 8px">'
        "g</span>ut.</p>"
    )

    assert blocks(styled) == [("Es war einmal.", 1), ("Kurz\nund gut.", 2)]


def test_what_is_not_text_of_the_book_is_left_out() -> None:
    cluttered = page(
        "<p>Ein Bild: <img src='hund.png' alt='ein Hund'/></p>"
        "<script>var x = 1;</script><svg><text>Zeichnung</text></svg>"
        "<p hidden='hidden'>Versteckt.</p><p>Tom &amp; Jerry&nbsp;AG</p><p> </p>"
    )

    assert blocks(cluttered) == [("Ein Bild:", 1), ("Tom & Jerry\xa0AG", 1)]


def test_the_page_that_lists_the_others_is_not_read() -> None:
    listing = (
        '<item id="nav" href="nav.xhtml" properties="nav"'
        ' media-type="application/xhtml+xml"/>'
    )
    book = read_epub(
        epub(
            page("<p>Text.</p>"),
            files={"OEBPS/nav.xhtml": page("<nav><ol><li>Kapitel 1</li></ol></nav>")},
            manifest=listing,
        )
    )

    assert [block.text for block in book.blocks] == ["Text."]


@pytest.mark.parametrize(
    ("value", "px"),
    [
        ("12pt", 16),
        ("1.5em", 30),
        ("2rem", 32),
        ("150%", 30),
        ("x-large", 24),
        ("larger", 24),
        ("inherit", 20),
        (" 10PX ", 10),
        ("0", None),
        ("calc(1em + 2px)", None),
        ("bold", None),
    ],
)
def test_a_size_is_counted_in_pixels_from_the_size_around_it(
    value: str, px: float | None
) -> None:
    assert font_size(value, 20) == px


def test_a_file_that_is_not_a_book_is_refused() -> None:
    not_a_book = io.BytesIO()
    with zipfile.ZipFile(not_a_book, "w") as archive:
        archive.writestr("notes.txt", "Hallo")

    with pytest.raises(BookError, match="not an EPUB"):
        read_epub(b"%PDF-1.7 and so on")
    with pytest.raises(BookError, match="not an EPUB"):
        read_epub(not_a_book.getvalue())
    with pytest.raises(BookError, match="no text"):
        read_epub(epub(page("<img src='cover.jpg'/>")))


def test_a_book_whose_pages_are_locked_is_refused_and_one_with_locked_fonts_read() -> (
    None
):
    def locking(name: str) -> dict[str, str]:
        return {
            "META-INF/encryption.xml": '<encryption xmlns="urn:oasis:names:tc:'
            'opendocument:xmlns:container"><EncryptedData><CipherData>'
            f'<CipherReference URI="{name}"/></CipherData></EncryptedData>'
            "</encryption>"
        }

    with_fonts_locked = epub(page("<p>Text.</p>"), files=locking("OEBPS/font.otf"))

    assert [block.text for block in read_epub(with_fonts_locked).blocks] == ["Text."]
    with pytest.raises(BookError, match="locked"):
        read_epub(epub(page("<p>Text.</p>"), files=locking("OEBPS/text/p0.xhtml")))


def links(*pages: str) -> list[tuple[str, list[tuple[int, int, int | str]]]]:
    """The paragraphs of a book with those pages, each with where it leads."""
    return [(block.text, block.links) for block in read_epub(epub(*pages)).blocks]


def test_a_link_leads_to_the_paragraph_its_page_or_the_place_in_it_starts_with() -> (
    None
):
    contents = page(
        '<p><a href="p1.xhtml">Erstes Kapitel</a></p>'
        '<p>Siehe <a href="p1.xhtml#note">die Anmerkung</a> dazu.</p>'
        '<p><a href="#top">Nach oben</a></p>',
    ).replace("<body>", '<body id="top">')
    chapter = page(
        '<h1>Eins</h1><p>Text<a id="ref"></a>.</p><div id="note"><p>Anmerkung.</p></div>'
    )

    assert links(contents, chapter) == [
        ("Erstes Kapitel", [(0, 14, 3)]),
        ("Siehe die Anmerkung dazu.", [(6, 19, 5)]),
        ("Nach oben", [(0, 9, 0)]),
        ("Eins", []),
        ("Text.", []),
        ("Anmerkung.", []),
    ]


def test_a_link_out_of_the_book_keeps_its_address_and_one_to_nowhere_is_dropped() -> (
    None
):
    linked = page(
        '<p>Mehr auf <a href="https://example.org/hund?x=1">der Seite</a>.</p>'
        '<p><a href="missing.xhtml">Fehlt</a> und <a href="javascript:x()">mehr</a></p>'
    )

    assert links(linked) == [
        ("Mehr auf der Seite.", [(9, 18, "https://example.org/hund?x=1")]),
        ("Fehlt und mehr", []),
    ]


def test_a_link_around_several_paragraphs_leads_on_from_each_of_them() -> None:
    wrapped = page(
        '<a href="#end"><p>Eins.</p> <p>Zwei.</p></a><p id="end">  Ende <a href="#end"'
        "> hier </a> </p>"
    )

    assert links(wrapped) == [
        ("Eins.", [(0, 5, 2)]),
        ("Zwei.", [(0, 5, 2)]),
        ("Ende hier", [(5, 9, 2)]),
    ]


def test_only_a_block_with_links_is_kept_with_them() -> None:
    assert Block("Text.", 1).kept() == {"text": "Text.", "size": 1}
    assert Block("Text.", 1, [(0, 4, 7)]).kept() == {
        "text": "Text.",
        "size": 1,
        "links": [[0, 4, 7]],
    }


def test_a_block_is_kept_with_how_it_is_written_only_where_most_are_not() -> None:
    assert Block(
        "Vokabeln",
        0.9,
        tag="h3",
        classes=["vocab"],
        bold=True,
        italic=True,
        roles=["chapter"],
        page="OEBPS/text/p3.xhtml",
    ).kept() == {
        "text": "Vokabeln",
        "size": 0.9,
        "tag": "h3",
        "classes": ["vocab"],
        "bold": True,
        "italic": True,
        "roles": ["chapter"],
        "page": "OEBPS/text/p3.xhtml",
    }


def read(*pages: str, files: dict[str, str] | None = None) -> list[Block]:
    """The blocks of a book with those pages, without the paragraph that most
    of it is written in the size of."""
    return read_epub(epub(*pages, page(f"<p>{TEXT}</p>"), files=files)).blocks[:-1]


def test_a_block_has_the_element_it_is_written_in_and_its_classes() -> None:
    found = read(
        page(
            '<section class="chapter"><h2 class="title big">Kapitel 1</h2>'
            '<div class="vocab"><p>der <b>Hund</b> dog</p>Ohne Absatz</div>'
            "</section>"
        )
    )

    assert [(block.tag, block.classes) for block in found] == [
        ("h2", ["big", "title"]),
        ("p", []),
        ("div", ["vocab"]),
    ]


def test_a_block_is_bold_or_italic_when_most_of_it_is_so() -> None:
    found = read(
        page(
            "<h3>Anhang</h3><p><b>Fast alles hier fett</b>, nicht.</p>"
            '<p class="note">Notiz</p><p><span style="font-style: italic">Kursiv'
            '</span></p><p style="font: bold 1em serif">Kurz</p>'
            '<h4 style="font-weight: normal">Leicht</h4><p><i>ein</i> Wort</p>',
            "<style>.note { font-weight: 700; font-style: oblique }</style>",
        )
    )

    assert [(block.text, block.bold, block.italic) for block in found] == [
        ("Anhang", True, False),
        ("Fast alles hier fett, nicht.", True, False),
        ("Notiz", True, True),
        ("Kursiv", False, True),
        ("Kurz", True, False),
        ("Leicht", False, False),
        ("ein Wort", False, False),
    ]


def test_a_block_has_what_the_book_says_the_parts_it_is_in_are() -> None:
    found = read(
        page(
            '<section epub:type="bodymatter chapter"><h1>Eins</h1>'
            '<aside epub:type="footnote" role="doc-footnote"><p>Fußnote</p></aside>'
            '<p epub:type="chapter">Text</p></section>'
        ),
        page('<section role="doc-glossary"><p>der Hund: dog</p></section>'),
    )

    assert [(block.text, block.roles) for block in found] == [
        ("Eins", ["bodymatter", "chapter"]),
        ("Fußnote", ["bodymatter", "chapter", "footnote", "doc-footnote"]),
        ("Text", ["bodymatter", "chapter"]),
        ("der Hund: dog", ["doc-glossary"]),
    ]


def test_a_block_that_starts_a_file_of_the_book_has_its_name() -> None:
    found = read(
        page("<p>Eins</p><p>Zwei</p>"),
        page("<script>nothing</script>"),
        page("<p>Drei</p>"),
    )

    assert [(block.text, block.page) for block in found] == [
        ("Eins", "OEBPS/text/p0.xhtml"),
        ("Zwei", ""),
        ("Drei", "OEBPS/text/p2.xhtml"),
    ]


@pytest.mark.parametrize(
    ("metadata", "manifest"),
    [
        (
            "",
            '<item id="front" href="images/front.jpg" media-type="image/jpeg"'
            ' properties="cover-image"/>',
        ),
        (
            '<meta name="cover" content="front"/>',
            '<item id="front" href="images/front.jpg" media-type="image/jpeg"/>',
        ),
        (
            "",
            '<item id="my-cover" href="images/front.jpg" media-type="image/jpeg"/>',
        ),
    ],
)
def test_the_cover_is_the_picture_the_book_says_or_one_it_calls_so(
    metadata: str, manifest: str
) -> None:
    other = '<item id="map" href="images/map.jpg" media-type="image/jpeg"/>'
    book = read_epub(
        epub(
            page("<p>Text.</p>"),
            files={"OEBPS/images/front.jpg": "JPEG", "OEBPS/images/map.jpg": "MAP"},
            metadata=metadata,
            manifest=other + manifest,
        )
    )

    assert book.cover == (b"JPEG", "image/jpeg")


def test_a_book_without_a_picture_for_its_cover_has_none() -> None:
    drawn = '<item id="cover" href="cover.svg" media-type="image/svg+xml"/>'

    assert read_epub(epub(page("<p>Text.</p>"), manifest=drawn)).cover is None


NAV_ITEM = (
    '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
    ' properties="nav"/>'
)


def test_a_book_has_the_table_of_contents_its_list_of_pages_has() -> None:
    nav = page(
        '<nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops"><ol>'
        '<li><a href="text/p0.xhtml">Vorwort</a></li>'
        "<li><span>Geschichten</span><ol>"
        '<li><a href="text/p1.xhtml#k1">Kapitel  1</a></li>'
        '<li><a href="text/p1.xhtml#nowhere">Kapitel 2</a></li>'
        '<li><a href="text/missing.xhtml">Verloren</a></li>'
        "</ol></li></ol></nav>"
        '<nav epub:type="landmarks" xmlns:epub="http://www.idpf.org/2007/ops"><ol>'
        '<li><a epub:type="bodymatter" href="text/p1.xhtml">Anfang</a></li>'
        "</ol></nav>"
    )
    book = read_epub(
        epub(
            page("<p>Vorwort</p>"),
            page('<p>Titel</p><h2 id="k1">Kapitel 1</h2><p>Text</p>'),
            files={"OEBPS/nav.xhtml": nav},
            manifest=NAV_ITEM,
        )
    )

    assert book.contents == [
        Entry("Vorwort", 0),
        Entry("Geschichten", 2, [Entry("Kapitel 1", 2), Entry("Kapitel 2", 1)]),
    ]
    assert book.landmarks == [Landmark("bodymatter", "Anfang", 1)]


def test_an_older_book_has_the_table_of_contents_of_its_own_file_and_its_guide() -> (
    None
):
    ncx = (
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>'
        '<navPoint id="a"><navLabel><text>Eins</text></navLabel>'
        '<content src="text/p0.xhtml"/>'
        '<navPoint id="b"><navLabel><text>Zwei</text></navLabel>'
        '<content src="text/p1.xhtml"/></navPoint></navPoint>'
        "</navMap></ncx>"
    )
    book = read_epub(
        epub(
            page("<p>Eins</p>"),
            page("<p>Zwei</p>"),
            files={"OEBPS/toc.ncx": ncx},
            manifest='<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
            guide='<reference type="text" title="Text" href="text/p1.xhtml"/>',
        )
    )

    assert book.contents == [Entry("Eins", 0, [Entry("Zwei", 1)])]
    assert book.landmarks == [Landmark("text", "Text", 1)]


def test_a_list_of_pages_that_cannot_be_read_leaves_the_book_without_contents() -> None:
    book = read_epub(
        epub(
            page("<p>Text</p>"),
            files={"OEBPS/nav.xhtml": "<html><nav>not closed"},
            manifest=NAV_ITEM,
        )
    )

    assert (book.contents, [block.text for block in book.blocks]) == ([], ["Text"])


def test_what_a_book_lists_of_itself_is_kept_with_what_it_has_under_it() -> None:
    assert Entry("Eins", 0, [Entry("Zwei", 3)]).kept() == {
        "title": "Eins",
        "block": 0,
        "entries": [{"title": "Zwei", "block": 3}],
    }
    assert Landmark("toc", "Inhalt", 2).kept() == {
        "type": "toc",
        "title": "Inhalt",
        "block": 2,
    }
