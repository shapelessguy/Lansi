# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import json
from pathlib import Path

import pytest
from users import TOKEN_SECS, Users, take_vocabulary, user_directory
from vocabulary import Vocabularies


def write(file: Path, users: object) -> None:
    file.write_text(json.dumps(users), encoding="utf-8")


@pytest.fixture
def file(tmp_path: Path) -> Path:
    file = tmp_path / "users.json"
    write(file, {"ada": "a password", "ben": "another one"})
    return file


@pytest.fixture
def users(file: Path, tmp_path: Path) -> Users:
    return Users(file, tmp_path / "data")


def test_a_user_is_let_in_with_the_password_written_in_the_file(users: Users) -> None:
    assert users.check("ada", "a password")
    assert not users.check("ada", "A password")
    assert not users.check("ada", "another one")
    assert not users.check("ada", "")
    assert not users.check("eve", "a password")
    assert users.names() == ["ada", "ben"]


def test_a_change_to_the_file_counts_at_once(users: Users, file: Path) -> None:
    write(file, {"ada": "a better one", "cleo": "hers"})

    assert users.check("ada", "a better one")
    assert not users.check("ada", "a password")
    assert users.check("cleo", "hers")
    assert not users.check("ben", "another one")


@pytest.mark.parametrize("name", ["", "Ada", "a da", "../ada", "a" * 41])
def test_a_name_that_could_not_be_a_directory_of_its_own_is_passed_over(
    users: Users, file: Path, name: str
) -> None:
    write(file, {name: "a password", "ada": "a password"})

    assert users.names() == ["ada"]
    assert not users.check(name, "a password")


def test_a_user_without_a_password_cannot_log_in(users: Users, file: Path) -> None:
    write(file, {"ada": "", "ben": 123, "cleo": None})

    assert users.names() == []
    assert not users.check("ada", "")
    assert not users.check("ben", "123")


@pytest.mark.parametrize("content", ["", "not json", "[]", '"ada"'])
def test_nobody_can_log_in_while_the_file_is_not_as_it_should_be(
    users: Users, file: Path, content: str
) -> None:
    file.write_text(content, encoding="utf-8")

    assert users.names() == []
    assert not users.check("ada", "a password")


def test_nobody_can_log_in_without_the_file(tmp_path: Path) -> None:
    users = Users(tmp_path / "no-such-file.json", tmp_path)

    assert users.names() == []
    assert not users.check("ada", "a password")


def test_a_token_says_who_it_was_given_to(users: Users) -> None:
    assert users.user_of(users.token("ada")) == "ada"
    assert users.user_of(users.token("ben")) == "ben"


def test_a_token_that_was_made_up_or_changed_says_nobody(users: Users) -> None:
    name, expires, signature = users.token("ada").split(".")

    assert users.user_of("") is None
    assert users.user_of("ada") is None
    assert users.user_of(f"ben.{expires}.{signature}") is None
    assert users.user_of(f"{name}.{int(expires) + 1}.{signature}") is None
    assert users.user_of(f"{name}.{expires}.{'0' * len(signature)}") is None


def test_a_token_runs_out(file: Path, tmp_path: Path) -> None:
    clock = [1000.0]
    users = Users(file, tmp_path, now=lambda: clock[0])
    token = users.token("ada")

    clock[0] += TOKEN_SECS - 1
    still_good = users.user_of(token)
    clock[0] += 2

    assert still_good == "ada"
    assert users.user_of(token) is None


def test_a_token_is_no_good_once_its_user_is_taken_out_of_the_file(
    users: Users, file: Path
) -> None:
    token = users.token("ben")

    write(file, {"ada": "a password"})

    assert users.user_of(token) is None


def test_a_token_stays_good_when_the_server_is_started_again(
    users: Users, file: Path, tmp_path: Path
) -> None:
    token = users.token("ada")

    assert Users(file, tmp_path / "data").user_of(token) == "ada"


def test_a_token_of_another_server_says_nobody(
    users: Users, file: Path, tmp_path: Path
) -> None:
    elsewhere = Users(file, tmp_path / "elsewhere")

    assert users.user_of(elsewhere.token("ada")) is None


def test_the_vocabulary_kept_before_there_were_users_is_handed_to_one(
    tmp_path: Path,
) -> None:
    Vocabularies(tmp_path).of("German").save("noun", "Hund", {}, [])

    moved = take_vocabulary(tmp_path, "ada")
    again = take_vocabulary(tmp_path, "ada")

    assert (moved, again) == (["vocabulary.german.db"], [])
    of_ada = Vocabularies(user_directory(tmp_path, "ada"))
    assert of_ada.of("German").find("noun", "Hund") is not None
