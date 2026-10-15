// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { afterEach, describe, expect, it } from "vitest";
import { newId } from "./ids";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

describe("newId", () => {
    // shadows the method of Crypto.prototype until it is deleted again
    afterEach(() => Reflect.deleteProperty(crypto, "randomUUID"));

    it("is a UUID", () => {
        expect(newId()).toMatch(uuid);
    });

    it("is still a UUID, and a new one each time, when the page is not a secure context", () => {
        Object.defineProperty(crypto, "randomUUID", { value: undefined, configurable: true });
        const ids = new Set([newId(), newId(), newId()]);
        expect(ids.size).toBe(3);
        for (const id of ids) {
            expect(id).toMatch(uuid);
        }
    });
});
