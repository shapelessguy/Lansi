// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import { type ModelChoice, modelRequest } from "./models";
import type { OptionValue } from "./practice";
import { checkerFetch } from "./session";
import type { BackgroundTask } from "./tasks";
import { describeError } from "./translate";

/**
 * A message of the chat with the tutor as the model was told it: what the
 * learner wrote, what the tutor answered with the tools it called, and what
 * they came to. The server answers the chat as a whole, so it is sent back
 * as it came.
 */
export interface TutorMessage {
    role: "system" | "user" | "assistant" | "tool";
    content: string | null;
    [more: string]: unknown;
}

/** An exercise the tutor offered, ready to be started as practice. */
export interface Offer {
    kind: "exercise";
    exercise: string;
    title: string;
    /** Whether it teaches the lesson rather than asks. */
    theory: boolean;
    /** Whether it practises a lesson, as one that corrects a text does not. */
    practises_lesson?: boolean;
    /** The lesson by its id, empty to review the lessons practised last. */
    lesson: string;
    lesson_title: string;
    instances: number;
    /** The topics by their ids, and by their titles. */
    topics: string[];
    topic_titles?: string[];
    options: Record<string, OptionValue>;
    /** What the options that are choices are set to, as they are called, such as the title of a text. */
    labels?: Record<string, string>;
    /** What the tutor wants it to aim at, and the words it is to be made of, if any. */
    focus?: string;
    words?: string[];
}

/** A mock exam the tutor offered, ready to be started in the tab of evaluations. */
export interface EvaluationOffer {
    kind: "evaluation";
    level: string;
    exam: string;
    /** How long it is to take, in half hours. */
    length: number;
    timed: boolean;
}

/** A request to the model, as the server sent it. */
export interface ModelRequest {
    model: string;
    messages: TutorMessage[];
    tools?: { type: "function"; function: { name: string; description: string; parameters: unknown } }[];
    [more: string]: unknown;
}

/** What a request to the model came to, as the model reported it. */
export interface ModelReply {
    message?: TutorMessage;
    /** All that was reasoned. */
    reasoning?: string;
    /** The usage, as OpenRouter reports it, with `prompt_tokens_details` and `completion_tokens_details`. */
    usage?: Record<string, unknown> | null;
    /** The model and the provider that answered, and the id of the generation. */
    model?: string | null;
    provider?: string | null;
    generation?: string | null;
    finish_reason?: string | null;
    /** How long the first piece of the answer and the whole of it took, in milliseconds. */
    first_ms: number | null;
    total_ms: number | null;
    error?: string;
}

/** What the server tells of the tutor as it answers, a line at a time. */
export type TutorEvent =
    | { type: "thinking"; text: string }
    | { type: "text"; text: string }
    | { type: "tool"; id: string; name: string; doing: string; arguments?: string }
    | {
        type: "tool_done";
        id: string;
        failed: boolean;
        shown: Offer | EvaluationOffer | null;
        content?: string;
        ms?: number;
    }
    | { type: "call"; id: number; at: number; request: ModelRequest }
    | ({ type: "call_done"; id: number } & ModelReply)
    | { type: "done"; messages: TutorMessage[]; usage: ProfileUsage[] }
    | { type: "error"; error: string };

/** A tool the tutor called, as the chat shows it. */
export interface Step {
    id: string;
    doing: string;
    status: "running" | "done" | "failed";
}

/** A turn of the tutor as the chat shows it, which grows as its events come. */
export interface TutorTurn {
    /** What it reasoned, for those who want to see it. */
    thinking: string;
    steps: Step[];
    offers: Offer[];
    /** The mock exams it offered. */
    exams: EvaluationOffer[];
    text: string;
    /** Whether it is still coming. */
    busy: boolean;
}

/** Who asks the tutor, and who is asked. */
export interface TutorAsking {
    apiKey: string;
    model: ModelChoice;
    language: string;
    into: string;
    level: string;
}

/** An exercise the tutor offered that was done, which the tutor is told how it went, once its log is written. */
export interface Practised {
    session: string;
    exercise: string;
    /** The tasks that write its log. */
    tasks: string[];
}

/** What is counted the usage of the tutor under. */
export const USAGE_ID = "tutor";

export function emptyTurn(): TutorTurn {
    return { thinking: "", steps: [], offers: [], exams: [], text: "", busy: true };
}

/** `turn` with `event` taken into it. */
export function withEvent(turn: TutorTurn, event: TutorEvent): TutorTurn {
    switch (event.type) {
        case "thinking":
            return { ...turn, thinking: turn.thinking + event.text };
        case "text":
            return { ...turn, text: turn.text + event.text };
        case "tool":
            return { ...turn, steps: [...turn.steps, { id: event.id, doing: event.doing, status: "running" }] };
        case "tool_done":
            return {
                ...turn,
                steps: turn.steps.map((step) =>
                    step.id === event.id ? { ...step, status: event.failed ? "failed" : "done" } : step
                ),
                offers: event.shown?.kind === "exercise" ? [...turn.offers, event.shown] : turn.offers,
                exams: event.shown?.kind === "evaluation" ? [...turn.exams, event.shown] : turn.exams,
            };
        case "done":
        case "error":
            return { ...turn, busy: false };
        default:
            return turn;
    }
}

/** What the tutor is doing at present, said in a few words, or null once it is done. */
export function doingNow(turn: TutorTurn): string | null {
    if (!turn.busy) {
        return null;
    }
    const running = [...turn.steps].reverse().find((step) => step.status === "running");
    if (running) {
        return running.doing;
    }
    return turn.text ? "Writing" : "Thinking";
}

