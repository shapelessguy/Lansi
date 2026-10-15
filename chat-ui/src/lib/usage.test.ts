// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { afterEach, expect, test, vi } from "vitest";

import { formatCost, legacyUsage, profileUsage, startOfDay } from "./usage";

afterEach(() => vi.unstubAllGlobals());

/** Has localStorage hold `stored` under the key the usage was kept in. */
function keptInTheBrowser(stored: string | null) {
    vi.stubGlobal("localStorage", { getItem: (key: string) => (key === "chat-ui.usage" ? stored : null) });
}

test("what the checker server said a request used is counted under its category", () => {
    const used = { id: "gen-1", model: "some/model", input_tokens: 40, output_tokens: 3, cost: 0.001 };

    expect(profileUsage(used, 1000, "vocabulary")).toEqual({
        id: "gen-1",
        at: 1000,
        category: "vocabulary",
        chatId: "vocabulary",
        model: "some/model",
        promptTokens: 40,
        completionTokens: 3,
        cost: 0.001,
    });
    expect(profileUsage(used, 1000, "checking", "chat-1").chatId).toBe("chat-1");
});

test("a day starts at its local midnight", () => {
    const afternoon = new Date(2026, 9, 15, 17, 30).getTime();

    expect(startOfDay(afternoon)).toBe(new Date(2026, 9, 15).getTime());
});

test("the usage kept in the browser before is given the category its chat id tells", () => {
    const entry = { at: 0, model: "test/model", promptTokens: 1, completionTokens: 1, cost: 0 };
    keptInTheBrowser(JSON.stringify([
        { ...entry, chatId: "4b6f0c9e-1111-4222-8333-944445555666" },
        { ...entry, chatId: "text:die-reise" },
        { ...entry, chatId: "translate" },
        { ...entry, chatId: "practice" },
        "not an entry",
    ]));

    expect(legacyUsage().map((left) => left.category)).toEqual(["chat", "text", "translation", "practice"]);
});

test("there is no usage left from before when the browser kept none, or something else", () => {
    keptInTheBrowser(null);
    expect(legacyUsage()).toEqual([]);
    keptInTheBrowser("{broken");
    expect(legacyUsage()).toEqual([]);
});

test("costs show more digits the smaller they are", () => {
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(0.00042)).toBe("$0.00042");
    expect(formatCost(0.0312)).toBe("$0.031");
    expect(formatCost(12.5)).toBe("$12.50");
});
