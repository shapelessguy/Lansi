// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { checkerFetch } from "./session";

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
    /** The name of its file in the folder the books are taken from, if it is from there. */
    source?: string | null;
    /** Whether there is a picture of its cover. */
    cover?: boolean;
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

/** A book as the server keeps it: its text, and how large each part is written. */
export interface Book extends ListedBook {
    blocks: BookBlock[];
}

const BASE = "/books";

async function send(path: string, init?: RequestInit): Promise<Response> {
    let response: Response;
    try {
        response = await checkerFetch(BASE + path, init);
    } catch {
        throw new Error("The server cannot be reached. Is `just dev` running?");
    }
    if (response.status === 400) {
        // the server says what is wrong with what it was sent
        const reply: { error?: string } = await response.json().catch(() => ({}));
        throw new Error(sentence(reply.error ?? "the book cannot be read"));
    }
    if (!response.ok) {
        throw new Error(`The server answered ${response.status}.`);
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

export async function deleteBook(id: string): Promise<void> {
    covers.delete(id);
    await send(`/${id}`, { method: "DELETE" });
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

/** What the server's taking of the books from a folder is doing. */
export interface FolderSync {
    /**
     * "off": there is no folder
     * "missing": the folder is not there, so nothing is added or removed
     * "syncing": the folder is being looked through
     * "synced": the books are those of the folder
     */
    state: "off" | "missing" | "syncing" | "synced";
    /** The folder, on the machine the server runs on; empty if there is none. */
    folder: string;
    /** How many e-books the folder had the last time it was looked through. */
    found: number;
    /** The files in it that could not be read as books, each with the reason. */
    unread: { file: string; reason: string }[];
    /** Goes up whenever a look has added or removed a book. */
    revision: number;
    /** A folder of OneDrive on that machine, if there is one, to start from. */
    suggestion: string;
}

export async function fetchFolderSync(): Promise<FolderSync> {
    return (await send("/folder")).json();
}

/** Has the books taken from `folder` from now on, with those of the folders inside it, or from none if it is empty. */
export async function chooseFolder(folder: string): Promise<FolderSync> {
    return (await send("/folder", { method: "PUT", body: JSON.stringify({ folder }) })).json();
}

/** Has the folder looked through now, without waiting for the next time it is. */
export async function syncFolder(): Promise<FolderSync> {
    return (await send("/sync", { method: "POST" })).json();
}

/** What the taking of the books from a folder is doing, in a line. */
export function describeSync(sync: FolderSync): string {
    switch (sync.state) {
        case "off":
            return "Name a folder, such as one in OneDrive, to keep its e-books here.";
        case "missing":
            return "The folder cannot be found. Its books stay until it can.";
        case "syncing":
            return "Looking through the folder…";
        default: {
            const found = `${sync.found} ${sync.found === 1 ? "e-book" : "e-books"} in the folder`;
            return sync.unread.length > 0 ? `${found}, ${sync.unread.length} of which cannot be read.` : `${found}.`;
        }
    }
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

/** The colours a book is read in, as in a reading app: the page and the text on it. */
export const PAPERS = {
    app: { label: "App", background: "", color: "" },
    day: { label: "Day", background: "#ffffff", color: "#1d1d1b" },
    sepia: { label: "Sepia", background: "#f4ecd8", color: "#5b4636" },
    dusk: { label: "Dusk", background: "#33363b", color: "#d5d5d0" },
    night: { label: "Night", background: "#121212", color: "#bdbdb8" },
    console: { label: "Console", background: "#000000", color: "#3ddc84" },
} as const;

/** The fonts a book is read in. Each is one most machines have, with others to fall back on. */
export const FONTS = {
    sans: { label: "Sans", family: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif" },
    serif: { label: "Georgia", family: "Georgia, \"Times New Roman\", serif" },
    book: { label: "Palatino", family: "\"Palatino Linotype\", Palatino, \"Book Antiqua\", serif" },
    cambria: { label: "Cambria", family: "Cambria, \"Hoefler Text\", \"Liberation Serif\", serif" },
    verdana: { label: "Verdana", family: "Verdana, \"DejaVu Sans\", sans-serif" },
    mono: { label: "Monospace", family: "Consolas, \"Cascadia Mono\", Menlo, monospace" },
} as const;

/** How far apart the lines of a book are, as a multiple of the size of the text. */
export const SPACINGS = {
    close: { label: "Close", lineHeight: 1.35 },
    normal: { label: "Normal", lineHeight: 1.6 },
    wide: { label: "Wide", lineHeight: 1.9 },
} as const;

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

/** Fills in anything missing or unusable in what was stored about reading with the defaults. */
export function normalizeReading(stored: unknown): Reading {
    if (typeof stored !== "object" || stored === null) {
        return defaultReading;
    }
    const candidate = stored as Partial<Reading>;
    const places: Record<string, number> = {};
    if (typeof candidate.places === "object" && candidate.places !== null) {
        for (const [id, place] of Object.entries(candidate.places)) {
            if (Number.isInteger(place) && place >= 0) {
                places[id] = place;
            }
        }
    }
    return {
        fontSize: typeof candidate.fontSize === "number" && Number.isFinite(candidate.fontSize)
            ? resized(candidate.fontSize, 0)
            : defaultReading.fontSize,
        paper: Object.hasOwn(PAPERS, candidate.paper ?? "") ? candidate.paper! : defaultReading.paper,
        font: Object.hasOwn(FONTS, candidate.font ?? "") ? candidate.font! : defaultReading.font,
        spacing: Object.hasOwn(SPACINGS, candidate.spacing ?? "") ? candidate.spacing! : defaultReading.spacing,
        bookId: typeof candidate.bookId === "string" ? candidate.bookId : null,
        places,
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
