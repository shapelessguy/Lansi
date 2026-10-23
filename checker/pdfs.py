# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Reads a PDF file into a book as `books` keeps one, so that it is read,
made versions of and exported as an EPUB is.

A PDF says where each piece of text is drawn and in what font, not what is a
paragraph or a heading, so that is worked out from how the text is drawn: a
paragraph ends where the lines leave a gap, where a line starts further in
or the one before it stops short after a sentence, or where the size of the
text changes; one that breaks off at the end of a page, mid-sentence, goes on
on the next. A word cut by a hyphen at the end of a line is joined again. A
line written larger than most of the book, and short, is a heading, the
larger the higher. What is written in the margin of most pages alike, as the
title of the book or the number of the page, is left out.

The pictures drawn among the text are kept, each where it is drawn, as
`books` keeps them; one drawn on many pages, such as a logo, and one behind
the text of its page are left out. A figure drawn of lines and shapes, such
as a diagram, is made a picture of itself with the words written on it,
which are not text of the book: a box of shapes with sentences in it, such
as a frame around a paragraph, is not a figure, and neither is a rule. The outline of the PDF, if it has one,
is its table of contents, and the first page, drawn small, its cover. A PDF
of scanned pages, which has pictures of text and no text, cannot be read.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import pymupdf
from books import Block, Book, BookError, Entry, Picture, clean_text, kept_picture

# how far from the top or the bottom of a page the margin is, as a part of
# the height of the page
MARGIN = 0.08
# On how many pages a line written in the margin must be, at the least, to
# be the same on each and not part of the text: no more than a few, as each
# chapter may have its own title at the top of its pages.
REPEATED_PAGES = 3
# A picture drawn on as many pages as this is part of how the pages look,
# such as a logo, and not of the text; so is one that covers as much of a
# page with text on it as this.
PICTURE_PAGES = 3
BACKGROUND = 0.8
# how much larger than most of the book a short line is written for it to be
# a heading, and how long a heading may be
HEADING_SIZE = 1.15
MAX_HEADING = 200
# how many levels of headings there are, the rest being the lowest
HEADING_LEVELS = 3
# How large the text of a line may differ from that of the paragraph it is
# in, as a part of it, before it starts another.
SIZE_CHANGE = 0.1
# How far a line may start further in than the one before it, in parts of
# the size of its text, before it starts a paragraph; and how far short of
# the right of the paragraph a line ends for it to end the paragraph, after
# a sentence.
INDENT = 0.8
SHORT = 3.0
# how far below the one before it a line may start, in parts of the height
# of the line, before there is a gap between them
GAP = 1.6
# how wide the cover is drawn, in pixels
COVER_WIDTH = 600
# How large shapes drawn together must be, on each side, in points, to be a
# figure, and how near it, in points, a shape, a word or a picture must be
# to be part of it.
MIN_FIGURE = 40
FIGURE_MARGIN = 12
# A word on a figure is written smaller than most of the book, as a part of
# its size; one as large is of the text, such as the caption of the figure.
LABEL_SIZE = 0.85
# how much room is left around a figure when it is drawn, in points, as a line
# is drawn half outside where it is
FIGURE_ROOM = 3
# A figure has words on it, not sentences: a line on it as long as this, in
# letters, is of a paragraph, and shapes with as much of their words in such
# lines as this are a frame around text.
SENTENCE = 60
FRAMED = 0.5
# how many times as large as it is on the page a figure is drawn
FIGURE_SCALE = 2
# what ends a sentence, after which a paragraph may end
_ENDS = (".", "!", "?", ":", '"', "”", "“", "»", "«", ")", "…", "’", "'")
_DIGITS = re.compile(r"\d+")
# a line in the margin that is no more than the number of its page, with the
# numbers made "#" as `_margin_key` has them
_PAGE_NUMBER = re.compile(r"[#\s.\-–—|/]+|[ivxlcdm]+")
_SPACE = re.compile(r"\s+")
_LETTER = re.compile(r"\w")
# the letters some fonts draw joined, as the letters they are
_LIGATURES = str.maketrans(
    {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
)
# the span is written in italics, and in bold, by the flags of PyMuPDF
_ITALIC = 2
_BOLD = 16
# the kind of file of a picture, by what PyMuPDF calls it
_KINDS = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
}


