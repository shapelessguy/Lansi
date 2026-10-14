// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { dueDate, plainText, seesAnkiWords, type Timing, wordsFromRows } from "./anki";

test("the Anki words are shown to the user whose collection they are from, and to nobody else", () => {
    expect(seesAnkiWords("cian_cl")).toBe(true);
    expect(seesAnkiWords("someone_else")).toBe(false);
    expect(seesAnkiWords("")).toBe(false);
});

// day 137 of the collection, which ends at local midnight after 2026-10-12
const timing: Timing = {
    days_elapsed: 137,
    next_day_at: new Date(2026, 9, 13).getTime() / 1000,
};

test("a card due on the current day is due today", () => {
    expect(dueDate(137, timing)).toBe("2026-10-12");
});

test("due days before and after today map to past and future dates", () => {
    expect(dueDate(98, timing)).toBe("2026-09-03");
    expect(dueDate(339, timing)).toBe("2027-05-02");
});

test("a card being relearned stores a time, which maps to that day", () => {
    const relearnAt = new Date(2026, 9, 12, 18, 30).getTime() / 1000;

    expect(dueDate(relearnAt, timing)).toBe("2026-10-12");
});

test("plain text drops markup and sound tags", () => {
    expect(plainText("<b>der&nbsp;Film</b> [sound:film.mp3]")).toBe("der Film");
});

test("the meaning and part of speech are taken from the fields with those names", () => {
    const fieldNames = new Map([[1, ["German", "Picture", "English", "Part of Speech"]]]);
    const row = [10, 1, "sitzen", ["sitzen", "", "to sit", "verb"].join("\x1f"), 98, 60] as const;

    const [word] = wordsFromRows([[...row]], fieldNames, timing);

    expect(word).toEqual({
        noteId: 10,
        word: "sitzen",
        meaning: "to sit",
        partOfSpeech: "verb",
        due: "2026-09-03",
        intervalDays: 60,
    });
});

test("the second field is the meaning when no field name says so", () => {
    const fieldNames = new Map([[2, ["Front", "Rückseite"]]]);

    const [word] = wordsFromRows([[11, 2, "hola", "hola\x1fhello", 137, 3]], fieldNames, timing);

    expect(word.meaning).toBe("hello");
    expect(word.partOfSpeech).toBe("");
});
