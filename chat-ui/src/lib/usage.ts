// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import type { Message } from "./i18n";
import { checkerFetch } from "./session";

/** The kinds of work requests to the models are made for, which the usage is added up by, as `t` shows them. */
export const USAGE_CATEGORIES = {
    chat: "Chat replies",
    checking: "Sentence checks",
    text: "Texts",
    speech: "Reading aloud",
    translation: "Translations",
    vocabulary: "Vocabulary",
    practice: "Practice",
    tutor: "Tutor",
} as const satisfies Record<string, Message>;

export type UsageCategory = keyof typeof USAGE_CATEGORIES;

/** What one reply used, as reported by OpenRouter. */
export interface UsageEntry {
    /** When the reply finished, in milliseconds since the epoch. */
    at: number;
    category: UsageCategory;
    /** What the request was made for: a chat, a text, or something such as "practice". */
    chatId: string;
    model: string;
    promptTokens: number;
    completionTokens: number;
    /** In US dollars; null if the provider did not report it. */
    cost: number | null;
    /** Set for a request that may be reported more than once, so that it is counted only the first time. */
    id?: string;
}

export interface UsageTotals {
    requests: number;
    promptTokens: number;
    completionTokens: number;
    cost: number;
    /** True if some request's cost was not reported, so `cost` is a lower bound. */
    costIncomplete: boolean;
}

/** The usage of the user who is logged in, as the checker server adds it up. */
export interface UsageSummary {
    /** That of the chat or text asked about. */
    chat: UsageTotals;
    /** That from the time asked about on. */
    since: UsageTotals;
    everything: UsageTotals;
    /** All of it, for each category and model. */
    byModel: (UsageTotals & { category: string; model: string })[];
    /** That from the time asked about on, for each category and model in bins of time, when bins were asked for. */
    series?: UsageBin[];
}

/** The usage of a category and a model in a bin of time, which starts at `at`. */
export type UsageBin = UsageTotals & { at: number; category: string; model: string };

/** The stretches of time the usage is shown for, as `t` shows them. */
export const PERIODS = {
    today: "Today",
    week: "7 days",
    month: "This month",
    days30: "30 days",
    all: "Everything",
} as const satisfies Record<string, Message>;

export type Period = keyof typeof PERIODS;

/** What the bars of the usage measure. */
export type Measure = "cost" | "tokens";

const HOUR = 3_600_000;

/** When `period` starts, as it is at `now`: at a local midnight, or at the start of everything. */
export function periodStart(period: Period, now: number): number {
    const day = new Date(startOfDay(now));
    if (period === "week") {
        day.setDate(day.getDate() - 6);
    } else if (period === "days30") {
        day.setDate(day.getDate() - 29);
    } else if (period === "month") {
        day.setDate(1);
    } else if (period === "all") {
        return 0;
    }
    return day.getTime();
}

/** How the usage of `period` is binned: by the hour for a day, and by the day otherwise. */
export function binOf(period: Period): "hour" | "day" {
    return period === "today" ? "hour" : "day";
}

/**
 * The starts of the bins from `start` to `now`, every one of them, those
 * with nothing in them too, by the hour or by the local day. Everything
 * starts with the first bin that has something in it.
 */
export function binStarts(period: Period, now: number, series: UsageBin[]): number[] {
    const start = period === "all"
        ? startOfDay(series.length ? Math.min(...series.map((each) => each.at)) : now)
        : periodStart(period, now);
    const starts: number[] = [];
    if (binOf(period) === "hour") {
        for (let at = start; at <= now; at += HOUR) {
            starts.push(at);
        }
        return starts;
    }
    // by the calendar, which a day of a change of the clocks is not 24 hours of
    for (const day = new Date(start); day.getTime() <= now; day.setDate(day.getDate() + 1)) {
        starts.push(day.getTime());
    }
    return starts;
}

/** What a bin of usage measures. */
export function measured(totals: UsageTotals, measure: Measure): number {
    return measure === "cost" ? totals.cost : totals.promptTokens + totals.completionTokens;
}

