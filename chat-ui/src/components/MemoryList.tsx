// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useState } from "react";

import { ask } from "../lib/dialogs";
import { locale, t } from "../lib/i18n";
import {
    deleteMemory,
    fetchMemories,
    fetchNoteRows,
    fetchNoteTables,
    type Memory,
    type NoteRows,
    type NoteTable,
} from "../lib/tutor";

interface Props {
    /** Changes when memories may have been made or removed, so that they are listed again. */
    revision: number;
}

type Loaded =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; memories: Memory[]; removed: Memory[] };

/**
 * What the tutor remembers of the learner from one chat to the next, the
 * newest first, as it is told it in every chat: made when a chat is
 * closed, and removed by the tutor when it is no longer true, or by the
 * learner here. The general ones are of the learner, and the tutor is
 * told them in every chat. The strategy, how the tutor and the learner
 * agreed to hold the lessons, and the calendar, what they planned to do on
 * a day, the tutor writes down as soon as they agree, and looks up, as it
 * does the recap of a few lines every chat leaves and the notes it writes
 * for itself, each by its title with what it says and the tables of its
 * database folded, each table read whenever it is opened, and again while it
 * is open whenever the memories may have changed. The calendar goes by
 * day, the days gone by greyed. What was removed is listed apart, with why
 * and by whom.
 */
export function MemoryList({ revision }: Props) {
    const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
    const load = useCallback(() => {
        fetchMemories().then(
            ({ memories, removed }) => setLoaded({ status: "ready", memories, removed }),
            (failed: Error) => setLoaded({ status: "error", message: failed.message }),
        );
    }, []);
    useEffect(load, [load, revision]);

    function forget(memory: Memory) {
        void ask(t("Have the tutor forget this?"), { detail: memory.content, confirm: t("Forget") }).then(
            async (agreed) => {
                if (agreed) {
                    await deleteMemory(memory.id);
                    load();
                }
            },
        );
    }

    if (loaded.status === "loading") {
        return <p className="sidebar-note">{t("Loading…")}</p>;
    }
    if (loaded.status === "error") {
        return <p className="sidebar-note error">{loaded.message}</p>;
    }
    const facts = loaded.memories.filter((memory) => memory.kind === "fact");
    const strategies = loaded.memories.filter((memory) => memory.kind === "strategy");
    const calendar = loaded.memories
        .filter((memory) => memory.kind === "calendar")
        .sort((one, other) => (one.day ?? "").localeCompare(other.day ?? "") || one.id - other.id);
    const today = localDay(new Date());
    const recaps = loaded.memories.filter((memory) => memory.kind === "recap");
    const notes = loaded.memories.filter((memory) => memory.kind === "note");
    const listed = (memories: Memory[]) => (
        <ul className="memory-list">
            {memories.map((memory) => (
                <li
                    key={memory.id}
                    className={["memory", memory.kind, memory.day && memory.day < today && "past"]
                        .filter(Boolean)
                        .join(" ")}
                >
                    {memory.kind === "note"
                        ? <Note id={memory.id} content={memory.content} revision={revision} />
                        : <p>{memory.content}</p>}
                    <div className="memory-meta">
                        <span>
                            {memory.kind === "note" && `#${memory.id} · `}
                            {memory.day
                                ? memory.day === today ? t("Today") : dayOf(memory.day)
                                : day(memory.createdAt)}
                        </span>
                        <button
                            className="link"
                            onClick={() => forget(memory)}
                            title={t("Have the tutor forget this")}
                        >
                            {t("Forget")}
                        </button>
                    </div>
                </li>
            ))}
        </ul>
    );
    return (
        <div className="panel-body memories">
            <details className="memory-group" open>
                <summary>{t("General")}</summary>
                {facts.length === 0
                    ? (
                        <p className="sidebar-note">
                            {t(
                                "The tutor remembers nothing yet. When you start a new chat with the tutor, the one before is closed, and what matters of it for the next lessons is kept here.",
                            )}
                        </p>
                    )
                    : listed([...facts].reverse())}
            </details>
            <details className="memory-group" open>
                <summary>{t("Strategy")}</summary>
                {strategies.length === 0
                    ? (
                        <p className="sidebar-note">
                            {t(
                                "You and the tutor have not agreed yet on how to hold the lessons, such as Anki first, then a chapter of a book. The tutor will ask you, and what you agree on is kept here.",
                            )}
                        </p>
                    )
                    : listed([...strategies].reverse())}
            </details>
            <details className="memory-group" open>
                <summary>{t("Calendar")}</summary>
                {calendar.length === 0
                    ? (
                        <p className="sidebar-note">
                            {t(
                                "Nothing is planned. When you and the tutor agree to do something on a day, such as a mock exam, it is put here.",
                            )}
                        </p>
                    )
                    : listed(calendar)}
            </details>
            <details className="memory-group" open>
                <summary>{t("Notes")}</summary>
                {notes.length === 0
                    ? (
                        <p className="sidebar-note">
                            {t(
                                "The tutor has no notes. What it works out and needs again, such as a table of the words your exercises used, it writes in a note here, to read again rather than make again.",
                            )}
                        </p>
                    )
                    : listed([...notes].reverse())}
            </details>
            {recaps.length > 0 && (
                <details className="memory-group">
                    <summary>{t("Recaps of the lessons")}</summary>
                    {listed([...recaps].reverse())}
                </details>
            )}
            {loaded.removed.length > 0 && (
                <details className="memory-group">
                    <summary>{t("Forgotten")}</summary>
                    <ul className="memory-list">
                        {[...loaded.removed].reverse().map((memory) => (
                            <li key={memory.id} className="memory removed">
                                <p>{memory.content}</p>
                                <div className="memory-meta">
                                    <span>
                                        {t(
                                            memory.removedBy === "learner"
                                                ? "{from} – {to}, by you"
                                                : "{from} – {to}, by the tutor",
                                            {
                                                from: day(memory.createdAt),
                                                to: memory.removedAt ? day(memory.removedAt) : "",
                                            },
                                        )}
                                        {memory.removedWhy && `: ${memory.removedWhy}`}
                                    </span>
                                </div>
                            </li>
                        ))}
                    </ul>
                </details>
            )}
        </div>
    );
}

