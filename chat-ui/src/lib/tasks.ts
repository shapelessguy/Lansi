// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import { checkerFetch } from "./session";

/** What became of a word that was to be taken into the vocabulary. */
export interface TakenWord {
    word: string;
    /** "known", "added", "form", "skipped", "rejected" or "failed". */
    status: string;
    reason: string;
    /** For a sentence that was read aloud: what OpenRouter knows the request by, to look its cost up with. */
    generation?: string;
}

/** Something the server does in the background, as it is at present. */
export interface BackgroundTask {
    id: string;
    /**
     * What kind of thing is done. "words" is taking the words of a selection
     * into the vocabulary, and "speech" making the audio of sentences of a book.
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
}

/** How often the server is asked how the tasks are going while some are running, in milliseconds. */
export const TASKS_INTERVAL_MS = 1500;

/** The tasks of whoever is logged in, the newest first. */
export async function fetchTasks(): Promise<BackgroundTask[]> {
    const response = await checkerFetch("/tasks");
    if (!response.ok) {
        throw new Error(`The server answered ${response.status}.`);
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
    const parts = [
        [count("added"), "new"],
        [count("form"), "new as a form of a word"],
        [count("known"), "already there"],
        [count("skipped", "rejected"), "not kept"],
        [count("failed"), "failed"],
    ].filter(([number]) => number !== 0).map(([number, what]) => `${number} ${what}`);
    return parts.length > 0 ? parts.join(", ") : "No words were found.";
}

/** What a task is doing, or what came of it, in a line. */
export function describeTask(task: BackgroundTask): string {
    const speech = task.kind === "speech";
    if (task.state === "running") {
        return `${speech ? "Making the audio" : "Looking into the words"}: ${task.done} of ${task.total}`;
    }
    if (task.state === "failed") {
        return `Failed: ${task.error}`;
    }
    return speech ? describeRead(task.result) : describeTaken(task.result);
}

/** What became of the sentences that were to be read aloud, in a few words. */
export function describeRead(sentences: TakenWord[]): string {
    const count = (status: string) => sentences.filter((sentence) => sentence.status === status).length;
    const parts = [
        [count("made"), "read"],
        [count("stopped"), "left unread"],
        [count("failed"), "failed"],
    ].filter(([number]) => number !== 0).map(([number, what]) => `${number} ${what}`);
    return parts.length > 0 ? `Sentences: ${parts.join(", ")}` : "Nothing was read.";
}

/** What a task of each kind is called. */
export function taskName(task: BackgroundTask): string {
    return task.kind === "speech" ? "Read aloud" : "Add to vocabulary";
}

/** The words of a task that are worth a mention: those that are new, and those that could not be taken. */
export function mentioned(task: BackgroundTask): TakenWord[] {
    const worth = task.kind === "speech" ? ["failed"] : ["added", "form", "failed"];
    return task.result.filter((word) => worth.includes(word.status));
}