/** The usage of `period` as bars of time stacked by model. */
export interface Stacked {
    /** The models, the costliest first, which keeps a model's place, and its colour, however the bars change. */
    models: string[];
    /** What each model measures over the whole period, by the order of `models`. */
    totals: number[];
    bars: { at: number; values: number[]; total: number }[];
}

/** The usage in `series` as a bar for each bin of `starts`, stacked by model, the costliest at the bottom. */
export function stacked(series: UsageBin[], starts: number[], measure: Measure): Stacked {
    // by what they cost, whatever the bars measure, so that a model keeps its colour
    const byModel = new Map<string, [number, number]>();
    for (const each of series) {
        const [cost, tokens] = byModel.get(each.model) ?? [0, 0];
        byModel.set(each.model, [cost + each.cost, tokens + measured(each, "tokens")]);
    }
    const models = [...byModel.entries()]
        .sort((a, b) => b[1][0] - a[1][0] || b[1][1] - a[1][1] || a[0].localeCompare(b[0]))
        .map(([model]) => model);
    const bars = starts.map((at) => ({ at, values: models.map(() => 0), total: 0 }));
    const barOf = new Map(starts.map((at, index) => [at, bars[index]]));
    for (const each of series) {
        // a bin the calendar puts an hour off, across a change of the clocks, is that of its day
        const bar = barOf.get(each.at) ?? [...bars].reverse().find((candidate) => candidate.at <= each.at) ?? bars[0];
        if (!bar) {
            continue;
        }
        const value = measured(each, measure);
        bar.values[models.indexOf(each.model)] += value;
        bar.total += value;
    }
    const totals = models.map((_, index) => bars.reduce((sum, bar) => sum + bar.values[index], 0));
    return { models, totals, bars };
}

/** How many colours there are that can be told apart, which are given out in order. */
export const SERIES_COLOURS = 8;

/**
 * How often the usage is asked for again while it is shown, in
 * milliseconds: the server counts what a background task uses as each of
 * its requests is done, and looks up a reply that was stopped a little
 * after, neither of which the app is told of.
 */
export const USAGE_INTERVAL_MS = 5000;

/**
 * The colour of the series at `place`: the eight in order, then the same
 * eight in paler tones, as there are no more that can be told apart.
 */
export function seriesColour(place: number): string {
    const colour = `var(--series-${(place % SERIES_COLOURS) + 1})`;
    const round = Math.floor(place / SERIES_COLOURS);
    return round === 0 ? colour : `color-mix(in oklab, ${colour} ${Math.max(30, 100 - 30 * round)}%, var(--bg))`;
}

/** The usage in `series` added up, for each category and model, the categories in order and the costliest first in each. */
export function byCategoryAndModel(series: UsageBin[]): UsageSummary["byModel"] {
    const added = new Map<string, UsageSummary["byModel"][number]>();
    for (const each of series) {
        const key = `${each.category}\u0000${each.model}`;
        const had = added.get(key) ?? {
            category: each.category,
            model: each.model,
            requests: 0,
            promptTokens: 0,
            completionTokens: 0,
            cost: 0,
            costIncomplete: false,
        };
        added.set(key, {
            ...had,
            requests: had.requests + each.requests,
            promptTokens: had.promptTokens + each.promptTokens,
            completionTokens: had.completionTokens + each.completionTokens,
            cost: had.cost + each.cost,
            costIncomplete: had.costIncomplete || each.costIncomplete,
        });
    }
    return [...added.values()].sort((a, b) =>
        a.category.localeCompare(b.category) || b.cost - a.cost || a.model.localeCompare(b.model)
    );
}

/** The totals of `series`. */
export function totalOf(series: UsageBin[]): UsageTotals {
    return series.reduce<UsageTotals>(
        (sum, each) => ({
            requests: sum.requests + each.requests,
            promptTokens: sum.promptTokens + each.promptTokens,
            completionTokens: sum.completionTokens + each.completionTokens,
            cost: sum.cost + each.cost,
            costIncomplete: sum.costIncomplete || each.costIncomplete,
        }),
        { requests: 0, promptTokens: 0, completionTokens: 0, cost: 0, costIncomplete: false },
    );
}

/** How the usage is looked at, which is kept in this browser to be found as it was left. */
export interface UsageView {
    period: Period;
    measure: Measure;
}

