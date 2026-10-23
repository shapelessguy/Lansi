// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type Message, t } from "./i18n";
import type { ModelChoice } from "./models";
import { checkerFetch } from "./session";
import type { BackgroundTask } from "./tasks";

/** A book as it is listed, without what it says. */
export interface ListedBook {
    id: string;
    title: string;
    /** Empty if the book does not say. */
    author: string;
    /** As the book names it, such as "de"; empty if it does not. */
    language: string;
    /** In milliseconds since the epoch. */
    addedAt: number;
    /** Whether there is a picture of its cover. */
    cover?: boolean;
    /** Its versions, the one made first first; a version has none. */
    versions?: BookVersion[];
}

/** The kinds of version a book can have: some of it, or written anew by a model as a prompt says. */
export type VersionKind = "stripped" | "transformed";

/**
 * A version of a book, which is read as a book of its own, by its id: a
 * copy of what it says, made from the book or from another of its versions.
 */
export interface BookVersion {
    id: string;
    name: string;
    kind: VersionKind;
    /** In milliseconds since the epoch. */
    addedAt: number;
}

/** A paragraph, a heading or another piece of text that stands alone. */
export interface BookBlock {
    /** A line break in it is one the book has. */
    text: string;
    /** How large it is written, as a multiple of the size of most of the book. */
    size: number;
    /**
     * The parts of the text that lead somewhere: where each starts and ends
     * in the text, and where it leads, which is another block, by its place
     * among the blocks from 0, or an address outside the book.
     */
    links?: [start: number, end: number, to: number | string][];
    /** The element it is written in, such as "h2"; a paragraph, "p", if not given. */
    tag?: string;
    /** The classes the book gives that element. */
    classes?: string[];
    /** Whether most of it is written in bold, and in italics. */
    bold?: boolean;
    italic?: boolean;
    /**
     * What the book says the parts it is in are, from the outermost, such as
     * "bodymatter" and "chapter": the epub:type and role of the elements.
     */
    roles?: string[];
    /** The file of the book that starts with it, if one does. */
    page?: string;
    /**
     * For a picture, which has no text: the picture, by its id among those
     * of the book, which its versions show too, what the book says it shows,
     * and how large it is in pixels.
     */
    image?: string;
    alt?: string;
    width?: number;
    height?: number;
}

/** A piece of the text of a block, with where it leads if it is a link. */
export interface Segment {
    text: string;
    to?: number | string;
}

/** The text of a block in pieces, of which those that are links say where they lead. */
export function segments(block: BookBlock): Segment[] {
    const pieces: Segment[] = [];
    let at = 0;
    for (const [start, end, to] of [...(block.links ?? [])].sort((a, b) => a[0] - b[0])) {
        // a link inside another, or one that is not in the text, is left out
        if (start < at || end <= start || end > block.text.length) {
            continue;
        }
        if (start > at) {
            pieces.push({ text: block.text.slice(at, start) });
        }
        pieces.push({ text: block.text.slice(start, end), to });
        at = end;
    }
    if (at < block.text.length) {
        pieces.push({ text: block.text.slice(at) });
    }
    return pieces;
}

/** An entry of the table of contents of a book, as the book has it, with those under it. */
export interface BookEntry {
    title: string;
    /** The block it leads to, by its place among them from 0. */
    block: number;
    entries?: BookEntry[];
}

/** A place the book names by what it is, such as "bodymatter" or "toc". */
export interface BookLandmark {
    type: string;
    title: string;
    block: number;
}

/**
 * A section of a book, with those under it: a stretch of its blocks, which
 * the server works out from its table of contents and its headings. Every
 * block is in a section at the top; one with no title holds those before
 * the first that has one.
 */
export interface BookSection {
    title: string;
    /** The first of its blocks, and the one after its last, by their places. */
    start: number;
    end: number;
    sections?: BookSection[];
}

/** A book as the server keeps it: its text, how each part is written, and what it lists of itself. */
export interface Book extends ListedBook {
    blocks: BookBlock[];
    contents: BookEntry[];
    landmarks: BookLandmark[];
    sections: BookSection[];
    /** For a version, the book it is a version of, by its id, and what version it is. */
    parent?: string;
    version?: BookVersion;
}

/** What tells a section from the others: where it starts and ends, as no two sections share both. */
export function sectionKey(section: BookSection): string {
    return `${section.start}-${section.end}`;
}

