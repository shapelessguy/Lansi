# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""How many tokens a text takes when it is sent to a model, to tell whether
it fits in what the model takes in at once, such as a part of a book to be
transformed. Every model counts them its own way, and few say how: they are
counted as OpenAI's newer models count them, which comes near enough to the
others for telling what fits. The encoding is fetched once, the first time
it is needed, and kept where tiktoken keeps it.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from typing import Any

import tiktoken

ENCODING = "o200k_base"
# what the blocks of a part of a book are parted by when it is sent
BLOCK_SEPARATOR = "\n\n"


@cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(ENCODING)


def count(text: str) -> int:
    """The tokens of `text`, in which what reads as a special token, such
    as `<|endoftext|>`, is text like any other."""
    return len(_encoding().encode_ordinary(text))


def block_tokens(blocks: Sequence[dict[str, Any]]) -> list[int]:
    """The tokens of each of these blocks, kept as `books.Block.kept` keeps
    them, as it is sent in a part of the book: its text with what parts it
    from the next, so that the tokens of a part are those of its blocks. A
    picture, which is not sent, takes none."""
    texts = [block.get("text", "") + BLOCK_SEPARATOR for block in blocks]
    counted = [len(each) for each in _encoding().encode_ordinary_batch(texts)]
    return [0 if block.get("image") else each for block, each in zip(blocks, counted)]
