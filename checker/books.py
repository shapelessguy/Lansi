# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Reads an e-book, an EPUB file, and keeps the text of it a paragraph at a
time, with how each paragraph is written: how large, whether in bold or in
italics, in which element and with which classes, and what the book says the
parts it is in are, such as a chapter or a glossary. Where the text leads on
to another place, in the book or outside it, that is kept as well, and so is
the picture on the cover. The other pictures, the fonts, the colours and
whatever else a book is made of are left out. What the book lists of itself
is kept too: its table of contents, and its landmarks, the places it names
by what they are, such as where the text itself starts.

How a paragraph is written is worked out from the style sheets of the book,
as far as they say it in a plain way. How large it is is given as a multiple
of the size most of the book is written in: 1 for the text itself, more for
most headings, less for the small print.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from functools import partial
from html.parser import HTMLParser
from urllib.parse import unquote
from xml.etree import ElementTree

# no file of a book is anywhere near as long, pictures aside, which are not read
MAX_MEMBER_BYTES = 30_000_000
# the kinds of picture a cover is kept as
_COVER_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
# where a link may lead outside the book
_OUTSIDE = ("http://", "https://", "mailto:")
# the size text is written in where nothing says otherwise, in pixels
ROOT_PX = 16.0

# the name the attributes of EPUB, such as epub:type, are under
_OPS = "{http://www.idpf.org/2007/ops}"
_NCX_TYPE = "application/x-dtbncx+xml"

_CONTAINER = "META-INF/container.xml"
_ENCRYPTION = "META-INF/encryption.xml"
_PAGE_TYPES = ("application/xhtml+xml", "text/html")
# The elements that start a paragraph of their own.
_BLOCKS = frozenset(
    "address article aside blockquote body caption center dd div dl dt"
    " figcaption figure footer form h1 h2 h3 h4 h5 h6 header hr html li main"
    " nav ol p pre section table td th tr ul".split()
)
# The elements that have no end, and nothing in them.
_VOID = frozenset(
    "area base br col embed hr img input link meta source track wbr".split()
)
# The elements whose text is not part of what the book says.
_UNREAD = frozenset("head script style svg math rp rt template".split())
# How the elements that are not written as what they are in are written,
# unless the book says otherwise, by the property of the style that says it.
_USUAL = {
    "font-size": {
        "h1": "2em",
        "h2": "1.5em",
        "h3": "1.17em",
        "h5": "0.83em",
        "h6": "0.67em",
        "small": "smaller",
        "sub": "smaller",
        "sup": "smaller",
        "big": "larger",
    },
    "font-weight": dict.fromkeys("b strong th h1 h2 h3 h4 h5 h6".split(), "bold"),
    "font-style": dict.fromkeys("i em cite var dfn address".split(), "italic"),
}
# the properties of a style that are read
_PROPERTIES = tuple(_USUAL)
_NAMED_SIZES = {
    "xx-small": 9.0,
    "x-small": 10.0,
    "small": 13.0,
    "medium": 16.0,
    "large": 18.0,
    "x-large": 24.0,
    "xx-large": 32.0,
    "xxx-large": 48.0,
}
# how many pixels one of each unit is
_UNITS = {
    "px": 1.0,
    "pt": 4 / 3,
    "pc": 16.0,
    "in": 96.0,
    "cm": 96 / 2.54,
    "mm": 96 / 25.4,
    "q": 96 / 101.6,
}
_LENGTH = re.compile(r"([+-]?(?:\d+\.?\d*|\.\d+))([a-z%]*)")
_COMPOUND = re.compile(r"([A-Za-z][\w-]*|\*)?((?:[.#][\w-]+)*)")
_SPACE = re.compile(r"[ \t\r\n\f]+")


class BookError(ValueError):
    """The file could not be read as a book. The message says why."""


