// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import {
    keptStretches,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    normalizeReading,
    pageCount,
    pageOf,
    partFits,
    resized,
    sectionsAt,
    segments,
    sentence,
    shownSize,
    storyAt,
    storyParts,
    stretchTokens,
    suggestedStories,
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
        offsets: { "book-1": 340 },
        versions: { "book-1": "version-2" },
    };

    expect(normalizeReading(stored)).toEqual(stored);
});

test.each([
    null,
    "large",
    {},
    { fontSize: "24", paper: "pink", font: 3, spacing: "toString", bookId: 3, places: [], versions: ["v"] },
])(
    "what was stored about reading as %j falls back to the defaults",
    (stored) => {
        expect(normalizeReading(stored)).toEqual({
            fontSize: 18,
            paper: "app",
            font: "sans",
            spacing: "normal",
            bookId: null,
            places: {},
            offsets: {},
            versions: {},
        });
    },
);

test("a stored size beyond the limits and a place that is not one are not used", () => {
    const reading = normalizeReading({
        fontSize: 400,
        places: { a: -1, b: 2.5, c: "3", d: 7 },
        offsets: { a: 12, b: -3 },
    });

    expect(reading.fontSize).toBe(MAX_FONT_SIZE);
    expect(reading.places).toEqual({ d: 7 });
    expect(reading.offsets).toEqual({ a: 12 });
});

test("what the server said is wrong with a file is shown as a sentence", () => {
    expect(sentence("the file is not an EPUB book")).toBe("The file is not an EPUB book.");
    expect(sentence("Too large!")).toBe("Too large!");
});

test("a block is in the sections around it, from the outermost in, and in none past the end", () => {
    const kapitel = { title: "Kapitel 1", start: 3, end: 9, sections: [{ title: "Vokabeln", start: 6, end: 9 }] };
    const sections = [
        { title: "", start: 0, end: 2 },
        { title: "Der Feuer-Traum", start: 2, end: 12, sections: [kapitel] },
    ];

    expect(sectionsAt(sections, 7).map((section) => section.title)).toEqual([
        "Der Feuer-Traum",
        "Kapitel 1",
        "Vokabeln",
    ]);
    expect(sectionsAt(sections, 2).map((section) => section.title)).toEqual(["Der Feuer-Traum"]);
    expect(sectionsAt(sections, 12)).toEqual([]);
});

test("the stretches kept are what is not in a section left out, those that touch made one", () => {
    const sections = [
        { title: "", start: 0, end: 2 },
        {
            title: "Der Feuer-Traum",
            start: 2,
            end: 12,
            sections: [
                { title: "Kapitel 1", start: 3, end: 8, sections: [{ title: "Anhang", start: 6, end: 8 }] },
                { title: "Kapitel 2", start: 8, end: 11, sections: [{ title: "Anhang", start: 10, end: 11 }] },
            ],
        },
        { title: "Glossar", start: 12, end: 15 },
    ];

    expect(keptStretches(sections, new Set())).toEqual([[0, 15]]);
    expect(keptStretches(sections, new Set(["0-2", "6-8", "10-11", "12-15"]))).toEqual([[2, 6], [8, 10], [11, 12]]);
    expect(keptStretches(sections, new Set(["2-12", "3-8"]))).toEqual([[0, 2], [12, 15]]);
});

test("a story goes on until the next starts, and what is before the first is a part of its own", () => {
    const sections = [
        { title: "", start: 0, end: 2 },
        {
            title: "Der Feuer-Traum",
            start: 2,
            end: 9,
            sections: [{ title: "Kapitel 1", start: 3, end: 9, sections: [{ title: "Anhang", start: 6, end: 9 }] }],
        },
        { title: "Hartnäckigkeit", start: 9, end: 12, sections: [{ title: "Kapitel 1", start: 10, end: 12 }] },
        { title: "Skull Tooth", start: 12, end: 15, sections: [{ title: "Kapitel 1", start: 13, end: 15 }] },
    ];

    expect(storyParts(sections, new Set(["6-9"]), new Set(["2-9", "12-15"]))).toEqual([
        { story: null, stretches: [[0, 2]] },
        { story: "2-9", stretches: [[2, 6], [9, 12]] },
        { story: "12-15", stretches: [[12, 15]] },
    ]);
    expect(storyParts(sections, new Set(), new Set(["2-9", "10-12"]))).toEqual([
        { story: null, stretches: [[0, 2]] },
        { story: "2-9", stretches: [[2, 10]] },
        { story: "10-12", stretches: [[10, 15]] },
    ]);
    expect(storyParts(sections, new Set(["0-2"]), new Set())).toEqual([{ story: null, stretches: [[2, 15]] }]);
    expect(storyAt(new Set(["2-9", "12-15"]), 11)).toBe("2-9");
    expect(storyAt(new Set(["2-9"]), 1)).toBeNull();
});

test("the tokens of a part are those of the blocks of its stretches", () => {
    const tokens = [3, 5, 7, 11, 13];

    expect(stretchTokens([[0, 2], [3, 5]], tokens)).toBe(3 + 5 + 11 + 13);
    expect(stretchTokens([], tokens)).toBe(0);
});

test("a part fits if it takes less than a third of what the reasoning model takes in", () => {
    expect(partFits(32_999, 99_000)).toBe(true);
    expect(partFits(33_000, 99_000)).toBe(false);
});

test("the stories suggested are the sections at the top with a title and sections under them", () => {
    const sections = [
        { title: "", start: 0, end: 2, sections: [{ title: "Inhalt", start: 1, end: 2 }] },
        { title: "Vorwort", start: 2, end: 4 },
        { title: "Der Feuer-Traum", start: 4, end: 9, sections: [{ title: "Kapitel 1", start: 5, end: 9 }] },
    ];

    expect(suggestedStories(sections)).toEqual(new Set(["4-9"]));
});
