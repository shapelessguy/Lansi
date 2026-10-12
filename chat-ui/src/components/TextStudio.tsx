// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { fetchGenerationUsage, streamChat } from "../lib/openrouter";
import { expandPrompt, type Settings } from "../lib/settings";
import { synthesizeSpeech } from "../lib/speech";
import {
    deleteText,
    fetchAudio,
    plainText,
    saveAudio,
    type SavedText,
    saveText,
    textId,
    type TextLength,
    textLengths,
    textRequest,
    textTitle,
} from "../lib/texts";
import type { UsageEntry } from "../lib/usage";
import type { Word } from "../lib/words";

interface Props {
    settings: Settings;
    words: Word[];
    /** A word clicked in the word list, to add to the topic. */
    picked: { word: string; nonce: number } | null;
    /** The saved text being shown, or null while a new one is being set up. */
    selected: SavedText | null;
    onSelect: (id: string | null) => void;
    onTextsChange: (change: (texts: SavedText[]) => SavedText[]) => void;
    onUsage: (entry: UsageEntry) => void;
    onOpenSettings: () => void;
    /** Why texts can't be saved at the moment, if they can't. Nothing is generated then. */
    storageError: string | null;
}

/** The audio loaded for a text. `stamp` tells one recording of a text from the next. */
interface LoadedAudio {
    id: string;
    stamp: number;
    url: string;
    autoPlay: boolean;
}

