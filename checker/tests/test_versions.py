# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from typing import Any

import pytest
from models import Model
from profiling import ProfileError, spent_by
from sections import Section
from tokens import count
from versions import (
    Keys,
    PartProgress,
    TransformError,
    kept_stretches,
    matches,
    part_blocks,
    part_sections,
    read_begun,
    read_part,
    stripped,
    transform_part,
    transform_parts,
    transformed,
    transformed_parts,
)

BOOK = {
    "blocks": [
        {"text": "Vorwort", "size": 1.5, "tag": "h1"},
        {"text": "Danke.", "size": 1},
        {"text": "Kapitel 1", "size": 1.5, "tag": "h1", "bold": True},
        {"text": "Es war einmal ein Hund.", "size": 1, "links": [[0, 2, 1]]},
    ],
    "contents": [
        {"title": "Vorwort", "block": 0},
        {"title": "Kapitel 1", "block": 2},
    ],
    "landmarks": [],
}
MODEL = Model("thinker", key="a key")


# what the model answers when it settles how to transform a part
PLAN = "Plain words."


def answering(*said: str, reasoning: str = "", cut: int = 0) -> Any:
    """A model that streams its answer to each request to write a part, the
    next of `said`, in two pieces after `reasoning` if it reasons, and keeps
    what it was sent. A request to settle how to transform a part is
    answered with `reasoning` and PLAN, and kept apart. The first `cut`
    answers that write break off, as one that reached the most a model may
    write at once does."""
    sent: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []
    # the parts are sent at the same time
    lock = threading.Lock()

    def stream(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        plan = "Write none of the part itself" in body["messages"][0]["content"]
        with lock:
            (planned if plan else sent).append(body)
            answer = PLAN if plan else said[len(sent) - 1]
        if reasoning and body["reasoning"].get("enabled", True):
            yield {"choices": [{"delta": {"reasoning": reasoning}}]}
        half = len(answer) // 2
        for content in (answer[:half], answer[half:]):
            yield {"choices": [{"delta": {"content": content}}]}
        finish = "length" if not plan and len(sent) <= cut else "stop"
        yield {"choices": [{"delta": {}, "finish_reason": finish}]}
        yield {
            "choices": [],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3, "cost": 0.01},
        }

    stream.sent = sent  # type: ignore[attr-defined]
    stream.planned = planned  # type: ignore[attr-defined]
    return stream


def test_the_stretches_to_keep_are_taken_as_they_were_asked_for() -> None:
    assert kept_stretches([[0, 2], [2, 3], [5, 6]], 6) == [(0, 2), (2, 3), (5, 6)]


@pytest.mark.parametrize(
    "keep",
    [
        [],
        "all",
        [[0]],
        [[0, 1.5]],
        [[2, 1]],
        [[0, 7]],
        [[3, 4], [0, 1]],
        [[0, 3], [2, 4]],
    ],
)
def test_stretches_that_are_not_in_order_or_in_the_book_are_refused(
    keep: object,
) -> None:
    with pytest.raises(ValueError, match="stretch|keeps some"):
        kept_stretches(keep, 6)


def test_a_stripped_version_has_the_blocks_kept_without_links_and_its_contents() -> (
    None
):
    book = {
        "blocks": [
            {"text": "Kapitel 1", "size": 1.5, "tag": "h1"},
            {
                "text": "Es war einmal.",
                "size": 1,
                "links": [[7, 14, 3], [0, 2, "https://x"]],
            },
            {"text": "Vokabeln", "size": 0.9, "tag": "h3"},
            {"text": "einmal: once", "size": 1},
            {"text": "Kapitel 2", "size": 1.5, "tag": "h1"},
        ],
        "contents": [
            {
                "title": "Kapitel 1",
                "block": 0,
                "entries": [{"title": "Vokabeln", "block": 2}],
            },
            {
                "title": "Anhang",
                "block": 3,
                "entries": [{"title": "Kapitel 2", "block": 4}],
            },
        ],
        "landmarks": [
            {"type": "bodymatter", "title": "Text", "block": 1},
            {"type": "glossary", "title": "Wörter", "block": 3},
        ],
    }

    blocks, contents, landmarks = stripped(book, [(0, 2), (4, 5)])

    assert blocks == [
        {"text": "Kapitel 1", "size": 1.5, "tag": "h1"},
        {"text": "Es war einmal.", "size": 1},
        {"text": "Kapitel 2", "size": 1.5, "tag": "h1"},
    ]
    assert contents == [
        {"title": "Kapitel 1", "block": 0},
        {"title": "Kapitel 2", "block": 2},
    ]
    assert landmarks == [{"type": "bodymatter", "title": "Text", "block": 1}]
    assert book["blocks"][1]["links"] == [[7, 14, 3], [0, 2, "https://x"]]


