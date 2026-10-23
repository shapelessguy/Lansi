// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import {
    type Book,
    type BookSection,
    type BookVersion,
    fetchBlockTokens,
    fetchBook,
    fetchTransformPrompts,
    keptStretches,
    PART_SHARE,
    partFits,
    REASONING_SHARE,
    sectionKey,
    storyAt,
    type StoryPart,
    storyParts,
    stretchTokens,
    stripBook,
    suggestedStories,
    transformBook,
    type TransformPrompt,
    type VersionKind,
} from "../lib/books";
import { type Message, t } from "../lib/i18n";
import { amount, modelFacts } from "../lib/inspect";
import { modelRequest, orModel } from "../lib/models";
import type { Settings } from "../lib/settings";
import type { BackgroundTask } from "../lib/tasks";
import { PromptKeywords } from "./PromptKeywords";

interface Props {
    /** The book, or the version of it, the new version is made from, by its id. */
    sourceId: string;
    /** What the book or the version is called, to say what the new one is made from. */
    sourceName: string;
    /** For the keywords of a prompt to be shown with what they stand for. */
    settings: Settings;
    /** A prompt with its keywords filled in, as every prompt of the learner's is. */
    expand: (prompt: string) => string;
    /** Told the settings with a prompt saved, changed or deleted. */
    onSettingsChange: (settings: Settings) => void;
    onClose: () => void;
    /** Told the version that was made. */
    onMade: (version: BookVersion) => void;
    /** Told the task a transformed version is being made in. */
    onStarted: (task: BackgroundTask) => void;
}

type SourceState =
    | { status: "loading" }
    | { status: "error"; message: string }
    | { status: "ready"; book: Book };

/** The ways of making a version, each with what its tab says. */
const KINDS: { kind: VersionKind; label: Message }[] = [
    { kind: "stripped", label: "Strip" },
    { kind: "transformed", label: "Transform" },
];

/** What the prompts the server offers are called, by their ids; one it does not name is called by its id. */
const PROMPT_NAMES: Record<string, Message> = {
    translate: "Translate into the language you learn",
    level: "Rewrite for your level",
    custom: "Custom",
};

/** A prompt of the learner's own, which starts empty, offered after those of the server and those saved. */
const CUSTOM_PROMPT: TransformPrompt = { id: "custom", prompt: "" };

/** How a saved prompt is told from the others in the list of prompts. */
const SAVED = "saved:";

/** A prompt to choose from, with what the list calls it. */
interface Offered extends TransformPrompt {
    name: string;
}

/** The colours the stories are told apart by, in the order they start, again from the first after the last. */
const STORY_HUES = [210, 25, 140, 290, 50, 340, 175, 95];

function storyColour(index: number): string {
    return `hsl(${STORY_HUES[index % STORY_HUES.length]} 65% 50%)`;
}

function flipped(set: ReadonlySet<string>, key: string): Set<string> {
    const next = new Set(set);
    if (!next.delete(key)) {
        next.add(key);
    }
    return next;
}

/**
 * Where a new version of a book is made, from the book or from one of its
 * versions. A stripped version is made by leaving out sections of the tree
 * of the book, each with all under it. A transformed one is written anew as
 * a prompt says, of the sections that are ticked; a story starts with each
 * section marked as one and goes on until the next, and each is
 * transformed apart from the others.
 */
