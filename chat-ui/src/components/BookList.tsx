// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import type { BooksState } from "../App";
import { fetchCover, type ListedBook } from "../lib/books";
import { ask } from "../lib/dialogs";

interface Props {
    state: BooksState;
    selectedId: string | null;
    /** Whether a book is being read in by the server. */
    adding: boolean;
    /** What was wrong with the last file that was added, if anything. */
    addError: string | null;
    onSelect: (id: string) => void;
    onAdd: (file: File) => void;
    onDelete: (id: string) => void;
    onReload: () => void;
}

/** The picture on the cover of a book, or the first letter of its title if it has none. */
function BookCover({ book }: { book: ListedBook }) {
    const [picture, setPicture] = useState<string | null>(null);
    useEffect(() => {
        setPicture(null);
        if (!book.cover) {
            return;
        }
        let current = true;
        fetchCover(book.id).then((address) => current && setPicture(address), () => undefined);
        return () => {
            current = false;
        };
    }, [book.id, book.cover]);

    return picture
        ? <img className="book-cover" src={picture} alt="" />
        : <div className="book-cover" aria-hidden="true">{book.title.trim().charAt(0).toUpperCase()}</div>;
}

export function BookList(
    { state, selectedId, adding, addError, onSelect, onAdd, onDelete, onReload }: Props,
) {
    const fileInput = useRef<HTMLInputElement>(null);

    function confirmDelete(book: ListedBook) {
        void ask(`Delete “${book.title}”?`, { detail: "This can't be undone." }).then((agreed) =>
            agreed && onDelete(book.id)
        );
    }

    return (
        <>
            <div className="sidebar-controls">
                <button onClick={() => fileInput.current?.click()} disabled={adding}>
                    {adding ? "Reading the book…" : "Add book"}
                </button>
                <input
                    ref={fileInput}
                    type="file"
                    accept=".epub,application/epub+zip"
                    hidden
                    onChange={(event) => {
                        const file = event.target.files?.[0];
                        // the same file can be chosen again after it was refused
                        event.target.value = "";
                        if (file) {
                            onAdd(file);
                        }
                    }}
                />
            </div>
            {addError && <p className="sidebar-note error" role="alert">{addError}</p>}
            {state.status === "loading" && <p className="sidebar-note">Loading books…</p>}
            {state.status === "error" && (
                <div className="sidebar-note error">
                    <p>{state.message}</p>
                    <button onClick={onReload}>Try again</button>
                </div>
            )}
            {state.status === "ready" && state.books.length === 0 && (
                <p className="sidebar-note">EPUB books you add are kept here, as their text.</p>
            )}
            <ul className="chat-list">
                {state.status === "ready"
                    && state.books.map((book) => (
                        <li key={book.id} className={book.id === selectedId ? "chat-item active" : "chat-item"}>
                            <BookCover book={book} />
                            <button
                                className="chat-open"
                                onClick={() =>
                                    onSelect(book.id)}
                                aria-current={book.id === selectedId ? "true" : undefined}
                            >
                                <span className="chat-title">{book.title}</span>
                                <span className="chat-detail">
                                    {[
                                        book.author,
                                        new Date(book.addedAt).toLocaleDateString(undefined, {
                                            month: "short",
                                            day: "numeric",
                                        }),
                                    ].filter(Boolean).join(" · ")}
                                </span>
                            </button>
                            <button
                                className="icon-button chat-delete"
                                onClick={() =>
                                    confirmDelete(book)}
                                title="Delete book"
                                aria-label={`Delete book: ${book.title}`}
                            >
                                ×
                            </button>
                        </li>
                    ))}
            </ul>
        </>
    );
}