def test_the_parts_to_transform_are_each_in_order_and_share_no_block() -> None:
    assert transformed_parts([[[0, 2]], [[4, 5], [6, 7]]], 8) == [
        [(0, 2)],
        [(4, 5), (6, 7)],
    ]
    with pytest.raises(ValueError, match="two parts"):
        transformed_parts([[[0, 3]], [[2, 4]]], 8)
    with pytest.raises(ValueError, match="transforms some"):
        transformed_parts([], 8)


def test_a_transformed_version_keeps_how_each_block_is_written_with_what_the_model_wrote() -> (
    None
):
    written = [{"2": "Chapter 1", "3": "Once there was a dog."}]

    kept, kept_contents, _ = transformed(BOOK, [[(2, 4)]], written, untouched_kept=True)
    left, left_contents, _ = transformed(
        BOOK, [[(2, 4)]], written, untouched_kept=False
    )

    assert kept == [
        {"text": "Vorwort", "size": 1.5, "tag": "h1"},
        {"text": "Danke.", "size": 1},
        {"text": "Chapter 1", "size": 1.5, "tag": "h1", "bold": True},
        {"text": "Once there was a dog.", "size": 1},
    ]
    assert kept_contents == [
        {"title": "Vorwort", "block": 0},
        {"title": "Chapter 1", "block": 2},
    ]
    assert [block["text"] for block in left] == ["Chapter 1", "Once there was a dog."]
    assert left_contents == [{"title": "Chapter 1", "block": 0}]


def test_a_transformed_version_keeps_the_structure_the_model_wrote_when_it_changed_it() -> (
    None
):
    written = [{"9": "Foreword", "0": "Foreword", "2": "Chapter 1", "x": "A dog."}]

    blocks, contents, _ = transformed(BOOK, [[(0, 4)]], written, untouched_kept=True)

    assert [block["text"] for block in blocks] == [
        "Foreword",
        "Foreword",
        "Chapter 1",
        "A dog.",
    ]
    assert blocks[0] == {"text": "Foreword", "size": 1}
    assert blocks[3] == {"text": "A dog.", "size": 1}
    assert contents == [
        {"title": "Foreword", "block": 1},
        {"title": "Chapter 1", "block": 2},
    ]
    assert not matches(BOOK, [(0, 4)], written[0])
    assert matches(BOOK, [(2, 4)], {"2": "Chapter 1", "3": "A dog."})


def test_a_part_is_sent_as_its_blocks_by_their_places_with_the_instructions() -> None:
    chat = answering('```json\n{"2": "Chapter 1", "3": "Once there was a dog."}\n```')
    blocks = part_blocks(BOOK, [(2, 4)])

    written, used = transform_part(
        "Translate it into English.", blocks, MODEL, stream=chat
    )

    assert blocks == {"2": "Kapitel 1", "3": "Es war einmal ein Hund."}
    assert written == {"2": "Chapter 1", "3": "Once there was a dog."}
    (plan,) = chat.planned
    (body,) = chat.sent
    planning = plan["messages"][0]["content"]
    prompt = body["messages"][0]["content"]
    assert (plan["model"], plan["reasoning"]) == ("thinker", {"max_tokens": 16_000})
    assert (body["model"], body["reasoning"]) == ("thinker", {"enabled": False})
    assert body["stream"] is True
    assert "at most 16000 tokens to reason in" in planning
    for each in (planning, prompt):
        assert "Translate it into English." in each
        assert json.dumps(blocks, ensure_ascii=False, indent=0) in each
        assert "\n\n\n" not in each
    # what is the same in both is sent first, for the model to keep it
    assert planning[: planning.index("The part is going")] in prompt
    assert PLAN in prompt
    assert 'from the key "2" to the key "3"' in prompt
    assert [(each.input_tokens, each.output_tokens, each.cost) for each in used] == [
        (9, 3, 0.01),
        (9, 3, 0.01),
    ]