const VIEW_KEY = "chat-ui.usage-view";

export function loadUsageView(): UsageView {
    const usual: UsageView = { period: "week", measure: "cost" };
    try {
        const stored = JSON.parse(localStorage.getItem(VIEW_KEY) ?? "null");
        return {
            period: stored?.period in PERIODS ? stored.period : usual.period,
            measure: stored?.measure === "tokens" ? "tokens" : usual.measure,
        };
    } catch {
        return usual;
    }
}

export function saveUsageView(view: UsageView): void {
    try {
        localStorage.setItem(VIEW_KEY, JSON.stringify(view));
    } catch {
        // it is then as usual the next time
    }
}

/** An entry for what the checker server said a request to a model used. */
export function profileUsage(
    used: ProfileUsage,
    at: number,
    category: UsageCategory,
    chatId: string = category,
): UsageEntry {
    return {
        id: used.id,
        at,
        category,
        chatId,
        model: used.model,
        promptTokens: used.input_tokens,
        completionTokens: used.output_tokens,
        cost: used.cost,
    };
}

/** Has the checker server keep `entries` for the user; those with an id it has already are counted once. */
export async function recordUsage(entries: UsageEntry[]): Promise<void> {
    const response = await checkerFetch("/usage", { method: "POST", body: JSON.stringify({ entries }) });
    if (!response.ok) {
        throw new Error(`checker server: ${response.status}`);
    }
}

/**
 * The usage of the user, with that of `chatId` and that from `since` on, in
 * milliseconds since the epoch, and, with a `bin`, that from `since` on in
 * bins of an hour or of a day of the learner's own.
 */
export async function fetchUsage(chatId: string, since: number, bin?: "hour" | "day"): Promise<UsageSummary> {
    const query = new URLSearchParams({ chat: chatId, since: String(Math.max(0, Math.floor(since))) });
    if (bin) {
        query.set("bin", bin);
        query.set("offset", String(-new Date().getTimezoneOffset()));
    }
    const response = await checkerFetch(`/usage?${query}`);
    if (!response.ok) {
        throw new Error(`checker server: ${response.status}`);
    }
    return response.json();
}

/** The local midnight that began the day `now` is in. */
export function startOfDay(now: number): number {
    const day = new Date(now);
    day.setHours(0, 0, 0, 0);
    return day.getTime();
}

/** Where the usage was kept in the browser before the server kept it. */
const LEGACY_KEY = "chat-ui.usage";

/** What a chat id of the usage kept in the browser was used for. */
function legacyCategory(chatId: string): UsageCategory {
    if (chatId.startsWith("text:")) {
        return "text";
    }
    const named: Record<string, UsageCategory> = {
        speech: "speech",
        vocabulary: "vocabulary",
        practice: "practice",
        translate: "translation",
    };
    return named[chatId] ?? "chat";
}

/**
 * The usage that was kept in this browser before the server kept it, each
 * entry given the category it most likely was. Empty if there is none.
 */
export function legacyUsage(): UsageEntry[] {
    try {
        const stored: unknown = JSON.parse(localStorage.getItem(LEGACY_KEY) ?? "[]");
        if (!Array.isArray(stored)) {
            return [];
        }
        return stored
            .filter((entry): entry is Omit<UsageEntry, "category"> =>
                typeof entry === "object" && entry !== null && typeof entry.chatId === "string"
            )
            .map((entry) => ({ ...entry, category: legacyCategory(entry.chatId) }));
    } catch {
        return [];
    }
}

/** Removes the usage kept in this browser, once the server has it. */
export function forgetLegacyUsage(): void {
    try {
        localStorage.removeItem(LEGACY_KEY);
    } catch {
        // it is then sent again the next time, and counted once all the same where it has an id
    }
}

/** Small amounts keep enough digits to show what a single reply cost. */
export function formatCost(dollars: number): string {
    if (dollars === 0) {
        return "$0.00";
    }
    const digits = dollars >= 1 ? 2 : dollars >= 0.01 ? 3 : 5;
    return `$${dollars.toFixed(digits)}`;
}

export function formatTokens(tokens: number): string {
    return tokens.toLocaleString("en-US");
}