@dataclass
class Block:
    """A paragraph, a heading or another piece of text that stands alone."""

    text: str
    # how large it is written, as a multiple of the size of most of the book
    size: float
    # The parts of the text that lead somewhere: where each starts and ends
    # in the text, and where it leads, which is another block, by its place
    # among the blocks from 0, or an address outside the book.
    links: list[tuple[int, int, int | str]] = field(default_factory=list)
    # the element it is written in, such as "p" or "h2"
    tag: str = "p"
    # the classes the book gives that element
    classes: list[str] = field(default_factory=list)
    # whether most of it is written in bold, and in italics
    bold: bool = False
    italic: bool = False
    # What the book says the parts it is in are, from the outermost, such as
    # "bodymatter" and "chapter": the epub:type and the role of the elements
    # it is in and of its own.
    roles: list[str] = field(default_factory=list)
    # the file of the book that starts with it, if one does
    page: str = ""

    def kept(self) -> dict[str, object]:
        """The block as it is kept, with only what it has of what most blocks
        do not."""
        kept: dict[str, object] = {"text": self.text, "size": self.size}
        if self.links:
            kept["links"] = [list(link) for link in self.links]
        if self.tag != "p":
            kept["tag"] = self.tag
        for name in ("classes", "bold", "italic", "roles", "page"):
            if getattr(self, name):
                kept[name] = getattr(self, name)
        return kept


@dataclass
class Entry:
    """An entry of the table of contents of a book, with those under it."""

    title: str
    # the block it leads to, by its place among them from 0
    block: int
    entries: list[Entry] = field(default_factory=list)

    def kept(self) -> dict[str, object]:
        kept: dict[str, object] = {"title": self.title, "block": self.block}
        if self.entries:
            kept["entries"] = [entry.kept() for entry in self.entries]
        return kept


@dataclass
class Landmark:
    """A place the book names by what it is."""

    # what it is, as the book says it, such as "bodymatter", "toc" or, in an
    # older book, "text"
    type: str
    title: str
    block: int

    def kept(self) -> dict[str, object]:
        return {"type": self.type, "title": self.title, "block": self.block}


@dataclass
class Book:
    title: str
    author: str
    # as the book names it, such as "de"; empty if it does not
    language: str
    blocks: list[Block]
    # the picture on the cover with the kind of file it is, if there is one
    cover: tuple[bytes, str] | None = None
    # what the book lists of itself, empty if it does not
    contents: list[Entry] = field(default_factory=list)
    landmarks: list[Landmark] = field(default_factory=list)


def _bold(value: str, parent: bool) -> bool | None:
    """Whether a `font-weight` of `value` makes an element bold, in one whose
    parent is bold if `parent` is. None if it cannot be told."""
    value = value.strip().lower()
    if value in ("bold", "bolder"):
        return True
    if value in ("normal", "lighter"):
        return False
    if value in ("inherit", "unset"):
        return parent
    return int(value) >= 600 if value.isdigit() else None


def _italic(value: str, parent: bool) -> bool | None:
    """Whether a `font-style` of `value` makes an element italic, in one
    whose parent is italic if `parent` is. None if it cannot be told."""
    value = value.strip().lower()
    if value == "italic" or value.startswith("oblique"):
        return True
    if value == "normal":
        return False
    if value in ("inherit", "unset"):
        return parent
    return None


def font_size(value: str, parent: float) -> float | None:
    """The size, in pixels, that a `font-size` of `value` gives an element
    whose parent is written in `parent` pixels. None if it cannot be told."""
    value = value.strip().lower()
    if value in _NAMED_SIZES:
        return _NAMED_SIZES[value]
    if value == "smaller":
        return parent / 1.2
    if value == "larger":
        return parent * 1.2
    if value in ("inherit", "unset"):
        return parent
    length = _LENGTH.fullmatch(value)
    if not length:
        return None
    number, unit = float(length.group(1)), length.group(2)
    if unit in _UNITS:
        size = number * _UNITS[unit]
    elif unit == "em":
        size = number * parent
    elif unit == "rem":
        size = number * ROOT_PX
    elif unit == "%":
        size = number * parent / 100
    elif unit in ("ex", "ch"):
        size = number * parent / 2
    else:
        return None
    # text that is not to be seen is not written in a size
    return size if size > 0 else None


@dataclass(frozen=True)
class _Element:
    tag: str
    id: str = ""
    classes: frozenset[str] = frozenset()
    # the size its text is written in, in pixels
    px: float = ROOT_PX
    # whether what is in it is left out
    unread: bool = False
    bold: bool = False
    italic: bool = False
    # what the book says the parts it is in are, its own as well
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Compound:
    """The part of a selector that is about one element, such as `p.note`."""

    tag: str = ""
    id: str = ""
    classes: frozenset[str] = frozenset()

    def fits(self, element: _Element) -> bool:
        return (
            (not self.tag or self.tag == element.tag)
            and (not self.id or self.id == element.id)
            and self.classes <= element.classes
        )


