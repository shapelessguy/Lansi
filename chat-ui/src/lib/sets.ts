// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { newId } from "./ids";
import { checkerFetch } from "./session";
import type { ListedWord } from "./vocabulary";

/** What the words of a category can be put in order by, to keep the first few. */
export type OrderKey = "lastUsed" | "used" | "seen" | "total";

/** How many words a category gives a set at the most, unless another number is asked for. */
export const DEFAULT_LIMIT = 100;

/** What picks the words of one category for a set. */
export interface CategoryRule {
    /** Whether the category gives the set any words at all. */
    included: boolean;
    /** How often you must have used a word, at the least, and at the most; null for no most. */
    minUsed: number;
    maxUsed: number | null;
    /** How often the model must have written it, at the least and at the most. */
    minSeen: number;
    maxSeen: number | null;
    /** How many words the category gives at the most; 0 for as many as there are. */
    limit: number;
    /** Which words are kept when there are more than that: those with the most of this, or the least. */
    orderBy: OrderKey;
    mostFirst: boolean;
}

/** A set of words picked out of the vocabulary, to be given to a model. */
export interface WordSet {
    id: string;
    name: string;
    /** The rule of each category that has one of its own, by the category's name. */
    rules: Record<string, CategoryRule>;
    /** The rule of every other category. */
    otherwise: CategoryRule;
    /** The words put in by hand though the rules leave them out, by their ids. */
    added: number[];
    /** The words taken out by hand though the rules let them in. */
    removed: number[];
}

export function defaultRule(): CategoryRule {
    return {
        included: true,
        minUsed: 0,
        maxUsed: null,
        minSeen: 0,
        maxSeen: null,
        limit: DEFAULT_LIMIT,
        orderBy: "lastUsed",
        mostFirst: true,
    };
}

export function newSet(name = ""): WordSet {
    return { id: newId(), name, rules: {}, otherwise: defaultRule(), added: [], removed: [] };
}

/** The rule a set has for a category. */
export function ruleOf(set: WordSet, category: string): CategoryRule {
    return set.rules[category] ?? set.otherwise;
}

/** The set with the rule of one category changed. */
export function withRule(set: WordSet, category: string, change: Partial<CategoryRule>): WordSet {
    return { ...set, rules: { ...set.rules, [category]: { ...ruleOf(set, category), ...change } } };
}

/** The ways the words of a category can be put in order, each as what is kept. */
export const keepLabels = {
    "lastUsed:most": "the most recently used",
    "lastUsed:least": "the least recently used",
    "used:most": "the most used by you",
    "used:least": "the least used by you",
    "seen:most": "the most seen",
    "seen:least": "the least seen",
    "total:most": "the most used or seen",
    "total:least": "the least used or seen",
} as const;

export type Keep = keyof typeof keepLabels;

export function keepOf(rule: CategoryRule): Keep {
    return `${rule.orderBy}:${rule.mostFirst ? "most" : "least"}`;
}

export function ruleKeeping(keep: Keep): Pick<CategoryRule, "orderBy" | "mostFirst"> {
    const [orderBy, direction] = keep.split(":");
    return { orderBy: orderBy as OrderKey, mostFirst: direction === "most" };
}

