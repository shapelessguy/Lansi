// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";

import { t } from "../lib/i18n";
import type { ModelChoice } from "../lib/models";
import { type ChatMessage, streamChat } from "../lib/openrouter";
import type { ExerciseChat } from "../lib/practice";
import { SidePanel } from "./SidePanel";

interface Props {
    /** How the chat starts. Give the component a key of its own for each, so that each starts a chat anew. */
    start: ExerciseChat;
    apiKey: string;
    model: ModelChoice;
    /** What the replies used is counted under. */
    usageId: string;
    onClose: () => void;
}

/**
 * A chat an exercise opened, in a window over the page: the model answers
 * what the exercise asks first, which is not shown, and then the learner.
 * Nothing of it is kept once it is closed.
 */
export function ExerciseChatWindow({ start, apiKey, model, usageId, onClose }: Props) {
    // what was said after the system prompt, the opening first
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [draft, setDraft] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const request = useRef<AbortController | null>(null);
    const end = useRef<HTMLDivElement>(null);

    useEffect(() => {
        void reply([{ role: "user", content: start.opening }]);
        return () => request.current?.abort();
    }, []);
    useEffect(() => {
        end.current?.scrollIntoView({ block: "end" });
    }, [messages, busy, error]);

    /** Has the model answer the last of `asked`, its reply shown as it arrives; resolves with whether it did. */
    async function reply(asked: ChatMessage[]): Promise<boolean> {
        const controller = new AbortController();
        request.current = controller;
        setMessages([...asked, { role: "assistant", content: "" }]);
        setError(null);
        setBusy(true);
        try {
            await streamChat({
                apiKey,
                model,
                messages: [{ role: "system", content: start.system }, ...asked],
                signal: controller.signal,
                usageId,
                onText: (piece) =>
                    setMessages((current) => {
                        const arriving = current[current.length - 1];
                        return [...current.slice(0, -1), { ...arriving, content: arriving.content + piece }];
                    }),
            });
            return true;
        } catch (caught) {
            if (!controller.signal.aborted) {
                setMessages(asked.slice(0, -1));
                setError(caught instanceof Error ? caught.message : String(caught));
            }
            return false;
        } finally {
            // the box is not focused for the learner, which would bring up the keyboard of a phone
            if (!controller.signal.aborted) {
                setBusy(false);
            }
        }
    }

    async function send() {
        const text = draft.trim();
        if (!text || busy) {
            return;
        }
        setDraft("");
        if (!await reply([...messages, { role: "user", content: text }])) {
            // what was not answered goes back into the box, to be sent again
            setDraft(text);
        }
    }

    function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        // Enter sends here as it does where a selection is asked about, and Shift+Enter starts a new line
        if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            void send();
        }
    }

    const opened = messages.length > 0 && messages[0].content === start.opening;
    return (
        <SidePanel title={start.title || t("Ask about it")} onClose={onClose} flush>
            <div className="subchat-log" data-selectable>
                {messages.slice(1).map((message, index) =>
                    message.content && (
                        <div key={index} className={`message ${message.role}`}>
                            {message.role === "assistant" ? <Markdown>{message.content}</Markdown> : message.content}
                        </div>
                    )
                )}
                {busy && messages[messages.length - 1]?.content === "" && (
                    <div className="message assistant">
                        <span className="typing">…</span>
                    </div>
                )}
                {error && (
                    <div className="message error" role="alert">
                        {error}
                        {!opened && (
                            <button
                                type="button"
                                onClick={() => void reply([{ role: "user", content: start.opening }])}
                            >
                                {t("Try again")}
                            </button>
                        )}
                    </div>
                )}
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
                    rows={2}
                    placeholder={t("Ask a follow-up")}
                    title={t("Enter sends, and Shift+Enter starts a new line")}
                    aria-label={t("Ask a follow-up")}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={onKeyDown}
                />
                <button type="submit" className="primary" disabled={!draft.trim() || busy || !opened}>
                    {t("Send")}
                </button>
            </form>
        </SidePanel>
    );
}
