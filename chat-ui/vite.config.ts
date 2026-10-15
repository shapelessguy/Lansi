// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The deck-status server does not allow requests from other origins, so the
// dev server forwards /anki to it.
const deckStatusUrl = process.env.ANKI_STATUS_URL ?? "http://127.0.0.1:8090";
// The same goes for the checker server, under /checker.
const checkerUrl = process.env.CHECKER_URL ?? "http://127.0.0.1:8092";

export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        // listen on every interface, so the GUI can be opened from other
        // machines of the LAN; the two servers it forwards to stay on 127.0.0.1
        host: true,
        // file change events are sometimes missed on Windows when a file is saved
        // several times in a row, which leaves the page running an old version
        watch: { usePolling: true, interval: 300 },
        proxy: {
            "/anki": {
                target: deckStatusUrl,
                rewrite: (path) => path.replace(/^\/anki/, ""),
            },
            "/checker": {
                target: checkerUrl,
                rewrite: (path) => path.replace(/^\/checker/, ""),
            },
        },
    },
});
