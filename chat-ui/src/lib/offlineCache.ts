// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * What the app keeps of the checker server on the device, to be used when
 * the server cannot be reached: what it starts from (the settings, the
 * chats and the list of books, with their covers), and all of each book
 * that is kept offline: its text, its notes, its pictures and the audio of
 * its sentences. Each answer is kept as it comes, and given in place of the
 * server's when there is none: in the Android app by the app, once for both
 * of its addresses (android/.../Offline.kt), and in a browser in its cache
 * of the user.
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

/** What the Android app gives the page to reach what it keeps (android/.../Offline.kt). */
interface NativeStore {
    read(user: string, path: string): string | null;
    write(user: string, path: string, text: string): void;
    remove(user: string, path: string): void;
    forget(user: string, bookId: string): void;
}

declare global {
    interface Window {
        lansiOffline?: NativeStore;
    }
}

/**
 * The store of the Android app, if the page is in it: there it is kept
 * once for both addresses of the app, rather than by the browser for each.
 */
export function nativeStore(): NativeStore | null {
    return typeof window === "undefined" ? null : window.lansiOffline ?? null;
}

/** Whether there is anywhere to keep things: there is nowhere outside a secure page, nor in tests. */
export function canKeep(): boolean {
    return nativeStore() !== null || typeof caches !== "undefined";
}

/** The cache of the browser for the user who is logged in, where the page keeps things outside the app. */
function openCache(user: string): Promise<Cache> {
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
 * `fetchIt` asks the server with the headers it is given besides its own.
 */
export async function cachedFetch(
    user: string,
    path: string,
    url: string,
    fetchIt: (headers?: Record<string, string>) => Promise<Response>,
    keptFirst = false,
): Promise<Response> {
    if (!canKeep() || !isKept(path)) {
        return fetchIt();
    }
    if (nativeStore()) {
        // the app keeps it as it passes, and gives what it has when the server cannot be reached
        return fetchIt({ "X-Lansi-Offline": keptFirst ? "first" : "keep", "X-Lansi-User": user });
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

/** What is kept of a path on the checker server, at `url`, without asking the server, if anything is. */
export async function keptAnswer(
    user: string,
    url: string,
    fetchIt: (headers: Record<string, string>) => Promise<Response>,
): Promise<Response | undefined> {
    if (nativeStore()) {
        const found = await fetchIt({ "X-Lansi-Offline": "only", "X-Lansi-User": user }).catch(() => undefined);
        return found?.ok ? found : undefined;
    }
    return (await openCache(user)).match(url);
}

/** Text kept under a path that is not the server's, such as what is noted of what is kept. */
export async function readKept(user: string, path: string, url: string): Promise<string | null> {
    const store = nativeStore();
    if (store) {
        return store.read(user, path);
    }
    const found = await (await openCache(user)).match(url);
    return found ? found.text() : null;
}

export async function writeKept(user: string, path: string, url: string, text: string): Promise<void> {
    const store = nativeStore();
    if (store) {
        store.write(user, path, text);
    } else {
        await (await openCache(user)).put(url, new Response(text));
    }
}

/** Lets go of what is kept of a path. */
export async function removeKept(user: string, path: string, url: string): Promise<void> {
    const store = nativeStore();
    if (store) {
        store.remove(user, path);
    } else {
        await (await openCache(user)).delete(url);
    }
}

/** Forgets all that is kept of a book on the device but its cover, which the list of books shows. */
export async function forgetBook(user: string, base: string, bookId: string): Promise<void> {
    const store = nativeStore();
    if (store) {
        store.forget(user, bookId);
        return;
    }
    if (typeof caches === "undefined") {
        return;
    }
    const cache = await openCache(user);
    const root = new URL(`${base}/books/${bookId}`, location.href).href;
    for (const request of await cache.keys()) {
        const path = request.url.split("?")[0];
        if ((path === root || path.startsWith(`${root}/`)) && path !== `${root}/cover`) {
            await cache.delete(request);
        }
    }
}

/**
 * In the Android app, lets go of what the page kept itself before the app
 * kept it, as the service worker and the cache of each address did.
 */
export async function dropBrowserCopies(): Promise<void> {
    const workers = await navigator.serviceWorker?.getRegistrations().catch(() => []) ?? [];
    await Promise.all(workers.map((worker) => worker.unregister()));
    if (typeof caches !== "undefined") {
        for (const name of await caches.keys()) {
            if (name === "lansi-app" || name.startsWith("lansi-checker:")) {
                await caches.delete(name);
            }
        }
    }
}
