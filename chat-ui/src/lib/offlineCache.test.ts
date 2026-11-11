// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { isKept } from "./offlineCache";

test("what the app starts from is kept whether or not a book is kept offline", () => {
    for (const path of ["/settings", "/chats", "/books", "/books/b/cover"]) {
        expect(isKept(path, []), path).toBe(true);
    }
});

test("all of a book is kept when it is kept offline, and nothing of the others", () => {
    const paths = ["/books/b", "/books/b/notes", "/books/b/pictures/p", "/books/b/speech", "/books/b/speech/1.2"];
    for (const path of paths) {
        expect(isKept(path, ["b"]), path).toBe(true);
        expect(isKept(path.replace("/b", "/c"), ["b"]), path).toBe(false);
    }
    expect(isKept("/books/b/versions", ["b"])).toBe(false);
    expect(isKept("/tasks", ["b"])).toBe(false);
});
