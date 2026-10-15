// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { ProfileUsage } from "./checker";
import { checkerFetch } from "./session";

/** The kinds of work requests to the models are made for, which the usage is added up by. */
export const USAGE_CATEGORIES = {
    chat: "Chat replies",
    checking: "Sentence checks",
    text: "Texts",
    speech: "Reading aloud",
    translation: "Translations",
    vocabulary: "Vocabulary",
    practice: "Practice",
} as const;

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

/** The usage of the user, with that of `chatId` and that from `since` on, in milliseconds since the epoch. */
export async function fetchUsage(chatId: string, since: number): Promise<UsageSummary> {
    const query = new URLSearchParams({ chat: chatId, since: String(Math.max(0, Math.floor(since))) });
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
