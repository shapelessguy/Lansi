// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Waits until the deck-status and checker servers accept connections, so that
// the GUI is started last and finds both of them running.

import { connect } from "node:net";

const servers = {
    "deck-status": process.env.ANKI_STATUS_URL ?? "http://127.0.0.1:8090",
    checker: process.env.CHECKER_URL ?? "http://127.0.0.1:8092",
};
const RETRY_MS = 500;
const REMIND_MS = 30_000;

function isListening(url) {
    const { hostname, port } = new URL(url);
    return new Promise((resolve) => {
        const socket = connect({ host: hostname, port: Number(port) || 80 });
        socket.once("connect", () => {
            socket.destroy();
            resolve(true);
        });
        socket.once("error", () => resolve(false));
    });
}

async function waitFor(name, url) {
    let waited = 0;
    while (!(await isListening(url))) {
        if (waited % REMIND_MS === 0) {
            console.log(`waiting for the ${name} server on ${url}`);
        }
        await new Promise((resolve) => setTimeout(resolve, RETRY_MS));
        waited += RETRY_MS;
    }
    console.log(`the ${name} server is up`);
}

await Promise.all(Object.entries(servers).map(([name, url]) => waitFor(name, url)));
