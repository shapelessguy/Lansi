// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useMemo, useState } from "react";

import type { WordsState } from "../App";
import { t } from "../lib/i18n";
import { filterWords, type SortKey, sortLabels, sortWords, type Word } from "../lib/words";

interface Props {
    state: WordsState;
    onReload: () => void;
    onPick: (word: Word) => void;
}

function today(): string {
    const now = new Date();
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function WordList({ state, onReload, onPick }: Props) {
    const [sortKey, setSortKey] = useState<SortKey>("due");
    const [descending, setDescending] = useState(false);
    const [query, setQuery] = useState("");

    const words = state.status === "ready" ? state.words : null;
    const shown = useMemo(
        () => (words ? sortWords(filterWords(words, query), sortKey, descending) : []),
        [words, query, sortKey, descending],
    );
    const dueBy = today();

    return (
        <>
            <div className="sidebar-controls">
                <input
                    type="search"
                    placeholder={t("Filter words")}
                    aria-label={t("Filter words")}
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                />
                <div className="sort-row">
                    <select
                        aria-label={t("Sort by")}
                        value={sortKey}
                        onChange={(event) => setSortKey(event.target.value as SortKey)}
                    >
                        {Object.entries(sortLabels).map(([key, label]) => (
                            <option key={key} value={key}>{t(label)}</option>
                        ))}
                    </select>
                    <button
                        className="icon-button"
                        onClick={() => setDescending(!descending)}
                        title={descending ? t("Descending") : t("Ascending")}
                        aria-label={descending ? t("Sorted descending") : t("Sorted ascending")}
                    >
                        {descending ? "↓" : "↑"}
                    </button>
                    <button
                        className="icon-button"
                        onClick={onReload}
                        title={t("Reload words")}
                        aria-label={t("Reload words")}
                    >
                        ↻
                    </button>
                </div>
                {words && query && (
                    <span className="count">
                        {t("{shown} of {count}", { shown: shown.length, count: words.length })}
                    </span>
                )}
            </div>
            {state.status === "loading" && <p className="sidebar-note">{t("Loading words…")}</p>}
            {state.status === "error" && (
                <div className="sidebar-note error">
                    <p>{state.message}</p>
                    <button onClick={onReload}>{t("Try again")}</button>
                </div>
            )}
            {words && shown.length === 0 && (
                <p className="sidebar-note">{query ? t("No words match.") : t("No Anki words yet.")}</p>
            )}
            <ul className="word-list">
                {shown.map((word) => (
                    <li key={word.noteId}>
                        <button className="word" onClick={() => onPick(word)} title={t("Add to message")}>
                            <span className="word-main">
                                <span className="word-text">{word.word}</span>
                                <span className="word-meaning">{word.meaning}</span>
                            </span>
                            <span className="word-side">
                                <span className={word.due <= dueBy ? "due overdue" : "due"}>{word.due}</span>
                                <span className="word-detail">
                                    {[word.partOfSpeech, t("{days}d", { days: word.intervalDays })].filter(Boolean)
                                        .join(" · ")}
                                </span>
                            </span>
                        </button>
                    </li>
                ))}
            </ul>
        </>
    );
}
