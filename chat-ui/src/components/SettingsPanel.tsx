// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";
import {
    type AnkiDeck,
    type AnkiState,
    chooseAnkiDecks,
    describeAnki,
    fetchAnkiDecks,
    linkAnki,
    unlinkAnki,
} from "../lib/anki";
import { newId } from "../lib/ids";

import { fetchOpenRouterModels, type ListedModel, type ModelKind } from "../lib/models";
import { isAskable, newQuestion, type ProfileQuestion, type QuestionOption } from "../lib/questions";
import type { WordSet } from "../lib/sets";
import {
    ACCENTS,
    type ChatContext,
    exerciseVocabularyOf,
    LANGUAGE_PLACEHOLDER,
    LANGUAGES,
    LEVEL_PLACEHOLDER,
    type Settings,
    TEXT_SIZES,
    THEMES,
    TRANSLATION_LANGUAGES,
    WORDS_PLACEHOLDER,
} from "../lib/settings";
import { LevelPicker } from "./Level";
import { ModelPicker, OpenChoice } from "./ModelPicker";
import { SidePanel } from "./SidePanel";

export type SettingsTab = "general" | "models" | "content" | "questions" | "exercises" | "look";

const TABS: { id: SettingsTab; label: string }[] = [
    { id: "general", label: "General" },
    { id: "models", label: "Models" },
    { id: "content", label: "Prompts" },
    { id: "questions", label: "Questions" },
    { id: "exercises", label: "Exercises" },
    { id: "look", label: "Look" },
];

interface Props {
    settings: Settings;
    /** The Anki account the user may link, once it is known whether there is one. */
    anki: AnkiState | null;
    onAnki: (anki: AnkiState) => void;
    /** Says that other Anki decks were chosen, whose words are to be fetched. */
    onDecks: () => void;
    /** The sets of words of the language being learned, which the exercises can be given. */
    sets: WordSet[];
    tab: SettingsTab;
    onTab: (tab: SettingsTab) => void;
    onChange: (settings: Settings) => void;
    onClose: () => void;
}

interface TabProps {
    settings: Settings;
    onChange: (settings: Settings) => void;
}

/** The decks of the linked collection, to choose those whose words are had. */
function AnkiDecks({ onDecks }: { onDecks: () => void }) {
    const [decks, setDecks] = useState<AnkiDeck[] | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let current = true;
        fetchAnkiDecks().then(
            (listed) => current && setDecks(listed),
            (failed: Error) => current && setError(failed.message),
        );
        return () => {
            current = false;
        };
    }, []);

    function toggle(deck: AnkiDeck) {
        if (!decks) {
            return;
        }
        // the decks inside it go with it, and can be changed one by one afterwards
        const ticked = !deck.chosen;
        const goes = (each: AnkiDeck) => each.id === deck.id || each.name.startsWith(`${deck.name}::`);
        const chosen = decks.filter((each) => (goes(each) ? ticked : each.chosen)).map((each) => each.id);
        setError(null);
        chooseAnkiDecks(chosen).then(
            (listed) => {
                setDecks(listed);
                onDecks();
            },
            (failed: Error) => setError(failed.message),
        );
    }

    return (
        <fieldset className="anki-decks">
            <legend>Decks</legend>
            {decks === null && !error && <small className="import-status">Loading the decks…</small>}
            {decks?.map((deck) => {
                const parts = deck.name.split("::");
                return (
                    <label key={deck.id} className="check" style={{ paddingLeft: (parts.length - 1) * 18 }}>
                        <input type="checkbox" checked={deck.chosen} onChange={() => toggle(deck)} />
                        <span title={deck.name}>{parts[parts.length - 1]}</span>
                        <small>{deck.total_cards} cards</small>
                    </label>
                );
            })}
            {error && <small className="import-status error">{error}</small>}
            {decks && (
                <small className="import-status">
                    The words of unticked decks are left out of the Anki tab and the import. Decks made later are
                    ticked.
                </small>
            )}
        </fieldset>
    );
}

