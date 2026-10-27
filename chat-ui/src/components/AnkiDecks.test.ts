// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { fieldParts } from "./AnkiDecks";

test("a field shows its text, with the sounds and the pictures it names apart", () => {
    const field = `<img src="hund%20bild.png"> der <b>Hund</b> [sound:hund.mp3]<img src='b.jpg' alt="">`;

    expect(fieldParts(field)).toEqual({
        text: "der Hund",
        sounds: ["hund.mp3"],
        pictures: ["hund bild.png", "b.jpg"],
    });
    expect(fieldParts("plain")).toEqual({ text: "plain", sounds: [], pictures: [] });
});
