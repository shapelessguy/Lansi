# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Reads a picture of a handwritten page into its words, each with where it
is written on the page.

The page is read by Google Cloud Vision, with the learner's key, which finds
each word on the picture before it reads it: where a word is comes from the
ink, not from a model that writes it out, so no word is placed where
nothing is written. What it reads is kept as it is, mistakes and all, as
they are the learner's to be corrected.

A mark such as a comma, which Vision reads as a word of its own, goes with
the word it is written against. A word is placed by the four corners of
the box around it, from its top left in the order it is read, as
`[[x, y], ...]` in pixels of the picture, and so is each of its letters,
which Vision finds in the same reading, so that a mark can be put on one
letter of a word, such as a wrong ending.
"""

from __future__ import annotations

import base64
import json
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

VISION_URL = "https://vision.googleapis.com/v1/images:annotate"
# how long Vision is given to read a page
TIMEOUT_SECS = 60
# what Vision says follows a symbol that ends a line
LINE_ENDS = frozenset({"EOL_SURE_SPACE", "LINE_BREAK", "HYPHEN"})

Box = list[list[int]]


class OcrError(ValueError):
    """A page that could not be read, with why."""


@dataclass
class Word:
    """A word read from a page: what it says, where it is, on which line and
    in which paragraph of the page, counted from 0, and how sure Vision is
    of it, from 0 to 1."""

    text: str
    box: Box
    line: int
    paragraph: int
    confidence: float
    # whether a space or the end of a line follows it, and whether the end
    # of a line does
    spaced: bool = True
    ends: bool = False
    # each of its letters, or such as a comma, with its box, the first
    # first, if Vision placed each of them
    letters: list[tuple[str, Box]] = field(default_factory=list)

    def kept(self) -> dict[str, Any]:
        kept: dict[str, Any] = {
            "text": self.text,
            "box": self.box,
            "line": self.line,
            "paragraph": self.paragraph,
            "confidence": round(self.confidence, 3),
        }
        if self.letters:
            kept["letters"] = [{"text": text, "box": box} for text, box in self.letters]
        return kept


@dataclass
class Page:
    """A page as it was read: the size of its picture and its words."""

    width: int
    height: int
    words: list[Word]

    def kept(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "words": [word.kept() for word in self.words],
        }


def read_picture(
    picture: bytes, width: int, height: int, key: str, hint: str | None
) -> Page:
    """The page read with `key` from `picture`, of that size, told it is
    written in the language `hint` names if there is one. Raises OcrError."""
    if not key:
        raise OcrError(
            "a handwritten page is read with a key of Google Cloud Vision,"
            " which is set in the settings, under Models"
        )
    return page_of(ask_vision(picture, key, hint), width, height)


def ask_vision(picture: bytes, key: str, hint: str | None) -> dict[str, Any]:
    """What Vision answers when it is asked to read the text of `picture`.
    Raises OcrError."""
    request: dict[str, Any] = {
        "image": {"content": base64.b64encode(picture).decode()},
        "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
    }
    if hint:
        request["imageContext"] = {"languageHints": [hint]}
    asked = urllib.request.Request(
        VISION_URL,
        data=json.dumps({"requests": [request]}).encode(),
        headers={"Content-Type": "application/json", "X-goog-api-key": key},
    )
    try:
        with urllib.request.urlopen(asked, timeout=TIMEOUT_SECS) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as error:
        raise OcrError(f"Google Cloud Vision: {_message_of(error)}") from None
    except (OSError, ValueError) as error:
        raise OcrError(f"Google Cloud Vision could not be asked: {error}") from None
    read = (answer.get("responses") or [{}])[0]
    if "error" in read:
        raise OcrError(f"Google Cloud Vision: {read['error'].get('message', '')}")
    return dict(read)


def _message_of(error: urllib.error.HTTPError) -> str:
    """What Vision says went wrong, or the status if it says nothing."""
    try:
        return str(json.load(error)["error"]["message"])
    except (OSError, ValueError, KeyError, TypeError):
        return f"it answered {error.code}"


def page_of(read: dict[str, Any], width: int, height: int) -> Page:
    """The page Vision's answer `read` describes, of a picture of that size."""
    words: list[Word] = []
    line = paragraph = 0
    pages = (read.get("fullTextAnnotation") or {}).get("pages") or []
    for block in pages[0].get("blocks", []) if pages else []:
        for each in block.get("paragraphs", []):
            starts = bool(words)
            for word in each.get("words", []):
                symbols = word.get("symbols", [])
                text = "".join(symbol.get("text", "") for symbol in symbols)
                if not text:
                    continue
                after = (
                    (symbols[-1].get("property") or {}).get("detectedBreak") or {}
                ).get("type")
                placed = [
                    (symbol["text"], _box(symbol["boundingBox"], width, height))
                    for symbol in symbols
                    if symbol.get("text") and symbol.get("boundingBox")
                ]
                if words and (starts or words[-1].ends):
                    line += 1
                    paragraph += starts
                    starts = False
                words.append(
                    Word(
                        text,
                        _box(word.get("boundingBox", {}), width, height),
                        line,
                        paragraph,
                        float(word.get("confidence", 0)),
                        bool(after),
                        after in LINE_ENDS,
                        # only if every letter was placed
                        placed if "".join(each[0] for each in placed) == text else [],
                    )
                )
    return Page(width, height, _with_marks_joined(words))


