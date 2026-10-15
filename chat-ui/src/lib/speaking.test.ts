// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { normalizeSpeed, speechInstructions, spotBeside, stepped, wanted } from "./speaking";

test("the speech model is told the direction as written, with the language and the level filled in", () => {
    expect(speechInstructions("  Speak {{language}} for a learner at {{level}}; only {{language}}. ", "Italian", "A2"))
        .toBe("Speak Italian for a learner at A2; only Italian.");
    expect(speechInstructions("Read slowly.", "German", "B1")).toBe("Read slowly.");
});

test("the next and the previous sentence are a step away, and there is none beyond the ends", () => {
    expect(stepped(2, 1, 5)).toBe(3);
    expect(stepped(2, -1, 5)).toBe(1);
    expect(stepped(4, 1, 5)).toBe(4);
    expect(stepped(0, -1, 5)).toBe(0);
});

test("the audio asked for is that of the sentence listened to and of the next few", () => {
    expect(wanted(0, 10)).toEqual([0, 1, 2]);
    expect(wanted(7, 10)).toEqual([7, 8, 9]);
    expect(wanted(9, 10)).toEqual([9]);
});

test("a stored speed is kept if it is one there is, and is the usual pace otherwise", () => {
    expect(normalizeSpeed(0.8)).toBe(0.8);
    expect(normalizeSpeed(1.5)).toBe(1.5);
    expect([3, "fast", null, undefined].map(normalizeSpeed)).toEqual([1, 1, 1, 1]);
});

test("the player is put to the left of what it is shown beside, level with it", () => {
    expect(spotBeside({ left: 400, top: 300, bottom: 334 }, { width: 260, height: 46 })).toEqual({
        left: 132,
        top: 294,
    });
});

test("the player is put above what it is shown beside when there is no room to the left", () => {
    expect(spotBeside({ left: 120, top: 300, bottom: 334 }, { width: 260, height: 46 })).toEqual({
        left: 120,
        top: 246,
    });
});

test("the player does not reach over the edge of what the thing it is shown beside is in", () => {
    // there is room to the left in the window, but not in the chat, which starts at 300
    expect(spotBeside({ left: 400, top: 300, bottom: 334 }, { width: 260, height: 46 }, 300)).toEqual({
        left: 400,
        top: 246,
    });
});
