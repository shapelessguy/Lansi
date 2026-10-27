// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useMemo, useRef, useState } from "react";

import { type AnkiDeck, ankiMediaUrl, type DeckNotes, fetchDeckNotes, type NoteState, plainText } from "../lib/anki";
import { type Message, plural, t } from "../lib/i18n";

/** The ids of a deck and of the decks inside it. */
export function deckAndInside(decks: AnkiDeck[], deck: AnkiDeck): Set<number> {
    return new Set(
        decks.filter((each) => each.id === deck.id || each.name.startsWith(`${deck.name}::`)).map((each) => each.id),
    );
}

interface Props {
    decks: AnkiDeck[] | null;
    error: string | null;
    /** The deck whose words alone are shown, or null for those of every deck ticked. */
    shown: number | null;
    onShow: (deckId: number | null) => void;
    onToggle: (deck: AnkiDeck) => void;
    onExplore: (deck: AnkiDeck) => void;
}

/**
 * The decks of the linked collection: ticked are those whose words are in
 * the Anki tab and the import, and decks made later are ticked; the words
 * of one alone are shown once it is clicked, until it is clicked again, and
 * every note of one can be explored.
 */
export function AnkiDecks({ decks, error, shown, onShow, onToggle, onExplore }: Props) {
    return (
        <details className="anki-decks" open>
            <summary>{t("Decks")}</summary>
            {decks === null && !error && <small>{t("Loading the decks…")}</small>}
            {decks?.map((deck) => {
                const parts = deck.name.split("::");
                return (
                    <div
                        key={deck.id}
                        className={shown === deck.id ? "deck shown" : "deck"}
                        style={{ paddingLeft: (parts.length - 1) * 18 }}
                    >
                        <input
                            className="deck-check"
                            type="checkbox"
                            aria-label={t("Include {deck}", { deck: deck.name })}
                            checked={deck.chosen}
                            onChange={() => onToggle(deck)}
                        />
                        <button
                            className="deck-name"
                            title={t("Show only the words of {deck}", { deck: deck.name })}
                            onClick={() => onShow(shown === deck.id ? null : deck.id)}
                        >
                            {parts[parts.length - 1]}
                        </button>
                        <small>{plural(deck.total_cards, "{count} card", "{count} cards")}</small>
                        <button
                            className="icon-button"
                            title={t("Explore {deck}", { deck: deck.name })}
                            aria-label={t("Explore {deck}", { deck: deck.name })}
                            onClick={() => onExplore(deck)}
                        >
                            ⊞
                        </button>
                    </div>
                );
            })}
            {error && <small className="error">{error}</small>}
        </details>
    );
}

const STATES: Record<NoteState, Message> = { 0: "New", 1: "Learning", 2: "In review" };
/** How many notes the explorer of a deck shows at once. */
const PAGE = 50;
/** How many of the fields of a notetype are shown before any is chosen. */
const FIRST_COLUMNS = 3;
const COLUMNS_KEY = "chat-ui.deck-columns.";

/** The names of the fields of a notetype chosen last to be shown, if any were. */
function keptColumns(notetype: string): string[] | null {
    try {
        const kept: unknown = JSON.parse(localStorage.getItem(COLUMNS_KEY + notetype) ?? "null");
        return Array.isArray(kept) ? kept.filter((name): name is string => typeof name === "string") : null;
    } catch {
        return null;
    }
}

function keepColumns(notetype: string, names: string[]): void {
    try {
        localStorage.setItem(COLUMNS_KEY + notetype, JSON.stringify(names));
    } catch {
        // storage is blocked, so the choice lasts as long as the page
    }
}

/** What a field of a note shows: its text, and the sounds and pictures of the media it names. */
export interface FieldParts {
    text: string;
    sounds: string[];
    pictures: string[];
}

const SOUND = /\[sound:([^\]]+)\]/g;
const PICTURE = /<img\b[^>]*?\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))[^>]*>/gi;

export function fieldParts(field: string): FieldParts {
    const sounds = [...field.matchAll(SOUND)].map((found) => found[1]);
    const pictures = [...field.matchAll(PICTURE)]
        .map((found) => found[1] ?? found[2] ?? found[3] ?? "")
        .filter(Boolean)
        .map((name) => {
            try {
                return decodeURIComponent(name);
            } catch {
                return name;
            }
        });
    return { text: plainText(field), sounds, pictures };
}

