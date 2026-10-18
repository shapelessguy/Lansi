# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from pathlib import Path

import pytest
from prompts import PROMPTS, PromptError, Prompts, every_prompt, variables_of

CHECKER = Path(__file__).resolve().parent


def write(tmp_path: Path, text: str) -> Prompts:
    path = tmp_path / "prompts.toml"
    path.write_text(text, encoding="utf-8")
    return Prompts(path)


def test_a_prompt_is_filled_in_with_the_values_it_uses(tmp_path: Path) -> None:
    prompts = write(tmp_path, 'greeting = "Hello $name, at level ${level}A."\n')
    assert prompts("greeting", name="Anna", level="B") == "Hello Anna, at level BA."


def test_a_prompt_is_found_by_its_dotted_name_among_its_variants(
    tmp_path: Path,
) -> None:
    prompts = write(tmp_path, '[topics]\none = "Topic: $topic."\nnone = "No topic."\n')
    assert prompts("topics.one", topic="food") == "Topic: food."
    assert prompts.table("topics") == {"one": "Topic: $topic.", "none": "No topic."}


def test_a_value_is_left_out_when_the_prompt_does_not_use_it(tmp_path: Path) -> None:
    prompts = write(tmp_path, 'short = "Be brief."\n')
    assert prompts("short", language="German") == "Be brief."


def test_a_value_may_be_called_name(tmp_path: Path) -> None:
    prompts = write(tmp_path, 'about = "The category $name."\n')
    assert prompts("about", name="noun") == "The category noun."


def test_braces_and_a_doubled_dollar_are_kept_as_they_are(tmp_path: Path) -> None:
    prompts = write(tmp_path, "reply = 'Reply {\"items\": []} for $$5.'\n")
    assert prompts("reply") == 'Reply {"items": []} for $5.'


def test_a_line_ending_in_a_backslash_goes_on_without_a_break(tmp_path: Path) -> None:
    prompts = write(tmp_path, 'long = """\nOne \\\ntwo.\n\nThree."""\n')
    assert prompts("long") == "One two.\n\nThree."


def test_a_prompt_is_an_error_when_it_uses_a_value_not_given(tmp_path: Path) -> None:
    prompts = write(tmp_path, 'greeting = "Hello $name in $language."\n')
    with pytest.raises(PromptError, match=r"\$language"):
        prompts("greeting", name="Anna")


def test_a_prompt_is_an_error_when_it_is_not_in_the_file(tmp_path: Path) -> None:
    prompts = write(tmp_path, '[topics]\none = "Topic."\n')
    with pytest.raises(PromptError, match="no prompt topics.two"):
        prompts("topics.two")
    with pytest.raises(PromptError, match="not a prompt"):
        prompts("topics")


def test_a_dollar_that_starts_no_variable_is_an_error() -> None:
    with pytest.raises(PromptError, match="starts no variable"):
        variables_of("It costs $ 5.")


def prompt_files() -> list[Path]:
    return [CHECKER / "prompts.toml", *sorted(CHECKER.glob("exercises/*/prompts.toml"))]


@pytest.mark.parametrize("path", prompt_files(), ids=lambda path: path.parent.name)
def test_every_prompt_of_a_file_is_one_that_can_be_filled_in(path: Path) -> None:
    prompts = every_prompt(Prompts(path).table())
    assert prompts
    for name, text in prompts.items():
        for variable in variables_of(text):
            assert variable.isidentifier(), (name, variable)


def test_the_prompts_of_the_server_have_the_kit_of_the_exercises() -> None:
    assert PROMPTS("kit.topics.one", topic="food") == "Topic: food."