/** Links an Anki account, or says how the linked one is doing and unlinks it. */
function AnkiAccount(
    { anki, onAnki, onDecks }: { anki: AnkiState | null; onAnki: (anki: AnkiState) => void; onDecks: () => void },
) {
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    function settle(asked: Promise<AnkiState>) {
        setBusy(true);
        setError(null);
        asked.then(
            (state) => {
                setPassword("");
                onAnki(state);
            },
            (failed: Error) => setError(failed.message),
        ).finally(() => setBusy(false));
    }

    if (anki === null) {
        return <small className="import-status">Asking whether an Anki account is linked…</small>;
    }
    if (anki.linked) {
        return (
            <>
                <div className="anki-account">
                    <span>
                        AnkiWeb account linked
                        <small className={anki.error ? "error" : undefined}>{describeAnki(anki)}</small>
                    </span>
                    <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                            window.confirm("Unlink your Anki account? Its words stay in the vocabulary.")
                            && settle(unlinkAnki())}
                    >
                        Unlink
                    </button>
                </div>
                {error && <small className="import-status error">{error}</small>}
                {anki.last_sync !== null && <AnkiDecks onDecks={onDecks} />}
            </>
        );
    }
    return (
        <form
            onSubmit={(event) => {
                event.preventDefault();
                settle(linkAnki(username.trim(), password));
            }}
        >
            <label className="field">
                <span>AnkiWeb email</span>
                <input
                    type="email"
                    autoComplete="username"
                    spellCheck={false}
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                />
            </label>
            <label className="field">
                <span>AnkiWeb password</span>
                <span className="input-row">
                    <input
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                    />
                    <button type="submit" disabled={busy || !username.trim() || !password}>
                        {busy ? "Linking…" : "Link"}
                    </button>
                </span>
                <small>
                    Your password is only used to log in once, and is not kept. A copy of your collection is kept on
                    this server and synced every few minutes, for the Anki tab and the vocabulary.
                </small>
            </label>
            {error && <small className="import-status error" role="alert">{error}</small>}
        </form>
    );
}

function GeneralTab(
    { settings, onChange, anki, onAnki, onDecks }: TabProps & {
        anki: AnkiState | null;
        onAnki: (anki: AnkiState) => void;
        onDecks: () => void;
    },
) {
    const [showKey, setShowKey] = useState(false);
    const ankiWords = anki?.linked ?? false;

    return (
        <>
            <h3>Language</h3>
            <label className="field">
                <span>Language you are learning</span>
                <select
                    value={settings.language}
                    onChange={(event) => onChange({ ...settings, language: event.target.value })}
                >
                    {LANGUAGES.map((language) => <option key={language} value={language}>{language}</option>)}
                </select>
                <small>Used for spelling, sentence checks, prompts and the vocabulary.</small>
            </label>
            <div className="field">
                <span>Your level</span>
                <LevelPicker
                    label="Your level"
                    value={settings.level}
                    onChange={(level) => onChange({ ...settings, level })}
                />
                <small>
                    Fills <code>{LEVEL_PLACEHOLDER}</code> in your prompts.
                </small>
            </div>
            <label className="field">
                <span>Translate into</span>
                <Choice
                    options={TRANSLATION_LANGUAGES}
                    value={settings.translateInto}
                    onChange={(translateInto) => onChange({ ...settings, translateInto })}
                />
                <small>The language text you select is translated into, and exercises explain in.</small>
            </label>
            <h3>Anki</h3>
            <AnkiAccount anki={anki} onAnki={onAnki} onDecks={onDecks} />
            {ankiWords && (
                <>
                    <label className="toggle">
                        <span>
                            Import Anki words
                            <small>Adds your Anki words to the vocabulary.</small>
                        </span>
                        <input
                            type="checkbox"
                            checked={settings.importAnki}
                            onChange={(event) => onChange({ ...settings, importAnki: event.target.checked })}
                        />
                    </label>
                    <label className="field">
                        <span>Import them as</span>
                        <select
                            value={settings.ankiLanguage}
                            onChange={(event) => onChange({ ...settings, ankiLanguage: event.target.value })}
                        >
                            {LANGUAGES.map((language) => <option key={language} value={language}>{language}</option>)}
                        </select>
                        <small>The language your Anki words are in.</small>
                    </label>
                </>
            )}
            <h3>OpenRouter</h3>
            <label className="field">
                <span>API key</span>
                <span className="input-row">
                    <input
                        type={showKey ? "text" : "password"}
                        autoComplete="off"
                        spellCheck={false}
                        placeholder="sk-or-…"
                        value={settings.apiKey}
                        onChange={(event) => onChange({ ...settings, apiKey: event.target.value.trim() })}
                    />
                    <button type="button" onClick={() => setShowKey(!showKey)}>
                        {showKey ? "Hide" : "Show"}
                    </button>
                </span>
                <small>Kept in this browser only, and sent to openrouter.ai with each message.</small>
            </label>
        </>
    );
}