export function BookVersionEditor(
    { sourceId, sourceName, settings, expand, onSettingsChange, onClose, onMade, onStarted }: Props,
) {
    const [source, setSource] = useState<SourceState>({ status: "loading" });
    const [kind, setKind] = useState<VersionKind>("stripped");
    // the name of the version each way would make
    const [names, setNames] = useState<Record<VersionKind, string>>(() => ({
        stripped: t("Stripped"),
        transformed: t("Transformed"),
    }));
    // the sections left out of each way, by their keys, and those whose sections are hidden
    const [left, setLeft] = useState<Record<VersionKind, ReadonlySet<string>>>({
        stripped: new Set(),
        transformed: new Set(),
    });
    const [closed, setClosed] = useState<ReadonlySet<string>>(new Set());
    // the sections that are stories of their own, by their keys
    const [stories, setStories] = useState<ReadonlySet<string>>(new Set());
    // whether what is not transformed is in the version as it is, or left out of it
    const [untouched, setUntouched] = useState<"kept" | "left">("kept");
    // whether the model reasons before it writes each part
    const [think, setThink] = useState(true);
    // the prompts the server offers to start from
    const [prompts, setPrompts] = useState<TransformPrompt[]>([]);
    const [promptId, setPromptId] = useState(CUSTOM_PROMPT.id);
    // the name a prompt is being saved under, while it is
    const [naming, setNaming] = useState<string | null>(null);
    const [prompt, setPrompt] = useState("");
    // what the prompt says, for what the server offers not to take the place of what was written
    const written = useRef(prompt);
    written.current = prompt;
    const [making, setMaking] = useState(false);
    const [error, setError] = useState<string | null>(null);
    // the tokens each block takes when it is sent, by its place, once the server has counted them
    const [tokens, setTokens] = useState<number[] | null>(null);
    // why they could not be counted, if they could not
    const [tokensError, setTokensError] = useState<string | null>(null);
    // how many tokens the reasoning model, which transforms the parts, takes in at once: null if it is
    // not known, and undefined while it is looked up
    const [contextWindow, setContextWindow] = useState<number | null | undefined>(undefined);
    const reasoning = orModel(settings.reasoningModel, settings.model);
    const reasoningId = reasoning.url ? "" : reasoning.model;

    useEffect(() => {
        let current = true;
        fetchBook(sourceId).then(
            (book) => current && setSource({ status: "ready", book }),
            (failed: Error) => current && setSource({ status: "error", message: failed.message }),
        );
        return () => {
            current = false;
        };
    }, [sourceId]);

    useEffect(() => {
        let current = true;
        setTokens(null);
        setTokensError(null);
        fetchBlockTokens(sourceId).then(
            (counted) => current && setTokens(counted),
            (failed: Error) => current && setTokensError(failed.message),
        );
        return () => {
            current = false;
        };
    }, [sourceId]);

    useEffect(() => {
        let current = true;
        if (reasoningId) {
            setContextWindow(undefined);
            modelFacts(reasoningId).then((facts) => current && setContextWindow(facts?.contextLength ?? null));
        } else {
            setContextWindow(null);
        }
        return () => {
            current = false;
        };
    }, [reasoningId]);

    useEffect(() => {
        let current = true;
        fetchTransformPrompts().then((offered) => {
            if (current && offered.length > 0) {
                setPrompts(offered);
                // the first is chosen unless the learner began a prompt of their own
                if (!written.current) {
                    setPromptId(offered[0].id);
                    setPrompt(offered[0].prompt);
                }
            }
        }, () => undefined);
        return () => {
            current = false;
        };
    }, []);

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => {
            if (event.key === "Escape" && !making) {
                event.stopPropagation();
                onClose();
            }
        };
        document.addEventListener("keydown", onKeyDown, true);
        return () => document.removeEventListener("keydown", onKeyDown, true);
    }, [making, onClose]);

    const book = source.status === "ready" ? source.book : null;
    const shownLeft = left[kind];
    const kept = book ? keptStretches(book.sections, shownLeft) : [];
    const keptCount = kept.reduce((count, [start, end]) => count + end - start, 0);
    const parts = book && kind === "transformed" ? storyParts(book.sections, shownLeft, stories) : [];
    const partTokens = parts.map((part) => (tokens ? stretchTokens(part.stretches, tokens) : null));
    // a book is transformed only once every part is known to fit in what the reasoning model takes in
    const tooLarge = typeof contextWindow === "number"
        ? partTokens.filter((each) => each !== null && !partFits(each, contextWindow)).length
        : 0;
    const allFit = typeof contextWindow === "number" && partTokens.every((each) => each !== null) && tooLarge === 0;
    // the stories in the order they start, for each to have its colour
    const storyOrder = [...stories].sort((a, b) => Number.parseInt(a, 10) - Number.parseInt(b, 10));
    const options: Offered[] = [
        ...prompts.map((each) => ({ ...each, name: each.id in PROMPT_NAMES ? t(PROMPT_NAMES[each.id]) : each.id })),
        ...settings.transformPrompts.map((each) => ({ id: SAVED + each.id, prompt: each.prompt, name: each.name })),
        { ...CUSTOM_PROMPT, name: t(PROMPT_NAMES.custom) },
    ];
    const offered = options.find((each) => each.id === promptId);
    const savedId = promptId.startsWith(SAVED) ? promptId.slice(SAVED.length) : null;

    /** Keeps what the prompt says under a new name, and chooses it. */
    function saveAs(name: string) {
        const id = `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
        onSettingsChange({
            ...settings,
            transformPrompts: [...settings.transformPrompts, { id, name, prompt }],
        });
        setPromptId(SAVED + id);
        setNaming(null);
    }

    /** Keeps what the saved prompt that is chosen now says. */
    function saveChosen() {
        onSettingsChange({
            ...settings,
            transformPrompts: settings.transformPrompts.map((each) => each.id === savedId ? { ...each, prompt } : each),
        });
    }

    /** Deletes the saved prompt that is chosen, leaving what it says to be changed or saved again. */
    function deleteChosen() {
        onSettingsChange({
            ...settings,
            transformPrompts: settings.transformPrompts.filter((each) => each.id !== savedId),
        });
        setPromptId(CUSTOM_PROMPT.id);
    }

    /** The title of the section of that key, for a part to be called by its story. */
    function titleOf(key: string, shown: BookSection[] = book?.sections ?? []): string {
        for (const section of shown) {
            if (sectionKey(section) === key) {
                return section.title || t("Beginning");
            }
            const found = titleOf(key, section.sections ?? []);
            if (found) {
                return found;
            }
        }
        return "";
    }

    /** What a part is called: the title of its story, or what comes before the first story. */
    function partTitle(part: StoryPart): string {
        return part.story !== null
            ? titleOf(part.story)
            : t(stories.size === 0 ? "All as one story" : "Before the first story");
    }

    function make() {
        if (!book) {
            return;
        }
        setMaking(true);
        setError(null);
        const failed = (reason: Error) => {
            setError(reason.message);
            setMaking(false);
        };
        if (kind === "stripped") {
            stripBook(sourceId, names.stripped.trim(), kept).then(onMade, failed);
        } else {
            transformBook(sourceId, {
                name: names.transformed.trim(),
                prompt: expand(prompt),
                parts: parts.map((part) => part.stretches),
                untouched,
                model: modelRequest(reasoning),
                reasoning: think,
                reasoningBudget: typeof contextWindow === "number"
                    ? Math.floor(contextWindow * REASONING_SHARE)
                    : null,
                titles: parts.map(partTitle),
            }, settings.apiKey).then(onStarted, failed);
        }
    }

    /** Whether any section under these is left out, for the one they are under to show it is kept in part. */
    function anyLeft(shown: BookSection[] | undefined): boolean {
        return (shown ?? []).some((section) => shownLeft.has(sectionKey(section)) || anyLeft(section.sections));
    }

    function tree(shown: BookSection[], outLeft: boolean) {
        return (
            <ul>
                {shown.map((section) => {
                    const key = sectionKey(section);
                    const isLeft = outLeft || shownLeft.has(key);
                    const isOpen = !closed.has(key);
                    const isStory = stories.has(key);
                    // the stories are of transforming alone, and are not shown when stripping
                    const its = kind === "transformed" ? storyAt(stories, section.start) : null;
                    const colour = its === null ? undefined : storyColour(storyOrder.indexOf(its));
                    const title = section.title || t("Beginning");
                    return (
                        <li key={key} style={colour ? { borderLeftColor: colour } : undefined}>
                            <div className="contents-row">
                                {section.sections
                                    ? (
                                        <button
                                            className="contents-toggle"
                                            aria-expanded={isOpen}
                                            onClick={() => setClosed(flipped(closed, key))}
                                            aria-label={t(
                                                isOpen ? "Hide the sections under it" : "Show the sections under it",
                                            )}
                                        >
                                            {isOpen ? "▾" : "▸"}
                                        </button>
                                    )
                                    : <span className="contents-toggle" />}
                                <label className={isLeft ? "version-section left" : "version-section"} title={title}>
                                    <input
                                        type="checkbox"
                                        checked={!isLeft}
                                        // one under a section that is left out goes with it
                                        disabled={outLeft || making}
                                        ref={(input) => {
                                            if (input) {
                                                input.indeterminate = !isLeft && anyLeft(section.sections);
                                            }
                                        }}
                                        onChange={() => setLeft({ ...left, [kind]: flipped(shownLeft, key) })}
                                    />
                                    <span className="version-section-title">{title}</span>
                                </label>
                                {kind === "transformed" && (
                                    <button
                                        className={isStory ? "story-chip marked" : "story-chip"}
                                        aria-pressed={isStory}
                                        style={isStory && colour
                                            ? { background: colour, borderColor: colour }
                                            : undefined}
                                        onClick={() => setStories(flipped(stories, key))}
                                        title={t("A new story starts here, and goes on until the next")}
                                    >
                                        {t("Story")}
                                    </button>
                                )}
                                <span className="count">
                                    {t("{count} par.", { count: section.end - section.start })}
                                </span>
                            </div>
                            {section.sections && isOpen && tree(section.sections, isLeft)}
                        </li>
                    );
                })}
            </ul>
        );
    }

    return (
        <div
            className="dialog-backdrop"
            onPointerDown={(event) => event.target === event.currentTarget && !making && onClose()}
        >
            <div className="dialog version-editor" role="dialog" aria-modal="true" aria-label={t("New version")}>
                <p className="dialog-message">{t("New version")}</p>
                <p className="dialog-detail">{t("Made from: {name}", { name: sourceName })}</p>
                <div className="version-kinds" role="tablist">
                    {KINDS.map((each) => (
                        <button
                            key={each.kind}
                            role="tab"
                            aria-selected={kind === each.kind}
                            disabled={making}
                            onClick={() => setKind(each.kind)}
                        >
                            {t(each.label)}
                        </button>
                    ))}
                </div>
                <label className="version-name">
                    {t("Name")}
                    <input
                        value={names[kind]}
                        onChange={(event) => setNames({ ...names, [kind]: event.target.value })}
                        maxLength={80}
                    />
                </label>
                {kind === "stripped"
                    ? (
                        <p className="version-help">
                            {t("Untick what is not the text itself.")}
                        </p>
                    )
                    : (
                        <div className="version-transform">
                            <label className="version-name">
                                {t("Prompt")}
                                <select
                                    value={promptId}
                                    onChange={(event) => {
                                        const chosen = options.find((each) => each.id === event.target.value);
                                        if (chosen) {
                                            setPromptId(chosen.id);
                                            setPrompt(chosen.prompt);
                                            setNaming(null);
                                        }
                                    }}
                                >
                                    {options.map((each) => <option key={each.id} value={each.id}>{each.name}</option>)}
                                </select>
                                {offered && offered.prompt !== prompt && (
                                    <button onClick={() => setPrompt(offered.prompt)}>{t("Undo changes")}</button>
                                )}
                            </label>
                            <div className="version-prompt-saving">
                                {naming === null
                                    ? (
                                        <>
                                            {savedId && (
                                                <button
                                                    className="small"
                                                    onClick={saveChosen}
                                                    disabled={offered?.prompt === prompt || !prompt.trim()}
                                                >
                                                    {t("Save")}
                                                </button>
                                            )}
                                            <button
                                                className="small"
                                                onClick={() => setNaming(savedId ? "" : offered?.name ?? "")}
                                                disabled={!prompt.trim()}
                                            >
                                                {t("Save as…")}
                                            </button>
                                            {savedId && (
                                                <button className="small" onClick={deleteChosen}>{t("Delete")}</button>
                                            )}
                                        </>
                                    )
                                    : (
                                        <form
                                            onSubmit={(event) => {
                                                event.preventDefault();
                                                if (naming.trim()) {
                                                    saveAs(naming.trim());
                                                }
                                            }}
                                        >
                                            <input
                                                autoFocus
                                                value={naming}
                                                maxLength={80}
                                                placeholder={t("Name of the prompt")}
                                                aria-label={t("Name of the prompt")}
                                                onChange={(event) => setNaming(event.target.value)}
                                            />
                                            <button className="small" type="submit" disabled={!naming.trim()}>
                                                {t("Save")}
                                            </button>
                                            <button className="small" type="button" onClick={() => setNaming(null)}>
                                                {t("Cancel")}
                                            </button>
                                        </form>
                                    )}
                            </div>
                            <textarea
                                className="version-prompt"
                                value={prompt}
                                rows={5}
                                onChange={(event) => setPrompt(event.target.value)}
                                aria-label={t("Prompt")}
                            />
                            <details className="version-keywords">
                                <summary>{t("Keywords")}</summary>
                                <PromptKeywords settings={settings} />
                            </details>
                            <div className="version-options">
                                <label>
                                    {t("Parts not ticked")}
                                    <select
                                        value={untouched}
                                        onChange={(event) => setUntouched(event.target.value as "kept" | "left")}
                                    >
                                        <option value="kept">{t("Kept as they are")}</option>
                                        <option value="left">{t("Left out")}</option>
                                    </select>
                                </label>
                                <label
                                    title={t(
                                        "The model reasons before it writes each part: slower and dearer, and perhaps truer to the prompt",
                                    )}
                                >
                                    <input
                                        type="checkbox"
                                        checked={think}
                                        onChange={(event) => setThink(event.target.checked)}
                                    />
                                    {t("Think first")}
                                </label>
                                <span className="version-stories">
                                    {t("Stories")}
                                    {book && (
                                        <button
                                            className="small"
                                            onClick={() => setStories(suggestedStories(book.sections))}
                                            title={t("Mark the sections that look like stories")}
                                        >
                                            {t("Suggest")}
                                        </button>
                                    )}
                                    <button
                                        className="small"
                                        onClick={() => setStories(new Set())}
                                        disabled={stories.size === 0}
                                    >
                                        {t("Clear")}
                                    </button>
                                </span>
                            </div>
                        </div>
                    )}
                <div className="version-tree">
                    {source.status === "loading" && <p className="reader-note">{t("Loading the book…")}</p>}
                    {source.status === "error" && <p className="reader-note error">{source.message}</p>}
                    {book && tree(book.sections, false)}
                </div>
                {kind === "transformed" && parts.length > 0 && (
                    <ul className="story-parts" aria-label={t("The parts transformed one by one")}>
                        {parts.map((part, index) => {
                            const counted = partTokens[index];
                            const over = counted !== null && typeof contextWindow === "number"
                                && !partFits(counted, contextWindow);
                            return (
                                <li key={part.story ?? ""}>
                                    <span
                                        className="story-swatch"
                                        style={part.story === null
                                            ? undefined
                                            : { background: storyColour(storyOrder.indexOf(part.story)) }}
                                    />
                                    {partTitle(part)}
                                    <span className="count">
                                        {t("{count} par.", {
                                            count: part.stretches.reduce(
                                                (count, [start, end]) => count + end - start,
                                                0,
                                            ),
                                        })}
                                    </span>
                                    {counted !== null && (
                                        <span
                                            className={over ? "count part-tokens over" : "count part-tokens"}
                                            title={typeof contextWindow !== "number"
                                                ? t("The tokens the part takes if it is sent as it is")
                                                : t(
                                                    "The tokens the part takes if it is sent as it is, of the {window} the reasoning model takes in at once",
                                                    {
                                                        window: amount(contextWindow),
                                                    },
                                                )}
                                        >
                                            {t("{tokens} tokens", { tokens: amount(counted) })}
                                        </span>
                                    )}
                                </li>
                            );
                        })}
                    </ul>
                )}
                {kind === "transformed" && tokensError && (
                    <p className="sidebar-note error">
                        {t("The tokens could not be counted: {reason}", { reason: tokensError })}
                    </p>
                )}
                {kind === "transformed" && tooLarge > 0 && typeof contextWindow === "number" && (
                    <p className="sidebar-note error">
                        {t(
                            "The parts in red are too long: each must take less than {limit} tokens, a third of what the reasoning model takes in at once. Mark more stories to cut them.",
                            { limit: amount(Math.ceil(contextWindow * PART_SHARE)) },
                        )}
                    </p>
                )}
                {kind === "transformed" && contextWindow === null && (
                    <p className="sidebar-note error">
                        {t("How many tokens the reasoning model takes in at once is not known, so no part can be told to fit.")}
                    </p>
                )}
                {error && <p className="sidebar-note error" role="alert">{error}</p>}
                <div className="dialog-buttons">
                    {book && (
                        <span className="count version-kept">
                            {kind === "stripped"
                                ? t("{kept} of {count} paragraphs kept", { kept: keptCount, count: book.blocks.length })
                                : t("{kept} of {count} paragraphs to transform, in {parts} parts", {
                                    kept: keptCount,
                                    count: book.blocks.length,
                                    parts: parts.length,
                                })}
                        </span>
                    )}
                    <button onClick={onClose} disabled={making}>{t("Cancel")}</button>
                    <button
                        className="primary"
                        onClick={make}
                        disabled={!book || making || keptCount === 0 || !names[kind].trim()
                            || (kind === "transformed" && (!prompt.trim() || !allFit))}
                    >
                        {making ? t("Making the version…") : t(kind === "stripped" ? "Make version" : "Transform")}
                    </button>
                </div>
            </div>
        </div>
    );
}
