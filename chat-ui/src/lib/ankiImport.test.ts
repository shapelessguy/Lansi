// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, it } from "vitest";

import { importBusy, type ImportStatus } from "./ankiImport";

describe("importBusy", () => {
    const status = (state: ImportStatus["state"], remaining: number | null): ImportStatus => ({
        state,
        remaining,
        taken: 0,
        message: "",
    });

    it("is busy while words are taken in, or wait to be", () => {
        expect(importBusy(status("importing", null))).toBe(true);
        expect(importBusy(status("waiting", 4))).toBe(true);
    });

    it("is idle once nothing is left, or nothing can be taken in", () => {
        expect(importBusy(status("waiting", 0))).toBe(false);
        expect(importBusy(status("waiting", null))).toBe(false);
        expect(importBusy(status("no-key", 4))).toBe(false);
        expect(importBusy(status("off", 4))).toBe(false);
        expect(importBusy(status("unavailable", 4))).toBe(false);
    });
});