/** The day something happened, as `2026-10-13`, in local time; "" if it never did. */
export function dayOf(seconds: number | null): string {
    if (seconds === null) {
        return "";
    }
    const date = new Date(seconds * 1000);
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Whether the rule of its category lets a word in, before the category is cut down to as many as it may give. */
export function matchesRule(word: ListedWord, set: WordSet): boolean {
    const rule = ruleOf(set, word.category);
    return (
        rule.included
        && word.used >= rule.minUsed
        && (rule.maxUsed === null || word.used <= rule.maxUsed)
        && word.seen >= rule.minSeen
        && (rule.maxSeen === null || word.seen <= rule.maxSeen)
    );
}

const collator = new Intl.Collator(undefined, { sensitivity: "base" });

/** How much a word has of what words are put in order by. A word never used was last used before all others. */
function amount(word: ListedWord, key: OrderKey): number {
    const amounts: Record<OrderKey, number> = {
        lastUsed: word.last_used ?? 0,
        used: word.used,
        seen: word.seen,
        total: word.used + word.seen,
    };
    return amounts[key];
}

/**
 * The words of the vocabulary that are of a set, worked out from what is
 * known about each word now. Each category gives the words its rule lets
 * in, without the ones taken out by hand, cut down to as many as it may
 * give. The words put in by hand are of the set whatever the rules say.
 */
export function membersOf(set: WordSet, words: ListedWord[]): ListedWord[] {
    const byCategory = new Map<string, ListedWord[]>();
    for (const word of words) {
        if (matchesRule(word, set) && !set.removed.includes(word.id)) {
            byCategory.set(word.category, [...(byCategory.get(word.category) ?? []), word]);
        }
    }
    const ids = new Set(set.added);
    for (const [category, picked] of byCategory) {
        const { limit, orderBy, mostFirst } = ruleOf(set, category);
        const direction = mostFirst ? -1 : 1;
        const kept = limit > 0 && picked.length > limit
            ? [...picked]
                .sort((a, b) =>
                    (amount(a, orderBy) - amount(b, orderBy)) * direction || collator.compare(a.lemma, b.lemma)
                )
                .slice(0, limit)
            : picked;
        kept.forEach((word) => ids.add(word.id));
    }
    return words.filter((word) => ids.has(word.id));
}

/**
 * The set with a word put in or taken out by hand. A word is only noted
 * where it would otherwise be the other way, so that changing one's mind
 * leaves nothing behind. `words` are those of the vocabulary, by which it is
 * told whether the word is of the set without being noted.
 */
export function withWord(set: WordSet, word: ListedWord, member: boolean, words: ListedWord[]): WordSet {
    const added = set.added.filter((id) => id !== word.id);
    const removed = set.removed.filter((id) => id !== word.id);
    const unnoted = membersOf({ ...set, added, removed }, words).some((each) => each.id === word.id);
    if (member && !unnoted) {
        added.push(word.id);
    } else if (!member && unnoted) {
        removed.push(word.id);
    }
    return { ...set, added, removed };
}

/** The parts of a rule that were kept, made into a whole rule. Dates, which rules once had, are let go of. */
function normalizeRule(stored: unknown, included = true): CategoryRule {
    const candidate = (typeof stored === "object" && stored !== null ? stored : {}) as Partial<CategoryRule>;
    const count = (value: unknown, otherwise: number) =>
        typeof value === "number" && value >= 0 ? Math.floor(value) : otherwise;
    const most = (value: unknown) => (typeof value === "number" && value >= 0 ? Math.floor(value) : null);
    const defaults = defaultRule();
    return {
        included: typeof candidate.included === "boolean" ? candidate.included : included,
        minUsed: count(candidate.minUsed, 0),
        maxUsed: most(candidate.maxUsed),
        minSeen: count(candidate.minSeen, 0),
        maxSeen: most(candidate.maxSeen),
        limit: count(candidate.limit, defaults.limit),
        orderBy: (["lastUsed", "used", "seen", "total"] as const).find((key) => key === candidate.orderBy)
            ?? defaults.orderBy,
        mostFirst: typeof candidate.mostFirst === "boolean" ? candidate.mostFirst : defaults.mostFirst,
    };
}

/**
 * A set as it was kept, made whole. One kept when a set had a single rule
 * for the categories it named has that rule for each of them, and gives no
 * words of the others.
 */
export function normalizeSet(stored: unknown): WordSet | null {
    if (typeof stored !== "object" || stored === null) {
        return null;
    }
    const candidate = stored as Partial<WordSet> & { rule?: { categories?: unknown } };
    if (typeof candidate.id !== "string" || typeof candidate.name !== "string") {
        return null;
    }
    const ids = (value: unknown) => (Array.isArray(value) ? value.filter((id) => typeof id === "number") : []);
    let rules: Record<string, CategoryRule> = {};
    let otherwise = normalizeRule(candidate.otherwise);
    if (typeof candidate.rules === "object" && candidate.rules !== null) {
        rules = Object.fromEntries(
            Object.entries(candidate.rules).map(([category, rule]) => [category, normalizeRule(rule)]),
        );
    } else if (typeof candidate.rule === "object" && candidate.rule !== null) {
        const named = Array.isArray(candidate.rule.categories)
            ? candidate.rule.categories.filter((category): category is string => typeof category === "string")
            : [];
        // the one rule had no most unless it was given one
        const one = { limit: 0, ...candidate.rule };
        rules = Object.fromEntries(named.map((category) => [category, normalizeRule(one)]));
        otherwise = normalizeRule(one, named.length === 0);
    }
    return {
        id: candidate.id,
        name: candidate.name,
        rules,
        otherwise,
        added: ids(candidate.added),
        removed: ids(candidate.removed),
    };
}

/** The lists of words a prompt can ask for. */
export interface WordLists {
    /** What `{{words}}` stands for: the words of the set that is in use, or of the whole vocabulary. */
    active: string[];
    /** What `{{words:Name}}` stands for, by the name of the set in small letters. */
    named: Record<string, string[]>;
}

/**
 * The dictionary forms a prompt is given for each set. `activeId` is the set
 * `{{words}}` stands for; without one, it stands for every word there is.
 */
export function wordLists(sets: WordSet[], activeId: string | undefined, words: ListedWord[]): WordLists {
    const lemmas = (members: ListedWord[]) => [...new Set(members.map((word) => word.lemma))];
    const active = sets.find((set) => set.id === activeId);
    return {
        active: lemmas(active ? membersOf(active, words) : words),
        named: Object.fromEntries(sets.map((set) => [set.name.trim().toLowerCase(), lemmas(membersOf(set, words))])),
    };
}

async function send(path: string, language: string, init?: RequestInit): Promise<Response> {
    let response: Response;
    try {
        response = await checkerFetch(`/vocabulary/sets${path}?language=${encodeURIComponent(language)}`, init);
    } catch {
        throw new Error("The server cannot be reached. Is `just dev` running?");
    }
    if (!response.ok) {
        throw new Error(`The server answered ${response.status}.`);
    }
    return response;
}

/** The sets of the vocabulary of a language. */
export async function fetchSets(language: string): Promise<WordSet[]> {
    const { sets }: { sets: unknown[] } = await (await send("", language)).json();
    return sets.map(normalizeSet).filter((set): set is WordSet => set !== null);
}

export async function saveSet(set: WordSet, language: string): Promise<void> {
    await send(`/${set.id}`, language, { method: "PUT", body: JSON.stringify(set) });
}

export async function deleteSet(id: string, language: string): Promise<void> {
    await send(`/${id}`, language, { method: "DELETE" });
}
