// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type KeyboardEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Markdown from "react-markdown";

import { isAtEnd, type StoredChat } from "../lib/chats";
import { type ProfileUsage, sentenceAtCaret } from "../lib/checker";
import type { Where } from "../lib/logs";
import { type ChatMessage, streamChat } from "../lib/openrouter";
import { requestQuestions } from "../lib/questions";
import type { WordLists } from "../lib/sets";
import { expandPrompt, type Settings } from "../lib/settings";
import { allowPlaying, speakMark } from "../lib/speaking";
import type { UsageEntry } from "../lib/usage";
import { ChecksPanel } from "./ChecksPanel";
import { useWritingCheck } from "./WritingChecks";

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
    /** Has a message of a chat read aloud: the one at that place among its messages, which says that. */
    onSpeak: (chatId: string, place: number, text: string) => void;
    /** The chat shown. Give the component this chat's id as its key, so a reply still arriving stops on a switch. */
    chat: StoredChat;
    /** Changes the messages of the chat with that id, which may no longer be the one shown. */
    onMessages: (chatId: string, change: (messages: ChatMessage[]) => ChatMessage[]) => void;
    onContext: (contextId: string) => void;
    onNewChat: () => void;
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
        onSpeak,
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
    // The messages, and whether they are scrolled to their end, which is
    // where they are kept as more arrives. Scrolled up to read something
    // earlier, they stay where they are.
    const listRef = useRef<HTMLDivElement>(null);
    const atEnd = useRef(true);
    const inputRef = useRef<HTMLTextAreaElement>(null);

    const busy = abort !== null;
    // the context may have been deleted in settings since the chat started
    const context = settings.contexts.find((candidate) => candidate.id === chat.contextId) ?? settings.contexts[0];

    // stop a reply that is still arriving when another chat is shown
    useEffect(() => () => abortRef.current?.abort(), []);

    const keepAtEnd = useCallback(() => {
        const list = listRef.current;
        if (list && atEnd.current) {
            list.scrollTop = list.scrollHeight;
        }
    }, []);
    // whatever makes the messages longer: a message, a piece of a reply, an error, the button under a finished reply
    useLayoutEffect(keepAtEnd, [keepAtEnd, messages, error, abort]);
    // and whatever makes the room for them smaller, or shows them again after they were hidden
    useEffect(() => {
        const list = listRef.current;
        if (!list) {
            return;
        }
        const observer = new ResizeObserver(keepAtEnd);
        observer.observe(list);
        return () => observer.disconnect();
    }, [keepAtEnd]);

    const questions = useMemo(() => requestQuestions(settings.questions), [settings.questions]);
    // Every request that profiling the sentences makes is counted, under the
    // chat it was made in.
    const countProfiling = useCallback(
        (used: ProfileUsage) =>
            onUsage({
                id: used.id,
                at: Date.now(),
                category: "checking",
                chatId,
                model: used.model,
                promptTokens: used.input_tokens,
                completionTokens: used.output_tokens,
                cost: used.cost,
            }),
        [chatId, onUsage],
    );
    // the spelling is checked as in every text box, and the sentences profiled as well
    const { check, lastCaret } = useWritingCheck(
        inputRef,
        {
            apiKey: settings.apiKey,
            model: settings.profileModel,
            questions,
            rateWords: settings.rateWords,
        },
        countProfiling,
    );
    // The checks panel goes on showing the sentence the caret was on after a
    // click in the panel has taken the caret out of the box.
    const sentenceShown = draft ? sentenceAtCaret(check, lastCaret) : null;

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
        // The reply is read aloud only once it is there, by when the click
        // or the key that sends this no longer counts for the browser.
        if (settings.speakReplies) {
            allowPlaying();
        }
        // what is sent is shown, wherever the messages were scrolled to
        atEnd.current = true;
        const history: ChatMessage[] = [...messages, { role: "user", content: text }];
        setMessages(() => [...history, { role: "assistant", content: "" }]);
        setDraft("");
        setError(null);

        const controller = new AbortController();
        abortRef.current = controller;
        setAbort(controller);
        // what the reply says, as it arrives
        let reply = "";
        try {
            // a set is worked out from the counts as they are now; if they cannot be had, from the last ones
            const lists = context.prompt.includes("{{words") ? await loadWords().catch(() => words) : words;
            const system = expandPrompt(context.prompt, lists, settings.language, settings.level).trim();
            const usage = await streamChat({
                apiKey: settings.apiKey,
                model: settings.model,
                messages: system ? [{ role: "system", content: system }, ...history] : history,
                signal: controller.signal,
                onText: (piece) => {
                    reply += piece;
                    setMessages((current) => {
                        const arriving = current[current.length - 1];
                        return [...current.slice(0, -1), { ...arriving, content: arriving.content + piece }];
                    });
                },
            });
            // the reply is the message after those that were sent
            if (settings.speakReplies && reply.trim()) {
                onSpeak(chatId, history.length, reply);
            }
            if (usage) {
                onUsage({
                    at: Date.now(),
                    category: "chat",
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
                    <label className="check" title="Reads each reply aloud once it has arrived. The audio is kept.">
                        <input
                            type="checkbox"
                            checked={settings.speakReplies}
                            onChange={(event) => onSettingsChange({ ...settings, speakReplies: event.target.checked })}
                        />
                        Speak replies
                    </label>
                    <button onClick={onNewChat}>New chat</button>
                </header>

                <div
                    className="messages"
                    data-selectable
                    data-where={JSON.stringify({ kind: "chat", id: chat.id } satisfies Where)}
                    ref={listRef}
                    onScroll={(event) => {
                        const list = event.currentTarget;
                        // nothing is shown, and so nothing scrolled, while another activity is
                        if (list.clientHeight > 0) {
                            atEnd.current = isAtEnd(list.scrollHeight, list.scrollTop, list.clientHeight);
                        }
                    }}
                >
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
                                ? (
                                    <>
                                        {/* to the left of the reply; one that is still arriving is not read yet */}
                                        <button
                                            className="icon-button message-speak"
                                            data-speak={speakMark(chatId, index)}
                                            onClick={() => onSpeak(chatId, index, message.content)}
                                            disabled={!message.content || (busy && index === messages.length - 1)}
                                            title="Read aloud"
                                            aria-label="Read this reply aloud"
                                        >
                                            🔊
                                        </button>
                                        <div className="message-body">
                                            <div className="message-text">
                                                {message.content
                                                    ? <Markdown>{message.content}</Markdown>
                                                    : <span className="typing">…</span>}
                                            </div>
                                        </div>
                                    </>
                                )
                                : message.content}
                        </div>
                    ))}
                    {error && <div className="message error" role="alert">{error}</div>}
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
                    <div className="composer-input" data-writing>
                        <textarea
                            ref={inputRef}
                            rows={2}
                            placeholder="Write a message"
                            aria-label="Message"
                            // the browser's own checker would underline the same words a second time
                            spellCheck={false}
                            value={draft}
                            onChange={(event) => setDraft(event.target.value)}
                            onKeyDown={onKeyDown}
                        />
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
