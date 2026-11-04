// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useState } from "react";

/**
 * Whether something has been shown at least once: a pane or a tab put in the
 * page only then fetches what it lists only then, rather than as the app
 * opens, and is kept there after, hidden, so that what it holds survives.
 */
export function useShownOnce(shown: boolean): boolean {
    const [once, setOnce] = useState(shown);
    if (shown && !once) {
        setOnce(true);
    }
    return once || shown;
}
