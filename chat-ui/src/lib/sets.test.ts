// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { describe, expect, it } from "vitest";

import {
    type CategoryRule,
    dayOf,
    DEFAULT_LIMIT,
    defaultRule,
    keepOf,
    matchesRule,
    membersOf,
    newSet,
    normalizeSet,
    ruleKeeping,
    ruleOf,
    withRule,
    withWord,
    wordLists,
    type WordSet,
} from "./sets";
import type { ListedWord } from "./vocabulary";

/** Noon of a day, in seconds since the epoch, in local time. */
function noon(day: string): number {
    return new Date(`${day}T12:00:00`).getTime() / 1000;
}

function word(id: number, lemma: string, more: Partial<ListedWord> = {}): ListedWord {
    return {
        id,
        lemma,
        category: "noun",
        created_at: "2026-10-13 12:00:00",
        forms: 1,
        used: 0,
        seen: 0,
        first_used: null,
        last_used: null,
        ...more,
    };
}

function rule(parts: Partial<CategoryRule> = {}): CategoryRule {
    return { ...defaultRule(), ...parts };
}

/** A set with the same rule for every category, unless told otherwise. */
function set(otherwise: Partial<CategoryRule> = {}, parts: Partial<WordSet> = {}): WordSet {
    return { id: "set-1", name: "Travel", rules: {}, otherwise: rule(otherwise), added: [], removed: [], ...parts };
}

const hund = word(1, "Hund", { used: 3, seen: 1, last_used: noon("2026-10-13") });
const gehen = word(2, "gehen", { category: "verb", seen: 4, last_used: noon("2026-10-12") });
const zug = word(3, "Zug");
const reise = word(5, "Reise", { used: 1, seen: 9, last_used: noon("2026-10-11") });
const all = [hund, gehen, zug, reise];
const lemmas = (of: WordSet, words = all) => membersOf(of, words).map((each) => each.lemma);

describe("a new set", () => {
    it("takes the words of every category, up to so many of each", () => {
        const fresh = newSet("Travel");

        expect(ruleOf(fresh, "noun")).toEqual(rule({ included: true, limit: DEFAULT_LIMIT }));
        expect(DEFAULT_LIMIT).toBe(100);
        expect(lemmas(fresh)).toEqual(["Hund", "gehen", "Zug", "Reise"]);
    });
});

describe("the rule of a category", () => {
    it("lets in the words used and seen often enough, and not too often", () => {
        expect(matchesRule(hund, set({ minUsed: 3 }))).toBe(true);
        expect(matchesRule(hund, set({ minUsed: 4 }))).toBe(false);
        expect(matchesRule(hund, set({ maxUsed: 2 }))).toBe(false);
        expect(matchesRule(zug, set({ maxUsed: 0 }))).toBe(true);
        expect(matchesRule(gehen, set({ minSeen: 4 }))).toBe(true);
        expect(matchesRule(gehen, set({ maxSeen: 3 }))).toBe(false);
    });

    it("is its own for the categories that have one, and the same for the others", () => {
        const picked = withRule(set({ maxUsed: 0 }), "verb", { minSeen: 5 });

        expect(ruleOf(picked, "verb")).toEqual(rule({ maxUsed: 0, minSeen: 5 }));
        expect(ruleOf(picked, "noun")).toEqual(rule({ maxUsed: 0 }));
        // nouns go by the one rule, verbs by their own
        expect(lemmas(picked)).toEqual(["Zug"]);
    });

    it("gives no words of a category that is left out", () => {
        const withoutVerbs = withRule(set(), "verb", { included: false });

        expect(lemmas(withoutVerbs)).toEqual(["Hund", "Zug", "Reise"]);
    });

    it("has a word leave the set once it is used more often than the rule allows", () => {
        const rarelyUsed = set({ maxUsed: 2 });
        const twice = word(7, "Tisch", { used: 2 });

        expect(membersOf(rarelyUsed, [twice])).toEqual([twice]);
        expect(membersOf(rarelyUsed, [{ ...twice, used: 3 }])).toEqual([]);
    });
});

describe("a category that gives so many words at the most", () => {
    it("keeps the words last used, in the order of the vocabulary", () => {
        expect(lemmas(set({ limit: 2, orderBy: "lastUsed" }))).toEqual(["Hund", "gehen", "Reise"]);
    });

    it("keeps the words used the most, or the least", () => {
        expect(lemmas(set({ limit: 1, orderBy: "used" }))).toEqual(["Hund", "gehen"]);
        expect(lemmas(set({ limit: 1, orderBy: "used", mostFirst: false }))).toEqual(["gehen", "Zug"]);
    });

    it("keeps the words seen the most, or used and seen the most taken together", () => {
        expect(lemmas(set({ limit: 1, orderBy: "seen" }))).toEqual(["gehen", "Reise"]);
        expect(lemmas(set({ limit: 1, orderBy: "total" }))).toEqual(["gehen", "Reise"]);
    });

    it("counts each category by itself", () => {
        const picked = withRule(set({ limit: 2, orderBy: "used" }), "verb", { limit: 1 });

        expect(lemmas(picked)).toEqual(["Hund", "gehen", "Reise"]);
    });

    it("keeps every word when there are no more than that, or there is no most", () => {
        expect(lemmas(set({ limit: 9 }))).toHaveLength(4);
        expect(lemmas(set({ limit: 0 }))).toHaveLength(4);
    });
});

