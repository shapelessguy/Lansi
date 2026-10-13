import { checkerFetch } from "./session";

// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/** A generated text, kept by the server for whoever is logged in, with its audio. */
export interface SavedText {
    id: string;
    /** In milliseconds since the epoch. */
    createdAt: number;
    title: string;
    /** Markdown, starting with the title as a heading. */
    text: string;
    /** What the user asked the text to be about. */
    topic: string;
    /** The model that wrote the text. */
    model: string;
    /** The language that was being learned when the text was written. */
    language?: string;
    /** The speech made from the text, if any. */
    audio: { model: string; voice: string; createdAt: number } | null;
}

export const textLengths = {
    short: { label: "Short", words: 80 },
    medium: { label: "Medium", words: 160 },
    long: { label: "Long", words: 320 },
} as const;

export type TextLength = keyof typeof textLengths;

const BASE = "/texts";

async function send(path: string, init?: RequestInit): Promise<Response> {
    let response: Response;
    try {
        response = await checkerFetch(BASE + path, init);
    } catch {
        throw new Error("The server cannot be reached. Is `just dev` running?");
    }
    if (!response.ok) {
        throw new Error(`The server answered ${response.status}.`);
    }
    return response;
}

/** Every saved text, newest first. */
export async function fetchTexts(): Promise<SavedText[]> {
    const texts: SavedText[] = await (await send("")).json();
    return texts.sort((a, b) => b.createdAt - a.createdAt);
}

export async function saveText(text: SavedText): Promise<void> {
    await send(`/${text.id}`, { method: "PUT", body: JSON.stringify(text, null, 2) });
}

export async function saveAudio(id: string, audio: Blob): Promise<void> {
    await send(`/${id}/audio`, { method: "PUT", headers: { "Content-Type": audio.type }, body: audio });
}

export async function fetchAudio(id: string): Promise<Blob> {
    return (await send(`/${id}/audio`)).blob();
}

export async function deleteText(id: string): Promise<void> {
    await send(`/${id}`, { method: "DELETE" });
}

/** What the model is asked for, after the instructions from the settings. */
export function textRequest(topic: string, length: TextLength): string {
    const about = topic.trim() ? `Write about: ${topic.trim()}` : "Choose a topic yourself.";
    return `${about}\nLength: about ${textLengths[length].words} words.`;
}

/** The text's heading if it starts with one, otherwise its first few words. */
export function textTitle(markdown: string): string {
    const firstLine = markdown.trim().split("\n")[0] ?? "";
    const heading = /^#+\s+(.*)$/.exec(firstLine);
    if (heading) {
        return plainText(heading[1]);
    }
    const words = plainText(firstLine).split(/\s+/).filter(Boolean);
    if (words.length === 0) {
        return "Untitled";
    }
    if (words.length <= 8) {
        return words.join(" ");
    }
    return `${words.slice(0, 8).join(" ").replace(/[,;:.!?]+$/, "")}…`;
}

/** Markdown with its markup removed, as it should be read aloud. */
export function plainText(markdown: string): string {
    return markdown
        .replace(/^#+\s+/gm, "")
        .replace(/^[ \t]*[-*+][ \t]+/gm, "")
        .replace(/^[ \t]*>[ \t]?/gm, "")
        .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
        .replace(/(\*\*|__|\*|_|`|~~)/g, "")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
}

/**
 * An id that sorts by date and reads well as a file name, such as
 * `2026-10-12-170501-der-film`.
 */
export function textId(createdAt: number, title: string): string {
    const date = new Date(createdAt);
    const pad = (value: number) => String(value).padStart(2, "0");
    const stamp = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}-`
        + `${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
    const slug = title
        // "ä" becomes "a" rather than a gap
        .normalize("NFKD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/[^A-Za-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "")
        .toLowerCase()
        .slice(0, 40)
        .replace(/-+$/, "");
    return slug ? `${stamp}-${slug}` : stamp;
}
