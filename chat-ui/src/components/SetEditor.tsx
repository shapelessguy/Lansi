// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useMemo, useState } from "react";

import {
    type CategoryRule,
    dayOf,
    type Keep,
    keepLabels,
    keepOf,
    matchesRule,
    membersOf,
    ruleKeeping,
    ruleOf,
    withRule,
    withWord,
    type WordSet,
} from "../lib/sets";
import { countWords, type ListedWord, type Vocabulary } from "../lib/vocabulary";

interface Props {
    /** The set as it is when the editor is opened. */
    set: WordSet;
    /** Whether the set has been kept before, and so can be deleted. */
    kept: boolean;
    vocabulary: Vocabulary;
    onSave: (set: WordSet) => void;
    onDelete: () => void;
    onClose: () => void;
}

type Column = "lemma" | "category" | "used" | "seen" | "last_used";

const columns: { key: Column; label: string }[] = [
    { key: "lemma", label: "Word" },
    { key: "category", label: "Category" },
    { key: "used", label: "Used" },
    { key: "seen", label: "Seen" },
    { key: "last_used", label: "Last used" },
];

const collator = new Intl.Collator(undefined, { sensitivity: "base", numeric: true });

function compare(a: ListedWord, b: ListedWord, column: Column): number {
    const [left, right] = [a[column] ?? "", b[column] ?? ""];
    const order = typeof left === "number" && typeof right === "number"
        ? left - right
        : collator.compare(String(left), String(right));
    return order || collator.compare(a.lemma, b.lemma);
}

/**
 * Makes a set of words over the whole page: on the left a rule for each
 * category, which picks its words by how often they were used, and on the
 * right every word of the vocabulary with a tick if it is in the set, to
 * put in or take out by hand.
 */
