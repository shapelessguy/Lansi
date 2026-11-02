// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import diary from "./fixtures/corrections/diary.json";
import edgeCases from "./fixtures/corrections/edge_cases.json";
import letter from "./fixtures/corrections/letter.json";
import type { Stroke } from "./ink";
import { type Correction, correctionArea, correctionMarks, MARK_COLORS, marksOf } from "./marks";
import type { HandwrittenWord } from "./texts";

/**
 * Three pages written by hand, as Vision read them, with what a model is to
 * correct on them: each kind of correction at least once.
 */
const FIXTURES = [diary, letter, edgeCases].map((fixture) => ({
    words: fixture.words as HandwrittenWord[],
    corrections: fixture.corrections as Correction[],
    ink: fixture.ink as Stroke[],
}));
const [DIARY, LETTER, EDGES] = FIXTURES;

const xs = (stroke: Stroke) => stroke.points.map((point) => point[0]);
const ys = (stroke: Stroke) => stroke.points.map((point) => point[1]);
const left = (word: HandwrittenWord) => Math.min(...word.box.map((corner) => corner[0]));
const right = (word: HandwrittenWord) => Math.max(...word.box.map((corner) => corner[0]));
const top = (word: HandwrittenWord) => Math.min(...word.box.map((corner) => corner[1]));
const bottom = (word: HandwrittenWord) => Math.max(...word.box.map((corner) => corner[1]));

/** Whether `stroke` runs across `word`, between its top and its bottom, from its left to its right. */
function crosses(stroke: Stroke, word: HandwrittenWord): boolean {
    return Math.min(...xs(stroke)) <= left(word) + 5 && Math.max(...xs(stroke)) >= right(word) - 5
        && ys(stroke).every((y) => y > top(word) && y < bottom(word));
}

function only(fixture: (typeof FIXTURES)[number], type: Correction["type"]): Correction {
    return fixture.corrections.find((correction) => correction.type === type) as Correction;
}

test("a misread word is not marked, as it is not the learner's mistake", () => {
    expect(correctionMarks(only(DIARY, "misread"), DIARY.words)).toEqual([]);
});

test("a replacement strikes its words out on each line they are on, and writes the right ones above", () => {
    // «la mia», the line ending between them
    const marks = correctionMarks(only(DIARY, "replace"), DIARY.words);
    expect(DIARY.words[6].line).not.toBe(DIARY.words[7].line);
    expect(marks.some((stroke) => crosses(stroke, DIARY.words[6]))).toBe(true);
    expect(marks.some((stroke) => crosses(stroke, DIARY.words[7]))).toBe(true);
    const written = marks.filter((stroke) => Math.max(...ys(stroke)) < top(DIARY.words[6]) + 5);
    expect(written.length).toBeGreaterThan(3);
    expect(marks.every((stroke) => stroke.color === MARK_COLORS.error)).toBe(true);
});

test("an erased word is only struck out", () => {
    const marks = correctionMarks(only(DIARY, "erase"), DIARY.words);
    expect(marks).toHaveLength(1);
    expect(crosses(marks[0], DIARY.words[17])).toBe(true);
});

test("an insertion puts a caret between the two words and writes what goes there above it", () => {
    const [caret, ...text] = correctionMarks(only(DIARY, "insert"), DIARY.words);
    const middle = xs(caret)[Math.floor(xs(caret).length / 2)];
    expect(middle).toBeGreaterThan(right(DIARY.words[19]) - 10);
    expect(middle).toBeLessThan(left(DIARY.words[20]) + 10);
    expect(text.length).toBeGreaterThan(0);
    expect(text.every((stroke) => Math.max(...ys(stroke)) < top(DIARY.words[19]) + 5)).toBe(true);
});

test("an insertion before the first word puts its caret left of it", () => {
    const [caret] = correctionMarks({ type: "insert", after_id: -1, text: "La" }, EDGES.words);
    expect(Math.max(...xs(caret))).toBeLessThan(left(EDGES.words[0]) + 5);
});

test("an insertion after the last word of a line puts its caret past it", () => {
    // «cominciato» ends the first line
    expect(EDGES.words[4].line).toBe(EDGES.words[3].line + 1);
    const [caret] = correctionMarks({ type: "insert", after_id: 3, text: "x" }, EDGES.words);
    expect(Math.min(...xs(caret))).toBeGreaterThan(right(EDGES.words[3]) - 10);
});

