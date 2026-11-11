// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * What the app keeps of the checker server on the device, to be used when
 * the server cannot be reached: what it starts from (the settings, the
 * chats and the list of books, with their covers), and all of each book
 * that is kept offline: its text, its notes, its pictures and the audio of
 * its sentences. Each answer is kept as it comes, in the browser's cache of
 * the user, and given in place of the server's when there is none.
 */

const KEPT_KEY = "chat-ui.offline-books";

/** The books that are kept offline, by their ids, as the reader of a book chose them. */
export function keptBooks(): string[] {
    try {
        const stored: unknown = JSON.parse(localStorage.getItem(KEPT_KEY) ?? "[]");
        return Array.isArray(stored) ? stored.filter((id): id is string => typeof id === "string") : [];
    } catch {
        return [];
    }
}

export function setKeptBooks(ids: string[]): void {
    try {
        localStorage.setItem(KEPT_KEY, JSON.stringify(ids));
    } catch {
        // without storage, nothing is kept
    }
}

/** What is always kept, as the app cannot start without it. */
const ALWAYS = /^\/(settings|chats|books)$|^\/books\/[^/]+\/cover$/;
/** What is kept of a book that is kept offline, by its id. */
const OF_BOOK = /^\/books\/([^/]+)(?:$|\/notes$|\/pictures\/[^/]+$|\/speech(?:$|\/[^/]+$))/;

/** Whether the answer to a GET of `path` is kept on the device. */
export function isKept(path: string, kept: readonly string[] = keptBooks()): boolean {
    if (ALWAYS.test(path)) {
        return true;
    }
    const book = OF_BOOK.exec(path)?.[1];
    return book !== undefined && kept.includes(book);
}

/** Whether there is a cache to keep things in: there is none outside a secure page, nor in tests. */
function hasCache(): boolean {
    return typeof caches !== "undefined";
}

/** The cache of the user who is logged in. */
export function openCache(user: string): Promise<Cache> {
    return caches.open(`lansi-checker:${user}`);
}

/** Whether an answer says that the server itself could not be reached, through the proxy in front of it. */
function unreachable(response: Response): boolean {
    return response.status === 502 || response.status === 503 || response.status === 504;
}

/**
 * The answer to a GET of `url`, which is `path` on the checker server: the
 * server's, kept as it comes, or, when it cannot be reached, the one kept
 * before, if there is one. With `keptFirst`, one kept before is given
 * without asking the server, as audio that does not change is.
 */
export async function cachedFetch(
    user: string,
    path: string,
    url: string,
    fetchIt: () => Promise<Response>,
    keptFirst = false,
): Promise<Response> {
    if (!hasCache() || !isKept(path)) {
        return fetchIt();
    }
    const cache = await openCache(user).catch(() => null);
    const kept = () => cache?.match(url) ?? Promise.resolve(undefined);
    if (keptFirst || !navigator.onLine) {
        const found = await kept();
        if (found) {
            return found;
        }
    }
    let response: Response;
    try {
        response = await fetchIt();
    } catch (caught) {
        // what was given up by whoever asked is not asked of the cache
        if (caught instanceof DOMException && caught.name === "AbortError") {
            throw caught;
        }
        const found = await kept();
        if (found) {
            return found;
        }
        throw caught;
    }
    if (response.ok) {
        await cache?.put(url, response.clone()).catch(() => undefined);
    } else if (unreachable(response)) {
        return (await kept()) ?? response;
    }
    return response;
}

/** Forgets all that is kept of a book on the device but its cover, which the list of books shows. */
export async function forgetBook(user: string, base: string, bookId: string): Promise<void> {
    if (!hasCache()) {
        return;
    }
    const cache = await openCache(user);
    const root = new URL(`${base}/books/${bookId}`, location.href).href;
    for (const request of await cache.keys()) {
        const { href } = new URL(request.url);
        const path = href.split("?")[0];
        if ((path === root || path.startsWith(`${root}/`)) && path !== `${root}/cover`) {
            await cache.delete(request);
        }
    }
}