@dataclass
class _Line:
    """A line of text as it is drawn on a page."""

    text: str
    # the size most of it is written in, and how many of its letters are
    # written in bold and in italics, of how many
    size: float
    bold: int
    italic: int
    letters: int
    left: float
    top: float
    right: float
    bottom: float


@dataclass
class _Paragraph:
    lines: list[_Line] = field(default_factory=list)
    # the page it starts on, from 0
    page: int = 0
    picture: Picture | None = None
    alt: str = ""

    @property
    def text(self) -> str:
        text = ""
        for line in self.lines:
            piece = line.text.strip()
            if not text:
                text = piece
            elif re.search(r"\w-$", text) and piece[:1].islower():
                # a word cut at the end of the line is joined again
                text = text[:-1] + piece
            else:
                text += " " + piece
        return _SPACE.sub(" ", text).strip()

    @property
    def size(self) -> float:
        sizes: Counter[float] = Counter()
        for line in self.lines:
            sizes[line.size] += line.letters
        return sizes.most_common(1)[0][0] if sizes else 0.0

    def share(self, name: str) -> bool:
        """Whether most of its letters are written in bold, or in italics."""
        letters = sum(line.letters for line in self.lines)
        return 2 * sum(int(getattr(line, name)) for line in self.lines) > letters


def _line(line: dict[str, Any]) -> _Line | None:
    """A line as PyMuPDF reads it, if it has any text."""
    drawn = "".join(span["text"] for span in line["spans"]).rstrip()
    text = clean_text(drawn).translate(_LIGATURES)
    if drawn.endswith("\xad"):
        # a word cut at the end of the line, as a hyphen would say
        text = text.rstrip() + "-"
    if not text.strip():
        return None
    sizes: Counter[float] = Counter()
    bold = italic = 0
    for span in line["spans"]:
        letters = len(span["text"].strip())
        sizes[round(span["size"], 1)] += letters
        font = span.get("font", "").lower()
        if span["flags"] & _BOLD or "bold" in font or "black" in font:
            bold += letters
        if span["flags"] & _ITALIC or "italic" in font or "oblique" in font:
            italic += letters
    left, top, right, bottom = line["bbox"]
    return _Line(
        text,
        sizes.most_common(1)[0][0],
        bold,
        italic,
        sum(sizes.values()),
        left,
        top,
        right,
        bottom,
    )


def _margin_key(line: _Line, height: float) -> str | None:
    """What a line in the margin of a page says, with its numbers left out,
    to tell it on other pages; None for one that is not in the margin."""
    if MARGIN * height < line.top and line.bottom < (1 - MARGIN) * height:
        return None
    return _DIGITS.sub("#", _SPACE.sub(" ", line.text).strip().casefold())


def _picture_kind(block: dict[str, Any]) -> str:
    ext = str(block.get("ext", "")).lower()
    return _KINDS.get(ext, f"image/{ext}")


def _pages(document: pymupdf.Document) -> list[tuple[float, float, list[Any]]]:
    """The width and the height of each page, with what is drawn on it: its
    lines, and its pictures, as PyMuPDF reads them, from the top down, and
    the figures drawn on it as pictures in place of their words."""
    pages = []
    for page in document:
        # a page turned to be read sideways is read as it is shown
        if page.rotation:
            page.remove_rotation()
        # from the top of the page down, as a book of one column is read
        read = page.get_text("dict", flags=pymupdf.TEXTFLAGS_DICT, sort=True)
        drawn: list[Any] = []
        for block in read["blocks"]:
            if block.get("type") == 1:
                drawn.append(block)
                continue
            # a block ends with a line that is not one, so that two blocks
            # are not taken for one paragraph only by how they are drawn
            drawn += [found for line in block["lines"] if (found := _line(line))]
            drawn.append(None)
        pages.append((page.rect.width, page.rect.height, drawn))
    letters: Counter[float] = Counter()
    for _, _, drawn in pages:
        for each in drawn:
            if isinstance(each, _Line):
                letters[each.size] += each.letters
    usual = letters.most_common(1)[0][0] if letters else 0.0
    for page, (width, height, drawn) in zip(document, pages):
        for figure, words in _figures(page, drawn, usual):
            drawn = _with_figure(drawn, figure, words)
        pages[page.number] = (width, height, drawn)
    return pages


