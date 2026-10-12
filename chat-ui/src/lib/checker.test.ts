// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { applySuggestion, type LiveCheck, markedParts, type Sentence, spellingIssues } from "./checker";

function sentence(text: string, start: number, spelling: Sentence["spelling"]): Sentence {
    return { text, start, end: start + text.length, complete: true, spelling, processed: false };
}

// "Hundd" is at 15-20 in the text, and "gutt" at 29-33
const text = "Ich habe einen Hundd. Er ist gutt.";
const check: LiveCheck = {
    text,
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
    expect(markedParts("Alles gut.", [])).toEqual([{ text: "Alles gut.", issue: null }]);
    expect(markedParts("", [])).toEqual([]);
});

test("applying a suggestion replaces only the misspelled word", () => {
    const [hundd] = spellingIssues(check, text, null);

    expect(applySuggestion(text, hundd, "Hund")).toBe("Ich habe einen Hund. Er ist gutt.");
});
