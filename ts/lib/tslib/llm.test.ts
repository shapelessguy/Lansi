// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test, vi } from "vitest";

// the storage functions aren't exercised here, and the generated backend
// module is not available to unit tests
vi.mock("@generated/backend", () => ({}));

import type { ExerciseConfig, ReviewHistoryEntry } from "./llm";
import {
    currentDayCode,
    MAX_REVIEW_HISTORY_ENTRIES,
    nextId,
    normalizeExercise,
    normalizeReviewHistoryEntry,
    resolveLlmConfig,
    upsertReviewHistory,
    usageTotals,
    validNotetypeDefaults,
    withQuickPrompt,
} from "./llm";

function exercise(overrides: Partial<ExerciseConfig>): ExerciseConfig {
    return { ...normalizeExercise({}), ...overrides };
}

function review(overrides: Partial<ReviewHistoryEntry>): ReviewHistoryEntry {
    return { ...normalizeReviewHistoryEntry({}), ...overrides };
}

test("exercise saved by AnkiDroid without default-valued fields gets those defaults", () => {
    const stored = { id: 3, notetypeId: 1700000000000, exerciseName: "Chat", systemPrompt: "Hi", cardUnrelated: false };

    expect(normalizeExercise(stored)).toEqual({
        id: 3,
        notetypeId: 1700000000000,
        exerciseName: "Chat",
        systemPrompt: "Hi",
        vocabularyFields: [],
        vocabularySelectionMode: "RANDOM",
        cardUnrelated: false,
        vocabularyWordBudget: 200,
        translationLanguage: "",
        practiceLanguage: "",
        aiStartsFirst: true,
    });
});

test("normalizing an exercise drops keys AnkiDroid would reject", () => {
    const normalized = normalizeExercise({ id: 1, desktopOnly: true });

    expect(normalized).not.toHaveProperty("desktopOnly");
});

test("review entry keeps an explicit null note id for chat-only sessions", () => {
    expect(normalizeReviewHistoryEntry({ dayCode: 20000, exerciseId: 2 })).toHaveProperty("noteId", null);
});

test("next id is 1 when nothing exists yet", () => {
    expect(nextId([])).toBe(1);
});

test("next id follows the highest existing id", () => {
    expect(nextId([{ id: 2 }, { id: 7 }, { id: 4 }])).toBe(8);
});

test("notetype defaults pointing at deleted or chat-only exercises are dropped", () => {
    const exercises = [exercise({ id: 1 }), exercise({ id: 2, cardUnrelated: true })];

    const defaults = validNotetypeDefaults({ "10": 1, "20": 2, "30": 99 }, exercises);

    expect(defaults).toEqual({ "10": 1 });
});

test("recording a review replaces the entry for the same day, exercise and note", () => {
    const earlier = review({ dayCode: 5, exerciseId: 1, noteId: 9, promptTokens: 10 });
    const otherNote = review({ dayCode: 5, exerciseId: 1, noteId: 8, promptTokens: 1 });
    const later = review({ dayCode: 5, exerciseId: 1, noteId: 9, promptTokens: 30 });

    expect(upsertReviewHistory([earlier, otherNote], later)).toEqual([otherNote, later]);
});

test("review history drops the oldest entries beyond the cap", () => {
    const full = Array.from({ length: MAX_REVIEW_HISTORY_ENTRIES }, (_, i) => review({ dayCode: i }));
    const newest = review({ dayCode: MAX_REVIEW_HISTORY_ENTRIES });

    const updated = upsertReviewHistory(full, newest);

    expect(updated).toHaveLength(MAX_REVIEW_HISTORY_ENTRIES);
    expect(updated[0].dayCode).toBe(1);
    expect(updated.at(-1)).toEqual(newest);
});

test("quick prompt description is trimmed and replaces the previous one", () => {
    const existing = [{ notetypeId: 1, type: "HINT" as const, taskDescription: "old" }];

    expect(withQuickPrompt(existing, 1, "HINT", "  new  ")).toEqual([
        { notetypeId: 1, type: "HINT", taskDescription: "new" },
    ]);
});

test("blank quick prompt description clears only that note type's override", () => {
    const hint = { notetypeId: 1, type: "HINT" as const, taskDescription: "a" };
    const moreInfo = { notetypeId: 1, type: "MORE_INFO" as const, taskDescription: "b" };

    expect(withQuickPrompt([hint, moreInfo], 1, "HINT", "   ")).toEqual([moreInfo]);
});

test("usage cost uses the price recorded with each entry", () => {
    const history = [
        review({
            promptTokens: 1_000_000,
            completionTokens: 500_000,
            pricing: { inputPerMillion: 2, outputPerMillion: 8 },
        }),
        review({
            promptTokens: 2_000_000,
            completionTokens: 0,
            pricing: { inputPerMillion: 0.5, outputPerMillion: 0 },
        }),
    ];

    expect(usageTotals(history)).toEqual({ promptTokens: 3_000_000, completionTokens: 500_000, cost: 7 });
});

const profile = {
    id: 4,
    apiEndpoint: "https://example.test/v1",
    modelName: "m",
    pricing: { inputPerMillion: 1, outputPerMillion: 2 },
};

test("active connection combines the selected profile with its local token", () => {
    expect(resolveLlmConfig([profile], 4, { "4": "secret" })).toEqual({
        apiEndpoint: "https://example.test/v1",
        apiToken: "secret",
        modelName: "m",
        pricing: { inputPerMillion: 1, outputPerMillion: 2 },
    });
});

test.each([
    ["no profile is selected", null, { "4": "secret" }],
    ["the selected profile no longer exists", 5, { "5": "secret" }],
    ["this device has no token for the profile", 4, {}],
    ["the token is blank", 4, { "4": "  " }],
])("there is no active connection when %s", (_, selectedId, tokens) => {
    expect(resolveLlmConfig([profile], selectedId, tokens)).toBeNull();
});

test("day code counts whole days since the epoch", () => {
    expect(currentDayCode(86_400_000 * 3 + 5)).toBe(3);
});
