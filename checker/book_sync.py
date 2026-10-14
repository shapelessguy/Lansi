# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Keeps the books a user reads the same as the e-books in a folder, such as
one that OneDrive keeps on this machine.

The folder is looked through again and again, with every folder inside it. An
e-book that has appeared in it is read and kept, one that has changed is read
again, and one that is gone from it is removed. The books the user added by
hand are left alone.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from books import BookError, read_epub
from storage import UserStore

# how often the folder is looked through
LOOK_EVERY_SECS = 60.0
# a book with many pictures in it, which are not kept
MAX_BOOK_BYTES = 200_000_000
# Raised whenever more is kept of a book than was, for the books that are
# kept already to be read again.
READING = 2
# the kinds of file that are books, by the end of their names
ENDINGS = (".epub",)

# Runs a job without making the caller wait for it.
Background = Callable[[Callable[[], None]], None]


def in_a_thread(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name="book-sync", daemon=True).start()


@dataclass
class Unread:
    """A file in the folder that could not be read as a book."""

    # its name, from the folder
    file: str
    reason: str


@dataclass
class SyncStatus:
    # What the taking of the books from the folder is doing:
    #   "off": there is no folder
    #   "missing": the folder is not there, so nothing is added or removed
    #   "syncing": the folder is being looked through
    #   "synced": the books are those of the folder
    state: str = "off"
    folder: str = ""
    # how many e-books the folder had the last time it was looked through
    found: int = 0
    unread: list[Unread] = field(default_factory=list)
    # goes up whenever a look has added or removed a book
    revision: int = 0
    # a folder of OneDrive on this machine, if there is one, to start from
    suggestion: str = ""


def one_drive_folder() -> str:
    """The folder OneDrive keeps on this machine, if it says where it is."""
    for name in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        if os.environ.get(name):
            return os.environ[name]
    return ""


def book_id(source: str) -> str:
    """The id of the book that is from the file of that name. It is the same
    each time, so that a book read again is the one it was."""
    return "f" + hashlib.sha1(source.encode()).hexdigest()[:31]


def books_in(folder: Path) -> dict[str, Path]:
    """The e-books in a folder and in every folder inside it, by their names
    from the folder, written with "/"."""
    found = {}
    for directory, _, names in os.walk(folder):
        for name in names:
            if name.lower().endswith(ENDINGS):
                file = Path(directory, name)
                found[file.relative_to(folder).as_posix()] = file
    return found


class BookSync:
    def __init__(
        self,
        store: UserStore,
        on_synced: Callable[[int, int], None] | None = None,
        background: Background = in_a_thread,
    ) -> None:
        """`on_synced` is told how many books a look added and removed, if it
        did either."""
        self._store = store
        self._on_synced = on_synced
        self._background = background
        self._status = SyncStatus(
            folder=store.books_folder(), suggestion=one_drive_folder()
        )
        # The files that could not be read, each with its stamp and why. One
        # is not tried again until it has changed.
        self._unread: dict[str, tuple[str, str]] = {}
        # guards the status
        self._lock = threading.Lock()
        # held while the folder is looked through, which is by one at a time
        self._looking = threading.Lock()

    def status(self) -> SyncStatus:
        with self._lock:
            return replace(self._status, unread=list(self._status.unread))

    def choose(self, folder: str) -> None:
        """Take the books from `folder` from now on, or from nowhere if it is
        empty. The books that are from the folder there was stay until the
        new one has been looked through."""
        folder = folder.strip().strip('"')
        self._store.save_books_folder(folder)
        with self._lock:
            self._status.folder = folder
            self._status.state = "syncing" if folder else "off"
            self._status.unread = []
        self._unread.clear()
        self.start()

    def start(self) -> None:
        """Look through the folder now, without waiting for it."""
        self._background(self.sync)

    def watch(self, every_secs: float = LOOK_EVERY_SECS) -> None:
        """Look again and again, on a thread of its own."""

        def keep_looking() -> None:
            # never set, so this only waits
            pause = threading.Event()
            self.sync()
            while not pause.wait(every_secs):
                self.sync()

        threading.Thread(target=keep_looking, name="book-sync", daemon=True).start()

    def sync(self) -> None:
        """Look through the folder once, and make the books that are from it
        those that are in it."""
        with self._looking:
            folder = self._store.books_folder()
            if not folder:
                self._update("off")
                return
            path = Path(folder).expanduser()
            if not path.is_dir():
                # A folder that cannot be found may only be away for now, so
                # the books that are from it stay.
                self._update("missing")
                return
            self._update("syncing")
            files = books_in(path)
            kept = self._store.books_from_folder()
            added = removed = 0
            for source, (kept_id, _) in kept.items():
                if source not in files:
                    self._store.delete_book(kept_id)
                    removed += 1
            for source, file in files.items():
                added += self._take(source, file, kept.get(source, ("", ""))[1])
            unread = [
                Unread(source, reason)
                for source, (_, reason) in sorted(self._unread.items())
                if source in files
            ]
            with self._lock:
                self._status.state = "synced"
                self._status.found = len(files)
                self._status.unread = unread
                self._status.revision += 1 if added or removed else 0
        if self._on_synced and (added or removed):
            self._on_synced(added, removed)

    def _take(self, source: str, file: Path, kept_stamp: str) -> bool:
        """Read a file of the folder and keep it as a book, unless it is kept
        as it is already. Returns whether it was kept."""
        try:
            described = file.stat()
        except OSError:
            # gone since the folder was looked through
            return False
        # what tells the file from a later one of the same name
        stamp = f"{READING}:{described.st_mtime_ns}:{described.st_size}"
        if stamp in (kept_stamp, self._unread.get(source, ("", ""))[0]):
            return False
        try:
            if described.st_size > MAX_BOOK_BYTES:
                raise BookError("the book is too large")
            book = read_epub(file.read_bytes(), file.stem)
        except BookError as error:
            self._unread[source] = (stamp, str(error))
            return False
        except OSError as error:
            self._unread[source] = (stamp, error.strerror or "the file cannot be read")
            return False
        self._unread.pop(source, None)
        self._store.add_book(
            book_id(source),
            book.title,
            book.author,
            book.language,
            [block.kept() for block in book.blocks],
            source,
            stamp,
            book.cover,
        )
        return True

    def _update(self, state: str) -> None:
        with self._lock:
            self._status.state = state
