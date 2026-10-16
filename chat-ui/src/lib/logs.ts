// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { checkerFetch } from "./session";

/**
 * The attribute that a panel puts on what can be selected in it to say
 * where it is, as the JSON of a `Where`, so that what is done with a
 * selection is logged with it.
 */
export const WHERE_ATTRIBUTE = "data-where";

/** Where something was done, as it is logged. */
export type Where =
    | { kind: "book"; id: string; title: string; page: number }
    | { kind: "chat"; id: string }
    | { kind: "exercise"; session: string; exercise: string };

/** What the logs are of. */
export const LOG_KINDS = { exercise: "Exercise", translation: "Translation", question: "Question" } as const;
export type LogKind = keyof typeof LOG_KINDS;

/**
 * A short account of something the learner did, written for the models
 * that work out what the learner can do, as the server keeps it.
 */
export interface Log {
    id: number;
    kind: LogKind;
    language: string;
    /** What it is about, in a few words. */
    subject: string;
    content: string;
    /** In seconds since the epoch. */
    writtenAt: number;
    /** The session and the exercise, for the log of an exercise. */
    session: string | null;
    exercise: string | null;
    /** Where else it was done, with the id of the log of the translation for a question about one. */
    source: Partial<Where> & { translation?: number };
}

/** How many logs the server sends at a time. */
export const LOGS_AT_A_TIME = 100;

/** The logs, the latest first, from the one before `before` on if it is given. */
export async function fetchLogs(before?: number): Promise<Log[]> {
    const response = await checkerFetch(before === undefined ? "/logs" : `/logs?before=${before}`);
    if (!response.ok) {
        throw new Error(`checker server: ${response.status}`);
    }
    return (await response.json()).logs;
}

/** The `Where` an element says, if it says one that can be read. */
export function readWhere(value: string | null | undefined): Where | null {
    if (!value) {
        return null;
    }
    try {
        const where = JSON.parse(value);
        return where && typeof where === "object" && typeof where.kind === "string" ? where : null;
    } catch {
        return null;
    }
}

/** Whether `log` is of one of `kinds` and has every word of `query` in its subject or its content. */
export function matchesLog(log: Log, kinds: ReadonlySet<LogKind>, query: string): boolean {
    if (!kinds.has(log.kind)) {
        return false;
    }
    const text = `${log.subject} ${log.content}`.toLowerCase();
    return query.toLowerCase().split(/\s+/).every((word) => text.includes(word));
}

/** The logs by the day they were written, in the order they come, each day with its name. */
export function byDay(logs: Log[], locale?: string): { day: string; logs: Log[] }[] {
    const days: { day: string; logs: Log[] }[] = [];
    for (const log of logs) {
        const day = new Date(log.writtenAt * 1000).toLocaleDateString(locale, {
            weekday: "short",
            day: "numeric",
            month: "short",
            year: "numeric",
        });
        if (days.at(-1)?.day === day) {
            days.at(-1)!.logs.push(log);
        } else {
            days.push({ day, logs: [log] });
        }
    }
    return days;
}

/** Where a log says it was done, in a few words, such as "Der Hund, p. 12". */
export function describeSource(log: Log): string {
    const { source } = log;
    if (source.kind === "book") {
        return `${source.title || "a book"}${typeof source.page === "number" ? `, p. ${source.page + 1}` : ""}`;
    }
    if (source.kind === "chat") {
        return "a chat";
    }
    if (source.kind === "exercise" || log.kind === "exercise") {
        return "practice";
    }
    return "";
}