def test_a_part_is_written_a_section_at_a_time_each_knowing_those_before() -> None:
    blocks = {"0": "Vorwort", "1": "Danke.", "2": "Kapitel 1", "3": "Ein Hund."}
    chat = answering(
        '{"0": "Foreword", "1": "Thanks.", "2": "Chapter 1"}',
        '{"2": "Chapter 1", "3": "A dog."}',
    )
    progress = PartProgress()

    written, used = transform_part(
        "Translate it.",
        blocks,
        MODEL,
        progress=progress,
        stream=chat,
        sections=[["0", "1"], ["2", "3"]],
    )

    # what the model wrote of another section is left to that section
    assert written == {"0": "Foreword", "1": "Thanks.", "2": "Chapter 1", "3": "A dog."}
    assert (len(chat.planned), len(used)) == (1, 3)
    first, second = (body["messages"][0]["content"] for body in chat.sent)
    assert 'from the key "0" to the key "1"' in first
    assert "(nothing yet)" in first
    assert 'from the key "2" to the key "3"' in second
    assert '"0": "Foreword",\n"1": "Thanks."' in second
    assert '"2": "Chapter 1"' not in second
    assert (progress.sections, progress.finished, progress.round) == (2, 2, 2)


def test_a_part_is_divided_by_the_highest_sections_it_has_more_than_one_of() -> None:
    book = [
        Section(
            "Teil",
            0,
            9,
            [Section("Eins", 1, 4), Section("Zwei", 4, 7), Section("Drei", 7, 9)],
        ),
        Section("Anhang", 9, 11),
    ]

    # the heading of the section they are under goes with the first
    assert part_sections(range(9), book) == [[0, 1, 2, 3], [4, 5, 6], [7, 8]]
    assert part_sections([2, 3, 5], book) == [[2, 3], [5]]
    assert part_sections([5, 6], book) == [[5, 6]]
    assert part_sections([7, 8, 9, 10], book) == [[7, 8], [9, 10]]
    assert part_sections([0, 1], []) == [[0, 1]]


def test_what_the_model_wrote_of_a_part_is_read_as_text_by_key() -> None:
    assert read_part('{"1": "Eins", "2": 2, "3": null}') == {"1": "Eins", "2": "2"}
    with pytest.raises(TransformError, match="JSON object"):
        read_part("Here is the story: once upon a time")


def test_a_part_the_model_did_not_write_as_json_fails_with_what_asking_used() -> None:
    with pytest.raises(TransformError) as raised:
        transform_part(
            "Translate it.", {"0": "Hallo"}, MODEL, stream=answering("Hello")
        )

    assert [used.input_tokens for used in spent_by(raised.value)] == [9, 9]


def test_a_part_is_not_sent_without_a_model_or_a_key() -> None:
    with pytest.raises(TransformError, match="key"):
        transform_part(
            "Translate it.", {"0": "Hallo"}, Model("thinker"), stream=answering()
        )


def test_the_parts_are_each_written_and_a_failed_one_fails_them_all_with_all_used() -> (
    None
):
    steps: list[None] = []
    reports: list[list[dict[str, Any]]] = []
    chat = answering('{"0": "Foreword"}', '{"2": "Chapter 1"}')

    written, used = transform_parts(
        "Translate it.",
        BOOK,
        [[(0, 1)], [(2, 3)]],
        MODEL,
        lambda: steps.append(None),
        reports.append,
        stream=chat,
    )
    with pytest.raises(TransformError) as raised:
        transform_parts(
            "Translate it.",
            BOOK,
            [[(0, 1)], [(2, 3)]],
            MODEL,
            lambda: None,
            stream=answering('{"0": "Foreword"}', "no JSON"),
        )

    assert sorted(written, key=list) == [{"0": "Foreword"}, {"2": "Chapter 1"}]
    # each part is planned, and then written
    assert (len(used), len(steps)) == (4, 2)
    assert len(spent_by(raised.value)) == 4
    assert [each["state"] for each in reports[0]] == ["waiting", "waiting"]
    assert [each["state"] for each in reports[-1]] == ["done", "done"]