@dataclass(frozen=True)
class _Rule:
    """What a style sheet says about how the elements a selector picks out
    are written: one of the properties that are read."""

    # each part with what ties it to the one before: ">" for a child, " " for
    # anything inside
    parts: tuple[tuple[str, _Compound], ...]
    property: str
    value: str
    # what decides which rule counts when several fit: whether it is marked
    # as important, how exact its selector is, and how far down it stands
    weight: tuple[int, int, int, int, int]

    def fits(self, path: list[_Element]) -> bool:
        """Whether the rule is about the last element of `path`, which is
        the element with everything it is inside of, from the outermost."""
        return self._fits(len(self.parts) - 1, path, len(path) - 1)

    def _fits(self, part: int, path: list[_Element], at: int) -> bool:
        tie, compound = self.parts[part]
        if not compound.fits(path[at]):
            return False
        if part == 0:
            return True
        if tie == ">":
            return at > 0 and self._fits(part - 1, path, at - 1)
        return any(self._fits(part - 1, path, above) for above in range(at))


def _declared(declarations: str) -> dict[str, tuple[str, bool]]:
    """What a block of declarations gives of the properties that are read,
    each with whether it is marked as important."""
    found: dict[str, tuple[str, bool]] = {}
    for declaration in declarations.split(";"):
        name, _, value = declaration.partition(":")
        name, value = name.strip().lower(), value.strip().lower()
        important = value.endswith("!important")
        value = value.removesuffix("!important").strip()
        if name in _PROPERTIES and value:
            found[name] = (value, important)
        elif name == "font":
            # "italic bold 1.2em/1.5 serif": the size is the part before the
            # "/", what comes before it is the style and the weight, and
            # whichever of those is not given is normal
            parts = value.split()
            for at, part in enumerate(parts):
                size = part.split("/")[0]
                if font_size(size, ROOT_PX) is None:
                    continue
                found["font-size"] = (size, important)
                found["font-weight"] = ("normal", important)
                found["font-style"] = ("normal", important)
                for before in parts[:at]:
                    if _bold(before, False):
                        found["font-weight"] = (before, important)
                    elif _italic(before, False):
                        found["font-style"] = (before, important)
                break
    return found


def _selector(text: str) -> tuple[tuple[str, _Compound], ...] | None:
    """A selector in parts, or None for one that is about more than which
    element is inside which, such as `p:first-letter` or `h1 + p`."""
    parts: list[tuple[str, _Compound]] = []
    tie = " "
    for token in text.replace(">", " > ").split():
        if token == ">":
            tie = ">"
            continue
        compound = _COMPOUND.fullmatch(token)
        if not compound or not token:
            return None
        tag = (compound.group(1) or "").lower()
        names = re.findall(r"([.#])([\w-]+)", compound.group(2))
        parts.append(
            (
                tie,
                _Compound(
                    "" if tag == "*" else tag,
                    next((name for kind, name in names if kind == "#"), ""),
                    frozenset(name for kind, name in names if kind == "."),
                ),
            )
        )
        tie = " "
    return tuple(parts) or None


def read_styles(css: str) -> list[_Rule]:
    """The rules of a style sheet that say how large something is written,
    or whether in bold or in italics, in the order they stand in."""
    rules: list[_Rule] = []
    _read_rules(re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL), rules)
    return rules


def _read_rules(css: str, rules: list[_Rule]) -> None:
    at = 0
    while True:
        opening = css.find("{", at)
        if opening == -1:
            return
        # what stands before a ";" is a line of its own, such as an @import
        prelude = css[at:opening].rpartition(";")[2].strip()
        depth, closing = 1, opening + 1
        while closing < len(css) and depth:
            depth += {"{": 1, "}": -1}.get(css[closing], 0)
            closing += 1
        body = css[opening + 1 : closing - 1]
        at = closing
        if prelude.startswith("@"):
            # what holds for the screen is among the rules, and nothing else
            # that starts with an "@" is
            if prelude.lower().startswith("@media") and "print" not in prelude.lower():
                _read_rules(body, rules)
            continue
        declared = _declared(body)
        for alternative in prelude.split(",") if declared else []:
            parts = _selector(alternative)
            if not parts:
                continue
            compounds = [compound for _, compound in parts]
            for property, (value, important) in declared.items():
                rules.append(
                    _Rule(
                        parts,
                        property,
                        value,
                        (
                            int(important),
                            sum(bool(compound.id) for compound in compounds),
                            sum(len(compound.classes) for compound in compounds),
                            sum(bool(compound.tag) for compound in compounds),
                            len(rules),
                        ),
                    )
                )