/**
 * A note of the tutor: its title, and what it says and its tables folded
 * under it, the tables read whenever it is opened and again while it is open
 * as `revision` changes, since the tutor may have changed them.
 */
function Note({ id, content, revision }: { id: number; content: string; revision: number }) {
    const [title, ...lines] = content.split("\n");
    const [open, setOpen] = useState(false);
    const [tables, setTables] = useState<NoteTable[] | string | null>(null);
    useEffect(() => {
        let current = true;
        if (open) {
            fetchNoteTables(id).then(
                (found) => current && setTables(found),
                (failed: Error) => current && setTables(failed.message),
            );
        }
        return () => {
            current = false;
        };
    }, [id, open, revision]);
    return (
        <details className="memory-note" onToggle={(event) => setOpen(event.currentTarget.open)}>
            <summary>{title}</summary>
            <pre>{lines.join("\n")}</pre>
            {open && typeof tables === "string" && <p className="sidebar-note error">{tables}</p>}
            {open && Array.isArray(tables)
                && tables.map((table) => <NoteTableView key={table.name} id={id} table={table} revision={revision} />)}
        </details>
    );
}

/**
 * A table of a note, by its name and how many rows it has, its rows read a
 * page at a time whenever it is opened, and from the first page again while
 * it is open as `revision` changes.
 */
function NoteTableView({ id, table, revision }: { id: number; table: NoteTable; revision: number }) {
    const [open, setOpen] = useState(false);
    const [rows, setRows] = useState<NoteRows | null>(null);
    const [failed, setFailed] = useState("");
    useEffect(() => {
        let current = true;
        if (open) {
            fetchNoteRows(id, table.name).then(
                (page) => {
                    if (current) {
                        setRows(page);
                        setFailed("");
                    }
                },
                (error: Error) => current && setFailed(error.message),
            );
        }
        return () => {
            current = false;
        };
    }, [id, table.name, open, revision]);
    function more(offset: number) {
        fetchNoteRows(id, table.name, offset).then(
            (page) => setRows((before) => before ? { ...page, rows: [...before.rows, ...page.rows] } : page),
            (error: Error) => setFailed(error.message),
        );
    }
    return (
        <details className="note-table" onToggle={(event) => setOpen(event.currentTarget.open)}>
            <summary>
                {t("{name}, {count} rows", { name: table.name, count: table.rows.toLocaleString(locale()) })}
            </summary>
            {failed && <p className="sidebar-note error">{failed}</p>}
            {open && rows && (
                <div className="note-table-rows">
                    <table>
                        <thead>
                            <tr>
                                {rows.columns.map((column) => <th key={column}>{column}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            {rows.rows.map((row, at) => (
                                <tr key={at}>
                                    {row.map((value, column) => (
                                        <td key={column}>{value === null ? "" : String(value)}</td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    {rows.next_offset !== undefined && (
                        <button
                            className="link"
                            onClick={() => more(rows.next_offset ?? 0)}
                        >
                            {t("Show more ({count} left)", {
                                count: (rows.total - rows.rows.length).toLocaleString(locale()),
                            })}
                        </button>
                    )}
                </div>
            )}
        </details>
    );
}

function day(seconds: number): string {
    return new Date(seconds * 1000).toLocaleDateString(locale(), { dateStyle: "medium" });
}

/** A day given as YYYY-MM-DD, as the learner reads dates. */
function dayOf(iso: string): string {
    const [year, month, date] = iso.split("-").map(Number);
    return new Date(year, month - 1, date).toLocaleDateString(locale(), { dateStyle: "medium" });
}

/** The day of `moment` where the learner is, as YYYY-MM-DD. */
function localDay(moment: Date): string {
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${moment.getFullYear()}-${pad(moment.getMonth() + 1)}-${pad(moment.getDate())}`;
}
