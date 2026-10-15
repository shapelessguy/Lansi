// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import type { ChatMessage } from "./openrouter";
import { checkerFetch } from "./session";
import type { BackgroundTask } from "./tasks";
import { profileUsage, type UsageEntry } from "./usage";

/** What was selected, with the text around it in what it was selected in. */
export interface Picked {
    selection: string;
    before: string;
    after: string;
}

/** A selection with the sentences it is in and the few before them, as the server cut them out. */
export type Passage = Picked;

/** A selection that was translated, which a chat can be started about. */
export interface Translated {
    passage: Passage;
    translation: string;
}

/** Who is asked, and for whom. */
export interface Asking {
    apiKey: string;
    model: string;
    /** The language being learned. */
    language: string;
    /** The language to translate into. */
    into: string;
}

/** What starts on a line of its own, so that text on either side of its edge is not of one sentence. */
const BLOCKS = "p, li, div, h1, h2, h3, h4, h5, h6, blockquote, pre, td, th, article, section";
/** How much of the text before and after a selection is sent with it, in characters. The server drops what it does not need. */
export const BEFORE_LENGTH = 3000;
export const AFTER_LENGTH = 1000;
/** What the requests about selections are counted under. */
export const USAGE_ID = "translate";

function blockOf(node: Node, root: Node): Node {
    const block = node.parentElement?.closest(BLOCKS);
    return block && root.contains(block) ? block : root;
}

function lastWithin(node: Node): Node {
    let last = node;
    while (last.lastChild) {
        last = last.lastChild;
    }
    return last;
}

/**
 * The text of `range` with the text around it in `root`, an element or a
 * shadow root, as far as is sent with it. Where one paragraph ends and the
 * next starts there is a new line.
 */
export function textAround(range: Range, root: Node, selection = range.toString()): Picked {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const { startContainer, startOffset, endContainer, endOffset } = range;

    let before = "";
    let from: Node = startContainer;
    if (startContainer instanceof Text) {
        before = startContainer.data.slice(0, startOffset);
    } else if (startOffset > 0) {
        // everything up to the end of the child before the one the range starts at
        from = lastWithin(startContainer.childNodes[startOffset - 1]);
        before = from instanceof Text ? from.data : "";
    }
    walker.currentNode = from;
    let block = blockOf(from, root);
    for (let node = walker.previousNode(); node && before.length < BEFORE_LENGTH; node = walker.previousNode()) {
        const its = blockOf(node, root);
        before = (node as Text).data + (its === block ? "" : "\n") + before;
        block = its;
    }

    let after = "";
    let to: Node = endContainer;
    if (endContainer instanceof Text) {
        after = endContainer.data.slice(endOffset);
    } else if (endOffset > 0) {
        to = lastWithin(endContainer.childNodes[endOffset - 1]);
    }
    walker.currentNode = to;
    block = blockOf(to, root);
    for (let node = walker.nextNode(); node && after.length < AFTER_LENGTH; node = walker.nextNode()) {
        const its = blockOf(node, root);
        after += (its === block ? "" : "\n") + (node as Text).data;
        block = its;
    }

    return { selection, before: before.slice(-BEFORE_LENGTH), after: after.slice(0, AFTER_LENGTH) };
}

/** Where a box is put by what was selected. */
export interface Anchor {
    /** The middle of the box, from the left edge of the window, in pixels. */
    left: number;
    /** The edge of the box that is towards the selection, from the top of the window. */
    top: number;
    /** Whether the box is above the selection rather than below it. */
    above: boolean;
}

/** The space left between a box and the selection, and the edge of the window, in pixels. */
const GAP = 8;

/**
 * Where to put a box at most `width` wide for a selection that takes up
 * `rect` of a window `viewport` wide: above the selection and centred on it,
 * but not over the edge of the window, and below it where there is not
 * `room` above.
 */
export function anchorFor(
    rect: { left: number; right: number; top: number; bottom: number },
    viewport: number,
    width: number,
    room: number,
): Anchor {
    const half = Math.min(width, viewport - 2 * GAP) / 2;
    const middle = (rect.left + rect.right) / 2;
    const left = Math.max(GAP + half, Math.min(viewport - GAP - half, middle));
    const above = rect.top - GAP >= room;
    return { left, top: above ? rect.top - GAP : rect.bottom + GAP, above };
}

/** What a request to the model used, as the usage is counted. */
export function usageEntry(used: ProfileUsage, at: number): UsageEntry {
    return profileUsage(used, at, "translation", USAGE_ID);
}

async function ask<Reply>(path: string, body: object, asking: Asking, signal?: AbortSignal): Promise<Reply> {
    let response: Response;
    try {
        response = await checkerFetch(path, {
            method: "POST",
            // the server asks the model with the key; it is not kept there
            headers: asking.apiKey ? { "X-OpenRouter-Key": asking.apiKey } : {},
            body: JSON.stringify({ ...body, model: asking.model, language: asking.language, into: asking.into }),
            signal,
        });
    } catch (error) {
        if (signal?.aborted) {
            throw error;
        }
        throw new Error("The server cannot be reached.");
    }
    const reply = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(describeError(reply.error, response.status));
    }
    return reply;
}

/** What to say when the server could not do what was asked, by the reason it gave. */
export function describeError(reason: unknown, status: number): string {
    if (reason === "an OpenRouter key is needed") {
        return "Add your OpenRouter API key in Settings first.";
    }
    return typeof reason === "string" && reason ? reason : `The server answered ${status}.`;
}

/** Has the selection translated as it is meant where it stands. */
export async function translate(
    picked: Picked,
    asking: Asking,
    signal?: AbortSignal,
): Promise<Translated & { usage: ProfileUsage[] }> {
    return ask("/translate", picked, asking, signal);
}

/** Has the last of `messages` answered, which are what was asked and answered so far about a translated selection. */
export async function askAbout(
    translated: Translated,
    messages: ChatMessage[],
    asking: Asking,
    signal?: AbortSignal,
): Promise<{ reply: string; usage: ProfileUsage[] }> {
    return ask("/translate/chat", { ...translated, messages }, asking, signal);
}

/**
 * Has the words of the selection taken into the vocabulary, with
 * `decisionModel` sorting them into categories. The server does that in the
 * background: what comes back is the task it started.
 */
export async function takeWords(
    picked: Picked,
    asking: Asking,
    decisionModel: string,
    signal?: AbortSignal,
): Promise<BackgroundTask> {
    const { task } = await ask<{ task: BackgroundTask }>(
        "/vocabulary/selection",
        { ...picked, decision_model: decisionModel },
        asking,
        signal,
    );
    return task;
}
