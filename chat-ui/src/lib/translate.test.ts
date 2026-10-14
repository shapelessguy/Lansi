// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { anchorFor, describeError, usageEntry } from "./translate";

/** A selection that takes up this much of the window. */
function rect(left: number, right: number, top: number, bottom = top + 20) {
    return { left, right, top, bottom };
}

test("a box is put above the selection and centred on it", () => {
    expect(anchorFor(rect(400, 500, 300), 1000, 160, 48)).toEqual({ left: 450, top: 292, above: true });
});

test("a box is put below the selection where there is no room above it", () => {
    expect(anchorFor(rect(400, 500, 30, 50), 1000, 160, 48)).toEqual({ left: 450, top: 58, above: false });
});

test("a box by a selection at the side of the window stays within the window", () => {
    expect(anchorFor(rect(0, 20, 300), 1000, 160, 48).left).toBe(88);
    expect(anchorFor(rect(980, 1000, 300), 1000, 160, 48).left).toBe(912);
});

test("a box wider than the window is centred in the window", () => {
    expect(anchorFor(rect(0, 20, 300), 300, 380, 48).left).toBe(150);
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
        chatId: "translate",
        model: "some/model",
        promptTokens: 40,
        completionTokens: 3,
        cost: 0.001,
    });
});
