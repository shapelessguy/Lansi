// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/**
 * The attribute that a panel puts on what can be selected in it to have it
 * translated or taken into the vocabulary. Set to `book`, it is a book whose
 * sentences can also be read aloud. What is in the shadow root of such an
 * element, as the interface of an exercise is, can be selected as well.
 */
export const SELECTABLE_ATTRIBUTE = "data-selectable";
export const SELECTABLE = `[${SELECTABLE_ATTRIBUTE}]`;

/** A node as far as finding what it is selectable in needs it. */
export interface Climbing {
    parentNode: Climbing | null;
    /** The element a shadow root is the shadow root of. */
    host?: Climbing;
    getAttribute?: (name: string) => string | null;
}

/** What can be selected in, that something selected is in. */
export interface Region<N> {
    /** The element marked as selectable. */
    region: N;
    /** What the text around the selection is taken from: the region, or the shadow root of it the selection is in. */
    root: N;
    /** Whether it is a book, whose sentences can be read aloud. */
    book: boolean;
}

/** The element `node` is the shadow root of, if it is one; a link has a host too, as a string. */
function hostOf(node: Climbing): Climbing | null {
    return typeof node.host === "object" ? node.host : null;
}

/** The nearest of the elements a node is in that has an attribute, with its value, and the first shadow root on the way up. */
export interface Marked<N> {
    marked: N;
    value: string;
    /** The shadow root the node is in, if the way up went through one. */
    shadow: N | null;
}

/**
 * The nearest element that `node` is in, or is, that has `attribute`. The
 * way up goes from a shadow root on to its host, so that what is in the
 * interface of an exercise is in what the host of the exercise is in.
 */
export function markedAncestor<N extends Climbing>(node: N, attribute: string): Marked<N> | null {
    let shadow: N | null = null;
    for (let at: Climbing | null = node; at; at = at.parentNode ?? hostOf(at)) {
        const value = at.getAttribute?.(attribute);
        if (value !== undefined && value !== null) {
            return { marked: at as N, value, shadow };
        }
        if (!at.parentNode && hostOf(at) && !shadow) {
            shadow = at as N;
        }
    }
    return null;
}

/** The selectable region that `node` is in, if it is in one. */
export function regionOf<N extends Climbing>(node: N): Region<N> | null {
    const found = markedAncestor(node, SELECTABLE_ATTRIBUTE);
    // the text around a selection is that of the tree it was made in
    return found && { region: found.marked, root: found.shadow ?? found.marked, book: found.value === "book" };
}

/** Where a range starts and ends, as `getComposedRanges` gives it. */
interface Bounds {
    startContainer: Node;
    startOffset: number;
    endContainer: Node;
    endOffset: number;
}

/** What is selected in `shadow`, in the browsers that tell it that way. */
type Selecting = ShadowRoot & { getSelection?: () => Selection | null };

/** The selection as the browsers that took the shadow roots one by one at first see into them. */
type Spread = (...shadowRoots: ShadowRoot[]) => Bounds[];

function composedBounds(selection: Selection, shadowRoots: ShadowRoot[]): Bounds | null {
    // not there in the browsers that came before it
    if (!("getComposedRanges" in selection)) {
        return null;
    }
    try {
        return selection.getComposedRanges({ shadowRoots })[0] ?? null;
    } catch {
        return (selection.getComposedRanges as unknown as Spread).apply(selection, shadowRoots)[0] ?? null;
    }
}

/**
 * The range that is selected, even where it is in one of `shadowRoots`,
 * where the selection of the document has only the host. It is null when
 * nothing, or nothing but space, is selected.
 */
export function selectedRange(
    selection: Selection,
    shadowRoots: ShadowRoot[],
    create: () => Range = () => document.createRange(),
): Range | null {
    let bounds: Bounds | null = composedBounds(selection, shadowRoots);
    if (!bounds) {
        const inShadow = shadowRoots
            .map((shadow) => (shadow as Selecting).getSelection?.())
            .find((within) => within && within.rangeCount > 0 && !within.isCollapsed);
        const chosen = inShadow ?? selection;
        bounds = chosen.rangeCount > 0 ? chosen.getRangeAt(0) : null;
    }
    if (!bounds) {
        return null;
    }
    const range = create();
    range.setStart(bounds.startContainer, bounds.startOffset);
    range.setEnd(bounds.endContainer, bounds.endOffset);
    return range.collapsed || !range.toString().trim() ? null : range;
}

/** The shadow roots of what can be selected in, which the selection of the document does not see into. */
export function selectableShadowRoots(): ShadowRoot[] {
    return Array.from(document.querySelectorAll(SELECTABLE)).flatMap((element) =>
        element.shadowRoot ? [element.shadowRoot] : []
    );
}
