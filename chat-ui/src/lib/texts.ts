// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type Message, t } from "./i18n";
import type { Stroke } from "./ink";
import { checkerFetch } from "./session";

/**
 * A text the learner writes, such as their homework, or the correction of
 * one, which is a text of its own. A text that was corrected is locked.
 */
export interface Text {
    id: string;
    title: string;
    /** In Markdown; null as texts are listed. */
    content: string | null;
    language: string;
    kind: "text" | "correction";
    /** The text a correction is of. */
    corrects: string | null;
    /** The session of practice it was corrected in. */
    session: string | null;
    /** In seconds since the epoch. */
    createdAt: number;
    updatedAt: number;
    /** When it was corrected, after which it is not changed; null for a text that may still be written in. */
    lockedAt: number | null;
    /** How many words it has, as texts are listed. */
    words?: number;
    /** Whether it is written by hand, in pages, rather than typed. It then says what its pages were read to say. */
    handwritten: boolean;
    /** The pages it is written by hand in, the first first, when it is fetched alone. */
    pages?: HandwrittenPage[];
}

/** A word read from a handwritten page, with the four corners of the box around it, in units of the page. */
export interface HandwrittenWord {
    text: string;
    box: [number, number][];
    /** On which line and in which paragraph of the page it is, counted from 0. */
    line: number;
    paragraph: number;
    /** How sure the reading of it is, from 0 to 1. */
    confidence: number;
}

/** A page of a text written by hand: its size, its ink, and the words read from it, if it was read. */
export interface HandwrittenPage {
    id: string;
    width: number;
    height: number;
    ink: Stroke[];
    words: HandwrittenWord[] | null;
    /** In seconds since the epoch: when it was last written on, and read. */
    inkedAt: number;
    readAt: number | null;
}

export async function fetchTexts(): Promise<Text[]> {
    const response = await checkerFetch("/texts");
    if (!response.ok) {
        throw new Error(t("The texts could not be listed."));
    }
    return (await response.json()).texts;
}

export async function fetchText(id: string): Promise<Text> {
    const response = await checkerFetch(`/texts/${encodeURIComponent(id)}`);
    if (!response.ok) {
        throw new Error(t("The text could not be found."));
    }
    return response.json();
}