@dataclass
class _Paragraph:
    text: str
    px: float
    # the parts that lead somewhere: where each starts and ends in the text,
    # and where the page says it leads
    links: list[tuple[int, int, str]]
    # the element it is written in
    element: _Element
    # whether most of it is written in bold, and in italics
    bold: bool
    italic: bool


class _Page(HTMLParser):
    """Reads one page of a book into paragraphs, each with the size most of
    it is written in and whether most of it is bold and italic."""

    def __init__(self, style_sheet: Callable[[str], list[_Rule] | None]) -> None:
        """`style_sheet` gives the style sheet the page names, if there is
        such a file."""
        super().__init__(convert_charrefs=True)
        self.style_sheet = style_sheet
        self.paragraphs: list[_Paragraph] = []
        # The places in the page that have a name, for links to lead to:
        # the paragraph each is in or before, by its place among them.
        self.anchors: dict[str, int] = {}
        # the style sheets of the page, in the order it names them
        self._sheets: list[list[_Rule]] = []
        # the element being read, with everything it is inside of
        self._path: list[_Element] = []
        # the text of the paragraph being read, as far as it has been
        self._text = ""
        # how many of its letters are written in each size, and how many
        # in bold and in italics
        self._letters: Counter[float] = Counter()
        self._bold = 0
        self._italic = 0
        # the element its text is written in, once there is any text
        self._element: _Element | None = None
        # its parts that lead somewhere, and those that are still being read:
        # how deep in the path each is, where it leads and where it starts
        self._links: list[tuple[int, int, str]] = []
        self._leading: list[tuple[int, str, int]] = []
        # the text of a style sheet written into the page itself
        self._style: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        given = {name: value or "" for name, value in attrs}
        if tag == "link" and "stylesheet" in given.get("rel", "").lower().split():
            sheet = self.style_sheet(given.get("href", ""))
            if sheet is not None:
                self._sheets.append(sheet)
        elif tag == "style":
            self._style = []
        if tag == "br" and self._text:
            self._text = self._text.rstrip(" ") + "\n"
        if tag in _BLOCKS:
            self._end_paragraph()
        for name in (given.get("id"), given.get("name") if tag == "a" else None):
            if name:
                self.anchors.setdefault(name, len(self.paragraphs))
        if tag in _VOID:
            return
        inside = self._path[-1] if self._path else _Element("")
        own = [
            role
            for role in (
                given.get("epub:type", "") + " " + given.get("role", "")
            ).split()
            if role not in inside.roles
        ]
        self._path.append(
            _Element(
                tag,
                given.get("id", ""),
                frozenset(given.get("class", "").split()),
                inside.px,
                inside.unread or tag in _UNREAD or "hidden" in given,
                inside.bold,
                inside.italic,
                inside.roles + tuple(dict.fromkeys(own)),
            )
        )
        self._path[-1] = self._written(given.get("style", ""))
        if tag == "a" and given.get("href"):
            self._leading.append((len(self._path), given["href"], len(self._text)))

    def _written(self, style: str) -> _Element:
        """The element at the end of the path as it is written, by what is
        usual for it, by the style sheets and by its own style. It has been
        given how what it is in is written."""
        element = self._path[-1]
        said: dict[str, list[tuple[tuple[int, ...], str]]] = {
            property: [] for property in _PROPERTIES
        }
        for property, usual in _USUAL.items():
            if element.tag in usual:
                said[property].append(((-1,), usual[element.tag]))
        for number, sheet in enumerate(self._sheets):
            for rule in sheet:
                if rule.fits(self._path):
                    said[rule.property].append(
                        ((*rule.weight[:4], number, rule.weight[4]), rule.value)
                    )
        for property, (value, important) in _declared(style).items():
            # its own style counts for more than any selector
            said[property].append(((int(important), 1000), value))
        px, bold, italic = element.px, element.bold, element.italic
        # the one that counts most is tried last, and so is the one that stays
        for _, value in sorted(said["font-size"]):
            px = font_size(value, element.px) or px
        for _, value in sorted(said["font-weight"]):
            found = _bold(value, element.bold)
            bold = bold if found is None else found
        for _, value in sorted(said["font-style"]):
            found = _italic(value, element.italic)
            italic = italic if found is None else found
        return replace(element, px=px, bold=bold, italic=italic)

    def handle_endtag(self, tag: str) -> None:
        if tag == "style" and self._style is not None:
            self._sheets.append(read_styles("".join(self._style)))
            self._style = None
        if tag in _VOID or not any(element.tag == tag for element in self._path):
            return
        if tag in _BLOCKS:
            self._end_paragraph()
        # an element that was not ended ends with the one it is in
        while self._path.pop().tag != tag:
            pass
        while self._leading and self._leading[-1][0] > len(self._path):
            _, href, start = self._leading.pop()
            self._links.append((start, len(self._text), href))

    def handle_data(self, data: str) -> None:
        if self._style is not None:
            self._style.append(data)
        elif self._path and not self._path[-1].unread:
            piece = _SPACE.sub(" ", data)
            # spaces count once, and not at all where a line starts
            if not self._text or self._text[-1] in " \n":
                piece = piece.lstrip(" ")
            self._text += piece
            letters = len(piece.strip())
            if letters:
                self._letters[self._path[-1].px] += letters
                self._bold += letters * self._path[-1].bold
                self._italic += letters * self._path[-1].italic
                # the paragraph is written in the innermost element it starts in
                # that starts a paragraph
                self._element = self._element or next(
                    (each for each in reversed(self._path) if each.tag in _BLOCKS),
                    self._path[-1],
                )

    def close(self) -> None:
        super().close()
        self._end_paragraph()

    def _end_paragraph(self) -> None:
        text = self._text.rstrip(" \n")
        # a link that is still being read leads on from the next paragraph
        links = self._links + [
            (start, len(text), href) for _, href, start in self._leading
        ]
        self._leading = [(depth, href, 0) for depth, href, _ in self._leading]
        letters, self._letters = self._letters, Counter()
        bold, italic, self._bold, self._italic = self._bold, self._italic, 0, 0
        element, self._element = self._element, None
        self._text, self._links = "", []
        if not text or element is None:
            return
        # the letters that count are those of the text that is kept
        counted = sum(letters.values())
        self.paragraphs.append(
            _Paragraph(
                text,
                letters.most_common(1)[0][0],
                [
                    (start, min(end, len(text)), href)
                    for start, end, href in links
                    if start < min(end, len(text))
                ],
                element,
                bold * 2 > counted,
                italic * 2 > counted,
            )
        )


