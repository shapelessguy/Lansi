// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { filterWords, sortWords, type Word } from "./words";

function word(fields: Partial<Word>): Word {
    return { noteId: 0, word: "", meaning: "", partOfSpeech: "", due: "2026-01-01", intervalDays: 1, ...fields };
}

const sitzen = word({ word: "sitzen", meaning: "to sit", due: "2026-09-03", intervalDays: 60 });
const film = word({ word: "der Film", meaning: "film", due: "2026-09-03", intervalDays: 54 });
const art = word({ word: "die Art", meaning: "type, kind", due: "2027-04-25", intervalDays: 232 });

function names(words: Word[]): string[] {
    return words.map((entry) => entry.word);
}

test("sorting by due date puts the earliest first and breaks ties by word", () => {
    expect(names(sortWords([art, sitzen, film], "due", false))).toEqual(["der Film", "sitzen", "die Art"]);
});

test("sorting descending reverses the key but still breaks ties by word", () => {
    expect(names(sortWords([sitzen, art, film], "due", true))).toEqual(["die Art", "der Film", "sitzen"]);
});

test("sorting by interval compares numbers rather than text", () => {
    expect(names(sortWords([art, film, sitzen], "interval", false))).toEqual(["der Film", "sitzen", "die Art"]);
});

test("sorting by word ignores case and accents", () => {
    const words = [word({ word: "zu" }), word({ word: "Äpfel" }), word({ word: "apfel" }), word({ word: "Bär" })];

    expect(names(sortWords(words, "word", false))).toEqual(["Äpfel", "apfel", "Bär", "zu"]);
});

test("sorting leaves the given list unchanged", () => {
    const words = [art, sitzen];

    sortWords(words, "word", true);

    expect(names(words)).toEqual(["die Art", "sitzen"]);
});

test("filtering matches the word or its meaning, ignoring case", () => {
    const words = [sitzen, film, art];

    expect(names(filterWords(words, "FILM"))).toEqual(["der Film"]);
    expect(names(filterWords(words, "kind"))).toEqual(["die Art"]);
});

test("filtering with a blank query keeps every word", () => {
    expect(filterWords([sitzen, film], "  ")).toEqual([sitzen, film]);
});
