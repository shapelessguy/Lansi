// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/** The panels that share the right-hand side, one at a time. */
export type Panel = "checks" | "usage" | "settings";

/** Which panels are shown at the sides. */
export interface Layout {
    /** Whether the panel on the left, with the known words, the chats and the texts, is shown. */
    libraryOpen: boolean;
    /** The panel shown on the right, or null if none is. */
    panel: Panel | null;
}

const STORAGE_KEY = "chat-ui.layout";
const PANELS: readonly unknown[] = ["checks", "usage", "settings"];

/**
 * The layout for a window that wide, in pixels, when none has been chosen
 * yet. A panel covers part of the chat on a narrow window, so it starts
 * closed there.
 */
export function defaultLayout(windowWidth: number): Layout {
    return { libraryOpen: windowWidth > 720, panel: windowWidth > 1300 ? "usage" : null };
}

/** Fills in anything missing or unusable in a stored layout with the defaults. */
export function normalizeLayout(stored: unknown, windowWidth: number): Layout {
    const defaults = defaultLayout(windowWidth);
    if (typeof stored !== "object" || stored === null) {
        return defaults;
    }
    const candidate = stored as Partial<Layout>;
    return {
        libraryOpen: typeof candidate.libraryOpen === "boolean" ? candidate.libraryOpen : defaults.libraryOpen,
        // null is a choice too: the panel was closed
        panel: candidate.panel === null || PANELS.includes(candidate.panel)
            ? candidate.panel as Panel | null
            : defaults.panel,
    };
}

export function loadLayout(): Layout {
    try {
        return normalizeLayout(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null"), window.innerWidth);
    } catch {
        return defaultLayout(window.innerWidth);
    }
}

export function saveLayout(layout: Layout): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
    } catch {
        // storage can be unavailable in private windows; the layout then lasts for the session
    }
}
