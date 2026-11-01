// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

// Which folders of the favourites were left open, remembered by the browser
// for the next time the panel is shown. A folder not among them is shut, as
// every folder is at first.

const STORAGE_KEY = "chat-ui.open-folders";

/** The ids of the open folders, out of whatever was stored. */
export function normalizeOpenFolders(stored: unknown): Set<number> {
    if (!Array.isArray(stored)) {
        return new Set();
    }
    return new Set(stored.filter((id): id is number => Number.isInteger(id)));
}

export function loadOpenFolders(): Set<number> {
    try {
        return normalizeOpenFolders(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null"));
    } catch {
        return new Set();
    }
}

export function saveOpenFolders(open: Set<number>): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify([...open]));
    } catch {
        // storage can be unavailable in private windows; the folders then stay as they are for the session
    }
}