export function TextStudio(
    { settings, words, picked, selected, onSelect, onTextsChange, onUsage, onOpenSettings, storageError }: Props,
) {
    const [topic, setTopic] = useState("");
    const [length, setLength] = useState<TextLength>("medium");
    const [phase, setPhase] = useState<"idle" | "writing" | "speaking">("idle");
    // the text so far, while it is being written
    const [draft, setDraft] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [audio, setAudio] = useState<LoadedAudio | null>(null);
    // a text that was written but could not be saved, kept on screen so it is not lost
    const [unsaved, setUnsaved] = useState<string | null>(null);
    const abortRef = useRef<AbortController | null>(null);
    const audioRef = useRef<HTMLAudioElement>(null);

    useEffect(() => {
        if (picked) {
            setTopic((current) => (current.trim() ? `${current.trimEnd()}, ${picked.word}` : picked.word));
        }
    }, [picked]);

    const selectedId = selected?.id;
    const audioStamp = selected?.audio?.createdAt;

    // load the saved audio of the text being shown, unless it was just made here
    useEffect(() => {
        if (!selectedId || !audioStamp) {
            return;
        }
        let cancelled = false;
        setAudio((current) => {
            if (current?.id === selectedId && current.stamp === audioStamp) {
                return current;
            }
            fetchAudio(selectedId).then(
                (blob) =>
                    cancelled
                    || setAudio({ id: selectedId, stamp: audioStamp, url: URL.createObjectURL(blob), autoPlay: false }),
                (caught: Error) => cancelled || setError(caught.message),
            );
            return current;
        });
        return () => {
            cancelled = true;
        };
    }, [selectedId, audioStamp]);

    const audioUrl = audio?.url;
    useEffect(() => () => {
        if (audioUrl) {
            URL.revokeObjectURL(audioUrl);
        }
    }, [audioUrl]);

    async function speak(text: SavedText, controller: AbortController) {
        setPhase("speaking");
        const { audio: blob, generationId } = await synthesizeSpeech({
            apiKey: settings.apiKey,
            model: settings.speechModel,
            voice: settings.speechVoice,
            input: plainText(text.text),
            instructions: settings.speechInstructions,
            signal: controller.signal,
        });
        const createdAt = Date.now();
        const spoken: SavedText = {
            ...text,
            audio: { model: settings.speechModel, voice: settings.speechVoice, createdAt },
        };
        await saveAudio(text.id, blob);
        await saveText(spoken);
        setAudio({ id: text.id, stamp: createdAt, url: URL.createObjectURL(blob), autoPlay: true });
        onTextsChange((texts) => texts.map((candidate) => (candidate.id === text.id ? spoken : candidate)));
        // The audio comes without what it used, so that is looked up afterwards,
        // without holding up playback. It is recorded without a cost if the
        // lookup fails.
        const { apiKey, speechModel } = settings;
        void (generationId ? fetchGenerationUsage(apiKey, generationId) : Promise.resolve(null)).then((usage) =>
            onUsage({
                at: createdAt,
                chatId: `text:${text.id}`,
                model: usage?.model ?? speechModel,
                promptTokens: usage?.promptTokens ?? 0,
                completionTokens: usage?.completionTokens ?? 0,
                cost: usage?.cost ?? null,
            })
        );
    }

    async function write(controller: AbortController): Promise<SavedText> {
        setPhase("writing");
        setDraft("");
        let written = "";
        const usage = await streamChat({
            apiKey: settings.apiKey,
            model: settings.model,
            messages: [
                { role: "system", content: expandPrompt(settings.textPrompt, words) },
                { role: "user", content: textRequest(topic, length) },
            ],
            signal: controller.signal,
            onText: (piece) => {
                written += piece;
                setDraft(written);
            },
        });
        if (!written.trim()) {
            throw new Error("The model returned no text.");
        }
        const createdAt = Date.now();
        const title = textTitle(written);
        const text: SavedText = {
            id: textId(createdAt, title),
            createdAt,
            title,
            text: written.trim(),
            topic: topic.trim(),
            model: usage?.model ?? settings.model,
            audio: null,
        };
        try {
            await saveText(text);
        } catch (caught) {
            setUnsaved(text.text);
            throw caught;
        }
        onTextsChange((texts) => [text, ...texts]);
        onSelect(text.id);
        if (usage) {
            onUsage({
                at: createdAt,
                chatId: `text:${text.id}`,
                model: text.model,
                promptTokens: usage.promptTokens,
                completionTokens: usage.completionTokens,
                cost: usage.cost,
            });
        }
        return text;
    }

    /** Runs the steps, showing what went wrong unless the user stopped them. */
    async function run(steps: (controller: AbortController) => Promise<void>) {
        const controller = new AbortController();
        abortRef.current = controller;
        setError(null);
        setUnsaved(null);
        try {
            await steps(controller);
        } catch (caught) {
            if (!controller.signal.aborted) {
                setError(caught instanceof Error ? caught.message : String(caught));
            }
        } finally {
            setPhase("idle");
            setDraft("");
        }
    }

    function generate() {
        void run(async (controller) => speak(await write(controller), controller));
    }

    function replay() {
        const element = audioRef.current;
        if (element) {
            element.currentTime = 0;
            void element.play();
        }
    }

    function rerecord(text: SavedText) {
        const question = "Send this text to the speech model again and replace the saved audio? "
            + "This is a new, billed request.";
        if (window.confirm(question)) {
            void run((controller) => speak(text, controller));
        }
    }

    async function remove(text: SavedText) {
        if (!window.confirm(`Delete “${text.title}” and its audio? This can't be undone.`)) {
            return;
        }
        setError(null);
        try {
            await deleteText(text.id);
            onTextsChange((texts) => texts.filter((candidate) => candidate.id !== text.id));
            onSelect(null);
        } catch (caught) {
            setError(caught instanceof Error ? caught.message : String(caught));
        }
    }

    const busy = phase !== "idle";
    const status = phase === "writing" ? "Writing the text…" : phase === "speaking" ? "Making the audio…" : null;
    const player = selected && audio?.id === selected.id && audio.stamp === audioStamp ? audio : null;

    return (
        <section className="studio">
            <div className="studio-body">
                {status && (
                    <div className="studio-status" role="status">
                        <span>{status}</span>
                        <button onClick={() => abortRef.current?.abort()}>Stop</button>
                    </div>
                )}
                {error && <div className="message error" role="alert">{error}</div>}
                {!error && storageError && !selected && (
                    <div className="message error" role="alert">
                        Texts can't be saved right now, so none will be written. {storageError}
                    </div>
                )}
                {unsaved && phase === "idle" && (
                    <article className="studio-text">
                        <p className="studio-meta">
                            This text was written but not saved. Copy it if you want to keep it.
                        </p>
                        <Markdown>{unsaved}</Markdown>
                    </article>
                )}

                {phase === "writing" && (
                    <article className="studio-text">
                        <Markdown>{draft}</Markdown>
                    </article>
                )}

                {phase !== "writing" && selected && (
                    <>
                        <div className="studio-actions">
                            {selected.audio
                                ? (
                                    // plays the saved recording; nothing is sent anywhere
                                    <button className="primary" onClick={replay} disabled={!player}>
                                        Play
                                    </button>
                                )
                                : (
                                    <button
                                        className="primary"
                                        onClick={() => void run((controller) => speak(selected, controller))}
                                        disabled={busy || !settings.apiKey}
                                    >
                                        Read aloud
                                    </button>
                                )}
                            <button onClick={() => onSelect(null)} disabled={busy}>New text</button>
                            <button onClick={() => void remove(selected)} disabled={busy}>Delete</button>
                            {selected.audio && (
                                <button
                                    className="studio-rerecord"
                                    onClick={() => rerecord(selected)}
                                    disabled={busy || !settings.apiKey}
                                >
                                    Record new audio…
                                </button>
                            )}
                        </div>
                        {player && (
                            <audio
                                ref={audioRef}
                                key={player.url}
                                className="studio-audio"
                                src={player.url}
                                controls
                                autoPlay={player.autoPlay}
                            />
                        )}
                        <article className="studio-text">
                            <Markdown>{selected.text}</Markdown>
                        </article>
                        <p className="studio-meta">
                            {new Date(selected.createdAt).toLocaleString()} · written by {selected.model}
                            {selected.audio && ` · read by ${selected.audio.model} (${selected.audio.voice})`}
                        </p>
                    </>
                )}

                {phase !== "writing" && !selected && (
                    <form
                        className="studio-form"
                        onSubmit={(event) => {
                            event.preventDefault();
                            generate();
                        }}
                    >
                        <h2>New text</h2>
                        <p className="hint">
                            A text is written from the words you know, read aloud, and saved with its audio.
                        </p>
                        <label className="field">
                            <span>What should it be about?</span>
                            <textarea
                                rows={3}
                                placeholder="Leave empty to let the model choose"
                                value={topic}
                                onChange={(event) => setTopic(event.target.value)}
                            />
                        </label>
                        <label className="field">
                            <span>Length</span>
                            <select value={length} onChange={(event) => setLength(event.target.value as TextLength)}>
                                {Object.entries(textLengths).map(([key, { label, words: count }]) => (
                                    <option key={key} value={key}>{label} (about {count} words)</option>
                                ))}
                            </select>
                        </label>
                        <button
                            type="submit"
                            className="primary"
                            disabled={busy || !settings.apiKey || storageError !== null}
                        >
                            Write and read aloud
                        </button>
                        {!settings.apiKey && (
                            <p className="hint">
                                Add your OpenRouter API key in{" "}
                                <button type="button" className="link" onClick={onOpenSettings}>Settings</button> first.
                            </p>
                        )}
                        <p className="hint">
                            Written by {settings.model}, read by {settings.speechModel} ({settings.speechVoice}).
                        </p>
                    </form>
                )}
            </div>
        </section>
    );
}
