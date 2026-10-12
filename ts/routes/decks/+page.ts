// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html
import { deckTree } from "@generated/backend";

import type { PageLoad } from "./$types";
import { deckRows } from "./lib";

export const load = (async () => {
    // a non-zero time asks the backend to include due counts
    const now = BigInt(Math.floor(Date.now() / 1000));
    const tree = await deckTree({ now });
    return { decks: deckRows(tree) };
}) satisfies PageLoad;
