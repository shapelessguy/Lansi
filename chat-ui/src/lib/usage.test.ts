// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { afterEach, expect, test, vi } from "vitest";

import {
    binStarts,
    byCategoryAndModel,
    formatCost,
    legacyUsage,
    loadUsageView,
    periodStart,
    profileUsage,
    seriesColour,
    stacked,
    startOfDay,
    type UsageBin,
} from "./usage";

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

/** The usage of a model in a bin, as the server adds it up. */
function bin(at: number, model: string, cost: number, more: Partial<UsageBin> = {}): UsageBin {
    return {
        at,
        category: "chat",
        model,
        requests: 1,
        promptTokens: 10,
        completionTokens: 2,
        cost,
        costIncomplete: false,
        ...more,
    };
}

test("a period starts at a local midnight, a week back to the first of the month", () => {
    const now = new Date(2026, 9, 22, 15, 30).getTime();

    expect(periodStart("today", now)).toBe(new Date(2026, 9, 22).getTime());
    expect(periodStart("week", now)).toBe(new Date(2026, 9, 16).getTime());
    expect(periodStart("month", now)).toBe(new Date(2026, 9, 1).getTime());
    expect(periodStart("days30", now)).toBe(new Date(2026, 8, 23).getTime());
    expect(periodStart("all", now)).toBe(0);
});

test("every bin of a period is there, those with nothing in them too", () => {
    const now = new Date(2026, 9, 22, 2, 10).getTime();

    expect(binStarts("today", now, [])).toEqual([0, 1, 2].map((hour) => new Date(2026, 9, 22, hour).getTime()));
    expect(binStarts("week", now, [])).toHaveLength(7);
    // everything starts with the first day anything was used
    const first = new Date(2026, 9, 20, 9).getTime();
    expect(binStarts("all", now, [bin(first, "a", 1)])[0]).toBe(new Date(2026, 9, 20).getTime());
});

test("the bars stack every model, the one that costs most first", () => {
    const days = [0, 86_400_000];
    const series = [
        bin(0, "big", 5),
        bin(0, "small", 0.1),
        bin(86_400_000, "middle", 1),
        bin(86_400_000, "tiny", 0.01),
        bin(86_400_000, "big", 2),
    ];

    const data = stacked(series, days, "cost");

    expect(data.models).toEqual(["big", "middle", "small", "tiny"]);
    expect(data.totals).toEqual([7, 1, 0.1, 0.01]);
    expect(data.bars.map((bar) => bar.values)).toEqual([[5, 0, 0.1, 0], [2, 1, 0, 0.01]]);
});

test("the colours go round in paler tones once the eight are given out", () => {
    expect(seriesColour(0)).toBe("var(--series-1)");
    expect(seriesColour(7)).toBe("var(--series-8)");
    expect(seriesColour(8)).toBe("color-mix(in oklab, var(--series-1) 70%, var(--bg))");
});

test("the bars can measure the tokens in and out", () => {
    const data = stacked([bin(0, "a", 1)], [0], "tokens");

    expect(data.bars[0].total).toBe(12);
});

test("the usage of a period is added up by category and model, the costliest first", () => {
    const rows = byCategoryAndModel([
        bin(0, "a", 1),
        bin(1, "a", 2, { costIncomplete: true }),
        bin(0, "b", 5),
        bin(0, "a", 1, { category: "tutor" }),
    ]);

    expect(rows.map((row) => [row.category, row.model, row.cost, row.requests])).toEqual([
        ["chat", "b", 5, 1],
        ["chat", "a", 3, 2],
        ["tutor", "a", 1, 1],
    ]);
    expect(rows[1].costIncomplete).toBe(true);
});

test("how the usage is looked at is found as it was left, and as usual when it was not kept", () => {
    vi.stubGlobal("localStorage", {
        getItem: () => JSON.stringify({ period: "month", measure: "tokens" }),
    });
    expect(loadUsageView()).toEqual({ period: "month", measure: "tokens" });

    vi.stubGlobal("localStorage", { getItem: () => JSON.stringify({ period: "decade" }) });
    expect(loadUsageView()).toEqual({ period: "week", measure: "cost" });
});
