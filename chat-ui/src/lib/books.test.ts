// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import {
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    normalizeReading,
    pageCount,
    pageOf,
    resized,
    segments,
    sentence,
    shownSize,
} from "./books";

test("the text of a block is cut where its links start and end", () => {
    const block = { text: "Siehe die Anmerkung dazu.", size: 1, links: [[6, 19, 5]] as [number, number, number][] };

    expect(segments(block)).toEqual([
        { text: "Siehe " },
        { text: "die Anmerkung", to: 5 },
        { text: " dazu." },
    ]);
    expect(segments({ text: "Nur Text.", size: 1 })).toEqual([{ text: "Nur Text." }]);
});

test("a link that is inside another or outside the text is not one", () => {
    const links: [number, number, number | string][] = [[4, 8, "https://example.org"], [0, 6, 1], [5, 7, 2], [
        7,
        40,
        3,
    ]];

    expect(segments({ text: "Eins zwei", size: 1, links })).toEqual([
        { text: "Eins z", to: 1 },
        { text: "wei" },
    ]);
});

test("the pages are counted by the columns the text is laid out in", () => {
    expect(pageCount(800, 800, 48)).toBe(1);
    expect(pageCount(800 * 3 + 48 * 2, 800, 48)).toBe(3);
    expect(pageCount(0, 800, 48)).toBe(1);
});

test("a paragraph is on the page of the column it starts in", () => {
    expect(pageOf(0, 800, 48)).toBe(0);
    expect(pageOf(847.6, 800, 48)).toBe(1);
    expect(pageOf(848 * 2, 800, 48)).toBe(2);
});

test("the text is made larger and smaller a step at a time, within limits", () => {
    expect(resized(18, 1)).toBe(20);
    expect(resized(18, -1)).toBe(16);
    expect(resized(MAX_FONT_SIZE, 1)).toBe(MAX_FONT_SIZE);
    expect(resized(MIN_FONT_SIZE, -1)).toBe(MIN_FONT_SIZE);
});

test("a block is shown in its size unless that is far larger or smaller than the text", () => {
    expect(shownSize({ text: "Kapitel 1", size: 1.5 })).toBe(1.5);
    expect(shownSize({ text: "Der Hund", size: 8 })).toBe(3);
    expect(shownSize({ text: "Anmerkung", size: 0.3 })).toBe(0.7);
});

test("what was stored about reading is kept as it was left", () => {
    const stored = {
        fontSize: 24,
        paper: "sepia",
        font: "serif",
        spacing: "wide",
        bookId: "book-1",
        places: { "book-1": 120 },
    };

    expect(normalizeReading(stored)).toEqual(stored);
});

test.each([null, "large", {}, { fontSize: "24", paper: "pink", font: 3, spacing: "toString", bookId: 3, places: [] }])(
    "what was stored about reading as %j falls back to the defaults",
    (stored) => {
        expect(normalizeReading(stored)).toEqual({
            fontSize: 18,
            paper: "app",
            font: "sans",
            spacing: "normal",
            bookId: null,
            places: {},
        });
    },
);

test("a stored size beyond the limits and a place that is not one are not used", () => {
    const reading = normalizeReading({ fontSize: 400, places: { a: -1, b: 2.5, c: "3", d: 7 } });

    expect(reading.fontSize).toBe(MAX_FONT_SIZE);
    expect(reading.places).toEqual({ d: 7 });
});

test("what the server said is wrong with a file is shown as a sentence", () => {
    expect(sentence("the file is not an EPUB book")).toBe("The file is not an EPUB book.");
    expect(sentence("Too large!")).toBe("Too large!");
});
