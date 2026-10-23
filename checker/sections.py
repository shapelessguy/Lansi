# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The sections of a book, a tree of them, for finding one's way in it and
for telling which parts of it make up a version of it, such as the text
alone without what was put around it.

A section is a stretch of the blocks of the book, from where it starts to
where the next that is not under it does. The table of contents of the book,
where it has one, gives the sections it lists, which are the surest. Within
each, and in a book without one, the headings give the rest: a block is a
heading by the element it is written in, or by being short and larger than
the text, or bold in a book that has no elements for its headings, as in
one that has them a bold line is something else, such as a word in a list. A heading is under the one before it if it is written
smaller, or as a lower heading, or less bold; it ends where one written as
large or larger comes. Blocks before the first section are a section with no
title, so that every block is in one, and a section with no blocks, such as
an entry that leads where the next one does, is left out.

Sections are worked out from the blocks each time, so a better way of
working them out holds for every book, and the blocks they are made of are
kept by their places, which do not change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# the elements a heading is written in, each with how high a heading it is
_HEADINGS = {f"h{level}": level for level in range(1, 7)}
# how much larger than the text a block is written for it to be a heading
_LARGER = 1.05
# no heading is any longer
MAX_HEADING = 200
# as many short bold lines one after the other as this are a list, such as
# one of words, and not headings
_LIST = 3
_LETTER = re.compile(r"\w")


@dataclass
class Section:
    title: str
    # the first of its blocks, and the one after its last, by their places
    start: int
    end: int
    sections: list[Section] = field(default_factory=list)

    def kept(self) -> dict[str, object]:
        kept: dict[str, object] = {
            "title": self.title,
            "start": self.start,
            "end": self.end,
        }
        if self.sections:
            kept["sections"] = [section.kept() for section in self.sections]
        return kept


def _style(block: dict[str, Any]) -> tuple[float, int, bool]:
    """How a heading is written, to tell which of two is the higher: the
    larger, then the higher heading, then the bold one."""
    return (
        -float(block.get("size", 1)),
        _HEADINGS.get(block.get("tag", "p"), len(_HEADINGS) + 1),
        not block.get("bold", False),
    )


def _may_head(block: dict[str, Any], bold_heads: bool) -> bool:
    """Whether a block may be a heading, a bold one if `bold_heads`."""
    text = block.get("text", "")
    if len(text) > MAX_HEADING or "\n" in text or not _LETTER.search(text):
        return False
    if block.get("tag", "p") in _HEADINGS:
        return True
    if float(block.get("size", 1)) > _LARGER:
        return True
    # a bold line is a heading unless it reads as the start of a sentence
    # that goes on
    return (
        bold_heads
        and bool(block.get("bold"))
        and not text.rstrip().endswith((",", ";", ":"))
    )


def headings(blocks: list[dict[str, Any]]) -> dict[int, int]:
    """The blocks that are headings, by their places, each with how high it
    is: 0 for the highest, and more for each that is under another."""
    marked = any(block.get("tag", "p") in _HEADINGS for block in blocks)
    found = [
        place for place, block in enumerate(blocks) if _may_head(block, not marked)
    ]
    # a run of lines written alike that are headings only by their looks is
    # a list
    in_list: set[int] = set()
    run: list[int] = []
    for place in [*found, -2]:
        alike = (
            run
            and place == run[-1] + 1
            and _style(blocks[place]) == _style(blocks[run[-1]])
            and blocks[place].get("tag", "p") not in _HEADINGS
        )
        if not alike:
            if len(run) >= _LIST:
                in_list.update(run)
            run = []
        if place >= 0 and blocks[place].get("tag", "p") not in _HEADINGS:
            run.append(place)
    found = [place for place in found if place not in in_list]
    styles = sorted({_style(blocks[place]) for place in found})
    return {place: styles.index(_style(blocks[place])) for place in found}


def _plain(text: str) -> str:
    return " ".join(_LETTER.findall(text.casefold()))


def _by_headings(
    blocks: list[dict[str, Any]],
    ranks: dict[int, int],
    start: int,
    end: int,
    title: str = "",
) -> list[Section]:
    """The sections the headings make of the blocks from `start` to `end`,
    leaving out a heading that says no more than `title`, the title of the
    section they are in."""
    top: list[Section] = []
    # the sections that have not ended yet, each with how high its heading is
    open_: list[tuple[Section, int]] = []
    for place in range(start, end):
        # the heading the title of the section is taken from, where the
        # table of contents leads just before it
        repeated = place - start < 2 and _plain(blocks[place]["text"]) in _plain(title)
        if place not in ranks or (title and repeated):
            continue
        while open_ and open_[-1][1] >= ranks[place]:
            open_.pop()[0].end = place
        section = Section(blocks[place]["text"], place, end)
        (open_[-1][0].sections if open_ else top).append(section)
        open_.append((section, ranks[place]))
    return top


def _from_contents(entries: list[dict[str, Any]], count: int) -> list[Section]:
    """The sections the table of contents lists, in a book of `count`
    blocks. An entry that leads back before the one listed before it is
    left out, with those under it, as no stretch of the book is its own."""
    flat: list[tuple[int, str, int]] = []

    def walk(listed: list[dict[str, Any]], depth: int) -> None:
        for entry in listed:
            block = entry.get("block")
            if isinstance(block, int) and 0 <= block < count:
                if not flat or block >= flat[-1][2]:
                    flat.append((depth, entry.get("title", ""), block))
                    walk(entry.get("entries", []), depth + 1)

    walk(entries, 0)
    top: list[Section] = []
    open_: list[tuple[Section, int]] = []
    for depth, title, block in flat:
        while open_ and open_[-1][1] >= depth:
            open_.pop()[0].end = block
        section = Section(title, block, count)
        (open_[-1][0].sections if open_ else top).append(section)
        open_.append((section, depth))
    return top


def _without_empty(sections: list[Section]) -> list[Section]:
    kept = []
    for section in sections:
        section.sections = _without_empty(section.sections)
        if section.start < section.end:
            kept.append(section)
    return kept


def _filled(
    sections: list[Section], blocks: list[dict[str, Any]], ranks: dict[int, int]
) -> None:
    """Gives each section of the table of contents the sections the
    headings make of what is in it before the first that is listed under
    it, or of all of it if none is."""
    for section in sections:
        _filled(section.sections, blocks, ranks)
        ahead = section.sections[0].start if section.sections else section.end
        section.sections = [
            *_by_headings(blocks, ranks, section.start + 1, ahead, section.title),
            *section.sections,
        ]


def outline(
    blocks: list[dict[str, Any]], contents: list[dict[str, Any]] | None = None
) -> list[Section]:
    """The sections of a book of these blocks, kept as `books.Block.kept`
    keeps them, with its table of contents kept as `books.Entry.kept` keeps
    each entry, if it has one."""
    ranks = headings(blocks)
    listed = _from_contents(contents or [], len(blocks))
    if listed:
        _filled(listed, blocks, ranks)
        top = [*_by_headings(blocks, ranks, 0, listed[0].start), *listed]
    else:
        top = _by_headings(blocks, ranks, 0, len(blocks))
    top = _without_empty(top)
    first = top[0].start if top else len(blocks)
    if first > 0:
        top.insert(0, Section("", 0, first))
    return top
