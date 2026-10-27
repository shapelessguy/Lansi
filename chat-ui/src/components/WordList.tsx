// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useMemo, useState } from "react";

import type { WordsState } from "../App";
import { type AnkiDeck, chooseAnkiDecks, fetchAnkiDecks } from "../lib/anki";
import { t } from "../lib/i18n";
import { filterWords, type SortKey, sortLabels, sortWords, type Word } from "../lib/words";
import { AnkiDecks, deckAndInside, DeckExplorer } from "./AnkiDecks";

interface Props {
    state: WordsState;
    onReload: () => void;
    onPick: (word: Word) => void;
    /** Says that other decks were ticked, whose words are to be fetched. */
    onDecks: () => void;
}

function today(): string {
    const now = new Date();
    const pad = (value: number) => String(value).padStart(2, "0");
    return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function WordList({ state, onReload, onPick, onDecks }: Props) {
    const [sortKey, setSortKey] = useState<SortKey>("due");
    const [descending, setDescending] = useState(false);
    const [query, setQuery] = useState("");
    const [decks, setDecks] = useState<AnkiDeck[] | null>(null);
    const [decksError, setDecksError] = useState<string | null>(null);
    // the deck whose words alone are shown, or null for every deck ticked
    const [shownDeck, setShownDeck] = useState<number | null>(null);
    const [explored, setExplored] = useState<AnkiDeck | null>(null);

    const words = state.status === "ready" ? state.words : null;

    // the decks are asked for again with the words, as after a sync
    useEffect(() => {
        if (!words) {
            return;
        }
        let current = true;
        fetchAnkiDecks().then(
            (listed) => {
                if (current) {
                    setDecks(listed);
                    setDecksError(null);
                }
            },
            (failed: Error) => current && setDecksError(failed.message),
        );
        return () => {
            current = false;
        };
    }, [words]);

    function toggle(deck: AnkiDeck) {
        if (!decks) {
            return;
        }
        // the decks inside it go with it, and can be changed one by one afterwards
        const ticked = !deck.chosen;
        const goes = deckAndInside(decks, deck);
        const chosen = decks.filter((each) => (goes.has(each.id) ? ticked : each.chosen)).map((each) => each.id);
        setDecksError(null);
        chooseAnkiDecks(chosen).then(
            (listed) => {
                setDecks(listed);
                onDecks();
            },
            (failed: Error) => setDecksError(failed.message),
        );
    }

    const inDeck = useMemo(() => {
        const deck = decks?.find((each) => each.id === shownDeck);
        return deck && decks ? deckAndInside(decks, deck) : null;
    }, [decks, shownDeck]);
    const shown = useMemo(
        () =>
            words
                ? sortWords(
                    filterWords(inDeck ? words.filter((word) => inDeck.has(word.deckId)) : words, query),
                    sortKey,
                    descending,
                )
                : [],
        [words, inDeck, query, sortKey, descending],
    );
    const dueBy = today();

    return (
        <>
            <div className="sidebar-controls">
                <AnkiDecks
                    decks={decks}
                    error={decksError}
                    shown={shownDeck}
                    onShow={setShownDeck}
                    onToggle={toggle}
                    onExplore={setExplored}
                />
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
                {words && (query || inDeck) && (
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
                <p className="sidebar-note">{query || inDeck ? t("No words match.") : t("No Anki words yet.")}</p>
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
            {explored && <DeckExplorer deck={explored} onClose={() => setExplored(null)} />}
        </>
    );
}