function ModelsTab({ settings, onChange }: TabProps) {
    const [listed, setListed] = useState<Partial<Record<ModelKind, ListedModel[]>>>({});
    const ids = (kind: ModelKind) => (listed[kind] ?? []).map((model) => model.id);
    const speechModel = settings.speechModel;
    const voices = speechModel.url
        ? []
        : listed.speech?.find((model) => model.id === speechModel.model)?.voices ?? [];

    // suggestions only; every model can be typed without them
    useEffect(() => {
        let stopped = false;
        for (const kind of ["text", "reasoning", "vision", "decisions", "speech", "image", "embeddings"] as const) {
            fetchOpenRouterModels(kind).then(
                (found) => stopped || setListed((current) => ({ ...current, [kind]: found })),
                () => undefined,
            );
        }
        return () => {
            stopped = true;
        };
    }, []);

    const picker = (
        key:
            | "model"
            | "translationModel"
            | "reasoningModel"
            | "profileModel"
            | "speechModel"
            | "embeddingModel"
            | "imageModel"
            | "visionModel",
        label: string,
        kind: ModelKind,
        none?: string,
    ) => (
        <ModelPicker
            label={label}
            value={settings[key]}
            onChange={(chosen) => onChange({ ...settings, [key]: chosen })}
            listed={ids(kind)}
            none={none}
        />
    );

    return (
        <>
            <p className="hint">
                Each model is one of{" "}
                <a href="https://openrouter.ai/models" target="_blank" rel="noreferrer">OpenRouter's</a>, asked with
                your key, or one on a server that takes OpenAI's requests, such as one running on this machine, asked at
                its address. Such a server's key is kept with your settings.
            </p>
            <h3>Writing</h3>
            <div className="field">
                <span>Chat and text model</span>
                {picker("model", "Chat and text model", "text")}
                <small>
                    Answers in the chat, and makes and checks the exercises. It answers without reasoning first.
                </small>
            </div>
            <div className="field">
                <span>Translation model</span>
                {picker("translationModel", "Translation model", "text", "the chat model")}
                <small>Translates the text you select. A small, quick model does this well.</small>
            </div>
            <div className="field">
                <span>Reasoning model</span>
                {picker("reasoningModel", "Reasoning model", "reasoning", "the chat model")}
                <small>Thinks over what needs it before it answers. The list has the models that can reason.</small>
            </div>

            <h3>Checking</h3>
            <div className="field">
                <span>Sentence check model</span>
                {picker("profileModel", "Sentence check model", "decisions")}
                <small>
                    Answers the questions about each sentence you finish typing in the chat, and sorts new words into
                    categories. It is a decision model: a server of your own is asked at <code>/decisions</code>{" "}
                    under its address.
                </small>
            </div>

            <h3>Speech</h3>
            <div className="field">
                <span>Speech model</span>
                {picker("speechModel", "Speech model", "speech")}
                <small>Reads the books, the replies and the stories aloud.</small>
            </div>
            <div className="field">
                <span>Voice</span>
                <OpenChoice
                    label="Voice"
                    options={voices}
                    placeholder="Voice name"
                    value={settings.speechVoice}
                    onChange={(speechVoice) => onChange({ ...settings, speechVoice })}
                />
                <small>The voices there are depend on the speech model.</small>
            </div>

            <h3>Topics</h3>
            <div className="field">
                <span>Embedding model</span>
                {picker("embeddingModel", "Embedding model", "embeddings")}
                <small>
                    Embeds every word of your vocabulary once, and each topic, to find the words of a topic. One that
                    knows many languages works best.
                </small>
            </div>
            <div className="field">
                <span>Image model</span>
                {picker("imageModel", "Image model", "image")}
                <small>Makes the icon of each topic you add, and the pictures of exercises.</small>
            </div>
            <div className="field">
                <span>Vision model</span>
                {picker("visionModel", "Vision model", "vision", "the chat model")}
                <small>
                    Finds where each thing is on the picture of an exercise. It must see pictures, and a small model
                    often points beside them: one such as Gemini Flash, rather than Flash Lite, is far better at it.
                </small>
            </div>
        </>
    );
}

