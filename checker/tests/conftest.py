# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""The tests of the checker's own modules, which are imported as the
server imports them: from the directory of the checker, above this one."""

import sys
from pathlib import Path

CHECKER = str(Path(__file__).resolve().parent.parent)
if CHECKER not in sys.path:
    sys.path.insert(0, CHECKER)