def test_the_tokens_a_part_is_reasoned_and_written_in_are_counted_as_they_stream() -> (
    None
):
    answer = '{"0": "Foreword"}'
    progress = PartProgress()
    seen: list[tuple[str, int, int]] = []

    transform_part(
        "Translate it.",
        {"0": "Vorwort"},
        MODEL,
        progress=progress,
        report=lambda: seen.append(
            (progress.state, progress.reasoning, progress.written)
        ),
        stream=answering(answer, reasoning="It is a heading."),
    )

    thought = count("It is a heading.")
    assert seen[0] == ("thinking", 0, 0)
    assert seen[1] == ("thinking", thought, 0)
    # what the model decided is not written of the part
    assert ("thinking", thought, 0) == seen[3]
    assert seen[4] == ("writing", thought, 0)
    assert seen[-1] == ("done", thought, progress.written)
    assert progress.estimated == progress.written
    assert progress.written == count(answer[:8]) + count(answer[8:])
    assert progress.expected == count(
        json.dumps({"0": "Vorwort"}, ensure_ascii=False, indent=0)
    )


def test_the_tokens_a_part_is_written_in_are_estimated_once_a_later_key_is_begun() -> (
    None
):
    blocks = {
        "0": "Ein kurzer Satz.",
        "1": "Noch ein Satz, der länger ist als der erste.",
    }
    progress = PartProgress()
    follow = Keys(blocks, progress)
    sent = [
        count(json.dumps({key: value}, ensure_ascii=False))
        for key, value in blocks.items()
    ]

    for piece in ('```json\n{"0": "A sho', 'rt sentence."', ', "1": "Ano'):
        estimated = progress.estimated
        progress.written += count(piece)
        follow(piece)

    assert estimated == 0
    assert progress.estimated == round(progress.written * sum(sent) / sent[0])


def test_a_part_is_reasoned_over_in_at_most_16k_tokens_whatever_budget_it_is_given() -> (
    None
):
    chat = answering('{"0": "Foreword"}')
    progress = PartProgress()

    transform_part(
        "Translate it.",
        {"0": "Vorwort"},
        MODEL,
        progress=progress,
        stream=chat,
        budget=100_000,
    )
    transform_part(
        "Translate it.",
        {"0": "Vorwort"},
        MODEL,
        think=False,
        stream=answering('{"0": "Foreword"}'),
        budget=100_000,
    )

    assert chat.planned[0]["reasoning"] == {"max_tokens": 16_000}
    assert "at most 16000 tokens to reason" in chat.planned[0]["messages"][0]["content"]
    assert progress.budget == 16_000


def test_the_blocks_written_whole_are_read_of_an_answer_that_broke_off() -> None:
    assert read_begun('```json\n{"1": "Eins", "2": "Zw\\"ei", "3": "Dr') == {
        "1": "Eins",
        "2": 'Zw"ei',
    }
    assert read_begun('{"1": "Eins", "2"') == {"1": "Eins"}
    assert read_begun('{\n"1": "Eins"\n}') == {"1": "Eins"}
    assert read_begun("Here it is") == {}


def test_an_answer_that_broke_off_is_taken_up_without_reasoning_where_it_stopped() -> (
    None
):
    blocks = {"0": "Vorwort", "1": "Danke.", "2": "Kapitel 1"}
    chat = answering(
        '{"0": "Foreword", "1": "Thank',
        '{"1": "Thanks.", "2": "Chapter 1"}',
        reasoning="Short and plain.",
        cut=1,
    )
    progress = PartProgress()

    written, used = transform_part(
        "Translate it.", blocks, MODEL, progress=progress, stream=chat
    )

    assert written == {"0": "Foreword", "1": "Thanks.", "2": "Chapter 1"}
    assert (len(used), progress.round) == (3, 2)
    first, second = chat.sent
    assert first["reasoning"] == second["reasoning"] == {"enabled": False}
    taken_up = second["messages"][0]["content"]
    assert 'from the key "1"' in taken_up
    assert "Short and plain." in taken_up
    assert '"0": "Foreword"' in taken_up
    assert 'Thank"' not in taken_up


