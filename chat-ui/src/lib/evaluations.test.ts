// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, it } from "vitest";

import { currentPart, type Evaluation, type EvaluationPart, minutesOf, shownScores } from "./evaluations";

function part(status: EvaluationPart["status"]): EvaluationPart {
    return {
        module: "reading",
        title: "Teil 1",
        exercise: "comprehension",
        options: {},
        instances: 1,
        minutes: 10,
        points: 5,
        instructions: "",
        session: status === "pending" ? null : "s",
        status,
        scores: null,
    };
}

function evaluation(...statuses: EvaluationPart["status"][]): Evaluation {
    return {
        id: "e",
        language: "German",
        level: "A1",
        size: 3,
        timed: true,
        plan: { exam: "A1", pass: { total: 60 }, modules: [] },
        status: "running",
        started_at: 0,
        finished_at: null,
        result: { scores: {}, passed: null },
        parts: statuses.map(part),
    };
}

describe("minutesOf", () => {
    it("is what the parts take together", () => {
        expect(minutesOf(evaluation("done", "pending", "pending"))).toBe(30);
    });
});

describe("currentPart", () => {
    it("is the part that is running, or else the first not done", () => {
        expect(currentPart(evaluation("done", "running", "pending"))).toBe(1);
        expect(currentPart(evaluation("done", "pending", "pending"))).toBe(1);
    });

    it("is none once every part is done", () => {
        expect(currentPart(evaluation("done", "done"))).toBeNull();
    });
});

describe("shownScores", () => {
    it("are those that were shown, in the order of the scores, with their names", () => {
        const shown = shownScores({
            scores: { total: 70, reading: 80, listening: null, writing_task: 50 },
            passed: null,
        });

        expect(shown).toEqual([
            { name: "reading", label: "Reading", value: 80 },
            { name: "writing_task", label: "Writing: task", value: 50 },
            { name: "total", label: "Total", value: 70 },
        ]);
    });

    it("call a module as the exam calls it", () => {
        const shown = shownScores(
            { scores: { reading: 80, writing_task: 50 }, passed: null },
            [{ id: "reading", title: "Lesen", weight: 1 }, { id: "writing", title: "Schreiben", weight: 1 }],
        );

        expect(shown.map((score) => score.label)).toEqual(["Lesen", "Schreiben: task"]);
    });
});