test("a moved word is ringed, and an arrow goes from it to the caret where it belongs", () => {
    const marks = correctionMarks(only(LETTER, "move"), LETTER.words);
    const [ring, arrow, head, caret] = marks;
    const gia = LETTER.words[15];
    expect(Math.min(...xs(ring))).toBeLessThan(left(gia));
    expect(Math.max(...xs(ring))).toBeGreaterThan(right(gia));
    // «Ho» and «comprato»
    const gap = (right(LETTER.words[13]) + left(LETTER.words[14])) / 2;
    expect(Math.abs(xs(arrow)[xs(arrow).length - 1] - gap)).toBeLessThan(20);
    expect(head.points.length).toBeGreaterThan(2);
    expect(Math.abs(xs(caret)[Math.floor(xs(caret).length / 2)] - gap)).toBeLessThan(20);
});

test("joined words are linked under the gap, with what they become written over them if it is more than the words put together", () => {
    // «In vece» is «Invece»
    expect(correctionMarks(only(LETTER, "join"), LETTER.words)).toHaveLength(1);
    // «la acqua» is «l'acqua»
    const [arc, ...text] = correctionMarks(only(DIARY, "join"), DIARY.words);
    expect(Math.min(...ys(arc))).toBeGreaterThan(top(DIARY.words[29]));
    expect(text.every((stroke) => Math.max(...ys(stroke)) < top(DIARY.words[29]) + 5)).toBe(true);
});

test("a split word is cut where the space goes", () => {
    // «Unabbraccio,» is «Un abbraccio,», cut after two of its twelve letters
    const [bar, ...rest] = correctionMarks(only(LETTER, "split"), LETTER.words);
    const word = LETTER.words[58];
    const expected = left(word) + ((right(word) - left(word)) * 2) / 12;
    expect(Math.abs(xs(bar)[0] - expected)).toBeLessThan(10);
    expect(rest).toEqual([]);
});

/** A word read with each of its letters placed, as wide as `widths` says, from `x` on line 0. */
function placed(text: string, x: number, widths: number[]): HandwrittenWord {
    const letters = [...text].map((char, index) => {
        const left = x + widths.slice(0, index).reduce((sum, wide) => sum + wide, 0);
        const box: [number, number][] = [[left, 100], [left + widths[index], 100], [left + widths[index], 160], [
            left,
            160,
        ]];
        return { text: char, box };
    });
    const right = letters[letters.length - 1].box[1][0];
    return {
        text,
        box: [[x, 100], [right, 100], [right, 160], [x, 160]],
        line: 0,
        paragraph: 0,
        confidence: 0.9,
        letters,
    };
}

test("a wrong ending is struck out alone, with the right one over it", () => {
    // «schönen» for «schöner»: the «n» at the end, from 130 to 150
    const word = placed("schönen", 0, [20, 20, 20, 25, 20, 25, 20]);
    const [strike, ...text] = correctionMarks({ type: "replace", from_id: 0, to_id: 0, text: "schöner" }, [word]);
    expect(Math.min(...xs(strike))).toBeGreaterThan(120);
    expect(Math.max(...xs(strike))).toBeLessThan(160);
    expect(text.length).toBeGreaterThan(0);
    expect(text.every((stroke) => Math.min(...xs(stroke)) > 115 && Math.max(...ys(stroke)) < 100)).toBe(true);
});

test("a missing letter gets a caret between the letters it goes between", () => {
    // «bellisimo» for «bellissimo»: after the «s», which ends at 70
    const word = placed("bellisimo", 0, [10, 10, 10, 10, 10, 20, 10, 20, 10]);
    const [caret] = correctionMarks({ type: "replace", from_id: 0, to_id: 0, text: "bellissimo" }, [word]);
    expect(Math.abs(xs(caret)[Math.floor(xs(caret).length / 2)] - 70)).toBeLessThan(3);
});

test("a word that is mostly wrong is struck out whole", () => {
    const word = placed("uno", 0, [20, 20, 20]);
    const [strike] = correctionMarks({ type: "replace", from_id: 0, to_id: 0, text: "del" }, [word]);
    expect(crosses(strike, word)).toBe(true);
});

test("a word is split where its letters end on the page, if they were placed", () => {
    // «Unabbraccio,» with a wide «U»: «Un» ends at 50, not at a sixth of its width
    const word = placed("Unabbraccio,", 0, [30, 20, 15, 15, 15, 15, 15, 15, 15, 15, 15, 5]);
    const [bar] = correctionMarks({ type: "split", id: 0, text: "Un abbraccio," }, [word]);
    expect(Math.abs(xs(bar)[0] - 50)).toBeLessThan(3);
});

test("a suggestion is underlined and written above in the colour of a suggestion, not an error", () => {
    const marks = correctionMarks(only(LETTER, "suggest"), LETTER.words);
    expect(marks.every((stroke) => stroke.color === MARK_COLORS.suggestion)).toBe(true);
    // «un ristorante buono?», over two lines
    const lines = new Set(LETTER.words.slice(28, 31).map((word) => word.line));
    expect(marks.filter((stroke) => xs(stroke).length > 20).length).toBeGreaterThanOrEqual(lines.size);
});

