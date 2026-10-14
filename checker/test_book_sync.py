# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

import os
from pathlib import Path

import pytest
from book_sync import BookSync, Unread, book_id, books_in
from storage import UserStore
from test_books import epub, page


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """A folder with a book in it, and another in a folder inside it."""
    folder = tmp_path / "OneDrive" / "Books"
    (folder / "German" / "Stories").mkdir(parents=True)
    (folder / "hund.epub").write_bytes(book("Der Hund"))
    (folder / "German" / "Stories" / "Katze.EPUB").write_bytes(book("Die Katze"))
    (folder / "German" / "notes.txt").write_text("not a book")
    return folder


@pytest.fixture
def store(tmp_path: Path) -> UserStore:
    return UserStore(tmp_path / "ada")


@pytest.fixture
def sync(store: UserStore, folder: Path) -> BookSync:
    """What keeps the books of the store those of the folder, which is
    looked through whenever it is told to, and not by itself."""
    sync = BookSync(store, background=lambda job: job())
    sync.choose(str(folder))
    return sync


def book(title: str) -> bytes:
    return epub(page("<p>Text.</p>"), metadata=f"<dc:title>{title}</dc:title>")


def titles(store: UserStore) -> list[str]:
    return sorted(book["title"] for book in store.books())


def test_the_books_of_a_folder_are_found_in_the_folders_inside_it_as_well(
    folder: Path,
) -> None:
    assert books_in(folder) == {
        "hund.epub": folder / "hund.epub",
        "German/Stories/Katze.EPUB": folder / "German" / "Stories" / "Katze.EPUB",
    }


def test_the_books_of_the_folder_that_is_chosen_are_kept(
    sync: BookSync, store: UserStore, folder: Path
) -> None:
    status = sync.status()

    assert titles(store) == ["Der Hund", "Die Katze"]
    assert (status.state, status.folder, status.found) == ("synced", str(folder), 2)
    assert (status.unread, status.revision) == ([], 1)
    assert store.book(book_id("hund.epub")) is not None


def test_a_book_that_appears_in_the_folder_is_kept_by_the_next_look(
    sync: BookSync, store: UserStore, folder: Path
) -> None:
    (folder / "German" / "maus.epub").write_bytes(book("Die Maus"))

    sync.sync()

    assert titles(store) == ["Der Hund", "Die Katze", "Die Maus"]
    assert sync.status().revision == 2


def test_a_book_that_is_gone_from_the_folder_is_removed_and_one_added_by_hand_stays(
    sync: BookSync, store: UserStore, folder: Path
) -> None:
    store.add_book("by-hand", "Das Pferd", "", "", [])
    (folder / "hund.epub").unlink()

    sync.sync()

    assert titles(store) == ["Das Pferd", "Die Katze"]


def test_a_book_is_read_again_only_when_its_file_has_changed(
    sync: BookSync, store: UserStore, folder: Path
) -> None:
    before = sync.status().revision
    sync.sync()
    unchanged = sync.status().revision
    (folder / "hund.epub").write_bytes(book("Der große Hund"))

    sync.sync()

    assert (before, unchanged, sync.status().revision) == (1, 1, 2)
    assert titles(store) == ["Der große Hund", "Die Katze"]
    # it is the book it was, and so is still open where it was read to
    assert store.book(book_id("hund.epub")) is not None


def test_a_file_that_cannot_be_read_is_named_with_the_reason_and_the_others_kept(
    sync: BookSync, store: UserStore, folder: Path
) -> None:
    (folder / "broken.epub").write_bytes(b"not a book")

    sync.sync()
    sync.sync()

    assert titles(store) == ["Der Hund", "Die Katze"]
    assert sync.status().found == 3
    assert sync.status().unread == [
        Unread("broken.epub", "the file is not an EPUB book")
    ]


def test_the_books_stay_while_the_folder_cannot_be_found(
    sync: BookSync, store: UserStore, folder: Path
) -> None:
    away = folder.with_name("Away")
    os.rename(folder, away)

    sync.sync()
    while_away = (sync.status().state, titles(store))
    os.rename(away, folder)
    sync.sync()

    assert while_away == ("missing", ["Der Hund", "Die Katze"])
    assert sync.status().state == "synced"


def test_another_folder_brings_its_own_books_and_takes_those_of_the_first_away(
    sync: BookSync, store: UserStore, tmp_path: Path
) -> None:
    other = tmp_path / "Other"
    other.mkdir()
    (other / "maus.epub").write_bytes(book("Die Maus"))

    sync.choose(f'"{other}"')

    assert titles(store) == ["Die Maus"]
    assert sync.status().folder == str(other)


def test_without_a_folder_nothing_is_looked_through_and_the_books_stay(
    sync: BookSync, store: UserStore
) -> None:
    sync.choose("")

    assert sync.status().state == "off"
    assert titles(store) == ["Der Hund", "Die Katze"]


def test_the_folder_is_still_the_one_chosen_after_a_restart(
    sync: BookSync, store: UserStore, folder: Path
) -> None:
    again = BookSync(store, background=lambda job: job())

    assert again.status().folder == str(folder)
