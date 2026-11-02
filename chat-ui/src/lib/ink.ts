// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { getStroke } from "perfect-freehand";

/**
 * The ink of a page of a text written by hand, as checker/ink.py keeps it:
 * strokes placed in units of the page, whatever size it is shown at, each
 * point with how hard the pen was pressed, from 0 to 1.
 */

export const PENS = ["pen", "fountain", "pencil", "highlighter"] as const;
export type Pen = (typeof PENS)[number];

export interface Stroke {
    pen: Pen;
    /** As #rrggbb. */
    color: string;
    size: number;
    points: [number, number, number][];
}

/** The thinnest and the thickest a pen can be set to, as the server takes them. */
export const MIN_SIZE = 1;
export const MAX_SIZE = 40;

/** How hard a mouse presses, which cannot say. */
export const MOUSE_PRESSURE = 0.5;

/**
 * How wide `pen`, set to `size`, draws at `pressure`, as checker/ink.py has
 * it: a pen a little wider the harder it is pressed, a fountain pen much
 * wider, a pencil thinner, and a highlighter as wide whatever the pressure.
 */
export function strokeWidth(pen: Pen, size: number, pressure: number): number {
    switch (pen) {
        case "fountain":
            return size * (0.3 + 1.4 * pressure);
        case "pencil":
            return size * 0.6 * (0.8 + 0.4 * pressure);
        case "highlighter":
            return size * 3;
        default:
            return size * (0.75 + 0.5 * pressure);
    }
}

/**
 * How each pen draws: how much thinner it is where it is pressed lightly,
 * from 0 for not at all to 1, and how see-through it is.
 */
const PEN_DRAWING: Record<Pen, { thinning: number; alpha: number }> = {
    pen: { thinning: 0.25, alpha: 1 },
    fountain: { thinning: 0.7, alpha: 1 },
    pencil: { thinning: 0.15, alpha: 0.8 },
    highlighter: { thinning: 0, alpha: 0.35 },
};

/**
 * The outline of a stroke, as one shape: the points it went through
 * smoothed, so that the shaking of the hand and of the pointer does not
 * show, and as wide at each as the pen was pressed there.
 */
export function outline(stroke: Stroke, last = true): number[][] {
    return getStroke(stroke.points, {
        size: strokeWidth(stroke.pen, stroke.size, 0.5),
        thinning: PEN_DRAWING[stroke.pen].thinning,
        smoothing: 0.5,
        streamline: 0.2,
        simulatePressure: false,
        last,
    });
}

/** How far apart, in units of the page, the points a stroke is drawn through are at the least. */
const MIN_STEP = 0.5;

/**
 * The points of a stroke with the shaking of the hand and of the pointer
 * taken out: those nearer the one before than `MIN_STEP` left out, and each
 * moved toward the one before it, by `streamline`.
 */
export function smoothed(points: Stroke["points"], streamline = 0.15): Stroke["points"] {
    const out: Stroke["points"] = [points[0]];
    let last = points[0];
    for (const [x, y, pressure] of points.slice(1)) {
        // a stylus tells many points a hair apart, whose wobble would show
        if (Math.hypot(x - last[0], y - last[1]) < MIN_STEP) {
            continue;
        }
        last = [x, y, pressure];
        const [px, py] = out[out.length - 1];
        out.push([px + (x - px) * (1 - streamline), py + (y - py) * (1 - streamline), pressure]);
    }
    // it ends where it was lifted
    if (points.length > 1) {
        out.push(points[points.length - 1]);
    }
    return out;
}

/**
 * Draws a stroke on a canvas whose units are those of the page, `last` once
 * it is finished. A fountain pen, whose width follows the pressure all
 * along, is filled as the shape of its outline; every other pen is one line,
 * smoothed, with round ends and joins, so that a sharp turn stays clean.
 */