/**
 * The stretches of blocks that are kept when the sections `left` names, by
 * their keys, are left out with all that is under them: each from its first
 * block to the one after its last, in order, those that touch made one.
 */
export function keptStretches(sections: BookSection[], left: ReadonlySet<string>): [number, number][] {
    const kept: [number, number][] = [];
    walkKept(sections, left, (start, end) => add(kept, start, end));
    return kept;
}

/** Adds a stretch to stretches in order, made one with the last if they touch. */
function add(stretches: [number, number][], start: number, end: number) {
    const last = stretches[stretches.length - 1];
    if (last && last[1] === start) {
        last[1] = end;
    } else {
        stretches.push([start, end]);
    }
}

/** Goes through the stretches of blocks that are not in a section left out, in order. */
function walkKept(
    sections: BookSection[],
    left: ReadonlySet<string>,
    visit: (start: number, end: number) => void,
) {
    for (const section of sections) {
        if (left.has(sectionKey(section))) {
            continue;
        }
        // what is in it before, between and after those under it is its own
        let at = section.start;
        for (const under of section.sections ?? []) {
            if (at < under.start) {
                visit(at, under.start);
            }
            walkKept([under], left, visit);
            at = under.end;
        }
        if (at < section.end) {
            visit(at, section.end);
        }
    }
}

/**
 * The story a block is in, by the key of the section marked as one that
 * starts it: the last of those that `stories` names to start at or before
 * the block, as a story goes on until the next starts. Null for a block
 * before the first.
 */
export function storyAt(stories: ReadonlySet<string>, place: number): string | null {
    let found: string | null = null;
    let foundStart = -1;
    for (const key of stories) {
        const start = Number.parseInt(key, 10);
        if (start <= place && start > foundStart) {
            found = key;
            foundStart = start;
        }
    }
    return found;
}

/**
 * A part of a book that is transformed on its own: a story, by the key of
 * the section that starts it, or null for what comes before the first, with
 * its stretches of blocks.
 */
export interface StoryPart {
    story: string | null;
    stretches: [number, number][];
}

/**
 * The parts a book is transformed in: the blocks that are not in a section
 * left out, gathered by the story each is in, in order. A story starts with
 * a section marked as one and goes on until the next such section starts.
 */
export function storyParts(
    sections: BookSection[],
    left: ReadonlySet<string>,
    stories: ReadonlySet<string>,
): StoryPart[] {
    const starts = [...new Set([...stories].map((key) => Number.parseInt(key, 10)))].sort((a, b) => a - b);
    const parts: StoryPart[] = [];
    function put(start: number, end: number) {
        const story = storyAt(stories, start);
        let part = parts.find((each) => each.story === story);
        if (!part) {
            part = { story, stretches: [] };
            parts.push(part);
        }
        add(part.stretches, start, end);
    }
    for (const [start, end] of keptStretches(sections, left)) {
        // a stretch is cut where a story starts in it
        let at = start;
        for (const cut of starts) {
            if (at < cut && cut < end) {
                put(at, cut);
                at = cut;
            }
        }
        put(at, end);
    }
    return parts;
}

/**
 * The sections that look like stories of their own, by their keys: those at
 * the top that have a title and sections under them, such as the stories of
 * a book of short stories with their chapters.
 */
export function suggestedStories(sections: BookSection[]): Set<string> {
    return new Set(sections.filter((section) => section.title && section.sections).map(sectionKey));
}

/** The tokens each block of a book takes when it is sent to a model, by its place, as the server counts them. */
export async function fetchBlockTokens(id: string): Promise<number[]> {
    const { blocks }: { blocks: number[] } = await (await send(`/${id}/tokens`)).json();
    return blocks;
}

/** The tokens of the blocks of these stretches, as they would be sent, of the tokens of each block by its place. */
export function stretchTokens(stretches: [number, number][], tokens: number[]): number {
    return stretches.reduce(
        (sum, [start, end]) => sum + tokens.slice(start, end).reduce((inner, each) => inner + each, 0),
        0,
    );
}

/** A part is transformed only if it takes no more than this share of what the reasoning model takes in at once, to leave room for the prompt and for what the model writes. */
export const PART_SHARE = 1 / 3;

/** The most a model may reason before it writes each part, as a share of what it takes in at once. */
export const REASONING_SHARE = 1 / 5;

