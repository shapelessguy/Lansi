// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ChatMessage } from "./openrouter";

export interface StoredChat {
    id: string;
    /** The context the chat was started with. */
    contextId: string;
    messages: ChatMessage[];
    /** When a message was last added, in milliseconds since the epoch. */
    updatedAt: number;
}

export interface ChatStore {
    chats: StoredChat[];
    /** The chat being shown. Always one of `chats`. */
    activeId: string;
}

const STORAGE_KEY = "chat-ui.chats";
/** Where the single chat was kept before previous chats were saved. */
const LEGACY_STORAGE_KEY = "chat-ui.chat";
const TITLE_LENGTH = 48;

export function emptyChat(contextId: string): StoredChat {
    return { id: crypto.randomUUID(), contextId, messages: [], updatedAt: Date.now() };
}

function storeWith(chat: StoredChat): ChatStore {
    return { chats: [chat], activeId: chat.id };
}

export function loadChats(defaultContextId: string): ChatStore {
    try {
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null");
        if (
            stored && Array.isArray(stored.chats)
            && stored.chats.some((chat: StoredChat) => chat.id === stored.activeId)
        ) {
            return stored;
        }
        const legacy = JSON.parse(localStorage.getItem(LEGACY_STORAGE_KEY) ?? "null");
        if (legacy && Array.isArray(legacy.messages) && legacy.messages.length > 0) {
            return storeWith({ ...emptyChat(legacy.contextId ?? defaultContextId), ...legacy });
        }
    } catch {
        // unreadable storage is treated like a first visit
    }
    return storeWith(emptyChat(defaultContextId));
}

export function saveChats(store: ChatStore): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    } catch {
        // the chats then last until the page is closed
    }
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
export function startChat(store: ChatStore, contextId: string): ChatStore {
    const chat = emptyChat(contextId);
    return selectChat({ chats: [...store.chats, chat], activeId: chat.id }, chat.id);
}

/** Removes a chat. If it was the one shown, the most recent other chat is shown instead. */
export function deleteChat(store: ChatStore, id: string, contextId: string): ChatStore {
    const chats = store.chats.filter((chat) => chat.id !== id);
    if (store.activeId !== id) {
        return { ...store, chats };
    }
    const next = listedChats({ chats, activeId: "" })[0];
    return next ? { chats, activeId: next.id } : startChat({ chats, activeId: "" }, contextId);
}

export function updateChat(store: ChatStore, id: string, change: (chat: StoredChat) => StoredChat): ChatStore {
    return { ...store, chats: store.chats.map((chat) => (chat.id === id ? change(chat) : chat)) };
}
