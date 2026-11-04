// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { afterEach, describe, expect, it, vi } from "vitest";

import { forgetIcon, iconOf, matchesTopic } from "./topics";

describe("matchesTopic", () => {
    const doctor = { title: "At the doctor", description: "symptoms, appointments and medicine" };

    it("finds a topic by any word of its title or of what it is about, whatever the capitals", () => {
        expect(matchesTopic(doctor, "Doctor")).toBe(true);
        expect(matchesTopic(doctor, "medic")).toBe(true);
        expect(matchesTopic(doctor, "doctor symptoms")).toBe(true);
    });

    it("leaves out a topic that lacks one of the words, and finds every topic for nothing", () => {
        expect(matchesTopic(doctor, "doctor train")).toBe(false);
        expect(matchesTopic(doctor, "")).toBe(true);
    });
});

describe("iconOf", () => {
    afterEach(() => vi.unstubAllGlobals());

    function asked(): RequestInit[] {
        const inits: RequestInit[] = [];
        vi.stubGlobal("fetch", (_: string, init: RequestInit) => {
            inits.push(init);
            return Promise.resolve(new Response(new Blob(["png"])));
        });
        vi.stubGlobal("URL", { createObjectURL: () => "blob:icon" });
        return inits;
    }

    it("fetches an icon once, as the browser keeps it", async () => {
        const inits = asked();

        await iconOf("kept");
        await iconOf("kept");

        expect(inits).toHaveLength(1);
        expect(inits[0].cache).toBeUndefined();
    });

    it("fetches an icon made again past the one the browser keeps", async () => {
        const inits = asked();
        await iconOf("remade");

        forgetIcon("remade");
        await iconOf("remade");
        forgetIcon("remade");
        await iconOf("remade");

        expect(inits.map((init) => init.cache)).toEqual([undefined, "reload", "reload"]);
    });
});
