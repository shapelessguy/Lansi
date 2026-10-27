// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/** The panels that share the right-hand side, one at a time. */
export type Panel = "checks" | "usage" | "settings";

/** What the main area shows, as the tabs at the top choose it. */
export type Activity = "tutor" | "chat" | "books" | "texts" | "practice" | "evaluations";

/** Which panels are shown at the sides, and what the main area shows. */
/** The tabs of the library, on the left. */
export type LibraryTab = "words" | "vocabulary" | "books";
/** The tabs of the panel of the logs, on the left in place of the library. */
export type LogsTab = "logs" | "memories" | "exercises" | "favourites" | "sessions" | "evaluations";

export interface Layout {
    /** Whether the panel on the left, with the words and the books, is shown. */
    libraryOpen: boolean;
    /** Whether the logs are shown on the left, in place of the library. */
    logsOpen: boolean;
    /** The tab of the library shown last. */
    libraryTab: LibraryTab;
    /** The tab of the panel of the logs shown last. */
    logsTab: LogsTab;
    /** The panel shown on the right, or null if none is. */
    panel: Panel | null;
    /** What was shown last, which the app opens on. */
    activity: Activity;
    /** The text open last, by its id, if any. */
    text: string | null;
}

const STORAGE_KEY = "chat-ui.layout";
const PANELS: readonly unknown[] = ["checks", "usage", "settings"];
const LIBRARY_TABS: readonly unknown[] = ["words", "vocabulary", "books"];
const LOGS_TABS: readonly unknown[] = ["logs", "memories", "exercises", "favourites", "sessions", "evaluations"];
const ACTIVITIES: readonly unknown[] = ["tutor", "chat", "books", "texts", "practice", "evaluations"];

/**
 * The layout for a window that wide, in pixels, when none has been chosen
 * yet. A panel covers part of the chat on a narrow window, so it starts
 * closed there.
 */
export function defaultLayout(windowWidth: number): Layout {
    return {
        libraryOpen: windowWidth > 720,
        logsOpen: false,
        libraryTab: "vocabulary",
        logsTab: "logs",
        panel: windowWidth > 1300 ? "usage" : null,
        activity: "chat",
        text: null,
    };
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
        logsOpen: typeof candidate.logsOpen === "boolean" ? candidate.logsOpen : defaults.logsOpen,
        libraryTab: LIBRARY_TABS.includes(candidate.libraryTab)
            ? candidate.libraryTab as LibraryTab
            : defaults.libraryTab,
        logsTab: LOGS_TABS.includes(candidate.logsTab) ? candidate.logsTab as LogsTab : defaults.logsTab,
        // null is a choice too: the panel was closed
        panel: candidate.panel === null || PANELS.includes(candidate.panel)
            ? candidate.panel as Panel | null
            : defaults.panel,
        activity: ACTIVITIES.includes(candidate.activity) ? candidate.activity as Activity : defaults.activity,
        text: typeof candidate.text === "string" ? candidate.text : null,
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