/** Whether a part of that many tokens may be transformed by a model that takes in `contextWindow` at once. */
export function partFits(tokens: number, contextWindow: number): boolean {
    return tokens < contextWindow * PART_SHARE;
}

/** A prompt a transformed version can be written anew with, as the server offers it to start from. */
export interface TransformPrompt {
    /** Which it is, such as "translate" or "level". */
    id: string;
    /** As it is written, with the keywords of a prompt, such as `{{language}}`, to be filled in as in every prompt. */
    prompt: string;
}

export async function fetchTransformPrompts(): Promise<TransformPrompt[]> {
    const { prompts }: { prompts: TransformPrompt[] } = await (await send("/prompts")).json();
    return prompts;
}

/** The sections a block is in, from the one at the top to the innermost, by the block's place. */
export function sectionsAt(sections: BookSection[] | undefined, place: number): BookSection[] {
    const found = sections?.find((section) => section.start <= place && place < section.end);
    return found ? [found, ...sectionsAt(found.sections, place)] : [];
}

const BASE = "/books";

async function send(path: string, init?: RequestInit): Promise<Response> {
    let response: Response;
    try {
        response = await checkerFetch(BASE + path, init);
    } catch {
        throw new Error(t("The server cannot be reached. Is `just dev` running?"));
    }
    if (response.status === 400) {
        // the server says what is wrong with what it was sent
        const reply: { error?: string } = await response.json().catch(() => ({}));
        throw new Error(sentence(reply.error ?? "the book cannot be read"));
    }
    if (!response.ok) {
        throw new Error(t("The server answered {status}.", { status: response.status }));
    }
    return response;
}

/** What the server said, as a sentence: "the file is not an EPUB book" with a capital and a full stop. */
export function sentence(said: string): string {
    const trimmed = said.trim();
    return trimmed.charAt(0).toUpperCase() + trimmed.slice(1) + (/[.!?]$/.test(trimmed) ? "" : ".");
}

/** Every book, the one added last first. */
export async function fetchBooks(): Promise<ListedBook[]> {
    const { books }: { books: ListedBook[] } = await (await send("")).json();
    return books.sort((a, b) => b.addedAt - a.addedAt);
}

export async function fetchBook(id: string): Promise<Book> {
    return (await send(`/${id}`)).json();
}

/** Has the server read an EPUB file and keep its text. Returns the book as it is listed. */
export async function addBook(file: File): Promise<ListedBook> {
    const added = await send("", {
        method: "POST",
        // what the book is called if it does not say itself
        headers: { "X-File-Name": encodeURIComponent(file.name) },
        body: file,
    });
    return added.json();
}

/** Has the server make a version of a book, or of one of its versions, of the stretches of blocks kept. */
export async function stripBook(id: string, name: string, keep: [number, number][]): Promise<BookVersion> {
    const made = await send(`/${id}/strip`, { method: "POST", body: JSON.stringify({ name, keep }) });
    return made.json();
}

/** What a transformed version is made of. */
export interface Transforming {
    name: string;
    /** The prompt with its keywords filled in. */
    prompt: string;
    /** The stretches of blocks of each part, which is transformed on its own. */
    parts: [number, number][][];
    /** Whether the blocks in no part are in the version as they are, or left out of it. */
    untouched: "kept" | "left";
    /** The reasoning model that writes each part anew, as the checker server is told a model. */
    model: string | ModelChoice;
    /** Whether the model reasons before it writes each part. */
    reasoning: boolean;
    /** The most tokens it may reason in for each part, or null for as many as it likes. */
    reasoningBudget: number | null;
    /** What each part is called, for how it is going to be shown by it. */
    titles: string[];
}

/**
 * Has the server make a transformed version of a book, or of one of its
 * versions, in the background. Returns the task, which lists the version
 * under the book once it is done.
 */
export async function transformBook(
    id: string,
    transforming: Transforming,
    apiKey: string,
): Promise<BackgroundTask> {
    const started = await send(`/${id}/transform`, {
        method: "POST",
        headers: apiKey ? { "X-OpenRouter-Key": apiKey } : {},
        body: JSON.stringify(transforming),
    });
    return started.json();
}

/** Has the server call a book, with its versions, or one of its versions, `name`. Returns every book. */
export async function renameBook(id: string, name: string): Promise<ListedBook[]> {
    const { books }: { books: ListedBook[] } = await (await send(`/${id}`, {
        method: "PUT",
        body: JSON.stringify({ name }),
    })).json();
    return books.sort((a, b) => b.addedAt - a.addedAt);
}

