# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The tests of the checker's own modules, which are imported as the
server imports them: from the directory of the checker, above this one."""

import sys
from pathlib import Path

import pytest

CHECKER = str(Path(__file__).resolve().parent.parent)
if CHECKER not in sys.path:
    sys.path.insert(0, CHECKER)


@pytest.fixture(autouse=True)
def no_listing_of_image_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    """What image models draw in is never listed by a test: it is not known
    unless the test says it."""
    import topics

    monkeypatch.setattr(topics.IMAGE_SHAPES, "accepted", lambda model: None)
