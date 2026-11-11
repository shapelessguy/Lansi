// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useSyncExternalStore } from "react";

import type { Book } from "./books";
import { canKeep, forgetBook, keptBooks, readKept, removeKept, setKeptBooks, writeKept } from "./offlineCache";
import { BASE, checkerFetch, checkerKept, currentSession } from "./session";
import type { BookSelection, Reading, SpokenSentence } from "./speaking";

/** A sentence of a book whose audio the server keeps, as it lists them, with who read it. */
interface ListedSentence extends Omit<SpokenSentence, "ready"> {
    model: string;
    voice: string;
}

/** The sentences of a book whose audio the server keeps, and how many the book has in all. */
interface Listing {
    sentences: ListedSentence[];
    total: number;
}

/** What is known of the audio of a sentence kept on the device: what it was made of, and its size in bytes. */
interface Had {
    made: string;
    size: number;
}

/** How much of a book is kept on the device, as the menu of the book shows it. */
export interface OfflineState {
    kept: boolean;
    /** Whether what is missing is being fetched. */
    syncing: boolean;
    /** How many sentences have their audio on the device. */
    audio: number;
    /** How many sentences the server has the audio of, and how many the book has, once they are known. */
    made: number | null;
    total: number | null;
    /** How large the audio on the device is, in bytes. */
    bytes: number;
}

/** How often, in milliseconds, a book that is open and kept offline is brought up to date with the server. */
const SYNC_MS = 60_000;
/** How many sentences have their audio fetched at once. */
const AT_ONCE = 4;

const states = new Map<string, OfflineState>();
const listeners = new Set<() => void>();
/** The books being brought up to date, so that each is only once at a time. */
const syncing = new Map<string, Promise<void>>();

function blank(bookId: string): OfflineState {
    return { kept: keptBooks().includes(bookId), syncing: false, audio: 0, made: null, total: null, bytes: 0 };
}

function stateOf(bookId: string): OfflineState {
    let state = states.get(bookId);
    if (!state) {
        state = blank(bookId);
        states.set(bookId, state);
    }
    return state;
}

