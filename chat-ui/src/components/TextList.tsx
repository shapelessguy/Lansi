// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import type { TextsState } from "../App";

interface Props {
    state: TextsState;
    selectedId: string | null;
    onSelect: (id: string | null) => void;
    onReload: () => void;
}

export function TextList({ state, selectedId, onSelect, onReload }: Props) {
    return (
        <>
            <div className="sidebar-controls">
                <button onClick={() => onSelect(null)}>New text</button>
            </div>
            {state.status === "loading" && <p className="sidebar-note">Loading texts…</p>}
            {state.status === "error" && (
                <div className="sidebar-note error">
                    <p>{state.message}</p>
                    <button onClick={onReload}>Try again</button>
                </div>
            )}
            {state.status === "ready" && state.texts.length === 0 && (
                <p className="sidebar-note">Texts you generate are kept here.</p>
            )}
            <ul className="chat-list">
                {state.status === "ready"
                    && state.texts.map((text) => (
                        <li key={text.id} className={text.id === selectedId ? "chat-item active" : "chat-item"}>
                            <button
                                className="chat-open"
                                onClick={() =>
                                    onSelect(text.id)}
                                aria-current={text.id === selectedId ? "true" : undefined}
                            >
                                <span className="chat-title">{text.title}</span>
                                <span className="chat-detail">
                                    {new Date(text.createdAt).toLocaleDateString(undefined, {
                                        month: "short",
                                        day: "numeric",
                                    })}
                                    {" · "}
                                    {text.audio ? "with audio" : "no audio yet"}
                                </span>
                            </button>
                        </li>
                    ))}
            </ul>
        </>
    );
}
