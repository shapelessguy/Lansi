// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import type { Stroke } from "./ink";
import { blocksOf, inkJson, inlineOf } from "./texts";

test("a line of a correction has what was wrong and what is right apart from the rest", () => {
    expect(inlineOf("Ich bin ~~gegeht~~ **gegangen**.")).toEqual([
        { kind: "plain", text: "Ich bin " },
        { kind: "wrong", text: "gegeht" },
        { kind: "plain", text: " " },
        { kind: "right", text: "gegangen" },
        { kind: "plain", text: "." },
    ]);
});

test("a correction has the comment on why after a mistake apart", () => {
    expect(inlineOf("~~Diese~~ **Dies** _(neuter)_ ist")).toEqual([
        { kind: "wrong", text: "Diese" },
        { kind: "plain", text: " " },
        { kind: "right", text: "Dies" },
        { kind: "plain", text: " " },
        { kind: "comment", text: "neuter" },
        { kind: "plain", text: " ist" },
    ]);
});

test("a correction is headings, the mistakes in a numbered list, and paragraphs with their lines", () => {
    const blocks = blocksOf(
        "# Wochenende: corrections\n\nIch bin ~~gegeht~~ **gegangen**.\nDer Film war gut.\n\n"
            + "## Mistakes\n\n1. ~~gegeht~~ **gegangen**: irregular\n",
    );

    expect(blocks.map((block) => block.kind)).toEqual(["heading", "paragraph", "heading", "item"]);
    expect(blocks[1]).toMatchObject({ kind: "paragraph", lines: [expect.any(Array), [{ text: "Der Film war gut." }]] });
    expect(blocks[3]).toMatchObject({ kind: "item", number: 1 });
});

test("the ink of a page is kept as the JSON of it, however often it is made", () => {
    const one: Stroke = { pen: "pen", color: "#000000", size: 2, points: [[1, 2, 0.5]] };
    const two: Stroke = { pen: "pencil", color: "#c62828", size: 3, points: [[3, 4, 0.2], [5, 6, 0.9]] };

    expect(JSON.parse(inkJson([one]))).toEqual({ ink: [one] });
    expect(JSON.parse(inkJson([one, two]))).toEqual({ ink: [one, two] });
    expect(JSON.parse(inkJson([]))).toEqual({ ink: [] });
});