def _rect(each: _Line | dict[str, Any]) -> pymupdf.Rect:
    if isinstance(each, _Line):
        return pymupdf.Rect(each.left, each.top, each.right, each.bottom)
    return pymupdf.Rect(each["bbox"])


def _middle(line: _Line) -> pymupdf.Point:
    return pymupdf.Point((line.left + line.right) / 2, (line.top + line.bottom) / 2)


def _grown(rect: pymupdf.Rect, by: float) -> pymupdf.Rect:
    return pymupdf.Rect(rect.x0 - by, rect.y0 - by, rect.x1 + by, rect.y1 + by)


def _figures(
    page: pymupdf.Page, drawn: list[Any], usual: float
) -> list[tuple[dict[str, Any], set[int]]]:
    """The figures drawn of shapes on `page`, each as PyMuPDF has a picture,
    drawn with the words on it, and with what of `drawn` is on it, by `id`:
    its words, and the pictures it is drawn around. `usual` is the size most
    of the book is written in, which the words on a figure are smaller than.

    A figure starts from shapes drawn together that are large enough, and
    takes in all that is near it, over and over: the other shapes, however
    small, the words that are not of a sentence and the pictures. Then the
    words inside it are on it, however large, but for sentences."""
    shapes = [pymupdf.Rect(each) for each in page.cluster_drawings()]
    parts: list[tuple[pymupdf.Rect, int | None]] = [(rect, None) for rect in shapes]
    for each in drawn:
        if isinstance(each, dict) or (
            isinstance(each, _Line)
            and each.size < LABEL_SIZE * usual
            and each.letters < SENTENCE
        ):
            parts.append((_rect(each), id(each)))
    taken = [False] * len(parts)
    figures = []
    for start, (seed, _) in enumerate(parts[: len(shapes)]):
        if taken[start] or seed.width < MIN_FIGURE or seed.height < MIN_FIGURE:
            continue
        rect, words = +seed, set()
        taken[start] = True
        grew = True
        while grew:
            grew = False
            near = _grown(rect, FIGURE_MARGIN)
            for place, (part, part_id) in enumerate(parts):
                if not taken[place] and near.intersects(part):
                    taken[place], grew = True, True
                    rect |= part
                    if part_id is not None:
                        words.add(part_id)
        # the words written inside it are on it, however large, but for
        # sentences: a frame around them is not a figure
        inside = [
            each
            for each in drawn
            if isinstance(each, _Line) and rect.contains(_middle(each))
        ]
        words |= {id(line) for line in inside if line.letters < SENTENCE}
        letters = sum(line.letters for line in inside)
        in_sentences = sum(
            line.letters
            for line in inside
            if id(line) not in words and line.letters >= SENTENCE
        )
        if letters and in_sentences > FRAMED * letters:
            continue
        clip = _grown(rect, FIGURE_ROOM) & page.rect
        scale = pymupdf.Matrix(FIGURE_SCALE, FIGURE_SCALE)
        figure = {
            "type": 1,
            "figure": True,
            "bbox": tuple(clip),
            "ext": "png",
            "image": page.get_pixmap(matrix=scale, clip=clip).tobytes("png"),
        }
        figures.append((figure, words))
    return figures


