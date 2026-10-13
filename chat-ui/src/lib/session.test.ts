// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { normalizeSession } from "./session";

test("a stored session with a user and a token is kept", () => {
    expect(normalizeSession({ user: "ada", token: "ada.1.abc", more: 1 })).toEqual({ user: "ada", token: "ada.1.abc" });
});

test("anything else that was stored is no session", () => {
    expect(normalizeSession(null)).toBeNull();
    expect(normalizeSession("ada")).toBeNull();
    expect(normalizeSession({ user: "ada" })).toBeNull();
    expect(normalizeSession({ user: "", token: "t" })).toBeNull();
    expect(normalizeSession({ user: "ada", token: 3 })).toBeNull();
});
