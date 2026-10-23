// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import { type Message, t } from "./i18n";
import { checkerFetch } from "./session";

/** What became of a word that was to be taken into the vocabulary. */
export interface TakenWord {
    word: string;
    /** "known", "added", "form", "skipped", "rejected" or "failed". */
    status: string;
    reason: string;
    /** For a sentence that was read aloud: what OpenRouter knows the request by, to look its cost up with. */
    generation?: string;
    /** For what was asked about a translation: what one of its logs is about. */
    subject?: string;
}

/** Something the server does in the background, as it is at present. */
export interface BackgroundTask {
    id: string;
    /**
     * What kind of thing is done. "words" is taking the words of a selection
     * into the vocabulary, "speech" making the audio of sentences of a book,
     * "icon" making the icon of a topic, "embeddings" embedding the words
     * of the vocabulary, and "transform" making a transformed version of a book.
     */
    kind: string;
    /** What it is done to, in a few words. */
    title: string;
    /** How many steps there are to it, and how many of them are done. */
    total: number;
    done: number;
    state: "running" | "done" | "failed";
    /** Why it failed, if it did. */
    error: string;
    /** What became of each word, or of each sentence that was to be read, once it is done. */
    result: TakenWord[];
    /** The requests to the models it made. */
    usage: ProfileUsage[];
    /** How each of its steps is going, for a task that says: each part of a book that is transformed. */
    progress?: PartProgress[];
}

/** How the transforming of a part of a book is going. */
export interface PartProgress {
    /** What the part is called, such as the title of its story. */
    title: string;
    state: "waiting" | "thinking" | "writing" | "done";
    /** The tokens the model has reasoned and written so far. */
    reasoning: number;
    written: number;
    /** The tokens of the part as it was sent, which what is written is about as long as. */
    expected: number;
    /** The most tokens the model may reason in, if it reasons. */
    budget: number | null;
    /** How many answers the model has been asked for: more than one once an answer broke off, being too long. */
    round: number;
}

/** How much of a part is written, as a share of the tokens it was sent in: more than 1 once it is longer. */
export function writtenShare(part: PartProgress): number {
    return part.expected > 0 ? part.written / part.expected : 0;
}

/** How often the server is asked how the tasks are going while some are running, in milliseconds. */
export const TASKS_INTERVAL_MS = 1500;

/** The tasks of whoever is logged in, the newest first. */
export async function fetchTasks(): Promise<BackgroundTask[]> {
    const response = await checkerFetch("/tasks");
    if (!response.ok) {
        throw new Error(t("The server answered {status}.", { status: response.status }));
    }
    return (await response.json()).tasks;
}

/** The tasks with `task` among them as it is now, the newest first. */
export function withTask(tasks: BackgroundTask[], task: BackgroundTask): BackgroundTask[] {
    return [task, ...tasks.filter((each) => each.id !== task.id)];
}

/** What became of the words of a selection, in a few words: how many are new, and how many could not be taken. */
export function describeTaken(words: TakenWord[]): string {
    const count = (...statuses: string[]) => words.filter((word) => statuses.includes(word.status)).length;
    const parts = ([
        [count("added"), "{count} new"],
        [count("form"), "{count} new as a form of a word"],
        [count("known"), "{count} already there"],
        [count("skipped", "rejected"), "{count} not kept"],
        [count("failed"), "{count} failed"],
    ] as const).filter(([number]) => number !== 0).map(([number, what]) => t(what, { count: number }));
    return parts.length > 0 ? parts.join(", ") : t("No words were found.");
}

/** What a task is doing, or what came of it, in a line. */
export function describeTask(task: BackgroundTask): string {
    const speech = task.kind === "speech";
    if (task.state === "running") {
        const doing = ({
            speech: "Making the audio",
            icon: "Making the icon",
            embeddings: "Embedding the words",
            log: "Writing the log",
            questions: "Logging what was asked",
            transform: "Transforming the parts",
        } as Record<string, Message>)[task.kind] ?? "Looking into the words";
        return t("{doing}: {done} of {total}", { doing: t(doing), done: task.done, total: task.total });
    }
    if (task.state === "failed") {
        return t("Failed: {error}", { error: task.error });
    }
    if (task.kind === "icon") {
        return t("The icon is made.");
    }
    if (task.kind === "embeddings") {
        return t("The words are embedded.");
    }
    if (task.kind === "log") {
        return t("The log is written.");
    }
    if (task.kind === "transform") {
        return t("The version is made.");
    }
    if (task.kind === "questions") {
        return t("Logged: {what}.", { what: task.result.map((each) => each.subject).join(", ") || t("nothing") });
    }
    return speech ? describeRead(task.result) : describeTaken(task.result);
}

/** What became of the sentences that were to be read aloud, in a few words. */
export function describeRead(sentences: TakenWord[]): string {
    const count = (status: string) => sentences.filter((sentence) => sentence.status === status).length;
    const parts = ([
        [count("made"), "{count} read"],
        [count("stopped"), "{count} left unread"],
        [count("failed"), "{count} failed"],
    ] as const).filter(([number]) => number !== 0).map(([number, what]) => t(what, { count: number }));
    return parts.length > 0 ? t("Sentences: {parts}", { parts: parts.join(", ") }) : t("Nothing was read.");
}

/** What a task of each kind is called. */
export function taskName(task: BackgroundTask): string {
    const name = ({
        speech: "Read aloud",
        icon: "Topic icon",
        embeddings: "Embed vocabulary",
        log: "Exercise log",
        questions: "Questions log",
        transform: "Transform book",
    } as Record<string, Message>)[task.kind];
    return t(name ?? "Add to vocabulary");
}

/** The words of a task that are worth a mention: those that are new, and those that could not be taken. */
export function mentioned(task: BackgroundTask): TakenWord[] {
    if (task.kind === "icon" || task.kind === "embeddings" || task.kind === "questions" || task.kind === "transform") {
        return [];
    }
    const worth = task.kind === "speech" ? ["failed"] : ["added", "form", "failed"];
    return task.result.filter((word) => worth.includes(word.status));
}
