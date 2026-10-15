// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import type { ChatMessage } from "../lib/openrouter";
import { askAbout, type Asking, type Translated, usageEntry } from "../lib/translate";
import type { UsageEntry } from "../lib/usage";
import { SidePanel } from "./SidePanel";

interface Props {
    /** What the chat is about. Give the component a key of its own for each, so that each starts a chat anew. */
    translated: Translated;
    asking: Asking;
    onUsage: (entry: UsageEntry) => void;
    onClose: () => void;
}

/**
 * A chat at the side about a selection that was translated. It starts with
 * the passage and the translation, and lasts until it is closed or another
 * is started: nothing of it is kept.
 */
export function SubChat({ translated, asking, onUsage, onClose }: Props) {
    const { passage, translation } = translated;
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [draft, setDraft] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const request = useRef<AbortController | null>(null);
    const input = useRef<HTMLTextAreaElement>(null);
    const end = useRef<HTMLDivElement>(null);

    // the chat opens ready to be written in
    useEffect(() => {
        input.current?.focus();
    }, []);
    useEffect(() => () => request.current?.abort(), []);
    useEffect(() => {
        end.current?.scrollIntoView({ block: "end" });
    }, [messages, busy, error]);

    async function send() {
        const text = draft.trim();
        if (!text || busy) {
            return;
        }
        const asked: ChatMessage[] = [...messages, { role: "user", content: text }];
        const controller = new AbortController();
        request.current = controller;
        setMessages(asked);
        setDraft("");
        setError(null);
        setBusy(true);
        try {
            const { reply, usage } = await askAbout(translated, asked, asking, controller.signal);
            usage.forEach((used) => onUsage(usageEntry(used, Date.now())));
            setMessages([...asked, { role: "assistant", content: reply }]);
        } catch (caught) {
            if (controller.signal.aborted) {
                return;
            }
            // what was not answered goes back into the box, to be sent again
            setMessages(messages);
            setDraft(text);
            setError(caught instanceof Error ? caught.message : String(caught));
        } finally {
            if (!controller.signal.aborted) {
                setBusy(false);
                input.current?.focus();
            }
        }
    }

    function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        // Enter sends here whatever it does in the chat, and Shift+Enter starts a new line
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void send();
        }
    }

    return (
        <SidePanel title="Ask about it" onClose={onClose} flush>
            <div className="subchat-log" data-selectable>
                <blockquote className="subchat-passage">
                    {passage.before}
                    <mark>{passage.selection}</mark>
                    {passage.after}
                </blockquote>
                <div className="message assistant">
                    <p>{translation}</p>
                </div>
                {messages.map((message, index) => (
                    <div key={index} className={`message ${message.role}`}>
                        {message.role === "assistant" ? <Markdown>{message.content}</Markdown> : message.content}
                    </div>
                ))}
                {busy && (
                    <div className="message assistant">
                        <span className="typing">…</span>
                    </div>
                )}
                {error && <div className="message error" role="alert">{error}</div>}
                <div ref={end} />
            </div>
            <form
                className="subchat-composer"
                onSubmit={(event) => {
                    event.preventDefault();
                    void send();
                }}
            >
                <textarea
                    ref={input}
                    rows={2}
                    placeholder="Ask about the selection"
                    title="Enter sends, and Shift+Enter starts a new line"
                    aria-label="Question about the selection"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={onKeyDown}
                />
                <button type="submit" className="primary" disabled={!draft.trim() || busy}>Send</button>
            </form>
        </SidePanel>
    );
}
