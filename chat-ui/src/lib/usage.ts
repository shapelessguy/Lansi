// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

/** What one reply used, as reported by OpenRouter. */
export interface UsageEntry {
    /** When the reply finished, in milliseconds since the epoch. */
    at: number;
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

const STORAGE_KEY = "chat-ui.usage";
/** Older entries are dropped, so the log can't outgrow the browser's storage. */
const MAX_ENTRIES = 2000;

export function loadUsage(): UsageEntry[] {
    try {
        const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
        return Array.isArray(stored) ? stored : [];
    } catch {
        return [];
    }
}

export function saveUsage(entries: UsageEntry[]): void {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
    } catch {
        // usage is then only tracked until the page is closed
    }
}

/** The entries with `entry` added. They are returned as they are if it has an id that was already counted. */
export function addUsage(entries: UsageEntry[], entry: UsageEntry): UsageEntry[] {
    if (entry.id !== undefined && entries.some((counted) => counted.id === entry.id)) {
        return entries;
    }
    return [...entries, entry].slice(-MAX_ENTRIES);
}

/** The entries from the same calendar day as `now`, in local time. */
export function usageOnDay(entries: UsageEntry[], now: number): UsageEntry[] {
    const day = new Date(now).toDateString();
    return entries.filter((entry) => new Date(entry.at).toDateString() === day);
}

export function totalUsage(entries: UsageEntry[]): UsageTotals {
    const totals: UsageTotals = {
        requests: entries.length,
        promptTokens: 0,
        completionTokens: 0,
        cost: 0,
        costIncomplete: false,
    };
    for (const entry of entries) {
        totals.promptTokens += entry.promptTokens;
        totals.completionTokens += entry.completionTokens;
        totals.cost += entry.cost ?? 0;
        totals.costIncomplete ||= entry.cost === null;
    }
    return totals;
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
