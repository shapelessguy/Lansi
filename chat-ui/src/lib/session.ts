// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/** Who is logged in, and the token the checker server gave them to say so. */
export interface Session {
    user: string;
    token: string;
}

const STORAGE_KEY = "chat-ui.session";
/** Where the dev server forwards requests to the checker server, under the base the GUI is served at. */
const BASE = `${import.meta.env.BASE_URL}checker`;

export function normalizeSession(stored: unknown): Session | null {
    if (typeof stored !== "object" || stored === null) {
        return null;
    }
    const { user, token } = stored as Partial<Session>;
    return typeof user === "string" && user && typeof token === "string" && token ? { user, token } : null;
}

export function loadSession(): Session | null {
    try {
        return normalizeSession(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null"));
    } catch {
        return null;
    }
}

function saveSession(session: Session | null): void {
    try {
        if (session) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
        } else {
            localStorage.removeItem(STORAGE_KEY);
        }
    } catch {
        // without storage, the session lasts until the page is closed
    }
}

let current: Session | null = loadSession();
const listeners = new Set<(session: Session | null) => void>();

/** The session there is at present, if anyone is logged in. */
export function currentSession(): Session | null {
    return current;
}

/** Has `listener` told whenever someone logs in or is logged out. Returns what stops that. */
export function onSessionChange(listener: (session: Session | null) => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

function setSession(session: Session | null): void {
    current = session;
    saveSession(session);
    listeners.forEach((listener) => listener(session));
}

/** Logs in. Throws an error that says why if it cannot be done. */
export async function logIn(user: string, password: string): Promise<void> {
    let response: Response;
    try {
        response = await fetch(`${BASE}/login`, { method: "POST", body: JSON.stringify({ user, password }) });
    } catch {
        throw new Error("The server cannot be reached.");
    }
    if (response.status === 401 || response.status === 400) {
        throw new Error("Wrong name or password.");
    }
    if (!response.ok) {
        throw new Error("The server cannot be reached. Is `just dev` running?");
    }
    setSession(normalizeSession(await response.json()));
}

export function logOut(): void {
    setSession(null);
}

/**
 * Asks the checker server for something as whoever is logged in. If the
 * server no longer takes the token, the session is over, and the login is
 * shown again.
 */
export async function checkerFetch(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    if (current) {
        headers.set("Authorization", `Bearer ${current.token}`);
    }
    const response = await fetch(`${BASE}${path}`, { ...init, headers });
    if (response.status === 401) {
        setSession(null);
    }
    return response;
}
