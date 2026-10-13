// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { checkerFetch } from "./session";

/** A word of the vocabulary as it is listed: without what is known about it. */
export interface ListedWord {
    id: number;
    category: string;
    /** The dictionary form. */
    lemma: string;
    /** When it was stored, in UTC, as `2026-10-13 14:12:07`. */
    created_at: string;
    /** How many forms it is stored with. */
    forms: number;
    /** How often you used it in what you wrote. */
    used: number;
    /** How often it came up in what the model wrote. */
    seen: number;
    /** When it was first and last used by either, in seconds since the epoch; null if never. */
    first_used: number | null;
    last_used: number | null;
}

/** How often a word was used and seen, in a few words; nothing if neither. */
export function describeUses(word: Pick<ListedWord, "used" | "seen">): string {
    return [word.used > 0 && `used ${word.used}×`, word.seen > 0 && `seen ${word.seen}×`].filter(Boolean).join(" · ");
}

/** Every word the checker server has stored. */
export interface Vocabulary {
    /** The categories, in the order they are to be shown in. */
    categories: string[];
    words: ListedWord[];
}

export interface WordForm {
    id: number;
    form: string;
    /** Which form of the word it is, such as "präsens ich". May be empty. */
    tags: string;
}

/** A word of the vocabulary with everything that is stored of it. */
export interface VocabularyEntry {
    id: number;
    category: string;
    lemma: string;
    /** What is known about the word beyond its forms. Which attributes there are depends on the category. */
    details: Record<string, unknown>;
    forms: WordForm[];
    /** When it was stored, in UTC. */
    created_at: string;
}

async function request<T>(path: string): Promise<T> {
    let response: Response;
    try {
        response = await checkerFetch(path);
    } catch {
        throw new Error("The checker server cannot be reached. Is `just checker` running?");
    }
    if (!response.ok) {
        throw new Error(`The checker server answered ${response.status}.`);
    }
    return await response.json();
}

/**
 * The list of the stored words of a language. What is known about each is
 * fetched with fetchEntry.
 */
export function fetchVocabulary(language: string): Promise<Vocabulary> {
    return request<Vocabulary>(`/vocabulary/words?language=${encodeURIComponent(language)}`);
}

export function fetchEntry(id: number, language: string): Promise<VocabularyEntry> {
    return request<VocabularyEntry>(`/vocabulary/words/${id}?language=${encodeURIComponent(language)}`);
}

export interface CategoryGroup {
    category: string;
    words: ListedWord[];
}

/** The orders the words of a category can be shown in. */
export const sortLabels = {
    word: "A–Z",
    newest: "Newest first",
    used: "Most used by you",
    seen: "Most seen",
    lastUsed: "Last used",
} as const;

export type SortKey = keyof typeof sortLabels;

const collator = new Intl.Collator(undefined, { sensitivity: "base" });

/** What puts two words in an order, the one to come first being the lesser. Words that are level go by the alphabet. */
function comparing(sort: SortKey): (a: ListedWord, b: ListedWord) => number {
    const by: Record<SortKey, (a: ListedWord, b: ListedWord) => number> = {
        word: () => 0,
        // a server that has not been restarted yet does not say when, so the ids are gone by
        newest: (a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? "") || b.id - a.id,
        used: (a, b) => b.used - a.used,
        seen: (a, b) => b.seen - a.seen,
        // a word that was never used comes after all that were
        lastUsed: (a, b) => (b.last_used ?? 0) - (a.last_used ?? 0),
    };
    return (a, b) => by[sort](a, b) || collator.compare(a.lemma, b.lemma);
}

/**
 * The words whose dictionary form has `query` in it, by category, and in
 * the order asked for within each. The categories come in the order the
 * server gave, then any it did not name, and those left without words are
 * left out.
 */
export function groupWords(vocabulary: Vocabulary, query: string, sort: SortKey = "word"): CategoryGroup[] {
    const wanted = query.trim().toLowerCase();
    const groups = new Map<string, ListedWord[]>(vocabulary.categories.map((category) => [category, []]));
    for (const word of vocabulary.words) {
        if (wanted && !word.lemma.toLowerCase().includes(wanted)) {
            continue;
        }
        const group = groups.get(word.category) ?? [];
        group.push(word);
        groups.set(word.category, group);
    }
    return [...groups]
        .filter(([, words]) => words.length > 0)
        .map(([category, words]) => ({ category, words: words.sort(comparing(sort)) }));
}

export interface DetailRow {
    label: string;
    value: string;
}

