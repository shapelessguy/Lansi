// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Keeps the app itself on the device, so that it opens without a
// connection: each file of it is asked of the server first, and the one
// kept the last time it answered is given when it does not. What the
// checker server says is kept by the page (src/lib/offlineCache.ts), and
// passes by here as it is.

const CACHE = "lansi-app";
const CHECKER = new URL("checker/", self.registration.scope).pathname;

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("fetch", (event) => {
    const request = event.request;
    const url = new URL(request.url);
    if (
        request.method !== "GET"
        || url.origin !== self.location.origin
        || url.pathname.startsWith(CHECKER)
        || request.headers.get("accept") === "text/event-stream"
    ) {
        return;
    }
    event.respondWith(fromNetwork(request));
});

async function fromNetwork(request) {
    const cache = await caches.open(CACHE);
    // every page of the app is the same page, which is kept once
    const key = request.mode === "navigate" ? new URL("./", self.registration.scope).href : request;
    try {
        const response = await fetch(request);
        if (response.ok && response.type === "basic") {
            await cache.put(key, response.clone());
        }
        return response;
    } catch (caught) {
        const kept = await cache.match(key);
        if (kept) {
            return kept;
        }
        throw caught;
    }
}
