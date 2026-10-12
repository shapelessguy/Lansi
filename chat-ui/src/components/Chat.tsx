// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import type { StoredChat } from "../lib/chats";
import { applySuggestion, markedParts, type SpellingIssue, spellingIssues, useLiveCheck } from "../lib/checker";
import { type ChatMessage, streamChat } from "../lib/openrouter";
import { expandPrompt, type Settings } from "../lib/settings";
import type { UsageEntry } from "../lib/usage";
import type { Word } from "../lib/words";

interface Props {
    settings: Settings;
    words: Word[];
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

export function Chat(
    { settings, words, picked, onOpenSettings, onUsage, chat, onMessages, onContext, onNewChat }: Props,
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
    const check = useLiveCheck(draft, caret, settings.apiKey, settings.profileModel);
    const backdropRef = useRef<HTMLDivElement>(null);
    const issues = spellingIssues(check, draft, caret);

    // Count what profiling the sentences cost. A profile is sent along with
    // its sentence every second from then on; its id keeps it from being
    // counted more than once.
    useEffect(() => {
        for (const { profile } of check?.sentences ?? []) {
            if (profile) {
                onUsage({
                    id: profile.id,
                    at: Date.now(),
                    chatId,
                    model: profile.model,
                    promptTokens: profile.input_tokens,
                    completionTokens: profile.output_tokens,
                    cost: profile.cost,
                });
            }
        }
    }, [check, chatId, onUsage]);

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
        const system = expandPrompt(context.prompt, words).trim();
        try {
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
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void send();
        }
    }

    return (
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
                            This chat starts with the “{context.name}” context. Write a message below, or click a word
                            on the left to add it.
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
                    Add your OpenRouter API key in <button className="link" onClick={onOpenSettings}>Settings</button>
                    {" "}
                    to start chatting.
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
                        {markedParts(draft, issues).map((part, index) =>
                            part.issue
                                ? (
                                    <mark key={index} className="misspelled" data-start={part.issue.start}>
                                        {part.text}
                                    </mark>
                                )
                                : <span key={index}>{part.text}</span>
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
                {busy
                    ? <button type="button" onClick={() => abort.abort()}>Stop</button>
                    : (
                        <button type="submit" className="primary" disabled={!draft.trim() || !settings.apiKey}>
                            Send
                        </button>
                    )}
            </form>
        </section>
    );
}