def _local(tag: str) -> str:
    """The name of an element of an XML file, without where it is from."""
    return tag.rpartition("}")[2]


@dataclass
class _Listed:
    """An entry of the table of contents, or a landmark, as the book has it:
    where it leads as the file it is in calls it."""

    title: str
    file: str
    href: str
    entries: list[_Listed] = field(default_factory=list)
    type: str = ""


def _children(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in element if _local(child.tag) == name]


def _words(element: ElementTree.Element | None) -> str:
    return (
        "" if element is None else _SPACE.sub(" ", "".join(element.itertext())).strip()
    )


def _listed_in_nav(
    root: ElementTree.Element, file: str
) -> tuple[list[_Listed], list[_Listed]]:
    """The table of contents and the landmarks the page that lists the others
    has, in a book of EPUB 3."""

    def entries(ol: ElementTree.Element) -> list[_Listed]:
        found = []
        for item in _children(ol, "li"):
            label = next(
                (child for child in item if _local(child.tag) in ("a", "span")), None
            )
            below = next(iter(_children(item, "ol")), None)
            found.append(
                _Listed(
                    _words(label),
                    file,
                    label.get("href", "") if label is not None else "",
                    entries(below) if below is not None else [],
                )
            )
        return found

    contents: list[_Listed] = []
    landmarks: list[_Listed] = []
    for nav in root.iter():
        if _local(nav.tag) != "nav":
            continue
        kinds = (nav.get(f"{_OPS}type") or nav.get("epub:type") or "").split()
        ol = next((each for each in nav.iter() if _local(each.tag) == "ol"), None)
        if ol is None:
            continue
        if "toc" in kinds and not contents:
            contents = entries(ol)
        elif "landmarks" in kinds and not landmarks:
            landmarks = [
                _Listed(
                    _words(link),
                    file,
                    link.get("href", ""),
                    type=link.get(f"{_OPS}type") or link.get("epub:type") or "",
                )
                for link in ol.iter()
                if _local(link.tag) == "a"
            ]
    return contents, landmarks


