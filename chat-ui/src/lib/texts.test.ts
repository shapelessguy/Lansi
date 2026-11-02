// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import type { Stroke } from "./ink";
import { inkJson } from "./texts";

test("the ink of a page is kept as the JSON of it, however often it is made", () => {
    const one: Stroke = { pen: "pen", color: "#000000", size: 2, points: [[1, 2, 0.5]] };
    const two: Stroke = { pen: "pencil", color: "#c62828", size: 3, points: [[3, 4, 0.2], [5, 6, 0.9]] };

    expect(JSON.parse(inkJson([one]))).toEqual({ ink: [one] });
    expect(JSON.parse(inkJson([one, two]))).toEqual({ ink: [one, two] });
    expect(JSON.parse(inkJson([]))).toEqual({ ink: [] });
});
