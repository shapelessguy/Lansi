// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import type { BooksState } from "../App";
import { describeSync, fetchCover, type FolderSync, type ListedBook } from "../lib/books";

interface Props {
    state: BooksState;
    selectedId: string | null;
    /** Whether a book is being read in by the server. */
    adding: boolean;
    /** What was wrong with the last file that was added, if anything. */
    addError: string | null;
    /** What the taking of the books from a folder is doing, once that is known. */
    sync: FolderSync | null;
    onSelect: (id: string) => void;
    onAdd: (file: File) => void;
    onDelete: (id: string) => void;
    onReload: () => void;
    /** Has the books taken from that folder from now on, or from none if it is empty. */
    onFolder: (folder: string) => void;
    /** Has the folder looked through now. */
    onSync: () => void;
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
    { state, selectedId, adding, addError, sync, onSelect, onAdd, onDelete, onReload, onFolder, onSync }: Props,
) {
    const fileInput = useRef<HTMLInputElement>(null);
    // the folder as it is being typed
    const [folder, setFolder] = useState("");
    const chosen = sync?.folder ?? "";
    useEffect(() => setFolder(chosen), [chosen]);

    function confirmDelete(book: ListedBook) {
        if (window.confirm(`Delete “${book.title}”? This can't be undone.`)) {
            onDelete(book.id);
        }
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
                {sync && (
                    <>
                        <form
                            className="sort-row"
                            onSubmit={(event) => {
                                event.preventDefault();
                                if (folder.trim() === chosen) {
                                    onSync();
                                } else {
                                    onFolder(folder.trim());
                                }
                            }}
                        >
                            <input
                                type="text"
                                className="book-folder"
                                spellCheck={false}
                                aria-label="Folder to take e-books from"
                                title="A folder on the machine the app runs on. Its e-books, and those of the folders inside it, are kept here."
                                placeholder={sync.suggestion ? `${sync.suggestion}\\Books` : "Folder with e-books"}
                                value={folder}
                                onChange={(event) => setFolder(event.target.value)}
                            />
                            <button type="submit" disabled={folder.trim() === chosen && !chosen}>
                                {folder.trim() === chosen ? "Sync" : "Use"}
                            </button>
                        </form>
                        <small
                            className={sync.state === "missing" ? "import-status error" : "import-status"}
                            title={sync.unread.map((unread) => `${unread.file}: ${unread.reason}`).join("\n")}
                        >
                            {describeSync(sync)}
                        </small>
                    </>
                )}
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
                                title={book.source ?? undefined}
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
                            {/* a book of the folder is removed by taking its file out of the folder */}
                            {!(book.source && chosen) && (
                                <button
                                    className="icon-button chat-delete"
                                    onClick={() => confirmDelete(book)}
                                    title="Delete book"
                                    aria-label={`Delete book: ${book.title}`}
                                >
                                    ×
                                </button>
                            )}
                        </li>
                    ))}
            </ul>
        </>
    );
}
