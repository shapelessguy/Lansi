// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { changedLetters, type Correction } from "./corrections";
import { HERSHEY_SCRIPT } from "./hershey";
import type { Pen, Stroke } from "./ink";
import type { HandwrittenWord } from "./texts";

/**
 * The corrections of a page written by hand, as a model gives them, each
 * naming the words it is about by their place among the words read from the
 * page, and the strokes that draw them on it, as a teacher would with a pen:
 * placed by the boxes of those words, so that they follow the lines as they
 * were written, slant and all.
 */

export type { Correction };

/** The colour each kind of mark is drawn in. */
export const MARK_COLORS = {
    error: "#d32f2f",
    suggestion: "#1e63c8",
    praise: "#2e9d4a",
    comment: "#ffd400",
    unclear: "#9aa6b8",
} as const;

type Point = [number, number];

const add = (a: Point, b: Point): Point => [a[0] + b[0], a[1] + b[1]];
const scaled = (a: Point, by: number): Point => [a[0] * by, a[1] * by];
const lerp = (a: Point, b: Point, at: number): Point => [a[0] + (b[0] - a[0]) * at, a[1] + (b[1] - a[1]) * at];
const distance = (a: Point, b: Point) => Math.hypot(b[0] - a[0], b[1] - a[1]);

/**
 * The words of a span on one line: its corners, as Vision gives those of a
 * box, from the top left clockwise, how tall its writing is, and the way
 * the line runs, and the way down from it, each a unit long.
 */
interface Piece {
    topLeft: Point;
    topRight: Point;
    bottomRight: Point;
    bottomLeft: Point;
    height: number;
    along: Point;
    down: Point;
    /** The line of the page it is on. */
    line: number;
}

function pieceOf(first: HandwrittenWord, last: HandwrittenWord): Piece {
    const [topLeft, , , bottomLeft] = first.box;
    const [, topRight, bottomRight] = last.box;
    const height = (distance(topLeft, bottomLeft) + distance(topRight, bottomRight)) / 2;
    const length = distance(topLeft, topRight) || 1;
    const along: Point = [(topRight[0] - topLeft[0]) / length, (topRight[1] - topLeft[1]) / length];
    return { topLeft, topRight, bottomRight, bottomLeft, height, along, down: [-along[1], along[0]], line: first.line };
}

/** The words from `from` to `to` cut where the lines end, one piece for each line. */
function piecesOf(words: HandwrittenWord[], from: number, to: number): Piece[] {
    const pieces: Piece[] = [];
    let start = from;
    for (let at = from; at <= to; at++) {
        if (at === to || words[at + 1].line !== words[at].line) {
            pieces.push(pieceOf(words[start], words[at]));
            start = at + 1;
        }
    }
    return pieces;
}

/** A point of a piece, `across` of the way from its left to its right, `deep` of the way from its top to its bottom. */
function at(piece: Piece, across: number, deep: number): Point {
    return lerp(lerp(piece.topLeft, piece.bottomLeft, deep), lerp(piece.topRight, piece.bottomRight, deep), across);
}