def _with_figure(drawn: list[Any], figure: dict[str, Any], on: set[int]) -> list[Any]:
    """What is drawn on a page with `figure` among it, where it is from the
    top, without what is on it, by `id`."""
    kept = [each for each in drawn if id(each) not in on]
    top = figure["bbox"][1]
    at = next(
        (
            place
            for place, each in enumerate(kept)
            if each is not None and _rect(each).y0 >= top
        ),
        len(kept),
    )
    # it is a paragraph of its own, as a block is
    return [*kept[:at], None, figure, None, *kept[at:]]


def _left_out(pages: list[tuple[float, float, list[Any]]]) -> set[str]:
    """What is written in the margin of so many pages that it is not part of
    the text, each as `_margin_key` has it."""
    seen: Counter[str] = Counter()
    for _, height, drawn in pages:
        seen.update(
            {
                key
                for each in drawn
                if isinstance(each, _Line) and (key := _margin_key(each, height))
            }
        )
    return {key for key, count in seen.items() if count >= REPEATED_PAGES}


def _starts_paragraph(paragraph: _Paragraph, line: _Line) -> bool:
    """Whether `line` starts a paragraph after `paragraph` on the same page."""
    last = paragraph.lines[-1]
    size = paragraph.size or line.size
    if abs(line.size - size) > SIZE_CHANGE * size:
        return True
    height = max(last.bottom - last.top, 1.0)
    if line.top - last.top > GAP * height:
        return True
    left = min(each.left for each in paragraph.lines)
    right = max(each.right for each in paragraph.lines)
    ended = last.text.rstrip().endswith(_ENDS)
    if line.left - left > INDENT * line.size and ended:
        return True
    return ended and right - last.right > SHORT * line.size


def _goes_on(paragraph: _Paragraph, line: _Line) -> bool:
    """Whether `line`, which starts another block or page, goes on with
    `paragraph`, which broke off in the middle of a sentence."""
    if paragraph.picture or not paragraph.lines:
        return False
    text = paragraph.lines[-1].text.rstrip()
    size = paragraph.size
    return (
        not text.endswith(_ENDS)
        and line.text.lstrip()[:1].islower()
        and abs(line.size - size) <= SIZE_CHANGE * size
    )


def _paragraphs(document: pymupdf.Document) -> list[_Paragraph]:
    """The paragraphs and the pictures of a PDF, in order."""
    pages = _pages(document)
    left_out = _left_out(pages)
    shown_on: Counter[str] = Counter()
    pictures: list[tuple[int, dict[str, Any], Picture]] = []
    for number, (width, height, drawn) in enumerate(pages):
        has_text = any(isinstance(each, _Line) for each in drawn)
        for each in drawn:
            if not isinstance(each, dict):
                continue
            left, top, right, bottom = each["bbox"]
            covers = (right - left) * (bottom - top) / max(width * height, 1.0)
            if has_text and covers >= BACKGROUND and not each.get("figure"):
                continue
            picture = kept_picture(each.get("image") or b"", _picture_kind(each))
            if picture is not None:
                pictures.append((number, each, picture))
                shown_on[picture.id] += 1
    kept = {
        id(block): picture
        for _, block, picture in pictures
        if shown_on[picture.id] < PICTURE_PAGES
    }

    paragraphs: list[_Paragraph] = []
    current: _Paragraph | None = None
    for number, (_, height, drawn) in enumerate(pages):
        # a new block may go on with the paragraph before it
        joined = False
        for each in drawn:
            if each is None:
                joined = False
                continue
            if isinstance(each, dict):
                picture = kept.get(id(each))
                if picture is not None:
                    paragraphs.append(_Paragraph([], number, picture))
                    current = None
                continue
            key = _margin_key(each, height)
            if key is not None and (key in left_out or _PAGE_NUMBER.fullmatch(key)):
                continue
            if current is not None and (
                (joined and not _starts_paragraph(current, each))
                or (not joined and _goes_on(current, each))
            ):
                current.lines.append(each)
            else:
                current = _Paragraph([each], number)
                paragraphs.append(current)
            joined = True
    return [each for each in paragraphs if each.picture or each.text]


