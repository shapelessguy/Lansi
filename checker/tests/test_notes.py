# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

from __future__ import annotations

from pathlib import Path

import notes
import pytest
from notes import PAGE_ROWS, NoteError, run, tables


def test_a_note_database_is_made_written_in_and_queried_a_statement_at_a_time(
    tmp_path: Path,
) -> None:
    base = tmp_path / "7.db"

    run(base, "CREATE TABLE usage (word TEXT PRIMARY KEY, used INTEGER)")
    added = run(base, "INSERT INTO usage VALUES ('Brot', 0), ('Milch', 2)")
    changed = run(base, "UPDATE usage SET used = used + 1 WHERE word = 'Brot'")
    found = run(base, "SELECT word, used FROM usage ORDER BY used")

    assert (added, changed) == ({"changed": 2}, {"changed": 1})
    assert found == {
        "columns": ["word", "used"],
        "rows": [["Brot", 1], ["Milch", 2]],
        "total": 2,
    }
    assert tables(base) == [
        {
            "name": "usage",
            "columns": [
                {"name": "word", "type": "TEXT"},
                {"name": "used", "type": "INTEGER"},
            ],
            "rows": 2,
        }
    ]


def test_what_a_query_gives_is_paged_rather_than_cut(tmp_path: Path) -> None:
    base = tmp_path / "7.db"
    run(base, "CREATE TABLE n (i INTEGER)")
    run(
        base,
        f"WITH RECURSIVE c(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM c"
        f" WHERE i < {PAGE_ROWS + 3}) INSERT INTO n SELECT i FROM c",
    )

    first = run(base, "SELECT i FROM n ORDER BY i")
    rest = run(base, "SELECT i FROM n ORDER BY i", first["next_offset"])

    assert (len(first["rows"]), first["more"], first["total"]) == (
        PAGE_ROWS,
        3,
        PAGE_ROWS + 3,
    )
    assert rest["rows"] == [[PAGE_ROWS + 1], [PAGE_ROWS + 2], [PAGE_ROWS + 3]]
    assert "more" not in rest


@pytest.mark.parametrize(
    "query",
    [
        "ATTACH DATABASE '../app.db' AS app",
        "VACUUM INTO '../copy.db'",
        "PRAGMA writable_schema = ON",
        "BEGIN",
        "SELECT 1; SELECT 2",
        "SELECT * FROM nothing",
        "  ",
    ],
)
def test_a_statement_that_reaches_beyond_its_note_or_is_wrong_is_refused(
    tmp_path: Path, query: str
) -> None:
    with pytest.raises(NoteError):
        run(tmp_path / "7.db", query)
    assert sorted(path.name for path in tmp_path.iterdir()) in ([], ["7.db"])


def test_a_statement_that_runs_too_long_is_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(notes, "QUERY_SECS", 0.05)

    with pytest.raises(NoteError, match="longer than"):
        run(
            tmp_path / "7.db",
            "WITH RECURSIVE c(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM c)"
            " SELECT count(*) FROM c",
        )


def test_a_note_without_a_database_has_no_tables(tmp_path: Path) -> None:
    assert tables(tmp_path / "7.db") == []
