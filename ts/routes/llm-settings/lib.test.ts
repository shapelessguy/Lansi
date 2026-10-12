// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test, vi } from "vitest";

// the generated backend module is not available to unit tests
vi.mock("@generated/backend", () => ({}));

import type { ConnectionProfile } from "./lib";
import { applyDraft, DEFAULT_ENDPOINT, draftFromProfile, newDraft, toConfig, withTokens } from "./lib";

function profile(overrides: Partial<ConnectionProfile>): ConnectionProfile {
    return {
        id: 1,
        apiEndpoint: "https://example.test/v1",
        apiToken: "secret",
        modelName: "model",
        pricing: { inputPerMillion: 1, outputPerMillion: 2 },
        ...overrides,
    };
}

test("synced profiles are joined with this device's tokens", () => {
    const { apiToken: _, ...config } = profile({ id: 7 });
    const { apiToken: __, ...other } = profile({ id: 8 });

    const profiles = withTokens([config, other], { "7": "secret" });

    expect(profiles.map((p) => p.apiToken)).toEqual(["secret", ""]);
});

test("first profile is pre-filled with the default endpoint", () => {
    expect(newDraft([]).apiEndpoint).toBe(DEFAULT_ENDPOINT);
});

test("later profiles start with a blank endpoint", () => {
    expect(newDraft([profile({})]).apiEndpoint).toBe("");
});

test("saving a new draft appends a profile with the next free id", () => {
    const existing = [profile({ id: 3 })];
    const draft = { ...newDraft(existing), apiEndpoint: " https://other.test ", apiToken: " key ", modelName: " m " };

    const { profiles, saved } = applyDraft(existing, draft);

    expect(saved).toEqual({
        id: 4,
        apiEndpoint: "https://other.test",
        apiToken: "key",
        modelName: "m",
        pricing: { inputPerMillion: 0, outputPerMillion: 0 },
    });
    expect(profiles).toEqual([existing[0], saved]);
});

test("saving an edited draft replaces the profile in place", () => {
    const first = profile({ id: 1 });
    const second = profile({ id: 2 });
    const draft = { ...draftFromProfile(first), modelName: "renamed" };

    const { profiles } = applyDraft([first, second], draft);

    expect(profiles).toEqual([{ ...first, modelName: "renamed" }, second]);
});

test.each([null, -5, Number.NaN])("a cost of %s is saved as zero", (cost) => {
    const draft = { ...newDraft([]), inputPerMillion: cost, outputPerMillion: 1.5 };

    expect(applyDraft([], draft).saved.pricing).toEqual({ inputPerMillion: 0, outputPerMillion: 1.5 });
});

test("the synced form of a profile leaves out its token", () => {
    expect(toConfig(profile({}))).not.toHaveProperty("apiToken");
});