interface ChoiceProps {
    /** What can be chosen, once that is known. */
    options: string[];
    value: string;
    /** What is used while the value is empty. */
    placeholder?: string;
    onChange: (value: string) => void;
}

/**
 * A list to choose from, with everything in it on show. Until it is known
 * what there is to choose from, the value is typed instead.
 */
function Choice({ options, value, placeholder, onChange }: ChoiceProps) {
    if (options.length === 0) {
        return (
            <input
                type="text"
                spellCheck={false}
                placeholder={placeholder}
                value={value}
                onChange={(event) => onChange(event.target.value.trim())}
            />
        );
    }
    return (
        <select value={value} onChange={(event) => onChange(event.target.value)}>
            {/* a value that is not in the list stays as it is until another is chosen */}
            {!options.includes(value) && <option value={value}>{value || placeholder}</option>}
            {options.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
    );
}

function ExercisesTab({ settings, onChange, sets }: TabProps & { sets: WordSet[] }) {
    const vocabulary = exerciseVocabularyOf(settings, settings.language);
    const known = vocabulary === "all" || vocabulary === "none" || sets.some((set) => set.id === vocabulary);

    return (
        <>
            <h3>Topics</h3>
            <label className="toggle">
                <span>
                    Mix topics
                    <small>
                        Bring all the topics you choose together in the exercises. Off, one of them is drawn for each
                        session.
                    </small>
                </span>
                <input
                    type="checkbox"
                    checked={settings.exerciseMixTopics}
                    onChange={(event) => onChange({ ...settings, exerciseMixTopics: event.target.checked })}
                />
            </label>

            <h3>Words</h3>
            <label className="field">
                <span>Words of your vocabulary</span>
                <select
                    value={known ? vocabulary : "all"}
                    onChange={(event) =>
                        onChange({
                            ...settings,
                            exerciseVocabulary: {
                                ...settings.exerciseVocabulary,
                                [settings.language]: event.target.value,
                            },
                        })}
                >
                    <option value="all">Every word</option>
                    {sets.map((set) => <option key={set.id} value={set.id}>Set: {set.name || "Untitled"}</option>)}
                    <option value="none">None</option>
                </select>
                <small>
                    The exercises are given at most 200 of these words, for{" "}
                    {settings.language}. With none, they use any words of your level.
                </small>
            </label>
            <label className="toggle">
                <span>
                    Words that fit the topics
                    <small>
                        Give the 200 words nearest the topics, found with embeddings, rather than the 200 used last.
                        With 20 or more to choose from, the exercises use those words alone; with fewer, they lean on
                        them.
                    </small>
                </span>
                <input
                    type="checkbox"
                    checked={settings.exerciseTopicWords}
                    disabled={vocabulary === "none"}
                    onChange={(event) => onChange({ ...settings, exerciseTopicWords: event.target.checked })}
                />
            </label>
        </>
    );
}

function LookTab({ settings, onChange }: TabProps) {
    return (
        <>
            <h3>Theme</h3>
            <label className="field">
                <span>Light or dark</span>
                <select
                    value={settings.theme}
                    onChange={(event) => onChange({ ...settings, theme: event.target.value as Settings["theme"] })}
                >
                    {Object.entries(THEMES).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
                </select>
            </label>
            <div className="field">
                <span>Colour</span>
                <div className="swatches" role="radiogroup" aria-label="Colour">
                    {Object.entries(ACCENTS).map(([id, accent]) => (
                        <button
                            key={id}
                            type="button"
                            role="radio"
                            aria-checked={settings.accent === id}
                            className="swatch"
                            title={accent.label}
                            aria-label={accent.label}
                            style={{ background: `light-dark(${accent.light}, ${accent.dark})` }}
                            onClick={() => onChange({ ...settings, accent: id as Settings["accent"] })}
                        />
                    ))}
                </div>
                <small>Used for buttons, links and what is selected.</small>
            </div>
            <label className="field">
                <span>Text size</span>
                <select
                    value={settings.textSize}
                    onChange={(event) =>
                        onChange({ ...settings, textSize: event.target.value as Settings["textSize"] })}
                >
                    {Object.entries(TEXT_SIZES).map(([id, size]) => <option key={id} value={id}>{size.label}</option>)}
                </select>
                <small>The size of the app. A book has a size of its own, set in the reader.</small>
            </label>
        </>
    );
}

function ContentTab({ settings, onChange }: TabProps) {
    function updateContext(id: string, change: Partial<ChatContext>) {
        onChange({
            ...settings,
            contexts: settings.contexts.map((context) => (context.id === id ? { ...context, ...change } : context)),
        });
    }

    function addContext() {
        const context = { id: newId(), name: "New context", prompt: "" };
        onChange({ ...settings, contexts: [...settings.contexts, context] });
    }

    function removeContext(id: string) {
        const contexts = settings.contexts.filter((context) => context.id !== id);
        const defaultContextId = settings.defaultContextId === id ? contexts[0].id : settings.defaultContextId;
        onChange({ ...settings, contexts, defaultContextId });
    }

    return (
        <>
            <h3>Keywords</h3>
            <p className="hint">Write these in a prompt, and each is replaced by what it stands for:</p>
            <dl className="keywords">
                <div>
                    <dt>
                        <code>{LANGUAGE_PLACEHOLDER}</code>
                    </dt>
                    <dd>the language you are learning ({settings.language})</dd>
                </div>
                <div>
                    <dt>
                        <code>{LEVEL_PLACEHOLDER}</code>
                    </dt>
                    <dd>your level in it ({settings.level})</dd>
                </div>
                <div>
                    <dt>
                        <code>{WORDS_PLACEHOLDER}</code>
                    </dt>
                    <dd>the words of the set in use, picked in the Vocabulary tab</dd>
                </div>
                <div>
                    <dt>
                        <code>{"{{words:Name}}"}</code>
                    </dt>
                    <dd>the words of the set of that name</dd>
                </div>
            </dl>
            <h3>Contexts</h3>
            <p className="hint">A context is the instruction a chat starts with.</p>
            {settings.contexts.map((context) => (
                <fieldset key={context.id} className="context">
                    <div className="input-row">
                        <input
                            type="text"
                            aria-label="Context name"
                            value={context.name}
                            onChange={(event) => updateContext(context.id, { name: event.target.value })}
                        />
                        <button
                            type="button"
                            onClick={() => removeContext(context.id)}
                            disabled={settings.contexts.length === 1}
                        >
                            Delete
                        </button>
                    </div>
                    <textarea
                        rows={5}
                        aria-label="Context instructions"
                        placeholder="Instructions for the model"
                        value={context.prompt}
                        onChange={(event) => updateContext(context.id, { prompt: event.target.value })}
                    />
                    <label className="check">
                        <input
                            type="radio"
                            name="default-context"
                            checked={settings.defaultContextId === context.id}
                            onChange={() => onChange({ ...settings, defaultContextId: context.id })}
                        />
                        Use for new chats
                    </label>
                </fieldset>
            ))}
            <button type="button" onClick={addContext}>Add context</button>

            <h3>Speech</h3>
            <label className="field">
                <span>How to read</span>
                <textarea
                    rows={4}
                    placeholder="For example: Speak {{language}} slowly and clearly."
                    value={settings.speechDirection}
                    onChange={(event) => onChange({ ...settings, speechDirection: event.target.value })}
                />
                <small>
                    Passed to the speech model as a direction, with <code>{LANGUAGE_PLACEHOLDER}</code> and{" "}
                    <code>{LEVEL_PLACEHOLDER}</code> filled in. It is not read aloud.
                </small>
            </label>
        </>
    );
}

function QuestionEditor(
    { question, onChange, onDelete }: {
        question: ProfileQuestion;
        onChange: (change: Partial<ProfileQuestion>) => void;
        onDelete: () => void;
    },
) {
    const scale = question.kind === "score";

    function updateOption(index: number, change: Partial<QuestionOption>) {
        onChange({
            options: question.options.map((option, at) => (at === index ? { ...option, ...change } : option)),
        });
    }

    return (
        <fieldset className="context">
            <div className="input-row">
                <input
                    type="text"
                    aria-label="Question title"
                    placeholder="Title"
                    value={question.title}
                    onChange={(event) => onChange({ title: event.target.value })}
                />
                <button type="button" onClick={onDelete}>Delete</button>
            </div>
            <textarea
                rows={3}
                aria-label="What to ask"
                placeholder="What to ask about the sentence"
                value={question.instructions}
                onChange={(event) => onChange({ instructions: event.target.value })}
            />
            <label className="check">
                Answered with
                <select
                    value={question.kind}
                    onChange={(event) => onChange({ kind: event.target.value as ProfileQuestion["kind"] })}
                >
                    <option value="choice">one of these options</option>
                    <option value="score">a place on this scale</option>
                </select>
            </label>
            <small className="hint">
                From the worst {scale ? "level" : "option"}{" "}
                to the best: the bar of the answer is fuller the further down the list it is.
            </small>
            {question.options.map((option, index) => (
                <div key={index} className="input-row option-row">
                    <input
                        type="text"
                        className="option-label"
                        aria-label={scale ? "Level name" : "Option name"}
                        placeholder={scale ? "Level" : "Option"}
                        value={option.label}
                        onChange={(event) => updateOption(index, { label: event.target.value })}
                    />
                    <input
                        type="text"
                        aria-label="When it applies"
                        placeholder="When it applies"
                        value={option.description}
                        onChange={(event) => updateOption(index, { description: event.target.value })}
                    />
                    <button
                        type="button"
                        className="icon-button"
                        title="Remove"
                        aria-label={`Remove ${option.label || "option"}`}
                        disabled={question.options.length <= 2}
                        onClick={() => onChange({ options: question.options.filter((_, at) => at !== index) })}
                    >
                        ×
                    </button>
                </div>
            ))}
            <div className="input-row">
                <button
                    type="button"
                    onClick={() => onChange({ options: [...question.options, { label: "", description: "" }] })}
                >
                    {scale ? "Add level" : "Add option"}
                </button>
            </div>
            {!isAskable(question) && (
                <small className="hint error">
                    Not asked yet: it needs something to ask and at least two{" "}
                    {scale ? "levels" : "options"}, each with a name of its own.
                </small>
            )}
        </fieldset>
    );
}

function QuestionsTab({ settings, onChange }: TabProps) {
    const questions = settings.questions;

    function update(id: string, change: Partial<ProfileQuestion>) {
        onChange({
            ...settings,
            questions: questions.map((question) => (question.id === id ? { ...question, ...change } : question)),
        });
    }

    return (
        <>
            <h3>Questions about each sentence</h3>
            <p className="hint">
                Each sentence you finish typing in the chat is sent to the sentence check model with these questions.
                Turn them on and off in the Checks panel, where the answers are shown as well.
            </p>
            {questions.map((question) => (
                <QuestionEditor
                    key={question.id}
                    question={question}
                    onChange={(change) => update(question.id, change)}
                    onDelete={() =>
                        onChange({ ...settings, questions: questions.filter((other) => other.id !== question.id) })}
                />
            ))}
            <button type="button" onClick={() => onChange({ ...settings, questions: [...questions, newQuestion()] })}>
                Add question
            </button>
        </>
    );
}

export function SettingsPanel({ settings, anki, onAnki, onDecks, sets, tab, onTab, onChange, onClose }: Props) {
    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && onClose();
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [onClose]);

    return (
        <SidePanel
            title="Settings"
            onClose={onClose}
            tabs={
                <div className="tabs" role="tablist">
                    {TABS.map(({ id, label }) => (
                        <button
                            key={id}
                            role="tab"
                            aria-selected={tab === id}
                            onClick={() => onTab(id)}
                        >
                            {label}
                        </button>
                    ))}
                </div>
            }
        >
            <div className="settings-body" role="tabpanel">
                {tab === "general" && (
                    <GeneralTab
                        settings={settings}
                        onChange={onChange}
                        anki={anki}
                        onAnki={onAnki}
                        onDecks={onDecks}
                    />
                )}
                {tab === "models" && <ModelsTab settings={settings} onChange={onChange} />}
                {tab === "content" && <ContentTab settings={settings} onChange={onChange} />}
                {tab === "questions" && <QuestionsTab settings={settings} onChange={onChange} />}
                {tab === "exercises" && <ExercisesTab settings={settings} onChange={onChange} sets={sets} />}
                {tab === "look" && <LookTab settings={settings} onChange={onChange} />}
            </div>
        </SidePanel>
    );
}