def _box(box: dict[str, Any], width: int, height: int) -> Box:
    """The four corners of a box of Vision's, kept within the picture."""
    corners = box.get("vertices") or []
    corners = (corners + [{}] * 4)[:4]
    return [
        [
            min(max(int(corner.get("x", 0)), 0), width),
            min(max(int(corner.get("y", 0)), 0), height),
        ]
        for corner in corners
    ]


def _is_mark(text: str) -> bool:
    """Whether `text` is only marks such as a comma or a quotation mark."""
    return all(unicodedata.category(char).startswith("P") for char in text)


def _with_marks_joined(words: list[Word]) -> list[Word]:
    """`words` with each mark written against a word, with no space between
    them, joined to it: a comma to the word before it, and an opening
    quotation mark to the word after it."""
    joined: list[Word] = []
    for word in words:
        before = joined[-1] if joined else None
        if (
            before is not None
            and before.line == word.line
            and not before.spaced
            and (_is_mark(word.text) or _is_mark(before.text))
        ):
            before.text += word.text
            before.box = [before.box[0], word.box[1], word.box[2], before.box[3]]
            before.confidence = min(before.confidence, word.confidence)
            before.spaced, before.ends = word.spaced, word.ends
            before.letters = (
                before.letters + word.letters if before.letters and word.letters else []
            )
        else:
            joined.append(word)
    return joined


def text_of(pages: list[dict[str, Any]]) -> str:
    """What the pages `pages`, as they are kept, say: each paragraph a line
    of its own, with a word cut by a hyphen at the end of a line joined
    again, and a blank line between paragraphs and between pages. A
    paragraph that ends on a letter, in the middle of a sentence, goes on
    with the next one, as Vision may part them where a line is short."""
    paragraphs: list[str] = []
    for page in pages:
        current: int | None = None
        line: int | None = None
        # a page starts a paragraph of its own
        for word in page.get("words") or []:
            text = word["text"]
            if word["paragraph"] != current:
                current = word["paragraph"]
                if paragraphs and paragraphs[-1][-1:].isalpha() and line is not None:
                    paragraphs[-1] += " " + text
                else:
                    paragraphs.append(text)
            elif (
                word["line"] != line
                and paragraphs[-1].endswith("-")
                and text[:1].islower()
            ):
                paragraphs[-1] = paragraphs[-1][:-1] + text
            else:
                paragraphs[-1] += " " + text
            line = word["line"]
    return "\n\n".join(paragraphs)
