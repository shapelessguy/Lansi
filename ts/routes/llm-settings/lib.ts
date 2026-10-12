// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ConnectionProfileConfig } from "@tslib/llm";
import { nextId } from "@tslib/llm";

export const DEFAULT_ENDPOINT = "https://api.openai.com/v1/chat/completions";

/** A synced connection profile joined with this device's token for it. */
export interface ConnectionProfile extends ConnectionProfileConfig {
    apiToken: string;
}

/** The add/edit form's state. `id` is null while creating a new profile. */
export interface ProfileDraft {
    id: number | null;
    apiEndpoint: string;
    apiToken: string;
    modelName: string;
    // null while the number input is empty
    inputPerMillion: number | null;
    outputPerMillion: number | null;
}

export function withTokens(configs: ConnectionProfileConfig[], tokens: Record<string, string>): ConnectionProfile[] {
    return configs.map((config) => ({ ...config, apiToken: tokens[config.id] ?? "" }));
}

/** Only the very first profile is pre-filled with a default endpoint. */
export function newDraft(profiles: ConnectionProfile[]): ProfileDraft {
    return {
        id: null,
        apiEndpoint: profiles.length ? "" : DEFAULT_ENDPOINT,
        apiToken: "",
        modelName: "",
        inputPerMillion: 0,
        outputPerMillion: 0,
    };
}

export function draftFromProfile(profile: ConnectionProfile): ProfileDraft {
    return {
        id: profile.id,
        apiEndpoint: profile.apiEndpoint,
        apiToken: profile.apiToken,
        modelName: profile.modelName,
        inputPerMillion: profile.pricing.inputPerMillion,
        outputPerMillion: profile.pricing.outputPerMillion,
    };
}

function sanitizeCost(cost: number | null): number {
    return cost !== null && Number.isFinite(cost) && cost > 0 ? cost : 0;
}

/** Adds the drafted profile, or replaces the one being edited. */
export function applyDraft(
    profiles: ConnectionProfile[],
    draft: ProfileDraft,
): { profiles: ConnectionProfile[]; saved: ConnectionProfile } {
    const saved: ConnectionProfile = {
        id: draft.id ?? nextId(profiles),
        apiEndpoint: draft.apiEndpoint.trim(),
        apiToken: draft.apiToken.trim(),
        modelName: draft.modelName.trim(),
        pricing: {
            inputPerMillion: sanitizeCost(draft.inputPerMillion),
            outputPerMillion: sanitizeCost(draft.outputPerMillion),
        },
    };
    const exists = profiles.some((p) => p.id === saved.id);
    return {
        profiles: exists ? profiles.map((p) => (p.id === saved.id ? saved : p)) : [...profiles, saved],
        saved,
    };
}

export function toConfig(profile: ConnectionProfile): ConnectionProfileConfig {
    return {
        id: profile.id,
        apiEndpoint: profile.apiEndpoint,
        modelName: profile.modelName,
        pricing: profile.pricing,
    };
}