/** Plays a sound of the media of the collection, fetched once it is asked for. */
function Sound({ name }: { name: string }) {
    const [failed, setFailed] = useState(false);
    return (
        <button
            className="icon-button note-sound"
            title={failed ? t("{name} is not in the media of Anki.", { name }) : name}
            aria-label={name}
            disabled={failed}
            onClick={() =>
                ankiMediaUrl(name).then(
                    (url) => void new Audio(url).play().catch(() => setFailed(true)),
                    () => setFailed(true),
                )}
        >
            ▶
        </button>
    );
}

/** A picture of the media of the collection, fetched once it is scrolled into sight. */
function Picture({ name }: { name: string }) {
    const [url, setUrl] = useState<string | null>(null);
    const placeholder = useRef<HTMLSpanElement>(null);
    useEffect(() => {
        const element = placeholder.current;
        if (!element) {
            return;
        }
        let current = true;
        const watcher = new IntersectionObserver((entries) => {
            if (entries.some((entry) => entry.isIntersecting)) {
                watcher.disconnect();
                ankiMediaUrl(name).then((found) => current && setUrl(found), () => undefined);
            }
        });
        watcher.observe(element);
        return () => {
            current = false;
            watcher.disconnect();
        };
    }, [name]);
    return url
        ? <img className="note-picture" src={url} alt={name} title={name} />
        : <span ref={placeholder} className="note-picture" title={name} />;
}

function Field({ field }: { field: string }) {
    const { text, sounds, pictures } = useMemo(() => fieldParts(field), [field]);
    return (
        <div className="note-field">
            {pictures.map((name) => <Picture key={name} name={name} />)}
            {text && <span>{text}</span>}
            {sounds.map((name) => <Sound key={name} name={name} />)}
        </div>
    );
}

/**
 * Every note of a deck and of the decks inside it, whatever its cards are
 * doing, a row each, with a column for each field of its notetype. It is
 * shown at once, and the notes once they come.
 */
