// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef } from "react";

/**
 * What Back closes, from the one on top: a dialog that asks something, then
 * what covers the page (a page on the whole screen, an editor), then a window
 * floating over it, then the panels at the sides.
 */
export type BackLayer = "panel" | "window" | "cover" | "dialog";

const ORDER: BackLayer[] = ["panel", "window", "cover", "dialog"];

interface Closer {
    layer: BackLayer;
    close: () => void;
}

// in the order they were opened, the latest last
const open: Closer[] = [];

/**
 * Closes what is on top, as the Back of the phone does in the Android app;
 * says whether there was anything to close, which there is not when the app
 * itself is left.
 */
export function goBack(): boolean {
    let top: Closer | null = null;
    for (const closer of open) {
        if (!top || ORDER.indexOf(closer.layer) >= ORDER.indexOf(top.layer)) {
            top = closer;
        }
    }
    top?.close();
    return top !== null;
}

/** Has Back call `close` while `shown`, unless something on a layer above it, or opened after it on its own, is there. */
export function useBack(layer: BackLayer, close: () => void, shown = true): void {
    const latest = useRef(close);
    latest.current = close;
    useEffect(() => {
        if (!shown) {
            return;
        }
        return closeOnBack(layer, () => latest.current());
    }, [layer, shown]);
}

/** Has Back call `close`, as `useBack` does, until what this returns is called. */
export function closeOnBack(layer: BackLayer, close: () => void): () => void {
    const closer: Closer = { layer, close };
    open.push(closer);
    return () => {
        const at = open.indexOf(closer);
        if (at >= 0) {
            open.splice(at, 1);
        }
    };
}

declare global {
    interface Window {
        /** What the Android app calls on Back, before it leaves the app itself. */
        lansiBack?: () => boolean;
    }
}
