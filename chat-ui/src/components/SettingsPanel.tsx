// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";
import { newId } from "../lib/ids";

import { fetchProfileModels } from "../lib/checker";
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
import { fetchSpeechModels, type SpeechModel } from "../lib/speech";
import { LevelPicker } from "./Level";
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
    /** Whether the user has Anki words, and so the settings of their import. */
    ankiWords: boolean;
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

function GeneralTab({ settings, onChange, ankiWords }: TabProps & { ankiWords: boolean }) {
    const [showKey, setShowKey] = useState(false);

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
    const [speechModels, setSpeechModels] = useState<SpeechModel[]>([]);
    const [profileModels, setProfileModels] = useState<string[]>([]);
    const voices = speechModels.find((model) => model.id === settings.speechModel)?.voices ?? [];

    // suggestions only; the fields work without them
    useEffect(() => {
        fetchSpeechModels().then(setSpeechModels, () => undefined);
        fetchProfileModels().then(setProfileModels, () => undefined);
    }, []);

    return (
        <>
            <p className="hint">
                Every model is an id from{" "}
                <a href="https://openrouter.ai/models" target="_blank" rel="noreferrer">openrouter.ai/models</a>.
            </p>
            <h3>Writing</h3>
            <label className="field">
                <span>Chat and text model</span>
                <input
                    type="text"
                    spellCheck={false}
                    placeholder="openrouter/auto"
                    value={settings.model}
                    onChange={(event) => onChange({ ...settings, model: event.target.value.trim() })}
                />
                <small>Answers in the chat, writes the texts, and makes and checks the exercises.</small>
            </label>
            <label className="field">
                <span>Translation model</span>
                <input
                    type="text"
                    spellCheck={false}
                    placeholder={settings.model}
                    value={settings.translationModel}
                    onChange={(event) => onChange({ ...settings, translationModel: event.target.value.trim() })}
                />
                <small>
                    Translates the text you select. A small, quick model does this well. Left empty, the chat model is
                    used.
                </small>
            </label>

            <h3>Checking</h3>
            <label className="field">
                <span>Sentence check model</span>
                <Choice
                    options={profileModels}
                    placeholder="typesafe/jev-1.13"
                    value={settings.profileModel}
                    onChange={(profileModel) => onChange({ ...settings, profileModel })}
                />
                <small>
                    Answers the questions about each sentence you finish typing in the chat, and sorts new words into
                    categories.
                </small>
            </label>

            <h3>Speech</h3>
            <label className="field">
                <span>Speech model</span>
                <Choice
                    options={speechModels.map((model) => model.id)}
                    value={settings.speechModel}
                    onChange={(speechModel) => onChange({ ...settings, speechModel })}
                />
                <small>Reads the texts, the books and the replies aloud.</small>
            </label>
            <label className="field">
                <span>Voice</span>
                <Choice
                    options={voices}
                    value={settings.speechVoice}
                    onChange={(speechVoice) => onChange({ ...settings, speechVoice })}
                />
                <small>Voice names depend on the speech model.</small>
            </label>

            <h3>Topics</h3>
            <label className="field">
                <span>Embedding model</span>
                <input
                    type="text"
                    spellCheck={false}
                    placeholder="baai/bge-m3"
                    value={settings.embeddingModel}
                    onChange={(event) => onChange({ ...settings, embeddingModel: event.target.value.trim() })}
                />
                <small>
                    Embeds every word of your vocabulary once, and each topic, to find the words of a topic. One that
                    knows many languages works best.
                </small>
            </label>
            <label className="field">
                <span>Image model</span>
                <input
                    type="text"
                    spellCheck={false}
                    placeholder="google/gemini-3.1-flash-lite-image"
                    value={settings.imageModel}
                    onChange={(event) => onChange({ ...settings, imageModel: event.target.value.trim() })}
                />
                <small>Makes the icon of each topic you add, and the pictures of exercises.</small>
            </label>
            <label className="field">
                <span>Vision model</span>
                <input
                    type="text"
                    spellCheck={false}
                    placeholder="the chat model"
                    value={settings.visionModel}
                    onChange={(event) => onChange({ ...settings, visionModel: event.target.value.trim() })}
                />
                <small>
                    Finds where each thing is on the picture of an exercise. It must see pictures, and a small model
                    often points beside them: one such as Gemini Flash, rather than Flash Lite, is far better at it.
                </small>
            </label>
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

            <h3>Texts</h3>
            <label className="field">
                <span>Instructions for writing a text</span>
                <textarea
                    rows={6}
                    value={settings.textPrompt}
                    onChange={(event) => onChange({ ...settings, textPrompt: event.target.value })}
                />
            </label>

            <h3>Speech</h3>
            <label className="field">
                <span>How to read</span>
                <input
                    type="text"
                    placeholder="For example: slowly and clearly"
                    value={settings.speechInstructions}
                    onChange={(event) => onChange({ ...settings, speechInstructions: event.target.value })}
                />
                <small>Passed to the speech model as a direction. It is not read aloud.</small>
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

export function SettingsPanel({ settings, ankiWords, sets, tab, onTab, onChange, onClose }: Props) {
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
                {tab === "general" && <GeneralTab settings={settings} onChange={onChange} ankiWords={ankiWords} />}
                {tab === "models" && <ModelsTab settings={settings} onChange={onChange} />}
                {tab === "content" && <ContentTab settings={settings} onChange={onChange} />}
                {tab === "questions" && <QuestionsTab settings={settings} onChange={onChange} />}
                {tab === "exercises" && <ExercisesTab settings={settings} onChange={onChange} sets={sets} />}
                {tab === "look" && <LookTab settings={settings} onChange={onChange} />}
            </div>
        </SidePanel>
    );
}