export async function deleteBook(id: string): Promise<void> {
    covers.delete(id);
    await send(`/${id}`, { method: "DELETE" });
}

/**
 * Has the browser save a book, or a version of it, as an EPUB file: the
 * file it was read from for a book, one written from what it says for a
 * version. It is named for the book and the version.
 */
export async function exportBook(book: Pick<Book, "id" | "title" | "version">): Promise<void> {
    const file = await (await send(`/${book.id}/epub`)).blob();
    const name = book.version ? `${book.title} (${book.version.name})` : book.title;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(file);
    // what a file may not be called in some systems is left out of its name
    link.download = `${name.replace(/[\\/:*?"<>|]+/g, " ").trim() || "book"}.epub`;
    link.click();
    // the browser has the file once the link is followed
    setTimeout(() => URL.revokeObjectURL(link.href), 0);
}

// the pictures in the text of books that were fetched, each as an address the
// page can show, by the id of the picture, which is the same in every version
const pictures = new Map<string, Promise<string>>();

/**
 * A picture in the text of a book, or of one of its versions, as an address
 * an image can be shown from. It is fetched once, as a picture of an id is
 * always the same.
 */
export function fetchPicture(bookId: string, pictureId: string): Promise<string> {
    let picture = pictures.get(pictureId);
    if (!picture) {
        picture = send(`/${bookId}/pictures/${pictureId}`)
            .then((response) => response.blob())
            .then((blob) => URL.createObjectURL(blob));
        pictures.set(pictureId, picture);
        // one that could not be fetched is fetched again the next time
        picture.catch(() => pictures.delete(pictureId));
    }
    return picture;
}

// the covers that were fetched, each as an address the page can show
const covers = new Map<string, Promise<string>>();

/**
 * The picture on the cover of a book, as an address an image can be shown
 * from. It is fetched once. The server gives it to whoever is logged in
 * only, so an image cannot name it by itself.
 */
export function fetchCover(id: string): Promise<string> {
    let cover = covers.get(id);
    if (!cover) {
        cover = send(`/${id}/cover`).then((response) => response.blob()).then((blob) => URL.createObjectURL(blob));
        covers.set(id, cover);
        // one that could not be fetched is fetched again the next time
        cover.catch(() => covers.delete(id));
    }
    return cover;
}

/**
 * How many pages a text has that is laid out in columns `width` wide with
 * `gap` between them, all of which are `laidWidth` wide together.
 */
export function pageCount(laidWidth: number, width: number, gap: number): number {
    return Math.max(1, Math.round((laidWidth + gap) / (width + gap)));
}

/** The page, from 0, of what is `left` from the start of such columns. */
export function pageOf(left: number, width: number, gap: number): number {
    // a pixel is allowed for, as places are not always whole numbers
    return Math.max(0, Math.floor((left + 1) / (width + gap)));
}

/** What each look of a book is called, to be shown with `t`. */
interface Labelled {
    label: Message;
    [other: string]: unknown;
}

/** The colours a book is read in, as in a reading app: the page and the text on it. */
export const PAPERS = {
    app: { label: "App", background: "", color: "" },
    day: { label: "Day", background: "#ffffff", color: "#1d1d1b" },
    sepia: { label: "Sepia", background: "#f4ecd8", color: "#5b4636" },
    dusk: { label: "Dusk", background: "#33363b", color: "#d5d5d0" },
    night: { label: "Night", background: "#121212", color: "#bdbdb8" },
    console: { label: "Console", background: "#000000", color: "#3ddc84" },
} as const satisfies Record<string, Labelled>;

