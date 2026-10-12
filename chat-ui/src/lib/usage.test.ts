// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { expect, test } from "vitest";

import { addUsage, formatCost, totalUsage, type UsageEntry, usageOnDay } from "./usage";

function entry(fields: Partial<UsageEntry>): UsageEntry {
    return { at: 0, chatId: "chat", model: "test/model", promptTokens: 0, completionTokens: 0, cost: 0, ...fields };
}

test("totals add up tokens and cost across requests", () => {
    const totals = totalUsage([
        entry({ promptTokens: 6000, completionTokens: 120, cost: 0.0031 }),
        entry({ promptTokens: 6200, completionTokens: 80, cost: 0.0029 }),
    ]);

    expect(totals).toEqual({
        requests: 2,
        promptTokens: 12200,
        completionTokens: 200,
        cost: 0.006,
        costIncomplete: false,
    });
});

test("totals of no requests are zero", () => {
    expect(totalUsage([])).toEqual({
        requests: 0,
        promptTokens: 0,
        completionTokens: 0,
        cost: 0,
        costIncomplete: false,
    });
});

test("a request without a reported cost marks the total as incomplete", () => {
    const totals = totalUsage([entry({ cost: 0.5 }), entry({ cost: null })]);

    expect(totals.cost).toBe(0.5);
    expect(totals.costIncomplete).toBe(true);
});

test("a day's usage is what was used between its local midnights", () => {
    const at = (day: number, hour: number, minute = 0) => new Date(2026, 9, day, hour, minute).getTime();
    const lateYesterday = entry({ at: at(11, 23, 59) });
    const earlyToday = entry({ at: at(12, 0, 0) });
    const lateToday = entry({ at: at(12, 23, 59) });
    const tomorrow = entry({ at: at(13, 0, 0) });

    const today = usageOnDay([lateYesterday, earlyToday, lateToday, tomorrow], at(12, 17, 30));

    expect(today).toEqual([earlyToday, lateToday]);
});

test("adding usage keeps earlier entries and appends the new one", () => {
    const first = entry({ at: 1 });
    const second = entry({ at: 2 });

    expect(addUsage([first], second)).toEqual([first, second]);
});

test("a request reported a second time under the same id is counted once", () => {
    const profile = entry({ id: "gen-dec-1", cost: 0.00001 });
    const counted = addUsage([], profile);

    const again = addUsage(counted, { ...profile, at: 99 });

    expect(again).toBe(counted);
    expect(addUsage(counted, entry({ id: "gen-dec-2" }))).toHaveLength(2);
});

test("requests without an id are always counted", () => {
    const reply = entry({ cost: 0.001 });

    expect(addUsage(addUsage([], reply), reply)).toHaveLength(2);
});

test("costs show more digits the smaller they are", () => {
    expect(formatCost(0)).toBe("$0.00");
    expect(formatCost(0.00042)).toBe("$0.00042");
    expect(formatCost(0.0312)).toBe("$0.031");
    expect(formatCost(12.5)).toBe("$12.50");
});