def _listed_in_ncx(root: ElementTree.Element, file: str) -> list[_Listed]:
    """The table of contents of a book of EPUB 2, which is in a file of its own."""

    def entries(parent: ElementTree.Element) -> list[_Listed]:
        found = []
        for point in _children(parent, "navPoint"):
            label = next(iter(_children(point, "navLabel")), None)
            content = next(iter(_children(point, "content")), None)
            found.append(
                _Listed(
                    _words(label),
                    file,
                    content.get("src", "") if content is not None else "",
                    entries(point),
                )
            )
        return found

    nav_map = next((each for each in root.iter() if _local(each.tag) == "navMap"), None)
    return entries(nav_map) if nav_map is not None else []


def _xml(archive: zipfile.ZipFile, name: str) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(_member(archive, name))
    except ElementTree.ParseError:
        raise BookError(f"{name} in it cannot be read") from None


def _member(archive: zipfile.ZipFile, name: str) -> bytes:
    try:
        if archive.getinfo(name).file_size > MAX_MEMBER_BYTES:
            raise BookError(f"{name} in it is too long")
        return archive.read(name)
    except KeyError:
        raise BookError(f"{name} is missing from it") from None
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise BookError(f"{name} in it cannot be read") from None


def _beside(file: str, href: str) -> str:
    """The name, in the book, of what `file` calls `href`."""
    path = unquote(href.partition("#")[0].partition("?")[0])
    return posixpath.normpath(posixpath.join(posixpath.dirname(file), path))