/** A random generator with a seed, so that a correction is drawn the same each time. */
function seeded(seed: number): () => number {
    let state = seed >>> 0;
    return () => {
        state = (state + 0x6d2b79f5) >>> 0;
        let t = state;
        t = Math.imul(t ^ (t >>> 15), t | 1);
        t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

/** How far apart, in units of the page, the points of a mark are. */
const STEP = 4;

/**
 * A stroke through `points`, with a point every `STEP` between them, each
 * moved a little, and pressed a little harder or lighter, as a hand would.
 */
function handStroke(
    pen: Pen,
    color: string,
    size: number,
    points: Point[],
    random: () => number,
    shake = 0.6,
): Stroke {
    const dense: Point[] = [points[0]];
    for (let index = 1; index < points.length; index++) {
        const [from, to] = [points[index - 1], points[index]];
        const steps = Math.max(1, Math.ceil(distance(from, to) / STEP));
        for (let step = 1; step <= steps; step++) {
            dense.push(lerp(from, to, step / steps));
        }
    }
    let pressure = 0.5 + random() * 0.15;
    return {
        pen,
        color,
        size: Math.round(Math.min(Math.max(size, 1), 40) * 10) / 10,
        points: dense.map(([x, y]) => {
            pressure = Math.min(0.85, Math.max(0.3, pressure + (random() - 0.5) * 0.06));
            return [
                Math.round((x + (random() - 0.5) * shake) * 10) / 10,
                Math.round((y + (random() - 0.5) * shake) * 10) / 10,
                Math.round(pressure * 100) / 100,
            ];
        }),
    };
}

/** How thick a pen mark is on writing `height` tall. */
const penSize = (height: number) => Math.min(Math.max(height / 20, 2), 6);

const ACCENTS: Record<string, [string, "grave" | "acute"]> = {
    "à": ["a", "grave"],
    "è": ["e", "grave"],
    "é": ["e", "acute"],
    "ì": ["i", "grave"],
    "í": ["i", "acute"],
    "ò": ["o", "grave"],
    "ó": ["o", "acute"],
    "ù": ["u", "grave"],
    "ú": ["u", "acute"],
    "À": ["A", "grave"],
    "È": ["E", "grave"],
    "É": ["E", "acute"],
    "Ì": ["I", "grave"],
    "Ò": ["O", "grave"],
    "Ù": ["U", "grave"],
};
// how tall the font's small letters are, in its units
const FONT_X_HEIGHT = 290;
// how far a character the font does not have moves the pen on
const UNKNOWN_ADVANCE = 400;

/** The lines `text` is written with in the font, in its units, from x = 0, y up, and how wide it is. */
function shapeOf(text: string): { lines: Point[][]; width: number } {
    const lines: Point[][] = [];
    let x = 0;
    for (const char of text.normalize("NFC")) {
        const [base, accent] = ACCENTS[char] ?? [char, null];
        const glyph = HERSHEY_SCRIPT[base];
        if (!glyph) {
            x += UNKNOWN_ADVANCE;
            continue;
        }
        const [advance, drawn] = glyph;
        for (const line of drawn ? drawn.split("|") : []) {
            const numbers = line.split(" ").map(Number);
            const points: Point[] = [];
            for (let index = 0; index < numbers.length; index += 2) {
                points.push([numbers[index] + x, numbers[index + 1]]);
            }
            lines.push(points);
        }
        if (accent) {
            const middle = x + advance * 0.55;
            const top = base === base.toUpperCase() ? FONT_X_HEIGHT * 2.6 : FONT_X_HEIGHT;
            lines.push(
                accent === "grave"
                    ? [[middle - 60, top + 190], [middle + 30, top + 70]]
                    : [[middle - 30, top + 70], [middle + 60, top + 190]],
            );
        }
        x += advance;
    }
    return { lines, width: x };
}

/** How tall the small letters of what is written over the words are, for writing `height` tall. */
const textXHeight = (height: number) => height * 0.22;

/** How far what is written over the words keeps from them, and from the line above, for writing `height` tall. */
const textMargin = (height: number) => height * 0.08;

const topOf = (word: HandwrittenWord) => Math.min(word.box[0][1], word.box[1][1]);
const bottomOf = (word: HandwrittenWord) => Math.max(word.box[2][1], word.box[3][1]);
const leftOf = (word: HandwrittenWord) => Math.min(word.box[0][0], word.box[3][0]);
const rightOf = (word: HandwrittenWord) => Math.max(word.box[1][0], word.box[2][0]);

/**
 * The strokes that write `text` over the words of `piece`, from `anchor`, a
 * point of the top of its line, or centred on it: just above the words, as
 * large as is usual, where there is room for it below the line above, and
 * where there is not, smaller, so that it fits, in the middle between the
 * two lines.
 */
function label(
    text: string,
    anchor: Point,
    centred: boolean,
    piece: Piece,
    words: HandwrittenWord[],
    ink: Stroke[],
    color: string,
    random: () => number,
): Stroke[] {
    const shape = shapeOf(text);
    const ys = shape.lines.flat().map((point) => point[1]);
    if (!ys.length) {
        return [];
    }
    // how far the letters go above and below the baseline, in the font's units
    const [high, low] = [Math.max(...ys), Math.min(...ys)];
    const margin = textMargin(piece.height);
    const usual = textXHeight(piece.height) / FONT_X_HEIGHT;
    const across = (scale: number): [number, number] => {
        const width = shape.width * scale;
        const from = centred ? anchor[0] - width / 2 : anchor[0];
        return [from, from + width];
    };
    const overlapping = (line: number, [from, to]: [number, number]) =>
        words.filter((word) => word.line === line && leftOf(word) < to && rightOf(word) > from);
    const middleOf = (word: HandwrittenWord) => (topOf(word) + bottomOf(word)) / 2;
    const mean = (values: number[]) => values.reduce((sum, value) => sum + value, 0) / values.length;
    // the room there is: from the bottom of the line above, if there is one, to the top of this one,
    // where the ink of each is, if it is known, and its boxes, which take in a letter as tall as
    // it could be, if it is not
    const room = (scale: number): [number, number] => {
        const span = across(scale);
        const below = overlapping(piece.line, span);
        const above = overlapping(piece.line - 1, span);
        const boxes: [number, number] = [
            above.length ? Math.max(...above.map(bottomOf)) : -Infinity,
            below.length ? Math.min(anchor[1], ...below.map(topOf)) : anchor[1],
        ];
        if (!ink.length) {
            return boxes;
        }
        const upper = above.length ? mean(above.map(middleOf)) : -Infinity;
        const lower = below.length ? mean(below.map(middleOf)) : anchor[1] + piece.height / 2;
        const between = above.length ? (upper + lower) / 2 : -Infinity;
        // in columns across the span, the lowest ink of the line above and the highest of this one
        const width = Math.max(piece.height * 0.3, 1);
        const columns = Math.max(1, Math.ceil((span[1] - span[0]) / width));
        const ceilings = Array<number>(columns).fill(upper);
        const floors = Array<number>(columns).fill(lower);
        for (const stroke of ink) {
            for (const [x, y] of stroke.points) {
                if (x < span[0] || x >= span[1] || y <= upper || y >= lower) {
                    continue;
                }
                const column = Math.min(columns - 1, Math.floor((x - span[0]) / width));
                if (y < between) {
                    ceilings[column] = Math.max(ceilings[column], y);
                } else {
                    floors[column] = Math.min(floors[column], y);
                }
            }
        }
        // a descender or an ascender here and there is written past, as a teacher would
        const sorted = (values: number[]) => [...values].sort((one, other) => one - other);
        const ceiling = sorted(ceilings)[Math.floor((columns - 1) * 0.8)];
        const floor = sorted(floors)[Math.ceil((columns - 1) * 0.2)];
        // the ink is drawn as wide as its pen
        return [ceiling + 3, floor - 3];
    };
    let scale = usual;
    let [ceiling, floor] = room(scale);
    let baseline = floor - margin + low * scale;
    if (baseline - high * scale < ceiling + margin) {
        // not room enough: as large as fits, in the middle of the two lines
        const fits = (floor - ceiling - 2 * margin) / (high - low);
        scale = Math.max(Math.min(usual, fits), usual * 0.4);
        [ceiling, floor] = room(scale);
        baseline = (ceiling + floor) / 2 + ((high + low) / 2) * scale;
    }
    const start: Point = [across(scale)[0], baseline];
    const { along, down } = piece;
    const place = ([x, y]: Point): Point => add(add(start, scaled(along, x * scale)), scaled(down, -y * scale));
    const size = Math.max(penSize(piece.height) * 0.6 * (scale / usual), 1);
    return shape.lines.map((line) => handStroke("pen", color, size, line.map(place), random, 0.3));
}

/** `text` written over the start of `piece`. */
function writtenOver(
    piece: Piece,
    words: HandwrittenWord[],
    ink: Stroke[],
    text: string,
    color: string,
    random: () => number,
): Stroke[] {
    return label(text, piece.topLeft, false, piece, words, ink, color, random);
}

/** A line through the middle of the words of `piece`, a little past them at each end. */
function strike(piece: Piece, color: string, random: () => number): Stroke {
    const over = piece.height * 0.08;
    const left = add(at(piece, 0, 0.5), scaled(piece.along, -over));
    const right = add(at(piece, 1, 0.5), scaled(piece.along, over));
    const middle = add(lerp(left, right, 0.5), scaled(piece.down, (random() - 0.5) * piece.height * 0.06));
    return handStroke("pen", color, penSize(piece.height), [left, middle, right], random);
}

/** A line under the words of `piece`. */
function underline(piece: Piece, color: string, random: () => number): Stroke {
    return handStroke("pen", color, penSize(piece.height), [at(piece, 0, 0.92), at(piece, 1, 0.92)], random);
}

/** The points of an ellipse around `center`, its axes along `along` and across it, from `from` to `to` turns. */
function ellipse(center: Point, along: Point, rx: number, ry: number, from: number, to: number): Point[] {
    const down: Point = [-along[1], along[0]];
    const points: Point[] = [];
    const steps = 32;
    for (let step = 0; step <= steps; step++) {
        const angle = 2 * Math.PI * (from + ((to - from) * step) / steps);
        points.push(add(add(center, scaled(along, Math.cos(angle) * rx)), scaled(down, Math.sin(angle) * ry)));
    }
    return points;
}

/**
 * Where something goes after word `after` (-1 before them all): the top and
 * the bottom of the gap between it and the word after it, or of the space
 * just past it where its line ends, and the line it is on.
 */
function gapAfter(words: HandwrittenWord[], after: number): { top: Point; bottom: Point; piece: Piece } {
    if (after < 0) {
        const piece = pieceOf(words[0], words[0]);
        const back = scaled(piece.along, -piece.height * 0.25);
        return { top: add(piece.topLeft, back), bottom: add(piece.bottomLeft, back), piece };
    }
    const piece = pieceOf(words[after], words[after]);
    const next = words[after + 1];
    if (next && next.line === words[after].line) {
        return {
            top: lerp(piece.topRight, next.box[0], 0.5),
            bottom: lerp(piece.bottomRight, next.box[3], 0.5),
            piece,
        };
    }
    const on = scaled(piece.along, piece.height * 0.25);
    return { top: add(piece.topRight, on), bottom: add(piece.bottomRight, on), piece };
}

/** A caret ‸ in the gap after word `after`, pointing up at where something goes, and the top of it. */
function caret(words: HandwrittenWord[], after: number, color: string, random: () => number) {
    const { top, bottom, piece } = gapAfter(words, after);
    return caretAt(top, bottom, piece, color, random);
}

/** A caret ‸ at the place from `top` to `bottom` of the line of `piece`, and the top of it. */
function caretAt(top: Point, bottom: Point, piece: Piece, color: string, random: () => number) {
    const wide = piece.height * 0.18;
    const apex = lerp(top, bottom, 0.6);
    const foot = lerp(top, bottom, 1.05);
    const stroke = handStroke(
        "pen",
        color,
        penSize(piece.height),
        [add(foot, scaled(piece.along, -wide)), apex, add(foot, scaled(piece.along, wide))],
        random,
    );
    return { stroke, top, piece };
}

/**
 * Where letter `index` of `word` starts, as the top and the bottom of it
 * (the end of the word for its length): between the boxes of its letters,
 * if they were placed when it was read, or as far along it as so many of
 * its letters would be, were they all as wide, if they were not.
 */
function letterEdge(word: HandwrittenWord, index: number): { top: Point; bottom: Point } {
    const count = [...word.text.normalize("NFC")].length;
    const letters = word.letters;
    if (letters && letters.length === count && count > 0) {
        if (index <= 0) {
            return { top: letters[0].box[0], bottom: letters[0].box[3] };
        }
        if (index >= count) {
            return { top: letters[count - 1].box[1], bottom: letters[count - 1].box[2] };
        }
        const [before, after] = [letters[index - 1].box, letters[index].box];
        return { top: lerp(before[1], after[0], 0.5), bottom: lerp(before[2], after[3], 0.5) };
    }
    const piece = pieceOf(word, word);
    const across = count ? Math.min(Math.max(index / count, 0), 1) : 0;
    return { top: at(piece, across, 0), bottom: at(piece, across, 1) };
}

/** The letters of `word` from `from` up to `to` as a piece of its line. */
function lettersPiece(word: HandwrittenWord, from: number, to: number): Piece {
    const [start, end] = [letterEdge(word, from), letterEdge(word, to)];
    const whole = pieceOf(word, word);
    const height = (distance(start.top, start.bottom) + distance(end.top, end.bottom)) / 2;
    return {
        ...whole,
        topLeft: start.top,
        bottomLeft: start.bottom,
        topRight: end.top,
        bottomRight: end.bottom,
        height: height || whole.height,
    };
}

/**
 * The marks of `word` written as `text`, a word too: only the letters that
 * are wrong struck out, with the right ones over them, or a caret where
 * letters are missing; or null if most of it is wrong.
 */
function letterMarks(
    word: HandwrittenWord,
    text: string,
    words: HandwrittenWord[],
    ink: Stroke[],
    color: string,
    random: () => number,
): Stroke[] | null {
    const changed = changedLetters(word.text, text);
    if (!changed) {
        return null;
    }
    const old = [...word.text.normalize("NFC")];
    const next = [...text.normalize("NFC")];
    const [from, to] = [changed.start, old.length - changed.end];
    const written = next.slice(changed.start, next.length - changed.end).join("");
    if (from === to) {
        const { top, bottom } = letterEdge(word, from);
        const { stroke, top: over, piece } = caretAt(top, bottom, pieceOf(word, word), color, random);
        return [stroke, ...label(written, over, true, piece, words, ink, color, random)];
    }
    const piece = lettersPiece(word, from, to);
    const marks = [strike(piece, color, random)];
    if (written) {
        marks.push(...label(written, at(piece, 0.5, 0), true, piece, words, ink, color, random));
    }
    return marks;
}

/** An arc ‿ under the gap between two words, as joins them. */
function joinArcs(
    words: HandwrittenWord[],
    left: number,
    color: string,
    random: () => number,
): Stroke[] {
    const [a, b] = [words[left], words[left + 1]];
    const piece = pieceOf(a, b);
    const reach = piece.height * 0.2;
    const size = penSize(piece.height);
    if (a.line !== b.line) {
        // the line ends between them: a half of the arc after the one, and one before the other
        const end = pieceOf(a, a);
        const start = pieceOf(b, b);
        return [
            handStroke(
                "pen",
                color,
                size,
                ellipse(add(at(end, 1, 0.9), scaled(end.along, -reach)), end.along, reach, reach * 0.8, 0.25, 0),
                random,
            ),
            handStroke(
                "pen",
                color,
                size,
                ellipse(add(at(start, 0, 0.9), scaled(start.along, reach)), start.along, reach, reach * 0.8, 0.5, 0.25),
                random,
            ),
        ];
    }
    return [
        handStroke(
            "pen",
            color,
            size,
            ellipse(lerp(a.box[2], b.box[3], 0.5), piece.along, reach * 1.6, reach, 0.5, 0),
            random,
        ),
    ];
}

/** The words `text` is said to be, without the spaces between them. */
const unspaced = (text: string) => [...text.normalize("NFC")].filter((char) => char !== " ");

/**
 * The strokes that draw `correction` on the page `words` were read from,
 * whose `ink`, if it is given, says where there is room to write between
 * its lines, `seed` to draw it the same each time.
 */
export function correctionMarks(
    correction: Correction,
    words: HandwrittenWord[],
    ink: Stroke[] = [],
    seed = 1,
): Stroke[] {
    const random = seeded(seed);
    const span = "from_id" in correction ? piecesOfSpan(words, correction) : null;
    if ("from_id" in correction && !span) {
        return [];
    }
    const pieces = span ?? [];
    switch (correction.type) {
        case "misread":
            return [];
        case "replace": {
            // one word written as another: only the letters that are wrong, if they are few
            const word = words[correction.from_id];
            const letters = correction.from_id === correction.to_id && !/\s/.test(correction.text.trim())
                ? letterMarks(word, correction.text.trim(), words, ink, MARK_COLORS.error, random)
                : null;
            if (letters) {
                return letters;
            }
            return [
                ...pieces.map((piece) => strike(piece, MARK_COLORS.error, random)),
                ...writtenOver(pieces[0], words, ink, correction.text, MARK_COLORS.error, random),
            ];
        }
        case "erase":
            return pieces.map((piece) => strike(piece, MARK_COLORS.error, random));
        case "insert": {
            if (correction.after_id < -1 || correction.after_id >= words.length) {
                return [];
            }
            const { stroke, top, piece } = caret(words, correction.after_id, MARK_COLORS.error, random);
            return [stroke, ...label(correction.text, top, true, piece, words, ink, MARK_COLORS.error, random)];
        }
        case "move": {
            if (correction.after_id < -1 || correction.after_id >= words.length) {
                return [];
            }
            const loops = pieces.map((piece) => {
                const center = at(piece, 0.5, 0.5);
                const rx = distance(at(piece, 0, 0.5), at(piece, 1, 0.5)) / 2 + piece.height * 0.2;
                return handStroke(
                    "pen",
                    MARK_COLORS.error,
                    penSize(piece.height),
                    ellipse(center, piece.along, rx, piece.height * 0.62, 0.7, 1.75),
                    random,
                );
            });
            const { stroke, top, piece } = caret(words, correction.after_id, MARK_COLORS.error, random);
            const from = add(at(pieces[0], 0.5, 0), scaled(pieces[0].down, -pieces[0].height * 0.15));
            const to = add(top, scaled(piece.down, -piece.height * 0.05));
            const rise = Math.max(piece.height * 0.5, distance(from, to) * 0.25);
            const control = add(lerp(from, to, 0.5), scaled(piece.down, -rise));
            const curve: Point[] = [];
            for (let step = 0; step <= 16; step++) {
                const t = step / 16;
                curve.push(
                    add(add(scaled(from, (1 - t) * (1 - t)), scaled(control, 2 * t * (1 - t))), scaled(to, t * t)),
                );
            }
            // the head of the arrow, the way the curve comes in
            const last = curve[curve.length - 2];
            const length = distance(last, to) || 1;
            const back: Point = [(last[0] - to[0]) / length, (last[1] - to[1]) / length];
            const side: Point = [-back[1], back[0]];
            const head = piece.height * 0.18;
            const size = penSize(piece.height);
            return [
                ...loops,
                handStroke("pen", MARK_COLORS.error, size, curve, random),
                handStroke("pen", MARK_COLORS.error, size, [
                    add(to, add(scaled(back, head), scaled(side, head * 0.6))),
                    to,
                    add(to, add(scaled(back, head), scaled(side, -head * 0.6))),
                ], random),
                stroke,
            ];
        }
        case "join": {
            const joined = words.slice(correction.from_id, correction.to_id + 1).map((word) => word.text).join("");
            const same = joined === correction.text;
            const arcs: Stroke[] = [];
            for (let left = correction.from_id; left < correction.to_id; left++) {
                arcs.push(...joinArcs(words, left, MARK_COLORS.error, random));
            }
            // what is not only the words put together is written over them
            return same
                ? arcs
                : [...arcs, ...writtenOver(pieces[0], words, ink, correction.text, MARK_COLORS.error, random)];
        }
        case "split": {
            const word = words[correction.id];
            if (!word) {
                return [];
            }
            const piece = pieceOf(word, word);
            const marks: Stroke[] = [];
            let before = 0;
            for (const char of correction.text.normalize("NFC")) {
                if (char === " ") {
                    // the space goes after as many letters as are before it, where they end on the page
                    const { top, bottom } = letterEdge(word, before);
                    const reach = scaled(piece.down, piece.height * 0.1);
                    marks.push(
                        handStroke("pen", MARK_COLORS.error, penSize(piece.height), [
                            add(top, scaled(reach, -1)),
                            add(bottom, reach),
                        ], random),
                    );
                } else {
                    before += 1;
                }
            }
            const same = unspaced(word.text).join("") === unspaced(correction.text).join("");
            return same
                ? marks
                : [...marks, ...writtenOver(piece, words, ink, correction.text, MARK_COLORS.error, random)];
        }
        case "suggest":
            return [
                ...pieces.map((piece) => underline(piece, MARK_COLORS.suggestion, random)),
                ...writtenOver(pieces[0], words, ink, correction.text, MARK_COLORS.suggestion, random),
            ];
        case "comment":
            return pieces.map((piece) => highlight(piece, MARK_COLORS.comment, random));
        case "praise": {
            const last = pieces[pieces.length - 1];
            const h = last.height;
            const start = add(last.topRight, add(scaled(last.along, h * 0.2), scaled(last.down, h * 0.3)));
            const tick = handStroke("pen", MARK_COLORS.praise, penSize(h), [
                start,
                add(start, add(scaled(last.along, h * 0.15), scaled(last.down, h * 0.3))),
                add(start, add(scaled(last.along, h * 0.55), scaled(last.down, -h * 0.35))),
            ], random);
            return [...pieces.map((piece) => underline(piece, MARK_COLORS.praise, random)), tick];
        }
        case "illegible":
            return pieces.map((piece) => highlight(piece, MARK_COLORS.unclear, random));
    }
}

/** A stroke of highlighter over `piece`, a little past both its ends. */
function highlight(piece: Piece, color: string, random: () => number): Stroke {
    const over = piece.height * 0.05;
    return handStroke(
        "highlighter",
        color,
        piece.height * 0.2,
        [add(at(piece, 0, 0.55), scaled(piece.along, -over)), add(at(piece, 1, 0.55), scaled(piece.along, over))],
        random,
        0.2,
    );
}

/** The pieces of the span of a correction, or null if it names words there are not. */
function piecesOfSpan(words: HandwrittenWord[], span: { from_id: number; to_id: number }): Piece[] | null {
    const { from_id: from, to_id: to } = span;
    if (!Number.isInteger(from) || !Number.isInteger(to) || from < 0 || to < from || to >= words.length) {
        return null;
    }
    return piecesOf(words, from, to);
}

/**
 * The boxes of the words `correction` is about on the page `words` were read
 * from, which point it out: for an insertion, the words it goes between.
 */
export function correctionArea(correction: Correction, words: HandwrittenWord[]): [number, number][][] {
    const ids = correction.type === "misread"
        ? []
        : correction.type === "insert"
        ? [correction.after_id, correction.after_id + 1]
        : correction.type === "split"
        ? [correction.id]
        : Array.from({ length: correction.to_id - correction.from_id + 1 }, (_, at) => correction.from_id + at);
    return ids.filter((id) => id >= 0 && id < words.length).map((id) => words[id].box);
}

/** The strokes that draw all of `corrections` on the page `words` were read from, and `ink` written on. */
export function marksOf(corrections: Correction[], words: HandwrittenWord[], ink: Stroke[] = []): Stroke[] {
    return corrections.flatMap((correction, index) => correctionMarks(correction, words, ink, index + 1));
}
