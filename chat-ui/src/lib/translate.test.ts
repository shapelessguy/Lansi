// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { anchorFor, describeError, usageEntry, visiblePart } from "./translate";

/** A selection that takes up this much of the window. */
function rect(left: number, right: number, top: number, bottom = top + 20) {
    return { left, right, top, bottom };
}

/** A window 1000 wide and 800 high. */
const WINDOW = rect(0, 1000, 0, 800);

test("a box is put above the selection and centred on it", () => {
    expect(anchorFor(rect(400, 500, 300), WINDOW, 160, 48)).toEqual({ left: 450, top: 292, above: true });
});

test("a box is put below the selection where there is no room above it", () => {
    expect(anchorFor(rect(400, 500, 30, 50), WINDOW, 160, 48)).toEqual({ left: 450, top: 58, above: false });
});

test("a box by a selection at the side of the window stays within the window", () => {
    expect(anchorFor(rect(0, 20, 300), WINDOW, 160, 48).left).toBe(88);
    expect(anchorFor(rect(980, 1000, 300), WINDOW, 160, 48).left).toBe(912);
});

test("a box wider than the window is centred in the window", () => {
    expect(anchorFor(rect(0, 20, 300), rect(0, 300, 0, 800), 380, 48).left).toBe(150);
});

test("a box below a selection at the foot of the window stays within the window", () => {
    expect(anchorFor(rect(400, 500, 30, 790), WINDOW, 160, 48)).toEqual({ left: 450, top: 744, above: false });
});

test("a box stays within what the selection is shown in, off the panels beside it and the bar above it", () => {
    // the pages of a book between a panel on each side, under their bar
    const pages = rect(460, 940, 120, 800);
    expect(anchorFor(rect(460, 480, 300), pages, 160, 48).left).toBe(548);
    expect(anchorFor(rect(400, 500, 130), pages, 160, 48).above).toBe(false);
    expect(anchorFor(rect(400, 500, 300), pages, 160, 48).above).toBe(true);
});

test("only the lines of a selection that can be seen are kept, put together", () => {
    const shown = rect(100, 500, 0, 800);
    // a line on the page shown, and one on the next page, to the right of it
    expect(visiblePart([rect(120, 480, 600, 620), rect(620, 900, 40, 60)], shown)).toEqual(rect(120, 480, 600, 620));
    expect(visiblePart([rect(120, 300, 600, 620), rect(100, 480, 620, 640)], shown)).toEqual(rect(100, 480, 600, 640));
});

test("nothing of a selection can be seen when all of it is on pages that are not shown", () => {
    expect(visiblePart([rect(620, 900, 40, 60)], rect(100, 500, 0, 800))).toBeNull();
});

test("a missing key is said in terms of where to add it, and anything else as the server said it", () => {
    expect(describeError("an OpenRouter key is needed", 502)).toBe("Add your OpenRouter API key in Settings first.");
    expect(describeError("OpenRouter refused the request (402): no credit", 502)).toBe(
        "OpenRouter refused the request (402): no credit",
    );
    expect(describeError(undefined, 500)).toBe("The server answered 500.");
});

test("what a request about a selection used is counted under its own heading, once", () => {
    const used = { id: "gen-1", model: "some/model", input_tokens: 40, output_tokens: 3, cost: 0.001 };

    expect(usageEntry(used, 1000)).toEqual({
        id: "gen-1",
        at: 1000,
        category: "translation",
        chatId: "translate",
        model: "some/model",
        promptTokens: 40,
        completionTokens: 3,
        cost: 0.001,
    });
});
