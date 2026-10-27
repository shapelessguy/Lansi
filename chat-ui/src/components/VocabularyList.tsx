// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useCallback, useEffect, useMemo, useState } from "react";

import type { ImportStatus } from "../lib/ankiImport";
import { languageName, plural, t } from "../lib/i18n";
import type { WordSet } from "../lib/sets";
import {
    countWords,
    describeUses,
    detailRows,
    fetchEntry,
    fetchVocabulary,
    type FormLayout,
    formsOf,
    type FormTables,
    groupWords,
    labelOf,
    layOutForms,
    type ListedWord,
    listWords,
    loadFlat,
    saveFlat,
    shownIn,
    type SortKey,
    sortLabels,
    type StoredNames,
    translationRow,
    type Vocabulary,
    type VocabularyEntry,
} from "../lib/vocabulary";
import type { TranslationsStatus, WordTranslations } from "../lib/wordTranslations";
import { Check } from "./Check";

interface Props {
    /** Whether the list is on show. It is fetched again each time it comes on show. */
    active: boolean;
    /** The language being learned, whose vocabulary this is. */
    language: string;
    /** The language the words are shown translated into. */
    into: string;
    /** The translating of the words that have no translations in `into`. */
    translations: WordTranslations;
    /** Changes when words were taken in, for the list to be fetched again. */
    revision: number;
    onCount: (words: number) => void;
    /** The sets of words picked out of this vocabulary. */
    sets: WordSet[];
    /** The set `{{words}}` stands for, by its id, if one is in use. */
    activeSetId: string | undefined;
    onActiveSet: (id: string) => void;
    /** Opens the editor for a set, or for a new one. */
    onEditSet: (set: WordSet | null) => void;
    /** The language the Anki words are imported as. */
    ankiLanguage: string;
    /**
     * What the import of the Anki words is doing, or null for a user who has
     * none. It is switched on and off in the settings.
     */
    importing: ImportStatus | null;
}

/** What the translating of the words into `into` is doing, in a line, or nothing if every word is translated. */
function describeTranslations(status: TranslationsStatus, into: string): string {
    const language = languageName(into);
    switch (status.state) {
        case "translating":
            return t("Translating the words into {language}: {count} left", {
                language,
                count: status.remaining ?? "…",
            });
        case "no-key":
            return t("Waiting for an OpenRouter key.");
        case "unavailable":
            return t("The words could not be translated into {language}: {message}", {
                language,
                message: status.message,
            });
        default:
            return status.remaining
                ? plural(
                    status.remaining,
                    "{count} word is not translated into {language} yet.",
                    "{count} words are not translated into {language} yet.",
                    { language },
                )
                : "";
    }
}

/** What the import is doing, in a line. */
function describeImport(importing: ImportStatus): string {
    const left = importing.remaining === null ? "" : t("{count} left", { count: importing.remaining });
    switch (importing.state) {
        case "off":
            return t("off.");
        case "no-key":
            return t("Waiting for an OpenRouter key.");
        case "unavailable":
            return importing.message;
        case "importing":
            return `${t("Importing…")} ${left}`;
        default:
            return importing.remaining === 0 ? t("Every Anki word is in.") : left;
    }
}

type ListState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; vocabulary: Vocabulary };

type EntryState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; entry: VocabularyEntry };

/**
 * The words the checker server has stored, by category. What is stored of a
 * word is fetched when the word is opened.
 */
