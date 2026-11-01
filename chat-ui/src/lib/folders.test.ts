// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { normalizeOpenFolders } from "./folders";

test("the open folders are the ids that were stored", () => {
    expect(normalizeOpenFolders([3, 7])).toEqual(new Set([3, 7]));
});

test("every folder is shut when nothing, or nothing of the right kind, was stored", () => {
    expect(normalizeOpenFolders(null)).toEqual(new Set());
    expect(normalizeOpenFolders({ 3: true })).toEqual(new Set());
    expect(normalizeOpenFolders([3, "7", 1.5])).toEqual(new Set([3]));
});
