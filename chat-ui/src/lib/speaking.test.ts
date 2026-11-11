// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { afterEach, expect, test, vi } from "vitest";

import { fetchSentenceAudio, normalizeSpeed, spotBeside, startingAt, stepped, Unreachable, wanted } from "./speaking";

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

test("a reading starts at the sentence that goes on past the place it is to start from", () => {
    const sentences = [{ block: 4, end: 20 }, { block: 4, end: 45 }, { block: 5, end: 30 }];

    expect(startingAt(sentences, { block: 4, offset: 25 })).toBe(1);
    expect(startingAt(sentences, { block: 4, offset: 45 })).toBe(2);
    expect(startingAt(sentences, { block: 4, offset: 0 })).toBe(0);
    expect(startingAt(sentences, { block: 9, offset: 0 })).toBe(0);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

test("audio asked for while the connection is lost is to be asked for again, rather than given up on", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(fetchSentenceAudio("/books/b", "1.0")).rejects.toBeInstanceOf(Unreachable);
});

test("audio that the server says cannot be had is given up on", async () => {
    vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "no credit" }), { status: 404 })),
    );

    const failed = fetchSentenceAudio("/books/b", "1.0");

    await expect(failed).rejects.toThrow("no credit");
    await expect(failed).rejects.not.toBeInstanceOf(Unreachable);
});
