// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import {
    type ChatStore,
    chatsToTell,
    chatTitle,
    deleteChat,
    isAtEnd,
    listedChats,
    selectChat,
    startChat,
    type StoredChat,
    storeOf,
} from "./chats";

function chat(id: string, updatedAt: number, firstMessage?: string): StoredChat {
    const messages = firstMessage === undefined ? [] : [{ role: "user" as const, content: firstMessage }];
    return { id, contextId: "tutor", messages, updatedAt };
}

function ids(chats: StoredChat[]): string[] {
    return chats.map((entry) => entry.id);
}

test("a chat is titled with the first thing the user said", () => {
    const withReply: StoredChat = {
        ...chat("a", 1, "  Wie geht's?\nGut?  "),
        messages: [
            { role: "user", content: "  Wie geht's?\nGut?  " },
            { role: "assistant", content: "Mir geht es gut." },
        ],
    };

    expect(chatTitle(withReply)).toBe("Wie geht's? Gut?");
});

test("a long first message is cut short in the title", () => {
    const title = chatTitle(chat("a", 1, "wort ".repeat(40)));

    expect(title.length).toBeLessThanOrEqual(49);
    expect(title.endsWith("…")).toBe(true);
});

test("a chat nobody has written in is titled as new", () => {
    expect(chatTitle(chat("a", 1))).toBe("New chat");
});

test("chats are listed most recent first, without unwritten ones", () => {
    const store: ChatStore = {
        chats: [chat("old", 10, "eins"), chat("empty", 30), chat("new", 20, "zwei")],
        activeId: "empty",
    };

    expect(ids(listedChats(store))).toEqual(["new", "old"]);
});

test("starting a chat keeps the one that was open and shows the new one", () => {
    const store: ChatStore = { chats: [chat("old", 10, "eins")], activeId: "old" };

    const next = startChat(store, "assistant");

    expect(next.chats).toHaveLength(2);
    expect(next.activeId).not.toBe("old");
    expect(next.chats.find((entry) => entry.id === next.activeId)).toMatchObject({
        contextId: "assistant",
        messages: [],
    });
});

test("starting a chat twice does not pile up unwritten chats", () => {
    const store: ChatStore = { chats: [chat("old", 10, "eins")], activeId: "old" };

    const next = startChat(startChat(store, "tutor"), "tutor");

    expect(next.chats).toHaveLength(2);
});

test("selecting a chat drops the unwritten one that was open", () => {
    const store: ChatStore = { chats: [chat("old", 10, "eins"), chat("empty", 30)], activeId: "empty" };

    expect(selectChat(store, "old")).toEqual({ chats: [chat("old", 10, "eins")], activeId: "old" });
});

test("selecting a chat that does not exist changes nothing", () => {
    const store: ChatStore = { chats: [chat("old", 10, "eins")], activeId: "old" };

    expect(selectChat(store, "gone")).toBe(store);
});

test("deleting another chat leaves the open one showing", () => {
    const store: ChatStore = { chats: [chat("a", 10, "eins"), chat("b", 20, "zwei")], activeId: "b" };

    expect(deleteChat(store, "a", "tutor")).toEqual({ chats: [chat("b", 20, "zwei")], activeId: "b" });
});

test("deleting the open chat shows the most recent remaining one", () => {
    const store: ChatStore = {
        chats: [chat("a", 10, "eins"), chat("b", 30, "zwei"), chat("c", 20, "drei")],
        activeId: "b",
    };

    expect(deleteChat(store, "b", "tutor").activeId).toBe("c");
});

test("deleting the last chat leaves a new one to write in", () => {
    const store: ChatStore = { chats: [chat("a", 10, "eins")], activeId: "a" };

    const next = deleteChat(store, "a", "tutor");

    expect(next.chats).toHaveLength(1);
    expect(next.chats[0]).toMatchObject({ id: next.activeId, messages: [] });
});

test("the chat that was written in last is the one shown", () => {
    const chats = [chat("a", 10, "eins"), chat("b", 30, "zwei"), chat("c", 20, "drei")];

    expect(storeOf(chats, "tutor", "German")).toEqual({ chats, activeId: "b" });
});

test("a fresh chat of the language being learned is shown when there are none", () => {
    const store = storeOf([], "tutor", "German");

    expect(store.chats).toHaveLength(1);
    expect(store.activeId).toBe(store.chats[0].id);
    expect(store.chats[0]).toMatchObject({ contextId: "tutor", language: "German", messages: [] });
});

test("the server is told of the chats that are not as it has them", () => {
    const a = chat("a", 10, "eins");
    const b = chat("b", 20, "zwei");
    const changed = { ...b, updatedAt: 30 };

    const toTell = chatsToTell(new Map([["a", a], ["b", b]]), { chats: [a, changed], activeId: "a" });

    expect(toTell).toEqual({ changed: [changed], removed: [] });
});

test("the server is told of a new chat once it is written in, and of one that is gone", () => {
    const a = chat("a", 10, "eins");
    const written = chat("b", 20, "zwei");
    const empty = { ...chat("c", 30, "x"), messages: [] };

    const toTell = chatsToTell(new Map([["a", a]]), { chats: [written, empty], activeId: "c" });

    expect(toTell).toEqual({ changed: [written], removed: ["a"] });
});

test("a list counts as scrolled to its end when it is there or nearly there", () => {
    expect(isAtEnd(1000, 600, 400)).toBe(true);
    expect(isAtEnd(1000, 560, 400)).toBe(true);
    expect(isAtEnd(1000, 300, 400)).toBe(false);
    // one that is not longer than its window
    expect(isAtEnd(300, 0, 400)).toBe(true);
});
