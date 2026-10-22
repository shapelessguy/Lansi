// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { Message } from "./i18n";

export interface Word {
    noteId: number;
    word: string;
    meaning: string;
    partOfSpeech: string;
    /** The day the word is next due, as YYYY-MM-DD. */
    due: string;
    intervalDays: number;
}

export type SortKey = "due" | "word" | "meaning" | "interval" | "partOfSpeech";

/** What each order is called, to be shown with `t`. */
export const sortLabels: Record<SortKey, Message> = {
    due: "Due date",
    word: "Word",
    meaning: "Meaning",
    interval: "Interval",
    partOfSpeech: "Part of speech",
};

const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

function compare(a: Word, b: Word, key: SortKey): number {
    switch (key) {
        case "due":
            return a.due.localeCompare(b.due);
        case "word":
            return collator.compare(a.word, b.word);
        case "meaning":
            return collator.compare(a.meaning, b.meaning);
        case "interval":
            return a.intervalDays - b.intervalDays;
        case "partOfSpeech":
            return collator.compare(a.partOfSpeech, b.partOfSpeech);
    }
}

/** Returns a sorted copy. Words that tie on `key` are ordered by the word itself. */
export function sortWords(words: Word[], key: SortKey, descending: boolean): Word[] {
    const direction = descending ? -1 : 1;
    return [...words].sort(
        (a, b) => direction * compare(a, b, key) || collator.compare(a.word, b.word),
    );
}

/** Keeps the words whose word or meaning contains `query`, ignoring case. */
export function filterWords(words: Word[], query: string): Word[] {
    const needle = query.trim().toLowerCase();
    if (!needle) {
        return words;
    }
    return words.filter(
        (word) => word.word.toLowerCase().includes(needle) || word.meaning.toLowerCase().includes(needle),
    );
}
