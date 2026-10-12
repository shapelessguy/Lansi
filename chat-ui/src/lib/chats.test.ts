// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { type ChatStore, chatTitle, deleteChat, listedChats, selectChat, startChat, type StoredChat } from "./chats";

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
