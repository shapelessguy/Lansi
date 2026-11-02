// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { keptPoint, smoothed, type Stroke, strokeWidth, touches } from "./ink";

const line: Stroke = { pen: "pen", color: "#000000", size: 2, points: [[0, 0, 0.5], [100, 0, 0.5]] };

test("a fountain pen is wider the harder it is pressed, and a highlighter is not", () => {
    expect(strokeWidth("fountain", 4, 1)).toBeGreaterThan(2 * strokeWidth("fountain", 4, 0.2));
    expect(strokeWidth("highlighter", 4, 1)).toBe(strokeWidth("highlighter", 4, 0));
});

test("an eraser takes a stroke it rubs near, and not one far from it", () => {
    expect(touches(line, 50, 4, 3)).toBe(true);
    expect(touches(line, 50, 40, 3)).toBe(false);
    expect(touches({ ...line, points: [[10, 10, 0.5]] }, 12, 10, 3)).toBe(true);
});

test("a point is kept to a tenth of a unit", () => {
    expect(keptPoint(1.234, 5.678, 0.4567)).toEqual([1.2, 5.7, 0.46]);
});

test("a stroke is smoothed, but starts and ends where it was written", () => {
    const shaken = smoothed([[0, 0, 0.5], [10, 4, 0.5], [20, -4, 0.5], [30, 0, 0.5]]);

    expect(shaken[0]).toEqual([0, 0, 0.5]);
    expect(shaken[shaken.length - 1]).toEqual([30, 0, 0.5]);
    expect(Math.abs(shaken[2][1])).toBeLessThan(4);
});
