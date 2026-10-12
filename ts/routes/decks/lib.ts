// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { DeckTreeNode } from "@generated/anki/decks_pb";

export interface DeckRow {
    deckId: bigint;
    name: string;
    /** 0 for a top-level deck. */
    depth: number;
    newCount: number;
    learnCount: number;
    reviewCount: number;
}

/** Lists every deck below `root` in display order, parents before children. */
export function deckRows(root: DeckTreeNode): DeckRow[] {
    const rows: DeckRow[] = [];
    const visit = (node: DeckTreeNode, depth: number): void => {
        rows.push({
            deckId: node.deckId,
            name: node.name,
            depth,
            newCount: node.newCount,
            learnCount: node.learnCount,
            reviewCount: node.reviewCount,
        });
        node.children.forEach((child) => visit(child, depth + 1));
    };
    root.children.forEach((child) => visit(child, 0));
    return rows;
}