function update(bookId: string, change: Partial<OfflineState>): void {
    states.set(bookId, { ...stateOf(bookId), ...change });
    listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

/** The path under which what is had of the audio of a book is noted, beside the audio itself. */
function hadPath(bookId: string): string {
    return `/books/${bookId}/speech-had`;
}

function madeOf(sentence: ListedSentence): string {
    return [sentence.text, sentence.model, sentence.voice].join("\u0000");
}

async function readHad(user: string, bookId: string): Promise<Record<string, Had>> {
    const text = await readKept(user, hadPath(bookId), BASE + hadPath(bookId));
    try {
        return text ? JSON.parse(text) : {};
    } catch {
        return {};
    }
}

function writeHad(user: string, bookId: string, had: Record<string, Had>): Promise<void> {
    return writeKept(user, hadPath(bookId), BASE + hadPath(bookId), JSON.stringify(had));
}

/** The listing of a book's audio as the device last had it from the server. */
async function keptListing(bookId: string): Promise<Listing | null> {
    const found = await checkerKept(`/books/${bookId}/speech`);
    return found ? found.json().catch(() => null) : null;
}

/** Shows what is kept of a book as the device has it, without asking the server. */
async function count(bookId: string): Promise<void> {
    const user = currentSession()?.user;
    if (!user || !canKeep()) {
        return;
    }
    const had = Object.values(await readHad(user, bookId));
    const listing = await keptListing(bookId);
    update(bookId, {
        audio: had.length,
        bytes: had.reduce((sum, each) => sum + each.size, 0),
        made: listing?.sentences.length ?? null,
        total: listing?.total ?? null,
    });
}

/** Asks the server for something of a book, to have it kept, and throws if it does not give it. */
async function fetched(path: string): Promise<Response> {
    const response = await checkerFetch(path);
    if (!response.ok) {
        throw new Error(`${path}: ${response.status}`);
    }
    return response;
}

/**
 * Brings what the device keeps of a book up to date with the server: its
 * text, its notes and its pictures, and the audio of every sentence the
 * server has, fetched where it is missing or was made anew, and let go of
 * where the server has it no more.
 */
async function sync(bookId: string): Promise<void> {
    const user = currentSession()?.user;
    if (!user || !canKeep()) {
        return;
    }
    update(bookId, { syncing: true });
    try {
        const book: Book = await (await fetched(`/books/${bookId}`)).json();
        await fetched(`/books/${bookId}/notes`).catch(() => undefined);
        for (const block of book.blocks) {
            const path = `/books/${bookId}/pictures/${block.image}`;
            if (block.image && !(await checkerKept(path))) {
                await fetched(path).catch(() => undefined);
            }
        }
        const listing: Listing = await (await fetched(`/books/${bookId}/speech`)).json();
        const had = await readHad(user, bookId);
        const listed = new Set(listing.sentences.map((each) => each.id));
        // what the server no longer has, as a sentence written anew, is let go of
        for (const id of Object.keys(had)) {
            if (!listed.has(id)) {
                delete had[id];
                const path = `/books/${bookId}/speech/${id}`;
                await removeKept(user, path, BASE + path);
            }
        }
        const show = () =>
            update(bookId, {
                audio: Object.keys(had).length,
                bytes: Object.values(had).reduce((sum, each) => sum + each.size, 0),
                made: listing.sentences.length,
                total: listing.total,
            });
        show();
        const missing: ListedSentence[] = [];
        for (const sentence of listing.sentences) {
            if (had[sentence.id]) {
                if (had[sentence.id].made !== madeOf(sentence)) {
                    missing.push(sentence);
                }
                continue;
            }
            const kept = await checkerKept(`/books/${bookId}/speech/${sentence.id}`);
            if (kept) {
                // audio the player fetched as it was listened to, which is as the server has it now
                had[sentence.id] = { made: madeOf(sentence), size: (await kept.blob()).size };
            } else {
                missing.push(sentence);
            }
        }
        show();
        let next = 0;
        let lastSaved = Date.now();
        const save = () => writeHad(user, bookId, had);
        async function worker() {
            while (next < missing.length && keptBooks().includes(bookId)) {
                const sentence = missing[next++];
                const audio = await (await fetched(`/books/${bookId}/speech/${sentence.id}`)).blob();
                had[sentence.id] = { made: madeOf(sentence), size: audio.size };
                show();
                // what is had is noted every so often, so that little is fetched again if the page is closed
                if (Date.now() - lastSaved > 5000) {
                    lastSaved = Date.now();
                    await save();
                }
            }
        }
        try {
            await Promise.all(Array.from({ length: AT_ONCE }, worker));
        } finally {
            if (keptBooks().includes(bookId)) {
                await save();
            }
        }
    } finally {
        update(bookId, { syncing: false });
    }
}

/** Brings what the device keeps of a book up to date, once at a time; nothing is said if the server cannot be reached. */
export function syncBook(bookId: string): Promise<void> {
    let running = syncing.get(bookId);
    if (!running) {
        running = sync(bookId)
            .catch((caught: unknown) => console.warn("the book could not be kept offline:", caught))
            .finally(() => syncing.delete(bookId));
        syncing.set(bookId, running);
    }
    return running;
}

/** Brings every book kept offline up to date, one after another, as the app starts. */
export async function syncAll(): Promise<void> {
    for (const id of keptBooks()) {
        await syncBook(id);
    }
}

/** Has a book kept on the device, or let go of with all that was kept of it. */
export async function keepOffline(bookId: string, keep: boolean): Promise<void> {
    const others = keptBooks().filter((id) => id !== bookId);
    setKeptBooks(keep ? [...others, bookId] : others);
    update(bookId, keep ? { kept: true } : { ...blank(bookId), kept: false });
    const user = currentSession()?.user;
    if (keep) {
        await syncBook(bookId);
    } else if (user) {
        await syncing.get(bookId);
        await forgetBook(user, BASE, bookId);
        update(bookId, { ...blank(bookId), kept: false });
    }
}

/**
 * How much of a book is kept on the device. While it is kept, and the hook
 * is in use, the book is brought up to date with the server now and then,
 * and as soon as the connection is back.
 */
export function useOffline(bookId: string | null): OfflineState | null {
    const state = useSyncExternalStore(subscribe, () => (bookId ? stateOf(bookId) : null));
    const kept = state?.kept ?? false;
    useEffect(() => {
        if (!bookId) {
            return;
        }
        if (!kept) {
            return;
        }
        count(bookId).catch(() => undefined);
        const again = () => {
            if (navigator.onLine) {
                syncBook(bookId);
            }
        };
        again();
        const timer = setInterval(again, SYNC_MS);
        window.addEventListener("online", again);
        return () => {
            clearInterval(timer);
            window.removeEventListener("online", again);
        };
    }, [bookId, kept]);
    return state;
}

/**
 * The sentences of a selection of a book that the device has the audio of,
 * to read it aloud while the server cannot be reached, or null if it has none.
 */
export async function offlineReading(bookId: string, selection: BookSelection): Promise<Reading | null> {
    const user = currentSession()?.user;
    if (!user || !canKeep() || !keptBooks().includes(bookId)) {
        return null;
    }
    const listing = await keptListing(bookId);
    const had = await readHad(user, bookId);
    const sentences = (listing?.sentences ?? []).filter((sentence) => {
        if (!(sentence.id in had) || sentence.block < selection.startBlock || sentence.block > selection.endBlock) {
            return false;
        }
        const from = sentence.block === selection.startBlock ? selection.start : 0;
        const to = sentence.block === selection.endBlock ? selection.end : Number.MAX_SAFE_INTEGER;
        return sentence.end > from && sentence.start < to;
    });
    if (sentences.length === 0) {
        return null;
    }
    return {
        sentences: sentences.map(({ id, block, start, end, text }) => ({ id, block, start, end, text, ready: true })),
        task: null,
    };
}

/** How large `bytes` is, in the unit that suits it. */
export function sizeOf(bytes: number): string {
    if (bytes < 1024 * 1024) {
        return `${Math.max(1, Math.round(bytes / 1024))} KB`;
    }
    return `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}
