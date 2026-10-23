# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Writes a book as it is kept back into an EPUB file, so that a version of
it can be read elsewhere. The book is kept as its blocks, and is written as
them: a file of the EPUB for each section at the top, each block in the
element it was in, as large, as bold and in italics as it was, its links
leading where they did, the pictures in the text where they were, the
picture on the cover, and a table of contents,
the book's own or else its sections. What was left out when the book was
read, such as its other pictures and its style sheets, is not there.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from collections.abc import Callable
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from books import PICTURE_ENDS
from sections import Section, outline

# the elements a block is written in as it was; any other is a paragraph, as
# an item of a list or a cell of a table is no longer in one
_TAGS = frozenset("h1 h2 h3 h4 h5 h6 p blockquote pre".split())
# the kind of file each picture is, by the end of its name
_PICTURE_TYPES = {end: kind for kind, end in PICTURE_ENDS.items()}
_CONTAINER = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
    '<rootfiles><rootfile full-path="OEBPS/content.opf"'
    ' media-type="application/oebps-package+xml"/></rootfiles></container>'
)
_PAGE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
    '<html xmlns="http://www.w3.org/1999/xhtml"'
    ' xmlns:epub="http://www.idpf.org/2007/ops" lang={language}'
    " xml:lang={language}><head><title>{title}</title></head><body>{body}</body></html>"
)


def _page_name(number: int) -> str:
    return f"text/part{number}.xhtml"


def _block(
    block: dict[str, Any],
    place: int,
    linked: set[int],
    where: list[str],
    pictures: dict[str, bytes],
) -> str:
    """A block as XHTML, with its links leading to the page of the block
    each leads to, by `where`, the page of each block. A picture is shown
    as a paragraph of its own, if it is among `pictures`."""
    attributes = f' id="b{place}"' if place in linked else ""
    if block.get("image"):
        if block["image"] not in pictures:
            return f"<p{attributes}/>"
        source = quoteattr(f"../images/{block['image']}")
        alt = quoteattr(block.get("alt", ""))
        return f"<p{attributes}><img src={source} alt={alt}/></p>"
    tag = block.get("tag", "p")
    tag = tag if tag in _TAGS else "p"
    styles = []
    size = block.get("size", 1)
    if not tag.startswith("h") and isinstance(size, (int, float)) and size != 1:
        styles.append(f"font-size: {size:.3g}em")
    if block.get("bold") and not tag.startswith("h"):
        styles.append("font-weight: bold")
    if block.get("italic"):
        styles.append("font-style: italic")
    if styles:
        attributes += f" style={quoteattr('; '.join(styles))}"
    text: str = block.get("text", "")
    written, at = [], 0
    for start, end, to in sorted(_links(block), key=lambda link: link[0]):
        if start < at or end <= start or end > len(text):
            continue
        if isinstance(to, int) and not 0 <= to < len(where):
            continue
        written.append(escape(text[at:start]))
        if isinstance(to, int):
            href = f"{where[to].removeprefix('text/')}#b{to}"
        else:
            href = to
        written.append(f"<a href={quoteattr(href)}>{escape(text[start:end])}</a>")
        at = end
    written.append(escape(text[at:]))
    return f"<{tag}{attributes}>{''.join(written)}</{tag}>"


def _links(block: dict[str, Any]) -> list[tuple[int, int, int | str]]:
    links = block.get("links") or []
    return [
        (start, end, to)
        for start, end, to in links
        if isinstance(start, int)
        and isinstance(end, int)
        and isinstance(to, (int, str))
    ]


def _navigation(entries: list[dict[str, Any]], where: list[str]) -> str:
    """The entries of a table of contents as a list of XHTML, each leading
    to the block it does."""
    items = []
    for entry in entries:
        block = entry["block"]
        href = f"{where[block]}#b{block}"
        under = entry.get("entries") or []
        items.append(
            f"<li><a href={quoteattr(href)}>{escape(entry['title'] or '…')}</a>"
            + (_navigation(under, where) if under else "")
            + "</li>"
        )
    return f"<ol>{''.join(items)}</ol>"


