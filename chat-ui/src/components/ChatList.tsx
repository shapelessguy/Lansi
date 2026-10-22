// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { chatTitle, type StoredChat } from "../lib/chats";
import { ask } from "../lib/dialogs";

interface Props {
    /** Most recent first. */
    chats: StoredChat[];
    activeId: string;
    onSelect: (id: string) => void;
    onDelete: (id: string) => void;
    onNewChat: () => void;
}

function when(at: number): string {
    const date = new Date(at);
    const sameDay = date.toDateString() === new Date().toDateString();
    return sameDay
        ? date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
        : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function ChatList({ chats, activeId, onSelect, onDelete, onNewChat }: Props) {
    function confirmDelete(chat: StoredChat) {
        void ask(`Delete “${chatTitle(chat)}”?`, { detail: "This can't be undone." }).then((agreed) =>
            agreed && onDelete(chat.id)
        );
    }

    return (
        <>
            <div className="sidebar-controls">
                <button onClick={onNewChat}>New chat</button>
            </div>
            {chats.length === 0 && <p className="sidebar-note">Chats you have are kept here.</p>}
            <ul className="chat-list">
                {chats.map((chat) => (
                    <li key={chat.id} className={chat.id === activeId ? "chat-item active" : "chat-item"}>
                        <button
                            className="chat-open"
                            onClick={() =>
                                onSelect(chat.id)}
                            aria-current={chat.id === activeId ? "true" : undefined}
                        >
                            <span className="chat-title">{chatTitle(chat)}</span>
                            <span className="chat-detail">
                                {when(chat.updatedAt)} · {chat.messages.length} messages
                            </span>
                        </button>
                        <button
                            className="icon-button chat-delete"
                            onClick={() =>
                                confirmDelete(chat)}
                            title="Delete chat"
                            aria-label={`Delete chat: ${chatTitle(chat)}`}
                        >
                            ×
                        </button>
                    </li>
                ))}
            </ul>
        </>
    );
}
