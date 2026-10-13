// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import {
    answerFraction,
    defaultQuestions,
    describeAnswer,
    isAskable,
    isQuestion,
    type ProfileQuestion,
    requestQuestions,
    upToDateQuestions,
} from "./questions";

const [grammar, clarity] = defaultQuestions();

function polite(change: Partial<ProfileQuestion> = {}): ProfileQuestion {
    return {
        id: "polite",
        title: "Politeness",
        kind: "choice",
        instructions: "Is the sentence polite?",
        options: [{ label: "yes", description: "It is polite." }, { label: "no", description: "" }],
        enabled: true,
        ...change,
    };
}

test("a choice is sent with its options by name, and one without a description says its name", () => {
    expect(requestQuestions([polite()])).toEqual({
        polite: {
            type: "choice",
            instructions: "Is the sentence polite?",
            criteria: { yes: "It is polite.", no: "no" },
        },
    });
});

test("a score is sent with its levels in order, lowest first", () => {
    expect(requestQuestions([clarity]).clarity.criteria).toEqual([
        "Unclear: It is not possible to tell what is meant.",
        "Hard to follow: The meaning can only be guessed.",
        "Mostly clear: The meaning comes across with some effort.",
        "Clear: The meaning is plain on first reading.",
    ]);
});

test("a disabled question is not sent", () => {
    expect(Object.keys(requestQuestions([grammar, { ...clarity, enabled: false }]))).toEqual(["grammar_errors"]);
});

test("a question that cannot be asked is not sent", () => {
    expect(requestQuestions([polite({ instructions: " " })])).toEqual({});
});

test.each([
    ["no instructions", polite({ instructions: "" })],
    ["a single option", polite({ options: [{ label: "yes", description: "" }] })],
    [
        "an option without a name",
        polite({ options: [{ label: "yes", description: "" }, { label: " ", description: "" }] }),
    ],
    [
        "two options of the same name",
        polite({ options: [{ label: "yes", description: "" }, { label: "yes ", description: "" }] }),
    ],
])("a question with %s cannot be asked", (_, question) => {
    expect(isAskable(question)).toBe(false);
});

test("the default questions can be asked", () => {
    expect(defaultQuestions().every(isAskable)).toBe(true);
});

test("a choice is described by the option picked", () => {
    const answer = { kind: "choice" as const, choice: "one", score: null, max_score: null, confidence: 0.9 };

    expect(describeAnswer(grammar, answer)).toBe("one");
});

test("a score is described by the nearest level and its place on the scale", () => {
    const answer = { kind: "score" as const, choice: null, score: 2.4, max_score: 3, confidence: 0.7 };

    expect(describeAnswer(clarity, answer)).toBe("Mostly clear (2.4 of 3)");
    expect(answerFraction(clarity, answer)).toBeCloseTo(0.8);
});

function picked(choice: string) {
    return { kind: "choice" as const, choice, score: null, max_score: null, confidence: null };
}

test("a choice is as good as the option picked is far down the list", () => {
    expect(["several", "one", "none"].map((choice) => answerFraction(grammar, picked(choice)))).toEqual([0, 0.5, 1]);
});

test("an answer that is not one of the options cannot be placed", () => {
    expect(answerFraction(grammar, picked("plenty"))).toBeNull();
});

test("a stored grammar question that lists its options best first is turned round", () => {
    const stored = { ...grammar, options: [...grammar.options].reverse() };

    const [question] = upToDateQuestions([stored]);

    expect(question.options.map((option) => option.label)).toEqual(["several", "one", "none"]);
});

test("stored questions that were changed by hand are left as they are", () => {
    const edited = { ...grammar, options: [{ label: "none", description: "" }, { label: "some", description: "" }] };

    expect(upToDateQuestions([edited, clarity])).toEqual([edited, clarity]);
});

test("stored values that are not questions are told apart from ones that are", () => {
    expect(isQuestion(polite())).toBe(true);
    expect(isQuestion({ ...polite(), options: "yes, no" })).toBe(false);
    expect(isQuestion({ ...polite(), kind: "essay" })).toBe(false);
    expect(isQuestion(null)).toBe(false);
});
