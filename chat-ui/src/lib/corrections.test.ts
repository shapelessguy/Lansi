// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { changedLetters, type Correction, correctionOf, pageCorrections, tokensOf } from "./corrections";

test("a typed text is cut into words between its spaces, a mark going with its word, as the server cuts it", () => {
    const tokens = tokensOf("Ciao,  Giulia!\nCome stai?");

    expect(tokens.map((token) => token.text)).toEqual(["Ciao,", "Giulia!", "Come", "stai?"]);
    expect(tokens[1]).toEqual({ text: "Giulia!", start: 7, end: 14 });
});

test("only the letters that changed in a word are marked, if the rest of it stays", () => {
    // a wrong ending, a missing letter, an accent, and a word that is all wrong
    expect(changedLetters("schönen", "schöner")).toEqual({ start: 6, end: 0 });
    expect(changedLetters("bellisimo", "bellissimo")).toEqual({ start: 6, end: 3 });
    expect(changedLetters("Pero", "Però")).toEqual({ start: 3, end: 0 });
    expect(changedLetters("uno", "del")).toBeNull();
});

test("a correction is read from what was kept, and anything else is not", () => {
    const kept = JSON.stringify({ words: ["a"], corrections: [], summary: "Good." });

    expect(correctionOf(kept)).toEqual({ words: ["a"], corrections: [], summary: "Good." });
    expect(correctionOf("~~a~~ **b**")).toBeNull();
    expect(correctionOf(null)).toBeNull();
});

test("the corrections of a page are those of its words, counted on it", () => {
    // two pages, of words 0 to 2 and 3 to 5
    const corrections: Correction[] = [
        { type: "replace", from_id: 1, to_id: 4, text: "x" },
        { type: "insert", after_id: -1, text: "La" },
        { type: "insert", after_id: 2, text: "y" },
        { type: "split", id: 5, text: "a b" },
        { type: "move", from_id: 0, to_id: 0, after_id: 4 },
        { type: "move", from_id: 3, to_id: 3, after_id: 5 },
    ];

    expect(pageCorrections(corrections, 0, 3)).toEqual([
        { type: "replace", from_id: 1, to_id: 2, text: "x" },
        { type: "insert", after_id: -1, text: "La" },
        { type: "insert", after_id: 2, text: "y" },
    ]);
    expect(pageCorrections(corrections, 3, 3)).toEqual([
        { type: "replace", from_id: 0, to_id: 1, text: "x" },
        { type: "split", id: 2, text: "a b" },
        { type: "move", from_id: 0, to_id: 0, after_id: 2 },
    ]);
});
