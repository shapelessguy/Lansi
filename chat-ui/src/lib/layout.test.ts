// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { defaultLayout, normalizeLayout } from "./layout";

test("a wide window starts with the library and the usage panel", () => {
    expect(defaultLayout(1600)).toEqual({ libraryOpen: true, panel: "usage", activity: "chat", text: null });
});

test("a narrow window starts without the panels that would cover the chat", () => {
    expect(defaultLayout(900)).toEqual({ libraryOpen: true, panel: null, activity: "chat", text: null });
    expect(defaultLayout(600)).toEqual({ libraryOpen: false, panel: null, activity: "chat", text: null });
});

test("a stored layout is kept as it was left", () => {
    expect(normalizeLayout({ libraryOpen: false, panel: "checks", activity: "texts", text: "t1" }, 1600)).toEqual({
        libraryOpen: false,
        panel: "checks",
        activity: "texts",
        text: "t1",
    });
});

test("a right-hand panel that was closed stays closed", () => {
    expect(normalizeLayout({ libraryOpen: true, panel: null }, 1600).panel).toBeNull();
});

test.each([null, "usage", { panel: "inbox" }, { libraryOpen: "yes" }, { activity: "games" }, {}])(
    "a stored layout of %j falls back to the defaults where it is unusable",
    (stored) => {
        expect(normalizeLayout(stored, 1600)).toEqual(defaultLayout(1600));
    },
);
