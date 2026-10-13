// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import {
    applySuggestion,
    doubt,
    type LiveCheck,
    markedParts,
    type Sentence,
    sentenceAtCaret,
    sentenceParts,
    sentenceState,
    spellingIssues,
} from "./checker";

function sentence(text: string, start: number, spelling: Sentence["spelling"]): Sentence {
    return { text, start, end: start + text.length, complete: true, spelling, processed: false };
}

// "Hundd" is at 15-20 in the text, and "gutt" at 29-33
const text = "Ich habe einen Hundd. Er ist gutt.";
const check: LiveCheck = {
    text,
    localModel: null,
    sentences: [
        sentence("Ich habe einen Hundd.", 0, [{ word: "Hundd", start: 15, end: 20, suggestions: ["Hund"] }]),
        sentence("Er ist gutt.", 22, [{ word: "gutt", start: 7, end: 11, suggestions: ["gut"] }]),
    ],
};

function words(issues: { word: string }[]): string[] {
    return issues.map((issue) => issue.word);
}

test("issues are placed in the whole text rather than in their sentence", () => {
    const issues = spellingIssues(check, text, null);

    expect(issues.map((issue) => [issue.start, issue.end])).toEqual([[15, 20], [29, 33]]);
    expect(issues.map((issue) => text.slice(issue.start, issue.end))).toEqual(["Hundd", "gutt"]);
});

test("there are no issues before the checker has answered", () => {
    expect(spellingIssues(null, text, null)).toEqual([]);
});

test("typing on at the end keeps the issues found so far", () => {
    expect(words(spellingIssues(check, `${text} Und dann`, null))).toEqual(["Hundd", "gutt"]);
});

test("an issue is dropped once its word was changed, or moved by an earlier edit", () => {
    const fixed = "Ich habe einen Hund. Er ist gutt.";

    // "gutt" is still wrong, but no longer where the check found it
    expect(spellingIssues(check, fixed, null)).toEqual([]);
});

test("the word the caret is in or next to is not reported", () => {
    expect(words(spellingIssues(check, text, 17))).toEqual(["gutt"]);
    expect(words(spellingIssues(check, text, 20))).toEqual(["gutt"]);
    expect(words(spellingIssues(check, text, 15))).toEqual(["gutt"]);
});

test("a caret elsewhere hides nothing", () => {
    expect(words(spellingIssues(check, text, 21))).toEqual(["Hundd", "gutt"]);
});

test("the text is cut into marked and unmarked parts that join back into it", () => {
    const parts = markedParts(text, spellingIssues(check, text, null));

    expect(parts.map((part) => [part.text, part.issue?.word ?? null])).toEqual([
        ["Ich habe einen ", null],
        ["Hundd", "Hundd"],
        [". Er ist ", null],
        ["gutt", "gutt"],
        [".", null],
    ]);
});

test("a text without issues is one unmarked part, and an empty text has none", () => {
    expect(markedParts("Alles gut.", [])).toEqual([{ text: "Alles gut.", issue: null, value: null }]);
    expect(markedParts("", [])).toEqual([]);
});

test("applying a suggestion replaces only the misspelled word", () => {
    const [hundd] = spellingIssues(check, text, null);

    expect(applySuggestion(text, hundd, "Hund")).toBe("Ich habe einen Hund. Er ist gutt.");
});

test("the sentence at the caret is the one the server found it on", () => {
    const [first, second] = check.sentences;
    const withCaretOnFirst = { ...check, sentences: [{ ...first, complete: false }, second] };

    expect(sentenceAtCaret(withCaretOnFirst, 30)?.text).toBe("Ich habe einen Hundd.");
});

test("once the box is left, the sentence at the caret is the one it was last on", () => {
    expect(sentenceAtCaret(check, 5)?.text).toBe("Ich habe einen Hundd.");
    expect(sentenceAtCaret(check, 25)?.text).toBe("Er ist gutt.");
});

test("there is no sentence at the caret before the box was used or the checker answered", () => {
    expect(sentenceAtCaret(check, null)).toBeNull();
    expect(sentenceAtCaret(null, 5)).toBeNull();
});

test("the text is cut into its sentences and the space between them", () => {
    const pieces = sentenceParts(text, check, []);

    expect(pieces.map((piece) => [piece.sentence?.text ?? null, piece.parts.map((part) => part.text).join("")]))
        .toEqual([
            ["Ich habe einen Hundd.", "Ich habe einen Hundd."],
            [null, " "],
            ["Er ist gutt.", "Er ist gutt."],
        ]);
});

test("a sentence is cut further at its spelling issues", () => {
    const [first] = sentenceParts(text, check, spellingIssues(check, text, null));

    expect(first.parts.map((part) => [part.text, part.issue?.word ?? null])).toEqual([
        ["Ich habe einen ", null],
        ["Hundd", "Hundd"],
        [".", null],
    ]);
});

test("a sentence that has changed since it was checked is not taken as one", () => {
    const edited = text.replace("Er ist", "Sie ist");

    const pieces = sentenceParts(edited, check, []);

    expect(pieces.map((piece) => piece.sentence?.text ?? null)).toEqual(["Ich habe einen Hundd.", null]);
    expect(pieces.flatMap((piece) => piece.parts).map((part) => part.text).join("")).toBe(edited);
});

test("text the checker has not answered about yet has no sentences", () => {
    expect(sentenceParts("Hallo.", null, [])).toEqual([{
        sentence: null,
        parts: [{ text: "Hallo.", issue: null, value: null }],
    }]);
    expect(sentenceParts("", check, [])).toEqual([]);
});

test.each(
    [
        ["typing", { complete: false }],
        ["done", {}],
        ["checking", { profiling: true }],
        ["checked", { processed: true }],
        ["failed", { profile_error: "no credit left" }],
        // going back onto a sentence that was checked is typing again
        ["typing", { complete: false, processed: true }],
    ] as const,
)("a sentence is %s when it is %j", (state, change) => {
    expect(sentenceState({ ...sentence("Er ist gut.", 0, []), ...change })).toBe(state);
});

test("a sentence is cut at its rated words, each with its value", () => {
    const rated = { ...check.sentences[1], words: [{ word: "ist", start: 3, end: 6, value: 0.2 }] };

    const [, , second] = sentenceParts(text, { ...check, sentences: [check.sentences[0], rated] }, []);

    expect(second.parts.map((part) => [part.text, part.value])).toEqual([
        ["Er ", null],
        ["ist", 0.2],
        [" gutt.", null],
    ]);
});

test("a rated word that is misspelled as well is one stretch with both", () => {
    const rated = { ...check.sentences[1], words: [{ word: "gutt", start: 7, end: 11, value: 0.1 }] };
    const issues = spellingIssues(check, text, null);

    const [, , second] = sentenceParts(text, { ...check, sentences: [check.sentences[0], rated] }, issues);

    expect(second.parts.map((part) => [part.text, part.issue?.word ?? null, part.value])).toEqual([
        ["Er ist ", null, null],
        ["gutt", "gutt", 0.1],
        [".", null, null],
    ]);
});

test("a word is marked the more strongly the less right it is, and not at all when nearly right", () => {
    expect(doubt(0)).toBe(1);
    expect(doubt(0.425)).toBeCloseTo(0.5);
    expect([0.85, 0.9, 1].map(doubt)).toEqual([0, 0, 0]);
    expect(doubt(0.2)).toBeGreaterThan(doubt(0.6));
});