/**
 * What is known about a word as rows of text. The attributes differ by
 * category and more will be added, so they are shown whatever they are:
 * a list of several things, such as the genders of a noun, gets a row for
 * each. Attributes that are empty are left out.
 */
export function detailRows(details: Record<string, unknown>): DetailRow[] {
    const rows: DetailRow[] = [];
    for (const [name, value] of Object.entries(details)) {
        const label = name.replaceAll("_", " ");
        const several = Array.isArray(value) && value.some((item) => typeof item === "object" && item !== null);
        for (const item of several ? (value as unknown[]) : [value]) {
            const text = describe(item);
            if (text) {
                rows.push({ label, value: text });
            }
        }
    }
    return rows;
}

function describe(value: unknown): string {
    if (typeof value === "boolean") {
        return value ? "yes" : "no";
    }
    if (Array.isArray(value)) {
        return value.map(describe).filter(Boolean).join(", ");
    }
    if (typeof value === "object" && value !== null) {
        return Object.entries(value)
            .map(([name, inner]) => [name.replaceAll("_", " "), describe(inner)])
            .filter(([, text]) => text)
            .map(([name, text]) => `${name}: ${text}`)
            .join(" · ");
    }
    return value === null || value === undefined ? "" : String(value);
}

/** A form in a table, with the other shape it takes, if it has one. */
export interface FormCell {
    form: string;
    /** For a separable verb, the form it has at the end of a subordinate clause: "anfange" for "fange an". */
    also: string;
}

/** Forms laid out by two things that tell them apart, such as person and tense. */
export interface FormTable {
    title: string;
    columns: string[];
    rows: { label: string; cells: FormCell[] }[];
}

export interface FormLayout {
    tables: FormTable[];
    /** The forms that have no place in a table, each with what it is. */
    others: { label: string; form: string }[];
}

interface TablePlan {
    title: string;
    columns: string[];
    rows: string[];
    /** The tags of the form that goes where a column and a row meet. */
    tags: (column: string, row: string) => string;
}

const PERSONS = ["ich", "du", "er", "wir", "ihr", "sie"];
const CASES = ["nominativ", "genitiv", "dativ", "akkusativ"];

/** The tables the forms of each category are laid out in. */
const PLANS: Record<string, TablePlan[]> = {
    verb: [
        {
            title: "Indikativ",
            columns: ["präsens", "präteritum"],
            rows: PERSONS,
            tags: (tense, person) => `${tense} ${person}`,
        },
        {
            title: "Konjunktiv",
            columns: ["konjunktiv I", "konjunktiv II"],
            rows: PERSONS,
            tags: (tense, person) => `${tense} ${person}`,
        },
    ],
    noun: ["der", "die", "das"].map((article) => ({
        title: article,
        columns: ["singular", "plural"],
        rows: CASES,
        tags: (number, grammaticalCase) => `${article} ${grammaticalCase} ${number}`,
    })),
    adjective: [
        {
            title: "Endings",
            columns: ["positiv", "komparativ", "superlativ"],
            rows: ["-e", "-er", "-es", "-en", "-em"],
            tags: (degree, ending) => `${degree} ${ending}`,
        },
    ],
};

/**
 * The forms of a word laid out to be read: verbs by person and tense, nouns
 * by case and number for each gender, adjectives by ending and degree. A
 * form that fits no table, and every form of the other categories, is
 * listed with its tags. A table none of whose forms are there is left out.
 */
export function layOutForms(entry: Pick<VocabularyEntry, "category" | "lemma" | "forms">): FormLayout {
    const byTags = new Map<string, string[]>();
    for (const form of entry.forms) {
        byTags.set(form.tags, [...(byTags.get(form.tags) ?? []), form.form]);
    }
    const placed = new Set<string>();
    const take = (tags: string): string => {
        placed.add(tags);
        return (byTags.get(tags) ?? []).join(", ");
    };
    const tables: FormTable[] = [];
    for (const plan of PLANS[entry.category] ?? []) {
        if (!plan.rows.some((row) => plan.columns.some((column) => byTags.has(plan.tags(column, row))))) {
            continue;
        }
        tables.push({
            title: plan.title,
            columns: plan.columns,
            rows: plan.rows.map((row) => ({
                label: row,
                cells: plan.columns.map((column) => ({
                    form: take(plan.tags(column, row)),
                    also: take(`${plan.tags(column, row)} nebensatz`),
                })),
            })),
        });
    }
    const others = entry.forms
        .filter((form) => !placed.has(form.tags))
        .map((form) => ({
            label: form.tags || (form.form === entry.lemma ? "dictionary form" : "–"),
            form: form.form,
        }));
    return { tables, others };
}