export function VocabularyList(
    {
        active,
        language,
        into,
        translations,
        ankiLanguage,
        revision,
        onCount,
        importing,
        sets,
        activeSetId,
        onActiveSet,
        onEditSet,
    }: Props,
) {
    const [state, setState] = useState<ListState>({ status: "loading" });
    const [query, setQuery] = useState("");
    const [sort, setSort] = useState<SortKey>("word");
    // There are too many words in a category to have them all on show, so
    // each is opened by hand, or by filtering.
    const [opened, setOpened] = useState<ReadonlySet<string>>(new Set());
    const [flat, setFlat] = useState(loadFlat);
    const [openId, setOpenId] = useState<number | null>(null);
    const [entryState, setEntryState] = useState<EntryState>({ status: "loading" });

    const load = useCallback(() => {
        // what was listed stays on show while it is fetched again
        setState((current) => (current.status === "ready" ? current : { status: "loading" }));
        fetchVocabulary(language).then(
            (vocabulary) => {
                setState({ status: "ready", vocabulary });
                onCount(countWords(vocabulary.words));
            },
            (error: Error) => setState({ status: "error", message: error.message }),
        );
    }, [onCount, language]);

    // the words of another language are not these
    useEffect(() => {
        setState({ status: "loading" });
        setOpenId(null);
    }, [language]);

    useEffect(() => {
        if (active) {
            load();
        }
    }, [active, load, revision]);

    useEffect(() => {
        if (openId === null) {
            return;
        }
        let current = true;
        // what was on show stays while it is fetched again with more translations
        setEntryState((
            state,
        ) => (state.status === "ready" && state.entry.id === openId ? state : { status: "loading" }));
        fetchEntry(openId, language).then(
            (entry) => current && setEntryState({ status: "ready", entry }),
            (error: Error) => current && setEntryState({ status: "error", message: error.message }),
        );
        return () => {
            current = false;
        };
    }, [openId, language, translations.status.translated]);

    const vocabulary = state.status === "ready" ? state.vocabulary : null;
    const activeSet = sets.find((set) => set.id === activeSetId);
    const groups = useMemo(
        () => (vocabulary && !flat ? groupWords(vocabulary, query, sort) : []),
        [vocabulary, query, sort, flat],
    );
    const listed = useMemo(
        () => (vocabulary && flat ? listWords(vocabulary, query, sort) : []),
        [vocabulary, query, sort, flat],
    );
    const isOpen = (category: string) => query.trim() !== "" || opened.has(category);

    function toggleCategory(category: string) {
        const next = new Set(opened);
        if (!next.delete(category)) {
            next.add(category);
        }
        setOpened(next);
    }

    function changeFlat(next: boolean) {
        setFlat(next);
        saveFlat(next);
    }

    function wordItem(word: ListedWord) {
        return (
            <li key={word.id}>
                <button
                    className="word"
                    aria-expanded={openId === word.id}
                    onClick={() => setOpenId(openId === word.id ? null : word.id)}
                >
                    <span className="word-text">{word.lemma}</span>
                    <span className="word-detail">
                        {[
                            flat && labelOf(word.category, vocabulary?.labels ?? {}),
                            describeUses(word),
                            plural(word.forms, "{count} form", "{count} forms"),
                        ]
                            .filter(Boolean).join(" · ")}
                    </span>
                </button>
                {openId === word.id && vocabulary && (
                    <Entry state={entryState} tables={vocabulary.tables} names={vocabulary} into={into} />
                )}
            </li>
        );
    }

    return (
        <>
            <div className="sidebar-controls">
                <div className="sort-row">
                    <input
                        type="search"
                        placeholder={t("Filter words")}
                        aria-label={t("Filter vocabulary")}
                        value={query}
                        onChange={(event) => setQuery(event.target.value)}
                    />
                    <select
                        aria-label={t("Sort by")}
                        value={sort}
                        onChange={(event) => setSort(event.target.value as SortKey)}
                    >
                        {Object.entries(sortLabels).map(([key, label]) => (
                            <option key={key} value={key}>{t(label)}</option>
                        ))}
                    </select>
                    <button
                        className="icon-button"
                        onClick={load}
                        title={t("Reload")}
                        aria-label={t("Reload vocabulary")}
                    >
                        ↻
                    </button>
                </div>
                <Check className="vocabulary-flat" checked={flat} onChange={changeFlat}>
                    {t("One list, without categories")}
                </Check>
                <div className="sort-row">
                    <select
                        aria-label={t("The set of words given to the model")}
                        title={t("The words that {{words}} stands for in your prompts")}
                        value={activeSet?.id ?? ""}
                        onChange={(event) => onActiveSet(event.target.value)}
                    >
                        <option value="">{t("Set in use: every word")}</option>
                        {sets.map((set) => (
                            <option key={set.id} value={set.id}>{t("Set in use: {name}", { name: set.name })}</option>
                        ))}
                    </select>
                    <button disabled={!activeSet} onClick={() => activeSet && onEditSet(activeSet)}>{t("Edit")}</button>
                    <button onClick={() => onEditSet(null)}>{t("New set")}</button>
                </div>
                {importing && (
                    <small
                        className={importing.state === "unavailable" ? "import-status error" : "import-status"}
                        title={importing.message}
                    >
                        {t("Anki import ({language}): {state}", {
                            language: languageName(ankiLanguage),
                            state: describeImport(importing),
                        })}
                    </small>
                )}
                {describeTranslations(translations.status, into) && (
                    <div className="translations-status">
                        <small
                            className={translations.status.state === "unavailable"
                                ? "import-status error"
                                : "import-status"}
                        >
                            {describeTranslations(translations.status, into)}
                        </small>
                        {(translations.status.state === "idle" || translations.status.state === "unavailable") && (
                            <button onClick={translations.start}>
                                {t("Translate them into {language}", { language: languageName(into) })}
                            </button>
                        )}
                    </div>
                )}
            </div>
            {state.status === "loading" && <p className="sidebar-note">{t("Loading vocabulary…")}</p>}
            {state.status === "error" && (
                <div className="sidebar-note error">
                    <p>{state.message}</p>
                    <button onClick={load}>{t("Try again")}</button>
                </div>
            )}
            {vocabulary && groups.length === 0 && listed.length === 0 && (
                <p className="sidebar-note">{query ? t("No words match.") : t("No words are stored yet.")}</p>
            )}
            <div className="vocabulary">
                {groups.map(({ category, words }) => (
                    <section key={category}>
                        <button
                            className="vocabulary-category"
                            aria-expanded={isOpen(category)}
                            onClick={() => toggleCategory(category)}
                        >
                            <span>{labelOf(category, vocabulary?.labels ?? {})}</span>
                            <span className="count">{words.length}</span>
                        </button>
                        {isOpen(category) && <ul className="word-list">{words.map(wordItem)}</ul>}
                    </section>
                ))}
                {listed.length > 0 && <ul className="word-list">{listed.map(wordItem)}</ul>}
            </div>
        </>
    );
}