export function DeckExplorer({ deck, onClose }: { deck: AnkiDeck; onClose: () => void }) {
    const [notes, setNotes] = useState<DeckNotes | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [notetype, setNotetype] = useState<string | null>(null);
    const [query, setQuery] = useState("");
    // the names of the fields shown, by the notetype, once chosen
    const [columns, setColumns] = useState<Record<string, string[]>>({});
    const [page, setPage] = useState(0);
    const table = useRef<HTMLDivElement>(null);

    useEffect(() => {
        let current = true;
        fetchDeckNotes(deck.id).then(
            (found) => current && setNotes(found),
            (failed: Error) => current && setError(failed.message),
        );
        return () => {
            current = false;
        };
    }, [deck.id]);

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && onClose();
        document.addEventListener("keydown", onKeyDown);
        return () => document.removeEventListener("keydown", onKeyDown);
    }, [onClose]);

    // the notetypes, the one with the most notes first
    const notetypes = useMemo(() => {
        if (!notes) {
            return [];
        }
        const counts = new Map<string, number>();
        for (const [, ntid] of notes.rows) {
            counts.set(String(ntid), (counts.get(String(ntid)) ?? 0) + 1);
        }
        return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([ntid, count]) => ({ ntid, count }));
    }, [notes]);
    const chosen = notetype ?? notetypes[0]?.ntid ?? null;

    // the notes of the notetype shown, and its fields that any of them fills, by their places, with how many do
    const { all, fields } = useMemo(() => {
        if (!notes || chosen === null) {
            return { all: [], fields: [] };
        }
        const all = notes.rows
            .filter(([, ntid]) => String(ntid) === chosen)
            .map(([noteId, , joined, state]) => ({ noteId, state, fields: joined.split("\x1f") }));
        const fields = (notes.notetypes[chosen]?.fields ?? [])
            .map((name, place) => ({
                name,
                place,
                filled: all.filter((row) => (row.fields[place] ?? "").trim()).length,
            }))
            .filter(({ filled }) => filled > 0);
        return { all, fields };
    }, [notes, chosen]);

    const shownNames = chosen === null
        ? []
        : columns[chosen] ?? keptColumns(chosen) ?? fields.slice(0, FIRST_COLUMNS).map(({ name }) => name);
    const shownFields = fields.filter(({ name }) => shownNames.includes(name));

    function showColumn(name: string, shown: boolean) {
        if (chosen === null) {
            return;
        }
        const names = fields
            .map((field) => field.name)
            .filter((each) => (each === name ? shown : shownNames.includes(each)));
        setColumns({ ...columns, [chosen]: names });
        keepColumns(chosen, names);
    }

    const rows = useMemo(() => {
        const needle = query.trim().toLowerCase();
        return needle
            ? all.filter((row) => row.fields.some((field) => plainText(field).toLowerCase().includes(needle)))
            : all;
    }, [all, query]);
    // a page is taken back to the first when what is shown changes
    useEffect(() => setPage(0), [rows]);
    const pages = Math.max(1, Math.ceil(rows.length / PAGE));
    const onPage = rows.slice(page * PAGE, (page + 1) * PAGE);
    useEffect(() => table.current?.scrollTo({ top: 0 }), [page]);

    return (
        <div className="overlay deck-explorer" role="dialog" aria-modal="true" aria-label={deck.name}>
            <header className="overlay-header">
                <h2>{deck.name}</h2>
                {notes && (
                    <span className="set-total">
                        {plural(notes.rows.length, "{count} note", "{count} notes")}
                    </span>
                )}
                {notetypes.length > 1 && (
                    <select
                        aria-label={t("Notetype")}
                        value={chosen ?? ""}
                        onChange={(event) => setNotetype(event.target.value)}
                    >
                        {notetypes.map(({ ntid, count }) => (
                            <option key={ntid} value={ntid}>
                                {`${notes?.notetypes[ntid]?.name || ntid} (${count})`}
                            </option>
                        ))}
                    </select>
                )}
                {fields.length > 0 && (
                    <details className="column-picker">
                        <summary>
                            {t("Columns ({shown} of {count})", { shown: shownFields.length, count: fields.length })}
                        </summary>
                        <div className="column-list">
                            {fields.map(({ name, filled }) => (
                                <label key={name} className="check">
                                    <input
                                        type="checkbox"
                                        checked={shownNames.includes(name)}
                                        onChange={(event) => showColumn(name, event.target.checked)}
                                    />
                                    <span>{name}</span>
                                    <small title={t("Filled in {count} notes", { count: filled })}>{filled}</small>
                                </label>
                            ))}
                        </div>
                    </details>
                )}
                <input
                    type="search"
                    placeholder={t("Filter notes")}
                    aria-label={t("Filter notes")}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                />
                <button onClick={onClose}>{t("Close")}</button>
            </header>
            <div className="deck-table" ref={table}>
                {!notes && !error && <p className="sidebar-note">{t("Loading the notes…")}</p>}
                {error && <p className="sidebar-note error">{error}</p>}
                {notes?.more && (
                    <p className="sidebar-note">
                        {t("Only the first {count} notes are shown.", { count: notes.rows.length })}
                    </p>
                )}
                {notes && (
                    <table>
                        <thead>
                            <tr>
                                <th>{t("State")}</th>
                                {shownFields.map(({ name, place }) => <th key={place}>{name}</th>)}
                            </tr>
                        </thead>
                        <tbody>
                            {onPage.map((row) => (
                                <tr key={row.noteId}>
                                    <td className={`note-state state-${row.state}`}>{t(STATES[row.state])}</td>
                                    {shownFields.map(({ place }) => (
                                        <td key={place}>
                                            <Field field={row.fields[place] ?? ""} />
                                        </td>
                                    ))}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
                {notes && rows.length === 0 && <p className="sidebar-note">{t("No notes match.")}</p>}
            </div>
            {rows.length > PAGE && (
                <footer className="deck-pages">
                    <button
                        className="icon-button"
                        disabled={page === 0}
                        aria-label={t("Previous page")}
                        onClick={() => setPage(page - 1)}
                    >
                        ◀
                    </button>
                    <span>
                        {t("{first}–{last} of {count}", {
                            first: page * PAGE + 1,
                            last: Math.min((page + 1) * PAGE, rows.length),
                            count: rows.length,
                        })}
                    </span>
                    <button
                        className="icon-button"
                        disabled={page >= pages - 1}
                        aria-label={t("Next page")}
                        onClick={() => setPage(page + 1)}
                    >
                        ▶
                    </button>
                </footer>
            )}
        </div>
    );
}
