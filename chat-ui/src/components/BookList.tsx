// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import { useEffect, useRef, useState } from "react";

import type { BooksState } from "../App";
import { type BookVersion, fetchCover, type ListedBook } from "../lib/books";
import { ask } from "../lib/dialogs";
import { locale, t } from "../lib/i18n";

interface Props {
    state: BooksState;
    /** The book or the version in the reader, by its id. */
    selectedId: string | null;
    /** The version of each book that was chosen last, by the ids of the book and of the version. */
    chosenVersions: Record<string, string>;
    /** Whether a book is being read in by the server. */
    adding: boolean;
    /** What was wrong with the last file that was added, if anything. */
    addError: string | null;
    /** Told the book or the version to read, by its id, with the book it is of. */
    onSelect: (id: string, book: ListedBook) => void;
    onAdd: (file: File) => void;
    /** Told the book or the version to remove, by its id, with the book it is of. */
    onDelete: (id: string, book: ListedBook) => void;
    /** Told the book a new version is to be made of, from the version of it that is chosen. */
    onEdit: (book: ListedBook) => void;
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

/** The version of a book that is chosen, by its id: the one chosen last if it is still there, or the book itself. */
export function chosenVersion(book: ListedBook, chosen: Record<string, string>): string {
    const id = chosen[book.id];
    return book.versions?.some((version) => version.id === id) ? id : book.id;
}

export function BookList(
    { state, selectedId, chosenVersions, adding, addError, onSelect, onAdd, onDelete, onEdit, onReload }: Props,
) {
    const fileInput = useRef<HTMLInputElement>(null);

    function confirmDelete(book: ListedBook) {
        const detail = book.versions?.length
            ? t("Its versions are deleted with it. This can't be undone.")
            : t("This can't be undone.");
        void ask(t("Delete “{name}”?", { name: book.title }), { detail }).then((agreed) =>
            agreed && onDelete(book.id, book)
        );
    }

    function confirmDeleteVersion(book: ListedBook, version: BookVersion) {
        void ask(t("Delete “{name}”?", { name: `${book.title} · ${version.name}` }), {
            detail: t("This can't be undone."),
        }).then((agreed) => agreed && onDelete(version.id, book));
    }

    return (
        <>
            <div className="sidebar-controls">
                <button onClick={() => fileInput.current?.click()} disabled={adding}>
                    {adding ? t("Reading the book…") : t("Add book")}
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
            {state.status === "loading" && <p className="sidebar-note">{t("Loading books…")}</p>}
            {state.status === "error" && (
                <div className="sidebar-note error">
                    <p>{state.message}</p>
                    <button onClick={onReload}>{t("Try again")}</button>
                </div>
            )}
            {state.status === "ready" && state.books.length === 0 && (
                <p className="sidebar-note">{t("EPUB books you add are kept here, as their text.")}</p>
            )}
            <ul className="chat-list">
                {state.status === "ready"
                    && state.books.map((book) => {
                        const chosen = chosenVersion(book, chosenVersions);
                        const open = book.id === selectedId
                            || book.versions?.some((version) => version.id === selectedId);
                        return (
                            <li key={book.id} className={open ? "chat-item book-item active" : "chat-item book-item"}>
                                <BookCover book={book} />
                                <button
                                    className="chat-open"
                                    onClick={() =>
                                        onSelect(chosen, book)}
                                    aria-current={open ? "true" : undefined}
                                >
                                    <span className="chat-title">{book.title}</span>
                                    <span className="chat-detail">
                                        {[
                                            book.author,
                                            new Date(book.addedAt).toLocaleDateString(locale(), {
                                                month: "short",
                                                day: "numeric",
                                            }),
                                        ].filter(Boolean).join(" · ")}
                                    </span>
                                </button>
                                <button
                                    className="icon-button chat-delete"
                                    onClick={() =>
                                        onEdit(book)}
                                    title={t("Make a new version")}
                                    aria-label={t("Make a new version")}
                                >
                                    ✎
                                </button>
                                <button
                                    className="icon-button chat-delete"
                                    onClick={() => confirmDelete(book)}
                                    title={t("Delete book")}
                                    aria-label={t("Delete book: {name}", { name: book.title })}
                                >
                                    ×
                                </button>
                                {book.versions && book.versions.length > 0 && (
                                    <ul
                                        className="book-versions"
                                        aria-label={t("Versions of {name}", { name: book.title })}
                                    >
                                        <li>
                                            <button
                                                aria-pressed={chosen === book.id}
                                                onClick={() => onSelect(book.id, book)}
                                            >
                                                {t("Original")}
                                            </button>
                                        </li>
                                        {book.versions.map((version) => (
                                            <li key={version.id}>
                                                <button
                                                    aria-pressed={chosen === version.id}
                                                    onClick={() => onSelect(version.id, book)}
                                                >
                                                    {version.name}
                                                </button>
                                                <button
                                                    className="version-delete"
                                                    onClick={() => confirmDeleteVersion(book, version)}
                                                    title={t("Delete version: {name}", { name: version.name })}
                                                    aria-label={t("Delete version: {name}", { name: version.name })}
                                                >
                                                    ×
                                                </button>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </li>
                        );
                    })}
            </ul>
        </>
    );
}