def test_an_answer_that_breaks_off_before_a_whole_block_fails_the_part() -> None:
    with pytest.raises(TransformError, match="whole block") as raised:
        transform_part(
            "Translate it.",
            {"0": "Vorwort", "1": "Danke."},
            MODEL,
            stream=answering('{"0": "Fore', cut=1),
        )

    assert len(spent_by(raised.value)) == 2


def test_a_part_is_written_without_reasoning_if_asked_or_with_it_if_the_model_must() -> (
    None
):
    sent: list[dict[str, Any]] = []
    answer = answering('{"0": "Foreword"}')

    def stream(body: dict[str, Any], model: Model) -> Iterator[dict[str, Any]]:
        sent.append(json.loads(json.dumps(body)))
        if not body["reasoning"].get("enabled", True):
            raise ProfileError("OpenRouter refused it (400): reasoning is mandatory")
        result: Iterator[dict[str, Any]] = answer(body, model)
        return result

    written, _ = transform_part(
        "Translate it.", {"0": "Vorwort"}, MODEL, think=False, stream=stream
    )

    assert written == {"0": "Foreword"}
    assert [body["reasoning"] for body in sent] == [
        {"enabled": False},
        {"max_tokens": 16_000},
    ]


PICTURE = {"text": "", "size": 1, "tag": "img", "image": "ab" * 12 + ".png"}
ILLUSTRATED = {
    **BOOK,
    "blocks": [*BOOK["blocks"][:3], PICTURE, BOOK["blocks"][3], PICTURE],
}


def test_a_picture_is_not_sent_to_the_model_and_stays_where_it_was() -> None:
    written = [{"2": "Chapter 1", "4": "Once there was a dog."}]

    sent = part_blocks(ILLUSTRATED, [(2, 6)])
    blocks, _, _ = transformed(ILLUSTRATED, [[(2, 6)]], written, untouched_kept=False)

    assert sent == {"2": "Kapitel 1", "4": "Es war einmal ein Hund."}
    assert [block.get("image") or block["text"] for block in blocks] == [
        "Chapter 1",
        PICTURE["image"],
        "Once there was a dog.",
        PICTURE["image"],
    ]
    assert matches(ILLUSTRATED, [(2, 6)], written[0])


def test_a_part_of_pictures_alone_is_kept_without_asking_the_model() -> None:
    stream = answering('{"2": "Chapter 1"}')

    written, used = transform_parts(
        "Translate.",
        ILLUSTRATED,
        [[(2, 3)], [(5, 6)]],
        MODEL,
        lambda: None,
        stream=stream,
    )
    blocks, _, _ = transformed(ILLUSTRATED, [[(2, 3)], [(5, 6)]], written, False)

    assert written == [{"2": "Chapter 1"}, {}]
    assert len(stream.sent) == 1 and len(used) == 2
    assert [block.get("image") or block["text"] for block in blocks] == [
        "Chapter 1",
        PICTURE["image"],
    ]


def test_a_key_the_model_writes_for_a_picture_does_not_show_it_twice() -> None:
    # the picture at 3 left a gap among the keys the model was sent
    written = [{"2": "Chapter 1", "3": "", "4": "Once there was a dog.", "5": ""}]

    blocks, _, _ = transformed(ILLUSTRATED, [[(2, 6)]], written, untouched_kept=False)

    assert [block.get("image") or block["text"] for block in blocks] == [
        "Chapter 1",
        PICTURE["image"],
        "Once there was a dog.",
        PICTURE["image"],
    ]
    assert matches(ILLUSTRATED, [(2, 6)], written[0])


def test_a_block_the_model_wrote_as_nothing_is_left_out() -> None:
    written = [{"2": "Chapter 1", "3": " "}]

    blocks, _, _ = transformed(BOOK, [[(2, 4)]], written, untouched_kept=False)

    assert [block["text"] for block in blocks] == ["Chapter 1"]
