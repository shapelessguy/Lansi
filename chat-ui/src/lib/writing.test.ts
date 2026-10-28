// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { onOpenRouter } from "./models";
import { askedOf, type Box, checkedBox, mirrorStyle, type Profiling, worthSending } from "./writing";

/** An element called `tagName`, with its attributes, in `parent`. */
function element(parent: Box | null, tagName = "DIV", attributes: Record<string, string> = {}): Box {
    return { parentNode: parent, tagName, getAttribute: (name) => attributes[name] ?? null };
}

/** The shadow root of `host`. */
function shadowOf(host: Box): Box {
    return { parentNode: null, host };
}

const page = element(null);
const chat = element(page, "DIV", { "data-writing": "" });
const exercise = element(page, "DIV", { "data-writing": "" });
const card = element(element(shadowOf(exercise)));

test("a text box in a place marked for writing is checked", () => {
    const box = element(chat, "TEXTAREA");
    expect(checkedBox([box, chat, page])).toBe(box);
});

test("a text box in the shadow root of an exercise is checked as the exercise is marked for writing", () => {
    const box = element(card, "TEXTAREA");
    expect(checkedBox([box, card])).toBe(box);
});

test("a text box marked to be left out is not checked", () => {
    expect(checkedBox([element(card, "TEXTAREA", { "data-no-check": "" })])).toBeNull();
});

test("a box of one line, such as a gap to fill in, is not checked", () => {
    expect(checkedBox([element(card, "INPUT")])).toBeNull();
});

test("a text box outside every place marked for writing is not checked", () => {
    expect(checkedBox([element(element(page), "TEXTAREA")])).toBeNull();
    expect(checkedBox([])).toBeNull();
});

const profiling: Profiling = {
    apiKey: "key",
    model: onOpenRouter("some/model"),
    questions: {},
    rateWords: false,
    correctWith: null,
    into: "English",
};

test("a text box is checked again when its text, its caret or what is asked about it changes", () => {
    const sent = { text: "Hallo", caret: 5, asked: askedOf("German", null) };
    expect(worthSending(sent, { ...sent }, false)).toBe(false);
    expect(worthSending(sent, { ...sent, text: "Hallo!" }, false)).toBe(true);
    expect(worthSending(sent, { ...sent, caret: 2 }, false)).toBe(true);
    expect(worthSending(sent, { ...sent, asked: askedOf("German", profiling) }, false)).toBe(true);
    expect(worthSending(sent, { ...sent, asked: askedOf("French", null) }, false)).toBe(true);
});

test("a text box is checked again while requests to the model are still out", () => {
    const sent = { text: "Hallo", caret: 5, asked: askedOf("German", profiling) };
    expect(worthSending(sent, { ...sent }, true)).toBe(true);
});

test("an empty text box is not checked again when only its caret moves", () => {
    const sent = { text: "", caret: null, asked: askedOf("German", null) };
    expect(worthSending(sent, { ...sent, caret: 0 }, false)).toBe(false);
});

test("the copy behind a text box lays out its text as the box does, see-through, with room for its scroll bar", () => {
    const style = new Proxy({} as CSSStyleDeclaration, {
        get: (_, name) => (name === "paddingRight" ? "12px" : name === "fontSize" ? "15px" : ""),
    });
    const copied = mirrorStyle(style, "rgb(1, 2, 3)", 8);
    expect(copied.fontSize).toBe("15px");
    expect(copied.paddingRight).toBe("calc(12px + 8px)");
    expect(copied.backgroundColor).toBe("rgb(1, 2, 3)");
    expect([copied.color, copied.borderColor, copied.pointerEvents]).toEqual(["transparent", "transparent", "none"]);
});

test("a text box is checked again when its corrections are to be translated into another language", () => {
    expect(askedOf("German", { ...profiling, into: "Italian" })).not.toBe(askedOf("German", profiling));
});
