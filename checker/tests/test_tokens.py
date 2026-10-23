# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from tokens import BLOCK_SEPARATOR, block_tokens, count


def test_a_text_is_counted_in_tokens_fewer_than_its_letters() -> None:
    text = "Es war einmal ein König, der hatte drei Töchter."

    assert 0 < count(text) < len(text)


def test_a_special_token_in_a_text_is_counted_as_text() -> None:
    assert count("<|endoftext|>") > 1


def test_the_tokens_of_a_block_are_those_of_its_text_and_what_parts_it_from_the_next() -> (
    None
):
    blocks = [{"text": "Kapitel 1", "tag": "h1"}, {"text": "Es war einmal."}, {}]

    assert block_tokens(blocks) == [
        count("Kapitel 1" + BLOCK_SEPARATOR),
        count("Es war einmal." + BLOCK_SEPARATOR),
        count(BLOCK_SEPARATOR),
    ]
