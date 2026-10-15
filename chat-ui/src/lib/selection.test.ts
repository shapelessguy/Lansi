// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { type Climbing, regionOf, selectedRange } from "./selection";

/** An element, with its attributes, in `parent`. */
function element(parent: Climbing | null, attributes: Record<string, string> = {}): Climbing {
    return { parentNode: parent, getAttribute: (name) => attributes[name] ?? null };
}

/** A text in `parent`. */
function text(parent: Climbing): Climbing {
    return { parentNode: parent };
}

/** The shadow root of `host`. */
function shadowOf(host: Climbing): Climbing {
    return { parentNode: null, host };
}

test("a selection is in the region it was made in, with the text around it taken from there", () => {
    const page = element(null);
    const messages = element(page, { "data-selectable": "" });
    const reply = element(messages);
    expect(regionOf(text(reply))).toEqual({ region: messages, root: messages, book: false });
});

test("a selection in a shadow root is in the region of its host, with the text around it taken from the shadow root", () => {
    const page = element(null);
    const exercise = element(page, { "data-selectable": "" });
    const shadow = shadowOf(exercise);
    const story = element(element(shadow));
    expect(regionOf(text(story))).toEqual({ region: exercise, root: shadow, book: false });
});

test("a selection in a book is said to be in a book, whose sentences can be read aloud", () => {
    const columns = element(element(null), { "data-selectable": "book" });
    expect(regionOf(text(element(columns)))?.book).toBe(true);
});

test("a selection outside every region is in none", () => {
    const page = element(null);
    element(page, { "data-selectable": "" });
    expect(regionOf(text(element(element(page))))).toBeNull();
});

test("a link without a parent is not taken for a shadow root, though it has a host", () => {
    const link = { parentNode: null, host: "example.com" } as unknown as Climbing;
    expect(regionOf(link)).toBeNull();
});

/** A range as far as `selectedRange` uses one, selecting `selected`. */
function fakeRange(selected: string) {
    const range = {
        collapsed: false,
        bounds: [] as unknown[],
        setStart: (node: unknown, offset: number) => range.bounds.push(node, offset),
        setEnd: (node: unknown, offset: number) => range.bounds.push(node, offset),
        toString: () => selected,
    };
    return range;
}

const story = { data: "Die Familie Müller wohnt in einer ruhigen Umgebung." } as unknown as Node;
const host = { data: "" } as unknown as Node;
const inStory = { startContainer: story, startOffset: 19, endContainer: story, endOffset: 33 };

test("the range selected in a shadow root is had from the composed ranges of the selection", () => {
    const shadow = {} as ShadowRoot;
    let asked: unknown;
    const selection = {
        rangeCount: 1,
        getRangeAt: () => ({ startContainer: host, startOffset: 0, endContainer: host, endOffset: 0 }),
        getComposedRanges: (options: unknown) => {
            asked = options;
            return [inStory];
        },
    } as unknown as Selection;
    const range = fakeRange("wohnt in einer");
    expect(selectedRange(selection, [shadow], () => range as unknown as Range)).toBe(range);
    expect(asked).toEqual({ shadowRoots: [shadow] });
    expect(range.bounds).toEqual([story, 19, story, 33]);
});

test("the range selected in a shadow root is had from the shadow root where there are no composed ranges", () => {
    const shadow = {
        getSelection: () => ({ rangeCount: 1, isCollapsed: false, getRangeAt: () => inStory }),
    } as unknown as ShadowRoot;
    const selection = { rangeCount: 0, getRangeAt: () => null } as unknown as Selection;
    const range = fakeRange("wohnt in einer");
    expect(selectedRange(selection, [shadow], () => range as unknown as Range)).toBe(range);
    expect(range.bounds).toEqual([story, 19, story, 33]);
});

test("no range is selected when only space is", () => {
    const selection = { getComposedRanges: () => [inStory] } as unknown as Selection;
    expect(selectedRange(selection, [], () => fakeRange("  \n") as unknown as Range)).toBeNull();
});