def _flat(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The entries of a table of contents, with those under each after it."""
    return [
        each
        for entry in entries
        for each in [entry, *_flat(entry.get("entries") or [])]
    ]


def _entries(sections: list[Section]) -> list[dict[str, Any]]:
    """Sections as entries of a table of contents, without those with no title."""
    entries: list[dict[str, Any]] = []
    for section in sections:
        under = _entries(section.sections)
        if section.title:
            entries.append(
                {"title": section.title, "block": section.start, "entries": under}
            )
        else:
            entries.extend(under)
    return entries


def _valid(entries: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    """The entries of a table of contents that lead to a block there is."""
    return [
        {**entry, "entries": _valid(entry.get("entries") or [], count)}
        for entry in entries
        if isinstance(entry.get("block"), int) and 0 <= entry["block"] < count
    ]


def write_epub(
    book: dict[str, Any],
    cover: tuple[bytes, str] | None = None,
    picture: Callable[[str], bytes | None] = lambda _: None,
) -> bytes:
    """An EPUB file of `book`, as `UserStore.book` gives it, with `cover`,
    the picture on its cover with the kind of file it is, if it has one,
    and the pictures in its text, as `picture` gives each by its id; one
    it does not give is left out."""
    blocks: list[dict[str, Any]] = book["blocks"]
    pictures = {
        block["image"]: data
        for block in blocks
        if block.get("image") and (data := picture(block["image"])) is not None
    }
    title = book.get("title") or "Book"
    if book.get("version", {}).get("name"):
        title = f"{title} ({book['version']['name']})"
    language = book.get("language") or "und"
    contents = _valid(book.get("contents") or [], len(blocks))
    sections = outline(blocks, contents)
    # a page for each section at the top, and the page of each block
    starts = [section.start for section in sections] or [0]
    where: list[str] = []
    for place in range(len(blocks)):
        where.append(_page_name(sum(1 for start in starts if start <= place) - 1))
    entries = contents or _entries(sections)
    # the blocks something leads to, which are given an id to be led to by
    linked = {
        to
        for block in blocks
        for _, _, to in _links(block)
        if isinstance(to, int) and 0 <= to < len(blocks)
    } | {entry["block"] for entry in _flat(entries)}

    pages: list[str] = []
    ends = [*starts[1:], len(blocks)]
    for start, end in zip(starts, ends):
        body = "".join(
            _block(blocks[place], place, linked, where, pictures)
            for place in range(start, end)
        )
        pages.append(
            _PAGE.format(
                language=quoteattr(language),
                title=escape(title),
                body=body or "<p/>",
            )
        )
    navigation = _PAGE.format(
        language=quoteattr(language),
        title=escape(title),
        body=f'<nav epub:type="toc" id="toc"><h1>{escape(title)}</h1>'
        + (
            _navigation(entries, where)
            if entries
            else f'<ol><li><a href="{_page_name(0)}">{escape(title)}</a></li></ol>'
        )
        + "</nav>",
    )

    identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"lansi:book:{book.get('id', title)}")
    manifest = [
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"'
        ' properties="nav"/>'
    ]
    manifest += [
        f'<item id="part{number}" href="{_page_name(number)}"'
        ' media-type="application/xhtml+xml"/>'
        for number in range(len(pages))
    ]
    manifest += [
        f'<item id="i{number}" href="images/{picture_id}"'
        f' media-type="{_PICTURE_TYPES[picture_id.rpartition(".")[2]]}"/>'
        for number, picture_id in enumerate(pictures)
    ]
    cover_meta = ""
    cover_file = None
    if cover and cover[1] in PICTURE_ENDS:
        cover_file = f"cover.{PICTURE_ENDS[cover[1]]}"
        manifest.append(
            f'<item id="cover" href="{cover_file}" media-type="{cover[1]}"'
            ' properties="cover-image"/>'
        )
        cover_meta = '<meta name="cover" content="cover"/>'
    spine = "".join(f'<itemref idref="part{number}"/>' for number in range(len(pages)))
    author = book.get("author") or ""
    package = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0"'
        ' unique-identifier="id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="id">urn:uuid:{identifier}</dc:identifier>'
        f"<dc:title>{escape(title)}</dc:title>"
        f"<dc:language>{escape(language)}</dc:language>"
        + (f"<dc:creator>{escape(author)}</dc:creator>" if author else "")
        + '<meta property="dcterms:modified">2000-01-01T00:00:00Z</meta>'
        + cover_meta
        + "</metadata>"
        f"<manifest>{''.join(manifest)}</manifest>"
        f"<spine>{spine}</spine></package>"
    )

    file = io.BytesIO()
    with zipfile.ZipFile(file, "w") as archive:
        # the kind of file comes first, and is not compressed, as EPUB asks
        archive.writestr("mimetype", "application/epub+zip", zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", _CONTAINER, zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/content.opf", package, zipfile.ZIP_DEFLATED)
        archive.writestr("OEBPS/nav.xhtml", navigation, zipfile.ZIP_DEFLATED)
        for number, page in enumerate(pages):
            archive.writestr(f"OEBPS/{_page_name(number)}", page, zipfile.ZIP_DEFLATED)
        for picture_id, data in pictures.items():
            archive.writestr(f"OEBPS/images/{picture_id}", data, zipfile.ZIP_STORED)
        if cover and cover_file:
            archive.writestr(f"OEBPS/{cover_file}", cover[0], zipfile.ZIP_STORED)
    return file.getvalue()