describe("words put in and taken out by hand", () => {
    const usedOnly = set({ minUsed: 1 });

    it("are of the set, or not, whatever the rules say", () => {
        const picked = set({ minUsed: 1 }, { removed: [1], added: [3] });

        expect(lemmas(picked)).toEqual(["Zug", "Reise"]);
    });

    it("are noted only where the rules say otherwise", () => {
        expect(withWord(usedOnly, zug, true, all)).toMatchObject({ added: [3], removed: [] });
        expect(withWord(usedOnly, hund, false, all)).toMatchObject({ added: [], removed: [1] });
        expect(withWord(usedOnly, hund, true, all)).toEqual(usedOnly);
        expect(withWord(withWord(usedOnly, zug, true, all), zug, false, all)).toEqual(usedOnly);
    });

    it("are noted for a word the most had cut off, or had kept", () => {
        const firstOnly = set({ limit: 1, orderBy: "used" });

        expect(withWord(firstOnly, reise, true, all)).toMatchObject({ added: [5], removed: [] });
        expect(withWord(firstOnly, hund, false, all)).toMatchObject({ added: [], removed: [1] });
    });

    it("come on top of as many as a category may give", () => {
        const picked = set({ limit: 1, orderBy: "used" }, { added: [3] });

        expect(lemmas(picked)).toEqual(["Hund", "gehen", "Zug"]);
    });
});

describe("what is kept of a category", () => {
    it("is told and taken as one choice", () => {
        expect(keepOf(rule({ orderBy: "used", mostFirst: false }))).toBe("used:least");
        expect(ruleKeeping("lastUsed:most")).toEqual({ orderBy: "lastUsed", mostFirst: true });
        expect(ruleKeeping("total:least")).toEqual({ orderBy: "total", mostFirst: false });
    });
});

describe("wordLists", () => {
    const nouns = withRule(set({ included: false }, { id: "a", name: "Nouns" }), "noun", { included: true });
    const seen = set({ minSeen: 1 }, { id: "b", name: " Seen Words " });

    it("gives the dictionary forms of the set in use, and of each set by its name", () => {
        const lists = wordLists([nouns, seen], "a", [hund, gehen, zug]);

        expect(lists.active).toEqual(["Hund", "Zug"]);
        expect(lists.named).toEqual({ "nouns": ["Hund", "Zug"], "seen words": ["Hund", "gehen"] });
    });

    it("gives every word there is when no set is in use, each once", () => {
        const lists = wordLists([nouns], undefined, [hund, gehen, word(9, "Hund", { category: "verb" })]);

        expect(lists.active).toEqual(["Hund", "gehen"]);
    });

    it("gives every word when the set in use is gone", () => {
        expect(wordLists([nouns], "deleted", [gehen]).active).toEqual(["gehen"]);
    });
});

describe("normalizeSet", () => {
    it("makes a set whole that was kept without some of its parts", () => {
        const made = normalizeSet({ id: "a", name: "Nouns", rules: { noun: { minUsed: 2 } }, added: [1, "x"] });

        expect(made).toEqual({
            id: "a",
            name: "Nouns",
            rules: { noun: rule({ minUsed: 2 }) },
            otherwise: rule(),
            added: [1],
            removed: [],
        });
    });

    it("gives a set kept with one rule that rule for the categories it named, and no others", () => {
        const made = normalizeSet({
            id: "a",
            name: "Old",
            rule: { categories: ["noun"], minUsed: 1, maxUsed: null, storedFrom: "2026-10-01", limit: 0 },
        });

        expect(made?.rules).toEqual({ noun: rule({ minUsed: 1, limit: 0 }) });
        expect(made?.otherwise).toEqual(rule({ minUsed: 1, limit: 0, included: false }));
        expect(lemmas(made!)).toEqual(["Hund", "Reise"]);
    });

    it("gives a set kept with one rule for every category that rule for all", () => {
        const made = normalizeSet({ id: "a", name: "Old", rule: { categories: [], minSeen: 4 } });

        expect(made?.rules).toEqual({});
        expect(lemmas(made!)).toEqual(["gehen", "Reise"]);
    });

    it("takes nothing that has no id or name for a set", () => {
        expect(normalizeSet(null)).toBeNull();
        expect(normalizeSet({ name: "Nouns" })).toBeNull();
    });
});

describe("dayOf", () => {
    it("gives the day of a time, and nothing for no time", () => {
        expect(dayOf(noon("2026-10-13"))).toBe("2026-10-13");
        expect(dayOf(null)).toBe("");
    });
});
