// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import {
    answerFraction,
    answerStars,
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

test("what a question asks and what its options mean are filled in before they are sent", () => {
    const question = polite({
        instructions: "Is the sentence polite in {{language}}?",
        options: [{ label: "yes", description: "Polite at {{level}}." }, { label: "no", description: "" }],
    });

    const sent = requestQuestions([question], (text) =>
        text.replaceAll("{{language}}", "German")
            .replaceAll("{{level}}", "A2")).polite;

    expect(sent.instructions).toBe("Is the sentence polite in German?");
    expect(sent.criteria).toEqual({ yes: "Polite at A2.", no: "no" });
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

test("a stored grammar question with the instructions of an earlier version is given the ones asked now", () => {
    const stored = {
        ...grammar,
        enabled: false,
        instructions: "How many grammar errors does the sentence have? Judge it by the rules of the language it is "
            + "written in. Count mistakes in grammar only, such as word order, agreement, case, tense and missing or "
            + "extra words. Do not count spelling or punctuation.",
        options: [{ label: "several", description: "" }, { label: "one", description: "" }, {
            label: "none",
            description: "",
        }],
    };

    expect(upToDateQuestions([stored])).toEqual([{ ...grammar, enabled: false }]);
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

function choiceOf(count: number): ProfileQuestion {
    return polite({ options: Array.from({ length: count }, (_, at) => ({ label: `o${at}`, description: "" })) });
}

test.each([
    [2, 2, [1, 2]],
    [3, 3, [1, 2, 3]],
    [5, 5, [1, 2, 3, 4, 5]],
    [6, 3, [0.5, 1, 1.5, 2, 2.5, 3]],
    [7, 4, [1, 1.5, 2, 2.5, 3, 3.5, 4]],
    [11, 3, [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 2.75, 3]],
    [17, 5, [1, 1.25, 1.5, 1.75, 2, 2.25, 2.5, 2.75, 3, 3.25, 3.5, 3.75, 4, 4.25, 4.5, 4.75, 5]],
])("a choice of %i options is drawn with %i stars, filled a step more for each option", (count, stars, filled) => {
    const question = choiceOf(count);

    const drawn = question.options.map((option) => answerStars(question, picked(option.label)));

    expect(drawn).toEqual(filled.map((each) => ({ stars, filled: each })));
});

test("a choice of more options than quarter stars can draw, or a score, has no stars", () => {
    const many = choiceOf(21);

    expect(answerStars(many, picked("o0"))).toBeNull();
    expect(answerStars(clarity, { kind: "score", choice: null, score: 2, max_score: 3, confidence: null })).toBeNull();
});
