// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { t } from "./i18n";
import { type ModelChoice, modelRequest } from "./models";
import { checkerFetch } from "./session";
import { pcmToWav } from "./speech";
import type { BackgroundTask } from "./tasks";
import { describeError } from "./translate";

/** What is selected of a book: from a place in the text of one paragraph to a place in that of another, or of the same. */
export interface BookSelection {
    startBlock: number;
    start: number;
    endBlock: number;
    end: number;
}

/** A sentence of a book that is read aloud. */
export interface SpokenSentence {
    /** The place of its paragraph and its own place in it, such as "12.3". Its audio is kept under it. */
    id: string;
    /** The place of its paragraph among the paragraphs of the book. */
    block: number;
    /** Where it is in the text of its paragraph. */
    start: number;
    end: number;
    text: string;
    /** Whether its audio was kept already when it was asked for. */
    ready: boolean;
}

/** The sentences to listen to, and what the server does to make the audio that is missing. */
export interface Reading {
    sentences: SpokenSentence[];
    /** The task that makes the missing audio, with what the reading goes by. There is none if nothing is missing. */
    task: (BackgroundTask & { reading: string }) | null;
}

/** Who reads, and how. */
export interface Voice {
    apiKey: string;
    model: ModelChoice;
    voice: string;
    /** How to read, such as "slowly and clearly". Not spoken. */
    instructions: string;
}

/** How many sentences from the one that is listened to have their audio asked for ahead of time. */
export const AHEAD = 2;
/** How often the audio of a sentence is asked for again while it is still being made. */
const TRIES = 6;
/**
 * How long, in milliseconds, an answer with the audio of a sentence is
 * waited for: the server waits up to 50 seconds for audio that is being
 * made, and a connection that was lost, as when a phone goes from Wi-Fi to
 * mobile data, may never answer at all.
 */
const AUDIO_WAIT_MS = 65_000;

/** What is thrown when the server could not be reached, as when the connection is lost or changes: it is asked again. */
export class Unreachable extends Error {}

/** The attribute each paragraph of a book that is laid out has, with its place among all of them. */
export const BLOCK_ATTRIBUTE = "data-block";

/** The paragraphs of a book laid out in `root`, in order, as only some parts of a book are laid out at once. */
export function laidBlocks(root: Element): HTMLElement[] {
    return [...root.querySelectorAll<HTMLElement>(`[${BLOCK_ATTRIBUTE}]`)];
}

/** The place of a paragraph of a book that is laid out, among all of them. */
export function placeOf(block: Element): number {
    return Number(block.getAttribute(BLOCK_ATTRIBUTE));
}

/** The paragraph of a book, by its place among all of them, in `root`, if it is laid out. */
export function bookBlock(root: Element, place: number): HTMLElement | undefined {
    return root.querySelector<HTMLElement>(`[${BLOCK_ATTRIBUTE}="${place}"]`) ?? undefined;
}

/** The paragraph of a book that a place in it is in, by its place among the paragraphs, and how far into its text. */
function placeIn(root: Element, node: Node, offset: number): { block: number; at: number } | null {
    const element = node instanceof Element ? node : node.parentElement;
    const block = element?.closest(`[${BLOCK_ATTRIBUTE}]`);
    if (!block || !root.contains(block)) {
        // a place between two paragraphs is the start of the second
        const after = node instanceof Element && root.contains(node) ? node.childNodes[offset] : undefined;
        const next = after instanceof Element
            ? after.matches(`[${BLOCK_ATTRIBUTE}]`) ? after : after.querySelector(`[${BLOCK_ATTRIBUTE}]`)
            : null;
        return next ? { block: placeOf(next), at: 0 } : null;
    }
    const before = document.createRange();
    before.selectNodeContents(block);
    before.setEnd(node, offset);
    return { block: placeOf(block), at: before.toString().length };
}

/** What `range` selects of the book whose paragraphs are the children of `root`. */
export function bookSelection(range: Range, root: Element): BookSelection | null {
    const from = placeIn(root, range.startContainer, range.startOffset);
    const to = placeIn(root, range.endContainer, range.endOffset);
    if (!from) {
        return null;
    }
    // a selection that runs out of the book ends with its last paragraph
    const blocks = laidBlocks(root);
    const end = to ?? { block: placeOf(blocks[blocks.length - 1]), at: Number.MAX_SAFE_INTEGER };
    return { startBlock: from.block, start: from.at, endBlock: end.block, end: end.at };
}

