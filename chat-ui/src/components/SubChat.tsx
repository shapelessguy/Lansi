// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { t } from "../lib/i18n";
import type { ChatMessage } from "../lib/openrouter";
import type { BackgroundTask } from "../lib/tasks";
import { askAbout, type Asking, endChatAbout, type Translated, usageEntry } from "../lib/translate";
import type { UsageEntry } from "../lib/usage";
import { SidePanel } from "./SidePanel";

interface Props {
    /** What the chat is about. Give the component a key of its own for each, so that each starts a chat anew. */
    translated: Translated;
    asking: Asking;
    onUsage: (entry: UsageEntry) => void;
    /** Told the task the server started to log what was asked, once the chat is over. */
    onTask: (task: BackgroundTask) => void;
    onClose: () => void;
}

/**
 * A chat about a selection that was translated, in a window over the page. It starts with
 * the passage and the translation, and lasts until it is closed or another
 * is started, or the page is left. Nothing of it is kept but the logs the
 * server has written of what was asked, once it is over.
 */
export function SubChat({ translated, asking, onUsage, onTask, onClose }: Props) {
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
    // what the chat is over with, as it is then
    const latest = useRef({ translated, messages, asking, onTask });
    latest.current = { translated, messages, asking, onTask };
    useEffect(() => {
        let ended = false;
        function end(leaving: boolean) {
            const { translated, messages, asking, onTask } = latest.current;
            if (ended || !messages.some((message) => message.role === "user")) {
                return;
            }
            ended = true;
            endChatAbout(translated, messages, asking, leaving).then(
                (task) => task && onTask(task),
                (error) => console.error("what was asked could not be logged:", error),
            );
        }
        const leave = () => end(true);
        window.addEventListener("pagehide", leave);
        return () => {
            window.removeEventListener("pagehide", leave);
            end(false);
        };
    }, []);
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
        <SidePanel title={t("Ask about it")} onClose={onClose} flush>
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
                    placeholder={t("Ask about the selection")}
                    title={t("Enter sends, and Shift+Enter starts a new line")}
                    aria-label={t("Question about the selection")}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={onKeyDown}
                />
                <button type="submit" className="primary" disabled={!draft.trim() || busy}>{t("Send")}</button>
            </form>
        </SidePanel>
    );
}
