// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { orModel } from "./models";
import { call, choosingOf, type Learner, posting } from "./practice";
import type { Settings } from "./settings";
import type { BackgroundTask } from "./tasks";

/**
 * The corrections of a text of the learner's, typed or written by hand
 * alike: its words, each by its id, its place among them from 0, and what a
 * model said is to be done to them, each a function of its own, as
 * checker/exercises/correcting/backend.py describes them. A typed text shows
 * them in its words; one written by hand draws them on its pages, as
 * marks.ts does.
 */

interface About {
    category?: string;
    explanation?: string;
}

/** Words from `from_id` to `to_id`, both in. */
interface Span {
    from_id: number;
    to_id: number;
}

export type Correction =
    | (About & Span & { type: "replace"; text: string })
    | (About & Span & { type: "erase" })
    // after_id -1 is before the first word
    | (About & { type: "insert"; after_id: number; text: string })
    | (About & Span & { type: "move"; after_id: number })
    | (About & Span & { type: "join"; text: string })
    | (About & { type: "split"; id: number; text: string })
    | (About & Span & { type: "suggest"; text: string })
    | (About & Span & { type: "comment"; text: string })
    | (About & Span & { type: "praise"; text: string })
    | (Span & { type: "misread"; text: string })
    | (Span & { type: "illegible" });

/** Those that correct a mistake of the learner's. */
export const MISTAKES: ReadonlySet<Correction["type"]> = new Set([
    "replace",
    "erase",
    "insert",
    "move",
    "join",
    "split",
]);

/** A text as it was corrected: its words, what is to be done to them, and what it most needs. */
export interface CorrectionRecord {
    words: string[];
    corrections: Correction[];
    summary: string;
}

/** The correction kept as `content`, or null if it is not one. */
export function correctionOf(content: string | null): CorrectionRecord | null {
    try {
        const read = JSON.parse(content ?? "");
        if (read && Array.isArray(read.words) && Array.isArray(read.corrections)) {
            return {
                words: read.words.map(String),
                corrections: read.corrections as Correction[],
                summary: typeof read.summary === "string" ? read.summary : "",
            };
        }
    } catch {
        // not JSON
    }
    return null;
}

/** The first and the last id of the words a correction is about, or null for an insertion. */
export function spanOf(correction: Correction): [number, number] | null {
    if ("id" in correction) {
        return [correction.id, correction.id];
    }
    return "from_id" in correction ? [correction.from_id, correction.to_id] : null;
}

/**
 * The words of a typed text, as their ids name them, with where each is in
 * it: what is between its spaces, a mark such as a comma going with the
 * word it is written against, as the server cuts it.
 */
export function tokensOf(content: string): { text: string; start: number; end: number }[] {
    return [...content.matchAll(/\S+/gu)].map((found) => ({
        text: found[0],
        start: found.index ?? 0,
        end: (found.index ?? 0) + found[0].length,
    }));
}

/**
 * What changes when the word `from` is written as `to`: how many letters at
 * its start and at its end stay as they are, if they are enough that only
 * what is between them is marked, as an ending, or a letter, that is wrong;
 * or null if most of it is wrong.
 */
export function changedLetters(from: string, to: string): { start: number; end: number } | null {
    const [old, next] = [[...from.normalize("NFC")], [...to.normalize("NFC")]];
    let start = 0;
    while (start < old.length && start < next.length && old[start] === next[start]) {
        start++;
    }
    let end = 0;
    while (
        end < old.length - start && end < next.length - start
        && old[old.length - 1 - end] === next[next.length - 1 - end]
    ) {
        end++;
    }
    // a word that is mostly wrong is struck out whole
    return start + end > 0 && 2 * (start + end) >= old.length ? { start, end } : null;
}

/**
 * The corrections of the words of a page that has `count` of the words of
 * the text from `offset` on, with their ids counted on the page: a span cut
 * to the words on it, and an insertion, or a move, kept on the page it goes
 * on, a move whose words and place are not on the same page left out.
 */
export function pageCorrections(corrections: Correction[], offset: number, count: number): Correction[] {
    const last = offset + count - 1;
    // what goes after a word of the page, or before the first of the text on the first page
    const placed = (after: number) => (after >= offset && after <= last) || (after === -1 && offset === 0);
    const kept: Correction[] = [];
    for (const correction of corrections) {
        const span = spanOf(correction);
        if (correction.type === "insert") {
            if (placed(correction.after_id)) {
                kept.push({ ...correction, after_id: correction.after_id - offset });
            }
            continue;
        }
        if (!span || span[1] < offset || span[0] > last) {
            continue;
        }
        if (correction.type === "move") {
            if (span[0] >= offset && span[1] <= last && placed(correction.after_id)) {
                kept.push({
                    ...correction,
                    from_id: span[0] - offset,
                    to_id: span[1] - offset,
                    after_id: correction.after_id - offset,
                });
            }
            continue;
        }
        if (correction.type === "split") {
            kept.push({ ...correction, id: correction.id - offset });
            continue;
        }
        kept.push({
            ...correction,
            from_id: Math.max(span[0], offset) - offset,
            to_id: Math.min(span[1], last) - offset,
        } as Correction);
    }
    return kept;
}

/** Who asks for a text to be corrected, as their settings say, the text corrected by their reasoning model. */
export function learnerOf(settings: Settings): Learner {
    return {
        apiKey: settings.apiKey,
        model: orModel(settings.reasoningModel, settings.model),
        imageModel: settings.imageModel,
        visionModel: settings.visionModel,
        into: settings.translateInto,
        level: settings.level,
        // a model that answers at once corrects badly
        reasoning: true,
    };
}

/**
 * Starts correcting the text `textId`, typed or written by hand, on the
 * server, in the background, so that it goes on though the app is closed:
 * a session of the exercise that corrects texts, graded, its log written
 * and its words taken into the vocabulary as any exercise's are, after
 * which the text is locked with its correction kept. Resolves with the task.
 */
export async function correctText(textId: string, settings: Settings): Promise<BackgroundTask> {
    const { task } = await call<{ task: BackgroundTask }>(
        `/texts/${encodeURIComponent(textId)}/correct`,
        posting(choosingOf(settings, "none", null), learnerOf(settings)),
    );
    return task;
}

/** The latest correction of the text `textId` among `tasks`, if there is one. */
export function correctionTask(tasks: BackgroundTask[], textId: string): BackgroundTask | undefined {
    // the newest first
    return tasks.find((task) => task.kind === "correction" && task.subject === textId);
}