/** The stretch of the page that a sentence takes up in the paragraph `block` is shown as, if it can be found. */
export function rangeOf(block: Element, sentence: Pick<SpokenSentence, "start" | "end">): Range | null {
    const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
    const range = document.createRange();
    let seen = 0;
    let started = false;
    for (let node = walker.nextNode() as Text | null; node; node = walker.nextNode() as Text | null) {
        const length = node.data.length;
        if (!started && sentence.start < seen + length) {
            range.setStart(node, sentence.start - seen);
            started = true;
        }
        if (started && sentence.end <= seen + length) {
            range.setEnd(node, sentence.end - seen);
            return range;
        }
        seen += length;
    }
    return null;
}

/** The sentence to go to from the one at `index`, `step` further on, among `count`. */
export function stepped(index: number, step: number, count: number): number {
    return Math.max(0, Math.min(count - 1, index + step));
}

/** The sentences whose audio is to be asked for while the one at `index` is listened to: that one and the next few. */
export function wanted(index: number, count: number): number[] {
    return Array.from({ length: AHEAD + 1 }, (_, ahead) => index + ahead).filter((each) => each < count);
}

/** A place in the text of a book: the paragraph, and the character in it. */
export interface BookPlace {
    block: number;
    offset: number;
}

/** The first of the sentences, which are in the order of the book, that goes on past a place in it, or the first. */
export function startingAt(sentences: Pick<SpokenSentence, "block" | "end">[], from: BookPlace): number {
    const found = sentences.findIndex((each) =>
        each.block > from.block || (each.block === from.block && each.end > from.offset)
    );
    return Math.max(0, found);
}

/** What is to be read aloud: where the server is asked for it, and what it is asked. */
export interface SpeechSource {
    /** The path of the book or the chat on the server, such as `/books/ID`. */
    base: string;
    /** What of it is to be read. */
    wanted: object;
    /** The book, if it is one, so that the sentence that is heard can be marked in it. */
    bookId: string | null;
    /** What on the page the player is shown beside, as a selector, if it is anything: the button of a reply in the chat. */
    beside: string | null;
    /** The slot in the bar above what is read that the player is shown in, as a selector, if it has one. */
    dock: string | null;
    /** Where in a book the reading starts, if not at its first sentence. */
    from?: BookPlace;
}

/** The slot the player is shown in, in the bar of the book reader or of practice. */
export function dockOf(place: "book" | "practice" | "evaluation"): string {
    return `[data-speech-dock="${place}"]`;
}

/** What was selected of a book, as something to read aloud, from its first sentence or from the one at `from`. */
export function bookSource(bookId: string, selection: BookSelection, from?: BookPlace): SpeechSource {
    return {
        base: `/books/${bookId}`,
        wanted: {
            start_block: selection.startBlock,
            start: selection.start,
            end_block: selection.endBlock,
            end: selection.end,
        },
        bookId,
        beside: null,
        dock: dockOf("book"),
        from,
    };
}

/**
 * A text of an exercise of a session, which the exercise numbers `number`,
 * as something to read aloud, with the player in the bar of practice or of
 * an evaluation. Its audio is kept under the session and the exercise
 * together.
 */
export function exerciseSource(
    sessionId: string,
    exercise: string,
    number: number,
    text: string,
    place: "practice" | "evaluation" = "practice",
): SpeechSource {
    return {
        base: `/sessions/${sessionId}-${exercise}`,
        wanted: { message: number, text },
        bookId: null,
        beside: null,
        dock: dockOf(place),
    };
}

/** A message of a chat, which is the one at `place` among its messages, as something to read aloud. */
export function messageSource(chatId: string, place: number, text: string): SpeechSource {
    return {
        base: `/chats/${chatId}`,
        wanted: { message: place, text },
        bookId: null,
        beside: `[data-speak="${speakMark(chatId, place)}"]`,
        dock: null,
    };
}

/** What the button that has a message of a chat read aloud is told from the others by. */
export function speakMark(chatId: string, place: number): string {
    return `${chatId}:${place}`;
}

/** Where the player is put when it is shown beside something, from the left and the top of the window. */
export interface Spot {
    left: number;
    top: number;
}

/** The space kept between the player and what it is beside, and the edge of the window, in pixels. */
const SPACE = 8;

/**
 * Where to put a player of that size for something that takes up `rect` of
 * the window: to its left and level with it, or, where there is no room to
 * the left, above it. `edge` is how far to the left the player may reach,
 * which is where what the thing is in starts, so that the player does not
 * lie over what is beside that.
 */
export function spotBeside(
    rect: { left: number; top: number; bottom: number },
    size: { width: number; height: number },
    edge = 0,
): Spot {
    const left = rect.left - SPACE - size.width;
    if (left >= edge + SPACE) {
        return { left, top: (rect.top + rect.bottom - size.height) / 2 };
    }
    return { left: Math.max(edge + SPACE, rect.left), top: rect.top - SPACE - size.height };
}