export function drawStroke(context: CanvasRenderingContext2D, stroke: Stroke, last = true) {
    context.save();
    context.fillStyle = stroke.color;
    context.strokeStyle = stroke.color;
    context.globalAlpha = PEN_DRAWING[stroke.pen].alpha;
    if (stroke.pen === "highlighter") {
        context.globalCompositeOperation = "multiply";
    }
    context.beginPath();
    if (stroke.pen === "fountain") {
        const shape = outline(stroke, last);
        if (shape.length > 1) {
            // curved through the middle of each side of the outline
            context.moveTo(shape[0][0], shape[0][1]);
            for (let at = 0; at < shape.length; at++) {
                const [x0, y0] = shape[at];
                const [x1, y1] = shape[(at + 1) % shape.length];
                context.quadraticCurveTo(x0, y0, (x0 + x1) / 2, (y0 + y1) / 2);
            }
            context.closePath();
            context.fill();
        }
        context.restore();
        return;
    }
    const points = smoothed(stroke.points);
    if (stroke.pen === "highlighter") {
        fillChisel(context, points, strokeWidth(stroke.pen, stroke.size, 1));
        context.restore();
        return;
    }
    const pressure = stroke.points.reduce((sum, point) => sum + point[2], 0) / stroke.points.length;
    context.lineWidth = strokeWidth(stroke.pen, stroke.size, pressure);
    if (stroke.pen === "pencil") {
        drawPencil(context, stroke, points);
        context.restore();
        return;
    }
    context.lineCap = "round";
    context.lineJoin = "round";
    context.moveTo(points[0][0], points[0][1]);
    if (points.length === 1) {
        context.lineTo(points[0][0] + 0.01, points[0][1]);
    }
    for (let at = 1; at < points.length - 1; at++) {
        const [x, y] = points[at];
        const [nx, ny] = points[at + 1];
        context.quadraticCurveTo(x, y, (x + nx) / 2, (y + ny) / 2);
    }
    if (points.length > 1) {
        const [x, y] = points[points.length - 1];
        context.lineTo(x, y);
    }
    context.stroke();
    context.restore();
}

const GRAIN_SIZE = 96;
const grains = new Map<string, HTMLCanvasElement>();
// the pattern of each colour on each canvas, made once
const patterns = new WeakMap<CanvasRenderingContext2D, Map<string, CanvasPattern>>();

/**
 * A pattern of `color` with the grain of paper in it, each pixel of the
 * screen covered by it or not as graphite catches on paper or skips it,
 * its pixels those of the screen whatever the page is drawn at, and moved
 * as `piece` says.
 */
function grain(context: CanvasRenderingContext2D, color: string, piece: number): CanvasPattern | string {
    let tile = grains.get(color);
    if (!tile) {
        tile = document.createElement("canvas");
        tile.width = GRAIN_SIZE;
        tile.height = GRAIN_SIZE;
        const drawn = tile.getContext("2d");
        if (!drawn) {
            return color;
        }
        const pixels = drawn.createImageData(GRAIN_SIZE, GRAIN_SIZE);
        const [red, green, blue] = [1, 3, 5].map((at) => parseInt(color.slice(at, at + 2), 16));
        for (let at = 0; at < pixels.data.length; at += 4) {
            const caught = Math.random();
            pixels.data[at] = red;
            pixels.data[at + 1] = green;
            pixels.data[at + 2] = blue;
            pixels.data[at + 3] = caught < 0.3 ? caught * 200 : 150 + caught * 105;
        }
        drawn.putImageData(pixels, 0, 0);
        grains.set(color, tile);
    }
    let made = patterns.get(context);
    if (!made) {
        made = new Map();
        patterns.set(context, made);
    }
    let pattern = made.get(color);
    if (!pattern) {
        pattern = context.createPattern(tile, "repeat") ?? undefined;
        if (!pattern) {
            return color;
        }
        made.set(color, pattern);
    }
    // moved by as much as a piece of the stroke says, the same each time it is drawn
    pattern.setTransform(
        context.getTransform().inverse().translate((piece * 37) % GRAIN_SIZE, (piece * 61) % GRAIN_SIZE),
    );
    return pattern;
}

/** How many points of a pencil's stroke are drawn as one piece. */
const PENCIL_PIECE = 8;

/**
 * Draws the stroke of a pencil as graphite goes on paper: thin, broken by
 * the grain, and as dark at each place as it was pressed there. It is drawn
 * a few points at a time, the pieces meeting end to end, so that where the
 * pencil goes over what it drew it adds to it, each piece with the grain
 * moved, so that it fills what the grain left out before.
 */
function drawPencil(context: CanvasRenderingContext2D, stroke: Stroke, points: Stroke["points"]) {
    const color = stroke.color;
    const width = (pressure: number) => strokeWidth(stroke.pen, stroke.size, pressure) * 0.7;
    const shade = (pressure: number) => 0.45 + 0.5 * pressure;
    const mid = (a: Stroke["points"][number], b: Stroke["points"][number]): [number, number] => [
        (a[0] + b[0]) / 2,
        (a[1] + b[1]) / 2,
    ];
    context.lineCap = "butt";
    context.lineJoin = "round";
    // its two ends, round
    for (const end of points.length > 1 ? [points[0], points[points.length - 1]] : [points[0]]) {
        context.beginPath();
        context.globalAlpha = shade(end[2]);
        context.fillStyle = grain(context, color, 0);
        context.arc(end[0], end[1], width(end[2]) / 2, 0, 2 * Math.PI);
        context.fill();
    }
    if (points.length < 2) {
        return;
    }
    // where each piece starts: the first point, then the middle between two, as the curve passes there
    let from: [number, number] = [points[0][0], points[0][1]];
    for (let start = 1, piece = 0; start < points.length; start += PENCIL_PIECE, piece++) {
        const until = Math.min(start + PENCIL_PIECE, points.length);
        const pressure = points.slice(start - 1, until).reduce((sum, point) => sum + point[2], 0) / (until - start + 1);
        context.beginPath();
        context.lineWidth = width(pressure);
        context.globalAlpha = shade(pressure);
        context.strokeStyle = grain(context, color, piece);
        context.moveTo(from[0], from[1]);
        for (let at = start; at < until; at++) {
            if (at === points.length - 1) {
                context.lineTo(points[at][0], points[at][1]);
                from = [points[at][0], points[at][1]];
            } else {
                const to = mid(points[at], points[at + 1]);
                context.quadraticCurveTo(points[at][0], points[at][1], to[0], to[1]);
                from = to;
            }
        }
        context.stroke();
    }
}

