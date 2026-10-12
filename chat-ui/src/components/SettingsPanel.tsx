// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useState } from "react";

import { fetchProfileModels } from "../lib/checker";
import { type ChatContext, type Settings, WORDS_PLACEHOLDER } from "../lib/settings";
import { fetchSpeechModels, type SpeechModel } from "../lib/speech";

interface Props {
    settings: Settings;
    onChange: (settings: Settings) => void;
    onClose: () => void;
}

export function SettingsPanel({ settings, onChange, onClose }: Props) {
    const [showKey, setShowKey] = useState(false);
    const [speechModels, setSpeechModels] = useState<SpeechModel[]>([]);
    const [profileModels, setProfileModels] = useState<string[]>([]);
    const voices = speechModels.find((model) => model.id === settings.speechModel)?.voices ?? [];

    // suggestions only; the fields work without them
    useEffect(() => {
        fetchSpeechModels().then(setSpeechModels, () => undefined);
        fetchProfileModels().then(setProfileModels, () => undefined);
    }, []);

    useEffect(() => {
        const onKeyDown = (event: KeyboardEvent) => event.key === "Escape" && onClose();
        window.addEventListener("keydown", onKeyDown);
        return () => window.removeEventListener("keydown", onKeyDown);
    }, [onClose]);

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
        <div className="overlay" onClick={onClose}>
            <section
                className="settings"
                role="dialog"
                aria-modal="true"
                aria-labelledby="settings-title"
                onClick={(event) => event.stopPropagation()}
            >
                <header className="settings-header">
                    <h2 id="settings-title">Settings</h2>
                    <button onClick={onClose}>Done</button>
                </header>

                <div className="settings-body">
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
                    <label className="field">
                        <span>Model</span>
                        <input
                            type="text"
                            spellCheck={false}
                            placeholder="openrouter/auto"
                            value={settings.model}
                            onChange={(event) => onChange({ ...settings, model: event.target.value.trim() })}
                        />
                        <small>
                            A model id from{" "}
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
                            Judges each sentence you finish typing in the chat.
                            {profileModels.length > 0
                                && ` ${profileModels.length} models can do this; clear the field to see them.`}
                        </small>
                    </label>

                    <h3>Contexts</h3>
                    <p className="hint">
                        A context is the instruction a chat starts with. Write <code>{WORDS_PLACEHOLDER}</code>{" "}
                        where the list of your known words should go.
                    </p>
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
                        <small>
                            Texts are written by the model above. <code>{WORDS_PLACEHOLDER}</code>{" "}
                            is replaced by your known words here too.
                        </small>
                    </label>

                    <h3>Speech</h3>
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
                </div>
            </section>
        </div>
    );
}
