# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Makes the audio of sentences read aloud that every user keeps as WAV
files Opus files, as the audio made from now on is (`speaking.py`), which
take about a fifteenth of the room. It can be run while the server is: a
sentence is played as WAV until it is replaced, and as Opus after."""

from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from speaking import OPUS, compressed
from storage import UserStore

DATA_DIRECTORY = Path(__file__).parent / "data"
WAV = "audio/wav"
# how many files are made at the same time
WORKERS = 4


def compress_user(store: UserStore, name: str) -> tuple[int, int]:
    """Make the WAV files of one user Opus: how many were, and how many
    could not be."""
    wanted = store.speech_of_kind(WAV)
    done = failed = 0

    def one(book_id: str, sentence_id: str) -> bool:
        kept = store.speech(book_id, sentence_id)
        if kept is None:
            return False
        audio, kind = compressed(*kept)
        if kind != OPUS:
            return False
        store.replace_speech_audio(book_id, sentence_id, audio, kind)
        return True

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for made in pool.map(lambda each: one(*each), wanted):
            done += made
            failed += not made
            if (done + failed) % 100 == 0:
                print(f"{name}: {done + failed} of {len(wanted)}", flush=True)
    return done, failed


def main() -> int:
    data = Path(os.environ.get("CHECKER_DATA") or DATA_DIRECTORY)
    for directory in sorted((data / "users").glob("*/")):
        if not (directory / "app.db").exists():
            continue
        done, failed = compress_user(UserStore(directory), directory.name)
        print(f"{directory.name}: {done} made Opus, {failed} left as they were")
    return 0


if __name__ == "__main__":
    sys.exit(main())
