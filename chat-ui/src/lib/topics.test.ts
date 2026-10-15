// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, it } from "vitest";

import { matchesTopic } from "./topics";

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
