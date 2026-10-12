// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { DeckTreeNode } from "@generated/anki/decks_pb";
import { expect, test } from "vitest";

import { deckRows } from "./lib";

test("decks are listed parents first with their nesting depth", () => {
    const tree = new DeckTreeNode({
        children: [
            { name: "German", children: [{ name: "Verbs", children: [{ name: "Irregular" }] }] },
            { name: "Spanish" },
        ],
    });

    const rows = deckRows(tree).map((row) => [row.name, row.depth]);

    expect(rows).toEqual([["German", 0], ["Verbs", 1], ["Irregular", 2], ["Spanish", 0]]);
});

test("each deck row carries its due counts", () => {
    const tree = new DeckTreeNode({
        children: [{ deckId: 5n, name: "German", newCount: 20, learnCount: 3, reviewCount: 41 }],
    });

    expect(deckRows(tree)).toEqual([
        { deckId: 5n, name: "German", depth: 0, newCount: 20, learnCount: 3, reviewCount: 41 },
    ]);
});

test("a collection without decks has no rows", () => {
    expect(deckRows(new DeckTreeNode())).toEqual([]);
});
