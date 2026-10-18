// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { checkerFetch } from "./session";
import type { Word } from "./words";

/** Whether the user has linked an Anki account, whose collection the server keeps a copy of. */
export interface AnkiState {
    linked: boolean;
    /** Unix seconds of the last sync of the collection, or null before the first. */
    last_sync: number | null;
    /** Why the last sync failed, if it did. */
    error: string | null;
}

async function ankiReply<T>(asked: Promise<Response>): Promise<T> {
    let response: Response;
    try {
        response = await asked;
    } catch {
        throw new Error("Could not reach the checker server. Is `just checker` running?");
    }
    if (!response.ok) {
        const detail = await response.json().then((reply: { error?: string }) => reply.error, () => undefined);
        throw new Error(detail ?? response.statusText);
    }
    return response.json();
}

export function fetchAnkiState(): Promise<AnkiState> {
    return ankiReply(checkerFetch("/anki"));
}

/** Links the Anki account of `username`. The server keeps no password, only what it is given to sync with. */
export function linkAnki(username: string, password: string): Promise<AnkiState> {
    return ankiReply(checkerFetch("/anki/link", { method: "POST", body: JSON.stringify({ username, password }) }));
}

/** Forgets the Anki account, and the copy of its collection. */
export function unlinkAnki(): Promise<AnkiState> {
    return ankiReply(checkerFetch("/anki/link", { method: "DELETE" }));
}

/** A deck of the linked collection, with whether its words are among those had. */
export interface AnkiDeck {
    id: number;
    /** The full name, such as "Languages::Verbs". */
    name: string;
    total_cards: number;
    chosen: boolean;
}

export async function fetchAnkiDecks(): Promise<AnkiDeck[]> {
    return (await ankiReply<{ decks: AnkiDeck[] }>(checkerFetch("/anki/decks"))).decks;
}

/** Has the words of the decks `ids` be those had, and no other deck's that there is now. */
export async function chooseAnkiDecks(ids: number[]): Promise<AnkiDeck[]> {
    const asked = checkerFetch("/anki/decks", { method: "PUT", body: JSON.stringify({ decks: ids }) });
    return (await ankiReply<{ decks: AnkiDeck[] }>(asked)).decks;
}

/** What a linked Anki account is doing, in a line. */
export function describeAnki(anki: AnkiState, locale?: string): string {
    if (anki.error) {
        return `The last sync failed: ${anki.error}`;
    }
    if (anki.last_sync === null) {
        return "The first sync is running, which can take a minute.";
    }
    const when = new Date(anki.last_sync * 1000).toLocaleString(locale, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
    });
    return `Last synced ${when}.`;
}

export interface Timing {
    /** Days since the collection was created; review cards are due on such a day. */
    days_elapsed: number;
    /** Unix seconds at which the current day ends. */
    next_day_at: number;
}

// One row of the notes with a card in review, as the checker server hands
// them over from the deck-status server.
type KnownWordRow = [
    noteId: number,
    notetypeId: number,
    sortField: string | number,
    fields: string,
    due: number,
    interval: number,
];

/** Converts the day a card is due into a calendar date, as YYYY-MM-DD. */
export function dueDate(due: number, timing: Timing): string {
    // cards being relearned today store a time rather than a day
    const dueSecs = due > 1_000_000_000
        ? due
        : timing.next_day_at - 86_400 + (due - timing.days_elapsed) * 86_400;
    const date = new Date(dueSecs * 1000);
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Removes markup and sound tags, leaving the text a field shows. */
export function plainText(field: string): string {
    return field
        .replace(/\[sound:[^\]]*\]/g, "")
        .replace(/<[^>]*>/g, "")
        .replace(/&nbsp;/g, " ")
        .replace(/&amp;/g, "&")
        .trim();
}

/** The position of the first field whose name matches, or -1. */
function fieldIndex(fieldNames: string[], pattern: RegExp): number {
    return fieldNames.findIndex((name) => pattern.test(name));
}

/**
 * Turns database rows into words. Notes don't say which field is the meaning,
 * so it is picked by the field's name, falling back to the second field.
 */
export function wordsFromRows(
    rows: KnownWordRow[],
    fieldNamesByNotetype: Map<number, string[]>,
    timing: Timing,
): Word[] {
    return rows.map(([noteId, notetypeId, sortField, joinedFields, due, intervalDays]) => {
        const fields = joinedFields.split("\x1f");
        const names = fieldNamesByNotetype.get(notetypeId) ?? [];
        const meaningIdx = fieldIndex(names, /^(english|meaning|translation|definition|back)$/i);
        const partOfSpeechIdx = fieldIndex(names, /part of speech/i);
        return {
            noteId,
            word: plainText(String(sortField)),
            meaning: plainText(fields[meaningIdx === -1 ? 1 : meaningIdx] ?? ""),
            partOfSpeech: plainText(fields[partOfSpeechIdx] ?? ""),
            due: dueDate(due, timing),
            intervalDays,
        };
    });
}

/** What the checker server hands over of the Anki collection. */
interface AnkiWords {
    rows: KnownWordRow[];
    timing: Timing;
    /** The names of the fields of each notetype, by its id. */
    field_names: Record<string, string[]>;
}

/**
 * Fetches every word with at least one card that has graduated to review,
 * through the checker server, which alone reaches the deck-status server.
 */
export async function fetchKnownWords(): Promise<Word[]> {
    const { rows, timing, field_names: fieldNames } = await ankiReply<AnkiWords>(checkerFetch("/anki/words"))
        .catch((error: Error) => {
            throw new Error(`Anki words: ${error.message}`);
        });
    const fieldNamesByNotetype = new Map(Object.entries(fieldNames).map(([ntid, names]) => [Number(ntid), names]));
    return wordsFromRows(rows, fieldNamesByNotetype, timing);
}
