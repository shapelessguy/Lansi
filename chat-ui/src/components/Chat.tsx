// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Markdown from "react-markdown";

import type { StoredChat } from "../lib/chats";
import {
    applySuggestion,
    doubt,
    type MarkedPart,
    type ProfileUsage,
    sentenceAtCaret,
    sentenceParts,
    sentenceState,
    type SpellingIssue,
    spellingIssues,
    useLiveCheck,
} from "../lib/checker";
import { type ChatMessage, streamChat } from "../lib/openrouter";
import { requestQuestions } from "../lib/questions";
import type { WordLists } from "../lib/sets";
import { expandPrompt, type Settings } from "../lib/settings";
import type { UsageEntry } from "../lib/usage";
import { ChecksPanel } from "./ChecksPanel";

interface Props {
    settings: Settings;
    onSettingsChange: (settings: Settings) => void;
    /** Where to show the panel with the sentence checks, or null while it is closed. */
    checksSlot: HTMLElement | null;
    onCloseChecks: () => void;
    onEditQuestions: () => void;
    /** The words a prompt can ask for, by set. */
    words: WordLists;
    /** Works the words out again from what is known about each now, for a prompt that is about to be sent. */
    loadWords: () => Promise<WordLists>;
    picked: { word: string; nonce: number } | null;
    onOpenSettings: () => void;
    onUsage: (entry: UsageEntry) => void;
    /** The chat shown. Give the component this chat's id as its key, so a reply still arriving stops on a switch. */
    chat: StoredChat;
    /** Changes the messages of the chat with that id, which may no longer be the one shown. */
    onMessages: (chatId: string, change: (messages: ChatMessage[]) => ChatMessage[]) => void;
    onContext: (contextId: string) => void;
    onNewChat: () => void;
}

/** A stretch of the copy of the text behind the box, underlined if it is misspelled. */
function markedPart(part: MarkedPart, index: number) {
    // a word that was rated is tinted red, the more the less right it is
    const strength = part.value === null ? 0 : doubt(part.value);
    const style = strength > 0 ? { backgroundColor: `rgb(var(--doubt) / ${(strength * 0.6).toFixed(2)})` } : undefined;
    return part.issue
        ? (
            <mark key={index} className="misspelled" data-start={part.issue.start} style={style}>
                {part.text}
            </mark>
        )
        : <span key={index} className={style && "doubted"} style={style}>{part.text}</span>;
}