/**
 * Fills the shape a highlighter makes along `points`: its nib a flat bar,
 * upright, `height` high and a quarter of it wide, so that the stroke is cut
 * straight where it starts and ends. Each step is the hull of the nib where
 * it starts and where it ends, all of them filled at once, so that where
 * they overlap is not coloured twice.
 */
function fillChisel(context: CanvasRenderingContext2D, points: Stroke["points"], height: number) {
    const halfHigh = height / 2;
    const halfWide = height / 8;
    const nib = ([x, y]: Stroke["points"][number]): [number, number][] => [
        [x - halfWide, y - halfHigh],
        [x + halfWide, y - halfHigh],
        [x + halfWide, y + halfHigh],
        [x - halfWide, y + halfHigh],
    ];
    const steps = points.length > 1 ? points.slice(1).map((point, at) => [points[at], point]) : [[points[0]]];
    for (const step of steps) {
        const hull = convexHull(step.flatMap(nib));
        context.moveTo(hull[0][0], hull[0][1]);
        hull.slice(1).forEach(([x, y]) => context.lineTo(x, y));
        context.closePath();
    }
    context.fill("nonzero");
}

/** The convex hull of some points, all turning the same way, as a filled path needs them to add up rather than cancel out. */
function convexHull(points: [number, number][]): [number, number][] {
    const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    const cross = (o: [number, number], a: [number, number], b: [number, number]) =>
        (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const half = (from: [number, number][]) => {
        const kept: [number, number][] = [];
        for (const point of from) {
            while (kept.length >= 2 && cross(kept[kept.length - 2], kept[kept.length - 1], point) <= 0) {
                kept.pop();
            }
            kept.push(point);
        }
        kept.pop();
        return kept;
    };
    return [...half(sorted), ...half([...sorted].reverse())];
}

/** Whether a stroke passes within `reach` of a point, as an eraser rubbing there takes it away. */
export function touches(stroke: Stroke, x: number, y: number, reach: number): boolean {
    const near = reach + strokeWidth(stroke.pen, stroke.size, 1) / 2;
    const { points } = stroke;
    for (let at = 0; at < points.length; at++) {
        const [ax, ay] = points[at];
        const [bx, by] = points[Math.min(at + 1, points.length - 1)];
        const dx = bx - ax;
        const dy = by - ay;
        const length = dx * dx + dy * dy;
        const along = length ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / length)) : 0;
        if (Math.hypot(ax + along * dx - x, ay + along * dy - y) <= near) {
            return true;
        }
    }
    return false;
}

/** A point as it is kept: to a tenth of a unit, which is finer than any pen. */
export function keptPoint(x: number, y: number, pressure: number): [number, number, number] {
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10, Math.round(pressure * 100) / 100];
}

/** What pen the learner writes with, kept in this browser between texts. */
export interface PenChoice {
    pen: Pen;
    color: string;
    size: number;
}

const PEN_STORAGE_KEY = "chat-ui.pen";

export const DEFAULT_PEN: PenChoice = { pen: "pen", color: "#1a1a1a", size: 3 };

export function loadPen(): PenChoice {
    try {
        const kept = JSON.parse(localStorage.getItem(PEN_STORAGE_KEY) ?? "null") as Partial<PenChoice> | null;
        return {
            pen: PENS.find((pen) => pen === kept?.pen) ?? DEFAULT_PEN.pen,
            color: typeof kept?.color === "string" && /^#[0-9a-f]{6}$/i.test(kept.color)
                ? kept.color
                : DEFAULT_PEN.color,
            size: typeof kept?.size === "number" && kept.size >= MIN_SIZE && kept.size <= MAX_SIZE
                ? kept.size
                : DEFAULT_PEN.size,
        };
    } catch {
        return DEFAULT_PEN;
    }
}

export function savePen(choice: PenChoice) {
    try {
        localStorage.setItem(PEN_STORAGE_KEY, JSON.stringify(choice));
    } catch {
        // storage can be unavailable in private windows; the pen then lasts for the session
    }
}
