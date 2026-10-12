// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { plainText, textId, textRequest, textTitle } from "./texts";

test("the title is the heading the text starts with", () => {
    expect(textTitle("# Der **alte** Film\n\nEs war einmal ein Film.")).toBe("Der alte Film");
});

test("a text without a heading is titled with its first words", () => {
    const title = textTitle("Es war einmal ein Film über den Frieden, den niemand sehen wollte.");

    expect(title).toBe("Es war einmal ein Film über den Frieden…");
});

test("an empty text is untitled", () => {
    expect(textTitle("  \n")).toBe("Untitled");
});

test("plain text drops headings, emphasis, lists, quotes and links but keeps the words", () => {
    const markdown = [
        "# Der Film",
        "",
        "Das ist **sehr** _gut_ und `kurz`.",
        "",
        "- eins",
        "- zwei",
        "",
        "> Siehe [hier](https://example.com).",
    ].join("\n");

    expect(plainText(markdown)).toBe(
        ["Der Film", "", "Das ist sehr gut und kurz.", "", "eins", "zwei", "", "Siehe hier."].join("\n"),
    );
});

test("the request names the topic and the length in words", () => {
    expect(textRequest("  ein Tag am See ", "short")).toBe("Write about: ein Tag am See\nLength: about 80 words.");
});

test("the request leaves the topic to the model when none is given", () => {
    expect(textRequest(" ", "long")).toBe("Choose a topic yourself.\nLength: about 320 words.");
});

test("an id is the local date and time followed by the title as a slug", () => {
    const createdAt = new Date(2026, 9, 12, 17, 5, 1).getTime();

    expect(textId(createdAt, "Der Film & die Bären!")).toBe("2026-10-12-170501-der-film-die-baren");
});

test("an id contains only characters the server accepts in a file name", () => {
    const id = textId(Date.now(), "Über/unter: «Straße» …\\..");

    expect(id).toMatch(/^[A-Za-z0-9_-]{1,80}$/);
});

test("a title with nothing usable gives an id of just the date and time", () => {
    const createdAt = new Date(2026, 0, 2, 3, 4, 5).getTime();

    expect(textId(createdAt, "…")).toBe("2026-01-02-030405");
});