export function Chat(
    {
        settings,
        onSettingsChange,
        checksSlot,
        onCloseChecks,
        onEditQuestions,
        words,
        loadWords,
        picked,
        onOpenSettings,
        onUsage,
        chat,
        onMessages,
        onContext,
        onNewChat,
    }: Props,
) {
    const { id: chatId, messages } = chat;
    const setMessages = (change: (messages: ChatMessage[]) => ChatMessage[]) => onMessages(chatId, change);
    const [draft, setDraft] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [abort, setAbort] = useState<AbortController | null>(null);
    const abortRef = useRef<AbortController | null>(null);
    const endRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    const busy = abort !== null;
    // the context may have been deleted in settings since the chat started
    const context = settings.contexts.find((candidate) => candidate.id === chat.contextId) ?? settings.contexts[0];

    // stop a reply that is still arriving when another chat is shown
    useEffect(() => () => abortRef.current?.abort(), []);

    useEffect(() => {
        endRef.current?.scrollIntoView({ block: "end" });
    }, [messages]);

    // where the caret is in the draft, or null while the box is not in use
    const [caret, setCaret] = useState<number | null>(null);
    const questions = useMemo(() => requestQuestions(settings.questions), [settings.questions]);
    // Every request that profiling the sentences makes is counted, under the
    // chat it was made in.
    const countProfiling = useCallback(
        (used: ProfileUsage) =>
            onUsage({
                id: used.id,
                at: Date.now(),
                chatId,
                model: used.model,
                promptTokens: used.input_tokens,
                completionTokens: used.output_tokens,
                cost: used.cost,
            }),
        [chatId, onUsage],
    );
    const check = useLiveCheck(
        draft,
        caret,
        settings.apiKey,
        settings.profileModel,
        questions,
        settings.rateWords,
        settings.language,
        countProfiling,
    );
    // The checks panel goes on showing the sentence the caret was on after a
    // click in the panel has taken the caret out of the box.
    const lastCaret = useRef<number | null>(null);
    if (caret !== null) {
        lastCaret.current = caret;
    }
    const sentenceShown = draft ? sentenceAtCaret(check, lastCaret.current) : null;
    const backdropRef = useRef<HTMLDivElement>(null);
    const issues = spellingIssues(check, draft, caret);

    // The misspelled word the mouse is over, by where it starts in the draft,
    // and where to show its suggestions within the box.
    const [hint, setHint] = useState<{ start: number; left: number; bottom: number } | null>(null);
    const hintTimer = useRef<number>();
    const hintIssue = hint ? issues.find((issue) => issue.start === hint.start) : undefined;

    useEffect(() => () => clearTimeout(hintTimer.current), []);

    /**
     * Shows the suggestions for the misspelled word under the mouse, if any.
     * The mouse is over the text box, so the word is found through its
     * underline in the copy of the text behind the box.
     */
    function hoverAt(x: number, y: number) {
        const backdrop = backdropRef.current;
        if (!backdrop) {
            return;
        }
        const box = backdrop.getBoundingClientRect();
        for (const mark of backdrop.querySelectorAll("mark")) {
            // a word that is broken across two lines has two rectangles
            const under = [...mark.getClientRects()].find((rect) =>
                x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
            );
            if (under) {
                clearTimeout(hintTimer.current);
                setHint({
                    start: Number(mark.dataset.start),
                    left: under.left - box.left,
                    bottom: box.bottom - under.top + 2,
                });
                return;
            }
        }
        closeHintSoon();
    }

    /** Leaves a moment to move the mouse from the word onto its suggestions. */
    function closeHintSoon() {
        clearTimeout(hintTimer.current);
        hintTimer.current = window.setTimeout(() => setHint(null), 250);
    }

    function fix(issue: SpellingIssue, suggestion: string) {
        setDraft(applySuggestion(draft, issue, suggestion));
        setCaret(null);
        setHint(null);
        inputRef.current?.focus();
    }

    useEffect(() => {
        if (picked) {
            setDraft((current) => (current && !/\s$/.test(current) ? `${current} ` : current) + picked.word);
            inputRef.current?.focus();
        }
    }, [picked]);

    async function send() {
        const text = draft.trim();
        if (!text || busy) {
            return;
        }
        const history: ChatMessage[] = [...messages, { role: "user", content: text }];
        setMessages(() => [...history, { role: "assistant", content: "" }]);
        setDraft("");
        setError(null);

        const controller = new AbortController();
        abortRef.current = controller;
        setAbort(controller);
        try {
            // a set is worked out from the counts as they are now; if they cannot be had, from the last ones
            const lists = context.prompt.includes("{{words") ? await loadWords().catch(() => words) : words;
            const system = expandPrompt(context.prompt, lists, settings.language, settings.level).trim();
            const usage = await streamChat({
                apiKey: settings.apiKey,
                model: settings.model,
                messages: system ? [{ role: "system", content: system }, ...history] : history,
                signal: controller.signal,
                onText: (piece) =>
                    setMessages((current) => {
                        const reply = current[current.length - 1];
                        return [...current.slice(0, -1), { ...reply, content: reply.content + piece }];
                    }),
            });
            if (usage) {
                onUsage({
                    at: Date.now(),
                    chatId,
                    model: usage.model ?? settings.model,
                    promptTokens: usage.promptTokens,
                    completionTokens: usage.completionTokens,
                    cost: usage.cost,
                });
            }
        } catch (caught) {
            if (!controller.signal.aborted) {
                setError(caught instanceof Error ? caught.message : String(caught));
            }
        } finally {
            // a reply that never started is not kept
            setMessages((current) => (current[current.length - 1]?.content === "" ? current.slice(0, -1) : current));
            setAbort(null);
        }
    }

    function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        // Enter sends and Shift+Enter starts a new line, or the other way
        // round. A new line is what the box does with the key by itself.
        if (event.key === "Enter" && event.shiftKey !== settings.enterSends && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void send();
        }
    }

    function toggleQuestion(id: string) {
        onSettingsChange({
            ...settings,
            questions: settings.questions.map((question) =>
                question.id === id ? { ...question, enabled: !question.enabled } : question
            ),
        });
    }

    return (
        <>
            <section className="chat">
                <header className="chat-header">
                    <label className="context-picker">
                        <span>Context</span>
                        <select
                            value={context.id}
                            onChange={(event) => onContext(event.target.value)}
                            disabled={messages.length > 0}
                            title={messages.length > 0 ? "Start a new chat to change the context" : undefined}
                        >
                            {settings.contexts.map((candidate) => (
                                <option key={candidate.id} value={candidate.id}>{candidate.name}</option>
                            ))}
                        </select>
                    </label>
                    <button onClick={onNewChat}>New chat</button>
                </header>

                <div className="messages">
                    {messages.length === 0 && (
                        <div className="empty">
                            <h2>{context.name}</h2>
                            <p>
                                This chat starts with the “{context.name}” context. Write a message below, or click a
                                word on the left to add it.
                            </p>
                        </div>
                    )}
                    {messages.map((message, index) => (
                        <div key={index} className={`message ${message.role}`}>
                            {message.role === "assistant"
                                ? (message.content
                                    ? <Markdown>{message.content}</Markdown>
                                    : <span className="typing">…</span>)
                                : message.content}
                        </div>
                    ))}
                    {error && <div className="message error" role="alert">{error}</div>}
                    <div ref={endRef} />
                </div>

                {!settings.apiKey && (
                    <div className="notice">
                        Add your OpenRouter API key in{" "}
                        <button className="link" onClick={onOpenSettings}>Settings</button> to start chatting.
                    </div>
                )}
                <form
                    className="composer"
                    onSubmit={(event) => {
                        event.preventDefault();
                        void send();
                    }}
                >
                    <div className="composer-input">
                        {/* a copy of the text behind the box, which is what carries the underlines */}
                        <div className="composer-backdrop" ref={backdropRef} aria-hidden="true">
                            {sentenceParts(draft, check, issues).map(({ sentence, parts }, index) =>
                                sentence
                                    ? (
                                        // drawn by how far along the sentence is
                                        <span key={index} className="sentence" data-state={sentenceState(sentence)}>
                                            {parts.map(markedPart)}
                                        </span>
                                    )
                                    : <span key={index}>{parts.map(markedPart)}</span>
                            )}
                            {/* keeps a last, empty line as tall as it is in the box */}
                            {" "}
                        </div>
                        <textarea
                            ref={inputRef}
                            rows={2}
                            placeholder="Write a message"
                            aria-label="Message"
                            // the browser's own checker would underline the same words a second time
                            spellCheck={false}
                            value={draft}
                            onChange={(event) => {
                                setDraft(event.target.value);
                                setCaret(event.target.selectionStart);
                            }}
                            onSelect={(event) => setCaret(event.currentTarget.selectionStart)}
                            onBlur={() => setCaret(null)}
                            onScroll={(event) => {
                                if (backdropRef.current) {
                                    backdropRef.current.scrollTop = event.currentTarget.scrollTop;
                                }
                            }}
                            onKeyDown={onKeyDown}
                            onMouseMove={(event) => hoverAt(event.clientX, event.clientY)}
                            onMouseLeave={closeHintSoon}
                        />
                        {hintIssue && hint && (
                            <div
                                className="spelling-hint"
                                style={{ left: hint.left, bottom: hint.bottom }}
                                // moving from the word onto the hint must not close it
                                onMouseEnter={() => clearTimeout(hintTimer.current)}
                                onMouseLeave={closeHintSoon}
                            >
                                {hintIssue.suggestions.length === 0 && <span>Not in the dictionary</span>}
                                {hintIssue.suggestions.map((suggestion) => (
                                    <button
                                        key={suggestion}
                                        type="button"
                                        onClick={() => fix(hintIssue, suggestion)}
                                        title={`Replace “${hintIssue.word}” with “${suggestion}”`}
                                    >
                                        {suggestion}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    <div className="composer-send">
                        <label
                            className="check"
                            title={settings.enterSends
                                ? "Enter sends the message, and Shift+Enter starts a new line"
                                : "Enter starts a new line, and Shift+Enter sends the message"}
                        >
                            <input
                                type="checkbox"
                                checked={settings.enterSends}
                                onChange={(event) =>
                                    onSettingsChange({ ...settings, enterSends: event.target.checked })}
                            />
                            Enter sends
                        </label>
                        {busy
                            ? <button type="button" onClick={() => abort.abort()}>Stop</button>
                            : (
                                <button type="submit" className="primary" disabled={!draft.trim() || !settings.apiKey}>
                                    Send
                                </button>
                            )}
                    </div>
                </form>
            </section>
            {checksSlot && createPortal(
                <ChecksPanel
                    questions={settings.questions}
                    onToggle={toggleQuestion}
                    rateWords={settings.rateWords}
                    onRateWords={(rateWords) => onSettingsChange({ ...settings, rateWords })}
                    sentence={sentenceShown}
                    hasText={draft.trim() !== ""}
                    checkerRunning={check !== null}
                    hasKey={settings.apiKey !== ""}
                    localModel={check?.localModel ?? null}
                    remoteModel={settings.profileModel}
                    onEditQuestions={onEditQuestions}
                    onClose={onCloseChecks}
                />,
                checksSlot,
            )}
        </>
    );
}
