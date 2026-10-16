// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, it } from "vitest";

import { byDay, describeSource, type Log, type LogKind, matchesLog, readWhere } from "./logs";

function log(more: Partial<Log>): Log {
    return {
        id: 1,
        kind: "translation",
        language: "German",
        subject: "gerade",
        content: "Asked for \"gerade\" to be translated.",
        writtenAt: new Date(2026, 9, 16, 10).getTime() / 1000,
        session: null,
        exercise: null,
        source: {},
        ...more,
    };
}

const ALL = new Set<LogKind>(["exercise", "translation", "question"]);

describe("readWhere", () => {
    it("reads where something was done from what an element says", () => {
        expect(readWhere("{\"kind\":\"chat\",\"id\":\"c1\"}")).toEqual({ kind: "chat", id: "c1" });
    });

    it("is null where nothing, or nothing it can read, is said", () => {
        expect(readWhere(null)).toBeNull();
        expect(readWhere("a book")).toBeNull();
        expect(readWhere("{\"id\":\"c1\"}")).toBeNull();
    });
});

describe("matchesLog", () => {
    it("finds a log by every word of the query in its subject or content, whatever the capitals", () => {
        expect(matchesLog(log({}), ALL, "GERADE translated")).toBe(true);
        expect(matchesLog(log({}), ALL, "gerade dog")).toBe(false);
        expect(matchesLog(log({}), ALL, "")).toBe(true);
    });

    it("leaves out a log of a kind that is not shown", () => {
        expect(matchesLog(log({}), new Set<LogKind>(["exercise"]), "")).toBe(false);
    });
});

describe("byDay", () => {
    it("puts the logs of one day together, in the order they come", () => {
        const morning = log({ id: 3 });
        const evening = log({ id: 2, writtenAt: morning.writtenAt + 8 * 3600 });
        const before = log({ id: 1, writtenAt: morning.writtenAt - 24 * 3600 });

        const days = byDay([evening, morning, before], "en-GB");

        expect(days.map((day) => day.logs.map((each) => each.id))).toEqual([[2, 3], [1]]);
    });
});

describe("describeSource", () => {
    it("names the book and the page, counted from one, a log was written on", () => {
        expect(describeSource(log({ source: { kind: "book", id: "b1", title: "Der Hund", page: 11 } }))).toBe(
            "Der Hund, p. 12",
        );
    });

    it("names a chat and practice, and nothing where nothing is known", () => {
        expect(describeSource(log({ source: { kind: "chat", id: "c1" } }))).toBe("a chat");
        expect(describeSource(log({ kind: "exercise", session: "s1", exercise: "cloze" }))).toBe("practice");
        expect(describeSource(log({}))).toBe("");
    });
});