def _entries(
    toc: list[list[Any]], first_on: dict[int, int], blocks: list[Block]
) -> list[Entry]:
    """The outline of a PDF as a table of contents, each entry leading to
    the block on its page that says its title, or to the first on it."""
    top: list[Entry] = []
    # the entries each new one may be under, by their levels
    open_at: list[tuple[int, Entry]] = []
    for level, title, page, *_ in toc:
        if not isinstance(title, str) or not isinstance(page, int) or page < 1:
            continue
        start = next(
            (place for at, place in sorted(first_on.items()) if at >= page - 1), None
        )
        if start is None:
            continue
        wanted = _SPACE.sub(" ", title).strip().casefold()
        end = next(
            (place for at, place in sorted(first_on.items()) if at > page - 1),
            len(blocks),
        )
        block = next(
            (
                place
                for place in range(start, max(end, start + 1))
                if blocks[place].text
                and (
                    blocks[place].text.casefold().startswith(wanted[:40])
                    or wanted.startswith(blocks[place].text.casefold()[:40])
                )
            ),
            start,
        )
        entry = Entry(_SPACE.sub(" ", title).strip(), block)
        while open_at and open_at[-1][0] >= level:
            open_at.pop()
        (open_at[-1][1].entries if open_at else top).append(entry)
        open_at.append((level, entry))
    return top


def read_pdf(data: bytes, name: str = "") -> Book:
    """The book a PDF file is, read as the module says. `name` is what it is
    called if it does not say. Raises BookError."""
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, RuntimeError, ValueError):
        raise BookError("the file is not a PDF that can be read") from None
    with document:
        if document.needs_pass:
            raise BookError("the PDF is locked with a password")
        paragraphs = _paragraphs(document)
        if not any(each.lines for each in paragraphs):
            raise BookError(
                "there is no text in the PDF: it may be of scanned pages,"
                " which cannot be read"
            )
        cover = None
        if document.page_count:
            first = document[0]
            scale = COVER_WIDTH / max(first.rect.width, 1.0)
            drawn = first.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
            cover = (drawn.tobytes("jpeg", jpg_quality=85), "image/jpeg")
        metadata = document.metadata or {}
        toc = document.get_toc(simple=True)
        language = getattr(document, "language", None) or ""

    letters: Counter[float] = Counter()
    for paragraph in paragraphs:
        for line in paragraph.lines:
            letters[line.size] += line.letters
    usual = letters.most_common(1)[0][0] or 1.0
    # the sizes of the headings, the largest the highest
    heading_sizes = sorted(
        {
            round(each.size / usual, 1)
            for each in paragraphs
            if each.lines
            and each.size / usual >= HEADING_SIZE
            and len(each.text) <= MAX_HEADING
        },
        reverse=True,
    )
    blocks: list[Block] = []
    first_on: dict[int, int] = {}
    pictures: dict[str, bytes] = {}
    for paragraph in paragraphs:
        first_on.setdefault(paragraph.page, len(blocks))
        if paragraph.picture:
            picture = paragraph.picture
            pictures[picture.id] = picture.data
            blocks.append(
                Block(
                    "",
                    1,
                    tag="img",
                    image=picture.id,
                    width=picture.width,
                    height=picture.height,
                )
            )
            continue
        size = round(paragraph.size / usual, 2)
        rank = round(size, 1)
        tag = (
            f"h{min(heading_sizes.index(rank) + 1, HEADING_LEVELS)}"
            if rank in heading_sizes and len(paragraph.text) <= MAX_HEADING
            else "p"
        )
        blocks.append(
            Block(
                paragraph.text,
                size,
                tag=tag,
                bold=paragraph.share("bold"),
                italic=paragraph.share("italic"),
            )
        )
    # a PDF may be called nothing, or something that is not a name
    title = _SPACE.sub(" ", metadata.get("title") or "").strip()
    return Book(
        title if _LETTER.search(title) else name or "Untitled",
        (metadata.get("author") or "").strip(),
        language,
        blocks,
        cover,
        _entries(toc, first_on, blocks),
        [],
        pictures,
    )
