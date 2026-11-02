// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { afterEach, describe, expect, it, vi } from "vitest";
import { closeOnBack, goBack } from "./back";

describe("goBack", () => {
    const opened: (() => void)[] = [];
    const open = (...args: Parameters<typeof closeOnBack>) => opened.push(closeOnBack(...args));
    afterEach(() => opened.splice(0).forEach((forget) => forget()));

    it("closes nothing and says so when nothing is open", () => {
        expect(goBack()).toBe(false);
    });

    it("closes what was opened last when it is on the same layer", () => {
        const first = vi.fn();
        const second = vi.fn();
        open("window", first);
        open("window", second);
        expect(goBack()).toBe(true);
        expect(second).toHaveBeenCalledOnce();
        expect(first).not.toHaveBeenCalled();
    });

    it("closes a dialog before what it was opened over even when that was opened after it", () => {
        const dialog = vi.fn();
        const cover = vi.fn();
        const panel = vi.fn();
        open("dialog", dialog);
        open("panel", panel);
        open("cover", cover);
        goBack();
        expect(dialog).toHaveBeenCalledOnce();
        expect(cover).not.toHaveBeenCalled();
        expect(panel).not.toHaveBeenCalled();
    });

    it("leaves alone what was closed otherwise", () => {
        const kept = vi.fn();
        const closed = vi.fn();
        open("panel", kept);
        closeOnBack("cover", closed)();
        goBack();
        expect(closed).not.toHaveBeenCalled();
        expect(kept).toHaveBeenCalledOnce();
    });
});
