// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ChatMessage } from "./openrouter";
import { checkerFetch } from "./session";

export interface StoredChat {
    id: string;
    /** The context the chat was started with. */
    contextId: string;
    /** The language that was being learned when the chat was started. */
    language?: string;
    messages: ChatMessage[];
    /** When a message was last added, in milliseconds since the epoch. */
    updatedAt: number;
}

export interface ChatStore {
    chats: StoredChat[];
    /** The chat being shown. Always one of `chats`. */
    activeId: string;
}

/** Where the chats were kept before the server kept them. */
const OLD_STORAGE_KEYS = ["chat-ui.chats", "chat-ui.chat"];
const TITLE_LENGTH = 48;

export function emptyChat(contextId: string, language = ""): StoredChat {
    return { id: crypto.randomUUID(), contextId, language, messages: [], updatedAt: Date.now() };
}

function storeWith(chat: StoredChat): ChatStore {
    return { chats: [chat], activeId: chat.id };
}

async function send(path: string, init?: RequestInit): Promise<Response> {
    let response: Response;
    try {
        response = await checkerFetch(path, init);
    } catch {
        throw new Error("The server cannot be reached. Is `just dev` running?");
    }
    if (!response.ok) {
        throw new Error(`The server answered ${response.status}.`);
    }
    return response;
}

/** The chats the server keeps for whoever is logged in. */
export async function fetchChats(): Promise<StoredChat[]> {
    const { chats }: { chats: StoredChat[] } = await (await send("/chats")).json();
    // The chats that were kept in this browser are let go of: the server's are the ones that count.
    try {
        OLD_STORAGE_KEYS.forEach((key) => localStorage.removeItem(key));
    } catch {
        // nothing to let go of
    }
    return chats.map((chat) => ({
        ...chat,
        // the server also says whether each message has been processed, which nothing here goes by yet
        messages: chat.messages.map(({ role, content }) => ({ role, content })),
    }));
}

/** Has the server keep a chat as it is now. `leaving` is for when the page is being left. */
export async function putChat(chat: StoredChat, leaving = false): Promise<void> {
    await send(`/chats/${chat.id}`, { method: "PUT", body: JSON.stringify(chat), keepalive: leaving });
}

export async function removeChat(id: string): Promise<void> {
    await send(`/chats/${id}`, { method: "DELETE" });
}

/** The chats with the most recent one on show, or a fresh one if there are none. */
export function storeOf(chats: StoredChat[], contextId: string, language: string): ChatStore {
    const latest = listedChats({ chats, activeId: "" })[0];
    return latest ? { chats, activeId: latest.id } : storeWith(emptyChat(contextId, language));
}

/**
 * What has to be told to the server for it to have the chats as they are in
 * `store`: the chats that are not as they were when last told, and the ids
 * of those that are gone. `told` is each chat as the server has it. Chats
 * nothing was written in are not kept.
 */
export function chatsToTell(
    told: ReadonlyMap<string, StoredChat>,
    store: ChatStore,
): { changed: StoredChat[]; removed: string[] } {
    const kept = store.chats.filter((chat) => chat.messages.length > 0);
    return {
        changed: kept.filter((chat) => told.get(chat.id) !== chat),
        removed: [...told.keys()].filter((id) => !kept.some((chat) => chat.id === id)),
    };
}

export function activeChat(store: ChatStore): StoredChat {
    return store.chats.find((chat) => chat.id === store.activeId) ?? store.chats[0];
}

/** A chat is named after the first thing the user said in it. */
export function chatTitle(chat: StoredChat): string {
    const first = chat.messages.find((message) => message.role === "user")?.content ?? "";
    const line = first.trim().replace(/\s+/g, " ");
    if (!line) {
        return "New chat";
    }
    return line.length > TITLE_LENGTH ? `${line.slice(0, TITLE_LENGTH).trimEnd()}…` : line;
}

/** The chats worth listing, most recently used first. */
export function listedChats(store: ChatStore): StoredChat[] {
    return store.chats
        .filter((chat) => chat.messages.length > 0)
        .sort((a, b) => b.updatedAt - a.updatedAt);
}

/** Shows `id`. Chats that were opened but never written in are dropped. */
export function selectChat(store: ChatStore, id: string): ChatStore {
    if (!store.chats.some((chat) => chat.id === id)) {
        return store;
    }
    return { chats: store.chats.filter((chat) => chat.id === id || chat.messages.length > 0), activeId: id };
}

/** Shows a fresh chat, keeping the one that was open. */
export function startChat(store: ChatStore, contextId: string, language = ""): ChatStore {
    const chat = emptyChat(contextId, language);
    return selectChat({ chats: [...store.chats, chat], activeId: chat.id }, chat.id);
}

/** Removes a chat. If it was the one shown, the most recent other chat is shown instead. */
export function deleteChat(store: ChatStore, id: string, contextId: string, language = ""): ChatStore {
    const chats = store.chats.filter((chat) => chat.id !== id);
    if (store.activeId !== id) {
        return { ...store, chats };
    }
    const next = listedChats({ chats, activeId: "" })[0];
    return next ? { chats, activeId: next.id } : startChat({ chats, activeId: "" }, contextId, language);
}

export function updateChat(store: ChatStore, id: string, change: (chat: StoredChat) => StoredChat): ChatStore {
    return { ...store, chats: store.chats.map((chat) => (chat.id === id ? change(chat) : chat)) };
}