/** The fonts a book is read in. Each is one most machines have, with others to fall back on. */
export const FONTS = {
    sans: { label: "Sans", family: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif" },
    serif: { label: "Georgia", family: "Georgia, \"Times New Roman\", serif" },
    book: { label: "Palatino", family: "\"Palatino Linotype\", Palatino, \"Book Antiqua\", serif" },
    cambria: { label: "Cambria", family: "Cambria, \"Hoefler Text\", \"Liberation Serif\", serif" },
    verdana: { label: "Verdana", family: "Verdana, \"DejaVu Sans\", sans-serif" },
    mono: { label: "Monospace", family: "Consolas, \"Cascadia Mono\", Menlo, monospace" },
} as const satisfies Record<string, Labelled>;

/** How far apart the lines of a book are, as a multiple of the size of the text. */
export const SPACINGS = {
    close: { label: "Tight", lineHeight: 1.35 },
    normal: { label: "Normal", lineHeight: 1.6 },
    wide: { label: "Wide", lineHeight: 1.9 },
} as const satisfies Record<string, Labelled>;

/** How a book is read: how its text looks, and how far each book has been read. */
export interface Reading {
    /** The size of most of the text, in pixels. */
    fontSize: number;
    /** The colours of the page and the text. "app" is those of the app. */
    paper: keyof typeof PAPERS;
    font: keyof typeof FONTS;
    spacing: keyof typeof SPACINGS;
    /** The book that was open last, by its id, if one was. */
    bookId: string | null;
    /** The paragraph at the top of the page of each book that was opened, by the id of the book. */
    places: Record<string, number>;
    /**
     * Where in that paragraph the page starts, as a character of its text,
     * by the id of the book, so that what was at the top of the page stays
     * on the page shown however the pages are laid out anew.
     */
    offsets: Record<string, number>;
    /** The version of each book that was chosen last, by the ids of the book and of the version. */
    versions: Record<string, string>;
}

export const MIN_FONT_SIZE = 12;
export const MAX_FONT_SIZE = 40;
const FONT_SIZE_STEP = 2;
const STORAGE_KEY = "chat-ui.reading";

const defaultReading: Reading = {
    fontSize: 18,
    paper: "app",
    font: "sans",
    spacing: "normal",
    bookId: null,
    places: {},
    offsets: {},
    versions: {},
};

/** The size that is `steps` larger, or smaller if `steps` is negative, as far as sizes go. */
export function resized(fontSize: number, steps: number): number {
    return Math.min(MAX_FONT_SIZE, Math.max(MIN_FONT_SIZE, fontSize + steps * FONT_SIZE_STEP));
}

/**
 * How large a block is shown, as a multiple of the size of the text. A book
 * may write a title many times as large as its text, or a note too small to
 * read, and neither is shown quite so.
 */
export function shownSize(block: BookBlock): number {
    return Math.min(3, Math.max(0.7, block.size));
}

/** The numbers of what was stored by the id of each book that are whole and not below 0. */
function counts(stored: unknown): Record<string, number> {
    const kept: Record<string, number> = {};
    if (typeof stored === "object" && stored !== null) {
        for (const [id, count] of Object.entries(stored)) {
            if (Number.isInteger(count) && count >= 0) {
                kept[id] = count;
            }
        }
    }
    return kept;
}

/** Fills in anything missing or unusable in what was stored about reading with the defaults. */
export function normalizeReading(stored: unknown): Reading {
    if (typeof stored !== "object" || stored === null) {
        return defaultReading;
    }
    const candidate = stored as Partial<Reading>;
    return {
        fontSize: typeof candidate.fontSize === "number" && Number.isFinite(candidate.fontSize)
            ? resized(candidate.fontSize, 0)
            : defaultReading.fontSize,
        paper: Object.hasOwn(PAPERS, candidate.paper ?? "") ? candidate.paper! : defaultReading.paper,
        font: Object.hasOwn(FONTS, candidate.font ?? "") ? candidate.font! : defaultReading.font,
        spacing: Object.hasOwn(SPACINGS, candidate.spacing ?? "") ? candidate.spacing! : defaultReading.spacing,
        bookId: typeof candidate.bookId === "string" ? candidate.bookId : null,
        places: counts(candidate.places),
        offsets: counts(candidate.offsets),
        versions: Object.fromEntries(
            Object.entries(
                typeof candidate.versions === "object" && candidate.versions !== null
                    && !Array.isArray(candidate.versions)
                    ? candidate.versions
                    : {},
            ).filter(([, version]) => typeof version === "string"),
        ),
    };
}

export function loadReading(): Reading {
    try {
        return normalizeReading(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null"));
    } catch {
        return defaultReading;
    }
}

/** Changes what is stored about reading, and returns it as it is then. */
export function changeReading(change: (reading: Reading) => Reading): Reading {
    const changed = change(loadReading());
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(changed));
    } catch {
        // without storage, a book is opened at its start the next time
    }
    return changed;
}
