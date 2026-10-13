// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";

import { fetchProfileModels } from "../lib/checker";
import { isAskable, newQuestion, type ProfileQuestion, type QuestionOption } from "../lib/questions";
import {
    type ChatContext,
    LANGUAGE_PLACEHOLDER,
    LANGUAGES,
    LEVEL_PLACEHOLDER,
    LEVELS,
    type Settings,
    WORDS_PLACEHOLDER,
} from "../lib/settings";
import { fetchSpeechModels, type SpeechModel } from "../lib/speech";
import { SidePanel } from "./SidePanel";

export type SettingsTab = "models" | "content" | "questions";

const TABS: { id: SettingsTab; label: string }[] = [
    { id: "models", label: "Key & models" },
    { id: "content", label: "Prompts" },
    { id: "questions", label: "Questions" },
];

interface Props {
    settings: Settings;
    tab: SettingsTab;
    onTab: (tab: SettingsTab) => void;
    onChange: (settings: Settings) => void;
    onClose: () => void;
}

interface TabProps {
    settings: Settings;
    onChange: (settings: Settings) => void;
}

function ModelsTab({ settings, onChange }: TabProps) {
    const [showKey, setShowKey] = useState(false);
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
            <label className="field">
                <span>Your level</span>
                <select
                    value={settings.level}
                    onChange={(event) => onChange({ ...settings, level: event.target.value })}
                >
                    {LEVELS.map((level) => <option key={level} value={level}>{level}</option>)}
                </select>
                <small>
                    Fills <code>{LEVEL_PLACEHOLDER}</code> in your prompts.
                </small>
            </label>
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

            <h3>Models</h3>
            <label className="field">
                <span>Chat and text model</span>
                <input
                    type="text"
                    spellCheck={false}
                    placeholder="openrouter/auto"
                    value={settings.model}
                    onChange={(event) => onChange({ ...settings, model: event.target.value.trim() })}
                />
                <small>
                    Answers in the chat and writes the texts. A model id from{" "}
                    <a href="https://openrouter.ai/models" target="_blank" rel="noreferrer">
                        openrouter.ai/models
                    </a>.
                </small>
            </label>
            <label className="field">
                <span>Sentence check model</span>
                <input
                    type="text"
                    spellCheck={false}
                    list="profile-models"
                    placeholder="typesafe/jev-1.13"
                    value={settings.profileModel}
                    onChange={(event) => onChange({ ...settings, profileModel: event.target.value.trim() })}
                />
                <datalist id="profile-models">
                    {profileModels.map((model) => <option key={model} value={model} />)}
                </datalist>
                <small>
                    Answers the questions about each sentence you finish typing in the chat.
                    {profileModels.length > 0
                        && ` ${profileModels.length} models can do this; clear the field to see them.`}
                </small>
            </label>
            <label className="field">
                <span>Speech model</span>
                <input
                    type="text"
                    spellCheck={false}
                    list="speech-models"
                    value={settings.speechModel}
                    onChange={(event) => onChange({ ...settings, speechModel: event.target.value.trim() })}
                />
                <datalist id="speech-models">
                    {speechModels.map((model) => <option key={model.id} value={model.id} />)}
                </datalist>
                <small>Reads the texts aloud.</small>
            </label>
            <label className="field">
                <span>Voice</span>
                <input
                    type="text"
                    spellCheck={false}
                    list="speech-voices"
                    value={settings.speechVoice}
                    onChange={(event) => onChange({ ...settings, speechVoice: event.target.value.trim() })}
                />
                <datalist id="speech-voices">
                    {voices.map((voice) => <option key={voice} value={voice} />)}
                </datalist>
                <small>
                    {voices.length > 0
                        ? `${voices.length} voices are available for this model; clear the field to see them.`
                        : "Voice names depend on the speech model."}
                </small>
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
        const context = { id: crypto.randomUUID(), name: "New context", prompt: "" };
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

export function SettingsPanel({ settings, tab, onTab, onChange, onClose }: Props) {
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
                {tab === "models" && <ModelsTab settings={settings} onChange={onChange} />}
                {tab === "content" && <ContentTab settings={settings} onChange={onChange} />}
                {tab === "questions" && <QuestionsTab settings={settings} onChange={onChange} />}
            </div>
        </SidePanel>
    );
}
