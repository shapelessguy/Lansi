// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { answer, ask, type Dialog, onDialog, tell } from "./dialogs";

test("a dialog asked resolves with whether the learner agreed, and the next waits its turn", async () => {
    const shown: (string | null)[] = [];
    const stop = onDialog((dialog: Dialog | null) => shown.push(dialog?.message ?? null));

    const first = ask("Delete “Notes”?");
    const second = tell("The exercise could not be done again.", "down");
    answer(true);
    answer(false);
    stop();

    expect(await first).toBe(true);
    await expect(second).resolves.toBeUndefined();
    expect(shown).toEqual([null, "Delete “Notes”?", "The exercise could not be done again.", null]);
});

test("a dialog that only tells something has a single button that is not of removing", () => {
    let told: Dialog | null = null;
    const stop = onDialog((dialog) => (told ??= dialog));

    void tell("Saved.");
    answer(true);
    stop();

    expect(told).toEqual({ message: "Saved.", detail: undefined, confirm: "OK", cancel: null, danger: false });
});
