# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from pathlib import Path

import pytest
from prompts import PROMPTS, PromptError, Prompts, read_prompts, variables_of

DIRECTORY = Path(__file__).resolve().parent / "prompts"


def write(tmp_path: Path, name: str, text: str) -> Prompts:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return Prompts(tmp_path)


def test_a_prompt_is_what_comes_under_its_heading_after_the_description(
    tmp_path: Path,
) -> None:
    prompts = write(
        tmp_path,
        "intake/greeting.md",
        "# Greeting\n\nWhat greets.\n\n- `$name`: who\n\n## Prompt\n\nHello $name.\n\nBye.\n",
    )
    assert prompts("intake.greeting", name="Anna") == "Hello Anna.\n\nBye."


def test_a_variant_is_found_by_its_name_after_that_of_its_file(tmp_path: Path) -> None:
    prompts = write(
        tmp_path,
        "topics.md",
        "# Topics\n\n## Prompt: one\n\nTopic: $topic.\n\n## Prompt: none\n\nNo topic.\n",
    )
    assert prompts("topics.one", topic="food") == "Topic: food."
    assert prompts.table("topics") == {"one": "Topic: $topic.", "none": "No topic."}


def test_a_value_is_left_out_when_the_prompt_does_not_use_it(tmp_path: Path) -> None:
    prompts = write(tmp_path, "short.md", "## Prompt\nBe brief.\n")
    assert prompts("short", language="German") == "Be brief."


def test_a_value_may_be_called_name(tmp_path: Path) -> None:
    prompts = write(tmp_path, "about.md", "## Prompt\nThe category $name.\n")
    assert prompts("about", name="noun") == "The category noun."


def test_braces_and_a_doubled_dollar_are_kept_as_they_are(tmp_path: Path) -> None:
    prompts = write(tmp_path, "reply.md", '## Prompt\nReply {"items": []} for $$5.\n')
    assert prompts("reply") == 'Reply {"items": []} for $5.'


def test_a_prompt_is_an_error_when_it_uses_a_value_not_given(tmp_path: Path) -> None:
    prompts = write(tmp_path, "greeting.md", "## Prompt\nHello $name in $language.\n")
    with pytest.raises(PromptError, match=r"\$language"):
        prompts("greeting", name="Anna")


def test_a_prompt_is_an_error_when_there_is_none_of_that_name(tmp_path: Path) -> None:
    prompts = write(tmp_path, "topics.md", "## Prompt: one\nTopic.\n")
    with pytest.raises(PromptError, match="no prompt topics.two"):
        prompts("topics.two")
    with pytest.raises(PromptError, match="no prompt others"):
        prompts("others")


def test_a_dollar_that_starts_no_variable_is_an_error() -> None:
    with pytest.raises(PromptError, match="starts no variable"):
        variables_of("It costs $ 5.")


@pytest.mark.parametrize(
    "path",
    sorted(DIRECTORY.rglob("*.md")),
    ids=lambda path: path.relative_to(DIRECTORY).as_posix(),
)
def test_every_file_of_prompts_has_prompts_that_can_be_filled_in(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# "), "a file starts with its title"
    prompts = read_prompts(text)
    assert prompts
    for variant, prompt in prompts.items():
        assert prompt, variant
        for variable in variables_of(prompt):
            assert f"`${variable}`" in text, f"${variable} is not described"


def test_the_prompts_of_the_server_have_the_kit_of_the_exercises() -> None:
    assert PROMPTS("kit.topics.one", topic="food") == "Topic: food."