test("what is written over the words goes between them and the line above, clear of the ink of both", () => {
    // «un buon ristorante?», over «un ristorante», under «stazione. Potresti»
    const marks = correctionMarks(only(LETTER, "suggest"), LETTER.words, LETTER.ink);
    const line = LETTER.words[28].line;
    const text = marks.filter((stroke) => Math.max(...ys(stroke)) < top(LETTER.words[28]));
    expect(text.length).toBeGreaterThan(5);
    const [from, to] = [Math.min(...text.flatMap(xs)), Math.max(...text.flatMap(xs))];
    const above = LETTER.words.filter((word) => word.line === line - 1 && left(word) < to && right(word) > from);
    expect(above.length).toBeGreaterThan(0);
    // hardly touching the ink of the learner's, but where a descender or an ascender reaches into it
    const learner = LETTER.ink.flatMap((stroke) => stroke.points);
    const points = text.flatMap((stroke) => stroke.points);
    const touching = points.filter(([x, y]) => learner.some(([lx, ly]) => Math.hypot(lx - x, ly - y) < 3));
    expect(touching.length / points.length).toBeLessThan(0.05);
    // and between the two lines
    expect(Math.min(...text.flatMap(ys))).toBeGreaterThan(Math.min(...above.map(bottom)) - 30);
});

test("a comment highlights its words", () => {
    const [mark] = correctionMarks(only(LETTER, "comment"), LETTER.words);
    expect(mark.pen).toBe("highlighter");
    expect(mark.color).toBe(MARK_COLORS.comment);
    expect(crosses(mark, LETTER.words[10])).toBe(true);
});

test("praise underlines its words in green and ticks them", () => {
    const marks = correctionMarks(only(DIARY, "praise"), DIARY.words);
    expect(marks.every((stroke) => stroke.color === MARK_COLORS.praise)).toBe(true);
    const lines = new Set(DIARY.words.slice(36, 42).map((word) => word.line));
    expect(marks).toHaveLength(lines.size + 1);
});

test("an illegible word is gone over with a light highlighter", () => {
    const marks = correctionMarks(only(LETTER, "illegible"), LETTER.words);
    expect(marks.length).toBeGreaterThan(0);
    expect(marks.every((stroke) => stroke.pen === "highlighter" && stroke.color === MARK_COLORS.unclear)).toBe(true);
});

test("a correction that names words the page does not have draws nothing", () => {
    const words = DIARY.words;
    expect(correctionMarks({ type: "erase", from_id: 3, to_id: words.length }, words)).toEqual([]);
    expect(correctionMarks({ type: "replace", from_id: 5, to_id: 4, text: "x" }, words)).toEqual([]);
    expect(correctionMarks({ type: "insert", after_id: words.length, text: "x" }, words)).toEqual([]);
    expect(correctionMarks({ type: "split", id: -1, text: "a b" }, words)).toEqual([]);
});

test("the corrections of a page are drawn on it, the same each time", () => {
    for (const { words, corrections, ink } of FIXTURES) {
        const marks = marksOf(corrections, words, ink);
        expect(marks.length).toBeGreaterThan(corrections.length);
        for (const stroke of marks) {
            expect(stroke.points.length).toBeGreaterThan(0);
            expect(stroke.size).toBeGreaterThanOrEqual(1);
            expect(stroke.size).toBeLessThanOrEqual(40);
            for (const [x, y, pressure] of stroke.points) {
                expect(x).toBeGreaterThanOrEqual(0);
                expect(x).toBeLessThanOrEqual(1240);
                expect(y).toBeGreaterThanOrEqual(0);
                expect(y).toBeLessThanOrEqual(1754);
                expect(pressure).toBeGreaterThan(0);
            }
        }
        expect(marksOf(corrections, words, ink)).toEqual(marks);
    }
});

test("the area of a correction is the boxes of its words, or of the two an insertion goes between", () => {
    const words = DIARY.words;
    expect(correctionArea({ type: "erase", from_id: 3, to_id: 4 }, words)).toEqual([words[3].box, words[4].box]);
    expect(correctionArea({ type: "insert", after_id: 5, text: "a" }, words)).toEqual([words[5].box, words[6].box]);
    expect(correctionArea({ type: "insert", after_id: -1, text: "a" }, words)).toEqual([words[0].box]);
    expect(correctionArea({ type: "misread", from_id: 1, to_id: 1, text: "x" }, words)).toEqual([]);
});
