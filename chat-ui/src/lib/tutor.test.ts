// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { doingNow, emptyTurn, type Offer, thinkingAbout, type TutorEvent, type TutorTurn, withEvent } from "./tutor";

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

test("what the tutor is thinking about is the last line it has reasoned", () => {
    expect(thinkingAbout("First the logs.\n\nThen the dative mistakes  \n")).toBe("Then the dative mistakes");
    expect(thinkingAbout("")).toBe("");
});
