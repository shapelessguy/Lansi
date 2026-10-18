# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""What English does its own way."""

from __future__ import annotations

from languages import Language


class English(Language):
    abbreviations = frozenset(
        {"dr", "e.g", "i.e", "mr", "mrs", "ms", "prof", "st", "vs"}
    )


LANGUAGE = English("English")