/** The last line of what was reasoned, as it is being reasoned, to show what it is about. */
export function thinkingAbout(thinking: string): string {
    const lines = thinking.trim().split("\n").map((line) => line.trim()).filter(Boolean);
    return lines.at(-1) ?? "";
}

/**
 * Has the tutor answer the last of `messages`, or tells it how an exercise
 * it offered went, if it was `practised`, keeping what was said in the
 * `chat` with that id, if one is given, and telling `onEvent` each event as
 * it comes. Resolves with the last event, which is what was added to the
 * chat, or rejects with why it could not be answered.
 */
export async function askTutor(
    messages: TutorMessage[],
    asking: TutorAsking,
    onEvent: (event: TutorEvent) => void,
    signal?: AbortSignal,
    practised?: Practised,
    chat?: string,
): Promise<Extract<TutorEvent, { type: "done" }>> {
    let response: Response;
    try {
        response = await checkerFetch("/tutor/chat", {
            method: "POST",
            headers: asking.apiKey ? { "X-OpenRouter-Key": asking.apiKey } : {},
            body: JSON.stringify({
                messages,
                model: modelRequest(asking.model),
                language: asking.language,
                into: asking.into,
                level: asking.level,
                ...(practised ? { practised } : {}),
                // where what the learner wrote and what the tutor answered are kept
                ...(chat ? { chat } : {}),
            }),
            signal,
        });
    } catch (error) {
        throw signal?.aborted ? error : new Error("The server cannot be reached.");
    }
    if (!response.ok || !response.body) {
        const reply = await response.json().catch(() => ({}));
        throw new Error(describeError(reply.error, response.status));
    }
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let pending = "";
    for (;;) {
        const { done, value } = await reader.read();
        pending += value ?? "";
        const lines = pending.split("\n");
        pending = done ? "" : lines.pop() ?? "";
        for (const line of lines.filter((each) => each.trim())) {
            const event = JSON.parse(line) as TutorEvent;
            if (event.type === "error") {
                throw new Error(event.error);
            }
            onEvent(event);
            if (event.type === "done") {
                return event;
            }
        }
        if (done) {
            throw new Error("The tutor's answer broke off.");
        }
    }
}

/** A chat with the tutor as it is kept: what the learner wrote and what the tutor answered, and nothing else. */
export interface KeptTutorChat {
    id: string;
    language: string;
    startedAt: number;
    updatedAt: number;
    /** When it was closed, after which nothing more is said in it; null while it is open. */
    closedAt: number | null;
    messages: { role: "user" | "assistant"; content: string; writtenAt: number }[];
}

/** A chat with the tutor as it is listed, with the first thing the learner wrote. */
export interface ListedTutorChat {
    id: string;
    language: string;
    startedAt: number;
    updatedAt: number;
    closedAt: number | null;
    first: string;
    count: number;
}

/** The chats with the tutor, the latest first. */
export async function fetchTutorChats(): Promise<ListedTutorChat[]> {
    const response = await checkerFetch("/tutor/chats");
    if (!response.ok) {
        throw new Error("The chats with the tutor could not be listed.");
    }
    return (await response.json()).chats;
}

export async function fetchTutorChat(id: string): Promise<KeptTutorChat> {
    const response = await checkerFetch(`/tutor/chats/${encodeURIComponent(id)}`);
    if (!response.ok) {
        throw new Error("The chat with the tutor could not be found.");
    }
    return response.json();
}

export async function deleteTutorChat(id: string): Promise<void> {
    await checkerFetch(`/tutor/chats/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** A turn of the tutor that is over, as a kept chat has it: only what it answered. */
export function keptTurn(text: string): TutorTurn {
    return { thinking: "", steps: [], offers: [], exams: [], text, busy: false };
}

/**
 * Closes a chat with the tutor, after which nothing more is said in it, and
 * has the model of `asking` decide in the background what the tutor is to
 * remember of it. Resolves with the task that does it, if one was started.
 */
export async function closeTutorChat(id: string, asking: TutorAsking): Promise<BackgroundTask[]> {
    const response = await checkerFetch(`/tutor/chats/${encodeURIComponent(id)}/close`, {
        method: "POST",
        headers: asking.apiKey ? { "X-OpenRouter-Key": asking.apiKey } : {},
        body: JSON.stringify({ model: modelRequest(asking.model) }),
    });
    if (!response.ok) {
        return [];
    }
    return (await response.json()).tasks ?? [];
}

/** Something the tutor remembers of the learner from one chat to the next. */
export interface Memory {
    id: number;
    content: string;
    /** In seconds since the epoch. */
    createdAt: number;
    /** The chat it was made of, if any. */
    chat: string | null;
    removedAt: number | null;
    removedWhy: string;
    removedBy: "tutor" | "learner" | "";
}

/** The memories the tutor has, the oldest first, and those that were removed. */
export async function fetchMemories(): Promise<{ memories: Memory[]; removed: Memory[] }> {
    const response = await checkerFetch("/tutor/memories");
    if (!response.ok) {
        throw new Error("The memories of the tutor could not be listed.");
    }
    return response.json();
}

/** Has the tutor forget a memory, as the learner wants. */
export async function deleteMemory(id: number): Promise<void> {
    await checkerFetch(`/tutor/memories/${id}`, { method: "DELETE" });
}
