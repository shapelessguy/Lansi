// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";
import { type AnkiState, describeAnki, linkAnki, unlinkAnki } from "../lib/anki";
import { newId } from "../lib/ids";

import { ask } from "../lib/dialogs";
import { languageName, locale, type Message, t } from "../lib/i18n";
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
} from "../lib/settings";
import { Help } from "./Help";
import { LevelPicker } from "./Level";
import { ModelPicker, OpenChoice } from "./ModelPicker";
import { PromptKeywords } from "./PromptKeywords";
import { SidePanel } from "./SidePanel";
import { T } from "./T";

export type SettingsTab = "general" | "models" | "content" | "questions" | "exercises" | "look";

const TABS: { id: SettingsTab; label: Message }[] = [
    { id: "general", label: "General" },
    { id: "models", label: "Models" },
    { id: "content", label: "Prompts" },
    { id: "questions", label: "Spelling" },
    { id: "exercises", label: "Exercises" },
    { id: "look", label: "Look" },
];

interface Props {
    settings: Settings;
    /** The Anki account the user may link, once it is known whether there is one. */
    anki: AnkiState | null;
    onAnki: (anki: AnkiState) => void;
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

/** Links an Anki account, or says how the linked one is doing and unlinks it. */
function AnkiAccount(
    { anki, onAnki }: { anki: AnkiState | null; onAnki: (anki: AnkiState) => void },
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
        return <small className="import-status">{t("Asking whether an Anki account is linked…")}</small>;
    }
    if (anki.linked) {
        return (
            <>
                <div className="anki-account">
                    <span>
                        {t("AnkiWeb account linked")}
                        <small className={anki.error ? "error" : undefined}>{describeAnki(anki, locale())}</small>
                    </span>
                    <button
                        type="button"
                        disabled={busy}
                        onClick={() =>
                            void ask(t("Unlink your Anki account?"), {
                                detail: t("Its words stay in the vocabulary."),
                                confirm: t("Unlink"),
                            }).then((agreed) => agreed && settle(unlinkAnki()))}
                    >
                        {t("Unlink")}
                    </button>
                </div>
                {error && <small className="import-status error">{error}</small>}
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
                <span>{t("AnkiWeb email")}</span>
                <input
                    type="email"
                    autoComplete="username"
                    spellCheck={false}
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                />
            </label>
            <label className="field">
                <span className="setting-name">
                    {t("AnkiWeb password")}
                    <Help>
                        {t(
                            "Your password is only used to log in once, and is not kept. A copy of your collection is kept on this server and synced every few minutes, for the Anki tab and the vocabulary.",
                        )}
                    </Help>
                </span>
                <span className="input-row">
                    <input
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                    />
                    <button type="submit" disabled={busy || !username.trim() || !password}>
                        {busy ? t("Linking…") : t("Link")}
                    </button>
                </span>
            </label>
            {error && <small className="import-status error" role="alert">{error}</small>}
        </form>
    );
}

function GeneralTab(
    { settings, onChange, anki, onAnki }: TabProps & {
        anki: AnkiState | null;
        onAnki: (anki: AnkiState) => void;
    },
) {
    const ankiWords = anki?.linked ?? false;

    return (
        <>
            <h3>{t("Language")}</h3>
            {/* the level is of the language, so it is chosen beside it */}
            <div className="field">
                <span className="setting-name">
                    {t("Language you are learning, and your level")}
                    <Help>
                        {t("Used for spelling, sentence checks, prompts and the vocabulary.")}{" "}
                        <T
                            message="The level fills {keyword} in your prompts."
                            values={{ keyword: <code>{LEVEL_PLACEHOLDER}</code> }}
                        />
                    </Help>
                </span>
                <div className="setting-row">
                    <select
                        aria-label={t("Language you are learning")}
                        value={settings.language}
                        onChange={(event) => onChange({ ...settings, language: event.target.value })}
                    >
                        {LANGUAGES.map((language) => (
                            <option key={language} value={language}>{languageName(language)}</option>
                        ))}
                    </select>
                    <LevelPicker
                        label={t("Your level")}
                        value={settings.level}
                        onChange={(level) => onChange({ ...settings, level })}
                    />
                </div>
            </div>
            <label className="field">
                <span className="setting-name">
                    {t("Translate into")}
                    <Help>
                        {t(
                            "The language text you select is translated into, and exercises explain in. The app is shown in it too.",
                        )}
                    </Help>
                </span>
                <Choice
                    options={[...TRANSLATION_LANGUAGES]}
                    value={settings.translateInto}
                    label={languageName}
                    onChange={(translateInto) => onChange({ ...settings, translateInto })}
                />
            </label>
            <h3>{t("Tutor")}</h3>
            <label className="field">
                <span className="setting-name">
                    {t("Tutor's tone")}
                    <Help>
                        {t("How the tutor talks with you. What you ask it in a lesson, once it remembers it, goes first.")}
                    </Help>
                </span>
                <textarea
                    rows={3}
                    placeholder={t("Such as: friendly but direct, short answers, correct every mistake")}
                    value={settings.tutorTone}
                    onChange={(event) => onChange({ ...settings, tutorTone: event.target.value })}
                />
            </label>
            <h3>Anki</h3>
            <AnkiAccount anki={anki} onAnki={onAnki} />
            {ankiWords && (
                <>
                    <label className="toggle">
                        <span>
                            <span className="setting-name">
                                {t("Import Anki words")}
                                <Help>
                                    {t("Adds your Anki words to the vocabulary.")}
                                </Help>
                            </span>
                        </span>
                        <input
                            type="checkbox"
                            checked={settings.importAnki}
                            onChange={(event) => onChange({ ...settings, importAnki: event.target.checked })}
                        />
                    </label>
                    {/* on one line, as the switch above it */}
                    <label className="toggle">
                        <span>
                            <span className="setting-name">
                                {t("Language of your Anki words")}
                                <Help>
                                    {t(
                                        "The language your Anki words are in: they are added to the vocabulary of that language.",
                                    )}
                                </Help>
                            </span>
                        </span>
                        <select
                            value={settings.ankiLanguage}
                            onChange={(event) => onChange({ ...settings, ankiLanguage: event.target.value })}
                        >
                            {LANGUAGES.map((language) => (
                                <option key={language} value={language}>{languageName(language)}</option>
                            ))}
                        </select>
                    </label>
                </>
            )}
        </>
    );
}

/** The key of OpenRouter, with a button that shows it. */
function ApiKey({ settings, onChange }: TabProps) {
    const [showKey, setShowKey] = useState(false);
    return (
        <>
            <label className="field">
                <span className="setting-name">
                    {t("OpenRouter API key")}
                    <Help>
                        {t("Kept in this browser only, and sent with each request to the server, which asks OpenRouter with it.")}
                    </Help>
                </span>
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
                        {showKey ? t("Hide") : t("Show")}
                    </button>
                </span>
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
        label: Message,
        kind: ModelKind,
        none?: Message,
    ) => (
        <ModelPicker
            label={t(label)}
            value={settings[key]}
            onChange={(chosen) => onChange({ ...settings, [key]: chosen })}
            listed={ids(kind)}
            none={none && t(none)}
            // those that chat, which OpenRouter can send to a provider of one's choice
            providers={kind === "text" || kind === "reasoning" || kind === "vision"}
            // the reasoning model is the one the tutor calls its tools with
            tools={kind === "reasoning"}
            apiKey={settings.apiKey}
        />
    );

    return (
        <>
            <ApiKey settings={settings} onChange={onChange} />
            <p className="hint">
                <T
                    message="Each model is one of {openrouter}, asked with your key, or one on a server that takes OpenAI's requests, such as one running on this machine, asked at its address. Such a server's key is kept with your settings."
                    values={{
                        openrouter: (
                            <a href="https://openrouter.ai/models" target="_blank" rel="noreferrer">
                                {t("OpenRouter's")}
                            </a>
                        ),
                    }}
                />
            </p>
            <div className="field">
                <span className="setting-name">
                    {t("Chat and text model")}
                    <Help>
                        {t("Answers in the chat, and makes and checks the exercises. It answers without reasoning first.")}
                    </Help>
                </span>
                {picker("model", "Chat and text model", "text")}
            </div>
            <div className="field">
                <span className="setting-name">
                    {t("Translation model")}
                    <Help>
                        {t("Translates the text you select. A small, quick model does this well.")}
                    </Help>
                </span>
                {picker("translationModel", "Translation model", "text", "the chat model")}
            </div>
            <div className="field">
                <span className="setting-name">
                    {t("Reasoning model")}
                    <Help>
                        {t("Thinks over what needs it before it answers. The list has the models that can reason.")}
                    </Help>
                </span>
                {picker("reasoningModel", "Reasoning model", "reasoning", "the chat model")}
            </div>
            <div className="field">
                <span className="setting-name">
                    {t("Sentence check model")}
                    <Help>
                        <T
                            message="Answers the questions about each sentence you finish typing in the chat, and sorts new words into categories. It is a decision model: a server of your own is asked at {path} under its address."
                            values={{ path: <code>/decisions</code> }}
                        />
                    </Help>
                </span>
                {picker("profileModel", "Sentence check model", "decisions")}
            </div>
            <div className="field">
                <span className="setting-name">
                    {t("Speech model")}
                    <Help>
                        {t("Reads the books, the replies and the stories aloud.")}
                    </Help>
                </span>
                {picker("speechModel", "Speech model", "speech")}
            </div>
            <div className="field">
                <span className="setting-name">
                    {t("Voice")}
                    <Help>
                        {t("The voices there are depend on the speech model.")}
                    </Help>
                </span>
                <OpenChoice
                    label={t("Voice")}
                    options={voices}
                    placeholder={t("Voice name")}
                    value={settings.speechVoice}
                    onChange={(speechVoice) => onChange({ ...settings, speechVoice })}
                />
            </div>
            <div className="field">
                <span className="setting-name">
                    {t("Embedding model")}
                    <Help>
                        {t(
                            "Embeds every word of your vocabulary once, and each topic, to find the words of a topic. One that knows many languages works best.",
                        )}
                    </Help>
                </span>
                {picker("embeddingModel", "Embedding model", "embeddings")}
            </div>
            <div className="field">
                <span className="setting-name">
                    {t("Image model")}
                    <Help>
                        {t("Makes the icon of each topic you add, and the pictures of exercises.")}
                    </Help>
                </span>
                {picker("imageModel", "Image model", "image")}
            </div>
            <div className="field">
                <span className="setting-name">
                    {t("Vision model")}
                    <Help>
                        {t(
                            "Finds where each thing is on the picture of an exercise. It must see pictures, and a small model often points beside them: one such as Gemini Flash, rather than Flash Lite, is far better at it.",
                        )}
                    </Help>
                </span>
                {picker("visionModel", "Vision model", "vision", "the chat model")}
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
    /** What each option is called, if not by itself. */
    label?: (option: string) => string;
    onChange: (value: string) => void;
}

/**
 * A list to choose from, with everything in it on show. Until it is known
 * what there is to choose from, the value is typed instead.
 */
function Choice({ options, value, placeholder, label = (option) => option, onChange }: ChoiceProps) {
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
            {!options.includes(value) && <option value={value}>{value ? label(value) : placeholder}</option>}
            {options.map((option) => <option key={option} value={option}>{label(option)}</option>)}
        </select>
    );
}

function ExercisesTab({ settings, onChange, sets }: TabProps & { sets: WordSet[] }) {
    const vocabulary = exerciseVocabularyOf(settings, settings.language);
    const known = vocabulary === "all" || vocabulary === "none" || sets.some((set) => set.id === vocabulary);

    return (
        <>
            <h3>{t("Topics")}</h3>
            <label className="toggle">
                <span>
                    <span className="setting-name">
                        {t("Mix topics")}
                        <Help>
                            {t(
                                "Bring all the topics you choose together in the exercises. Off, one of them is drawn for each session.",
                            )}
                        </Help>
                    </span>
                </span>
                <input
                    type="checkbox"
                    checked={settings.exerciseMixTopics}
                    onChange={(event) => onChange({ ...settings, exerciseMixTopics: event.target.checked })}
                />
            </label>

            <h3>{t("Words")}</h3>
            <label className="field">
                <span className="setting-name">
                    {t("Words of your vocabulary")}
                    <Help>
                        {t(
                            "The exercises are given at most 200 of these words, for {language}. With none, they use any words of your level.",
                            { language: languageName(settings.language) },
                        )}
                    </Help>
                </span>
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
                    <option value="all">{t("Every word")}</option>
                    {sets.map((set) => (
                        <option key={set.id} value={set.id}>
                            {t("Set: {name}", { name: set.name || t("Untitled") })}
                        </option>
                    ))}
                    <option value="none">{t("None")}</option>
                </select>
            </label>
            <label className="toggle">
                <span>
                    <span className="setting-name">
                        {t("Words that fit the topics")}
                        <Help>
                            {t(
                                "Give the 200 words nearest the topics, found with embeddings, rather than the 200 used last. With 20 or more to choose from, the exercises use those words alone; with fewer, they lean on them.",
                            )}
                        </Help>
                    </span>
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
            <h3>{t("Theme")}</h3>
            <label className="field">
                <span>{t("Light or dark")}</span>
                <select
                    value={settings.theme}
                    onChange={(event) => onChange({ ...settings, theme: event.target.value as Settings["theme"] })}
                >
                    {Object.entries(THEMES).map(([id, label]) => <option key={id} value={id}>{t(label)}</option>)}
                </select>
            </label>
            <div className="field">
                <span className="setting-name">
                    {t("Colour")}
                    <Help>
                        {t("Used for buttons, links and what is selected.")}
                    </Help>
                </span>
                <div className="swatches" role="radiogroup" aria-label={t("Colour")}>
                    {Object.entries(ACCENTS).map(([id, accent]) => (
                        <button
                            key={id}
                            type="button"
                            role="radio"
                            aria-checked={settings.accent === id}
                            className="swatch"
                            title={t(accent.label)}
                            aria-label={t(accent.label)}
                            style={{ background: `light-dark(${accent.light}, ${accent.dark})` }}
                            onClick={() => onChange({ ...settings, accent: id as Settings["accent"] })}
                        />
                    ))}
                </div>
            </div>
            <label className="field">
                <span className="setting-name">
                    {t("Text size")}
                    <Help>
                        {t("The size of the app. A book has a size of its own, set in the reader.")}
                    </Help>
                </span>
                <select
                    value={settings.textSize}
                    onChange={(event) =>
                        onChange({ ...settings, textSize: event.target.value as Settings["textSize"] })}
                >
                    {Object.entries(TEXT_SIZES).map(([id, size]) => <option key={id} value={id}>{t(size.label)}
                    </option>)}
                </select>
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
        const context = { id: newId(), name: t("New context"), prompt: "" };
        onChange({ ...settings, contexts: [...settings.contexts, context] });
    }

    function removeContext(id: string) {
        const contexts = settings.contexts.filter((context) => context.id !== id);
        const defaultContextId = settings.defaultContextId === id ? contexts[0].id : settings.defaultContextId;
        onChange({ ...settings, contexts, defaultContextId });
    }

    return (
        <>
            <h3>{t("Keywords")}</h3>
            <p className="hint">
                {t(
                    "Write these in any prompt, whether of a context, of the speech model or of a question about each sentence, and each is replaced by what it stands for:",
                )}
            </p>
            <PromptKeywords settings={settings} />
            <h3>{t("Contexts")}</h3>
            <p className="hint">{t("A context is the instruction a chat starts with.")}</p>
            {settings.contexts.map((context) => (
                <fieldset key={context.id} className="context">
                    <div className="input-row">
                        <input
                            type="text"
                            aria-label={t("Context name")}
                            value={context.name}
                            onChange={(event) => updateContext(context.id, { name: event.target.value })}
                        />
                        <button
                            type="button"
                            onClick={() => removeContext(context.id)}
                            disabled={settings.contexts.length === 1}
                        >
                            {t("Delete")}
                        </button>
                    </div>
                    <textarea
                        rows={5}
                        aria-label={t("Context instructions")}
                        placeholder={t("Instructions for the model")}
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
                        {t("Use for new chats")}
                    </label>
                </fieldset>
            ))}
            <button type="button" onClick={addContext}>{t("Add context")}</button>

            <h3>{t("Speech")}</h3>
            <label className="field">
                <span className="setting-name">
                    {t("How to read")}
                    <Help>
                        {t("Passed to the speech model as a direction, with the keywords above filled in. It is not read aloud.")}
                    </Help>
                </span>
                <textarea
                    rows={4}
                    placeholder={t("For example: Speak {{language}} slowly and clearly.")}
                    value={settings.speechDirection}
                    onChange={(event) => onChange({ ...settings, speechDirection: event.target.value })}
                />
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
                    aria-label={t("Question title")}
                    placeholder={t("Title")}
                    value={question.title}
                    onChange={(event) => onChange({ title: event.target.value })}
                />
                <button type="button" onClick={onDelete}>{t("Delete")}</button>
            </div>
            <textarea
                rows={3}
                aria-label={t("What to ask")}
                placeholder={t("What to ask about the sentence")}
                value={question.instructions}
                onChange={(event) => onChange({ instructions: event.target.value })}
            />
            <label className="check">
                {t("Answered with")}
                <select
                    value={question.kind}
                    onChange={(event) => onChange({ kind: event.target.value as ProfileQuestion["kind"] })}
                >
                    <option value="choice">{t("one of these options")}</option>
                    <option value="score">{t("a place on this scale")}</option>
                </select>
            </label>
            <small className="hint">
                {scale
                    ? t("From the worst level to the best: the bar of the answer is fuller the further down the list it is.")
                    : t("From the worst option to the best: the bar of the answer is fuller the further down the list it is.")}
            </small>
            {question.options.map((option, index) => (
                <div key={index} className="input-row option-row">
                    <input
                        type="text"
                        className="option-label"
                        aria-label={scale ? t("Level name") : t("Option name")}
                        placeholder={scale ? t("Level") : t("Option")}
                        value={option.label}
                        onChange={(event) => updateOption(index, { label: event.target.value })}
                    />
                    <input
                        type="text"
                        aria-label={t("When it applies")}
                        placeholder={t("When it applies")}
                        value={option.description}
                        onChange={(event) => updateOption(index, { description: event.target.value })}
                    />
                    <button
                        type="button"
                        className="icon-button"
                        title={t("Remove")}
                        aria-label={t("Remove {name}", { name: option.label || t("option") })}
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
                    {scale ? t("Add level") : t("Add option")}
                </button>
            </div>
            {!isAskable(question) && (
                <small className="hint error">
                    {scale
                        ? t("Not asked yet: it needs something to ask and at least two levels, each with a name of its own.")
                        : t("Not asked yet: it needs something to ask and at least two options, each with a name of its own.")}
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
            <h3>{t("Questions about each sentence")}</h3>
            <p className="hint">
                <T
                    message="Each sentence you finish typing in the chat is sent to the sentence check model with these questions. Turn them on and off in the Checks panel, where the answers are shown as well. The keywords of the Prompts tab, such as {keyword}, are filled in, in what a question asks and in what its options mean."
                    values={{ keyword: <code>{LANGUAGE_PLACEHOLDER}</code> }}
                />
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
                {t("Add question")}
            </button>
        </>
    );
}

export function SettingsPanel({ settings, anki, onAnki, sets, tab, onTab, onChange, onClose }: Props) {
    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && onClose();
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [onClose]);

    return (
        <SidePanel
            title={t("Settings")}
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
                            {t(label)}
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