/** Keeps a text as it is now, starting it if there is none: written by hand, with a blank page, if `handwritten`. */
export async function saveText(
    id: string,
    title: string,
    content: string,
    language: string,
    handwritten = false,
): Promise<void> {
    const response = await checkerFetch(`/texts/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify({ title, content, language, handwritten }),
    });
    if (!response.ok) {
        const reply = await response.json().catch(() => ({}));
        throw new Error(typeof reply.error === "string" ? reply.error : "The text could not be kept.");
    }
}

export async function deleteText(id: string): Promise<void> {
    await checkerFetch(`/texts/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** A piece of a line of a correction: text as it is, what was wrong, what is right, or a comment on why. */
export type Inline = { kind: "plain" | "wrong" | "right" | "comment"; text: string };

/** A block of a correction: a heading, an item of a numbered list, or a paragraph, with its lines. */
export type Block =
    | { kind: "heading"; level: number; inline: Inline[] }
    | { kind: "item"; number: number; inline: Inline[] }
    | { kind: "paragraph"; lines: Inline[][] };

/** The pieces of a line: `~~what was wrong~~`, `**what is right**`, `_(why)_`, and the text between them. */
export function inlineOf(line: string): Inline[] {
    const pieces: Inline[] = [];
    const marks = /~~(.+?)~~|\*\*(.+?)\*\*|_\((.+?)\)_/g;
    let at = 0;
    for (const found of line.matchAll(marks)) {
        if (found.index > at) {
            pieces.push({ kind: "plain", text: line.slice(at, found.index) });
        }
        pieces.push(
            found[1] !== undefined
                ? { kind: "wrong", text: found[1] }
                : found[2] !== undefined
                ? { kind: "right", text: found[2] }
                : { kind: "comment", text: found[3] },
        );
        at = found.index + found[0].length;
    }
    if (at < line.length) {
        pieces.push({ kind: "plain", text: line.slice(at) });
    }
    return pieces;
}

/**
 * The blocks of a correction, which is Markdown made by the exercise that
 * corrected the text: headings, a numbered list of the mistakes, and
 * paragraphs whose lines are kept as they were written.
 */
export function blocksOf(markdown: string): Block[] {
    const blocks: Block[] = [];
    let paragraph: Inline[][] | null = null;
    for (const line of markdown.split("\n")) {
        const heading = /^(#{1,3}) (.*)$/.exec(line);
        const item = /^(\d+)\. (.*)$/.exec(line);
        if (heading || item || !line.trim()) {
            paragraph = null;
        }
        if (heading) {
            blocks.push({ kind: "heading", level: heading[1].length, inline: inlineOf(heading[2]) });
        } else if (item) {
            blocks.push({ kind: "item", number: Number(item[1]), inline: inlineOf(item[2]) });
        } else if (line.trim()) {
            if (paragraph === null) {
                paragraph = [];
                blocks.push({ kind: "paragraph", lines: paragraph });
            }
            paragraph.push(inlineOf(line));
        }
    }
    return blocks;
}

/** What a request about a page answered: the text, or why it failed. */
async function pageAnswer(response: Response, otherwise: Message): Promise<Text> {
    if (!response.ok) {
        const reply = await response.json().catch(() => ({}));
        throw new Error(typeof reply.error === "string" ? reply.error : t(otherwise));
    }
    return response.json();
}

function pagePath(id: string, pageId?: string): string {
    return `/texts/${encodeURIComponent(id)}/pages${pageId ? `/${encodeURIComponent(pageId)}` : ""}`;
}

/** Adds a blank page after the pages of a text written by hand. Returns the text. */
export async function addPage(id: string, position: number): Promise<Text> {
    return pageAnswer(
        await checkerFetch(pagePath(id), { method: "POST", body: JSON.stringify({ position }) }),
        "The page could not be added.",
    );
}

// each stroke as JSON, made once, as a stroke is not changed once it is written
const strokeJson = new WeakMap<Stroke, string>();

/**
 * The ink of a page as JSON, its strokes made into it once each, so that
 * keeping a page full of them does not hold up the pen.
 */
export function inkJson(ink: Stroke[]): string {
    const strokes = ink.map((stroke) => {
        let json = strokeJson.get(stroke);
        if (json === undefined) {
            json = JSON.stringify(stroke);
            strokeJson.set(stroke, json);
        }
        return json;
    });
    return `{"ink":[${strokes.join(",")}]}`;
}

/** Keeps the ink of a page as it is now. */
export async function saveInk(id: string, pageId: string, ink: Stroke[]): Promise<void> {
    const response = await checkerFetch(pagePath(id, pageId), { method: "PUT", body: inkJson(ink) });
    if (!response.ok) {
        const reply = await response.json().catch(() => ({}));
        throw new Error(typeof reply.error === "string" ? reply.error : t("The page could not be kept."));
    }
}

/**
 * Has the server read a page with the key of Google Cloud Vision. Returns the
 * text, which then says what its pages were read to say.
 */
export async function readPage(id: string, pageId: string, visionKey: string): Promise<Text> {
    return pageAnswer(
        await checkerFetch(`${pagePath(id, pageId)}/read`, {
            method: "POST",
            headers: visionKey ? { "X-Vision-Key": visionKey } : {},
        }),
        "The page could not be read.",
    );
}

/** Removes a page of a text written by hand. Returns the text, which says what the pages left say. */
export async function deletePage(id: string, pageId: string): Promise<Text> {
    return pageAnswer(await checkerFetch(pagePath(id, pageId), { method: "DELETE" }), "The page could not be removed.");
}