function Entry(
    { state, tables, names, into }: { state: EntryState; tables: FormTables; names: StoredNames; into: string },
) {
    if (state.status === "loading") {
        return <p className="entry sidebar-note">{t("Loading…")}</p>;
    }
    if (state.status === "error") {
        return <p className="entry sidebar-note error">{state.message}</p>;
    }
    const { entry } = state;
    const language = shownIn(entry, into);
    const several = entry.variants.length > 1;
    // the forms of the word as a whole, such as a spelling it was met in, apart from its variants
    const ofTheWhole = several ? entry.forms.filter((form) => form.variant === 0) : [];
    return (
        <div className="entry">
            {entry.variants.map((variant, index) => (
                <section key={variant.id} className={several ? "entry-variant" : undefined}>
                    {several && <h4 className="entry-variant-title">{index + 1}</h4>}
                    <dl>
                        {[translationRow(variant, language, into, names.labels), ...detailRows(variant.details, names)]
                            .filter((row) =>
                                row !== null
                            )
                            .map((row, index) => (
                                <div key={index}>
                                    <dt>{row.label}</dt>
                                    <dd>
                                        {row.value}
                                        {row.language && <small className="translations-language">{row.language}
                                        </small>}
                                    </dd>
                                </div>
                            ))}
                    </dl>
                    <Forms layout={layOutForms({ ...entry, forms: formsOf(entry, variant) }, tables)} />
                </section>
            ))}
            {ofTheWhole.length > 0 && <Forms layout={layOutForms({ ...entry, forms: ofTheWhole }, tables)} />}
            <dl>
                <div>
                    <dt>{t("stored")}</dt>
                    <dd>{entry.created_at}</dd>
                </div>
            </dl>
        </div>
    );
}

/** The forms of a word, or of one of its variants, laid out in tables and a list. */
function Forms({ layout }: { layout: FormLayout }) {
    return (
        <>
            {layout.tables.map((table) => (
                <table key={table.title} className="forms">
                    <thead>
                        <tr>
                            <th scope="col">{table.title}</th>
                            {table.columns.map((column) => <th key={column} scope="col">{column}</th>)}
                        </tr>
                    </thead>
                    <tbody>
                        {table.rows.map((row) => (
                            <tr key={row.label}>
                                <th scope="row">{row.label}</th>
                                {row.cells.map((cell, index) => (
                                    <td key={index}>
                                        {cell.form || "–"}
                                        {cell.also && <small title={table.also}>{cell.also}</small>}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            ))}
            {layout.others.length > 0 && (
                <dl className="other-forms">
                    {layout.others.map((other, index) => (
                        <div key={index}>
                            <dt>{other.label}</dt>
                            <dd>{other.form}</dd>
                        </div>
                    ))}
                </dl>
            )}
        </>
    );
}
