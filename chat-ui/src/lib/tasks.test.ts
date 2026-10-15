// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { type BackgroundTask, describeTaken, describeTask, mentioned, taskName, withTask } from "./tasks";

function task(change: Partial<BackgroundTask> = {}): BackgroundTask {
    return {
        id: "a",
        kind: "words",
        title: "Der Hund",
        total: 2,
        done: 1,
        state: "running",
        error: "",
        result: [],
        usage: [],
        ...change,
    };
}

/** Words that each had this happen to them. */
function taken(...statuses: string[]) {
    return statuses.map((status) => ({ word: status, status, reason: "" }));
}

test("what became of the words of a selection is counted by what happened to them", () => {
    const words = taken("added", "added", "form", "known", "skipped", "rejected", "failed");

    expect(describeTaken(words)).toBe("2 new, 1 new as a form of a word, 1 already there, 2 not kept, 1 failed");
    expect(describeTaken(taken("known"))).toBe("1 already there");
    expect(describeTaken([])).toBe("No words were found.");
});

test("a task is described by how far it is, and in the end by what came of it", () => {
    expect(describeTask(task())).toBe("Looking into the words: 1 of 2");
    expect(describeTask(task({ state: "done", result: taken("added") }))).toBe("1 new");
    expect(describeTask(task({ state: "failed", error: "no key" }))).toBe("Failed: no key");
});

test("the words of a task that are mentioned are the new ones and those that failed", () => {
    const done = task({ state: "done", result: taken("added", "known", "form", "skipped", "failed") });

    expect(mentioned(done).map((word) => word.status)).toEqual(["added", "form", "failed"]);
});

test("a task that was just started is put first, and one that is known is replaced", () => {
    const tasks = [task({ id: "a" }), task({ id: "b" })];

    expect(withTask(tasks, task({ id: "c" })).map((each) => each.id)).toEqual(["c", "a", "b"]);
    expect(withTask(tasks, task({ id: "b", done: 2 }))).toEqual([task({ id: "b", done: 2 }), task({ id: "a" })]);
});

test("a task that makes audio is described by the sentences that were read, left unread and failed", () => {
    const speech = task({ kind: "speech", total: 3 });

    expect(describeTask(speech)).toBe("Making the audio: 1 of 3");
    expect(describeTask({ ...speech, state: "done", result: taken("made", "made", "stopped", "failed") })).toBe(
        "Sentences: 2 read, 1 left unread, 1 failed",
    );
    expect(mentioned({ ...speech, result: taken("made", "failed") }).map((one) => one.status)).toEqual(["failed"]);
    expect([taskName(speech), taskName(task())]).toEqual(["Read aloud", "Add to vocabulary"]);
});

test("the tasks of topics are named and described for what they do", () => {
    expect(taskName(task({ kind: "icon" }))).toBe("Topic icon");
    expect(taskName(task({ kind: "embeddings" }))).toBe("Embed vocabulary");
    expect(describeTask(task({ kind: "embeddings", state: "running", done: 1, total: 4 }))).toBe(
        "Embedding the words: 1 of 4",
    );
    expect(describeTask(task({ kind: "icon", state: "done" }))).toBe("The icon is made.");
    expect(mentioned(task({ kind: "icon", state: "done" }))).toEqual([]);
});