/** What a reading is refused with until the listener agrees to have the audio of so many sentences made. */
export class ManyToMake extends Error {
    constructor(readonly toMake: number) {
        super(`the audio of ${toMake} sentences is to be made`);
    }
}

/**
 * Has the sentences of something read aloud. The audio that is not kept
 * yet is made by the server in the background. Throws ManyToMake if there
 * is more of it to make than the server makes without asking, unless the
 * listener `agreed` to it.
 */
export async function startReading(
    source: SpeechSource,
    voice: Voice,
    signal?: AbortSignal,
    agreed = false,
): Promise<Reading> {
    const response = await checkerFetch(`${source.base}/speech`, {
        method: "POST",
        headers: voice.apiKey ? { "X-OpenRouter-Key": voice.apiKey } : {},
        body: JSON.stringify({
            ...source.wanted,
            model: modelRequest(voice.model),
            voice: voice.voice,
            instructions: voice.instructions,
            agreed,
        }),
        signal,
    });
    const reply = await response.json().catch(() => ({}));
    if (response.status === 409 && typeof reply.toMake === "number") {
        throw new ManyToMake(reply.toMake);
    }
    if (!response.ok) {
        throw new Error(describeError(reply.error, response.status));
    }
    return reply;
}

/**
 * The audio of a sentence of the book or the chat at `base`. One that is still being made is waited
 * for. Throws if there is none in the end, with the reason.
 */
export async function fetchSentenceAudio(base: string, sentenceId: string, signal?: AbortSignal): Promise<Blob> {
    let reason = "";
    for (let attempt = 0; attempt < TRIES; attempt++) {
        let response: Response;
        try {
            const timeout = AbortSignal.timeout(AUDIO_WAIT_MS);
            response = await checkerFetch(`${base}/speech/${sentenceId}`, {
                signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
            });
            if (response.ok) {
                return await response.blob();
            }
        } catch (caught) {
            if (signal?.aborted) {
                throw caught;
            }
            throw new Unreachable(caught instanceof Error ? caught.message : String(caught));
        }
        reason = (await response.json().catch(() => ({}))).error
            ?? t("The server answered {status}.", { status: response.status });
        // the server stops waiting after a while, and is then asked again
        if (reason !== "the audio is not made yet") {
            break;
        }
    }
    throw new Error(reason);
}

/** Tells the server which sentence of a reading is listened to, so that the audio from there on is made next. */
export function listenAt(base: string, reading: string, at: number): void {
    checkerFetch(`${base}/speech/${reading}`, { method: "PUT", body: JSON.stringify({ at }) })
        .catch(() => undefined);
}

/** Has the audio of a reading that is not being made yet left unmade. */
export function stopReading(base: string, reading: string): void {
    checkerFetch(`${base}/speech/${reading}`, { method: "DELETE", keepalive: true }).catch(() => undefined);
}

/** How fast the audio can be played, as so many times the pace it was read at. */
export const SPEEDS = [0.5, 0.6, 0.7, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 2] as const;
const SPEED_KEY = "chat-ui.speech-speed";

/** A stored speed if it is one of those there are, and else the pace the audio was read at. */
export function normalizeSpeed(stored: unknown): number {
    return SPEEDS.find((speed) => speed === stored) ?? 1;
}

/** The speed that was listened at last in this browser. */
export function loadSpeed(): number {
    try {
        return normalizeSpeed(JSON.parse(localStorage.getItem(SPEED_KEY) ?? "1"));
    } catch {
        return 1;
    }
}

export function saveSpeed(speed: number): void {
    try {
        localStorage.setItem(SPEED_KEY, JSON.stringify(speed));
    } catch {
        // without storage, the speed lasts until the page is closed
    }
}

/** A tenth of a second of silence, as a file, once it has been asked for. */
let silence: string | null = null;
let player: HTMLAudioElement | null = null;

/**
 * What plays everything that is read aloud. It is one for the whole page: a
 * browser lets a page play sound by itself only through a player that
 * something the user did has started before.
 */
export function audioPlayer(): HTMLAudioElement {
    player ??= new Audio();
    return player;
}

/**
 * Has the player allowed to play by itself later on. This is to be called
 * while a click or a key is being handled, before audio that arrives only
 * after a while, such as that of a reply that is still to be written.
 */
export function allowPlaying(): void {
    const audio = audioPlayer();
    // what is playing is left alone
    if (audio.paused) {
        silence ??= URL.createObjectURL(pcmToWav(new ArrayBuffer(4800), 24_000));
        audio.src = silence;
        audio.play().catch(() => undefined);
    }
}