export function SetEditor({ set: initial, kept, vocabulary, onSave, onDelete, onClose }: Props) {
    const [set, setSet] = useState(initial);
    const [search, setSearch] = useState("");
    const [onlyMembers, setOnlyMembers] = useState(false);
    const [sort, setSort] = useState<{ column: Column; descending: boolean }>({ column: "lemma", descending: false });

    const members = useMemo(() => membersOf(set, vocabulary.words), [vocabulary, set]);
    const memberIds = useMemo(() => new Set(members.map((word) => word.id)), [members]);
    // how many words each category has, and how many of them are in the set
    const counts = useMemo(() => {
        const count = (words: ListedWord[]) => {
            const byCategory = new Map<string, number>();
            words.forEach((word) => byCategory.set(word.category, (byCategory.get(word.category) ?? 0) + 1));
            return byCategory;
        };
        return { all: count(vocabulary.words), members: count(members) };
    }, [vocabulary, members]);
    const shown = useMemo(() => {
        const wanted = search.trim().toLowerCase();
        const rows = vocabulary.words.filter((word) =>
            (!wanted || word.lemma.toLowerCase().includes(wanted)) && (!onlyMembers || memberIds.has(word.id))
        );
        rows.sort((a, b) => compare(a, b, sort.column) * (sort.descending ? -1 : 1));
        return rows;
    }, [vocabulary, search, onlyMembers, memberIds, sort]);

    /** A box for a number of the rule of a category. Left empty, it is `empty`. */
    function count(
        category: string,
        rule: CategoryRule,
        key: "minUsed" | "maxUsed" | "minSeen" | "maxSeen" | "limit",
        label: string,
        empty: number | null,
        placeholder: string,
    ) {
        return (
            <input
                type="number"
                min={0}
                disabled={!rule.included}
                aria-label={`${category}: ${label}`}
                placeholder={placeholder}
                value={rule[key] === empty ? "" : rule[key] ?? ""}
                onChange={(event) =>
                    setSet(
                        withRule(set, category, {
                            [key]: event.target.value === "" ? empty : Math.max(0, Number(event.target.value) || 0),
                        }),
                    )}
            />
        );
    }

    return (
        <div className="overlay" role="dialog" aria-modal="true" aria-label="Edit a set of words">
            <header className="overlay-header">
                <input
                    className="set-name"
                    type="text"
                    placeholder="Name of the set"
                    aria-label="Name of the set"
                    autoFocus
                    value={set.name}
                    onChange={(event) => setSet({ ...set, name: event.target.value })}
                />
                <span className="set-total">
                    <b>{countWords(members)}</b> of {countWords(vocabulary.words)} words
                </span>
                {kept && (
                    <button onClick={() => window.confirm(`Delete the set “${initial.name}”?`) && onDelete()}>
                        Delete
                    </button>
                )}
                <button onClick={onClose}>Cancel</button>
                <button className="primary" disabled={!set.name.trim()} onClick={() => onSave(set)}>Save</button>
            </header>
            <div className="overlay-body">
                <aside className="set-rule">
                    <div className="rule-grid rule-head">
                        <span>Category</span>
                        <span>Used by you</span>
                        <span>Seen</span>
                        <span>At most</span>
                        <span>Keeping</span>
                        <span>In the set</span>
                    </div>
                    {vocabulary.categories.map((category) => {
                        const rule = ruleOf(set, category);
                        const inSet = counts.members.get(category) ?? 0;
                        const total = counts.all.get(category) ?? 0;
                        return (
                            <div
                                key={category}
                                className={rule.included ? "rule-grid rule-row" : "rule-grid rule-row left-out"}
                            >
                                <label className="rule-name">
                                    <input
                                        type="checkbox"
                                        checked={rule.included}
                                        onChange={(event) =>
                                            setSet(withRule(set, category, { included: event.target.checked }))}
                                    />
                                    {category}
                                </label>
                                <span className="range">
                                    {count(category, rule, "minUsed", "used at least", 0, "0")}
                                    <i>to</i>
                                    {count(category, rule, "maxUsed", "used at most", null, "any")}
                                </span>
                                <span className="range">
                                    {count(category, rule, "minSeen", "seen at least", 0, "0")}
                                    <i>to</i>
                                    {count(category, rule, "maxSeen", "seen at most", null, "any")}
                                </span>
                                {count(category, rule, "limit", "words at most", 0, "all")}
                                <select
                                    disabled={!rule.included}
                                    aria-label={`${category}: which words are kept`}
                                    value={keepOf(rule)}
                                    onChange={(event) =>
                                        setSet(withRule(set, category, ruleKeeping(event.target.value as Keep)))}
                                >
                                    {Object.entries(keepLabels).map(([key, label]) => (
                                        <option key={key} value={key}>{label}</option>
                                    ))}
                                </select>
                                <span className="rule-count">
                                    <span>
                                        <b>{inSet}</b> of {total}
                                    </span>
                                    <span className="bar">
                                        <span style={{ width: `${total ? (100 * inSet) / total : 0}%` }} />
                                    </span>
                                </span>
                            </div>
                        );
                    })}
                    <p className="hint">
                        The set is worked out again each time it is used, from the counts as they are then: a word joins
                        when its category's rule lets it in, and leaves when it no longer does. Words you tick or untick
                        by hand stay as you left them: {set.added.length} put in, {set.removed.length} taken out.
                    </p>
                </aside>
                <section className="set-words">
                    <div className="set-toolbar">
                        <input
                            type="search"
                            placeholder="Find a word"
                            aria-label="Find a word"
                            value={search}
                            onChange={(event) => setSearch(event.target.value)}
                        />
                        <label>
                            <input
                                type="checkbox"
                                checked={onlyMembers}
                                onChange={(event) => setOnlyMembers(event.target.checked)}
                            />
                            Only the words of the set
                        </label>
                        <span className="count">{shown.length} shown</span>
                    </div>
                    <div className="set-table">
                        <table>
                            <thead>
                                <tr>
                                    <th aria-label="In the set" />
                                    {columns.map(({ key, label }) => (
                                        <th key={key}>
                                            <button
                                                onClick={() =>
                                                    setSort({
                                                        column: key,
                                                        descending: sort.column === key && !sort.descending,
                                                    })}
                                            >
                                                {label}
                                                {sort.column === key && (sort.descending ? " ↓" : " ↑")}
                                            </button>
                                        </th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {shown.map((word) => {
                                    const member = memberIds.has(word.id);
                                    const byHand = set.added.includes(word.id) || set.removed.includes(word.id);
                                    return (
                                        <tr key={word.id} className={member ? "member" : undefined}>
                                            <td>
                                                <input
                                                    type="checkbox"
                                                    aria-label={`${word.lemma} in the set`}
                                                    checked={member}
                                                    onChange={() =>
                                                        setSet(withWord(set, word, !member, vocabulary.words))}
                                                />
                                            </td>
                                            <td>
                                                {word.lemma}
                                                {byHand && <small title="Ticked or unticked by hand">by hand</small>}
                                                {!member && !byHand && matchesRule(word, set) && (
                                                    <small
                                                        className="cut"
                                                        title="Its category already gives as many words as it may"
                                                    >
                                                        over the most
                                                    </small>
                                                )}
                                            </td>
                                            <td>
                                                <span className="pill">{word.category}</span>
                                            </td>
                                            <td className="num">{word.used || ""}</td>
                                            <td className="num">{word.seen || ""}</td>
                                            <td>{dayOf(word.last_used)}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </section>
            </div>
        </div>
    );
}
