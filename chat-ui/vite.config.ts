// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The checker server does not allow requests from other origins, so the dev
// server forwards /lansi/checker to it. The deck-status server is reached only
// by the checker, and never from the browser.
const checkerUrl = process.env.CHECKER_URL ?? "http://127.0.0.1:8092";

export default defineConfig({
    plugins: [react()],
    // the GUI is served under /lansi/ by the nginx of CyanHouse
    base: "/lansi/",
    server: {
        port: 5173,
        // only nginx, on this machine, reaches the GUI; it is opened from
        // elsewhere through it
        host: "127.0.0.1",
        // file change events are sometimes missed on Windows when a file is saved
        // several times in a row, which leaves the page running an old version
        watch: { usePolling: true, interval: 300 },
        proxy: {
            "/lansi/checker": {
                target: checkerUrl,
                rewrite: (path) => path.replace(/^\/lansi\/checker/, ""),
            },
        },
    },
});
