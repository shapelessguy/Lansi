// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import {
    doingNow,
    emptyTurn,
    keptMessages,
    keptTurn,
    type Offer,
    thinkingAbout,
    type TutorEvent,
    type TutorTurn,
    withEvent,
} from "./tutor";

const OFFER: Offer = {
    kind: "exercise",
    exercise: "cloze",
    title: "Fill the gaps",
    theory: false,
    lesson: "dative",
    lesson_title: "The dative",
    instances: 3,
    topics: [],
    options: { sentences: 5 },
};

function after(...events: TutorEvent[]): TutorTurn {
    return events.reduce(withEvent, emptyTurn());
}

test("a turn of the tutor is thinking until anything else is known", () => {
    expect(doingNow(emptyTurn())).toBe("Thinking");
    expect(doingNow(after({ type: "thinking", text: "Hm" }))).toBe("Thinking");
});

test("a turn says which tool is running while it runs, and writing once the answer comes", () => {
    const calling = after({ type: "tool", id: "1", name: "logs", doing: "Reading your logs" });
    const writing = withEvent(
        withEvent(calling, { type: "tool_done", id: "1", failed: false, shown: null }),
        { type: "text", text: "You" },
    );

    expect(doingNow(calling)).toBe("Reading your logs");
    expect(writing.steps).toEqual([{ id: "1", doing: "Reading your logs", status: "done" }]);
    expect(doingNow(writing)).toBe("Writing");
});

test("a turn keeps the exercises the tutor offered, and a tool that failed", () => {
    const turn = after(
        { type: "tool", id: "1", name: "exercise_cloze", doing: "Preparing" },
        { type: "tool_done", id: "1", failed: false, shown: OFFER },
        { type: "tool", id: "2", name: "logs", doing: "Reading" },
        { type: "tool_done", id: "2", failed: true, shown: null },
    );

    expect(turn.offers).toEqual([OFFER]);
    expect(turn.steps.map((step) => step.status)).toEqual(["done", "failed"]);
});

test("a turn is done once the last event comes, and says nothing of what it is doing", () => {
    const turn = after({ type: "text", text: "Hi." }, { type: "done", messages: [], usage: [] });

    expect(turn.busy).toBe(false);
    expect(doingNow(turn)).toBeNull();
});

test("what the tutor thinks about is nothing before it has reasoned", () => {
    expect(thinkingAbout("")).toBe("");
});

test("what the tutor thinks about is the latest heading of its steps, when it gives them", () => {
    const thinking = "**Looking at the logs**\n\nThe learner mixes up the cases. A **cloze** would";

    expect(thinkingAbout(thinking)).toBe("Looking at the logs");
    expect(thinkingAbout(`${thinking}\n\n## Picking the words\nSome`)).toBe("Picking the words");
});

test("what the tutor thinks about is nothing when its reasoning has no headings", () => {
    expect(thinkingAbout("The learner wants to translate. They are at B1. I should pick")).toBe("");
});

test("what the tutor thinks about is cut short at a word when it is long", () => {
    const long = `**${"The learner keeps confusing the dative and the accusative ".repeat(3).trim()}**`;

    const about = thinkingAbout(long);

    expect(about.length).toBeLessThanOrEqual(81);
    expect(about.endsWith("…")).toBe(true);
    expect(about).not.toMatch(/\s…$/);
});

test("a kept chat is told to the model again with the tools its answers called", () => {
    const called = [
        { role: "assistant" as const, content: null, tool_calls: [{ id: "call-1" }] },
        { role: "tool" as const, content: "[]", tool_call_id: "call-1" },
        { role: "assistant" as const, content: "Read the first lesson." },
    ];

    const told = keptMessages([
        { role: "user", content: "Hallo", writtenAt: 1 },
        { role: "assistant", content: "Read the first lesson.", writtenAt: 2, turn: { messages: called } },
        // one kept before turns were kept has only what it said
        { role: "assistant", content: "Old.", writtenAt: 3 },
    ]);

    expect(told).toEqual([{ role: "user", content: "Hallo" }, ...called, { role: "assistant", content: "Old." }]);
});

test("a kept answer is shown with its steps and the exercises it offered", () => {
    const turn = keptTurn("Here.", {
        steps: [{ id: "call-1", doing: "Looking at the lessons", status: "done" }],
        offers: [{ ...OFFER, session: "s1", status: "done" }],
    });

    expect(turn.steps.map((step) => step.doing)).toEqual(["Looking at the lessons"]);
    expect(turn.offers.map((offer) => offer.exercise)).toEqual(["cloze"]);
    expect(turn.busy).toBe(false);
    expect(keptTurn("Old.")).toEqual({ thinking: "", steps: [], offers: [], exams: [], text: "Old.", busy: false });
});