def _decoded(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def read_epub(data: bytes, name: str = "") -> Book:
    """The text of the EPUB file that `data` is, with how large each part of
    it is written. `name` is what the book is called if it does not say.
    Raises BookError."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise BookError("the file is not an EPUB book") from None
    with archive:
        if _CONTAINER not in archive.namelist():
            raise BookError("the file is not an EPUB book")
        package_name = next(
            (
                element.get("full-path") or ""
                for element in _xml(archive, _CONTAINER).iter()
                if _local(element.tag) == "rootfile"
            ),
            "",
        )
        package = _xml(archive, package_name)
        described: dict[str, str] = {}
        files: dict[str, str] = {}
        pages: list[str] = []
        # the pictures of the book: where each is and what it is for, by its id
        pictures: dict[str, tuple[str, str]] = {}
        named_cover = ""
        # the files that list what the book has, and its landmarks if it is
        # a book of EPUB 2, which has them in the package itself
        nav_file = ""
        ncx_file = ""
        guide: list[_Listed] = []
        for element in package.iter():
            kind = _local(element.tag)
            properties = (element.get("properties") or "").split()
            if kind in ("title", "creator", "language") and element.text:
                described.setdefault(kind, _SPACE.sub(" ", element.text).strip())
            elif kind == "meta" and element.get("name") == "cover":
                named_cover = element.get("content") or ""
            elif kind == "item" and element.get("media-type") in _COVER_TYPES:
                where = _beside(package_name, element.get("href") or "")
                pictures[element.get("id") or ""] = (
                    where,
                    element.get("media-type") or "",
                )
                if "cover-image" in properties:
                    named_cover = named_cover or element.get("id") or ""
            elif kind == "item" and element.get("media-type") in _PAGE_TYPES:
                # the page that lists the others says nothing of its own
                if "nav" in properties:
                    nav_file = _beside(package_name, element.get("href") or "")
                else:
                    files[element.get("id") or ""] = element.get("href") or ""
            elif kind == "item" and element.get("media-type") == _NCX_TYPE:
                ncx_file = _beside(package_name, element.get("href") or "")
            elif kind == "reference" and element.get("href"):
                guide.append(
                    _Listed(
                        element.get("title") or "",
                        package_name,
                        element.get("href") or "",
                        type=element.get("type") or "",
                    )
                )
            elif kind == "itemref" and element.get("idref") in files:
                pages.append(_beside(package_name, files[element.get("idref") or ""]))
        cover = None
        # a book that does not say which picture is on its cover may call it so
        for picture in [named_cover] + [
            each for each in pictures if "cover" in each.lower()
        ]:
            if picture in pictures:
                try:
                    cover = (
                        _member(archive, pictures[picture][0]),
                        pictures[picture][1],
                    )
                    break
                except BookError:
                    pass

        if _ENCRYPTION in archive.namelist():
            locked = {
                _beside("", element.get("URI") or "")
                for element in _xml(archive, _ENCRYPTION).iter()
                if _local(element.tag) == "CipherReference"
            }
            # a book may lock its fonts alone, which are not read anyway
            if locked.intersection(pages):
                raise BookError(
                    "the book is locked against copying, so its text cannot be read"
                )

        listed: list[_Listed] = []
        landmarks: list[_Listed] = []
        # a list that cannot be read is gone without, as the text is still there
        if nav_file:
            try:
                listed, landmarks = _listed_in_nav(_xml(archive, nav_file), nav_file)
            except BookError:
                pass
        if not listed and ncx_file:
            try:
                listed = _listed_in_ncx(_xml(archive, ncx_file), ncx_file)
            except BookError:
                pass
        landmarks = landmarks or guide

        sheets: dict[str, list[_Rule] | None] = {}

        def style_sheet(page: str, href: str) -> list[_Rule] | None:
            sheet = _beside(page, href)
            if sheet not in sheets:
                try:
                    sheets[sheet] = read_styles(_decoded(_member(archive, sheet)))
                except BookError:
                    sheets[sheet] = None
            return sheets[sheet]

        paragraphs: list[_Paragraph] = []
        # where each page starts among the paragraphs, and where each place
        # with a name in it is
        starts: dict[str, int] = {}
        anchors: dict[tuple[str, str], int] = {}
        # the page each paragraph is from
        from_page: list[str] = []
        for page in pages:
            reader = _Page(partial(style_sheet, page))
            reader.feed(_decoded(_member(archive, page)))
            reader.close()
            starts.setdefault(page, len(paragraphs))
            for anchor, place in reader.anchors.items():
                anchors.setdefault((page, anchor), len(paragraphs) + place)
            paragraphs += reader.paragraphs
            from_page += [page] * len(reader.paragraphs)
    if not paragraphs:
        raise BookError("there is no text in the book")

    def target(page: str, href: str) -> int | str | None:
        """Where a link in a page leads: a paragraph, by its place among
        them, an address outside the book, or nowhere that is known."""
        if href.lower().startswith(_OUTSIDE):
            return href
        if re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", href):
            return None
        file, _, anchor = href.partition("#")
        file = _beside(page, file) if file else page
        place = anchors.get((file, unquote(anchor)), starts.get(file))
        return None if place is None else min(place, len(paragraphs) - 1)

    # the size most of the book is written in is the one the others are
    # measured by
    letters: Counter[float] = Counter()
    for paragraph in paragraphs:
        letters[paragraph.px] += len(paragraph.text)
    usual = letters.most_common(1)[0][0]
    blocks: list[Block] = []
    for paragraph, page in zip(paragraphs, from_page):
        links = [
            (start, end, leads_to)
            for start, end, href in paragraph.links
            if (leads_to := target(page, href)) is not None
        ]
        written = paragraph.element
        blocks.append(
            Block(
                paragraph.text,
                round(paragraph.px / usual, 2),
                links,
                written.tag,
                sorted(written.classes),
                paragraph.bold,
                paragraph.italic,
                list(written.roles),
                page if starts.get(page) == len(blocks) else "",
            )
        )

    def entry(each: _Listed) -> Entry | None:
        """An entry of the table of contents with where it leads, which is
        where the first under it leads if it does not say. None for one
        that leads nowhere in the book."""
        below = [found for under in each.entries if (found := entry(under))]
        leads_to = target(each.file, each.href) if each.href else None
        if not isinstance(leads_to, int):
            leads_to = below[0].block if below else None
        return None if leads_to is None else Entry(each.title, leads_to, below)

    return Book(
        described.get("title") or name or "Untitled",
        described.get("creator", ""),
        described.get("language", ""),
        blocks,
        cover,
        [found for each in listed if (found := entry(each))],
        [
            Landmark(each.type, each.title, leads_to)
            for each in landmarks
            if isinstance(leads_to := target(each.file, each.href), int)
        ],
    )
