// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { Word } from "./words";

/** Where the dev server forwards requests to the deck-status server. */
const BASE = "/anki";
/** The user whose collection the deck-status server keeps. */
const ANKI_USER = "cian_cl";

/** Whether the Anki words are `user`'s to see. */
export function seesAnkiWords(user: string): boolean {
    return user === ANKI_USER;
}

export interface Timing {
    /** Days since the collection was created; review cards are due on such a day. */
    days_elapsed: number;
    /** Unix seconds at which the current day ends. */
    next_day_at: number;
}

// One row per note that has a card in review or being relearned, with the
// earliest day one of those cards is due.
const KNOWN_WORDS_SQL = `
select n.id, n.mid, n.sfld, n.flds,
       min(case when c.odue > 0 then c.odue else c.due end),
       max(c.ivl)
from cards c join notes n on n.id = c.nid
where c.type in (2, 3)
group by n.id`;

type KnownWordRow = [
    noteId: number,
    notetypeId: number,
    sortField: string | number,
    fields: string,
    due: number,
    interval: number,
];

async function request<T>(path: string, body?: unknown): Promise<T> {
    let response: Response;
    try {
        response = await fetch(BASE + path, {
            method: body === undefined ? "GET" : "POST",
            body: body === undefined ? undefined : JSON.stringify(body),
        });
    } catch {
        throw new Error("Could not reach the deck-status server. Is `just deck-status` running?");
    }
    if (!response.ok) {
        const detail = (await response.text()) || response.statusText;
        throw new Error(`deck-status server: ${detail}`);
    }
    return response.json();
}

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

/** Fetches every word with at least one card that has graduated to review. */
export async function fetchKnownWords(): Promise<Word[]> {
    const [rows, timing] = await Promise.all([
        request<KnownWordRow[]>("/sql", { sql: KNOWN_WORDS_SQL }),
        request<Timing>("/api/schedTimingToday"),
    ]);
    const notetypeIds = [...new Set(rows.map((row) => row[1]))];
    const fieldNames = await Promise.all(
        notetypeIds.map((ntid) => request<{ vals: string[] }>("/api/getFieldNames", { ntid })),
    );
    const fieldNamesByNotetype = new Map(notetypeIds.map((ntid, index) => [ntid, fieldNames[index].vals]));
    return wordsFromRows(rows, fieldNamesByNotetype, timing);
}
