// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, it } from "vitest";

import { currentPart, describeLength, type Evaluation, type EvaluationPart, shownScores } from "./evaluations";

function part(status: EvaluationPart["status"]): EvaluationPart {
    return {
        module: "lesen",
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
        length: 2,
        timed: true,
        plan: { exam: "A1", pass: { total: 60 }, modules: [] },
        status: "running",
        started_at: 0,
        finished_at: null,
        result: { scores: {}, passed: null },
        parts: statuses.map(part),
    };
}

describe("describeLength", () => {
    it("says half hours as hours and minutes", () => {
        expect(describeLength(1)).toBe("30 min");
        expect(describeLength(2)).toBe("1 h");
        expect(describeLength(3)).toBe("1 h 30 min");
        expect(describeLength(8)).toBe("4 h");
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
            scores: { total: 70, lesen: 80, hoeren: null, schreiben_aufgabe: 50 },
            passed: null,
        });

        expect(shown).toEqual([
            { name: "lesen", label: "Lesen", value: 80 },
            { name: "schreiben_aufgabe", label: "Schreiben: task", value: 50 },
            { name: "total", label: "Total", value: 70 },
        ]);
    });
});
